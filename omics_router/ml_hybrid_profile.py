"""ML/HYBRID profile packaging and lightweight benchmarks.

This module deliberately avoids scikit-learn, PyTorch, XGBoost, and
Flexynesis runtime dependencies.  It turns existing Omics-GEM feature tables
into a stable profile package with simple baselines and GEM-aware importance
tables that can be consumed by the API, React UI, and reports.
"""

from __future__ import annotations

import json
import math
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Any

from .constraints import read_csv_records, write_csv, write_json
from .model_generation import normalize_selected_model_variant_ids, read_model_variant_registry
from .sammi_visualization import parse_sbml_reactions


@dataclass(slots=True)
class MlHybridProfileResult:
    """Summary returned after an ML/HYBRID profile package is written."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]
    manifest: dict[str, Any]


@dataclass(slots=True)
class MlHybridProfileExportResult:
    """Result returned after exporting an ML/HYBRID profile bundle."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]
    manifest: dict[str, Any]


@dataclass(slots=True)
class MlHybridExternalImportResult:
    """Result returned after importing external ML results into a profile."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]
    manifest: dict[str, Any]


def run_ml_hybrid_profile(
    package_dir: str | Path,
    profile_id: str = "",
    task_type: str = "auto",
    selected_variant_ids: Iterable[str] | str | None = None,
    target_column: str = "",
    feature_sources: Iterable[str] | str | None = None,
    benchmark_feature_sets: Iterable[str] | str | None = None,
    max_features: int = 50,
) -> MlHybridProfileResult:
    """Build a reproducible ML/HYBRID profile package from existing outputs."""

    package = Path(package_dir)
    profile = normalize_profile_id(profile_id)
    output = package / "ml_hybrid_profiles" / profile
    results = output / "results"
    files = profile_files(output)
    config = {
        "schema_version": "0.1.0",
        "profile_id": profile,
        "task_type": normalize_task_type(task_type),
        "selected_variant_ids": normalize_selected_model_variant_ids(selected_variant_ids),
        "target_column": str(target_column or ""),
        "feature_sources": normalize_feature_sources(feature_sources),
        "benchmark_feature_sets": normalize_benchmark_feature_sets(benchmark_feature_sets),
        "max_features": max(1, int(max_features or 50)),
        "package_dir": str(package),
    }

    matrix_rows = read_optional_table(package / "ml_results" / "ml_feature_matrix.csv")
    target_column_resolved = resolve_target_column(matrix_rows, config["target_column"])
    selected_features = select_feature_columns(
        matrix_rows,
        target_column_resolved,
        config["feature_sources"],
        max_features=config["max_features"],
    )
    profile_matrix = project_matrix(matrix_rows, target_column_resolved, selected_features)
    target_rows = build_target_rows(profile_matrix, target_column_resolved)
    resolved_task = resolve_task_type(config["task_type"], target_rows)
    annotation_rows = build_feature_annotation(package, selected_features)
    sample_rows = build_sample_metadata(profile_matrix, target_column_resolved, selected_features)
    variant_rows = build_model_variant_context(package, config["selected_variant_ids"])

    benchmark = run_benchmark_feature_sets(
        profile_matrix,
        target_column_resolved,
        selected_features,
        resolved_task,
        config["benchmark_feature_sets"],
    )
    gem_rows = build_gem_feature_importance(package, benchmark["feature_importance"])
    subsystem_rows = build_subsystem_importance_summary(gem_rows)
    production_explainability_rows = build_production_candidate_explainability(package, gem_rows)
    overlay_rows = build_ml_feature_importance_overlay(gem_rows)
    status = profile_status(matrix_rows, target_column_resolved, target_rows, resolved_task, benchmark)
    best = best_benchmark_row(benchmark["benchmark_matrix"], resolved_task)
    message = profile_message(status, profile, resolved_task, len(profile_matrix), len(selected_features))
    summary_rows = [
        {
            "profile_id": profile,
            "status": status,
            "task_type": resolved_task or "not_ready",
            "target_column": target_column_resolved,
            "sample_count": len(target_rows),
            "feature_count": len(selected_features),
            "model_count": len(benchmark["metrics"]),
            "top_feature_count": len(benchmark["feature_importance"]),
            "benchmark_feature_set_count": len(config["benchmark_feature_sets"]),
            "best_model_id": best.get("model_id", ""),
            "best_feature_set": best.get("feature_set", ""),
            "selected_variant_ids": ";".join(config["selected_variant_ids"]),
            "guidance": profile_guidance(status, resolved_task),
        }
    ]

    manifest = {
        "schema_version": "0.1.0",
        "status": status,
        "message": message,
        "profile_id": profile,
        "package_dir": str(package),
        "output_dir": str(output),
        "result_dir": str(results),
        "task_type": resolved_task or "not_ready",
        "target_column": target_column_resolved,
        "sample_count": len(target_rows),
        "feature_count": len(selected_features),
        "benchmark_feature_sets": config["benchmark_feature_sets"],
        "best_model_id": best.get("model_id", ""),
        "best_feature_set": best.get("feature_set", ""),
        "selected_variant_ids": config["selected_variant_ids"],
        "files": files,
        "notes": [
            "Lightweight local baselines only; no scikit-learn, PyTorch, XGBoost, or Flexynesis runtime dependency is used.",
            "Feature importance is a predictive marker screen and should not be interpreted as causal mechanism.",
        ],
    }

    write_json(files["config"], config)
    write_csv(files["feature_matrix"], profile_matrix)
    write_csv(files["target_table"], target_rows)
    write_csv(files["sample_metadata"], sample_rows)
    write_csv(files["feature_annotation"], annotation_rows)
    write_csv(files["model_variant_context"], variant_rows)
    write_csv(files["profile_summary"], summary_rows)
    write_csv(files["prediction_table"], benchmark["predictions"])
    write_csv(files["model_metrics"], benchmark["metrics"])
    write_csv(files["benchmark_summary"], benchmark["benchmark_summary"])
    write_csv(files["benchmark_matrix"], benchmark["benchmark_matrix"])
    write_csv(files["feature_importance"], benchmark["feature_importance"])
    write_csv(files["gem_feature_importance"], gem_rows)
    write_csv(files["subsystem_importance_summary"], subsystem_rows)
    write_csv(files["production_candidate_explainability"], production_explainability_rows)
    write_csv(files["ml_feature_importance_overlay"], overlay_rows)
    write_json(files["manifest"], manifest)
    return MlHybridProfileResult(status, str(output), message, files, manifest)


def list_ml_hybrid_profiles(package_dir: str | Path) -> list[dict[str, Any]]:
    """List generated ML/HYBRID profile manifests for one package."""

    root = Path(package_dir) / "ml_hybrid_profiles"
    if not root.exists():
        return []
    rows: list[dict[str, Any]] = []
    for manifest_path in sorted(root.glob("*/results/profile_manifest.json")):
        manifest = read_json_object(manifest_path)
        files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
        summary_path = manifest_path.parents[1] / "profile_summary.csv"
        modified_at = manifest_path.stat().st_mtime if manifest_path.exists() else 0
        rows.append(
            {
                "profile_id": manifest.get("profile_id", manifest_path.parents[1].name),
                "status": manifest.get("status", ""),
                "message": manifest.get("message", ""),
                "task_type": manifest.get("task_type", ""),
                "target_column": manifest.get("target_column", ""),
                "sample_count": manifest.get("sample_count", 0),
                "feature_count": manifest.get("feature_count", 0),
                "best_model_id": manifest.get("best_model_id", ""),
                "best_feature_set": manifest.get("best_feature_set", ""),
                "benchmark_feature_sets": ";".join(manifest.get("benchmark_feature_sets", []))
                if isinstance(manifest.get("benchmark_feature_sets"), list)
                else manifest.get("benchmark_feature_sets", ""),
                "selected_variant_ids": ";".join(manifest.get("selected_variant_ids", []))
                if isinstance(manifest.get("selected_variant_ids"), list)
                else manifest.get("selected_variant_ids", ""),
                "output_dir": manifest.get("output_dir", ""),
                "result_dir": manifest.get("result_dir", ""),
                "summary_path": str(summary_path),
                "metrics_path": str(files.get("model_metrics", "")),
                "benchmark_summary_path": str(files.get("benchmark_summary", "")),
                "benchmark_matrix_path": str(files.get("benchmark_matrix", "")),
                "feature_importance_path": str(files.get("feature_importance", "")),
                "gem_feature_importance_path": str(files.get("gem_feature_importance", "")),
                "subsystem_importance_path": str(files.get("subsystem_importance_summary", "")),
                "production_explainability_path": str(files.get("production_candidate_explainability", "")),
                "ml_feature_importance_overlay_path": str(files.get("ml_feature_importance_overlay", "")),
                "manifest_path": str(manifest_path),
                "modified_at": modified_at,
                "modified_at_iso": datetime.fromtimestamp(modified_at).isoformat(timespec="seconds") if modified_at else "",
            }
        )
    return sorted(rows, key=lambda row: float(row.get("modified_at") or 0), reverse=True)


def get_ml_hybrid_profile_detail(package_dir: str | Path, profile_id: str) -> dict[str, Any]:
    """Read one ML/HYBRID profile package with its main result tables."""

    profile = normalize_existing_profile_id(profile_id)
    root = Path(package_dir) / "ml_hybrid_profiles" / profile
    manifest_path = root / "results" / "profile_manifest.json"
    if not manifest_path.exists():
        return {
            "status": "missing",
            "message": f"ML/HYBRID profile was not found: {profile}",
            "profile_id": profile,
            "profile_dir": str(root),
            "manifest_path": str(manifest_path),
            "manifest": {},
            "files": {},
            "profile_summary": [],
            "benchmark_summary": [],
            "benchmark_matrix": [],
            "model_metrics": [],
            "top_feature_importance": [],
            "gem_feature_importance": [],
            "subsystem_importance": [],
            "production_candidate_explainability": [],
        }
    manifest = read_json_object(manifest_path)
    files = profile_files(root)
    benchmark_matrix = read_optional_table(Path(files["benchmark_matrix"]))
    model_metrics = read_optional_table(Path(files["model_metrics"]))
    gem_importance = read_optional_table(Path(files["gem_feature_importance"]))
    production_explainability = read_optional_table(Path(files["production_candidate_explainability"]))
    top_importance = sorted(
        read_optional_table(Path(files["feature_importance"])),
        key=lambda row: -(_to_float(row.get("importance_score")) or 0.0),
    )[:40]
    return {
        "status": str(manifest.get("status") or "completed"),
        "message": str(manifest.get("message") or ""),
        "profile_id": str(manifest.get("profile_id") or profile),
        "profile_dir": str(root),
        "manifest_path": str(manifest_path),
        "manifest": manifest,
        "files": files,
        "profile_summary": read_optional_table(Path(files["profile_summary"])),
        "benchmark_summary": read_optional_table(Path(files["benchmark_summary"])),
        "benchmark_matrix": benchmark_matrix,
        "model_metrics": model_metrics,
        "top_feature_importance": top_importance,
        "gem_feature_importance": gem_importance[:80],
        "subsystem_importance": read_optional_table(Path(files["subsystem_importance_summary"])),
        "production_candidate_explainability": production_explainability,
        "comparison_row": ml_hybrid_profile_comparison_row(manifest, benchmark_matrix, gem_importance, production_explainability),
    }


def compare_ml_hybrid_profiles(package_dir: str | Path) -> dict[str, Any]:
    """Summarize existing ML/HYBRID profiles without rerunning benchmarks."""

    profiles = list_ml_hybrid_profiles(package_dir)
    if not profiles:
        return {
            "status": "empty_guidance",
            "message": "No ML/HYBRID profiles were found. Run a profile first, then refresh comparison.",
            "profile_count": 0,
            "best_profile_id": "",
            "best_feature_set": "",
            "best_model_id": "",
            "comparison": [],
        }
    rows: list[dict[str, Any]] = []
    for profile in profiles:
        detail = get_ml_hybrid_profile_detail(package_dir, str(profile.get("profile_id", "")))
        row = detail.get("comparison_row") if isinstance(detail.get("comparison_row"), dict) else {}
        if row:
            rows.append(row)
    best = best_profile_comparison_row(rows)
    return {
        "status": "completed" if rows else "empty_guidance",
        "message": f"Compared {len(rows)} ML/HYBRID profile(s)." if rows else "Profile comparison could not read any profile outputs.",
        "profile_count": len(rows),
        "best_profile_id": best.get("profile_id", ""),
        "best_feature_set": best.get("best_feature_set", ""),
        "best_model_id": best.get("best_model_id", ""),
        "comparison": rows,
    }


def export_ml_hybrid_profile(
    package_dir: str | Path,
    profile_id: str,
    export_format: str = "both",
) -> MlHybridProfileExportResult:
    """Export one profile into reproducible bundle formats without rerunning ML."""

    package = Path(package_dir)
    profile = normalize_existing_profile_id(profile_id)
    detail = get_ml_hybrid_profile_detail(package, profile)
    exports_root = package / "ml_hybrid_profiles" / profile / "exports"
    formats = normalize_profile_export_format(export_format)
    if detail.get("status") == "missing":
        manifest = {
            "schema_version": "0.1.0",
            "status": "missing",
            "message": detail.get("message", "ML/HYBRID profile was not found."),
            "profile_id": profile,
            "requested_export_format": export_format,
            "formats": [],
            "files": {},
        }
        return MlHybridProfileExportResult(
            "missing",
            str(exports_root),
            str(manifest["message"]),
            {},
            manifest,
        )

    exports_root.mkdir(parents=True, exist_ok=True)
    generated: dict[str, Any] = {}
    files: dict[str, str] = {}
    summary_rows: list[dict[str, Any]] = []
    for fmt in formats:
        if fmt == "omics_gem_profile_bundle":
            result = write_omics_gem_profile_bundle(detail, exports_root / fmt)
        else:
            result = write_flexynesis_like_inputs(detail, exports_root / fmt)
        generated[fmt] = result
        files.update({f"{fmt}.{key}": value for key, value in result.get("files", {}).items()})
        summary_rows.append(
            {
                "profile_id": profile,
                "export_format": fmt,
                "status": result.get("status", ""),
                "output_dir": result.get("output_dir", ""),
                "target_readiness": result.get("target_readiness", ""),
                "feature_view_count": result.get("feature_view_count", ""),
                "file_count": len(result.get("files", {})) if isinstance(result.get("files"), dict) else 0,
                "message": result.get("message", ""),
            }
        )

    status = "completed"
    if any(row.get("status") == "partial" for row in summary_rows):
        status = "partial"
    manifest_path = exports_root / "ml_hybrid_profile_export_manifest.json"
    summary_path = exports_root / "ml_hybrid_profile_export_summary.csv"
    manifest = {
        "schema_version": "0.1.0",
        "status": status,
        "message": f"Exported ML/HYBRID profile {profile} as {', '.join(formats)}.",
        "profile_id": profile,
        "profile_status": detail.get("status", ""),
        "requested_export_format": export_format,
        "formats": formats,
        "output_dir": str(exports_root),
        "generated": generated,
        "files": {
            **files,
            "manifest": str(manifest_path),
            "summary": str(summary_path),
        },
        "notes": [
            "Flexynesis-like inputs are an interoperability-oriented tabular export, not a Flexynesis runtime integration.",
            "No scikit-learn, PyTorch, XGBoost, or Flexynesis dependency is required to create this export.",
        ],
    }
    write_json(manifest_path, manifest)
    write_csv(summary_path, summary_rows)
    return MlHybridProfileExportResult(status, str(exports_root), str(manifest["message"]), manifest["files"], manifest)


def list_ml_hybrid_profile_exports(package_dir: str | Path, profile_id: str) -> dict[str, Any]:
    """Discover existing export bundles for one ML/HYBRID profile."""

    profile = normalize_existing_profile_id(profile_id)
    exports_root = Path(package_dir) / "ml_hybrid_profiles" / profile / "exports"
    if not exports_root.exists():
        return {
            "status": "empty_guidance",
            "message": "No ML/HYBRID profile exports were found. Export the selected profile first.",
            "profile_id": profile,
            "exports_root": str(exports_root),
            "count": 0,
            "exports": [],
            "latest": None,
        }
    rows: list[dict[str, Any]] = []
    for manifest_path in sorted(exports_root.glob("*/export_manifest.json")):
        manifest = read_json_object(manifest_path)
        output_dir = manifest_path.parent
        modified_at = manifest_path.stat().st_mtime
        rows.append(
            {
                "profile_id": profile,
                "export_format": manifest.get("export_format", output_dir.name),
                "status": manifest.get("status", ""),
                "message": manifest.get("message", ""),
                "target_readiness": manifest.get("target_readiness", ""),
                "feature_view_count": manifest.get("feature_view_count", 0),
                "output_dir": str(output_dir),
                "manifest_path": str(manifest_path),
                "readme_path": str(output_dir / "README.md"),
                "files": manifest.get("files", {}),
                "modified_at": modified_at,
                "modified_at_iso": datetime.fromtimestamp(modified_at).isoformat(timespec="seconds"),
            }
        )
    root_manifest = exports_root / "ml_hybrid_profile_export_manifest.json"
    root_summary = exports_root / "ml_hybrid_profile_export_summary.csv"
    rows = sorted(rows, key=lambda row: float(row.get("modified_at") or 0), reverse=True)
    return {
        "status": "ok" if rows else "empty_guidance",
        "message": "ML/HYBRID profile exports found." if rows else "No ML/HYBRID profile exports were found.",
        "profile_id": profile,
        "exports_root": str(exports_root),
        "manifest_path": str(root_manifest) if root_manifest.exists() else "",
        "summary_path": str(root_summary) if root_summary.exists() else "",
        "count": len(rows),
        "exports": rows,
        "latest": rows[0] if rows else None,
    }


def import_ml_hybrid_external_results(
    package_dir: str | Path,
    profile_id: str,
    source_dir: str | Path,
    result_format: str = "generic_tabular",
    import_id: str = "",
) -> MlHybridExternalImportResult:
    """Import external ML outputs and map feature importance back to GEM context."""

    package = Path(package_dir)
    profile = normalize_existing_profile_id(profile_id)
    import_name = normalize_external_import_id(import_id)
    output = package / "ml_hybrid_profiles" / profile / "external_results" / import_name
    files = external_import_files(output)
    profile_detail = get_ml_hybrid_profile_detail(package, profile)
    source_text = str(source_dir or "").strip()
    source = Path(source_text).expanduser() if source_text else Path("__missing_external_result_source__")
    if source_text:
        try:
            source = source.resolve()
        except OSError:
            source = Path(source_text)
    output.mkdir(parents=True, exist_ok=True)

    validation_rows: list[dict[str, Any]] = []
    normalized_predictions: list[dict[str, Any]] = []
    normalized_metrics: list[dict[str, Any]] = []
    normalized_importance: list[dict[str, Any]] = []
    source_files: dict[str, str] = {}

    if profile_detail.get("status") == "missing":
        validation_rows.append(validation_flag("error", "profile_missing", f"Profile {profile} was not found.", ""))
    if not source or not source.exists() or not source.is_dir():
        validation_rows.append(validation_flag("error", "source_dir_missing", "External result folder was not found.", str(source)))
    else:
        prediction_path = find_external_result_file(source, ["prediction_table.csv", "predictions.csv"])
        metrics_path = find_external_result_file(source, ["model_metrics.csv", "metrics.csv", "benchmark_summary.csv"])
        importance_path = find_external_result_file(source, ["feature_importance.csv", "features_importance.csv"])
        embeddings_path = find_external_result_file(source, ["sample_embeddings.csv", "embeddings.csv"])
        config_path = find_external_result_file(source, ["model_config.json", "config.json"])
        for label, path in {
            "prediction_table": prediction_path,
            "model_metrics": metrics_path,
            "feature_importance": importance_path,
            "sample_embeddings": embeddings_path,
            "model_config": config_path,
        }.items():
            if path:
                source_files[label] = str(path)

        if prediction_path:
            normalized_predictions = normalize_external_prediction_rows(read_optional_table(prediction_path), prediction_path)
        else:
            validation_rows.append(validation_flag("warning", "prediction_table_missing", "prediction_table.csv was not found.", str(source)))
        if metrics_path:
            normalized_metrics = normalize_external_metric_rows(read_optional_table(metrics_path), metrics_path)
        else:
            validation_rows.append(validation_flag("warning", "model_metrics_missing", "model_metrics.csv was not found.", str(source)))
        if importance_path:
            normalized_importance = normalize_external_feature_importance_rows(read_optional_table(importance_path), importance_path)
        else:
            validation_rows.append(validation_flag("warning", "feature_importance_missing", "feature_importance.csv was not found.", str(source)))
        if not embeddings_path:
            validation_rows.append(validation_flag("info", "sample_embeddings_missing", "sample embeddings are optional and were not found.", str(source)))
        if not config_path:
            validation_rows.append(validation_flag("info", "model_config_missing", "model_config.json is optional and was not found.", str(source)))

    gem_rows = build_external_gem_feature_importance(package, normalized_importance)
    overlay_rows = build_external_ml_feature_importance_overlay(gem_rows)
    if normalized_importance and not any(row.get("reaction_id") for row in gem_rows):
        validation_rows.append(
            validation_flag(
                "warning",
                "no_reaction_level_mapping",
                "External feature importance was imported, but no feature could be mapped to a GEM reaction.",
                source_files.get("feature_importance", ""),
            )
        )

    status = external_import_status(profile_detail, source, normalized_predictions, normalized_metrics, normalized_importance, validation_rows)
    message = external_import_message(status, import_name, normalized_importance, gem_rows)
    summary_rows = [
        {
            "profile_id": profile,
            "import_id": import_name,
            "status": status,
            "result_format": normalize_external_result_format(result_format),
            "source_dir": str(source),
            "prediction_row_count": len(normalized_predictions),
            "metric_row_count": len(normalized_metrics),
            "feature_importance_row_count": len(normalized_importance),
            "gem_mapped_feature_count": sum(1 for row in gem_rows if row.get("reaction_id")),
            "unmapped_feature_count": sum(1 for row in gem_rows if not row.get("reaction_id")),
            "overlay_row_count": sum(1 for row in overlay_rows if row.get("reaction_id")),
            "validation_flag_count": len(validation_rows),
            "guidance": "External ML importance is predictive marker evidence, not causal mechanism proof.",
        }
    ]

    write_csv(Path(files["validation_flags"]), validation_rows)
    write_csv(Path(files["summary"]), summary_rows)
    write_csv(Path(files["normalized_prediction_table"]), normalized_predictions)
    write_csv(Path(files["normalized_model_metrics"]), normalized_metrics)
    write_csv(Path(files["normalized_feature_importance"]), normalized_importance)
    write_csv(Path(files["gem_feature_importance"]), gem_rows)
    write_csv(Path(files["overlay"]), overlay_rows)

    manifest = {
        "schema_version": "0.1.0",
        "status": status,
        "message": message,
        "profile_id": profile,
        "import_id": import_name,
        "result_format": normalize_external_result_format(result_format),
        "source_dir": str(source),
        "source_files": source_files,
        "output_dir": str(output),
        "summary": summary_rows[0],
        "files": files,
        "validation_flags": validation_rows,
        "interpretation_note": "External ML feature importance is treated as predictive marker evidence and must not be interpreted as causal mechanism proof.",
    }
    write_json(Path(files["manifest"]), manifest)
    return MlHybridExternalImportResult(status, str(output), message, files, manifest)


def list_ml_hybrid_external_results(package_dir: str | Path, profile_id: str) -> dict[str, Any]:
    """Discover previously imported external ML result folders for one profile."""

    package = Path(package_dir)
    profile = normalize_existing_profile_id(profile_id)
    root = package / "ml_hybrid_profiles" / profile / "external_results"
    if not root.exists():
        return {
            "status": "empty_guidance",
            "message": "No external ML result imports were found. Import an external result folder first.",
            "profile_id": profile,
            "external_results_root": str(root),
            "count": 0,
            "imports": [],
            "latest": None,
        }
    rows: list[dict[str, Any]] = []
    for manifest_path in sorted(root.glob("*/external_import_manifest.json")):
        manifest = read_json_object(manifest_path)
        output_dir = manifest_path.parent
        modified_at = manifest_path.stat().st_mtime
        summary = manifest.get("summary", {}) if isinstance(manifest.get("summary"), dict) else {}
        qa = external_import_qa_summary(output_dir, manifest)
        rows.append(
            {
                "profile_id": profile,
                "import_id": manifest.get("import_id", output_dir.name),
                "status": manifest.get("status", ""),
                "qa_status": qa.get("qa_status", ""),
                "validation_error_count": qa.get("validation_error_count", 0),
                "validation_warning_count": qa.get("validation_warning_count", 0),
                "message": manifest.get("message", ""),
                "result_format": manifest.get("result_format", ""),
                "source_dir": manifest.get("source_dir", ""),
                "output_dir": str(output_dir),
                "manifest_path": str(manifest_path),
                "summary_path": str(output_dir / "external_import_summary.csv"),
                "validation_flags_path": str(output_dir / "external_validation_flags.csv"),
                "gem_feature_importance_path": str(output_dir / "gem_external_feature_importance.csv"),
                "overlay_path": str(output_dir / "external_ml_feature_importance_overlay.csv"),
                "feature_importance_row_count": summary.get("feature_importance_row_count", 0),
                "gem_mapped_feature_count": summary.get("gem_mapped_feature_count", 0),
                "unmapped_feature_count": summary.get("unmapped_feature_count", 0),
                "overlay_row_count": summary.get("overlay_row_count", 0),
                "modified_at": modified_at,
                "modified_at_iso": datetime.fromtimestamp(modified_at).isoformat(timespec="seconds"),
            }
        )
    rows = sorted(rows, key=lambda row: float(row.get("modified_at") or 0), reverse=True)
    return {
        "status": "ok" if rows else "empty_guidance",
        "message": "External ML result imports found." if rows else "No external ML result imports were found.",
        "profile_id": profile,
        "external_results_root": str(root),
        "count": len(rows),
        "imports": rows,
        "latest": rows[0] if rows else None,
    }


def get_ml_hybrid_external_result_detail(package_dir: str | Path, profile_id: str, import_id: str) -> dict[str, Any]:
    """Read one external import with QA status and preview tables."""

    package = Path(package_dir)
    profile = normalize_existing_profile_id(profile_id)
    import_name = normalize_existing_profile_id(import_id)
    output = package / "ml_hybrid_profiles" / profile / "external_results" / import_name
    manifest_path = output / "external_import_manifest.json"
    if not manifest_path.exists():
        return {
            "status": "missing",
            "message": "External ML import was not found.",
            "profile_id": profile,
            "import_id": import_name,
            "output_dir": str(output),
            "manifest_path": str(manifest_path),
            "manifest": {},
            "qa_summary": {
                "qa_status": "missing",
                "message": "No external_import_manifest.json was found for this import.",
            },
            "external_import_summary": [],
            "validation_flags": [],
            "normalized_model_metrics": [],
            "top_external_feature_importance": [],
            "gem_feature_importance": [],
            "overlay_rows": [],
            "files": external_import_files(output),
        }
    manifest = read_json_object(manifest_path)
    files = manifest.get("files", {}) if isinstance(manifest.get("files"), dict) else external_import_files(output)
    summary_rows = read_optional_table(Path(str(files.get("summary", output / "external_import_summary.csv"))))
    validation_rows = read_optional_table(Path(str(files.get("validation_flags", output / "external_validation_flags.csv"))))
    metric_rows = read_optional_table(Path(str(files.get("normalized_model_metrics", output / "normalized_model_metrics.csv"))))
    feature_rows = read_optional_table(Path(str(files.get("normalized_feature_importance", output / "normalized_feature_importance.csv"))))
    gem_rows = read_optional_table(Path(str(files.get("gem_feature_importance", output / "gem_external_feature_importance.csv"))))
    overlay_rows = read_optional_table(Path(str(files.get("overlay", output / "external_ml_feature_importance_overlay.csv"))))
    qa = external_import_qa_summary(output, manifest, summary_rows=summary_rows, validation_rows=validation_rows, gem_rows=gem_rows, overlay_rows=overlay_rows)
    return {
        "status": manifest.get("status", qa.get("qa_status", "")),
        "message": manifest.get("message", ""),
        "profile_id": profile,
        "import_id": manifest.get("import_id", import_name),
        "output_dir": str(output),
        "manifest_path": str(manifest_path),
        "manifest": manifest,
        "qa_summary": qa,
        "external_import_summary": summary_rows,
        "validation_flags": validation_rows,
        "normalized_model_metrics": metric_rows[:40],
        "top_external_feature_importance": top_importance_rows(feature_rows, limit=40),
        "gem_feature_importance": top_importance_rows(gem_rows, limit=40),
        "overlay_rows": [row for row in overlay_rows if row.get("reaction_id")][:40],
        "files": files,
    }


def external_import_qa_summary(
    output: Path,
    manifest: dict[str, Any] | None = None,
    *,
    summary_rows: list[dict[str, str]] | None = None,
    validation_rows: list[dict[str, str]] | None = None,
    gem_rows: list[dict[str, str]] | None = None,
    overlay_rows: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    manifest = manifest or {}
    files = manifest.get("files", {}) if isinstance(manifest.get("files"), dict) else external_import_files(output)
    manifest_path = Path(str(files.get("manifest", output / "external_import_manifest.json")))
    summary_rows = summary_rows if summary_rows is not None else read_optional_table(Path(str(files.get("summary", output / "external_import_summary.csv"))))
    validation_rows = validation_rows if validation_rows is not None else read_optional_table(Path(str(files.get("validation_flags", output / "external_validation_flags.csv"))))
    gem_rows = gem_rows if gem_rows is not None else read_optional_table(Path(str(files.get("gem_feature_importance", output / "gem_external_feature_importance.csv"))))
    overlay_rows = overlay_rows if overlay_rows is not None else read_optional_table(Path(str(files.get("overlay", output / "external_ml_feature_importance_overlay.csv"))))
    required_paths = {
        "manifest": manifest_path,
        "summary": Path(str(files.get("summary", output / "external_import_summary.csv"))),
        "validation_flags": Path(str(files.get("validation_flags", output / "external_validation_flags.csv"))),
        "normalized_feature_importance": Path(str(files.get("normalized_feature_importance", output / "normalized_feature_importance.csv"))),
        "gem_feature_importance": Path(str(files.get("gem_feature_importance", output / "gem_external_feature_importance.csv"))),
        "overlay": Path(str(files.get("overlay", output / "external_ml_feature_importance_overlay.csv"))),
    }
    missing_files = [name for name, path in required_paths.items() if not path.exists()]
    severity_counts = count_validation_severities(validation_rows)
    summary = summary_rows[0] if summary_rows else {}
    mapped_count = int(_to_float(summary.get("gem_mapped_feature_count")) or sum(1 for row in gem_rows if row.get("reaction_id")))
    unmapped_count = int(_to_float(summary.get("unmapped_feature_count")) or sum(1 for row in gem_rows if not row.get("reaction_id")))
    overlay_count = int(_to_float(summary.get("overlay_row_count")) or sum(1 for row in overlay_rows if row.get("reaction_id")))
    manifest_status = str(manifest.get("status", "missing" if missing_files else ""))
    if not manifest_path.exists():
        qa_status = "missing"
        message = "External import manifest is missing."
    elif severity_counts.get("error", 0) > 0 or manifest_status in {"missing_profile", "missing_source", "not_ready"}:
        qa_status = "failed"
        message = "External import has blocking validation errors."
    elif missing_files or manifest_status == "partial" or severity_counts.get("warning", 0) > 0 or mapped_count == 0:
        qa_status = "partial"
        message = "External import is usable with caution; review missing files, warnings, or unmapped features."
    else:
        qa_status = "passed"
        message = "External import passed QA checks and has reaction-level overlay rows."
    return {
        "qa_status": qa_status,
        "message": message,
        "manifest_status": manifest_status,
        "missing_files": ";".join(missing_files),
        "mapped_feature_count": mapped_count,
        "unmapped_feature_count": unmapped_count,
        "overlay_row_count": overlay_count,
        "validation_error_count": severity_counts.get("error", 0),
        "validation_warning_count": severity_counts.get("warning", 0),
        "validation_info_count": severity_counts.get("info", 0),
        "interpretation_note": "External ML feature importance is predictive marker evidence, not causal mechanism proof.",
    }


def count_validation_severities(rows: list[dict[str, str]]) -> dict[str, int]:
    counts = {"error": 0, "warning": 0, "info": 0}
    for row in rows:
        severity = str(row.get("severity", "")).lower()
        if severity in counts:
            counts[severity] += 1
    return counts


def top_importance_rows(rows: list[dict[str, str]], limit: int = 40) -> list[dict[str, str]]:
    return sorted(rows, key=lambda row: _to_float(row.get("importance_score")) or 0.0, reverse=True)[:limit]


def write_omics_gem_profile_bundle(detail: dict[str, Any], output: Path) -> dict[str, Any]:
    """Write a complete Omics-GEM profile bundle from existing profile files."""

    output.mkdir(parents=True, exist_ok=True)
    files = detail.get("files", {}) if isinstance(detail.get("files"), dict) else {}
    copied: dict[str, str] = {}
    missing: list[str] = []
    copy_keys = [
        "config",
        "feature_matrix",
        "target_table",
        "sample_metadata",
        "feature_annotation",
        "model_variant_context",
        "profile_summary",
        "prediction_table",
        "model_metrics",
        "benchmark_summary",
        "benchmark_matrix",
        "feature_importance",
        "gem_feature_importance",
        "subsystem_importance_summary",
        "production_candidate_explainability",
        "ml_feature_importance_overlay",
        "manifest",
    ]
    for key in copy_keys:
        source = Path(str(files.get(key, "")))
        if not source.exists():
            missing.append(key)
            continue
        target = output / source.name
        shutil.copy2(source, target)
        copied[key] = str(target)

    readme_path = output / "README.md"
    manifest_path = output / "export_manifest.json"
    target_ready = "ready" if detail.get("profile_summary") and detail.get("status") == "completed" else "not_ready"
    manifest = {
        "schema_version": "0.1.0",
        "status": "completed" if not missing else "partial",
        "message": "Omics-GEM profile bundle exported." if not missing else "Omics-GEM bundle exported with missing optional files.",
        "export_format": "omics_gem_profile_bundle",
        "profile_id": detail.get("profile_id", ""),
        "profile_status": detail.get("status", ""),
        "target_readiness": target_ready,
        "output_dir": str(output),
        "missing_files": missing,
        "files": {
            **copied,
            "readme": str(readme_path),
            "manifest": str(manifest_path),
        },
    }
    readme_path.write_text(render_profile_bundle_readme(manifest), encoding="utf-8")
    write_json(manifest_path, manifest)
    return manifest


def write_flexynesis_like_inputs(detail: dict[str, Any], output: Path) -> dict[str, Any]:
    """Write Flexynesis-inspired multi-view tables from one profile matrix."""

    output.mkdir(parents=True, exist_ok=True)
    files = detail.get("files", {}) if isinstance(detail.get("files"), dict) else {}
    matrix_rows = read_optional_table(Path(str(files.get("feature_matrix", ""))))
    target_rows = read_optional_table(Path(str(files.get("target_table", ""))))
    sample_rows = read_optional_table(Path(str(files.get("sample_metadata", ""))))
    target_column = str((detail.get("manifest") or {}).get("target_column") or "")
    feature_columns = [
        column
        for column in (matrix_rows[0].keys() if matrix_rows else [])
        if column not in {"condition", "sample_id", target_column}
    ]
    grouped = {
        "omics_view": [column for column in feature_columns if classify_feature_view(column) == "omics_view"],
        "flux_view": [column for column in feature_columns if classify_feature_view(column) == "flux_view"],
        "kcat_readiness_view": [column for column in feature_columns if classify_feature_view(column) == "kcat_readiness_view"],
        "production_view": [column for column in feature_columns if classify_feature_view(column) == "production_view"],
    }
    output_files: dict[str, str] = {}
    for view_name, columns in grouped.items():
        path = output / f"{view_name}.csv"
        write_csv(path, project_feature_view_rows(matrix_rows, columns))
        output_files[view_name] = str(path)
    clinical_path = output / "clinical_or_target.csv"
    metadata_path = output / "sample_metadata.csv"
    feature_annotation_path = output / "feature_annotation.csv"
    readme_path = output / "README.md"
    manifest_path = output / "export_manifest.json"
    write_csv(clinical_path, target_rows or target_not_ready_rows(matrix_rows, target_column))
    write_csv(metadata_path, sample_rows or sample_metadata_from_matrix(matrix_rows))
    if Path(str(files.get("feature_annotation", ""))).exists():
        shutil.copy2(Path(str(files["feature_annotation"])), feature_annotation_path)
    else:
        write_csv(feature_annotation_path, [{"status": "missing", "message": "feature_annotation.csv was not available."}])
    output_files.update(
        {
            "clinical_or_target": str(clinical_path),
            "sample_metadata": str(metadata_path),
            "feature_annotation": str(feature_annotation_path),
        }
    )
    target_readiness = "ready" if target_rows else "not_ready"
    manifest = {
        "schema_version": "0.1.0",
        "status": "completed" if target_rows else "partial",
        "message": "Flexynesis-like input tables exported." if target_rows else "Feature views exported; target table is not ready.",
        "export_format": "flexynesis_like_inputs",
        "profile_id": detail.get("profile_id", ""),
        "profile_status": detail.get("status", ""),
        "target_readiness": target_readiness,
        "feature_view_count": sum(1 for columns in grouped.values() if columns),
        "feature_view_columns": {key: columns for key, columns in grouped.items()},
        "output_dir": str(output),
        "files": {
            **output_files,
            "readme": str(readme_path),
            "manifest": str(manifest_path),
        },
        "notes": [
            "These files follow Flexynesis-style multi-view input organization but do not include or run Flexynesis.",
            "Use clinical_or_target.csv as phenotype/label input after confirming target semantics.",
        ],
    }
    readme_path.write_text(render_flexynesis_like_readme(manifest), encoding="utf-8")
    write_json(manifest_path, manifest)
    return manifest


def normalize_profile_export_format(export_format: str) -> list[str]:
    raw = str(export_format or "both").strip().lower()
    aliases = {
        "omics_gem_bundle": "omics_gem_profile_bundle",
        "omics_gem_profile_bundle": "omics_gem_profile_bundle",
        "flexynesis_like_inputs": "flexynesis_like_inputs",
    }
    if raw == "both":
        return ["omics_gem_profile_bundle", "flexynesis_like_inputs"]
    values = [aliases.get(token.strip(), "") for token in re.split(r"[;,\s]+", raw) if token.strip()]
    normalized = [value for value in values if value]
    return normalized or ["omics_gem_profile_bundle", "flexynesis_like_inputs"]


def classify_feature_view(feature_id: str) -> str:
    text = feature_id.lower()
    if any(token in text for token in ("production", "fseof", "target", "ko_", "kd_", "oe_", "design")):
        return "production_view"
    if any(token in text for token in ("kcat", "readiness", "uniprot", "gpr", "enzyme", "gecko")):
        return "kcat_readiness_view"
    if any(token in text for token in ("flux", "fba", "pfba", "exchange", "objective")):
        return "flux_view"
    return "omics_view"


def project_feature_view_rows(matrix_rows: list[dict[str, str]], feature_columns: list[str]) -> list[dict[str, object]]:
    if not matrix_rows:
        return [{"sample_id": "", "status": "empty_matrix"}]
    rows: list[dict[str, object]] = []
    for index, record in enumerate(matrix_rows, start=1):
        row: dict[str, object] = {
            "sample_id": record.get("condition") or record.get("sample_id") or f"sample_{index}",
            "condition": record.get("condition", ""),
        }
        if not feature_columns:
            row["status"] = "no_features_for_view"
        for column in feature_columns:
            row[column] = record.get(column, "")
        rows.append(row)
    return rows


def target_not_ready_rows(matrix_rows: list[dict[str, str]], target_column: str) -> list[dict[str, object]]:
    if not matrix_rows:
        return [{"sample_id": "", "target_column": target_column, "status": "not_ready", "message": "feature matrix is empty"}]
    rows: list[dict[str, object]] = []
    for index, record in enumerate(matrix_rows, start=1):
        rows.append(
            {
                "sample_id": record.get("condition") or record.get("sample_id") or f"sample_{index}",
                "condition": record.get("condition", ""),
                "target_column": target_column,
                "target_value": record.get(target_column, "") if target_column else "",
                "status": "not_ready",
                "message": "No usable target_table.csv rows were available for this profile.",
            }
        )
    return rows


def sample_metadata_from_matrix(matrix_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    if not matrix_rows:
        return [{"sample_id": "", "condition": "", "status": "empty_matrix"}]
    rows: list[dict[str, object]] = []
    for index, record in enumerate(matrix_rows, start=1):
        rows.append(
            {
                "sample_id": record.get("condition") or record.get("sample_id") or f"sample_{index}",
                "condition": record.get("condition", ""),
                "status": "available",
            }
        )
    return rows


def render_profile_bundle_readme(manifest: dict[str, Any]) -> str:
    return f"""# Omics-GEM ML/HYBRID Profile Bundle

Profile: `{manifest.get("profile_id", "")}`

Status: `{manifest.get("status", "")}`

This folder is a reproducible Omics-GEM profile export. It contains the profile
configuration, feature matrix, target table, benchmark outputs, GEM feature
importance, subsystem importance, production candidate explainability, and the
source profile manifest when available.

Important interpretation note: feature importance is predictive marker evidence,
not causal mechanism proof.
"""


def render_flexynesis_like_readme(manifest: dict[str, Any]) -> str:
    return f"""# Flexynesis-Like Inputs

Profile: `{manifest.get("profile_id", "")}`

Target readiness: `{manifest.get("target_readiness", "")}`

This folder organizes one Omics-GEM ML/HYBRID profile into multi-view tables
inspired by Flexynesis-style bulk multi-omics inputs:

- `omics_view.csv`
- `flux_view.csv`
- `kcat_readiness_view.csv`
- `production_view.csv`
- `clinical_or_target.csv`
- `sample_metadata.csv`
- `feature_annotation.csv`

This export does not include or run Flexynesis. Confirm target semantics before
using `clinical_or_target.csv` with any external ML backend.
"""


def ml_hybrid_profile_comparison_row(
    manifest: dict[str, Any],
    benchmark_matrix: list[dict[str, str]],
    gem_importance: list[dict[str, str]],
    production_explainability: list[dict[str, str]],
) -> dict[str, Any]:
    task_type = str(manifest.get("task_type") or "")
    best = best_benchmark_row([dict(row) for row in benchmark_matrix], task_type)
    metric_name = best_metric_name(task_type)
    stronger = sum(
        1
        for row in production_explainability
        if str(row.get("interpretation_label") or "").strip() == "stronger_evidence_candidate"
    )
    warnings = sum(1 for row in gem_importance if str(row.get("warning_flag") or "").strip())
    subsystems = {str(row.get("subsystem") or "").strip() for row in gem_importance if str(row.get("subsystem") or "").strip()}
    output_dir = str(manifest.get("output_dir") or "")
    manifest_path = str(manifest.get("files", {}).get("manifest") or "")
    modified_at = 0.0
    if manifest_path and Path(manifest_path).exists():
        modified_at = Path(manifest_path).stat().st_mtime
    return {
        "profile_id": str(manifest.get("profile_id") or ""),
        "status": str(manifest.get("status") or ""),
        "task_type": task_type,
        "target_column": str(manifest.get("target_column") or ""),
        "sample_count": manifest.get("sample_count", 0),
        "feature_count": manifest.get("feature_count", 0),
        "best_model_id": str(manifest.get("best_model_id") or best.get("model_id") or ""),
        "best_feature_set": str(manifest.get("best_feature_set") or best.get("feature_set") or ""),
        "best_metric_name": metric_name,
        "best_metric_value": str(best.get(metric_name) or ""),
        "production_overlap_count": stronger,
        "warning_feature_count": warnings,
        "subsystem_count": len(subsystems),
        "output_dir": output_dir,
        "manifest_path": manifest_path,
        "modified_at": modified_at,
        "modified_at_iso": datetime.fromtimestamp(modified_at).isoformat(timespec="seconds") if modified_at else "",
    }


def best_metric_name(task_type: str) -> str:
    if task_type == "classification":
        return "balanced_accuracy"
    if task_type == "regression":
        return "r2"
    return "score"


def best_profile_comparison_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    completed = [row for row in rows if row.get("status") == "completed"]
    candidates = completed or rows

    def score(row: dict[str, Any]) -> tuple[float, float, float]:
        task = str(row.get("task_type") or "")
        value = _to_float(row.get("best_metric_value"))
        if value is None:
            value = -9999.0 if task == "regression" else 0.0
        return (
            value,
            float(_to_float(row.get("production_overlap_count")) or 0.0),
            float(_to_float(row.get("modified_at")) or 0.0),
        )

    return sorted(candidates, key=score, reverse=True)[0] if candidates else {}


def normalize_existing_profile_id(profile_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(profile_id or "").strip()).strip("._-")
    return cleaned


def profile_files(output: Path) -> dict[str, str]:
    results = output / "results"
    return {
        "config": str(output / "profile_config.json"),
        "feature_matrix": str(output / "feature_matrix.csv"),
        "target_table": str(output / "target_table.csv"),
        "sample_metadata": str(output / "sample_metadata.csv"),
        "feature_annotation": str(output / "feature_annotation.csv"),
        "model_variant_context": str(output / "model_variant_context.csv"),
        "profile_summary": str(output / "profile_summary.csv"),
        "prediction_table": str(results / "prediction_table.csv"),
        "model_metrics": str(results / "model_metrics.csv"),
        "benchmark_summary": str(results / "benchmark_summary.csv"),
        "benchmark_matrix": str(results / "benchmark_matrix.csv"),
        "feature_importance": str(results / "feature_importance.csv"),
        "gem_feature_importance": str(results / "gem_feature_importance.csv"),
        "subsystem_importance_summary": str(results / "subsystem_importance_summary.csv"),
        "production_candidate_explainability": str(results / "production_candidate_explainability.csv"),
        "ml_feature_importance_overlay": str(results / "ml_feature_importance_overlay.csv"),
        "manifest": str(results / "profile_manifest.json"),
    }


def normalize_profile_id(profile_id: str) -> str:
    raw = profile_id.strip() or f"profile_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._-")
    return cleaned or f"profile_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def normalize_external_import_id(import_id: str) -> str:
    raw = str(import_id or "").strip() or f"external_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._-")
    return cleaned or f"external_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def normalize_external_result_format(result_format: str) -> str:
    fmt = str(result_format or "generic_tabular").strip().lower()
    return fmt if fmt in {"generic_tabular", "flexynesis_like"} else "generic_tabular"


def external_import_files(output: Path) -> dict[str, str]:
    return {
        "manifest": str(output / "external_import_manifest.json"),
        "summary": str(output / "external_import_summary.csv"),
        "validation_flags": str(output / "external_validation_flags.csv"),
        "normalized_prediction_table": str(output / "normalized_prediction_table.csv"),
        "normalized_model_metrics": str(output / "normalized_model_metrics.csv"),
        "normalized_feature_importance": str(output / "normalized_feature_importance.csv"),
        "gem_feature_importance": str(output / "gem_external_feature_importance.csv"),
        "overlay": str(output / "external_ml_feature_importance_overlay.csv"),
    }


def normalize_task_type(task_type: str) -> str:
    task = str(task_type or "auto").strip().lower()
    return task if task in {"auto", "regression", "classification", "survival", "multi_task"} else "auto"


def normalize_feature_sources(feature_sources: Iterable[str] | str | None) -> list[str]:
    if feature_sources is None:
        return []
    if isinstance(feature_sources, str):
        values = re.split(r"[;,\s]+", feature_sources)
    else:
        values = [str(item) for item in feature_sources]
    return sorted({value.strip() for value in values if value and value.strip()})


DEFAULT_BENCHMARK_FEATURE_SETS = [
    "all_features",
    "omics_only",
    "flux_only",
    "readiness_or_kcat",
    "production_related",
]


def normalize_benchmark_feature_sets(feature_sets: Iterable[str] | str | None) -> list[str]:
    allowed = set(DEFAULT_BENCHMARK_FEATURE_SETS)
    if feature_sets is None or feature_sets == "":
        return list(DEFAULT_BENCHMARK_FEATURE_SETS)
    if isinstance(feature_sets, str):
        values = re.split(r"[;,\s]+", feature_sets)
    else:
        values = [str(item) for item in feature_sets]
    normalized = [value.strip() for value in values if value.strip() in allowed]
    return normalized or list(DEFAULT_BENCHMARK_FEATURE_SETS)


def read_optional_table(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return read_csv_records(path)


def find_external_result_file(source: Path, names: list[str]) -> Path | None:
    if not source.exists() or not source.is_dir():
        return None
    name_lookup = {name.lower(): name for name in names}
    for child in source.iterdir():
        if child.is_file() and child.name.lower() in name_lookup:
            return child
    for name in names:
        direct = source / name
        if direct.exists() and direct.is_file():
            return direct
    return None


def validation_flag(severity: str, flag: str, message: str, source_file: str) -> dict[str, str]:
    return {
        "severity": severity,
        "flag": flag,
        "message": message,
        "source_file": source_file,
    }


def normalize_external_prediction_rows(rows: list[dict[str, str]], source_file: Path) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        merged = dict(row)
        merged.setdefault("sample_id", first_existing_value(row, ["sample_id", "sample", "condition", "id"]) or f"sample_{index}")
        merged.setdefault("prediction", first_existing_value(row, ["prediction", "predicted", "y_pred", "score"]) or "")
        merged.setdefault("observed", first_existing_value(row, ["observed", "true", "actual", "y_true", "target"]) or "")
        merged["source_file"] = str(source_file)
        normalized.append(merged)
    return normalized


def normalize_external_metric_rows(rows: list[dict[str, str]], source_file: Path) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        merged = dict(row)
        merged.setdefault("model_id", first_existing_value(row, ["model_id", "model", "method"]) or f"external_model_{index}")
        merged.setdefault("metric_name", first_existing_value(row, ["metric_name", "metric", "name"]) or "")
        merged.setdefault("metric_value", first_existing_value(row, ["metric_value", "value", "score"]) or "")
        merged["source_file"] = str(source_file)
        normalized.append(merged)
    return normalized


def normalize_external_feature_importance_rows(rows: list[dict[str, str]], source_file: Path) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        feature_id = first_existing_value(
            row,
            ["feature_id", "feature", "feature_name", "name", "variable", "gene", "reaction_id", "entity_id"],
        )
        reaction_id = first_existing_value(row, ["reaction_id", "model_reaction_id", "cobra_reaction_id"])
        if not feature_id and reaction_id:
            feature_id = reaction_id
        score_raw = first_existing_value(
            row,
            ["importance_score", "importance", "weight", "coefficient", "coef", "score", "attribution", "shap_value"],
        )
        score = _to_float(score_raw)
        normalized.append(
            {
                "feature_id": feature_id or f"external_feature_{index}",
                "raw_feature_id": feature_id or "",
                "model_id": first_existing_value(row, ["model_id", "model", "method"]) or "external_model",
                "importance_score": "" if score is None else round(abs(score), 6),
                "importance_signed": "" if score is None else round(score, 6),
                "reaction_id_hint": canonical_reaction_id(reaction_id or ""),
                "source": first_existing_value(row, ["source", "view", "feature_set", "modality"]) or "external_ml_result",
                "rank": first_existing_value(row, ["rank", "importance_rank"]) or index,
                "source_file": str(source_file),
            }
        )
    return normalized


def first_existing_value(row: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    lower_lookup = {str(key).lower(): value for key, value in row.items()}
    for key in keys:
        value = lower_lookup.get(key.lower())
        if value not in (None, ""):
            return str(value)
    return ""


def resolve_target_column(matrix_rows: list[dict[str, str]], requested: str) -> str:
    if not matrix_rows:
        return requested.strip()
    columns = list(matrix_rows[0].keys())
    if requested and requested in columns:
        return requested
    for column in columns:
        if column.startswith("phenotype_") or column.startswith("target_") or column.startswith("label_"):
            return column
    return requested.strip()


def select_feature_columns(
    matrix_rows: list[dict[str, str]],
    target_column: str,
    feature_sources: list[str],
    *,
    max_features: int,
) -> list[str]:
    if not matrix_rows:
        return []
    columns = [column for column in matrix_rows[0].keys() if column != "condition" and column != target_column]
    if feature_sources:
        columns = [
            column
            for column in columns
            if any(column == source or column.startswith(f"{source}::") or column.startswith(source) for source in feature_sources)
        ]
    ranked = sorted(columns, key=lambda column: (-numeric_value_count(matrix_rows, column), column))
    return ranked[:max_features]


def project_matrix(matrix_rows: list[dict[str, str]], target_column: str, feature_columns: list[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in matrix_rows:
        row: dict[str, object] = {"condition": record.get("condition", "")}
        if target_column:
            row[target_column] = record.get(target_column, "")
        for feature in feature_columns:
            row[feature] = record.get(feature, "")
        rows.append(row)
    return rows


def build_target_rows(matrix_rows: list[dict[str, object]], target_column: str) -> list[dict[str, object]]:
    if not target_column:
        return []
    rows: list[dict[str, object]] = []
    for record in matrix_rows:
        value = record.get(target_column, "")
        if value in {"", None}:
            continue
        rows.append(
            {
                "condition": record.get("condition", ""),
                "target_column": target_column,
                "target_value": value,
                "target_numeric_value": _to_float(value) if _to_float(value) is not None else "",
                "target_label": "" if _to_float(value) is not None else str(value),
                "status": "available",
            }
        )
    return rows


def resolve_task_type(requested: str, target_rows: list[dict[str, object]]) -> str:
    if requested in {"regression", "classification"}:
        return requested
    if requested in {"survival", "multi_task"}:
        return requested
    if not target_rows:
        return ""
    numeric_count = sum(1 for row in target_rows if _to_float(row.get("target_value")) is not None)
    if numeric_count == len(target_rows):
        return "regression"
    return "classification"


def build_feature_annotation(package: Path, feature_columns: list[str]) -> list[dict[str, object]]:
    long_rows = read_optional_table(package / "ml_results" / "ml_feature_long.csv")
    by_feature: dict[str, dict[str, str]] = {}
    for row in long_rows:
        feature_id = row.get("feature_id", "")
        if feature_id and feature_id not in by_feature:
            by_feature[feature_id] = row
    rows: list[dict[str, object]] = []
    for feature in feature_columns:
        parsed = parse_feature_id(feature)
        source = by_feature.get(feature, {})
        rows.append(
            {
                "feature_id": feature,
                "feature_type": source.get("feature_type") or parsed["feature_type"],
                "entity_type": parsed["entity_type"],
                "entity_id": source.get("entity_id") or parsed["entity_id"],
                "source": source.get("source") or parsed["feature_type"],
                "status": source.get("status", ""),
                "evidence": source.get("evidence", ""),
                "note": source.get("note", ""),
            }
        )
    return rows


def build_sample_metadata(matrix_rows: list[dict[str, object]], target_column: str, feature_columns: list[str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in matrix_rows:
        available = sum(1 for feature in feature_columns if record.get(feature) not in {"", None})
        rows.append(
            {
                "condition": record.get("condition", ""),
                "feature_count_available": available,
                "target_column": target_column,
                "target_available": bool(target_column and record.get(target_column) not in {"", None}),
                "status": "available" if available else "no_features",
            }
        )
    return rows


def build_model_variant_context(package: Path, selected_variant_ids: list[str]) -> list[dict[str, object]]:
    registry = read_model_variant_registry(package)
    selected = set(selected_variant_ids)
    if not selected:
        selected = {str(row.get("variant_id", "")) for row in registry if row.get("variant_id")}
    rows: list[dict[str, object]] = []
    for row in registry:
        variant_id = str(row.get("variant_id", ""))
        if selected and variant_id not in selected:
            continue
        rows.append(
            {
                "variant_id": variant_id,
                "generation_method": row.get("generation_method", ""),
                "generation_method_label": row.get("generation_method_label", ""),
                "condition": row.get("condition", ""),
                "primary_model_path": row.get("primary_model_path", ""),
                "confidence": row.get("confidence", ""),
                "status": row.get("generation_status", row.get("status", "")),
            }
        )
    return rows


def run_lightweight_benchmark(
    matrix_rows: list[dict[str, object]],
    target_column: str,
    feature_columns: list[str],
    task_type: str,
) -> dict[str, list[dict[str, object]]]:
    if task_type == "regression":
        return run_regression_benchmark(matrix_rows, target_column, feature_columns)
    if task_type == "classification":
        return run_classification_benchmark(matrix_rows, target_column, feature_columns)
    return {"predictions": [], "metrics": [], "benchmark_summary": [], "feature_importance": []}


def run_benchmark_feature_sets(
    matrix_rows: list[dict[str, object]],
    target_column: str,
    feature_columns: list[str],
    task_type: str,
    feature_sets: list[str],
) -> dict[str, list[dict[str, object]]]:
    predictions: list[dict[str, object]] = []
    metrics: list[dict[str, object]] = []
    summaries: list[dict[str, object]] = []
    importance_rows: list[dict[str, object]] = []
    benchmark_matrix: list[dict[str, object]] = []
    seen_importance: set[tuple[str, str, str]] = set()
    for feature_set in feature_sets:
        subset = feature_subset_columns(feature_columns, feature_set)
        result = run_lightweight_benchmark(matrix_rows, target_column, subset, task_type)
        for collection_name, target in (
            ("predictions", predictions),
            ("metrics", metrics),
            ("benchmark_summary", summaries),
            ("feature_importance", importance_rows),
        ):
            for row in result.get(collection_name, []):
                enriched = dict(row)
                enriched["feature_set"] = feature_set
                if collection_name == "feature_importance":
                    key = (str(enriched.get("feature_set", "")), str(enriched.get("model_id", "")), str(enriched.get("feature_id", "")))
                    if key in seen_importance:
                        continue
                    seen_importance.add(key)
                target.append(enriched)
        for row in result.get("metrics", []):
            benchmark_matrix.append(benchmark_matrix_row(row, feature_set, len(subset), task_type))
    return {
        "predictions": predictions,
        "metrics": metrics,
        "benchmark_summary": summaries,
        "feature_importance": importance_rows,
        "benchmark_matrix": benchmark_matrix,
    }


def feature_subset_columns(feature_columns: list[str], feature_set: str) -> list[str]:
    if feature_set == "all_features":
        return feature_columns
    if feature_set == "omics_only":
        return [
            feature
            for feature in feature_columns
            if any(token in feature for token in ("tx_", "prot_", "metabol", "transcript", "protein"))
        ]
    if feature_set == "flux_only":
        return [feature for feature in feature_columns if "flux" in feature or feature.startswith(("fba_", "pfba_", "eflux_"))]
    if feature_set == "readiness_or_kcat":
        return [feature for feature in feature_columns if "readiness" in feature or "kcat" in feature or "uniprot" in feature]
    if feature_set == "production_related":
        return [feature for feature in feature_columns if "production" in feature or "fseof" in feature or "target" in feature]
    return feature_columns


def benchmark_matrix_row(row: dict[str, object], feature_set: str, feature_count: int, task_type: str) -> dict[str, object]:
    return {
        "feature_set": feature_set,
        "model_id": row.get("model_id", ""),
        "task_type": task_type,
        "feature_count": feature_count,
        "sample_count": row.get("sample_count", ""),
        "rmse": row.get("rmse", ""),
        "mae": row.get("mae", ""),
        "r2": row.get("r2", ""),
        "accuracy": row.get("accuracy", ""),
        "balanced_accuracy": row.get("balanced_accuracy", ""),
        "selected_feature_id": row.get("selected_feature_id", ""),
        "feature_importance_score": row.get("feature_importance_score", ""),
        "status": row.get("status", ""),
    }


def run_regression_benchmark(
    matrix_rows: list[dict[str, object]],
    target_column: str,
    feature_columns: list[str],
) -> dict[str, list[dict[str, object]]]:
    target_pairs = [(row, _to_float(row.get(target_column))) for row in matrix_rows]
    target_pairs = [(row, value) for row, value in target_pairs if value is not None]
    if not target_pairs:
        return {"predictions": [], "metrics": [], "benchmark_summary": [], "feature_importance": []}
    values = [float(value) for _row, value in target_pairs]
    mean_value = sum(values) / len(values)
    predictions = regression_prediction_rows(target_pairs, "mean_baseline", [mean_value] * len(target_pairs))
    metrics = [regression_metric_row("mean_baseline", values, [mean_value] * len(values), "", 0.0)]
    benchmark_rows = [benchmark_row(metrics[-1], "Mean target baseline.")]
    importance_rows: list[dict[str, object]] = []

    best = best_regression_feature(target_pairs, feature_columns)
    if best:
        feature, slope, intercept, corr = best
        feature_predictions = []
        for row, _target in target_pairs:
            x = _to_float(row.get(feature))
            feature_predictions.append((intercept + slope * x) if x is not None else mean_value)
        predictions.extend(regression_prediction_rows(target_pairs, "best_univariate_feature", feature_predictions))
        metrics.append(regression_metric_row("best_univariate_feature", values, feature_predictions, feature, abs(corr)))
        benchmark_rows.append(benchmark_row(metrics[-1], "Best single numeric feature by absolute Pearson correlation."))
        importance_rows.append(feature_importance_row("best_univariate_feature", feature, abs(corr), "positive" if corr > 0 else "negative"))
    return {
        "predictions": predictions,
        "metrics": metrics,
        "benchmark_summary": benchmark_rows,
        "feature_importance": importance_rows,
    }


def run_classification_benchmark(
    matrix_rows: list[dict[str, object]],
    target_column: str,
    feature_columns: list[str],
) -> dict[str, list[dict[str, object]]]:
    target_pairs = [(row, str(row.get(target_column, ""))) for row in matrix_rows if row.get(target_column) not in {"", None}]
    if not target_pairs:
        return {"predictions": [], "metrics": [], "benchmark_summary": [], "feature_importance": []}
    labels = [label for _row, label in target_pairs]
    majority = majority_label(labels)
    majority_predictions = [majority] * len(labels)
    predictions = classification_prediction_rows(target_pairs, "majority_baseline", majority_predictions)
    metrics = [classification_metric_row("majority_baseline", labels, majority_predictions, "", 0.0)]
    benchmark_rows = [benchmark_row(metrics[-1], "Majority-class baseline.")]
    importance_rows: list[dict[str, object]] = []

    best = best_classification_feature(target_pairs, feature_columns)
    if best:
        feature, centroids, separation = best
        centroid_predictions = []
        for row, _label in target_pairs:
            x = _to_float(row.get(feature))
            centroid_predictions.append(predict_nearest_centroid(x, centroids, majority))
        predictions.extend(classification_prediction_rows(target_pairs, "nearest_centroid_lite", centroid_predictions))
        metrics.append(classification_metric_row("nearest_centroid_lite", labels, centroid_predictions, feature, separation))
        benchmark_rows.append(benchmark_row(metrics[-1], "Nearest-centroid baseline using the best single numeric feature."))
        importance_rows.append(feature_importance_row("nearest_centroid_lite", feature, separation, "class_separation"))
    return {
        "predictions": predictions,
        "metrics": metrics,
        "benchmark_summary": benchmark_rows,
        "feature_importance": importance_rows,
    }


def regression_prediction_rows(
    target_pairs: list[tuple[dict[str, object], float]],
    model_id: str,
    predictions: list[float],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for (record, target), predicted in zip(target_pairs, predictions):
        rows.append(
            {
                "condition": record.get("condition", ""),
                "model_id": model_id,
                "feature_set": "",
                "task_type": "regression",
                "target_value": round(target, 6),
                "predicted_value": round(predicted, 6),
                "predicted_label": "",
                "residual": round(target - predicted, 6),
                "status": "completed",
            }
        )
    return rows


def classification_prediction_rows(
    target_pairs: list[tuple[dict[str, object], str]],
    model_id: str,
    predictions: list[str],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for (record, target), predicted in zip(target_pairs, predictions):
        rows.append(
            {
                "condition": record.get("condition", ""),
                "model_id": model_id,
                "feature_set": "",
                "task_type": "classification",
                "target_value": target,
                "predicted_value": "",
                "predicted_label": predicted,
                "residual": "",
                "status": "completed",
            }
        )
    return rows


def regression_metric_row(
    model_id: str,
    targets: list[float],
    predictions: list[float],
    feature_id: str,
    importance: float,
) -> dict[str, object]:
    residuals = [target - predicted for target, predicted in zip(targets, predictions)]
    mse = sum(value * value for value in residuals) / len(residuals) if residuals else 0.0
    mae = sum(abs(value) for value in residuals) / len(residuals) if residuals else 0.0
    mean_target = sum(targets) / len(targets) if targets else 0.0
    total = sum((value - mean_target) ** 2 for value in targets)
    ss_res = sum(value * value for value in residuals)
    r2 = 1.0 - ss_res / total if total else 0.0
    return {
        "model_id": model_id,
        "task_type": "regression",
        "sample_count": len(targets),
        "rmse": round(math.sqrt(mse), 6),
        "mae": round(mae, 6),
        "r2": round(r2, 6),
        "accuracy": "",
        "balanced_accuracy": "",
        "selected_feature_id": feature_id,
        "feature_importance_score": round(importance, 6),
        "status": "completed",
    }


def classification_metric_row(
    model_id: str,
    labels: list[str],
    predictions: list[str],
    feature_id: str,
    importance: float,
) -> dict[str, object]:
    accuracy = sum(1 for label, predicted in zip(labels, predictions) if label == predicted) / len(labels) if labels else 0.0
    classes = sorted(set(labels))
    recalls = []
    for label in classes:
        total = sum(1 for item in labels if item == label)
        correct = sum(1 for item, predicted in zip(labels, predictions) if item == label and predicted == label)
        recalls.append(correct / total if total else 0.0)
    balanced = sum(recalls) / len(recalls) if recalls else 0.0
    return {
        "model_id": model_id,
        "task_type": "classification",
        "sample_count": len(labels),
        "rmse": "",
        "mae": "",
        "r2": "",
        "accuracy": round(accuracy, 6),
        "balanced_accuracy": round(balanced, 6),
        "selected_feature_id": feature_id,
        "feature_importance_score": round(importance, 6),
        "status": "completed",
    }


def benchmark_row(metric: dict[str, object], guidance: str) -> dict[str, object]:
    row = dict(metric)
    row["guidance"] = guidance
    return row


def feature_importance_row(model_id: str, feature_id: str, score: float, direction: str) -> dict[str, object]:
    parsed = parse_feature_id(feature_id)
    return {
        "model_id": model_id,
        "feature_id": feature_id,
        "feature_type": parsed["feature_type"],
        "entity_type": parsed["entity_type"],
        "entity_id": parsed["entity_id"],
        "importance_score": round(float(score), 6),
        "direction": direction,
        "status": "predictive_marker",
    }


def best_regression_feature(
    target_pairs: list[tuple[dict[str, object], float]],
    feature_columns: list[str],
) -> tuple[str, float, float, float] | None:
    best: tuple[str, float, float, float] | None = None
    for feature in feature_columns:
        pairs = [(float(_to_float(row.get(feature))), target) for row, target in target_pairs if _to_float(row.get(feature)) is not None]
        if len(pairs) < 2:
            continue
        xs = [item[0] for item in pairs]
        ys = [item[1] for item in pairs]
        corr = pearson(xs, ys)
        if corr is None:
            continue
        variance = sum((x - sum(xs) / len(xs)) ** 2 for x in xs)
        if variance == 0:
            continue
        covariance = sum((x - sum(xs) / len(xs)) * (y - sum(ys) / len(ys)) for x, y in pairs)
        slope = covariance / variance
        intercept = sum(ys) / len(ys) - slope * (sum(xs) / len(xs))
        candidate = (feature, slope, intercept, corr)
        if best is None or abs(candidate[3]) > abs(best[3]):
            best = candidate
    return best


def best_classification_feature(
    target_pairs: list[tuple[dict[str, object], str]],
    feature_columns: list[str],
) -> tuple[str, dict[str, float], float] | None:
    best: tuple[str, dict[str, float], float] | None = None
    for feature in feature_columns:
        grouped: dict[str, list[float]] = {}
        for row, label in target_pairs:
            value = _to_float(row.get(feature))
            if value is not None:
                grouped.setdefault(label, []).append(value)
        if len(grouped) < 2:
            continue
        centroids = {label: sum(values) / len(values) for label, values in grouped.items() if values}
        if len(centroids) < 2:
            continue
        separation = max(centroids.values()) - min(centroids.values())
        candidate = (feature, centroids, abs(separation))
        if best is None or candidate[2] > best[2]:
            best = candidate
    return best


def predict_nearest_centroid(value: float | None, centroids: dict[str, float], fallback: str) -> str:
    if value is None or not centroids:
        return fallback
    return sorted(centroids.items(), key=lambda item: (abs(item[1] - value), item[0]))[0][0]


def build_gem_feature_importance(package: Path, feature_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    subsystem_index = build_subsystem_index(package)
    production_candidates = production_candidate_reactions(package)
    warning_index = reaction_warning_index(package)
    rows: list[dict[str, object]] = []
    for row in feature_rows:
        parsed = parse_feature_id(str(row.get("feature_id", "")))
        reaction_id = parsed["reaction_id"]
        warning = warning_index.get(reaction_id, "")
        is_production = reaction_id in production_candidates if reaction_id else False
        importance = _to_float(row.get("importance_score")) or 0.0
        if is_production and importance >= 0.5:
            label = "stronger_evidence_candidate"
            note = "High-importance predictive feature overlaps a production/design candidate."
        elif warning:
            label = "caution"
            note = "Predictive feature maps to a reaction with semantic/readiness warning; treat as review evidence."
        else:
            label = "predictive_marker"
            note = "Predictive marker only; do not interpret as causal mechanism without validation."
        rows.append(
            {
                "feature_set": row.get("feature_set", ""),
                "model_id": row.get("model_id", ""),
                "feature_id": row.get("feature_id", ""),
                "entity_type": parsed["entity_type"],
                "entity_id": parsed["entity_id"],
                "reaction_id": reaction_id,
                "subsystem": subsystem_index.get(reaction_id, ""),
                "importance_score": row.get("importance_score", ""),
                "source": parsed["feature_type"],
                "interpretation_label": label,
                "warning_label": warning,
                "interpretation_note": note,
            }
        )
    return rows


def build_subsystem_importance_summary(gem_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in gem_rows:
        subsystem = str(row.get("subsystem") or "unannotated")
        grouped.setdefault(subsystem, []).append(row)
    summary: list[dict[str, object]] = []
    for subsystem, rows in sorted(grouped.items()):
        scores = [_to_float(row.get("importance_score")) or 0.0 for row in rows]
        warning_count = sum(1 for row in rows if row.get("warning_label"))
        production_overlap_count = sum(1 for row in rows if row.get("interpretation_label") == "stronger_evidence_candidate")
        top = sorted(rows, key=lambda row: _to_float(row.get("importance_score")) or 0.0, reverse=True)[:10]
        summary.append(
            {
                "subsystem": subsystem,
                "feature_count": len(rows),
                "total_importance_score": round(sum(scores), 6),
                "max_importance_score": round(max(scores) if scores else 0.0, 6),
                "warning_count": warning_count,
                "production_overlap_count": production_overlap_count,
                "top_reactions": ";".join(str(row.get("reaction_id", "")) for row in top if row.get("reaction_id")),
                "interpretation_note": "Subsystem-level predictive marker summary; not a causal pathway proof.",
            }
        )
    if not summary:
        return [
            {
                "subsystem": "none",
                "feature_count": 0,
                "total_importance_score": 0,
                "max_importance_score": 0,
                "warning_count": 0,
                "production_overlap_count": 0,
                "top_reactions": "",
                "interpretation_note": "No reaction-level ML feature importance was available.",
            }
        ]
    return summary


def build_production_candidate_explainability(package: Path, gem_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    candidates = production_candidate_reactions(package)
    if not candidates:
        return [
            {
                "reaction_id": "",
                "status": "empty_guidance",
                "interpretation_label": "exploratory",
                "importance_score": "",
                "subsystem": "",
                "warning_label": "",
                "guidance": "No production/design candidate table was found; run Production Analysis before ML-production overlap review.",
            }
        ]
    by_reaction: dict[str, dict[str, object]] = {}
    for row in gem_rows:
        reaction = str(row.get("reaction_id", ""))
        if reaction and reaction not in by_reaction:
            by_reaction[reaction] = row
        elif reaction:
            current = _to_float(by_reaction[reaction].get("importance_score")) or 0.0
            candidate = _to_float(row.get("importance_score")) or 0.0
            if candidate > current:
                by_reaction[reaction] = row
    rows: list[dict[str, object]] = []
    for reaction in sorted(candidates):
        match = by_reaction.get(reaction, {})
        score = _to_float(match.get("importance_score"))
        warning = str(match.get("warning_label", ""))
        if score is not None and score >= 0.5:
            label = "stronger_evidence_candidate"
        elif warning:
            label = "caution"
        else:
            label = "exploratory"
        rows.append(
            {
                "reaction_id": reaction,
                "status": "available" if match else "candidate_without_ml_importance",
                "interpretation_label": label,
                "importance_score": "" if score is None else round(score, 6),
                "subsystem": match.get("subsystem", ""),
                "warning_label": warning,
                "guidance": production_explainability_guidance(label),
            }
        )
    return rows


def production_explainability_guidance(label: str) -> str:
    if label == "stronger_evidence_candidate":
        return "Production/design candidate overlaps a high-importance ML marker; prioritize for review."
    if label == "caution":
        return "Candidate has warning/readiness caution; inspect evidence before action."
    return "Production candidate lacks strong ML support in this profile; keep exploratory."


def build_ml_feature_importance_overlay(gem_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    by_reaction: dict[str, dict[str, object]] = {}
    for row in gem_rows:
        reaction = str(row.get("reaction_id", ""))
        if not reaction:
            continue
        current = by_reaction.get(reaction)
        if current is None or (_to_float(row.get("importance_score")) or 0.0) > (_to_float(current.get("importance_score")) or 0.0):
            by_reaction[reaction] = row
    for reaction, row in sorted(by_reaction.items()):
        score = _to_float(row.get("importance_score")) or 0.0
        warning = bool(row.get("warning_label")) or row.get("interpretation_label") == "caution"
        color = "#7c3aed" if row.get("interpretation_label") == "stronger_evidence_candidate" else "#0f766e"
        if warning:
            color = "#dc2626"
        rows.append(
            {
                "overlay_source": "ml_feature_importance",
                "semantic_type": "ml_importance",
                "condition": "ALL",
                "reaction_id": reaction,
                "cobra_reaction_id": reaction[2:] if reaction.startswith("R_") else reaction,
                "importance_score": round(score, 6),
                "overlay_value": round(score, 6),
                "overlay_value_column": "importance_score",
                "overlay_color": color,
                "overlay_size": round(1.0 + min(4.0, abs(score) * 4.0), 4),
                "warning_flag": warning,
                "readiness_label": row.get("interpretation_label", ""),
                "status": row.get("interpretation_label", "predictive_marker"),
                "evidence": row.get("source", ""),
                "warning_reasons": row.get("warning_label", ""),
                "source_file": "ml_hybrid_profile",
                "source_status": "available",
            }
        )
    if not rows:
        return [
            {
                "overlay_source": "ml_feature_importance",
                "semantic_type": "ml_importance",
                "condition": "",
                "reaction_id": "",
                "cobra_reaction_id": "",
                "importance_score": "",
                "overlay_value": "",
                "overlay_value_column": "importance_score",
                "overlay_color": "#94a3b8",
                "overlay_size": 1.0,
                "warning_flag": False,
                "readiness_label": "empty_guidance",
                "status": "empty_guidance",
                "evidence": "",
                "warning_reasons": "No reaction-level ML feature importance is available.",
                "source_file": "ml_hybrid_profile",
                "source_status": "empty_guidance",
            }
        ]
    return rows


def build_external_gem_feature_importance(package: Path, feature_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    subsystem_index = build_subsystem_index(package)
    production_candidates = production_candidate_reactions(package)
    warning_index = reaction_warning_index(package)
    rows: list[dict[str, object]] = []
    for row in feature_rows:
        raw_feature_id = str(row.get("feature_id", ""))
        parsed = parse_feature_id(raw_feature_id)
        reaction_id = canonical_reaction_id(row.get("reaction_id_hint", "")) or parsed["reaction_id"]
        if not reaction_id and "::" not in raw_feature_id:
            candidate = canonical_reaction_id(raw_feature_id)
            if raw_feature_id.startswith("R_") or candidate in subsystem_index or candidate in production_candidates or candidate in warning_index:
                reaction_id = candidate
        warning = warning_index.get(reaction_id, "")
        importance = _to_float(row.get("importance_score")) or 0.0
        if reaction_id and reaction_id in production_candidates and importance >= 0.5:
            label = "stronger_evidence_candidate"
            note = "External ML marker overlaps a production/design candidate; prioritize for review."
        elif warning:
            label = "readiness_caution"
            note = "External ML marker maps to a reaction with UniProt/GPR/kcat/readiness caution."
        elif reaction_id:
            label = "matched_gem_feature"
            note = "External ML marker maps to a GEM reaction; interpret as predictive evidence only."
        else:
            label = "unmapped_feature"
            note = "External feature could not be mapped to a GEM reaction and remains external-only."
        rows.append(
            {
                "feature_id": row.get("feature_id", ""),
                "raw_feature_id": row.get("raw_feature_id", ""),
                "entity_type": "reaction" if reaction_id else "external_feature",
                "entity_id": parsed["entity_id"],
                "reaction_id": reaction_id,
                "subsystem": subsystem_index.get(reaction_id, ""),
                "importance_score": row.get("importance_score", ""),
                "importance_signed": row.get("importance_signed", ""),
                "source": row.get("source", "external_ml_result"),
                "model_id": row.get("model_id", "external_model"),
                "interpretation_label": label,
                "warning_label": warning,
                "mapping_status": "matched_gem_feature" if reaction_id else "unmapped_feature",
                "external_status": "external_only_marker" if not reaction_id else "mapped_external_marker",
                "interpretation_note": note,
                "source_file": row.get("source_file", ""),
            }
        )
    return rows


def build_external_ml_feature_importance_overlay(gem_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    by_reaction: dict[str, dict[str, object]] = {}
    for row in gem_rows:
        reaction = str(row.get("reaction_id", ""))
        if not reaction:
            continue
        current = by_reaction.get(reaction)
        if current is None or (_to_float(row.get("importance_score")) or 0.0) > (_to_float(current.get("importance_score")) or 0.0):
            by_reaction[reaction] = row
    for reaction, row in sorted(by_reaction.items()):
        score = _to_float(row.get("importance_score")) or 0.0
        label = str(row.get("interpretation_label") or "matched_gem_feature")
        warning = label in {"readiness_caution", "caution"} or bool(row.get("warning_label"))
        color = "#7c3aed" if label == "stronger_evidence_candidate" else "#2563eb"
        if warning:
            color = "#dc2626"
        rows.append(
            {
                "overlay_source": "external_ml_feature_importance",
                "semantic_type": "ml_importance",
                "condition": "ALL",
                "reaction_id": reaction,
                "cobra_reaction_id": reaction[2:] if reaction.startswith("R_") else reaction,
                "importance_score": round(score, 6),
                "overlay_value": round(score, 6),
                "overlay_value_column": "importance_score",
                "overlay_color": color,
                "overlay_size": round(1.0 + min(4.0, abs(score) * 4.0), 4),
                "warning_flag": warning,
                "readiness_label": label,
                "status": label,
                "evidence": row.get("source", "external_ml_result"),
                "warning_reasons": row.get("warning_label", ""),
                "source_file": row.get("source_file", "external_ml_result"),
                "source_status": "available",
            }
        )
    if not rows:
        return [
            {
                "overlay_source": "external_ml_feature_importance",
                "semantic_type": "ml_importance",
                "condition": "",
                "reaction_id": "",
                "cobra_reaction_id": "",
                "importance_score": "",
                "overlay_value": "",
                "overlay_value_column": "importance_score",
                "overlay_color": "#94a3b8",
                "overlay_size": 1.0,
                "warning_flag": False,
                "readiness_label": "empty_guidance",
                "status": "empty_guidance",
                "evidence": "",
                "warning_reasons": "No reaction-level external ML feature importance is available.",
                "source_file": "external_ml_result",
                "source_status": "empty_guidance",
            }
        ]
    return rows


def external_import_status(
    profile_detail: dict[str, Any],
    source: Path,
    predictions: list[dict[str, Any]],
    metrics: list[dict[str, Any]],
    importance: list[dict[str, Any]],
    validation_rows: list[dict[str, Any]],
) -> str:
    if profile_detail.get("status") == "missing":
        return "missing_profile"
    if not source.exists() or not source.is_dir():
        return "missing_source"
    if not predictions and not metrics and not importance:
        return "not_ready"
    if any(row.get("severity") in {"error"} for row in validation_rows) or not importance or not metrics:
        return "partial"
    return "completed"


def external_import_message(status: str, import_id: str, importance_rows: list[dict[str, Any]], gem_rows: list[dict[str, Any]]) -> str:
    if status == "missing_profile":
        return "External ML result import skipped because the selected profile was not found."
    if status == "missing_source":
        return "External ML result import skipped because the source folder was not found."
    if status == "not_ready":
        return "External ML result folder did not contain recognized prediction, metrics, or feature importance tables."
    mapped = sum(1 for row in gem_rows if row.get("reaction_id"))
    return f"Imported external ML results as {import_id}; mapped {mapped} of {len(importance_rows)} importance feature(s) to GEM reactions."


def build_subsystem_index(package: Path) -> dict[str, str]:
    index: dict[str, str] = {}
    for path in (package / "visualization_results" / "sammi").glob("*/subsystem_reaction_assignment.csv"):
        for row in read_optional_table(path):
            reaction_id = canonical_reaction_id(row.get("reaction_id") or row.get("cobra_reaction_id") or "")
            subsystem = row.get("subsystem") or row.get("group_label") or row.get("group_id") or ""
            if reaction_id and subsystem:
                index[reaction_id] = subsystem
    for model_path in model_paths(package):
        try:
            for row in parse_sbml_reactions(model_path):
                reaction_id = canonical_reaction_id(str(row.get("reaction_id", "")))
                if reaction_id and reaction_id not in index:
                    index[reaction_id] = str(row.get("subsystem", ""))
        except Exception:
            continue
    return index


def model_paths(package: Path) -> list[Path]:
    paths: list[Path] = []
    for row in read_optional_table(package / "input_file_map.csv"):
        role = " ".join([row.get("kind", ""), row.get("role", "")]).lower()
        if "model" not in role and "gem" not in role:
            continue
        path = resolve_package_path(package, row.get("path") or row.get("relative_path", ""))
        if path.exists():
            paths.append(path)
    for row in read_model_variant_registry(package):
        path = resolve_package_path(package, row.get("primary_model_path", "") or row.get("source_model_path", ""))
        if path.exists():
            paths.append(path)
    return paths


def resolve_package_path(package: Path, path_text: str) -> Path:
    path = Path(str(path_text or ""))
    return path if path.is_absolute() else package / path


def production_candidate_reactions(package: Path) -> set[str]:
    paths = [
        package / "production_results" / "production_design_targets.csv",
        package / "production_results" / "production_target_ranking.csv",
        package / "production_results" / "fseof_lite_reaction_targets.csv",
        package / "production_results" / "fseof_reaction_targets.csv",
    ]
    reactions: set[str] = set()
    for path in paths:
        for row in read_optional_table(path):
            for key in ("reaction_id", "model_reaction_id", "target_id", "candidate_reaction_id", "design_reaction_id"):
                reaction = canonical_reaction_id(row.get(key, ""))
                if reaction:
                    reactions.add(reaction)
    return reactions


def reaction_warning_index(package: Path) -> dict[str, str]:
    paths = [
        package / "uniprot_model_check" / "reaction_annotation_flags.csv",
        package / "generated_constraints" / "kcat_conflict_flags.csv",
        package / "production_results" / "production_design_readiness.csv",
        package / "production_results" / "production_target_readiness.csv",
    ]
    warnings: dict[str, str] = {}
    for path in paths:
        for row in read_optional_table(path):
            reaction = canonical_reaction_id(row.get("reaction_id") or row.get("model_reaction_id") or row.get("target_id") or "")
            if not reaction:
                continue
            label = row.get("warning_flag") or row.get("status") or row.get("readiness_label") or row.get("production_readiness_label") or ""
            if label and any(token in str(label).lower() for token in ("warning", "conflict", "caution", "missing", "failed")):
                warnings[reaction] = str(label)
    return warnings


def parse_feature_id(feature_id: str) -> dict[str, str]:
    feature_type, _, entity = feature_id.partition("::")
    entity = entity or feature_id
    entity_type = "feature"
    reaction_id = ""
    if feature_type.endswith("_gene") or feature_type in {"gene", "tx_gene", "prot_gene"}:
        entity_type = "gene"
    elif (
        feature_type.endswith("_reaction")
        or feature_type.endswith("_flux")
        or "reaction" in feature_type
        or "flux" in feature_type
    ):
        entity_type = "reaction"
        reaction_id = canonical_reaction_id(entity)
    elif feature_type.startswith("kcat"):
        entity_type = "enzyme"
        reaction_id = canonical_reaction_id(entity)
    elif feature_type.startswith("production"):
        entity_type = "production"
        reaction_id = canonical_reaction_id(entity)
    return {
        "feature_type": feature_type,
        "entity_type": entity_type,
        "entity_id": entity,
        "reaction_id": reaction_id,
    }


def canonical_reaction_id(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith("R_"):
        return text
    if re.match(r"^[A-Za-z][A-Za-z0-9_]*$", text):
        return f"R_{text}"
    return text


def profile_status(
    matrix_rows: list[dict[str, str]],
    target_column: str,
    target_rows: list[dict[str, object]],
    task_type: str,
    benchmark: dict[str, list[dict[str, object]]],
) -> str:
    if not matrix_rows:
        return "not_ready"
    if not target_column or not target_rows:
        return "not_ready"
    if task_type in {"survival", "multi_task", ""}:
        return "not_ready"
    if not benchmark.get("metrics"):
        return "not_ready"
    return "completed"


def best_benchmark_row(rows: list[dict[str, object]], task_type: str) -> dict[str, object]:
    if not rows:
        return {}
    if task_type == "regression":
        return sorted(rows, key=lambda row: (-(_to_float(row.get("r2")) or -9999.0), _to_float(row.get("rmse")) or 9999.0))[0]
    if task_type == "classification":
        return sorted(rows, key=lambda row: (-(_to_float(row.get("balanced_accuracy")) or 0.0), -(_to_float(row.get("accuracy")) or 0.0)))[0]
    return rows[0]


def profile_message(status: str, profile_id: str, task_type: str, sample_count: int, feature_count: int) -> str:
    if status == "completed":
        return f"Built ML/HYBRID profile {profile_id} with {sample_count} samples, {feature_count} features, and {task_type} baselines."
    return "ML/HYBRID profile is not ready; provide a feature matrix and a target column with usable labels."


def profile_guidance(status: str, task_type: str) -> str:
    if status == "completed":
        return f"{task_type} baseline benchmark is available; interpret feature importance as predictive marker evidence."
    return "No runnable benchmark was produced. Check target_column, phenotype labels, and feature matrix coverage."


def numeric_value_count(rows: list[dict[str, str]], column: str) -> int:
    return sum(1 for row in rows if _to_float(row.get(column)) is not None)


def _to_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(parsed) or math.isinf(parsed):
        return None
    return parsed


def pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs))
    den_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def majority_label(labels: list[str]) -> str:
    counts = {label: labels.count(label) for label in set(labels)}
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    import json

    return json.loads(path.read_text(encoding="utf-8"))
