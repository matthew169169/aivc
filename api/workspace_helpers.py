"""Workspace response-shaping helpers for backend service wrappers."""

from __future__ import annotations

from pathlib import Path


def resolve_directory_candidate_path(path_text: str, *, base_root: Path) -> Path:
    candidate = Path(str(path_text).strip()).expanduser()
    if not candidate.is_absolute():
        candidate = base_root / candidate
    return candidate.resolve()


def build_workspace_config_payload(root: Path, *, updated_at: float) -> dict[str, object]:
    return {
        "schema_version": 1,
        "workspace_root": str(root),
        "updated_at": updated_at,
    }


def build_project_row(
    *,
    workspace_root: Path,
    user_runs_dir: Path,
    examples_dir: Path,
    task_logs_dir: Path,
    app_root: Path,
) -> dict[str, str]:
    return {
        "project_id": "default",
        "name": "Active Omics-GEM Router workspace",
        "root": str(workspace_root),
        "user_runs_dir": str(user_runs_dir),
        "examples_dir": str(examples_dir),
        "task_logs_dir": str(task_logs_dir),
        "app_root": str(app_root),
    }


def build_workspace_status_payload(
    *,
    app_root: Path,
    workspace_root: Path,
    user_runs_dir: Path,
    examples_dir: Path,
    task_logs_dir: Path,
    config_path: Path,
    configured_root: str,
    source: str,
    is_default: bool,
    exists: bool,
    is_dir: bool,
    writable: bool,
    allowed_file_roots: tuple[Path, ...],
    default_workspace_root: Path | None = None,
) -> dict[str, object]:
    return {
        "status": "configured" if exists else "missing",
        "app_root": str(app_root),
        "workspace_root": str(workspace_root),
        "default_workspace_root": str(default_workspace_root or app_root),
        "user_runs_dir": str(user_runs_dir),
        "examples_dir": str(examples_dir),
        "task_logs_dir": str(task_logs_dir),
        "config_path": str(config_path),
        "configured_workspace_root": configured_root,
        "source": source,
        "is_default": is_default,
        "exists": exists,
        "is_dir": is_dir,
        "writable": writable,
        "allowed_file_roots": [str(root) for root in allowed_file_roots],
    }
