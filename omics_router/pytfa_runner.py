"""External Python/pyTFA runner for exported pyTFA packages."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .constraints import write_csv, write_json


REQUIRED_PACKAGE_FILES = [
    "pytfa_export_manifest.json",
    "protocol_template.py",
    "model.xml",
    "concentration_bounds.tsv",
]


@dataclass(slots=True)
class PyTFARunResult:
    """Summary returned by the external pyTFA runner."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]


def run_pytfa_external_workflow(
    package_dir: str | Path,
    output_dir: str | Path,
    python_cmd: str | None = None,
    thermo_db: str | Path | None = None,
    dry_run: bool = False,
    require_pytfa: bool = False,
    timeout_seconds: int = 3600,
) -> PyTFARunResult:
    """Run or stage a Python/pyTFA execution for an exported package."""

    package = Path(package_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "summary": str(output / "pytfa_external_run_summary.csv"),
        "manifest": str(output / "pytfa_external_run_manifest.json"),
        "command": str(output / "pytfa_execution_command.txt"),
        "stdout": str(output / "pytfa_stdout.log"),
        "stderr": str(output / "pytfa_stderr.log"),
    }

    package_status = validate_pytfa_package(package)
    requested_python = python_cmd or sys.executable or "python"
    python_path = resolve_python_command(requested_python)
    dependency_status = check_python_dependencies(python_path) if python_path else missing_python_status(requested_python)
    resolved_thermo_db = str(thermo_db or os.environ.get("PYTFA_THERMO_DB", "")).strip()
    thermo_db_exists = bool(resolved_thermo_db and Path(resolved_thermo_db).exists())
    command = build_python_protocol_command(python_path or requested_python, package / "protocol_template.py")
    Path(files["command"]).write_text(format_command(command), encoding="utf-8")

    readiness = build_run_readiness(
        package_status=package_status,
        python_path=python_path,
        dependency_status=dependency_status,
        thermo_db=resolved_thermo_db,
        thermo_db_exists=thermo_db_exists,
    )
    if readiness["status"] != "ready" or dry_run:
        status = "dry_run" if readiness["status"] == "ready" and dry_run else "skipped"
        message = "pyTFA external run staged but not executed." if status == "dry_run" else readiness["message"]
        if require_pytfa and status == "skipped":
            raise RuntimeError(message)
        write_run_outputs(
            files=files,
            package_dir=package,
            status=status,
            message=message,
            command=command,
            python_path=python_path,
            thermo_db=resolved_thermo_db,
            thermo_db_exists=thermo_db_exists,
            package_status=package_status,
            dependency_status=dependency_status,
            return_code=None,
            timeout_seconds=timeout_seconds,
        )
        return PyTFARunResult(status=status, output_dir=str(output), message=message, files=files)

    env = os.environ.copy()
    env["PYTFA_THERMO_DB"] = resolved_thermo_db
    try:
        completed = subprocess.run(
            command,
            cwd=str(package),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        Path(files["stdout"]).write_text(completed.stdout or "", encoding="utf-8")
        Path(files["stderr"]).write_text(completed.stderr or "", encoding="utf-8")
        status = "completed" if completed.returncode == 0 else "failed"
        message = "pyTFA external command completed." if status == "completed" else "pyTFA external command failed."
        write_run_outputs(
            files=files,
            package_dir=package,
            status=status,
            message=message,
            command=command,
            python_path=python_path,
            thermo_db=resolved_thermo_db,
            thermo_db_exists=thermo_db_exists,
            package_status=package_status,
            dependency_status=dependency_status,
            return_code=completed.returncode,
            timeout_seconds=timeout_seconds,
        )
        return PyTFARunResult(status=status, output_dir=str(output), message=message, files=files)
    except subprocess.TimeoutExpired as exc:
        Path(files["stdout"]).write_text(_safe_text(exc.stdout), encoding="utf-8")
        Path(files["stderr"]).write_text(_safe_text(exc.stderr), encoding="utf-8")
        message = f"pyTFA external command timed out after {timeout_seconds} seconds."
        write_run_outputs(
            files=files,
            package_dir=package,
            status="failed",
            message=message,
            command=command,
            python_path=python_path,
            thermo_db=resolved_thermo_db,
            thermo_db_exists=thermo_db_exists,
            package_status=package_status,
            dependency_status=dependency_status,
            return_code=None,
            timeout_seconds=timeout_seconds,
        )
        return PyTFARunResult(status="failed", output_dir=str(output), message=message, files=files)


def validate_pytfa_package(package_dir: str | Path) -> dict[str, object]:
    """Check whether an exported pyTFA package has the expected files."""

    package = Path(package_dir)
    missing = [name for name in REQUIRED_PACKAGE_FILES if not (package / name).exists()]
    return {
        "package_dir": str(package),
        "exists": package.exists(),
        "missing_files": missing,
        "status": "ready" if package.exists() and not missing else "missing_files",
    }


def resolve_python_command(python_cmd: str) -> str:
    """Resolve a Python command to an executable path when possible."""

    if not python_cmd:
        return ""
    candidate = Path(python_cmd)
    if candidate.exists():
        return str(candidate)
    resolved = shutil.which(python_cmd)
    return resolved or ""


def check_python_dependencies(python_path: str, timeout_seconds: int = 30) -> dict[str, object]:
    """Check whether COBRApy and pyTFA are importable in the target Python."""

    command = [
        python_path,
        "-c",
        (
            "import importlib.util, json; "
            "mods={name: importlib.util.find_spec(name) is not None for name in ['cobra','pytfa']}; "
            "print(json.dumps(mods))"
        ),
    ]
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "status": "missing_python",
            "python_path": python_path,
            "cobra_available": False,
            "pytfa_available": False,
            "message": f"Could not inspect Python dependencies: {exc}",
        }

    if completed.returncode != 0:
        return {
            "status": "dependency_check_failed",
            "python_path": python_path,
            "cobra_available": False,
            "pytfa_available": False,
            "message": completed.stderr.strip() or "Python dependency check failed.",
        }

    try:
        modules = json.loads(completed.stdout.strip() or "{}")
    except json.JSONDecodeError:
        modules = {}
    cobra_available = bool(modules.get("cobra"))
    pytfa_available = bool(modules.get("pytfa"))
    missing = [name for name, available in {"cobra": cobra_available, "pytfa": pytfa_available}.items() if not available]
    return {
        "status": "ready" if not missing else "missing_dependencies",
        "python_path": python_path,
        "cobra_available": cobra_available,
        "pytfa_available": pytfa_available,
        "missing_modules": missing,
        "message": "Python dependencies are available." if not missing else f"Missing Python modules: {', '.join(missing)}",
    }


def missing_python_status(requested_python: str) -> dict[str, object]:
    """Return a dependency status for an unresolved Python command."""

    return {
        "status": "missing_python",
        "python_path": "",
        "requested_python": requested_python,
        "cobra_available": False,
        "pytfa_available": False,
        "missing_modules": ["cobra", "pytfa"],
        "message": f"Python command was not found: {requested_python}",
    }


def build_python_protocol_command(python_cmd: str, protocol_path: str | Path) -> list[str]:
    """Build a command for the package protocol template."""

    return [python_cmd, str(Path(protocol_path).resolve())]


def build_run_readiness(
    *,
    package_status: dict[str, object],
    python_path: str,
    dependency_status: dict[str, object],
    thermo_db: str,
    thermo_db_exists: bool,
) -> dict[str, str]:
    """Return readiness status and blocking message."""

    if package_status.get("status") != "ready":
        missing = ", ".join(package_status.get("missing_files", []))
        return {"status": "blocked", "message": f"pyTFA package is incomplete: {missing}"}
    if not python_path:
        return {"status": "blocked", "message": str(dependency_status.get("message") or "Python command was not found.")}
    if dependency_status.get("status") != "ready":
        return {"status": "blocked", "message": str(dependency_status.get("message") or "Python dependencies are incomplete.")}
    if not thermo_db:
        return {"status": "blocked", "message": "PYTFA_THERMO_DB is not set; skipped external pyTFA execution."}
    if not thermo_db_exists:
        return {"status": "blocked", "message": f"PYTFA_THERMO_DB does not exist: {thermo_db}"}
    return {"status": "ready", "message": "Ready to run Python/pyTFA."}


def write_run_outputs(
    *,
    files: dict[str, str],
    package_dir: Path,
    status: str,
    message: str,
    command: list[str],
    python_path: str,
    thermo_db: str,
    thermo_db_exists: bool,
    package_status: dict[str, object],
    dependency_status: dict[str, object],
    return_code: int | None,
    timeout_seconds: int,
) -> None:
    """Write summary and manifest files for a pyTFA external run."""

    summary = {
        "status": status,
        "message": message,
        "package_dir": str(package_dir),
        "package_status": package_status.get("status", ""),
        "python_path": python_path,
        "cobra_available": dependency_status.get("cobra_available", False),
        "pytfa_available": dependency_status.get("pytfa_available", False),
        "thermo_db": thermo_db,
        "thermo_db_exists": thermo_db_exists,
        "return_code": return_code,
        "timeout_seconds": timeout_seconds,
    }
    write_csv(files["summary"], [summary])
    write_json(
        files["manifest"],
        {
            **summary,
            "command": command,
            "package_status_detail": package_status,
            "dependency_status_detail": dependency_status,
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
