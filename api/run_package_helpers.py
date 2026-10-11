"""Pure run package structure helpers for backend service wrappers."""

from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Callable, Iterable

CsvRowReader = Callable[[Path], list[dict[str, str]]]
JsonObjectReader = Callable[[Path], dict[str, Any]]
RunOverviewReader = Callable[[Path], dict[str, Any]]
VariantRegistryReader = Callable[[Path], list[Any]]

RUN_PACKAGE_MARKERS = (
    "upload_manifest.json",
    "input_file_map.csv",
    "run_config.json",
    "ecoli_router_selection.json",
    "router_input",
    "generated_constraints",
    "pipeline_results",
    "workflow_results/model_variant_registry.csv",
)


def list_known_run_packages(user_runs_dir: Path, examples_dir: Path) -> list[Path]:
    packages: list[Path] = []
    if user_runs_dir.exists():
        packages.extend(path for path in user_runs_dir.iterdir() if path.is_dir() and looks_like_run_package(path))
    for example in (examples_dir / "ecoli", examples_dir / "ecoli_real"):
        if example.exists() and example.is_dir():
            packages.append(example)
    return packages


def discover_run_package_paths(root: Path, *, limit: int) -> list[tuple[Path, str]]:
    candidate_paths: list[tuple[Path, str]] = [(root, "selected_root")]
    user_runs = root / "user_runs"
    if user_runs.exists() and user_runs.is_dir():
        candidate_paths.extend((path, "user_runs_child") for path in sorted(user_runs.iterdir()) if path.is_dir())
    candidate_paths.extend((path, "child") for path in sorted(root.iterdir()) if path.is_dir())

    seen: set[Path] = set()
    rows: list[tuple[Path, str]] = []
    for path, location in candidate_paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if not looks_like_run_package(resolved):
            continue
        rows.append((resolved, location))
        if len(rows) >= limit:
            break
    return rows


def same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False


def build_run_package_candidate(
    path: Path,
    location: str,
    *,
    user_runs_dir: Path,
    known_packages: Iterable[Path],
    overview: dict[str, Any],
) -> dict[str, Any]:
    run_id = sanitize_run_id(path.name)
    target = (user_runs_dir / run_id).resolve() if run_id else user_runs_dir.resolve()
    already_available = any(same_path(path, package) for package in known_packages)
    if already_available:
        import_status = "already_available"
    elif target.exists():
        import_status = "target_exists"
    else:
        import_status = "importable"
    return {
        "run_id": run_id,
        "source_name": path.name,
        "path": str(path),
        "location": location,
        "import_status": import_status,
        "target_path": str(target),
        "input_count": overview.get("input_count", 0),
        "model_variant_count": overview.get("model_variant_count", 0),
        "report_count": overview.get("report_count", 0),
        "visualization_count": overview.get("visualization_count", 0),
        "last_modified": overview.get("last_modified", 0),
    }


def safe_run_overview(
    path: Path,
    *,
    read_overview: RunOverviewReader,
    read_rows: CsvRowReader,
    read_variants: VariantRegistryReader,
) -> dict[str, Any]:
    try:
        return read_overview(path)
    except Exception:
        return {
            "run_id": path.name,
            "path": str(path),
            "input_count": len(read_rows(path / "input_file_map.csv")),
            "model_variant_count": len(read_variants(path)),
            "report_count": 0,
            "visualization_count": 0,
            "last_modified": path.stat().st_mtime if path.exists() else 0,
            "import_status": "native",
            "import_source_path": "",
            "imported_at": "",
            "import_manifest_path": "",
        }


def build_archived_run_overview(path: Path, *, overview: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        **overview,
        "run_id": path.name,
        "path": str(path),
        "archive_status": str(manifest.get("status", "missing_manifest") or "missing_manifest"),
        "archived_at": manifest.get("archived_at", ""),
        "archive_source_path": manifest.get("source_path", ""),
        "archive_target_path": manifest.get("target_path", ""),
        "archive_manifest_path": str(path / "archive_manifest.json") if manifest else "",
        "manifest_status": "available" if manifest else "missing_manifest",
    }


def build_import_manifest_payload(
    target: Path,
    source: Path,
    target_run_id: str,
    *,
    workspace_root: Path,
    user_runs_dir: Path,
    imported_at: float,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "imported",
        "imported_at": imported_at,
        "source_path": str(source),
        "source_name": source.name,
        "target_run_id": target_run_id,
        "target_path": str(target),
        "workspace_root": str(workspace_root),
        "user_runs_dir": str(user_runs_dir),
        "copy_mode": "copytree_no_overwrite",
    }


def build_archive_manifest_payload(
    target: Path,
    source: Path,
    run_id: str,
    *,
    workspace_root: Path,
    user_runs_dir: Path,
    archive_root: Path,
    archived_at: float,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "archived",
        "archived_at": archived_at,
        "run_id": run_id,
        "source_path": str(source),
        "target_path": str(target),
        "workspace_root": str(workspace_root),
        "user_runs_dir": str(user_runs_dir),
        "archive_root": str(archive_root),
        "move_mode": "move_to_archived_runs_no_delete",
    }


def build_restore_manifest_payload(
    target: Path,
    source: Path,
    run_id: str,
    *,
    workspace_root: Path,
    user_runs_dir: Path,
    archive_root: Path,
    restored_at: float,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "restored",
        "restored_at": restored_at,
        "run_id": run_id,
        "source_path": str(source),
        "target_path": str(target),
        "workspace_root": str(workspace_root),
        "user_runs_dir": str(user_runs_dir),
        "archive_root": str(archive_root),
        "move_mode": "restore_from_archived_runs_no_overwrite",
    }


def build_already_available_import_result(
    source: Path,
    target: Path,
    target_run_id: str,
    *,
    dry_run: bool,
    manifest: dict[str, Any],
    overview: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "already_available",
        "dry_run": dry_run,
        "message": "Source run package is already available in the active workspace.",
        "source_path": str(source),
        "target_run_id": target_run_id,
        "target_path": str(target),
        "manifest_path": str(source / "import_manifest.json") if manifest else "",
        "import_manifest": manifest,
        "overview": overview,
    }


def build_import_run_result(
    source: Path,
    target: Path,
    target_run_id: str,
    *,
    dry_run: bool,
    source_overview: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "dry_run" if dry_run else "imported",
        "dry_run": dry_run,
        "message": "Dry run only; no files were copied." if dry_run else "Run package imported into the active workspace.",
        "source_path": str(source),
        "target_run_id": target_run_id,
        "target_path": str(target),
        "source_overview": source_overview,
    }


def build_archive_run_result(
    source: Path,
    target: Path,
    run_id: str,
    *,
    dry_run: bool,
    workspace_root: Path,
    archive_root: Path,
) -> dict[str, Any]:
    return {
        "status": "dry_run" if dry_run else "archived",
        "dry_run": dry_run,
        "message": "Dry run only; no files were moved." if dry_run else "Run package archived.",
        "run_id": run_id,
        "source_path": str(source),
        "target_path": str(target),
        "workspace_root": str(workspace_root),
        "archive_root": str(archive_root),
    }


def build_restore_run_result(
    source: Path,
    target: Path,
    run_id: str,
    *,
    dry_run: bool,
    workspace_root: Path,
    archive_root: Path,
    user_runs_dir: Path,
) -> dict[str, Any]:
    return {
        "status": "dry_run" if dry_run else "restored",
        "dry_run": dry_run,
        "message": "Dry run only; no files were moved." if dry_run else "Archived run restored.",
        "run_id": run_id,
        "source_path": str(source),
        "target_path": str(target),
        "workspace_root": str(workspace_root),
        "archive_root": str(archive_root),
        "user_runs_dir": str(user_runs_dir),
    }


def build_run_package_job_header_lines(title: str, run_id: str, *, dry_run: bool) -> list[str]:
    return [
        title,
        f"run_id={run_id}",
        f"dry_run={dry_run}",
        "",
    ]


def build_run_package_job_result_lines(result: dict[str, Any]) -> list[str]:
    return [
        f"status={result.get('status', '')}",
        f"message={result.get('message', '')}",
        f"source_path={result.get('source_path', '')}",
        f"target_path={result.get('target_path', '')}",
    ]


def build_import_manifest_response(package: Path, manifest_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    if not manifest:
        return {
            "run_id": package.name,
            "status": "native",
            "message": "No import manifest was found; this appears to be a native or built-in run package.",
            "manifest_path": "",
            "manifest": {},
        }
    return {
        "run_id": package.name,
        "status": str(manifest.get("status", "imported") or "imported"),
        "message": "Import manifest found.",
        "manifest_path": str(manifest_path),
        "manifest": manifest,
    }


def build_archived_manifest_response(source: Path, manifest_path: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    if not manifest:
        return {
            "run_id": source.name,
            "status": "missing_manifest",
            "message": "No archive_manifest.json was found for this archived run.",
            "manifest_path": "",
            "manifest": {},
        }
    return {
        "run_id": source.name,
        "status": str(manifest.get("status", "archived") or "archived"),
        "message": "Archive manifest found.",
        "manifest_path": str(manifest_path),
        "manifest": manifest,
    }


def looks_like_run_package(path: Path) -> bool:
    return any((path / marker).exists() for marker in RUN_PACKAGE_MARKERS)


def find_run_model_path(package: Path, *, read_rows: CsvRowReader) -> Path | None:
    for row in read_rows(package / "input_file_map.csv"):
        kind = str(row.get("kind", "")).lower()
        role = str(row.get("role", "")).lower()
        if kind == "model" or role in {"gem", "gsmm", "model"}:
            raw = row.get("path") or row.get("relative_path") or ""
            if not raw:
                continue
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = package / candidate
            if candidate.exists():
                return candidate.resolve()
    for candidate in (package / "inputs" / "model").glob("*"):
        if candidate.is_file():
            return candidate.resolve()
    return None


def read_model_id_from_gecko_manifest(gecko_package: Path, *, read_json: JsonObjectReader) -> str:
    manifest = read_json(gecko_package / "gecko_export_manifest.json")
    return str(manifest.get("model_id") or "")


def sanitize_run_id(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip())
    return normalized.strip("_-")


def next_available_run_id(base: str, root: Path, *, default: str = "run") -> str:
    run_id = sanitize_run_id(base) or default
    if not (root / run_id).exists():
        return run_id
    for index in range(2, 1000):
        candidate = f"{run_id}_{index}"
        if not (root / candidate).exists():
            return candidate
    return f"{run_id}_{uuid.uuid4().hex[:8]}"
