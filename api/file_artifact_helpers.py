"""Pure file/artifact access helpers for backend service wrappers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable

CsvRowReader = Callable[[Path], list[dict[str, str]]]
JsonObjectReader = Callable[[Path], dict[str, Any]]


def is_relative_to_path(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def safe_relative_path(package: Path, path: Path) -> str:
    try:
        return str(path.relative_to(package))
    except ValueError:
        return str(path)


def list_relative_files(package: Path, root: Path, pattern: str) -> list[dict[str, str]]:
    if not root.exists():
        return []
    rows: list[dict[str, str]] = []
    for path in sorted(root.glob(pattern)):
        if path.is_file():
            rows.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "relative_path": safe_relative_path(package, path),
                }
            )
    return rows


def build_file_summary(package: Path, path: Path, label: str, *, read_rows: CsvRowReader) -> dict[str, object]:
    exists = path.exists()
    row_count = 0
    if exists and path.is_file() and path.suffix.lower() in {".csv", ".tsv", ".txt"}:
        row_count = len(read_rows(path))
    return {
        "label": label,
        "path": str(path),
        "relative_path": safe_relative_path(package, path),
        "exists": exists,
        "row_count": row_count,
        "kind": "directory" if exists and path.is_dir() else "file",
    }


def preview_table_rows(path: Path, *, read_rows: CsvRowReader, limit: int = 25) -> list[dict[str, str]]:
    rows = read_rows(path)
    if limit < 1:
        return rows
    return rows[:limit]


def collect_json_artifacts(
    package: Path,
    filename: str,
    *,
    read_json: JsonObjectReader,
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not package.exists():
        return rows
    for path in package.rglob(filename):
        if len(rows) >= limit:
            break
        item = read_json(path)
        rows.append(
            {
                "path": str(path),
                "relative_path": safe_relative_path(package, path),
                "status": item.get("status") or item.get("result_status") or item.get("qa_status") or "unknown",
                "message": item.get("message") or item.get("guidance") or "",
                "data": item,
            }
        )
    return rows


def resolve_safe_file_path(
    path_text: str,
    *,
    workspace_root: Path,
    allowed_roots: Iterable[Path],
    error_factory: Callable[[int, str], Exception],
) -> Path:
    if not path_text:
        raise error_factory(400, "Missing file path.")
    candidate = Path(path_text)
    if not candidate.is_absolute():
        candidate = workspace_root / candidate
    resolved = candidate.resolve()
    resolved_allowed_roots = [root.resolve() for root in allowed_roots]
    if not any(is_relative_to_path(resolved, root) for root in resolved_allowed_roots):
        raise error_factory(403, "File access is restricted to the Omics-GEM workspace.")
    if not resolved.exists() or not resolved.is_file():
        raise error_factory(404, f"File not found: {path_text}")
    return resolved
