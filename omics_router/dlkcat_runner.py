"""Optional external GECKO/DLKcat runner."""

from __future__ import annotations

import csv
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .constraints import parse_sbml_index, read_csv_records, write_csv, write_json
from .dlkcat_bridge import (
    build_reaction_kcat_prior_rows,
    normalize_dlkcat_predictions,
    summarize_dlkcat_bridge,
    write_dlkcat_prediction_import_to_package,
)
from .gecko_runner import build_matlab_batch_command, format_command, resolve_matlab_command


@dataclass(slots=True)
class DLKcatExternalRunResult:
    """Summary returned by the optional external GECKO/DLKcat runner."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]


def run_dlkcat_external_workflow(
    dlkcat_results_dir: str | Path,
    model_path: str | Path | None = None,
    package_dir: str | Path | None = None,
    matlab_cmd: str = "matlab",
    gecko_home: str | Path | None = None,
    enabled: bool = False,
    dry_run: bool = False,
    require_dlkcat: bool = False,
    timeout_seconds: int = 7200,
) -> DLKcatExternalRunResult:
    """Run or stage GECKO's Docker-backed DLKcat workflow.

    The runner is opt-in because GECKO's `runDLKcat` requires MATLAB, GECKO,
    Docker, and a model adapter. If any dependency is missing it writes a stable
    skipped manifest instead of interrupting the custom pipeline.
    """

    output = Path(dlkcat_results_dir)
    output.mkdir(parents=True, exist_ok=True)
    input_path = output / "dlkcat_input.tsv"
    files = {
        "summary": str(output / "dlkcat_external_run_summary.csv"),
        "manifest": str(output / "dlkcat_external_run_manifest.json"),
        "protocol": str(output / "dlkcat_gecko_protocol.m"),
        "command": str(output / "dlkcat_gecko_command.txt"),
        "stdout": str(output / "dlkcat_gecko_stdout.log"),
        "stderr": str(output / "dlkcat_gecko_stderr.log"),
        "gecko_input": str(output / "dlkcat_gecko_input.tsv"),
        "gecko_output": str(output / "dlkcat_gecko_output.tsv"),
    }

    if input_path.exists():
        shutil.copyfile(input_path, files["gecko_input"])
    Path(files["protocol"]).write_text(
        build_dlkcat_gecko_protocol(files["gecko_input"], files["gecko_output"]),
        encoding="utf-8",
    )
    effective_matlab_cmd = os.environ.get("MATLAB_CMD", "").strip() if matlab_cmd == "matlab" else str(matlab_cmd).strip()
    effective_matlab_cmd = effective_matlab_cmd or "matlab"
    matlab_path = resolve_matlab_command(effective_matlab_cmd)
    command = build_matlab_batch_command(matlab_path or effective_matlab_cmd, files["protocol"])
    Path(files["command"]).write_text(format_command(command), encoding="utf-8")

    resolved_gecko_home = str(gecko_home or os.environ.get("GECKO_HOME", "")).strip()
    gecko_home_exists = bool(resolved_gecko_home and Path(resolved_gecko_home).exists())
    docker_path = resolve_docker_command()
    input_status = validate_dlkcat_input(input_path)
    readiness = build_dlkcat_run_readiness(
        input_status=input_status,
        enabled=enabled,
        matlab_path=matlab_path,
        gecko_home=resolved_gecko_home,
        gecko_home_exists=gecko_home_exists,
        docker_path=docker_path,
    )

    if readiness["status"] != "ready" or dry_run:
        status = "dry_run" if readiness["status"] == "ready" and dry_run else "skipped"
        message = "DLKcat external run staged but not executed." if status == "dry_run" else readiness["message"]
        if require_dlkcat and status == "skipped":
            raise RuntimeError(message)
        write_dlkcat_run_outputs(
            files=files,
            status=status,
            message=message,
            command=command,
            input_status=input_status,
            matlab_path=matlab_path,
            gecko_home=resolved_gecko_home,
            gecko_home_exists=gecko_home_exists,
            docker_path=docker_path,
            return_code=None,
            timeout_seconds=timeout_seconds,
        )
        return DLKcatExternalRunResult(status=status, output_dir=str(output), message=message, files=files)

    env = os.environ.copy()
    env["GECKO_HOME"] = resolved_gecko_home
    try:
        completed = subprocess.run(
            command,
            cwd=str(output),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        Path(files["stdout"]).write_text(completed.stdout or "", encoding="utf-8")
        Path(files["stderr"]).write_text(completed.stderr or "", encoding="utf-8")
        status = "completed" if completed.returncode == 0 else "failed"
        message = "DLKcat external command completed." if status == "completed" else "DLKcat external command failed."
        if status == "completed":
            import_external_predictions(
                output_dir=output,
                gecko_output_path=Path(files["gecko_output"]),
                model_path=Path(model_path) if model_path else None,
                package_dir=Path(package_dir) if package_dir else None,
            )
        write_dlkcat_run_outputs(
            files=files,
            status=status,
            message=message,
            command=command,
            input_status=input_status,
            matlab_path=matlab_path,
            gecko_home=resolved_gecko_home,
            gecko_home_exists=gecko_home_exists,
            docker_path=docker_path,
            return_code=completed.returncode,
            timeout_seconds=timeout_seconds,
        )
        return DLKcatExternalRunResult(status=status, output_dir=str(output), message=message, files=files)
    except subprocess.TimeoutExpired as exc:
        Path(files["stdout"]).write_text(exc.stdout or "", encoding="utf-8")
        Path(files["stderr"]).write_text(exc.stderr or "", encoding="utf-8")
        message = f"DLKcat external command timed out after {timeout_seconds} seconds."
        write_dlkcat_run_outputs(
            files=files,
            status="failed",
            message=message,
            command=command,
            input_status=input_status,
            matlab_path=matlab_path,
            gecko_home=resolved_gecko_home,
            gecko_home_exists=gecko_home_exists,
            docker_path=docker_path,
            return_code=None,
            timeout_seconds=timeout_seconds,
        )
        return DLKcatExternalRunResult(status="failed", output_dir=str(output), message=message, files=files)


def build_dlkcat_gecko_protocol(gecko_input_path: str | Path, gecko_output_path: str | Path) -> str:
    """Return a MATLAB protocol that calls GECKO `runDLKcat` on a staged file."""

    gecko_input = matlab_path_literal(gecko_input_path)
    gecko_output = matlab_path_literal(gecko_output_path)
    return f"""% GECKO/DLKcat external run protocol
% Generated by Omics-GEM Router.
%
% Requires:
%   - MATLAB
%   - GECKO on GECKO_HOME
%   - Docker with Docker Desktop/daemon running
%   - A GECKO ModelAdapter configured as the default adapter

geckoHome = getenv('GECKO_HOME');
if isempty(geckoHome)
    error('GECKO_HOME is not set.');
end
addpath(genpath(geckoHome));

inputFile = '{gecko_input}';
outputFile = '{gecko_output}';

if ~exist(inputFile, 'file')
    error('DLKcat input file does not exist: %s', inputFile);
end

modelAdapter = ModelAdapterManager.getDefault();
if isempty(modelAdapter)
    error('No default GECKO ModelAdapter is configured. Configure one before running runDLKcat.');
end

runDLKcat(modelAdapter, inputFile);
copyfile(inputFile, outputFile);
fprintf('DLKcat output copied to %s\\n', outputFile);
"""


def validate_dlkcat_input(path: Path) -> dict[str, object]:
    """Check whether the staged DLKcat input file is present and non-empty."""

    exists = path.exists()
    size = path.stat().st_size if exists else 0
    rows = read_csv_records(path) if exists and size else []
    ready_rows = [row for row in rows if row.get("input_status") == "ready_for_dlkcat"]
    return {
        "path": str(path),
        "exists": exists,
        "size_bytes": size,
        "row_count": len(rows),
        "ready_query_count": len(ready_rows),
        "status": "ready" if exists and size and ready_rows else "not_ready",
    }


def build_dlkcat_run_readiness(
    *,
    input_status: dict[str, object],
    enabled: bool,
    matlab_path: str,
    gecko_home: str,
    gecko_home_exists: bool,
    docker_path: str,
) -> dict[str, str]:
    """Return readiness status and a blocking message."""

    if not enabled:
        return {"status": "disabled", "message": "External GECKO/DLKcat execution is disabled; staged input only."}
    if input_status.get("status") != "ready":
        return {"status": "blocked", "message": "DLKcat input has no ready query rows."}
    if not matlab_path:
        return {"status": "blocked", "message": "MATLAB command was not found."}
    if not gecko_home:
        return {"status": "blocked", "message": "GECKO_HOME is not set; skipped external DLKcat execution."}
    if not gecko_home_exists:
        return {"status": "blocked", "message": f"GECKO_HOME does not exist: {gecko_home}"}
    if not docker_path:
        return {"status": "blocked", "message": "Docker command was not found; GECKO runDLKcat requires Docker."}
    return {"status": "ready", "message": "Ready to run GECKO/DLKcat."}


def resolve_docker_command() -> str:
    """Resolve Docker executable when available."""

    return shutil.which("docker") or ""


def import_external_predictions(
    *,
    output_dir: Path,
    gecko_output_path: Path,
    model_path: Path | None,
    package_dir: Path | None,
) -> None:
    """Convert GECKO/DLKcat output into router prediction and kcat-prior files."""

    if not gecko_output_path.exists() or gecko_output_path.stat().st_size == 0:
        return
    import_rows = parse_gecko_dlkcat_output_rows(gecko_output_path)
    if package_dir is not None:
        write_dlkcat_prediction_import_to_package(package_dir, import_rows)
    if model_path is None:
        return
    model_index = parse_sbml_index(model_path)
    input_rows = read_csv_records(output_dir / "dlkcat_input.tsv")
    normalized = normalize_dlkcat_predictions(import_rows, input_rows, model_index)
    priors = build_reaction_kcat_prior_rows(normalized)
    coverage_rows = read_csv_records(output_dir / "dlkcat_input_coverage.csv")
    summary_rows = summarize_dlkcat_bridge(input_rows, coverage_rows, import_rows, normalized, priors)
    write_csv(output_dir / "dlkcat_prediction_normalized.csv", normalized)
    write_csv(output_dir / "dlkcat_reaction_kcat_priors.csv", priors)
    write_csv(output_dir / "dlkcat_bridge_summary.csv", summary_rows)


def parse_gecko_dlkcat_output_rows(path: str | Path) -> list[dict[str, object]]:
    """Parse GECKO/DLKcat six-column output into the router import schema."""

    source = Path(path)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        raw_rows = [row for row in csv.reader(handle, delimiter="\t") if row]
    if not raw_rows:
        return []

    data_rows = raw_rows[1:] if looks_like_header(raw_rows[0]) else raw_rows
    rows: list[dict[str, object]] = []
    for row in data_rows:
        padded = [*row, "", "", "", "", "", ""]
        reaction_id, gene_id, substrate_name, substrate_smiles, _sequence, kcat = padded[:6]
        if not reaction_id and not kcat:
            continue
        rows.append(
            {
                "query_id": "",
                "reaction_id": reaction_id,
                "gene_id": gene_id,
                "substrate_id": "",
                "substrate_name": substrate_name,
                "substrate_smiles": substrate_smiles,
                "predicted_kcat": "" if str(kcat).upper() == "NA" else kcat,
                "unit": "per_s",
                "confidence": "",
                "dlkcat_status": "predicted" if str(kcat).strip() and str(kcat).upper() != "NA" else "no_prediction",
                "note": "Imported from GECKO runDLKcat output.",
            }
        )
    return rows


def looks_like_header(row: list[str]) -> bool:
    """Heuristically detect GECKO/DLKcat header rows."""

    tokens = {value.strip().lower() for value in row}
    return bool(tokens & {"rxn", "rxns", "reaction", "reaction_id", "gene", "genes", "kcat", "kcats"})


def write_dlkcat_run_outputs(
    *,
    files: dict[str, str],
    status: str,
    message: str,
    command: list[str],
    input_status: dict[str, object],
    matlab_path: str,
    gecko_home: str,
    gecko_home_exists: bool,
    docker_path: str,
    return_code: int | None,
    timeout_seconds: int,
) -> None:
    """Write summary and manifest files for an external DLKcat run."""

    summary = {
        "status": status,
        "message": message,
        "input_status": input_status.get("status", ""),
        "input_query_count": input_status.get("row_count", 0),
        "ready_query_count": input_status.get("ready_query_count", 0),
        "matlab_path": matlab_path,
        "gecko_home": gecko_home,
        "gecko_home_exists": gecko_home_exists,
        "docker_path": docker_path,
        "return_code": return_code,
        "timeout_seconds": timeout_seconds,
    }
    write_csv(files["summary"], [summary])
    write_json(
        files["manifest"],
        {
            **summary,
            "command": command,
            "input_status_detail": input_status,
            "files": files,
        },
    )
    Path(files["stdout"]).touch(exist_ok=True)
    Path(files["stderr"]).touch(exist_ok=True)


def matlab_path_literal(path: str | Path) -> str:
    """Return a MATLAB-safe path literal with forward slashes."""

    return str(Path(path).resolve()).replace("\\", "/").replace("'", "''")
