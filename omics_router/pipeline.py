"""Pipeline orchestration for Omics-GEM Router workflows."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .cobra_runner import cobrapy_available
from .constraints import read_csv_records, write_csv, write_json
from .gecko_runner import resolve_matlab_command
from .local_config import apply_local_backend_env
from .memote_runner import resolve_memote_command
from .pytfa_runner import check_python_dependencies
from .troppo_runner import troppo_available


OK_STEP_STATUSES = {"completed", "completed_with_failures", "skipped", "dry_run"}


@dataclass(slots=True)
class PipelineStep:
    """A command-backed pipeline step."""

    step_id: str
    label: str
    command: list[str]
    required_inputs: list[str] = field(default_factory=list)
    expected_outputs: list[str] = field(default_factory=list)
    status_json: str | None = None
    status_csv: str | None = None
    optional: bool = False


@dataclass(slots=True)
class PipelineRunResult:
    """Summary returned by a pipeline run."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]


def run_pipeline(
    steps: list[PipelineStep],
    output_dir: str | Path,
    cwd: str | Path | None = None,
    dry_run: bool = False,
    continue_on_error: bool = True,
    timeout_seconds: int = 7200,
    backend_python_cmd: str | None = None,
) -> PipelineRunResult:
    """Run a list of command-backed steps and write a manifest."""

    apply_local_backend_env()
    root = Path(cwd) if cwd else Path.cwd()
    output = Path(output_dir)
    if not output.is_absolute():
        output = root / output
    output.mkdir(parents=True, exist_ok=True)
    log_dir = output / "logs"
    log_dir.mkdir(exist_ok=True)

    files = {
        "steps": str(output / "pipeline_steps.csv"),
        "backend_status": str(output / "pipeline_backend_status.csv"),
        "manifest": str(output / "pipeline_run_manifest.json"),
    }

    step_rows = []
    for index, step in enumerate(steps, start=1):
        row = run_pipeline_step(
            step,
            index=index,
            cwd=root,
            log_dir=log_dir,
            dry_run=dry_run,
            timeout_seconds=timeout_seconds,
        )
        step_rows.append(row)
        if not continue_on_error and row["status"] not in OK_STEP_STATUSES:
            break

    backend_rows = build_backend_status(backend_python_cmd)
    write_csv(files["steps"], step_rows)
    write_csv(files["backend_status"], backend_rows)
    status = classify_pipeline_status(step_rows, dry_run=dry_run)
    message = build_pipeline_message(step_rows, status)
    write_json(
        files["manifest"],
        {
            "status": status,
            "message": message,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "cwd": str(root),
            "dry_run": dry_run,
            "continue_on_error": continue_on_error,
            "timeout_seconds": timeout_seconds,
            "step_count": len(step_rows),
            "steps": step_rows,
            "backend_status": backend_rows,
            "files": files,
        },
    )
    return PipelineRunResult(status=status, output_dir=str(output), message=message, files=files)


def run_pipeline_step(
    step: PipelineStep,
    *,
    index: int,
    cwd: Path,
    log_dir: Path,
    dry_run: bool,
    timeout_seconds: int,
) -> dict[str, object]:
    """Run one pipeline step and return a row for `pipeline_steps.csv`."""

    stdout_log = log_dir / f"{index:02d}_{step.step_id}.stdout.log"
    stderr_log = log_dir / f"{index:02d}_{step.step_id}.stderr.log"
    missing_inputs = [path for path in step.required_inputs if not _resolve_path(path, cwd).exists()]
    started_at = datetime.now().isoformat(timespec="seconds")
    return_code = None
    elapsed = 0.0
    message = ""

    if missing_inputs:
        status = "skipped" if step.optional else "input_missing"
        message = "Missing required inputs: " + ", ".join(missing_inputs)
        stdout_log.write_text("", encoding="utf-8")
        stderr_log.write_text(message, encoding="utf-8")
    elif dry_run:
        status = "dry_run"
        message = "Pipeline dry run; command was not executed."
        stdout_log.write_text("", encoding="utf-8")
        stderr_log.write_text("", encoding="utf-8")
    else:
        start = time.perf_counter()
        try:
            completed = subprocess.run(
                step.command,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
            elapsed = time.perf_counter() - start
            return_code = completed.returncode
            stdout_log.write_text(completed.stdout or "", encoding="utf-8")
            stderr_log.write_text(completed.stderr or "", encoding="utf-8")
            if completed.returncode == 0:
                status = "completed"
                message = "Command completed."
            elif step.optional:
                status = "skipped"
                message = "Optional command failed; skipped external execution."
            else:
                status = "failed"
                message = "Command failed."
        except subprocess.TimeoutExpired as exc:
            elapsed = time.perf_counter() - start
            status = "skipped" if step.optional else "failed"
            message = (
                f"Optional command timed out after {timeout_seconds} seconds; skipped external execution."
                if step.optional
                else f"Command timed out after {timeout_seconds} seconds."
            )
            stdout_log.write_text(_safe_text(exc.stdout), encoding="utf-8")
            stderr_log.write_text(_safe_text(exc.stderr), encoding="utf-8")

        if status == "completed":
            source_status = read_step_status(step, cwd)
            if source_status:
                status = source_status.get("status") or status
                message = source_status.get("message") or message
            missing_outputs = [path for path in step.expected_outputs if not _resolve_path(path, cwd).exists()]
            if missing_outputs and not step.optional:
                status = "missing_outputs"
                message = "Missing expected outputs: " + ", ".join(missing_outputs)

    existing_outputs = [path for path in step.expected_outputs if _resolve_path(path, cwd).exists()]
    return {
        "step_index": index,
        "step_id": step.step_id,
        "label": step.label,
        "status": status,
        "message": message,
        "optional": step.optional,
        "return_code": return_code,
        "elapsed_seconds": round(elapsed, 3),
        "started_at": started_at,
        "command": format_command(step.command),
        "required_inputs": ";".join(step.required_inputs),
        "missing_inputs": ";".join(missing_inputs),
        "expected_outputs": ";".join(step.expected_outputs),
        "existing_outputs": ";".join(existing_outputs),
        "stdout_log": str(stdout_log),
        "stderr_log": str(stderr_log),
    }


def build_ecoli_pipeline_steps(
    python_cmd: str | None = None,
    example_dir: str | Path = "examples/ecoli",
    run_dir: str | Path | None = None,
    model_filename: str = "iJO1366 (1).xml",
) -> list[PipelineStep]:
    """Return the default E. coli pipeline for a demo or real-data directory."""

    python = python_cmd or sys.executable or "python"
    example = _path_text(example_dir)
    run_root = _path_text(run_dir or example_dir)
    model = _join_path(example, model_filename)
    constraints = _join_path(run_root, "generated_constraints")
    cobra_results = _join_path(run_root, "cobra_results")
    evidence_mode_results = _join_path(run_root, "evidence_mode_results")
    ml_results = _join_path(run_root, "ml_results")
    model_qc_results = _join_path(run_root, "model_qc_results")
    memote_results = _join_path(run_root, "memote_results")
    transcriptomics_flux_results = _join_path(run_root, "transcriptomics_flux_results")
    context_results = _join_path(run_root, "context_results")
    troppo_results = _join_path(run_root, "troppo_results")
    troppo_method_results = _join_path(run_root, "troppo_method_results")
    interpretation_results = _join_path(run_root, "interpretation_results")
    minn_export = _join_path(run_root, "minn_export")
    enzyme_results = _join_path(run_root, "enzyme_results")
    gecko_package = _join_path(run_root, "gecko_package")
    gecko_run_results = _join_path(run_root, "gecko_run_results")
    pytfa_package = _join_path(run_root, "pytfa_package")
    pytfa_run_results = _join_path(run_root, "pytfa_run_results")
    return [
        PipelineStep(
            step_id="constraints",
            label="Generate normalized omics constraints",
            command=[
                python,
                "tools/build_ecoli_demo_constraints.py",
                "--example-dir",
                example,
                "--model",
                model_filename,
                "--output-dir",
                constraints,
            ],
            required_inputs=[
                model,
                _join_path(example, "ecoli_transcriptomics_tpm.csv"),
                _join_path(example, "ecoli_absolute_proteomics.csv"),
                _join_path(example, "ecoli_relative_proteomics.csv"),
                _join_path(example, "ecoli_extracellular_metabolomics.csv"),
                _join_path(example, "ecoli_intracellular_metabolomics.csv"),
                _join_path(example, "ecoli_fluxomics_13c_mfa.csv"),
                _join_path(example, "ecoli_ml_kcat_priors.csv"),
            ],
            expected_outputs=[f"{constraints}/manifest.json", f"{constraints}/run_config.generated.json"],
        ),
        PipelineStep(
            step_id="evidence_mode_comparison",
            label="Compare transcriptomics, proteomics, and consensus evidence modes",
            command=[
                python,
                "tools/compare_evidence_modes.py",
                "--constraints-dir",
                constraints,
                "--output-dir",
                evidence_mode_results,
            ],
            required_inputs=[
                f"{constraints}/context_reaction_policy.csv",
                f"{constraints}/fastcore_core_reactions.csv",
                f"{constraints}/reaction_expression_evidence.csv",
                f"{constraints}/relative_protein_context_reaction_policy.csv",
                f"{constraints}/relative_protein_fastcore_core_reactions.csv",
                f"{constraints}/relative_protein_reaction_evidence.csv",
                f"{constraints}/consensus_context_reaction_policy.csv",
                f"{constraints}/consensus_fastcore_core_reactions.csv",
                f"{constraints}/multi_omics_consensus_reaction_evidence.csv",
            ],
            expected_outputs=[f"{evidence_mode_results}/evidence_mode_comparison_manifest.json"],
            status_json=f"{evidence_mode_results}/evidence_mode_comparison_manifest.json",
        ),
        PipelineStep(
            step_id="model_qc",
            label="Run lightweight GEM model QC",
            command=[python, "tools/run_model_qc.py", "--model", model, "--output-dir", model_qc_results],
            required_inputs=[model],
            expected_outputs=[f"{model_qc_results}/model_qc_manifest.json"],
            status_json=f"{model_qc_results}/model_qc_manifest.json",
        ),
        PipelineStep(
            step_id="memote",
            label="Stage or run MEMOTE snapshot report",
            command=[python, "tools/run_memote_external.py", "--model", model, "--output-dir", memote_results],
            required_inputs=[model],
            expected_outputs=[f"{memote_results}/memote_external_run_summary.csv"],
            status_csv=f"{memote_results}/memote_external_run_summary.csv",
            optional=True,
        ),
        PipelineStep(
            step_id="cobra",
            label="Run COBRApy FBA, pFBA, and targeted FVA",
            command=[
                python,
                "tools/run_cobra_baseline.py",
                "--model",
                model,
                "--constraints-dir",
                constraints,
                "--output-dir",
                cobra_results,
            ],
            required_inputs=[model, f"{constraints}/exchange_bounds.csv", f"{constraints}/flux_validation_targets.csv"],
            expected_outputs=[f"{cobra_results}/cobra_runner_manifest.json"],
            status_json=f"{cobra_results}/cobra_runner_manifest.json",
        ),
        PipelineStep(
            step_id="transcriptomics_flux",
            label="Run E-Flux and delta-FBA-lite from transcriptomics",
            command=[
                python,
                "tools/run_transcriptomics_flux.py",
                "--model",
                model,
                "--constraints-dir",
                constraints,
                "--output-dir",
                transcriptomics_flux_results,
            ],
            required_inputs=[
                model,
                f"{constraints}/exchange_bounds.csv",
                f"{constraints}/reaction_expression_evidence.csv",
                f"{constraints}/flux_validation_targets.csv",
            ],
            expected_outputs=[f"{transcriptomics_flux_results}/transcriptomics_flux_manifest.json"],
            status_json=f"{transcriptomics_flux_results}/transcriptomics_flux_manifest.json",
        ),
        PipelineStep(
            step_id="context_feasibility",
            label="Check consensus context delete-candidate feasibility",
            command=[
                python,
                "tools/run_context_feasibility.py",
                "--model",
                model,
                "--constraints-dir",
                constraints,
                "--output-dir",
                context_results,
                "--evidence-mode",
                "consensus",
            ],
            required_inputs=[model, f"{constraints}/exchange_bounds.csv", f"{constraints}/consensus_context_reaction_policy.csv"],
            expected_outputs=[f"{context_results}/context_feasibility_manifest.json"],
            status_json=f"{context_results}/context_feasibility_manifest.json",
        ),
        PipelineStep(
            step_id="troppo_fastcore",
            label="Run TROPPO FASTcore with consensus evidence when available",
            command=[
                python,
                "tools/run_troppo_fastcore.py",
                "--model",
                model,
                "--constraints-dir",
                constraints,
                "--output-dir",
                troppo_results,
                "--evidence-mode",
                "consensus",
            ],
            required_inputs=[
                model,
                f"{constraints}/consensus_fastcore_core_reactions.csv",
                f"{constraints}/exchange_bounds.csv",
                f"{constraints}/gene_expression_evidence.csv",
                f"{constraints}/multi_omics_consensus_reaction_evidence.csv",
            ],
            expected_outputs=[f"{troppo_results}/troppo_fastcore_manifest.json"],
            status_json=f"{troppo_results}/troppo_fastcore_manifest.json",
            optional=True,
        ),
        PipelineStep(
            step_id="troppo_method_inputs",
            label="Prepare iMAT, GIMME, CORDA, and FASTcore TROPPO inputs",
            command=[
                python,
                "tools/prepare_troppo_methods.py",
                "--model",
                model,
                "--constraints-dir",
                constraints,
                "--output-dir",
                troppo_method_results,
                "--evidence-mode",
                "consensus",
            ],
            required_inputs=[
                model,
                f"{constraints}/exchange_bounds.csv",
                f"{constraints}/multi_omics_consensus_reaction_evidence.csv",
            ],
            expected_outputs=[f"{troppo_method_results}/troppo_method_manifest.json"],
            status_json=f"{troppo_method_results}/troppo_method_manifest.json",
        ),
        PipelineStep(
            step_id="condition_interpretation",
            label="Build condition-level interpretation dashboard",
            command=[
                python,
                "tools/build_condition_dashboard.py",
                "--constraints-dir",
                constraints,
                "--evidence-mode-results-dir",
                evidence_mode_results,
                "--context-results-dir",
                context_results,
                "--troppo-results-dir",
                troppo_results,
                "--ml-results-dir",
                ml_results,
                "--output-dir",
                interpretation_results,
            ],
            required_inputs=[
                f"{constraints}/multi_omics_conflict_summary.csv",
                f"{evidence_mode_results}/evidence_mode_delta_summary.csv",
                f"{evidence_mode_results}/evidence_mode_summary.csv",
                f"{context_results}/context_feasibility_summary.csv",
                f"{troppo_results}/omics_signal_quality.csv",
            ],
            expected_outputs=[f"{interpretation_results}/condition_interpretation_manifest.json"],
            status_json=f"{interpretation_results}/condition_interpretation_manifest.json",
        ),
        PipelineStep(
            step_id="minn_export",
            label="Export MINN-style graph, feature tensor, and labels",
            command=[
                python,
                "tools/export_minn_inputs.py",
                "--model",
                model,
                "--package-dir",
                run_root,
                "--output-dir",
                minn_export,
            ],
            required_inputs=[model],
            expected_outputs=[f"{minn_export}/minn_export_manifest.json"],
            status_json=f"{minn_export}/minn_export_manifest.json",
        ),
        PipelineStep(
            step_id="enzyme_constraints",
            label="Build enzyme-capacity bridge tables",
            command=[
                python,
                "tools/run_enzyme_constraints.py",
                "--model",
                model,
                "--constraints-dir",
                constraints,
                "--cobra-results-dir",
                cobra_results,
                "--output-dir",
                enzyme_results,
            ],
            required_inputs=[model, f"{constraints}/protein_abundance.csv", f"{constraints}/kcat_priors.csv"],
            expected_outputs=[f"{enzyme_results}/enzyme_constraint_manifest.json"],
            status_json=f"{enzyme_results}/enzyme_constraint_manifest.json",
        ),
        PipelineStep(
            step_id="gecko_export",
            label="Export GECKO input package",
            command=[
                python,
                "tools/export_gecko_inputs.py",
                "--model",
                model,
                "--constraints-dir",
                constraints,
                "--enzyme-results-dir",
                enzyme_results,
                "--output-dir",
                gecko_package,
            ],
            required_inputs=[model, f"{constraints}/protein_abundance.csv", f"{constraints}/kcat_priors.csv"],
            expected_outputs=[f"{gecko_package}/gecko_export_manifest.json"],
            status_json=f"{gecko_package}/gecko_export_manifest.json",
        ),
        PipelineStep(
            step_id="gecko_external",
            label="Stage or run external GECKO workflow",
            command=[python, "tools/run_gecko_external.py", "--package-dir", gecko_package, "--output-dir", gecko_run_results],
            required_inputs=[
                f"{gecko_package}/gecko_export_manifest.json",
                f"{gecko_package}/protocol_template.m",
            ],
            expected_outputs=[f"{gecko_run_results}/gecko_external_run_summary.csv"],
            status_csv=f"{gecko_run_results}/gecko_external_run_summary.csv",
            optional=True,
        ),
        PipelineStep(
            step_id="pytfa_export",
            label="Export pyTFA input package",
            command=[
                python,
                "tools/export_pytfa_inputs.py",
                "--model",
                model,
                "--constraints-dir",
                constraints,
                "--output-dir",
                pytfa_package,
            ],
            required_inputs=[model, f"{constraints}/intracellular_concentrations.csv"],
            expected_outputs=[f"{pytfa_package}/pytfa_export_manifest.json"],
            status_json=f"{pytfa_package}/pytfa_export_manifest.json",
        ),
        PipelineStep(
            step_id="pytfa_external",
            label="Stage or run external pyTFA workflow",
            command=[python, "tools/run_pytfa_external.py", "--package-dir", pytfa_package, "--output-dir", pytfa_run_results],
            required_inputs=[
                f"{pytfa_package}/pytfa_export_manifest.json",
                f"{pytfa_package}/protocol_template.py",
            ],
            expected_outputs=[f"{pytfa_run_results}/pytfa_external_run_summary.csv"],
            status_csv=f"{pytfa_run_results}/pytfa_external_run_summary.csv",
            optional=True,
        ),
        PipelineStep(
            step_id="report",
            label="Build integrated HTML report",
            command=[python, "tools/build_cobra_report.py", "--results-dir", cobra_results],
            required_inputs=[f"{cobra_results}/cobra_runner_manifest.json"],
            expected_outputs=[f"{cobra_results}/report.html"],
        ),
    ]


def build_backend_status(python_cmd: str | None = None) -> list[dict[str, object]]:
    """Return backend availability rows for the pipeline report."""

    apply_local_backend_env()
    python = python_cmd or sys.executable or "python"
    matlab_path = resolve_matlab_command("matlab")
    docker_path = shutil.which("docker") or ""
    gecko_home = os.environ.get("GECKO_HOME", "")
    thermo_db = os.environ.get("PYTFA_THERMO_DB", "")
    pytfa_deps = check_python_dependencies(python) if _command_exists(python) else {"status": "missing_python"}
    memote_path = resolve_memote_command("memote")
    rows = [
        backend_row("cobrapy", cobrapy_available(), "Local Python import check", path=""),
        backend_row("troppo_fastcore", troppo_available(), "TROPPO FASTcore import check", path=""),
        backend_row("matlab", bool(matlab_path), "MATLAB command for GECKO external runner", path=matlab_path),
        backend_row("gecko_home", bool(gecko_home and Path(gecko_home).exists()), "GECKO_HOME environment path", path=gecko_home),
        backend_row("docker", bool(docker_path), "Docker command for GECKO runDLKcat", path=docker_path),
        backend_row(
            "pytfa_python",
            pytfa_deps.get("status") == "ready",
            str(pytfa_deps.get("message", "")),
            path=str(pytfa_deps.get("python_path", python)),
        ),
        backend_row(
            "pytfa_thermo_db",
            bool(thermo_db and Path(thermo_db).exists()),
            "PYTFA_THERMO_DB environment path",
            path=thermo_db,
        ),
        backend_row("memote", bool(memote_path), "MEMOTE command for standardized GEM QC", path=memote_path),
    ]
    return rows


def backend_row(backend: str, available: bool, detail: str, path: str = "") -> dict[str, object]:
    """Build one backend availability row."""

    return {
        "backend": backend,
        "available": available,
        "status": "available" if available else "missing",
        "detail": detail,
        "path": path,
    }


def read_step_status(step: PipelineStep, cwd: Path) -> dict[str, str]:
    """Read a step's self-reported status from CSV or JSON if configured."""

    if step.status_csv:
        path = _resolve_path(step.status_csv, cwd)
        if path.exists() and path.stat().st_size > 0:
            rows = read_csv_records(path)
            if rows:
                return {"status": rows[0].get("status", ""), "message": rows[0].get("message", "")}
    if step.status_json:
        path = _resolve_path(step.status_json, cwd)
        if path.exists() and path.stat().st_size > 0:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {"status": str(data.get("status", "")), "message": str(data.get("message", ""))}
    return {}


def classify_pipeline_status(step_rows: list[dict[str, object]], dry_run: bool = False) -> str:
    """Classify the whole pipeline from step rows."""

    if dry_run:
        return "dry_run"
    statuses = [str(row.get("status", "")) for row in step_rows]
    if any(status in {"failed", "input_missing", "missing_outputs"} for status in statuses):
        return "failed"
    if any(status in {"skipped", "dry_run", "completed_with_failures"} for status in statuses):
        return "completed_with_skips"
    return "completed"


def build_pipeline_message(step_rows: list[dict[str, object]], status: str) -> str:
    """Build a compact pipeline summary message."""

    counts: dict[str, int] = {}
    for row in step_rows:
        step_status = str(row.get("status", "unknown"))
        counts[step_status] = counts.get(step_status, 0) + 1
    parts = ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))
    return f"Pipeline {status}: {parts}."


def format_command(command: list[str]) -> str:
    """Format a command list for display/copying."""

    return " ".join(_quote_part(part) for part in command)


def _path_text(path: str | Path) -> str:
    return Path(path).as_posix()


def _join_path(root: str | Path, *parts: str) -> str:
    return Path(root).joinpath(*parts).as_posix()


def _resolve_path(path: str | Path, cwd: Path) -> Path:
    value = Path(path)
    return value if value.is_absolute() else cwd / value


def _command_exists(command: str) -> bool:
    if not command:
        return False
    candidate = Path(command)
    return candidate.exists() or shutil.which(command) is not None


def _quote_part(value: str) -> str:
    if not value:
        return '""'
    if any(ch.isspace() for ch in value) or any(ch in value for ch in {"(", ")", "'"}):
        return '"' + value.replace('"', '\\"') + '"'
    return value


def _safe_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
