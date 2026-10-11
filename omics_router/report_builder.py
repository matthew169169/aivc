"""Preset report bundle builder for staged Omics-GEM packages."""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .constraints import read_csv_records, write_csv, write_json
from .ml_hybrid_profile import (
    compare_ml_hybrid_profiles,
    list_ml_hybrid_external_results,
    list_ml_hybrid_profile_exports,
    list_ml_hybrid_profiles,
)
from .model_generation import normalize_selected_model_variant_ids
from .report import build_cobra_report
from .sammi_native_export import list_sammi_native_exports


REPORT_PRESETS: dict[str, dict[str, str]] = {
    "full_audit_report": {
        "label": "Full audit report",
        "description": "Complete integrated audit report, compatible with the legacy COBRA report.",
    },
    "model_generation_report": {
        "label": "Model generation report",
        "description": "Model-variant registry, generation artifacts, and evidence quality.",
    },
    "single_variant_analysis_report": {
        "label": "Single-variant analysis report",
        "description": "Analysis context and FBA output for one selected model variant.",
    },
    "multi_variant_comparison_report": {
        "label": "Multi-variant comparison report",
        "description": "Side-by-side variant registry, FBA, feasibility, and evidence-quality comparison.",
    },
    "production_design_report": {
        "label": "Production design report",
        "description": "Production Analysis, ecFactory-lite, FSEOF-lite, and readiness outputs.",
    },
    "ml_hybrid_report": {
        "label": "ML / hybrid report",
        "description": "PCA/LASSO-lite, MINN-style export, hybrid runner, and graph adapter outputs.",
    },
    "shewanella_trigger_reproduction_report": {
        "label": "Shewanella trigger reproduction report",
        "description": "Paper reproduction evidence chain, guarded algorithm status, and report-ready caveats.",
    },
}


@dataclass(slots=True)
class ReportBundleResult:
    """Result returned after a preset report bundle is written."""

    status: str
    message: str
    report_path: str
    manifest_path: str
    selection_path: str


def build_report_bundle(
    package_dir: str | Path,
    preset: str,
    active_variant_id: Iterable[str] | str | None = "",
    output_dir: str | Path | None = None,
) -> ReportBundleResult:
    """Build a selected report preset and write its manifest."""

    package = Path(package_dir)
    preset_id = preset if preset in REPORT_PRESETS else "full_audit_report"
    output = Path(output_dir) if output_dir else package / "report_results"
    output.mkdir(parents=True, exist_ok=True)
    selected_variants = normalize_selected_model_variant_ids(active_variant_id)

    report_path = output / f"{preset_id}.html"
    selection_path = output / "report_selection.csv"
    manifest_path = output / "report_manifest.json"
    selection_rows = [
        {
            "preset": preset_id,
            "preset_label": REPORT_PRESETS[preset_id]["label"],
            "active_variant_id": selected_variants[0] if selected_variants else "",
            "selected_variant_ids": ";".join(selected_variants),
            "output_html": str(report_path),
        }
    ]
    write_csv(selection_path, selection_rows)

    if preset_id == "full_audit_report":
        build_cobra_report(package / "cobra_results", report_path, title=REPORT_PRESETS[preset_id]["label"])
    else:
        data = _load_report_data(package)
        sections = _sections_for_preset(preset_id, data, selected_variants, package)
        report_path.write_text(
            _render_preset_html(
                title=REPORT_PRESETS[preset_id]["label"],
                description=REPORT_PRESETS[preset_id]["description"],
                preset=preset_id,
                selected_variants=selected_variants,
                sections=sections,
            ),
            encoding="utf-8",
        )

    manifest_files = {
        "report_html": str(report_path),
        "report_selection": str(selection_path),
    }
    if preset_id == "shewanella_trigger_reproduction_report":
        paper_manifest_path = output / "paper_reproduction_report_manifest.json"
        write_json(
            paper_manifest_path,
            {
                "schema_version": "0.1.0",
                "status": "completed",
                "preset": preset_id,
                "report_html": str(report_path),
                "package_dir": str(package),
                "reproduction_boundary": {
                    "GDM-lite": "computed_lite",
                    "D2T2": "paper_reported_only",
                    "dFBA/glycogen": "paper_reported_model_prediction_available",
                    "condition_bounds": "not_generated",
                    "enzyme_capacity": "not_applicable",
                },
            },
        )
        manifest_files["paper_reproduction_report_manifest"] = str(paper_manifest_path)

    write_json(
        manifest_path,
        {
            "schema_version": "0.1.0",
            "status": "completed",
            "preset": preset_id,
            "preset_label": REPORT_PRESETS[preset_id]["label"],
            "package_dir": str(package),
            "output_dir": str(output),
            "active_variant_id": selected_variants[0] if selected_variants else "",
            "selected_variant_ids": selected_variants,
            "files": manifest_files,
        },
    )
    return ReportBundleResult(
        status="completed",
        message=f"Built {REPORT_PRESETS[preset_id]['label']} at {report_path}.",
        report_path=str(report_path),
        manifest_path=str(manifest_path),
        selection_path=str(selection_path),
    )


def _load_report_data(package: Path) -> dict[str, list[dict[str, str]]]:
    return {
        "workflow_selection": _read_table(package / "workflow_results" / "workflow_selection.csv"),
        "model_generation_parameters": _read_table(package / "workflow_results" / "model_generation_parameters_summary.csv"),
        "analysis_parameters": _read_table(package / "workflow_results" / "analysis_parameters_summary.csv"),
        "model_variant_registry": _read_table(package / "workflow_results" / "model_variant_registry.csv"),
        "analysis_variant_context": _read_table(package / "workflow_results" / "analysis_variant_context.csv"),
        "context_model_artifacts": _read_table(package / "workflow_results" / "context_model_artifact_summary.csv"),
        "variant_fba_summary": _read_table(package / "variant_cobra_results" / "variant_fba_summary.csv"),
        "variant_comparison_summary": _read_table(package / "variant_comparison" / "variant_comparison_summary.csv"),
        "variant_flux_comparison": _read_table(package / "variant_comparison" / "variant_flux_comparison.csv"),
        "variant_evidence_quality": _read_table(package / "variant_comparison" / "variant_evidence_quality.csv"),
        "production_summary": _read_table(package / "production_results" / "production_analysis_summary.csv"),
        "production_envelope": _read_table(package / "production_results" / "production_envelope.csv"),
        "production_target_ranking": _read_table(package / "production_results" / "production_target_ranking.csv"),
        "fseof_lite_reaction_targets": _read_table(package / "production_results" / "fseof_lite_reaction_targets.csv"),
        "production_design_targets": _read_table(package / "production_results" / "production_design_targets.csv"),
        "production_gene_targets": _read_table(package / "production_results" / "production_gene_targets.csv"),
        "production_readiness_summary": _read_table(package / "production_results" / "production_readiness_summary.csv"),
        "production_target_readiness": _read_table(package / "production_results" / "production_target_readiness.csv"),
        "production_design_readiness": _read_table(package / "production_results" / "production_design_readiness.csv"),
        "production_gene_readiness": _read_table(package / "production_results" / "production_gene_readiness.csv"),
        "gecko_external_summary": _read_table(package / "gecko_run_results" / "gecko_external_run_summary.csv"),
        "gecko_flux_delta": _read_table(package / "gecko_run_results" / "gecko_flux_delta_high_vs_low.csv"),
        "gecko_enzyme_usage_high": _read_table(package / "gecko_run_results" / "gecko_enzyme_usage_highO2.csv"),
        "gecko_enzyme_usage_low": _read_table(package / "gecko_run_results" / "gecko_enzyme_usage_lowO2.csv"),
        "ml_feature_summary": _read_table(package / "ml_results" / "ml_feature_summary.csv"),
        "ml_analysis_summary": _read_table(package / "ml_results" / "ml_analysis_summary.csv"),
        "ml_diagnostic_summary": _read_table(package / "ml_results" / "ml_diagnostic_summary.csv"),
        "ml_pca_scores": _read_table(package / "ml_results" / "ml_pca_scores.csv"),
        "ml_condition_clusters": _read_table(package / "ml_results" / "ml_condition_clusters.csv"),
        "ml_lasso_lite": _read_table(package / "ml_results" / "ml_lasso_lite_coefficients.csv"),
        "minn_summary": _read_table(package / "minn_export" / "minn_export_summary.csv"),
        "minn_readiness_summary": _read_table(package / "minn_export" / "minn_readiness_summary.csv"),
        "minn_readiness_priors": _read_table(package / "minn_export" / "minn_readiness_target_priors.csv"),
        "minn_readiness_weights": _read_table(package / "minn_export" / "minn_readiness_sample_weights.csv"),
        "hybrid_summary": _read_table(package / "hybrid_results" / "hybrid_runner_summary.csv"),
        "hybrid_target_scores": _read_table(package / "hybrid_results" / "hybrid_target_scores.csv"),
        "hybrid_loocv_summary": _read_table(package / "hybrid_results" / "hybrid_loocv_summary.csv"),
        "hybrid_loocv_evaluation": _read_table(package / "hybrid_results" / "hybrid_loocv_evaluation.csv"),
        "hybrid_adapter_summary": _read_table(package / "hybrid_adapter_results" / "hybrid_graph_adapter_summary.csv"),
        "hybrid_adapter_flags": _read_table(package / "hybrid_adapter_results" / "hybrid_graph_adapter_validation_flags.csv"),
        "ml_hybrid_profile_summary": _read_glob_tables(package / "ml_hybrid_profiles", "*/profile_summary.csv"),
        "ml_hybrid_benchmark_summary": _read_glob_tables(package / "ml_hybrid_profiles", "*/results/benchmark_summary.csv"),
        "ml_hybrid_benchmark_matrix": _read_glob_tables(package / "ml_hybrid_profiles", "*/results/benchmark_matrix.csv"),
        "ml_hybrid_model_metrics": _read_glob_tables(package / "ml_hybrid_profiles", "*/results/model_metrics.csv"),
        "ml_hybrid_gem_feature_importance": _read_glob_tables(
            package / "ml_hybrid_profiles",
            "*/results/gem_feature_importance.csv",
        ),
        "ml_hybrid_subsystem_importance": _read_glob_tables(
            package / "ml_hybrid_profiles",
            "*/results/subsystem_importance_summary.csv",
        ),
        "ml_hybrid_production_explainability": _read_glob_tables(
            package / "ml_hybrid_profiles",
            "*/results/production_candidate_explainability.csv",
        ),
        "ml_hybrid_profile_discovery": [
            {key: str(value) for key, value in row.items()}
            for row in list_ml_hybrid_profiles(package)
        ],
        "ml_hybrid_profile_comparison": [
            {key: str(value) for key, value in row.items()}
            for row in compare_ml_hybrid_profiles(package).get("comparison", [])
        ],
        "ml_hybrid_profile_exports": _ml_hybrid_profile_export_rows(package),
        "ml_hybrid_external_imports": _ml_hybrid_external_import_rows(package),
        "ml_hybrid_external_import_qa": _ml_hybrid_external_import_qa_rows(package),
        "ml_hybrid_external_import_summary": _read_glob_tables(
            package / "ml_hybrid_profiles",
            "*/external_results/*/external_import_summary.csv",
        ),
        "ml_hybrid_external_validation_flags": _read_glob_tables(
            package / "ml_hybrid_profiles",
            "*/external_results/*/external_validation_flags.csv",
        ),
        "ml_hybrid_external_gem_feature_importance": _read_glob_tables(
            package / "ml_hybrid_profiles",
            "*/external_results/*/gem_external_feature_importance.csv",
        ),
        "interactive_visualization_summary": _read_glob_tables(
            package / "visualization_results" / "sammi",
            "*/interactive_map_summary.csv",
        ),
        "production_visualization_summary": _read_glob_tables(
            package / "visualization_results" / "sammi",
            "*/production_visualization_summary.csv",
        ),
        "sammi_native_export_summary": _read_glob_tables(
            package / "visualization_results" / "sammi",
            "*/sammi_native_export_summary.csv",
        ),
        "sammi_native_export_discovery": [
            {key: str(value) for key, value in row.items()}
            for row in list_sammi_native_exports(package).get("exports", [])
        ],
    }


def _sections_for_preset(
    preset: str,
    data: dict[str, list[dict[str, str]]],
    selected_variants: list[str],
    package: Path,
) -> list[tuple[str, str]]:
    if preset == "model_generation_report":
        return [
            ("Workflow Selection", _render_table(data["workflow_selection"])),
            ("Model Generation Parameters", _render_table(data["model_generation_parameters"])),
            ("Model Variant Registry", _render_table(data["model_variant_registry"])),
            ("Context Model Artifacts", _render_table(data["context_model_artifacts"])),
            ("Variant Evidence Quality", _render_table(data["variant_evidence_quality"])),
            ("Interactive Visualization", _render_table(data["interactive_visualization_summary"])),
            ("SAMMI Native Export", _render_table(data["sammi_native_export_summary"])),
            ("SAMMI Native Session Loading", _render_table(data["sammi_native_export_discovery"])),
        ]
    if preset == "single_variant_analysis_report":
        selected = selected_variants[:1]
        return [
            ("Selected Variant", _render_table(_filter_variants(data["model_variant_registry"], selected, "variant_id"))),
            ("Analysis Variant Context", _render_table(_filter_variants(data["analysis_variant_context"], selected, "active_variant_id"))),
            ("Analysis Parameters", _render_table(data["analysis_parameters"])),
            ("Variant FBA / pFBA", _render_table(_filter_variants(data["variant_fba_summary"], selected, "variant_id"))),
            ("Variant Comparison Summary", _render_table(_filter_variants(data["variant_comparison_summary"], selected, "variant_id"))),
            ("Interactive Visualization", _render_table(_filter_variants(data["interactive_visualization_summary"], selected, "variant_id"))),
            ("SAMMI Native Export", _render_table(_filter_variants(data["sammi_native_export_summary"], selected, "variant_id"))),
            ("SAMMI Native Session Loading", _render_table(_filter_variants(data["sammi_native_export_discovery"], selected, "variant_id"))),
        ]
    if preset == "multi_variant_comparison_report":
        selected = selected_variants
        return [
            ("Variant Comparison Summary", _render_table(_filter_variants(data["variant_comparison_summary"], selected, "variant_id"))),
            ("Variant Flux Comparison", _render_table(_filter_variants(data["variant_flux_comparison"], selected, "variant_id"))),
            ("Variant Evidence Quality", _render_table(_filter_variants(data["variant_evidence_quality"], selected, "variant_id"))),
            ("Model Variant Registry", _render_table(_filter_variants(data["model_variant_registry"], selected, "variant_id"))),
            ("Model Generation Parameters", _render_table(data["model_generation_parameters"])),
            ("Analysis Parameters", _render_table(data["analysis_parameters"])),
            ("Interactive Visualization", _render_table(_filter_variants(data["interactive_visualization_summary"], selected, "variant_id"))),
            ("SAMMI Native Export", _render_table(_filter_variants(data["sammi_native_export_summary"], selected, "variant_id"))),
            ("SAMMI Native Session Loading", _render_table(_filter_variants(data["sammi_native_export_discovery"], selected, "variant_id"))),
        ]
    if preset == "production_design_report":
        return [
            ("Production Analysis Summary", _render_table(data["production_summary"])),
            ("Production / Analysis Parameters", _render_table(data["analysis_parameters"])),
            ("Production Readiness Summary", _render_table(data["production_readiness_summary"])),
            ("Production Target Ranking", _render_table(data["production_target_ranking"])),
            ("FSEOF-lite Reaction Targets", _render_table(data["fseof_lite_reaction_targets"])),
            ("Production Design Targets", _render_table(data["production_design_targets"])),
            ("Production Gene Targets", _render_table(data["production_gene_targets"])),
            ("Production Visualization", _render_table(data["production_visualization_summary"])),
            ("Shewanella GECKO External Run", _render_table(data["gecko_external_summary"])),
            ("Shewanella GECKO Flux Delta", _render_table(data["gecko_flux_delta"][:80])),
            ("Shewanella GECKO Enzyme Usage High O2", _render_table(data["gecko_enzyme_usage_high"][:80])),
            ("Shewanella GECKO Enzyme Usage Low O2", _render_table(data["gecko_enzyme_usage_low"][:80])),
            ("Target Readiness", _render_table(data["production_target_readiness"])),
            ("Design Readiness", _render_table(data["production_design_readiness"])),
            ("Gene Readiness", _render_table(data["production_gene_readiness"])),
            ("Interactive Visualization", _render_table(data["interactive_visualization_summary"])),
            ("SAMMI Native Export", _render_table(data["sammi_native_export_summary"])),
            ("SAMMI Native Session Loading", _render_table(data["sammi_native_export_discovery"])),
        ]
    if preset == "ml_hybrid_report":
        return [
            ("ML Feature Summary", _render_table(data["ml_feature_summary"])),
            ("ML / Analysis Parameters", _render_table(data["analysis_parameters"])),
            ("ML Analysis Summary", _render_table(data["ml_analysis_summary"])),
            ("ML Diagnostics", _render_table(data["ml_diagnostic_summary"])),
            ("PCA Scores", _render_table(data["ml_pca_scores"][:40])),
            ("Condition Clusters", _render_table(data["ml_condition_clusters"])),
            ("LASSO-lite Coefficients", _render_table(data["ml_lasso_lite"][:40])),
            ("MINN-style Readiness Export", _render_table(data["minn_readiness_summary"])),
            ("Readiness Target Priors", _render_table(data["minn_readiness_priors"][:40])),
            ("Readiness Sample Weights", _render_table(data["minn_readiness_weights"])),
            ("Hybrid Runner Summary", _render_table(data["hybrid_summary"])),
            ("Hybrid Target Scores", _render_table(data["hybrid_target_scores"][:40])),
            ("Hybrid LOOCV Summary", _render_table(data["hybrid_loocv_summary"])),
            ("Hybrid LOOCV Evaluation", _render_table(data["hybrid_loocv_evaluation"])),
            ("Graph Adapter Summary", _render_table(data["hybrid_adapter_summary"])),
            ("Graph Adapter Flags", _render_table(data["hybrid_adapter_flags"])),
            ("ML/HYBRID Profile Discovery", _render_table(data["ml_hybrid_profile_discovery"])),
            ("ML/HYBRID Profile Comparison", _render_table(data["ml_hybrid_profile_comparison"])),
            ("ML/HYBRID Profile Export Bundle", _render_table(data["ml_hybrid_profile_exports"])),
            ("External ML Results", _render_table(data["ml_hybrid_external_imports"])),
            ("External Import Detail / QA", _render_table(data["ml_hybrid_external_import_qa"])),
            ("External ML Import Summary", _render_table(data["ml_hybrid_external_import_summary"])),
            ("External ML Validation Flags", _render_table(data["ml_hybrid_external_validation_flags"])),
            ("External ML GEM Feature Importance", _render_table(data["ml_hybrid_external_gem_feature_importance"][:40])),
            ("ML/HYBRID Profile Summary", _render_table(data["ml_hybrid_profile_summary"])),
            ("ML/HYBRID Benchmark Summary", _render_table(data["ml_hybrid_benchmark_summary"])),
            ("ML/HYBRID Benchmark Matrix", _render_table(data["ml_hybrid_benchmark_matrix"])),
            ("ML/HYBRID Model Metrics", _render_table(data["ml_hybrid_model_metrics"])),
            ("GEM Feature Importance", _render_table(data["ml_hybrid_gem_feature_importance"][:40])),
            ("Subsystem Importance", _render_table(data["ml_hybrid_subsystem_importance"])),
            ("Production Candidate Explainability", _render_table(data["ml_hybrid_production_explainability"])),
        ]
    if preset == "shewanella_trigger_reproduction_report":
        return _shewanella_trigger_report_sections(package)
    return [("Report", "<p>No preset sections were configured.</p>")]


def _shewanella_trigger_report_sections(package: Path) -> list[tuple[str, str]]:
    case_dir = package / "case_study"
    manifest = _read_json_object(case_dir / "paper_reproduction_manifest.json")
    data_needed = _read_json_object(case_dir / "data_needed_manifest.json")
    growth_state = _read_json_object(case_dir / "growth_state_map_data.json")
    trigger_timeline = _read_json_object(case_dir / "trigger_timeline_data.json")
    gdm_lite = _read_json_object(case_dir / "gdm_lite_results.json")
    dfba = _read_json_object(case_dir / "dfba_glycogen_scenario.json")
    mapping = _read_json_object(case_dir / "paper_evidence_mapping_summary.json")
    supplement = _read_json_object(case_dir / "supplement_download_manifest.json")
    gdm_classes = _read_table(case_dir / "gdm_gene_classes.csv")
    d2t2_rows = _read_table(case_dir / "d2t2_trigger_genes.csv")
    overlay_rows = _read_table(case_dir / "paper_evidence_reaction_overlay.csv")

    algorithm_status = manifest.get("algorithm_status") if isinstance(manifest.get("algorithm_status"), dict) else {}
    artifacts = manifest.get("artifacts") if isinstance(manifest.get("artifacts"), dict) else {}
    gaps = data_needed.get("still_missing_or_guarded") if isinstance(data_needed.get("still_missing_or_guarded"), list) else []

    summary_cards = [
        {"metric": "Case", "value": manifest.get("case_id", "shewanella_transcriptional_triggers_lac_lb")},
        {"metric": "Round 2 status", "value": manifest.get("round_2_status", manifest.get("status", "partial_computed_lite"))},
        {"metric": "GDM-lite", "value": algorithm_status.get("GDM-lite", "computed_lite")},
        {"metric": "D2T2", "value": algorithm_status.get("D2T2", "paper_reported_only")},
        {"metric": "dFBA/glycogen", "value": algorithm_status.get("dFBA/glycogen", "paper_reported_model_prediction_available")},
        {"metric": "Condition bounds", "value": algorithm_status.get("condition_bounds", "not_generated")},
        {"metric": "Enzyme capacity", "value": algorithm_status.get("enzyme_capacity", "not_applicable")},
        {"metric": "Mapped reactions", "value": mapping.get("mapped_reaction_count", "not_available")},
    ]
    source_rows = [
        {"artifact": key, "path": str(value)}
        for key, value in sorted(artifacts.items())
    ][:40]
    gap_rows = [
        {
            "artifact": str(row.get("artifact", "")),
            "needed_for": "; ".join(str(item) for item in row.get("needed_for", [])) if isinstance(row, dict) else "",
            "status": str(row.get("status", "")) if isinstance(row, dict) else "",
            "source_note": str(row.get("source_note", "")) if isinstance(row, dict) else "",
        }
        for row in gaps
        if isinstance(row, dict)
    ]
    return [
        (
            "Reproduction Conclusion",
            _render_key_value_cards(summary_cards)
            + _render_note(
                manifest.get("guidance")
                or "Round 2F is a presentation-ready reproduction bundle. Full D2T2 recomputation and fresh solver dFBA remain guarded."
            ),
        ),
        (
            "Data Sources and Provenance",
            _render_json_summary(
                [
                    ("Supplement download status", supplement.get("status", "reused_or_available")),
                    ("Source note", supplement.get("source_note", "")),
                    ("Downloaded files", len(supplement.get("downloads", [])) if isinstance(supplement.get("downloads"), list) else 0),
                    ("Artifact count", len(artifacts)),
                ]
            )
            + _render_table(source_rows),
        ),
        (
            "Growth State Map",
            _render_json_summary(
                [
                    ("Status", growth_state.get("status", "not_available")),
                    ("Source", growth_state.get("source", "")),
                    ("Transition window", growth_state.get("transition_window", growth_state.get("transition_window_hours", ""))),
                    ("Series count", _count_series(growth_state)),
                    ("Heatmap rows", _count_matrix_rows(growth_state)),
                ]
            ),
        ),
        (
            "Trigger Timeline",
            _render_json_summary(
                [
                    ("Status", trigger_timeline.get("status", "not_available")),
                    ("Source", trigger_timeline.get("source", "")),
                    ("Series count", _count_series(trigger_timeline)),
                    ("Point count", _count_points(trigger_timeline)),
                    ("Boundary", "Supplement/GEO-derived timeline; no PDF digitization."),
                ]
            ),
        ),
        (
            "GDM-lite",
            _render_json_summary(
                [
                    ("Status", gdm_lite.get("status", "computed_lite")),
                    ("Gene mapping", gdm_lite.get("gene_mapping_status", "")),
                    ("Boundary", "Local lightweight calculation; not the original full GDM implementation."),
                ]
            )
            + _render_table(gdm_classes[:20]),
        ),
        (
            "D2T2 Reported Triggers",
            _render_json_summary(
                [
                    ("Status", algorithm_status.get("D2T2", "paper_reported_only")),
                    ("Rows", len(d2t2_rows)),
                    ("Boundary", "Paper-reported trigger table; static perturbation compendium is not attached."),
                ]
            )
            + _render_table(d2t2_rows[:80]),
        ),
        (
            "dFBA / Glycogen Scenario",
            _render_json_summary(
                [
                    ("Status", dfba.get("status", "paper_reported_model_prediction_available")),
                    ("Source", dfba.get("source", "")),
                    ("Series count", _count_series(dfba)),
                    ("Boundary", "Paper-reported model prediction curves; no fresh solver recomputation."),
                ]
            ),
        ),
        (
            "Model Compare Evidence Overlay",
            _render_json_summary(
                [
                    ("Status", mapping.get("status", "partial_mapping_ready")),
                    ("Mapped genes", mapping.get("mapped_gene_count", "")),
                    ("Unmapped genes", mapping.get("unmapped_gene_count", "")),
                    ("Mapped reactions", mapping.get("mapped_reaction_count", "")),
                    ("Boundary", "Only GPR-mapped paper evidence is highlighted; no pathway-name forced mapping."),
                ]
            )
            + _render_table(overlay_rows[:80]),
        ),
        ("Guarded Gaps and Caveats", _render_table(gap_rows)),
    ]


def _read_table(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return read_csv_records(path)


def _read_json_object(path: Path) -> dict[str, object]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _render_key_value_cards(rows: list[dict[str, object]]) -> str:
    if not rows:
        return '<p class="empty">No summary metrics are available.</p>'
    cards = "".join(
        f"<article><small>{_e(row.get('metric', ''))}</small><strong>{_e(row.get('value', ''))}</strong></article>"
        for row in rows
    )
    return f'<div class="metric-grid">{cards}</div>'


def _render_json_summary(rows: list[tuple[str, object]]) -> str:
    table_rows = [{"field": label, "value": value} for label, value in rows]
    return _render_table(table_rows)


def _render_note(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return f'<p class="note">{_e(text)}</p>'


def _count_series(payload: dict[str, object]) -> int:
    for key in ("series", "chart_series", "growth_series", "scenario_series", "timeline_series"):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            return len(value)
    return 0


def _count_points(payload: dict[str, object]) -> int:
    total = 0
    for key in ("series", "chart_series", "growth_series", "scenario_series", "timeline_series"):
        value = payload.get(key)
        if isinstance(value, list):
            for row in value:
                if isinstance(row, dict) and isinstance(row.get("points"), list):
                    total += len(row["points"])
        elif isinstance(value, dict):
            for row in value.values():
                if isinstance(row, list):
                    total += len(row)
                elif isinstance(row, dict) and isinstance(row.get("points"), list):
                    total += len(row["points"])
    return total


def _count_matrix_rows(payload: dict[str, object]) -> int:
    for key in ("heatmap", "heatmap_matrix", "correlation_heatmap", "sample_correlation_heatmap"):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, dict):
            matrix = value.get("matrix")
            if isinstance(matrix, list):
                return len(matrix)
    return 0


def _read_glob_tables(root: Path, pattern: str) -> list[dict[str, str]]:
    if not root.exists():
        return []
    rows: list[dict[str, str]] = []
    for path in sorted(root.glob(pattern)):
        for row in _read_table(path):
            merged = dict(row)
            merged.setdefault("source_file", str(path))
            rows.append(merged)
    return rows


def _ml_hybrid_profile_export_rows(package: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for profile in list_ml_hybrid_profiles(package):
        exports = list_ml_hybrid_profile_exports(package, str(profile.get("profile_id", "")))
        for row in exports.get("exports", []):
            rows.append({key: str(value) for key, value in row.items() if key != "files"})
    return rows


def _ml_hybrid_external_import_rows(package: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for profile in list_ml_hybrid_profiles(package):
        imports = list_ml_hybrid_external_results(package, str(profile.get("profile_id", "")))
        for row in imports.get("imports", []):
            rows.append({key: str(value) for key, value in row.items()})
    return rows


def _ml_hybrid_external_import_qa_rows(package: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in _ml_hybrid_external_import_rows(package):
        rows.append(
            {
                "profile_id": row.get("profile_id", ""),
                "import_id": row.get("import_id", ""),
                "qa_status": row.get("qa_status", ""),
                "status": row.get("status", ""),
                "mapped_features": row.get("gem_mapped_feature_count", ""),
                "unmapped_features": row.get("unmapped_feature_count", ""),
                "overlay_rows": row.get("overlay_row_count", ""),
                "validation_errors": row.get("validation_error_count", ""),
                "validation_warnings": row.get("validation_warning_count", ""),
                "manifest": row.get("manifest_path", ""),
                "guidance": "External feature importance is predictive marker evidence, not causal mechanism proof.",
            }
        )
    if not rows:
        rows.append(
            {
                "profile_id": "",
                "import_id": "",
                "qa_status": "empty_guidance",
                "status": "",
                "mapped_features": "0",
                "unmapped_features": "0",
                "overlay_rows": "0",
                "validation_errors": "0",
                "validation_warnings": "0",
                "manifest": "",
                "guidance": "No external ML imports were found. Import external results before building this section.",
            }
        )
    return rows


def _filter_variants(rows: list[dict[str, str]], selected: list[str], key: str) -> list[dict[str, str]]:
    if not selected:
        return rows
    selected_set = set(selected)
    return [row for row in rows if str(row.get(key, "")).strip() in selected_set]


def _render_preset_html(
    *,
    title: str,
    description: str,
    preset: str,
    selected_variants: list[str],
    sections: list[tuple[str, str]],
) -> str:
    section_html = "\n".join(
        f"<section><h2>{_e(section_title)}</h2>{section_body}</section>"
        for section_title, section_body in sections
    )
    selected_text = "; ".join(selected_variants) if selected_variants else "all available variants"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{_e(title)}</title>
  <style>
    :root {{ color-scheme: light; --ink: #18242b; --muted: #66747d; --line: #dce3e7; --panel: #f6f9fa; --accent: #116a6b; }}
    body {{ margin: 0; font-family: Arial, Helvetica, sans-serif; color: var(--ink); background: white; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 32px 24px 56px; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; }}
    h2 {{ margin-top: 30px; font-size: 21px; }}
    p {{ color: var(--muted); line-height: 1.5; }}
    .meta {{ background: var(--panel); border: 1px solid var(--line); border-radius: 8px; padding: 12px 14px; margin: 18px 0; }}
    table {{ border-collapse: collapse; width: 100%; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 8px 9px; text-align: left; vertical-align: top; }}
    th {{ background: #edf3f6; }}
    tr:last-child td {{ border-bottom: 0; }}
    .metric-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; margin: 18px 0; }}
    .metric-grid article {{ border: 1px solid var(--line); border-radius: 8px; background: var(--panel); padding: 12px; }}
    .metric-grid small {{ display: block; color: var(--muted); font-weight: 700; text-transform: uppercase; letter-spacing: .03em; }}
    .metric-grid strong {{ display: block; margin-top: 7px; font-size: 16px; overflow-wrap: anywhere; }}
    .note {{ border-left: 4px solid var(--accent); background: var(--panel); padding: 10px 12px; border-radius: 6px; }}
    .empty {{ color: var(--muted); background: var(--panel); border: 1px dashed var(--line); border-radius: 8px; padding: 10px 12px; }}
    @media (max-width: 720px) {{ main {{ padding: 20px 12px; }} table {{ font-size: 12px; }} }}
  </style>
</head>
<body>
  <main>
    <h1>{_e(title)}</h1>
    <p>{_e(description)}</p>
    <div class="meta"><strong>Preset:</strong> {_e(preset)}<br><strong>Selected variants:</strong> {_e(selected_text)}</div>
    {section_html}
  </main>
</body>
</html>
"""


def _render_table(rows: list[dict[str, str]]) -> str:
    if not rows:
        return '<p class="empty">No data available for this report section yet. Run the matching workflow stage or choose another preset.</p>'
    headers = list(rows[0].keys())
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in rows
    )
    return (
        "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _e(value: object) -> str:
    return html.escape(str(value))
