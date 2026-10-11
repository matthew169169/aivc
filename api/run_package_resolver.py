"""Read-only run package resolver.

This module turns a run package directory into a stable runtime context. It is
intentionally free of FastAPI, workflow execution, archive/import side effects,
and service globals so it can be tested as a backend seam.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Callable

CsvReader = Callable[[Path], list[dict[str, str]]]
JsonReader = Callable[[Path], dict[str, Any]]


def resolve_run_package_context(package: Path, *, readers: dict[str, Callable[..., Any]] | None = None, options: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve a read-only package context for UI/API orchestration.

    The resolver never raises for a missing package. Missing critical artifacts
    become stage readiness statuses and guidance; missing optional evidence is
    reported separately so unavailable evidence is not confused with numeric 0.
    """

    del options
    reader_map = readers or {}
    read_csv = _reader(reader_map, "csv", _read_csv_rows)
    read_json = _reader(reader_map, "json", _read_json_object)
    read_variants = _reader(reader_map, "variant_registry", _read_variant_registry)
    read_edit_index = _reader(reader_map, "edit_reaction_index", _read_edit_reaction_index)

    package = Path(package)
    if not package.exists() or not package.is_dir():
        return _missing_context(package, "missing")

    run_id = package.name
    import_manifest_path = package / "import_manifest.json"
    import_manifest = read_json(import_manifest_path)
    upload_manifest_path = package / "upload_manifest.json"
    upload_manifest = read_json(upload_manifest_path)
    input_rows = read_csv(package / "input_file_map.csv")
    model_files = _model_files(package, input_rows)
    variant_rows = [dict(row) for row in read_variants(package)]
    edit_rows = [dict(row) for row in read_edit_index(package)]
    report_files = _report_files(package)
    compare_graph_count = _compare_graph_count(package)
    analysis_status = _analysis_status(package, read_json)
    optional_evidence = _optional_evidence(package, read_csv)
    comparison_summary_count = _row_count(package / "variant_comparison" / "variant_comparison_summary.csv", read_csv)
    reaction_diff_count = _row_count(package / "variant_comparison" / "model_reaction_diff.csv", read_csv)
    variant_ids = [_variant_id(row) for row in variant_rows if _variant_id(row)]
    baseline_variant_id = _baseline_variant_id(variant_rows)
    generated_variant_ids = [
        _variant_id(row)
        for row in variant_rows
        if _variant_id(row) and str(row.get("generation_status") or "").lower() in {"generated", "staged", "evidence_prepared", "inputs_prepared", ""}
    ]
    generated_variant_ids = list(dict.fromkeys(generated_variant_ids))
    compare_ready_pairs = _compare_ready_pairs(baseline_variant_id, variant_ids)
    paper_manifest_path = package / "case_study" / "paper_reproduction_manifest.json"
    paper_manifest = read_json(paper_manifest_path)
    paper_status = str(paper_manifest.get("status") or "")
    report_presets = _report_presets(report_files, paper_status)

    identity = {
        "run_id": run_id,
        "run_dir": str(package),
        "package_status": "available",
        "source_manifest": {
            "upload_manifest_path": str(upload_manifest_path) if upload_manifest else "",
            "import_manifest_path": str(import_manifest_path) if import_manifest else "",
            "import_status": import_manifest.get("status", "native") if import_manifest else "native",
            "source_path": import_manifest.get("source_path", "") if import_manifest else "",
        },
        "created_at": upload_manifest.get("created_at", "") or upload_manifest.get("generated_at", ""),
        "imported_at": import_manifest.get("imported_at", ""),
        "last_modified": package.stat().st_mtime,
    }

    inventory = {
        "input_map": _artifact_status(package / "input_file_map.csv", len(input_rows)),
        "model_files": {
            "status": "ready" if model_files else "missing_artifact",
            "count": len(model_files),
            "files": model_files,
        },
        "variant_registry": _artifact_status(package / "workflow_results" / "model_variant_registry.csv", len(variant_rows)),
        "edit_provenance": _artifact_status(package / "workflow_results" / "model_edit_reaction_index.csv", len(edit_rows), missing_status="not_generated"),
        "variant_comparison": {
            "status": "ready" if comparison_summary_count or reaction_diff_count else "not_generated",
            "summary_count": comparison_summary_count,
            "reaction_diff_count": reaction_diff_count,
            "path": str(package / "variant_comparison"),
        },
        "compare_graphs": {
            "status": "ready" if compare_graph_count else "needs_graph_render",
            "count": compare_graph_count,
            "path": str(package / "visualization_results"),
        },
        "analysis_summary": analysis_status,
        "reports": {
            "status": "ready" if report_files else "not_generated",
            "count": len(report_files),
            "files": report_files,
        },
        "optional_evidence": optional_evidence,
        "missing_optional": [key for key, item in optional_evidence.items() if item.get("status") not in {"ready", "not_applicable"}],
    }
    stage_readiness = _stage_readiness(input_rows, variant_rows, edit_rows, inventory, analysis_status, report_files)
    variant_context = {
        "variants": variant_rows,
        "variant_ids": variant_ids,
        "baseline_variant_id": baseline_variant_id,
        "generated_variant_ids": generated_variant_ids,
        "edit_provenance_status": inventory["edit_provenance"]["status"],
        "compare_ready_pairs": compare_ready_pairs,
    }
    paper_report_context = {
        "analysis_summary_status": analysis_status.get("status", "missing_artifact"),
        "paper_reproduction_status": paper_status or ("missing" if not paper_manifest else "available"),
        "paper_reproduction_manifest_path": str(paper_manifest_path) if paper_manifest else "",
        "report_artifacts": report_files,
        "report_presets": report_presets,
    }
    guidance = _context_guidance(stage_readiness, inventory, paper_report_context)
    return {
        "package_identity": identity,
        "artifact_inventory": inventory,
        "stage_readiness": stage_readiness,
        "variant_context": variant_context,
        "paper_report_context": paper_report_context,
        "guidance": guidance,
    }


def _reader(readers: dict[str, Callable[..., Any]], key: str, default: Callable[..., Any]) -> Callable[..., Any]:
    reader = readers.get(key)
    return reader if callable(reader) else default


def _missing_context(package: Path, status: str) -> dict[str, Any]:
    stage = {key: _stage(status, f"Run package is {status}.") for key in ("input", "generate", "compare", "analysis", "summary")}
    return {
        "package_identity": {
            "run_id": package.name,
            "run_dir": str(package),
            "package_status": status,
            "source_manifest": {},
            "created_at": "",
            "imported_at": "",
            "last_modified": 0,
        },
        "artifact_inventory": {
            "input_map": {"status": "missing_artifact", "count": 0, "path": str(package / "input_file_map.csv")},
            "model_files": {"status": "missing_artifact", "count": 0, "files": []},
            "variant_registry": {"status": "missing_artifact", "count": 0, "path": str(package / "workflow_results" / "model_variant_registry.csv")},
            "edit_provenance": {"status": "not_generated", "count": 0, "path": str(package / "workflow_results" / "model_edit_reaction_index.csv")},
            "variant_comparison": {"status": "not_generated", "summary_count": 0, "reaction_diff_count": 0, "path": str(package / "variant_comparison")},
            "compare_graphs": {"status": "needs_graph_render", "count": 0, "path": str(package / "visualization_results")},
            "analysis_summary": {"status": "missing_artifact", "count": 0, "guidance": "Run package is missing."},
            "reports": {"status": "not_generated", "count": 0, "files": []},
            "optional_evidence": {},
            "missing_optional": [],
        },
        "stage_readiness": stage,
        "variant_context": {
            "variants": [],
            "variant_ids": [],
            "baseline_variant_id": "",
            "generated_variant_ids": [],
            "edit_provenance_status": "not_generated",
            "compare_ready_pairs": [],
        },
        "paper_report_context": {
            "analysis_summary_status": "missing_artifact",
            "paper_reproduction_status": "missing",
            "paper_reproduction_manifest_path": "",
            "report_artifacts": [],
            "report_presets": [],
        },
        "guidance": [f"Run package is {status}: {package}"],
    }


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or not path.is_file() or path.stat().st_size == 0:
        return []
    delimiter = "\t" if path.suffix.lower() in {".tsv", ".txt"} else ","
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists() or not path.is_file() or path.stat().st_size == 0:
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_variant_registry(package: Path) -> list[dict[str, str]]:
    return _read_csv_rows(package / "workflow_results" / "model_variant_registry.csv")


def _read_edit_reaction_index(package: Path) -> list[dict[str, str]]:
    return _read_csv_rows(package / "workflow_results" / "model_edit_reaction_index.csv")


def _artifact_status(path: Path, count: int, *, missing_status: str = "missing_artifact") -> dict[str, Any]:
    if count > 0:
        return {"status": "ready", "count": count, "path": str(path)}
    if path.exists():
        return {"status": "partial", "count": 0, "path": str(path)}
    return {"status": missing_status, "count": 0, "path": str(path)}


def _row_count(path: Path, read_csv: CsvReader) -> int:
    return len(read_csv(path))


def _model_files(package: Path, input_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    files: list[dict[str, str]] = []
    for row in input_rows:
        role = str(row.get("role") or row.get("file_role") or row.get("kind") or "").strip().lower()
        if role not in {"model", "gem", "gsmm", "sbml"} and str(row.get("kind") or "").lower() != "model":
            continue
        path_text = str(row.get("relative_path") or row.get("path") or row.get("file") or row.get("saved_name") or "").strip()
        if not path_text:
            continue
        candidate = Path(path_text)
        if not candidate.is_absolute():
            candidate = package / path_text
        files.append({"path": str(candidate), "relative_path": _safe_relative(package, candidate), "exists": str(candidate.exists()).lower()})
    return files


def _report_files(package: Path) -> list[dict[str, str]]:
    roots = [package / "report_results", package / "reports", package / "summary_results"]
    rows: list[dict[str, str]] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.glob("**/*.html")):
            if path.is_file():
                rows.append({"name": path.name, "path": str(path), "relative_path": _safe_relative(package, path)})
    legacy = package / "cobra_results" / "report.html"
    if legacy.exists() and legacy.is_file():
        rows.insert(0, {"name": "full_audit_legacy_report.html", "path": str(legacy), "relative_path": _safe_relative(package, legacy)})
    return rows


def _compare_graph_count(package: Path) -> int:
    roots = [package / "visualization_results" / "compare_submaps", package / "visualization_results" / "sammi"]
    return sum(len(list(root.glob("**/network_graph.json"))) for root in roots if root.exists())


def _analysis_status(package: Path, read_json: JsonReader) -> dict[str, Any]:
    roots = [package / "analysis_results", package / "report_results", package / "reports", package / "summary_results"]
    file_count = sum(len([path for path in root.glob("**/*") if path.is_file()]) for root in roots if root.exists())
    scaffold_files = [
        package / "workflow_results" / "analysis_parameters_summary.csv",
        package / "case_study" / "paper_reproduction_manifest.json",
        package / "case_study" / "data_needed_manifest.json",
    ]
    scaffold_count = sum(1 for path in scaffold_files if path.exists() and path.is_file())
    paper_manifest = read_json(package / "case_study" / "paper_reproduction_manifest.json")
    if str(paper_manifest.get("status") or "") == "partial_computed_lite":
        chart_files = [
            package / "case_study" / "growth_state_map_data.json",
            package / "case_study" / "trigger_timeline_data.json",
            package / "case_study" / "gdm_lite_results.json",
            package / "case_study" / "dfba_glycogen_scenario.json",
        ]
        chart_count = sum(1 for path in chart_files if path.exists() and path.is_file())
        if chart_count >= 3:
            return {
                "status": "ready",
                "count": scaffold_count + chart_count,
                "guidance": "Paper reproduction workbench artifacts are chart-ready; full D2T2/dFBA remain guarded.",
            }
    if file_count:
        return {"status": "ready", "count": file_count, "guidance": "Analysis or report outputs are available."}
    if scaffold_count:
        return {
            "status": "partial",
            "count": scaffold_count,
            "guidance": "Analysis scaffold artifacts are available; algorithmic reproduction or final report outputs are still pending.",
        }
    return {"status": "missing_artifact", "count": 0, "guidance": "No analysis/report output files were found."}


def _optional_evidence(package: Path, read_csv: CsvReader) -> dict[str, dict[str, Any]]:
    specs = {
        "kcat_priors": [package / "generated_constraints" / "kcat_priors.csv"],
        "reaction_expression_evidence": [package / "generated_constraints" / "reaction_expression_evidence.csv"],
        "reaction_enzyme_capacity": [
            package / "enzyme_results" / "reaction_enzyme_capacity.csv",
            package / "gecko_package" / "reaction_enzyme_capacity.csv",
        ],
        "enzyme_flux_capacity_check": [package / "enzyme_results" / "enzyme_flux_capacity_check.csv"],
        "gecko_enzyme_usage": list((package / "enzyme_results").glob("gecko_enzyme_usage_*.csv")) if (package / "enzyme_results").exists() else [],
        "paper_evidence_overlay": [package / "case_study" / "paper_evidence_reaction_overlay.csv"],
    }
    rows: dict[str, dict[str, Any]] = {}
    for key, paths in specs.items():
        existing = [path for path in paths if path.exists() and path.is_file()]
        if not existing:
            rows[key] = {"status": "not_generated", "count": 0, "path": "", "guidance": "Optional evidence artifact is not generated."}
            continue
        first = existing[0]
        count = len(read_csv(first)) if first.suffix.lower() in {".csv", ".tsv", ".txt"} else 1
        if count:
            rows[key] = {"status": "ready", "count": count, "path": str(first), "guidance": "Optional evidence artifact is available."}
        else:
            rows[key] = {
                "status": "reaction_level_unavailable" if "capacity" in key else "partial",
                "count": 0,
                "path": str(first),
                "guidance": "Artifact exists but has no usable reaction-level rows; do not display this as numeric 0.",
            }
    return rows


def _stage_readiness(
    input_rows: list[dict[str, str]],
    variant_rows: list[dict[str, Any]],
    edit_rows: list[dict[str, Any]],
    inventory: dict[str, Any],
    analysis_status: dict[str, Any],
    report_files: list[dict[str, str]],
) -> dict[str, dict[str, Any]]:
    input_status = "ready" if input_rows else "missing_artifact"
    generate_status = "ready" if variant_rows else "not_generated"
    if not variant_rows:
        compare_status = "not_generated"
    elif edit_rows or inventory["variant_comparison"]["status"] == "ready":
        compare_status = "ready"
    else:
        compare_status = "partial"
    summary_status = "ready" if report_files or analysis_status.get("status") == "ready" else str(analysis_status.get("status") or "missing_artifact")
    return {
        "input": _stage(input_status, "Input map is available." if input_rows else "Input map is missing."),
        "generate": _stage(generate_status, "Model variants are available." if variant_rows else "Variant registry is missing."),
        "compare": _stage(compare_status, "Compare facts are available." if compare_status == "ready" else "Variant comparison or edit provenance is not fully generated."),
        "analysis": _stage(str(analysis_status.get("status") or "missing_artifact"), str(analysis_status.get("guidance") or "")),
        "summary": _stage(summary_status, "Report or analysis summary is available." if summary_status == "ready" else "Summary has no report-ready analysis artifacts."),
    }


def _stage(status: str, guidance: str) -> dict[str, Any]:
    return {"status": status, "guidance": guidance}


def _variant_id(row: dict[str, Any]) -> str:
    return str(row.get("variant_id") or row.get("model_variant_id") or "").strip()


def _baseline_variant_id(rows: list[dict[str, Any]]) -> str:
    for row in rows:
        variant_id = _variant_id(row)
        if variant_id and ("baseline" in variant_id.lower() or str(row.get("generation_method") or "").lower() == "baseline_gem"):
            return variant_id
    return _variant_id(rows[0]) if rows else ""


def _compare_ready_pairs(baseline_variant_id: str, variant_ids: list[str]) -> list[dict[str, str]]:
    if not baseline_variant_id:
        return []
    return [
        {"reference_variant_id": baseline_variant_id, "target_variant_id": variant_id}
        for variant_id in variant_ids
        if variant_id and variant_id != baseline_variant_id
    ]


def _report_presets(report_files: list[dict[str, str]], paper_status: str) -> list[str]:
    presets: list[str] = []
    if paper_status:
        presets.append("shewanella_trigger_reproduction_report")
    for row in report_files:
        name = str(row.get("name") or "")
        if "shewanella_trigger_reproduction_report" in name:
            presets.append("shewanella_trigger_reproduction_report")
        elif name.endswith(".html"):
            presets.append("html_report")
    return list(dict.fromkeys(presets))


def _context_guidance(stage_readiness: dict[str, dict[str, Any]], inventory: dict[str, Any], paper: dict[str, Any]) -> list[str]:
    guidance: list[str] = []
    for stage_id, row in stage_readiness.items():
        if row.get("status") not in {"ready", "not_applicable"}:
            guidance.append(f"{stage_id}: {row.get('guidance', '')}")
    if inventory.get("missing_optional"):
        guidance.append("Optional evidence is missing or reaction-level unavailable; keep status labels instead of numeric 0.")
    if paper.get("paper_reproduction_status") not in {"", "missing"}:
        guidance.append("Paper reproduction context is available.")
    return guidance


def _safe_relative(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except (OSError, ValueError):
        return str(path)
