"""External MEMOTE runner for standardized GEM quality reports."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .constraints import write_csv, write_json


ROOT = Path(__file__).resolve().parents[1]
MEMOTE_WRAPPER = ROOT / "tools" / "run_memote_cli.py"


@dataclass(slots=True)
class MemoteRunResult:
    """Summary returned by the external MEMOTE runner."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]


def run_memote_external_workflow(
    model_path: str | Path,
    output_dir: str | Path,
    memote_cmd: str = "memote",
    dry_run: bool = False,
    require_memote: bool = False,
    timeout_seconds: int = 7200,
    solver: str | None = None,
    solver_timeout: int | None = None,
    skip: list[str] | None = None,
    exclusive: list[str] | None = None,
) -> MemoteRunResult:
    """Run or stage a MEMOTE snapshot report for a GEM."""

    model = Path(model_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    report_html = output / "memote_snapshot_report.html"
    files = {
        "summary": str(output / "memote_external_run_summary.csv"),
        "manifest": str(output / "memote_external_run_manifest.json"),
        "command": str(output / "memote_execution_command.txt"),
        "stdout": str(output / "memote_stdout.log"),
        "stderr": str(output / "memote_stderr.log"),
        "report_html": str(report_html),
    }

    model_status = validate_model_input(model)
    memote_path = resolve_memote_command(memote_cmd)
    command = build_memote_snapshot_command(
        memote_path or memote_cmd,
        model,
        report_html,
        solver=solver,
        solver_timeout=solver_timeout,
        skip=skip or [],
        exclusive=exclusive or [],
    )
    Path(files["command"]).write_text(format_command(command), encoding="utf-8")

    readiness = build_run_readiness(model_status, memote_path)
    if readiness["status"] != "ready" or dry_run:
        status = "dry_run" if readiness["status"] == "ready" and dry_run else "skipped"
        message = "MEMOTE external run staged but not executed." if status == "dry_run" else readiness["message"]
        if require_memote and status == "skipped":
            raise RuntimeError(message)
        write_run_outputs(
            files=files,
            status=status,
            message=message,
            model_status=model_status,
            memote_path=memote_path,
            command=command,
            report_html=report_html,
            return_code=None,
            timeout_seconds=timeout_seconds,
        )
        return MemoteRunResult(status=status, output_dir=str(output), message=message, files=files)

    try:
        completed = subprocess.run(
            command,
            cwd=str(output),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        Path(files["stdout"]).write_text(completed.stdout or "", encoding="utf-8")
        Path(files["stderr"]).write_text(completed.stderr or "", encoding="utf-8")
        status = "completed" if completed.returncode == 0 else "failed"
        message = "MEMOTE external command completed." if status == "completed" else "MEMOTE external command failed."
        write_run_outputs(
            files=files,
            status=status,
            message=message,
            model_status=model_status,
            memote_path=memote_path,
            command=command,
            report_html=report_html,
            return_code=completed.returncode,
            timeout_seconds=timeout_seconds,
        )
        return MemoteRunResult(status=status, output_dir=str(output), message=message, files=files)
    except subprocess.TimeoutExpired as exc:
        Path(files["stdout"]).write_text(_safe_text(exc.stdout), encoding="utf-8")
        Path(files["stderr"]).write_text(_safe_text(exc.stderr), encoding="utf-8")
        message = f"MEMOTE external command timed out after {timeout_seconds} seconds."
        write_run_outputs(
            files=files,
            status="failed",
            message=message,
            model_status=model_status,
            memote_path=memote_path,
            command=command,
            report_html=report_html,
            return_code=None,
            timeout_seconds=timeout_seconds,
        )
        return MemoteRunResult(status="failed", output_dir=str(output), message=message, files=files)


def validate_model_input(model_path: str | Path) -> dict[str, object]:
    """Check whether a model file exists for MEMOTE."""

    model = Path(model_path)
    return {
        "model_path": str(model),
        "exists": model.exists(),
        "status": "ready" if model.exists() else "missing_model",
    }


def resolve_memote_command(memote_cmd: str) -> str:
    """Resolve a MEMOTE command to an executable path when possible."""

    if not memote_cmd:
        return ""
    candidate = Path(memote_cmd)
    if candidate.exists():
        return str(candidate)
    if candidate.name.lower() in {"memote", "memote.exe"}:
        for executable_name in ("memote.exe", "memote"):
            sibling = Path(sys.executable).resolve().parent / executable_name
            if sibling.exists():
                return str(sibling)
    resolved = shutil.which(memote_cmd)
    return resolved or ""


def build_memote_snapshot_command(
    memote_cmd: str,
    model_path: str | Path,
    report_html: str | Path,
    *,
    solver: str | None = None,
    solver_timeout: int | None = None,
    skip: list[str] | None = None,
    exclusive: list[str] | None = None,
) -> list[str]:
    """Build a MEMOTE snapshot-report command."""

    command = build_memote_command_prefix(memote_cmd) + ["report", "snapshot", "--filename", str(Path(report_html).resolve())]
    if solver:
        command.extend(["--solver", solver])
    if solver_timeout is not None:
        command.extend(["--solver-timeout", str(solver_timeout)])
    for item in skip or []:
        command.extend(["--skip", item])
    for item in exclusive or []:
        command.extend(["--exclusive", item])
    command.append(str(Path(model_path).resolve()))
    return command


def build_memote_command_prefix(memote_cmd: str) -> list[str]:
    """Use a local wrapper for venv MEMOTE so COBRApy cache is redirected first."""

    if MEMOTE_WRAPPER.exists() and Path(memote_cmd).name.lower() in {"memote", "memote.exe"}:
        return [sys.executable, str(MEMOTE_WRAPPER)]
    return [memote_cmd]


def build_run_readiness(model_status: dict[str, object], memote_path: str) -> dict[str, str]:
    """Return readiness status and blocking message."""

    if model_status.get("status") != "ready":
        return {"status": "blocked", "message": f"Model file does not exist: {model_status.get('model_path', '')}"}
    if not memote_path:
        return {"status": "blocked", "message": "MEMOTE command was not found; skipped external MEMOTE execution."}
    return {"status": "ready", "message": "Ready to run MEMOTE snapshot report."}


def write_run_outputs(
    *,
    files: dict[str, str],
    status: str,
    message: str,
    model_status: dict[str, object],
    memote_path: str,
    command: list[str],
    report_html: Path,
    return_code: int | None,
    timeout_seconds: int,
) -> None:
    """Write summary and manifest files for a MEMOTE external run."""

    summary = {
        "status": status,
        "message": message,
        "model_path": model_status.get("model_path", ""),
        "model_exists": model_status.get("exists", False),
        "memote_path": memote_path,
        "report_html": str(report_html),
        "report_exists": report_html.exists(),
        "return_code": return_code,
        "timeout_seconds": timeout_seconds,
    }
    write_csv(files["summary"], [summary])
    write_json(
        files["manifest"],
        {
            **summary,
            "command": command,
            "model_status_detail": model_status,
            "files": files,
        },
    )
    Path(files["stdout"]).touch(exist_ok=True)
    Path(files["stderr"]).touch(exist_ok=True)


def format_command(command: list[str]) -> str:
    """Format a command list for display/copying."""

    return " ".join(_quote_part(part) for part in command)


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
