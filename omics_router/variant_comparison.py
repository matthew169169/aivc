"""Variant comparison summaries for staged Omics-GEM packages."""

from __future__ import annotations

from dataclasses import dataclass
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from .constraints import read_csv_records, write_csv, write_json


@dataclass(slots=True)
class VariantComparisonResult:
    """Result returned after writing variant comparison artifacts."""

    status: str
    message: str
    summary_path: str
    manifest_path: str


def run_variant_comparison(
    package_dir: str | Path,
    output_dir: str | Path | None = None,
) -> VariantComparisonResult:
    """Build model-variant comparison tables from existing package artifacts."""

    package = Path(package_dir)
    output = Path(output_dir) if output_dir else package / "variant_comparison"
    output.mkdir(parents=True, exist_ok=True)

    registry_rows = _read_rows(package / "workflow_results" / "model_variant_registry.csv")
    analysis_context_rows = _read_rows(package / "workflow_results" / "analysis_variant_context.csv")
    fba_rows = _read_rows(package / "variant_cobra_results" / "variant_fba_summary.csv")
    production_summary_rows = _read_rows(package / "production_results" / "production_analysis_summary.csv")
    readiness_summary_rows = _read_rows(package / "production_results" / "production_readiness_summary.csv")
    target_readiness_rows = _read_rows(package / "production_results" / "production_target_readiness.csv")
    evidence_mode_rows = _read_rows(package / "evidence_mode_results" / "evidence_mode_summary.csv")
    conflict_rows = _read_rows(package / "generated_constraints" / "multi_omics_conflict_summary.csv")
    delta_fba_summary_rows = _read_rows(package / "transcriptomics_flux_results" / "delta_fba_summary.csv")
    exchange_bound_rows = _read_exchange_bound_rows(package)
    nested_pfba_rows = _read_nested_csv_rows(package / "variant_cobra_results", "pfba_fluxes.csv")
    nested_fva_rows = _read_nested_csv_rows(package / "variant_cobra_results", "target_fva.csv")
    nested_fva_summary_rows = _read_nested_csv_rows(package / "variant_cobra_results", "target_fva_summary.csv")
    enzyme_qc_rows = _read_first_nonempty_rows(
        package / "enzyme_results" / "enzyme_qc_summary.csv",
        package / "gecko_package" / "enzyme_qc_summary.csv",
    )
    enzyme_capacity_rows = _read_first_nonempty_rows(
        package / "enzyme_results" / "reaction_enzyme_capacity.csv",
        package / "gecko_package" / "reaction_enzyme_capacity.csv",
    )
    enzyme_flux_capacity_rows = _read_rows(package / "enzyme_results" / "enzyme_flux_capacity_check.csv")

    feasibility_cache: dict[str, dict[str, str]] = {}
    readiness_counts = _readiness_label_counts(target_readiness_rows)
    production_target_count = _production_target_count(production_summary_rows, target_readiness_rows)
    conflict_fraction_by_condition = _index_by_condition(conflict_rows, "conflict_fraction")
    evidence_status_by_condition = _index_by_condition(evidence_mode_rows, "status")
    fba_by_variant = _group_rows(fba_rows, "variant_id")
    analysis_by_variant = _group_rows(analysis_context_rows, "active_variant_id")

    baseline_model_path = _baseline_model_path(package, registry_rows)
    structural_tables = _build_structural_diff_tables(package, registry_rows, baseline_model_path)

    summary_rows: list[dict[str, Any]] = []
    evidence_quality_rows: list[dict[str, Any]] = []
    for row in registry_rows:
        variant_id = str(row.get("variant_id", "")).strip()
        method = row.get("generation_method") or row.get("method", "")
        condition = row.get("condition", "")
        context_model_sbml = str(row.get("context_model_sbml", "")).strip()
        primary_model_path = str(row.get("primary_model_path", "")).strip()
        context_available = bool(context_model_sbml and Path(context_model_sbml).exists())
        active_model_path = context_model_sbml if context_available else primary_model_path
        feasibility = _context_feasibility(context_model_sbml, feasibility_cache)
        variant_fba_rows = fba_by_variant.get(variant_id, [])
        fba_summary = _summarize_variant_fba(variant_fba_rows)
        quality = _evidence_quality_label(
            confidence=row.get("confidence") or row.get("confidence_label", ""),
            context_available=context_available,
            feasibility_status=feasibility["context_model_feasibility_status"],
            fba_status=fba_summary["fba_status"],
        )
        guidance = _variant_guidance(
            method=method,
            context_available=context_available,
            feasibility_status=feasibility["context_model_feasibility_status"],
            fba_status=fba_summary["fba_status"],
            quality=quality,
        )
        summary_rows.append(
            {
                "variant_id": variant_id,
                "generation_method": method,
                "generation_method_label": row.get("generation_method_label", ""),
                "condition": condition,
                "evidence_mode": row.get("evidence_mode", ""),
                "generation_status": row.get("generation_status", ""),
                "active_model_path": active_model_path,
                "primary_model_path": primary_model_path,
                "context_model_sbml": context_model_sbml,
                "context_model_sbml_available": context_available,
                "context_model_feasibility_status": feasibility["context_model_feasibility_status"],
                "context_model_objective_value": feasibility["context_model_objective_value"],
                "context_model_feasibility_message": feasibility["context_model_feasibility_message"],
                "confidence": row.get("confidence") or row.get("confidence_label", ""),
                "compatible_analyses": row.get("compatible_analyses", ""),
                "selected_analysis_count": len(analysis_by_variant.get(variant_id, [])),
                "fba_status": fba_summary["fba_status"],
                "fba_objective_value": fba_summary["fba_objective_value"],
                "fba_condition_count": fba_summary["fba_condition_count"],
                "production_target_count": production_target_count,
                "readiness_stronger_evidence_count": readiness_counts["stronger_evidence"],
                "readiness_usable_with_caution_count": readiness_counts["usable_with_caution"],
                "readiness_guidance_only_count": readiness_counts["guidance_only"],
                "evidence_quality_label": quality,
                "comparison_status": "ready" if variant_id else "missing_variant_id",
                "guidance": guidance,
            }
        )
        evidence_quality_rows.append(
            {
                "variant_id": variant_id,
                "condition": condition,
                "evidence_mode": row.get("evidence_mode", ""),
                "confidence": row.get("confidence") or row.get("confidence_label", ""),
                "evidence_quality_label": quality,
                "condition_evidence_status": evidence_status_by_condition.get(condition, ""),
                "multi_omics_conflict_fraction": conflict_fraction_by_condition.get(condition, ""),
                "context_model_sbml_available": context_available,
                "context_model_feasibility_status": feasibility["context_model_feasibility_status"],
                "fba_status": fba_summary["fba_status"],
                "guidance": guidance,
            }
        )

    flux_rows = _flux_comparison_rows(fba_rows)
    summary_path = output / "variant_comparison_summary.csv"
    flux_path = output / "variant_flux_comparison.csv"
    evidence_path = output / "variant_evidence_quality.csv"
    structural_summary_path = output / "model_structural_diff_summary.csv"
    reaction_diff_path = output / "model_reaction_diff.csv"
    metabolite_diff_path = output / "model_metabolite_diff.csv"
    gene_gpr_diff_path = output / "model_gene_gpr_diff.csv"
    bound_objective_diff_path = output / "model_bound_objective_diff.csv"
    interpretation_tables = _build_comparison_interpretation_tables(
        structural_tables=structural_tables,
        summary_rows=summary_rows,
        evidence_quality_rows=evidence_quality_rows,
        flux_rows=flux_rows,
        target_readiness_rows=target_readiness_rows,
    )
    interpretation_path = output / "model_comparison_interpretation_summary.csv"
    layer_status_path = output / "model_comparison_layer_status.csv"
    reaction_drilldown_path = output / "model_reaction_drilldown.csv"
    axis_summary_path = output / "model_comparison_axis_summary.csv"
    condition_behavior_path = output / "condition_behavior_comparison.csv"
    gecko_condition_path = output / "gecko_condition_comparison.csv"
    story_cards_path = output / "model_comparison_story_cards.csv"
    qc_matrix_path = output / "model_comparison_qc_matrix.csv"
    phenotype_exchange_path = output / "condition_phenotype_exchange_comparison.csv"
    pathway_flux_path = output / "pathway_flux_comparison.csv"
    fva_flexibility_path = output / "fva_flexibility_comparison.csv"
    oxygen_sweep_path = output / "oxygen_sweep_comparison.csv"
    targeted_essentiality_path = output / "targeted_essentiality_comparison.csv"
    enzyme_allocation_path = output / "enzyme_allocation_comparison.csv"
    recommendation_cards_path = output / "model_comparison_recommendation_cards.csv"
    condition_exchange_chart_path = output / "condition_exchange_chart.csv"
    pathway_flux_delta_chart_path = output / "pathway_flux_delta_chart.csv"
    enzyme_pathway_allocation_chart_path = output / "enzyme_pathway_allocation_chart.csv"
    chart_manifest_path = output / "comparison_chart_manifest.csv"
    manifest_path = output / "variant_comparison_manifest.json"
    condition_behavior_rows = _condition_behavior_comparison_rows(
        flux_rows=flux_rows,
        target_readiness_rows=target_readiness_rows,
        delta_fba_summary_rows=delta_fba_summary_rows,
    )
    gecko_condition_rows = _gecko_condition_comparison_rows(package)
    axis_summary_rows = _model_comparison_axis_summary_rows(
        structural_tables=structural_tables,
        evidence_quality_rows=evidence_quality_rows,
        condition_behavior_rows=condition_behavior_rows,
        gecko_condition_rows=gecko_condition_rows,
        interpretation_rows=interpretation_tables["interpretation_summary"],
    )
    story_card_rows = _model_comparison_story_cards(
        structural_tables=structural_tables,
        condition_behavior_rows=condition_behavior_rows,
        gecko_condition_rows=gecko_condition_rows,
        interpretation_rows=interpretation_tables["interpretation_summary"],
        flux_rows=flux_rows,
        target_readiness_rows=target_readiness_rows,
    )
    qc_matrix_rows = _model_comparison_qc_matrix_rows(
        structural_tables=structural_tables,
        summary_rows=summary_rows,
        evidence_quality_rows=evidence_quality_rows,
        exchange_bound_rows=exchange_bound_rows,
        enzyme_qc_rows=enzyme_qc_rows,
    )
    phenotype_exchange_rows = _condition_phenotype_exchange_rows(
        flux_rows=flux_rows,
        pfba_rows=nested_pfba_rows,
        exchange_bound_rows=exchange_bound_rows,
        target_readiness_rows=target_readiness_rows,
    )
    pathway_flux_rows = _pathway_flux_comparison_rows(
        package=package,
        pfba_rows=nested_pfba_rows,
        delta_fba_summary_rows=delta_fba_summary_rows,
    )
    fva_flexibility_rows = _fva_flexibility_comparison_rows(
        fva_rows=nested_fva_rows,
        fva_summary_rows=nested_fva_summary_rows,
        target_readiness_rows=target_readiness_rows,
    )
    oxygen_sweep_rows = _oxygen_sweep_comparison_rows(
        exchange_bound_rows=exchange_bound_rows,
        flux_rows=flux_rows,
        pfba_rows=nested_pfba_rows,
    )
    targeted_essentiality_rows = _targeted_essentiality_comparison_rows(
        structural_tables=structural_tables,
        target_readiness_rows=target_readiness_rows,
        pathway_flux_rows=pathway_flux_rows,
    )
    enzyme_allocation_rows = _enzyme_allocation_comparison_rows(
        enzyme_qc_rows=enzyme_qc_rows,
        enzyme_capacity_rows=enzyme_capacity_rows,
        enzyme_flux_capacity_rows=enzyme_flux_capacity_rows,
        gecko_condition_rows=gecko_condition_rows,
    )
    recommendation_card_rows = _model_comparison_recommendation_cards(
        qc_matrix_rows=qc_matrix_rows,
        phenotype_exchange_rows=phenotype_exchange_rows,
        pathway_flux_rows=pathway_flux_rows,
        fva_flexibility_rows=fva_flexibility_rows,
        oxygen_sweep_rows=oxygen_sweep_rows,
        targeted_essentiality_rows=targeted_essentiality_rows,
        enzyme_allocation_rows=enzyme_allocation_rows,
        story_card_rows=story_card_rows,
    )
    condition_exchange_chart_rows = _condition_exchange_chart_rows(phenotype_exchange_rows)
    pathway_flux_delta_chart_rows = _pathway_flux_delta_chart_rows(pathway_flux_rows)
    enzyme_pathway_allocation_chart_rows = _enzyme_pathway_allocation_chart_rows(
        package=package,
        enzyme_capacity_rows=enzyme_capacity_rows,
        enzyme_flux_capacity_rows=enzyme_flux_capacity_rows,
    )
    chart_manifest_rows = _comparison_chart_manifest_rows(
        condition_exchange_chart_rows=condition_exchange_chart_rows,
        pathway_flux_delta_chart_rows=pathway_flux_delta_chart_rows,
        qc_matrix_rows=qc_matrix_rows,
        enzyme_allocation_rows=enzyme_allocation_rows,
        enzyme_pathway_allocation_chart_rows=enzyme_pathway_allocation_chart_rows,
        fva_flexibility_rows=fva_flexibility_rows,
        oxygen_sweep_rows=oxygen_sweep_rows,
        targeted_essentiality_rows=targeted_essentiality_rows,
    )
    write_csv(summary_path, summary_rows)
    write_csv(flux_path, flux_rows)
    write_csv(evidence_path, evidence_quality_rows)
    write_csv(structural_summary_path, structural_tables["summary"])
    write_csv(reaction_diff_path, structural_tables["reaction_diff"])
    write_csv(metabolite_diff_path, structural_tables["metabolite_diff"])
    write_csv(gene_gpr_diff_path, structural_tables["gene_gpr_diff"])
    write_csv(bound_objective_diff_path, structural_tables["bound_objective_diff"])
    write_csv(interpretation_path, interpretation_tables["interpretation_summary"])
    write_csv(layer_status_path, interpretation_tables["layer_status"])
    write_csv(reaction_drilldown_path, interpretation_tables["reaction_drilldown"])
    write_csv(axis_summary_path, axis_summary_rows)
    write_csv(condition_behavior_path, condition_behavior_rows)
    write_csv(gecko_condition_path, gecko_condition_rows)
    write_csv(story_cards_path, story_card_rows)
    write_csv(qc_matrix_path, qc_matrix_rows)
    write_csv(phenotype_exchange_path, phenotype_exchange_rows)
    write_csv(pathway_flux_path, pathway_flux_rows)
    write_csv(fva_flexibility_path, fva_flexibility_rows)
    write_csv(oxygen_sweep_path, oxygen_sweep_rows)
    write_csv(targeted_essentiality_path, targeted_essentiality_rows)
    write_csv(enzyme_allocation_path, enzyme_allocation_rows)
    write_csv(recommendation_cards_path, recommendation_card_rows)
    write_csv(condition_exchange_chart_path, condition_exchange_chart_rows)
    write_csv(pathway_flux_delta_chart_path, pathway_flux_delta_chart_rows)
    write_csv(enzyme_pathway_allocation_chart_path, enzyme_pathway_allocation_chart_rows)
    write_csv(chart_manifest_path, chart_manifest_rows)
    status = "completed" if registry_rows else "skipped"
    message = (
        f"Compared {len(summary_rows)} model variant(s)."
        if registry_rows
        else "No model_variant_registry.csv rows were available for comparison."
    )
    write_json(
        manifest_path,
        {
            "schema_version": "0.1.0",
            "status": status,
            "message": message,
            "package_dir": str(package),
            "output_dir": str(output),
            "variant_count": len(summary_rows),
            "flux_row_count": len(flux_rows),
            "structural_diff_row_count": len(structural_tables["summary"]),
            "interpretation_row_count": len(interpretation_tables["interpretation_summary"]),
            "reaction_drilldown_row_count": len(interpretation_tables["reaction_drilldown"]),
            "axis_summary_row_count": len(axis_summary_rows),
            "condition_behavior_row_count": len(condition_behavior_rows),
            "gecko_condition_row_count": len(gecko_condition_rows),
            "story_card_row_count": len(story_card_rows),
            "qc_matrix_row_count": len(qc_matrix_rows),
            "phenotype_exchange_row_count": len(phenotype_exchange_rows),
            "pathway_flux_row_count": len(pathway_flux_rows),
            "fva_flexibility_row_count": len(fva_flexibility_rows),
            "oxygen_sweep_row_count": len(oxygen_sweep_rows),
            "targeted_essentiality_row_count": len(targeted_essentiality_rows),
            "enzyme_allocation_row_count": len(enzyme_allocation_rows),
            "recommendation_card_row_count": len(recommendation_card_rows),
            "condition_exchange_chart_row_count": len(condition_exchange_chart_rows),
            "pathway_flux_delta_chart_row_count": len(pathway_flux_delta_chart_rows),
            "enzyme_pathway_allocation_chart_row_count": len(enzyme_pathway_allocation_chart_rows),
            "files": {
                "variant_comparison_summary": str(summary_path),
                "variant_flux_comparison": str(flux_path),
                "variant_evidence_quality": str(evidence_path),
                "model_structural_diff_summary": str(structural_summary_path),
                "model_reaction_diff": str(reaction_diff_path),
                "model_metabolite_diff": str(metabolite_diff_path),
                "model_gene_gpr_diff": str(gene_gpr_diff_path),
                "model_bound_objective_diff": str(bound_objective_diff_path),
                "model_comparison_interpretation_summary": str(interpretation_path),
                "model_comparison_layer_status": str(layer_status_path),
                "model_reaction_drilldown": str(reaction_drilldown_path),
                "model_comparison_axis_summary": str(axis_summary_path),
                "condition_behavior_comparison": str(condition_behavior_path),
                "gecko_condition_comparison": str(gecko_condition_path),
                "model_comparison_story_cards": str(story_cards_path),
                "model_comparison_qc_matrix": str(qc_matrix_path),
                "condition_phenotype_exchange_comparison": str(phenotype_exchange_path),
                "pathway_flux_comparison": str(pathway_flux_path),
                "fva_flexibility_comparison": str(fva_flexibility_path),
                "oxygen_sweep_comparison": str(oxygen_sweep_path),
                "targeted_essentiality_comparison": str(targeted_essentiality_path),
                "enzyme_allocation_comparison": str(enzyme_allocation_path),
                "model_comparison_recommendation_cards": str(recommendation_cards_path),
                "condition_exchange_chart": str(condition_exchange_chart_path),
                "pathway_flux_delta_chart": str(pathway_flux_delta_chart_path),
                "enzyme_pathway_allocation_chart": str(enzyme_pathway_allocation_chart_path),
                "comparison_chart_manifest": str(chart_manifest_path),
            },
        },
    )
    return VariantComparisonResult(
        status=status,
        message=message,
        summary_path=str(summary_path),
        manifest_path=str(manifest_path),
    )


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return read_csv_records(path)


def _read_first_nonempty_rows(*paths: Path) -> list[dict[str, str]]:
    for path in paths:
        rows = _read_rows(path)
        if rows:
            return rows
    return []


def _read_nested_csv_rows(root: Path, filename: str) -> list[dict[str, str]]:
    if not root.exists():
        return []
    rows: list[dict[str, str]] = []
    for path in sorted(root.glob(f"*/{filename}")):
        for row in _read_rows(path):
            enriched = dict(row)
            enriched.setdefault("source_dir", path.parent.name)
            enriched.setdefault("source_file", str(path))
            rows.append(enriched)
    return rows


def _read_exchange_bound_rows(package: Path) -> list[dict[str, str]]:
    rows = _read_rows(package / "generated_constraints" / "exchange_bounds.csv")
    if rows:
        return rows
    condition_dir = package / "inputs" / "condition"
    if condition_dir.exists():
        for path in sorted(condition_dir.glob("*condition_exchange_bounds*.csv")):
            rows = _read_rows(path)
            if rows:
                return rows
    return []


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _group_rows(rows: list[dict[str, str]], key: str) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        value = str(row.get(key, "")).strip()
        grouped.setdefault(value, []).append(row)
    return grouped


def _index_by_condition(rows: list[dict[str, str]], value_key: str) -> dict[str, str]:
    indexed: dict[str, str] = {}
    for row in rows:
        condition = str(row.get("condition", "")).strip()
        if condition and condition not in indexed:
            indexed[condition] = str(row.get(value_key, ""))
    return indexed


def _safe_float(value: Any) -> float | None:
    try:
        text = str(value).strip()
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def _format_float(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value:.6g}"


def _condition_group(condition: str) -> str:
    text = str(condition).lower()
    if "higho2" in text or "20pcto2" in text or "20pct" in text:
        return "highO2"
    if "lowo2" in text or "8p5" in text or "8.5" in text or "pinchuk" in text:
        return "lowO2"
    return str(condition or "unknown")


def _condition_sort_key(condition: str) -> int:
    group = _condition_group(condition)
    if group == "highO2":
        return 0
    if group == "lowO2":
        return 1
    return 2


def _product_flux(row: dict[str, str] | None) -> float | None:
    if not row:
        return None
    for key in (
        "max_product_flux_at_zero_growth",
        "max_product_flux_at_half_growth",
        "max_product_flux_at_high_growth",
        "max_product_flux",
    ):
        value = _safe_float(row.get(key, ""))
        if value is not None:
            return value
    return None


def _max_product_flux_row(rows: list[dict[str, str]]) -> dict[str, str] | None:
    best_row: dict[str, str] | None = None
    best_value: float | None = None
    for row in rows:
        value = _product_flux(row)
        if value is None:
            continue
        if best_value is None or value > best_value:
            best_value = value
            best_row = row
    return best_row


def _condition_behavior_guidance(
    condition: str,
    fba_status: str,
    production_count: int,
    delta_statuses: list[str],
) -> str:
    group = _condition_group(condition)
    if fba_status != "optimal":
        return f"{condition} is not optimal in FBA ({fba_status}); interpret downstream behavior with caution."
    if group in {"highO2", "lowO2"} and production_count:
        return f"{condition} contributes to the highO2/lowO2 condition-behavior comparison."
    if delta_statuses:
        return f"{condition} has delta-FBA context: {';'.join(delta_statuses)}."
    return f"{condition} has FBA behavior output; compare with matching condition rows before drawing conclusions."


def _gecko_condition_guidance(readiness: str, adapter_missing_count: int, external_status: str) -> str:
    if adapter_missing_count:
        return "GECKO adapter readiness is partial; missing adapter fields should be resolved before external MATLAB/GECKO runs."
    if str(readiness).lower() in {"insufficient", "missing"}:
        return "Proteomics/kcat mapping is insufficient; treat GECKO-ready output as package/readiness evidence rather than completed ecModel behavior."
    if external_status in {"completed", "ready"}:
        return "External GECKO output is available for enzyme-constrained behavior interpretation."
    return "GECKO package/readiness data are available; external ecModel reconstruction remains optional."


def _readiness_label_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts = {"stronger_evidence": 0, "usable_with_caution": 0, "guidance_only": 0}
    for row in rows:
        label = str(row.get("readiness_label") or row.get("guidance_label") or row.get("label") or "").lower()
        if "strong" in label or "stronger" in label:
            counts["stronger_evidence"] += 1
        elif "caution" in label or "usable" in label:
            counts["usable_with_caution"] += 1
        elif "guidance" in label or "only" in label:
            counts["guidance_only"] += 1
    return counts


def _production_target_count(
    production_summary_rows: list[dict[str, str]],
    target_readiness_rows: list[dict[str, str]],
) -> int:
    if target_readiness_rows:
        return len(target_readiness_rows)
    for row in production_summary_rows:
        for key in ("target_count", "production_target_count", "targets"):
            value = str(row.get(key, "")).strip()
            if value.isdigit():
                return int(value)
    return 0


def _summarize_variant_fba(rows: list[dict[str, str]]) -> dict[str, str]:
    if not rows:
        return {"fba_status": "missing", "fba_objective_value": "", "fba_condition_count": "0"}
    statuses = [str(row.get("status") or row.get("run_status") or "").strip() for row in rows]
    objective_values = [str(row.get("objective_value", "")).strip() for row in rows if str(row.get("objective_value", "")).strip()]
    if any(status == "optimal" for status in statuses):
        status = "optimal"
    elif any(status for status in statuses):
        status = next(status for status in statuses if status)
    else:
        status = "completed"
    return {
        "fba_status": status,
        "fba_objective_value": objective_values[0] if objective_values else "",
        "fba_condition_count": str(len(rows)),
    }


def _flux_comparison_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    for row in rows:
        output.append(
            {
                "variant_id": row.get("variant_id", ""),
                "condition": row.get("condition", ""),
                "status": row.get("status") or row.get("run_status", ""),
                "objective_value": row.get("objective_value", ""),
                "active_generation_method_label": row.get("active_generation_method_label", ""),
                "active_model_path": row.get("active_model_path", ""),
                "output_dir": row.get("output_dir", ""),
                "run_message": row.get("run_message", ""),
            }
        )
    return output


def _baseline_model_path(package: Path, registry_rows: list[dict[str, str]]) -> Path | None:
    for row in registry_rows:
        method = str(row.get("generation_method") or row.get("method") or "").lower()
        variant_id = str(row.get("variant_id", "")).lower()
        if method == "baseline_gem" or "baseline" in variant_id:
            return _resolve_model_path(package, _active_model_path(row))
    if registry_rows:
        return _resolve_model_path(package, _active_model_path(registry_rows[0]))
    return None


def _active_model_path(row: dict[str, str]) -> str:
    return str(
        row.get("context_model_sbml")
        or row.get("primary_model_path")
        or row.get("primary_artifact")
        or row.get("source_model_path")
        or ""
    ).strip()


def _resolve_model_path(package: Path, text: str | Path | None) -> Path | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = package / path
    return path


def _build_structural_diff_tables(
    package: Path,
    registry_rows: list[dict[str, str]],
    baseline_path: Path | None,
) -> dict[str, list[dict[str, Any]]]:
    tables: dict[str, list[dict[str, Any]]] = {
        "summary": [],
        "reaction_diff": [],
        "metabolite_diff": [],
        "gene_gpr_diff": [],
        "bound_objective_diff": [],
    }
    baseline = _parse_model_structure(baseline_path)
    for row in registry_rows:
        variant_id = str(row.get("variant_id", "")).strip()
        model_path = _resolve_model_path(package, _active_model_path(row))
        model = _parse_model_structure(model_path)
        comparison = _compare_model_structures(variant_id, baseline, model)
        tables["summary"].append(
            {
                "variant_id": variant_id,
                "generation_method": row.get("generation_method") or row.get("method", ""),
                "condition": row.get("condition", ""),
                "reference_model_path": str(baseline.path or ""),
                "model_path": str(model.path or ""),
                "reference_parse_status": baseline.status,
                "model_parse_status": model.status,
                "comparison_label": comparison["label"],
                "reference_reaction_count": len(baseline.reactions),
                "reaction_count": len(model.reactions),
                "reaction_added_count": len(comparison["added_reactions"]),
                "reaction_removed_count": len(comparison["removed_reactions"]),
                "reaction_changed_bounds_count": len(comparison["changed_bounds"]),
                "exchange_added_count": sum(1 for rid in comparison["added_reactions"] if _is_exchange_id(rid)),
                "exchange_removed_count": sum(1 for rid in comparison["removed_reactions"] if _is_exchange_id(rid)),
                "reference_metabolite_count": len(baseline.metabolites),
                "metabolite_count": len(model.metabolites),
                "metabolite_added_count": len(comparison["added_metabolites"]),
                "metabolite_removed_count": len(comparison["removed_metabolites"]),
                "reference_gene_count": len(baseline.genes),
                "gene_count": len(model.genes),
                "gene_added_count": len(comparison["added_genes"]),
                "gene_removed_count": len(comparison["removed_genes"]),
                "gpr_changed_count": len(comparison["changed_gpr"]),
                "objective_changed": comparison["objective_changed"],
                "guidance": comparison["guidance"],
            }
        )
        tables["reaction_diff"].extend(_reaction_diff_rows(variant_id, baseline, model, comparison))
        tables["metabolite_diff"].extend(_entity_diff_rows(variant_id, "metabolite", comparison["added_metabolites"], comparison["removed_metabolites"], baseline.metabolites, model.metabolites))
        tables["gene_gpr_diff"].extend(_gene_gpr_diff_rows(variant_id, baseline, model, comparison))
        tables["bound_objective_diff"].extend(_bound_objective_diff_rows(variant_id, baseline, model, comparison))
    return tables


def _build_comparison_interpretation_tables(
    *,
    structural_tables: dict[str, list[dict[str, Any]]],
    summary_rows: list[dict[str, Any]],
    evidence_quality_rows: list[dict[str, Any]],
    flux_rows: list[dict[str, str]],
    target_readiness_rows: list[dict[str, str]],
) -> dict[str, list[dict[str, Any]]]:
    structural_rows = structural_tables.get("summary", [])
    reaction_diff_rows = structural_tables.get("reaction_diff", [])
    gene_gpr_rows = structural_tables.get("gene_gpr_diff", [])
    bound_objective_rows = structural_tables.get("bound_objective_diff", [])

    structural_change_count = _count_rows_with_value(structural_rows, "comparison_label", "structural_change_detected")
    same_source_count = _count_rows_with_value(structural_rows, "comparison_label", "same_source_model")
    skipped_count = sum(1 for row in structural_rows if str(row.get("comparison_label", "")).startswith("skipped"))
    changed_reaction_count = len(reaction_diff_rows) + len(bound_objective_rows) + sum(1 for row in gene_gpr_rows if row.get("reaction_id"))
    context_variant_count = sum(1 for row in summary_rows if str(row.get("context_model_sbml_available", "")).lower() == "true")
    context_method_count = sum(
        1
        for row in summary_rows
        if str(row.get("generation_method", "")).lower() in {"eflux", "fastcore", "consensus_evidence", "consensus_context"}
    )
    evidence_row_count = len(evidence_quality_rows)
    evidence_warning_count = sum(
        1
        for row in evidence_quality_rows
        if str(row.get("evidence_quality_label", "")).lower() in {"usable_with_caution", "guidance_only"}
    )
    flux_row_count = len(flux_rows)
    optimal_flux_count = sum(1 for row in flux_rows if str(row.get("status", "")).lower() == "optimal")
    production_row_count = len(target_readiness_rows)

    structural_status = (
        "changed"
        if structural_change_count
        else "same_source"
        if same_source_count and not changed_reaction_count
        else "partial"
        if skipped_count or not structural_rows
        else "unchanged"
    )
    constraint_status = "ready" if context_variant_count or context_method_count else "baseline_only"
    evidence_status = "ready" if evidence_row_count and evidence_warning_count < evidence_row_count else "partial" if evidence_row_count else "missing"
    behavior_status = "ready" if flux_row_count or production_row_count else "missing"

    interpretation_summary = [
        _interpretation_row(
            "structural_changes",
            structural_status,
            _structural_headline(structural_change_count, same_source_count, skipped_count),
            _structural_detail(structural_rows, changed_reaction_count),
            "Review reaction drilldown before using structurally changed variants; same-source variants should be interpreted through constraints, evidence, or behavior outputs.",
        ),
        _interpretation_row(
            "constraint_context",
            constraint_status,
            f"{context_variant_count} context model(s) and {context_method_count} context-oriented method row(s) detected.",
            "E-Flux, FASTcore, and consensus variants can change constraints or interpretation even when the conventional GEM file is unchanged.",
            "Check condition bounds and generation parameters when behavior differs without structural diff.",
        ),
        _interpretation_row(
            "evidence_context",
            evidence_status,
            f"{evidence_row_count} evidence quality row(s); {evidence_warning_count} caution/guidance row(s).",
            "Transcriptomics, proteomics, kcat, and conflict signals are evidence markers, not causal mechanisms.",
            "Resolve missing evidence only when it blocks the planned downstream analysis.",
        ),
        _interpretation_row(
            "behavior_outputs",
            behavior_status,
            f"{flux_row_count} flux row(s), {optimal_flux_count} optimal FBA row(s), {production_row_count} production readiness row(s).",
            "Behavior comparisons come from existing FBA, production, and downstream result tables.",
            "Run analysis modules if structural variants exist but behavior outputs are still missing.",
        ),
        _interpretation_row(
            "gecko_behavior",
            "optional",
            "GECKO ecModel outputs are interpreted separately from conventional GEM structural diff.",
            "Enzyme pseudo reactions in GECKO models are not mixed into the main structural diff table.",
            "Use GECKO flux and enzyme usage tables when proteomics/kcat-constrained behavior is central.",
        ),
    ]
    layer_status = [
        _layer_status_row("structural_changes", structural_status, changed_reaction_count, skipped_count, interpretation_summary[0]["headline"]),
        _layer_status_row("constraint_context", constraint_status, context_variant_count + context_method_count, 0, interpretation_summary[1]["headline"]),
        _layer_status_row("evidence_context", evidence_status, evidence_row_count, evidence_warning_count, interpretation_summary[2]["headline"]),
        _layer_status_row("behavior_outputs", behavior_status, flux_row_count + production_row_count, 0, interpretation_summary[3]["headline"]),
        _layer_status_row("gecko_behavior", "optional", 0, 0, interpretation_summary[4]["headline"]),
    ]
    return {
        "interpretation_summary": interpretation_summary,
        "layer_status": layer_status,
        "reaction_drilldown": _reaction_drilldown_rows(reaction_diff_rows, gene_gpr_rows, bound_objective_rows),
    }


def _condition_behavior_comparison_rows(
    *,
    flux_rows: list[dict[str, str]],
    target_readiness_rows: list[dict[str, str]],
    delta_fba_summary_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    production_by_condition = _group_rows(target_readiness_rows, "condition")
    delta_by_condition: dict[str, list[dict[str, str]]] = {}
    for row in delta_fba_summary_rows:
        for key in ("reference_condition", "target_condition"):
            condition = str(row.get(key, "")).strip()
            if condition:
                delta_by_condition.setdefault(condition, []).append(row)

    conditions = sorted(
        {
            str(row.get("condition", "")).strip()
            for row in [*flux_rows, *target_readiness_rows]
            if str(row.get("condition", "")).strip()
        },
        key=lambda item: (_condition_sort_key(item), item),
    )
    output: list[dict[str, Any]] = []
    for condition in conditions:
        flux_for_condition = [row for row in flux_rows if str(row.get("condition", "")).strip() == condition]
        production_for_condition = production_by_condition.get(condition, [])
        delta_rows = delta_by_condition.get(condition, [])
        fba_statuses = [str(row.get("status", "")).strip() for row in flux_for_condition if str(row.get("status", "")).strip()]
        objective_values = [_safe_float(row.get("objective_value", "")) for row in flux_for_condition]
        objective_values = [value for value in objective_values if value is not None]
        max_product_row = _max_product_flux_row(production_for_condition)
        review_count = sum(
            1
            for row in production_for_condition
            if "review" in str(row.get("production_readiness_label") or row.get("semantic_label") or "").lower()
        )
        growth_coupled_count = sum(
            1
            for row in production_for_condition
            if "growth_coupled" in str(row.get("growth_coupling_label", "")).lower()
        )
        delta_statuses = sorted({str(row.get("status", "")).strip() for row in delta_rows if str(row.get("status", "")).strip()})
        group = _condition_group(condition)
        fba_status = "optimal" if "optimal" in fba_statuses else (fba_statuses[0] if fba_statuses else "missing")
        behavior_status = (
            "ready"
            if fba_status == "optimal" and production_for_condition
            else "partial"
            if flux_for_condition or production_for_condition or delta_rows
            else "missing"
        )
        output.append(
            {
                "condition": condition,
                "condition_group": group,
                "comparison_axis": "highO2_lowO2" if group in {"highO2", "lowO2"} else "condition",
                "fba_status": fba_status,
                "objective_value": _format_float(objective_values[0] if objective_values else None),
                "fba_row_count": len(flux_for_condition),
                "production_target_count": len(production_for_condition),
                "growth_coupled_possible_count": growth_coupled_count,
                "production_review_required_count": review_count,
                "top_product_name": max_product_row.get("product_name", "") if max_product_row else "",
                "top_product_flux": _format_float(_product_flux(max_product_row) if max_product_row else None),
                "delta_fba_status": ";".join(delta_statuses),
                "behavior_status": behavior_status,
                "guidance": _condition_behavior_guidance(condition, fba_status, len(production_for_condition), delta_statuses),
            }
        )
    return output


def _gecko_condition_comparison_rows(package: Path) -> list[dict[str, Any]]:
    adapter_rows = _read_rows(package / "gecko_package" / "gecko_adapter_readiness.csv")
    enzyme_qc_rows = _read_rows(package / "gecko_package" / "enzyme_qc_summary.csv")
    kcat_prior_rows = _read_rows(package / "generated_constraints" / "kcat_priors.csv")
    gecko_dir = package / "gecko_run_results"
    gecko_manifest = _read_json_object(gecko_dir / "gecko_external_run_manifest.json")
    flux_delta_rows = _read_rows(gecko_dir / "gecko_flux_delta_high_vs_low.csv")
    enzyme_usage_high = _read_rows(gecko_dir / "gecko_enzyme_usage_highO2.csv")
    enzyme_usage_low = _read_rows(gecko_dir / "gecko_enzyme_usage_lowO2.csv")
    adapter_missing = sum(1 for row in adapter_rows if str(row.get("status", "")).lower() in {"missing", "failed", "blocked"})
    external_status = str(gecko_manifest.get("status") or gecko_manifest.get("run_status") or "").strip() or (
        "not_run" if not gecko_manifest else "unknown"
    )
    if not enzyme_qc_rows:
        if adapter_rows or kcat_prior_rows:
            readiness = "kcat_ready_missing_absolute_proteomics" if kcat_prior_rows else "adapter_ready_missing_kcat"
            return [
                {
                    "condition": "all",
                    "condition_group": "combined",
                    "ecmodel_status": "adapter_ready",
                    "external_run_status": external_status,
                    "adapter_missing_count": adapter_missing,
                    "protein_count": "",
                    "mapped_protein_fraction": "",
                    "kcat_prior_count": len(kcat_prior_rows),
                    "mapped_kcat_prior_fraction": "1.0" if kcat_prior_rows else "",
                    "ready_capacity_fraction": "",
                    "enzyme_readiness": readiness,
                    "flux_delta_row_count": len(flux_delta_rows),
                    "enzyme_usage_row_count": len(enzyme_usage_high) + len(enzyme_usage_low),
                    "guidance": "GECKO adapter and kcat priors are staged, but absolute proteomics/protein pool evidence is missing; treat this as guarded ecModel-ready input, not enzyme-capacity output.",
                }
            ]
        return [
            {
                "condition": "highO2/lowO2",
                "condition_group": "combined",
                "ecmodel_status": "optional_missing",
                "external_run_status": external_status,
                "adapter_missing_count": adapter_missing,
                "protein_count": "",
                "mapped_protein_fraction": "",
                "kcat_prior_count": "",
                "mapped_kcat_prior_fraction": "",
                "ready_capacity_fraction": "",
                "enzyme_readiness": "missing",
                "flux_delta_row_count": len(flux_delta_rows),
                "enzyme_usage_row_count": len(enzyme_usage_high) + len(enzyme_usage_low),
                "guidance": "GECKO condition outputs are optional; run adapter probe/external GECKO only when enzyme-constrained behavior is required.",
            }
        ]
    output: list[dict[str, Any]] = []
    for row in enzyme_qc_rows:
        condition = str(row.get("condition", "")).strip()
        group = _condition_group(condition)
        usage_count = len(enzyme_usage_high) if group == "highO2" else len(enzyme_usage_low) if group == "lowO2" else 0
        readiness = str(row.get("enzyme_readiness") or "").strip() or "partial"
        output.append(
            {
                "condition": condition,
                "condition_group": group,
                "ecmodel_status": "external_completed" if external_status in {"completed", "ready"} else "gecko_package_ready",
                "external_run_status": external_status,
                "adapter_missing_count": adapter_missing,
                "protein_count": row.get("protein_count", ""),
                "mapped_protein_fraction": row.get("mapped_protein_fraction", ""),
                "kcat_prior_count": row.get("kcat_prior_count", ""),
                "mapped_kcat_prior_fraction": row.get("mapped_kcat_prior_fraction", ""),
                "ready_capacity_fraction": row.get("ready_capacity_fraction", ""),
                "enzyme_readiness": readiness,
                "flux_delta_row_count": len(flux_delta_rows),
                "enzyme_usage_row_count": usage_count,
                "guidance": _gecko_condition_guidance(readiness, adapter_missing, external_status),
            }
        )
    return output


def _model_comparison_axis_summary_rows(
    *,
    structural_tables: dict[str, list[dict[str, Any]]],
    evidence_quality_rows: list[dict[str, Any]],
    condition_behavior_rows: list[dict[str, Any]],
    gecko_condition_rows: list[dict[str, Any]],
    interpretation_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    interpretation_by_layer = {str(row.get("layer", "")): row for row in interpretation_rows}
    structural_rows = structural_tables.get("summary", [])
    changed_structural_count = sum(1 for row in structural_rows if str(row.get("comparison_label", "")) == "structural_change_detected")
    condition_ready_count = sum(1 for row in condition_behavior_rows if str(row.get("behavior_status", "")) == "ready")
    gecko_ready_count = sum(
        1
        for row in gecko_condition_rows
        if str(row.get("ecmodel_status", "")).lower() in {"external_completed", "gecko_package_ready", "adapter_ready"}
    )
    gecko_warning_count = sum(1 for row in gecko_condition_rows if str(row.get("enzyme_readiness", "")).lower() in {"insufficient", "missing"})
    return [
        _axis_row(
            "model_structure",
            "changed" if changed_structural_count else "same_source",
            len(structural_rows),
            0,
            interpretation_by_layer.get("structural_changes", {}).get("headline")
            or "Conventional GEM structural comparison is available.",
            "Structural diff is limited to conventional GEM fields; GECKO enzyme pseudo reactions are excluded.",
        ),
        _axis_row(
            "constraint_evidence",
            "ready" if evidence_quality_rows else "partial",
            len(evidence_quality_rows),
            sum(1 for row in evidence_quality_rows if "guidance" in str(row.get("evidence_quality_label", "")).lower()),
            interpretation_by_layer.get("evidence_context", {}).get("headline")
            or "Evidence and constraint context are summarized from existing workflow outputs.",
            "Use evidence rows to explain why behavior may differ without structural changes.",
        ),
        _axis_row(
            "condition_behavior",
            "ready" if condition_ready_count else "partial" if condition_behavior_rows else "missing",
            len(condition_behavior_rows),
            sum(1 for row in condition_behavior_rows if str(row.get("fba_status", "")).lower() != "optimal"),
            f"{len(condition_behavior_rows)} condition behavior row(s), including highO2/lowO2 when available.",
            "Compare highO2/lowO2 as oxygen-condition behavior, not voltage conditions.",
        ),
        _axis_row(
            "gecko_ecmodel",
            "ready" if gecko_ready_count else "optional_missing",
            len(gecko_condition_rows),
            gecko_warning_count,
            f"{len(gecko_condition_rows)} GECKO condition row(s) summarizing adapter/enzyme readiness.",
            "GECKO ecModel behavior is interpreted separately from conventional GEM structural diff.",
        ),
    ]


def _model_comparison_story_cards(
    *,
    structural_tables: dict[str, list[dict[str, Any]]],
    condition_behavior_rows: list[dict[str, Any]],
    gecko_condition_rows: list[dict[str, Any]],
    interpretation_rows: list[dict[str, Any]],
    flux_rows: list[dict[str, str]],
    target_readiness_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    structural_rows = structural_tables.get("summary", [])
    changed_structural_count = sum(1 for row in structural_rows if str(row.get("comparison_label", "")) == "structural_change_detected")
    same_source_count = sum(1 for row in structural_rows if str(row.get("comparison_label", "")) in {"same_source_model", "reference_model"})
    optimal_conditions = sum(1 for row in condition_behavior_rows if str(row.get("fba_status", "")) == "optimal")
    high_low_rows = [row for row in condition_behavior_rows if row.get("condition_group") in {"highO2", "lowO2"}]
    gecko_rows_with_qc = [row for row in gecko_condition_rows if row.get("protein_count") or row.get("kcat_prior_count")]
    story: list[dict[str, Any]] = []
    story.append(
        _story_card(
            1,
            "model_structure",
            "changed" if changed_structural_count else "same_source",
            "Conventional GEM structure changed." if changed_structural_count else "Conventional GEM structure is unchanged or same-source.",
            (
                f"{changed_structural_count} structural-change variant row(s) were detected."
                if changed_structural_count
                else f"{same_source_count or len(structural_rows)} same-source/reference row(s); compare constraints and behavior instead."
            ),
            "Use reaction drilldown when structural-change rows exist; otherwise focus on condition and evidence layers.",
        )
    )
    story.append(
        _story_card(
            2,
            "condition_behavior",
            "ready" if high_low_rows else "partial",
            "highO2/lowO2 behavior is available." if high_low_rows else "Condition behavior is partial.",
            f"{len(condition_behavior_rows)} condition row(s), {optimal_conditions} optimal FBA row(s), {len(flux_rows)} flux comparison row(s).",
            "Use condition behavior rows to explain oxygen-condition differences.",
        )
    )
    story.append(
        _story_card(
            3,
            "production_readiness",
            "ready" if target_readiness_rows else "missing",
            "Production target readiness is available." if target_readiness_rows else "Production readiness is missing.",
            f"{len(target_readiness_rows)} target-condition readiness row(s) are available.",
            "Review readiness warnings before treating production targets as actionable.",
        )
    )
    story.append(
        _story_card(
            4,
            "gecko_ecmodel",
            "ready" if gecko_rows_with_qc else "optional_missing",
            "GECKO enzyme constraint evidence is summarized." if gecko_rows_with_qc else "GECKO remains optional or missing.",
            f"{len(gecko_condition_rows)} GECKO condition row(s); {len(gecko_rows_with_qc)} include enzyme QC values.",
            "Do not mix GECKO enzyme pseudo reactions into conventional GEM structural diff.",
        )
    )
    for row in interpretation_rows[:2]:
        story.append(
            _story_card(
                len(story) + 1,
                str(row.get("layer", "interpretation")),
                str(row.get("status", "partial")),
                str(row.get("headline", "")),
                str(row.get("detail", "")),
                str(row.get("recommended_next_step", "")),
            )
        )
    return story[:6]


def _model_comparison_qc_matrix_rows(
    *,
    structural_tables: dict[str, list[dict[str, Any]]],
    summary_rows: list[dict[str, Any]],
    evidence_quality_rows: list[dict[str, Any]],
    exchange_bound_rows: list[dict[str, str]],
    enzyme_qc_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    structural_rows = structural_tables.get("summary", [])
    reaction_diff_count = len(structural_tables.get("reaction_diff", []))
    bound_diff_count = len(structural_tables.get("bound_objective_diff", []))
    same_source_count = sum(1 for row in structural_rows if str(row.get("comparison_label", "")) in {"same_source_model", "reference_model"})
    objective_changed_count = sum(1 for row in structural_rows if str(row.get("objective_changed", "")).lower() in {"true", "1"})
    exchange_count = sum(1 for row in exchange_bound_rows if _is_exchange_id(str(row.get("reaction_id") or row.get("model_reaction_id") or "")))
    oxygen_bound_count = sum(1 for row in exchange_bound_rows if _reaction_role(row) == "oxygen")
    caution_evidence_count = sum(
        1 for row in evidence_quality_rows if str(row.get("evidence_quality_label", "")).lower() in {"usable_with_caution", "guidance_only"}
    )
    protein_count = max((_safe_float(row.get("protein_count", "")) or 0 for row in enzyme_qc_rows), default=0)
    kcat_count = max((_safe_float(row.get("kcat_prior_count", "")) or 0 for row in enzyme_qc_rows), default=0)
    mapped_protein_fraction = max((_safe_float(row.get("mapped_protein_fraction", "")) or 0 for row in enzyme_qc_rows), default=0)
    return [
        {
            "qc_layer": "model_structure",
            "status": "same_source" if same_source_count and not reaction_diff_count else "changed" if reaction_diff_count else "partial",
            "signal_count": len(structural_rows),
            "warning_count": reaction_diff_count + bound_diff_count,
            "primary_metric": f"{same_source_count}/{len(structural_rows) or 1} same-source/reference",
            "guidance": "Same-source variants should be compared through constraints, evidence, and behavior rather than structural reaction diff.",
        },
        {
            "qc_layer": "biomass_objective",
            "status": "changed" if objective_changed_count else "ready",
            "signal_count": len(summary_rows),
            "warning_count": objective_changed_count,
            "primary_metric": f"{objective_changed_count} objective change(s)",
            "guidance": "Objective changes affect behavior interpretation; no objective changes were detected when this count is zero.",
        },
        {
            "qc_layer": "exchange_bounds",
            "status": "ready" if exchange_count else "missing",
            "signal_count": exchange_count,
            "warning_count": 0 if oxygen_bound_count else 1,
            "primary_metric": f"{exchange_count} exchange row(s); {oxygen_bound_count} oxygen row(s)",
            "guidance": "Exchange bounds are the main fairness layer for highO2/lowO2 condition comparison.",
        },
        {
            "qc_layer": "evidence_coverage",
            "status": "ready" if evidence_quality_rows and caution_evidence_count < len(evidence_quality_rows) else "partial" if evidence_quality_rows else "missing",
            "signal_count": len(evidence_quality_rows),
            "warning_count": caution_evidence_count,
            "primary_metric": f"{len(evidence_quality_rows)} evidence row(s)",
            "guidance": "Evidence rows summarize transcriptomics/proteomics/kcat support and should not be interpreted as causal proof.",
        },
        {
            "qc_layer": "enzyme_proteome_coverage",
            "status": "ready" if enzyme_qc_rows and mapped_protein_fraction > 0 else "optional_missing" if not enzyme_qc_rows else "partial",
            "signal_count": len(enzyme_qc_rows),
            "warning_count": sum(1 for row in enzyme_qc_rows if str(row.get("enzyme_readiness", "")).lower() in {"missing", "insufficient"}),
            "primary_metric": f"{_format_float(protein_count)} proteins; {_format_float(kcat_count)} kcat priors",
            "guidance": "GECKO/proteome QC is an enzyme-constrained behavior layer, not conventional GEM structural diff.",
        },
    ]


def _condition_phenotype_exchange_rows(
    *,
    flux_rows: list[dict[str, str]],
    pfba_rows: list[dict[str, str]],
    exchange_bound_rows: list[dict[str, str]],
    target_readiness_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    conditions = sorted(
        {
            str(row.get("condition", "")).strip()
            for row in [*flux_rows, *pfba_rows, *exchange_bound_rows, *target_readiness_rows]
            if str(row.get("condition", "")).strip()
        },
        key=lambda item: (_condition_sort_key(item), item),
    )
    if not conditions:
        return [
            {
                "condition": "highO2/lowO2",
                "condition_group": "combined",
                "status": "not_available",
                "guidance": "No condition rows were available for phenotype/exchange comparison.",
            }
        ]
    output: list[dict[str, Any]] = []
    for condition in conditions:
        condition_flux_rows = [row for row in flux_rows if str(row.get("condition", "")).strip() == condition]
        condition_pfba_rows = [row for row in pfba_rows if str(row.get("condition", "")).strip() == condition]
        condition_bounds = [row for row in exchange_bound_rows if str(row.get("condition", "")).strip() == condition]
        production_rows = [row for row in target_readiness_rows if str(row.get("condition", "")).strip() == condition]
        objective = next((str(row.get("objective_value", "")) for row in condition_flux_rows if str(row.get("objective_value", "")).strip()), "")
        fba_status = next((str(row.get("status", "")) for row in condition_flux_rows if str(row.get("status", "")).strip()), "missing")
        output.append(
            {
                "condition": condition,
                "condition_group": _condition_group(condition),
                "status": "ready" if condition_flux_rows or condition_pfba_rows or condition_bounds else "partial",
                "fba_status": fba_status,
                "objective_value": objective,
                "oxygen_lower_bound": _bound_for_role(condition_bounds, "oxygen", "lower_bound"),
                "oxygen_pfba_flux": _flux_for_role(condition_pfba_rows, "oxygen"),
                "co2_pfba_flux": _flux_for_role(condition_pfba_rows, "co2"),
                "substrate_lower_bound": _bound_for_role(condition_bounds, "substrate", "lower_bound"),
                "acetate_flux": _flux_for_role(condition_pfba_rows, "acetate"),
                "formate_flux": _flux_for_role(condition_pfba_rows, "formate"),
                "pyruvate_flux": _flux_for_role(condition_pfba_rows, "pyruvate"),
                "succinate_flux": _flux_for_role(condition_pfba_rows, "succinate"),
                "production_target_count": len(production_rows),
                "exchange_bound_count": len(condition_bounds),
                "guidance": "Compare highO2/lowO2 as oxygen-condition behavior; do not interpret these rows as voltage conditions.",
            }
        )
    return output


def _pathway_flux_comparison_rows(
    *,
    package: Path,
    pfba_rows: list[dict[str, str]],
    delta_fba_summary_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    if not pfba_rows:
        return [
            {
                "condition": "highO2/lowO2",
                "pathway_group": "not_available",
                "status": "not_available",
                "guidance": "No pFBA flux table is available for pathway-level flux aggregation.",
            }
        ]
    assignment = _pathway_assignment_map(package)
    grouped: dict[tuple[str, str], list[float]] = {}
    top_reaction: dict[tuple[str, str], tuple[str, float]] = {}
    for row in pfba_rows:
        condition = str(row.get("condition", "")).strip() or "default"
        reaction_id = _row_reaction_id(row)
        value = _safe_float(row.get("predicted_flux") or row.get("flux") or row.get("value"))
        if value is None:
            continue
        pathways = assignment.get(_normalize_reaction_id(reaction_id)) or [_reaction_functional_group(reaction_id, str(row.get("reaction_name", "")))]
        for pathway in pathways:
            key = (condition, pathway)
            grouped.setdefault(key, []).append(abs(value))
            current = top_reaction.get(key)
            if current is None or abs(value) > current[1]:
                top_reaction[key] = (reaction_id, abs(value))
    rows: list[dict[str, Any]] = []
    for (condition, pathway), values in sorted(grouped.items(), key=lambda item: (_condition_sort_key(item[0][0]), item[0][1])):
        top = top_reaction.get((condition, pathway), ("", 0.0))
        rows.append(
            {
                "condition": condition,
                "condition_group": _condition_group(condition),
                "pathway_group": pathway,
                "status": "ready",
                "reaction_count": len(values),
                "sum_abs_flux": _format_float(sum(values)),
                "mean_abs_flux": _format_float(sum(values) / len(values) if values else None),
                "top_reaction_id": top[0],
                "top_abs_flux": _format_float(top[1]),
                "delta_fba_context_rows": len(delta_fba_summary_rows),
                "guidance": "Pathway groups are derived from KEGG pathway mapping when available; otherwise reaction keywords are used as functional hints.",
            }
        )
    return rows[:80]


def _fva_flexibility_comparison_rows(
    *,
    fva_rows: list[dict[str, str]],
    fva_summary_rows: list[dict[str, str]],
    target_readiness_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    if fva_summary_rows:
        return [
            {
                "condition": row.get("condition", ""),
                "condition_group": _condition_group(str(row.get("condition", ""))),
                "status": "ready" if _safe_float(row.get("comparable_count", "")) else "partial",
                "target_count": row.get("target_count", ""),
                "comparable_count": row.get("comparable_count", ""),
                "within_fva_count": row.get("within_fva_count", ""),
                "within_fva_fraction": row.get("within_fva_fraction", ""),
                "mean_fva_width": row.get("mean_fva_width", ""),
                "guidance": "Targeted FVA summarizes flexibility for exchange, production-target, or representative reactions only.",
            }
            for row in fva_summary_rows
        ]
    if fva_rows:
        grouped = _group_rows(fva_rows, "condition")
        return [_summarize_fva_rows(condition, rows) for condition, rows in sorted(grouped.items())]
    return [
        {
            "condition": "targeted_scope",
            "condition_group": "combined",
            "status": "not_available",
            "target_count": len(target_readiness_rows),
            "comparable_count": 0,
            "within_fva_count": 0,
            "within_fva_fraction": "",
            "mean_fva_width": "",
            "guidance": "Targeted FVA was not generated. Run FVA for selected exchange, production-target, and pathway representative reactions if flexibility is needed.",
        }
    ]


def _oxygen_sweep_comparison_rows(
    *,
    exchange_bound_rows: list[dict[str, str]],
    flux_rows: list[dict[str, str]],
    pfba_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    oxygen_bounds = [row for row in exchange_bound_rows if _reaction_role(row) == "oxygen"]
    if not oxygen_bounds:
        return [
            {
                "sweep_point": "oxygen_unresolved",
                "condition": "",
                "oxygen_reaction_id": "",
                "oxygen_lower_bound": "",
                "status": "not_available",
                "guidance": "No oxygen exchange reaction/bound was resolved; oxygen sensitivity sweep is unavailable.",
            }
        ]
    rows: list[dict[str, Any]] = []
    min_bound = min((_safe_float(row.get("lower_bound", "")) or 0.0 for row in oxygen_bounds), default=0.0)
    for row in oxygen_bounds:
        condition = str(row.get("condition", "")).strip()
        condition_flux = [item for item in flux_rows if str(item.get("condition", "")).strip() == condition]
        condition_pfba = [item for item in pfba_rows if str(item.get("condition", "")).strip() == condition]
        rows.append(
            {
                "sweep_point": "observed_condition_bound",
                "condition": condition,
                "condition_group": _condition_group(condition),
                "oxygen_reaction_id": row.get("model_reaction_id") or row.get("reaction_id", ""),
                "oxygen_lower_bound": row.get("lower_bound", ""),
                "fba_status": next((item.get("status", "") for item in condition_flux if item.get("status")), ""),
                "objective_value": next((item.get("objective_value", "") for item in condition_flux if item.get("objective_value")), ""),
                "oxygen_pfba_flux": _flux_for_role(condition_pfba, "oxygen"),
                "status": "condition_bound_only",
                "guidance": "This row uses an observed condition oxygen bound; it is not a full oxygen sweep solve.",
            }
        )
    if min_bound < 0:
        for index, fraction in enumerate([1.0, 0.8, 0.6, 0.4, 0.2, 0.0], start=1):
            rows.append(
                {
                    "sweep_point": f"planned_sweep_{index}",
                    "condition": "oxygen_sweep_design",
                    "condition_group": "sweep_design",
                    "oxygen_reaction_id": oxygen_bounds[0].get("model_reaction_id") or oxygen_bounds[0].get("reaction_id", ""),
                    "oxygen_lower_bound": _format_float(min_bound * fraction),
                    "fba_status": "",
                    "objective_value": "",
                    "oxygen_pfba_flux": "",
                    "status": "planned_not_run",
                    "guidance": "Controlled six-point oxygen sweep design point; solver run is intentionally not executed inside comparison aggregation.",
                }
            )
    return rows


def _targeted_essentiality_comparison_rows(
    *,
    structural_tables: dict[str, list[dict[str, Any]]],
    target_readiness_rows: list[dict[str, str]],
    pathway_flux_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    changed_reactions = {
        str(row.get("reaction_id", "")).strip()
        for row in structural_tables.get("reaction_diff", [])
        if str(row.get("reaction_id", "")).strip()
    }
    pathway_candidates = [
        row for row in pathway_flux_rows if str(row.get("pathway_group", "")).lower() in {"respiration", "redox_quinone_flavin_eet", "fermentation", "transport_exchange"}
    ]
    return [
        {
            "target_scope": "changed_structural_reactions",
            "status": "not_run_targeted_scope" if changed_reactions else "not_available",
            "candidate_count": len(changed_reactions),
            "max_default_scope": 150,
            "guidance": "Targeted deletion is scoped to changed conventional GEM reactions when structural changes exist.",
        },
        {
            "target_scope": "respiration_redox_fermentation_transport",
            "status": "not_run_targeted_scope" if pathway_candidates else "not_available",
            "candidate_count": len(pathway_candidates),
            "max_default_scope": 150,
            "guidance": "Targeted essentiality should focus on respiration, redox, fermentation, transport/EET, and production-related candidates.",
        },
        {
            "target_scope": "production_targets",
            "status": "not_run_targeted_scope" if target_readiness_rows else "not_available",
            "candidate_count": len(target_readiness_rows),
            "max_default_scope": 150,
            "guidance": "Production target essentiality is optional and should be interpreted as model behavior, not biological causality.",
        },
    ]


def _enzyme_allocation_comparison_rows(
    *,
    enzyme_qc_rows: list[dict[str, str]],
    enzyme_capacity_rows: list[dict[str, str]],
    enzyme_flux_capacity_rows: list[dict[str, str]],
    gecko_condition_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not enzyme_qc_rows and not gecko_condition_rows:
        return [
            {
                "condition": "highO2/lowO2",
                "condition_group": "combined",
                "status": "optional_missing",
                "guidance": "No enzyme/proteome allocation table is available; GECKO remains an optional external-dependency path.",
            }
        ]
    rows: list[dict[str, Any]] = []
    qc_by_condition = {str(row.get("condition", "")).strip(): row for row in enzyme_qc_rows}
    capacity_by_condition = _group_rows(enzyme_capacity_rows, "condition")
    flux_capacity_by_condition = _group_rows(enzyme_flux_capacity_rows, "condition")
    conditions = sorted(set(qc_by_condition) | set(capacity_by_condition) | {str(row.get("condition", "")).strip() for row in gecko_condition_rows}, key=lambda item: (_condition_sort_key(item), item))
    for condition in conditions:
        qc = qc_by_condition.get(condition, {})
        capacity_rows = capacity_by_condition.get(condition, [])
        flux_capacity_rows = flux_capacity_by_condition.get(condition, [])
        readiness = str(qc.get("enzyme_readiness", "") or "partial")
        rows.append(
            {
                "condition": condition,
                "condition_group": _condition_group(condition),
                "status": "ready" if capacity_rows or flux_capacity_rows else "partial" if qc else "optional_missing",
                "protein_count": qc.get("protein_count", ""),
                "mapped_protein_fraction": qc.get("mapped_protein_fraction", ""),
                "kcat_prior_count": qc.get("kcat_prior_count", ""),
                "mapped_kcat_prior_fraction": qc.get("mapped_kcat_prior_fraction", ""),
                "capacity_reaction_count": qc.get("capacity_reaction_count", len(capacity_rows)),
                "ready_capacity_fraction": qc.get("ready_capacity_fraction", ""),
                "exceeds_capacity_count": qc.get("exceeds_capacity_count", len(flux_capacity_rows)),
                "enzyme_readiness": readiness,
                "guidance": _gecko_condition_guidance(readiness, 0, "not_run"),
            }
        )
    return rows


def _model_comparison_recommendation_cards(
    *,
    qc_matrix_rows: list[dict[str, Any]],
    phenotype_exchange_rows: list[dict[str, Any]],
    pathway_flux_rows: list[dict[str, Any]],
    fva_flexibility_rows: list[dict[str, Any]],
    oxygen_sweep_rows: list[dict[str, Any]],
    targeted_essentiality_rows: list[dict[str, Any]],
    enzyme_allocation_rows: list[dict[str, Any]],
    story_card_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ready_pathway_count = sum(1 for row in pathway_flux_rows if str(row.get("status", "")) == "ready")
    not_run_oxygen_count = sum(1 for row in oxygen_sweep_rows if str(row.get("status", "")) == "planned_not_run")
    fva_available = any(str(row.get("status", "")) in {"ready", "partial"} and _safe_float(row.get("comparable_count", "")) for row in fva_flexibility_rows)
    enzyme_available = any(str(row.get("status", "")) in {"ready", "partial"} for row in enzyme_allocation_rows)
    cards = [
        _story_card(
            1,
            "model_qc_fairness",
            "ready" if qc_matrix_rows else "partial",
            "Model construction fairness is summarized.",
            f"{len(qc_matrix_rows)} QC layer row(s) cover structure, objective, exchange bounds, evidence, and enzyme/proteome readiness.",
            "Use QC rows to separate model construction differences from downstream behavior differences.",
        ),
        _story_card(
            2,
            "phenotype_exchange",
            "ready" if phenotype_exchange_rows and str(phenotype_exchange_rows[0].get("status")) != "not_available" else "missing",
            "Phenotype and exchange behavior are available." if phenotype_exchange_rows else "Phenotype/exchange behavior is missing.",
            f"{len(phenotype_exchange_rows)} condition row(s) summarize objective, oxygen, byproduct, and production target context.",
            "Compare highO2/lowO2 only as oxygen-condition behavior.",
        ),
        _story_card(
            3,
            "pathway_flux",
            "ready" if ready_pathway_count else "missing",
            "Pathway-level flux summaries are available." if ready_pathway_count else "Pathway-level flux is not available.",
            f"{ready_pathway_count} pathway-condition row(s) were derived from pFBA and KEGG/pathway hints.",
            "Use pathway flux to choose submaps for visualization, not as a causal mechanism claim.",
        ),
        _story_card(
            4,
            "fva_oxygen_essentiality",
            "partial",
            "Sensitivity analyses are targeted and bounded.",
            f"FVA available: {fva_available}; planned oxygen sweep points: {not_run_oxygen_count}; essentiality scopes: {len(targeted_essentiality_rows)}.",
            "Run targeted FVA, oxygen sweep, or deletion only for selected reactions when needed.",
        ),
        _story_card(
            5,
            "enzyme_allocation",
            "ready" if enzyme_available else "optional_missing",
            "Enzyme/proteome allocation is handled as an independent GECKO layer.",
            f"{len(enzyme_allocation_rows)} enzyme allocation row(s) summarize proteomics/kcat/capacity readiness.",
            "Do not mix GECKO enzyme pseudo reactions into conventional GEM structural diff.",
        ),
    ]
    return [*cards, *story_card_rows[:1]][:6]


def _condition_exchange_chart_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metrics = [
        ("objective_value", "Growth objective", "growth"),
        ("oxygen_pfba_flux", "O2 uptake", "exchange"),
        ("co2_pfba_flux", "CO2 secretion", "exchange"),
        ("acetate_flux", "Acetate", "byproduct"),
        ("formate_flux", "Formate", "byproduct"),
        ("pyruvate_flux", "Pyruvate", "byproduct"),
        ("succinate_flux", "Succinate", "byproduct"),
    ]
    output: list[dict[str, Any]] = []
    for row in rows:
        condition = str(row.get("condition", "")).strip()
        group = str(row.get("condition_group", "")).strip() or _condition_group(condition)
        for metric_key, metric_label, category in metrics:
            value = _safe_float(row.get(metric_key, ""))
            output.append(
                {
                    "condition": condition,
                    "condition_group": group,
                    "metric_key": metric_key,
                    "metric_label": metric_label,
                    "metric_category": category,
                    "value": _format_float(value),
                    "abs_value": _format_float(abs(value) if value is not None else None),
                    "status": "ready" if value is not None else "missing",
                    "guidance": "Chart-ready highO2/lowO2 phenotype and exchange metric; sign follows model flux convention.",
                }
            )
    return output


def _pathway_flux_delta_chart_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, float]] = {}
    counts: dict[str, dict[str, int]] = {}
    for row in rows:
        if str(row.get("status", "")).lower() != "ready":
            continue
        pathway = str(row.get("pathway_group", "")).strip()
        if not pathway or pathway == "not_available":
            continue
        condition_group = _condition_group(str(row.get("condition_group") or row.get("condition") or ""))
        if condition_group not in {"highO2", "lowO2"}:
            continue
        value = _safe_float(row.get("sum_abs_flux", ""))
        if value is None:
            continue
        grouped.setdefault(pathway, {"highO2": 0.0, "lowO2": 0.0})
        counts.setdefault(pathway, {"highO2": 0, "lowO2": 0})
        grouped[pathway][condition_group] += value
        counts[pathway][condition_group] += int(_safe_float(row.get("reaction_count", "")) or 0)
    output: list[dict[str, Any]] = []
    for pathway, values in grouped.items():
        high = values.get("highO2", 0.0)
        low = values.get("lowO2", 0.0)
        delta = low - high
        has_pair = counts.get(pathway, {}).get("highO2", 0) > 0 and counts.get(pathway, {}).get("lowO2", 0) > 0
        output.append(
            {
                "pathway_group": pathway,
                "highO2_sum_abs_flux": _format_float(high),
                "lowO2_sum_abs_flux": _format_float(low),
                "delta_low_minus_high": _format_float(delta),
                "abs_delta": _format_float(abs(delta)),
                "highO2_reaction_count": counts.get(pathway, {}).get("highO2", 0),
                "lowO2_reaction_count": counts.get(pathway, {}).get("lowO2", 0),
                "status": "ready" if has_pair else "partial",
                "guidance": "Pathway flux delta is based on model pFBA absolute flux aggregation; use as descriptive model output, not causal proof.",
            }
        )
    output.sort(key=lambda row: (_safe_float(row.get("abs_delta", "")) or 0.0), reverse=True)
    return output


def _enzyme_pathway_allocation_chart_rows(
    *,
    package: Path,
    enzyme_capacity_rows: list[dict[str, str]],
    enzyme_flux_capacity_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    if enzyme_capacity_rows:
        rows = _enzyme_pathway_capacity_rows(
            package=package,
            enzyme_capacity_rows=enzyme_capacity_rows,
            enzyme_flux_capacity_rows=enzyme_flux_capacity_rows,
        )
        if rows:
            return rows
    rows = _enzyme_pathway_kcat_proteomics_rows(package)
    if rows:
        return rows
    return [
        {
            "pathway_group": "not_available",
            "pathway_id": "",
            "allocation_source": "not_available",
            "kcat_prior_count": "0",
            "gene_count": "0",
            "reaction_count": "0",
            "capacity_sum": "",
            "usage_sum": "",
            "highO2_protein_abundance": "",
            "lowO2_protein_abundance": "",
            "delta_low_minus_high": "",
            "mean_kcat_per_s": "",
            "mean_kcat_confidence": "",
            "status": "not_available",
            "guidance": "No reaction-level enzyme capacity, kcat-prior, or proteomics-pathway mapping data were available.",
        }
    ]


def _enzyme_pathway_capacity_rows(
    *,
    package: Path,
    enzyme_capacity_rows: list[dict[str, str]],
    enzyme_flux_capacity_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    pathway_by_reaction = _pathway_assignment_map(package)
    flux_by_reaction = {
        _normalize_reaction_id(str(row.get("reaction_id") or row.get("model_reaction_id") or row.get("reaction") or "")): row
        for row in enzyme_flux_capacity_rows
    }
    grouped: dict[str, dict[str, Any]] = {}
    for row in enzyme_capacity_rows:
        reaction_id = _normalize_reaction_id(str(row.get("reaction_id") or row.get("model_reaction_id") or row.get("reaction") or ""))
        if not reaction_id:
            continue
        pathways = pathway_by_reaction.get(reaction_id) or [_reaction_functional_group(reaction_id, str(row.get("reaction_name", "")))]
        capacity = _safe_float(row.get("capacity") or row.get("enzyme_capacity") or row.get("protein_capacity") or row.get("capacity_value")) or 0.0
        kcat = _safe_float(row.get("kcat_value") or row.get("kcat_per_s") or row.get("selected_kcat")) or 0.0
        flux_row = flux_by_reaction.get(reaction_id, {})
        usage = _safe_float(flux_row.get("usage") or flux_row.get("enzyme_usage") or flux_row.get("flux")) or 0.0
        for pathway in pathways:
            item = grouped.setdefault(pathway, {"reaction_ids": set(), "capacity_sum": 0.0, "usage_sum": 0.0, "kcat_sum": 0.0, "kcat_count": 0})
            item["reaction_ids"].add(reaction_id)
            item["capacity_sum"] += abs(capacity)
            item["usage_sum"] += abs(usage)
            if kcat > 0:
                item["kcat_sum"] += kcat
                item["kcat_count"] += 1
    output: list[dict[str, Any]] = []
    for pathway, item in sorted(grouped.items(), key=lambda entry: entry[1]["capacity_sum"], reverse=True):
        kcat_count = int(item["kcat_count"])
        output.append(
            {
                "pathway_group": pathway,
                "pathway_id": "",
                "allocation_source": "reaction_enzyme_capacity",
                "kcat_prior_count": str(kcat_count),
                "gene_count": "",
                "reaction_count": str(len(item["reaction_ids"])),
                "capacity_sum": _format_float(item["capacity_sum"]),
                "usage_sum": _format_float(item["usage_sum"]),
                "highO2_protein_abundance": "",
                "lowO2_protein_abundance": "",
                "delta_low_minus_high": "",
                "mean_kcat_per_s": _format_float(item["kcat_sum"] / kcat_count if kcat_count else None),
                "mean_kcat_confidence": "",
                "status": "ready",
                "guidance": "Pathway enzyme allocation aggregated from reaction-level enzyme capacity rows.",
            }
        )
    return output[:40]


def _enzyme_pathway_kcat_proteomics_rows(package: Path) -> list[dict[str, Any]]:
    kcat_rows = _read_kcat_prior_rows(package)
    proteomics_rows = _read_first_matching_rows(
        package,
        "inputs/omics/*absolute_proteomics*.csv",
        "normalized_inputs/omics/*absolute_proteomics*.csv",
    )
    kegg_to_pathways = _kegg_reaction_pathway_assignment_map(package)
    if not kcat_rows or not kegg_to_pathways:
        return []
    abundance = _proteomics_abundance_by_gene_condition(proteomics_rows)
    grouped: dict[str, dict[str, Any]] = {}
    for row in kcat_rows:
        kegg_reaction = str(row.get("target_id") or row.get("kegg_reaction_id") or row.get("reaction_id") or "").strip()
        if not kegg_reaction:
            continue
        pathways = kegg_to_pathways.get(kegg_reaction) or []
        if not pathways:
            continue
        gene_id = str(row.get("gene_id") or row.get("protein_id") or "").strip()
        kcat_value = _safe_float(row.get("value") or row.get("kcat_value") or row.get("kcat_per_s"))
        confidence = _safe_float(row.get("confidence") or row.get("kcat_confidence"))
        high_value = abundance.get((gene_id, "highO2"), 0.0) if gene_id else 0.0
        low_value = abundance.get((gene_id, "lowO2"), 0.0) if gene_id else 0.0
        for pathway_id, pathway_name in pathways:
            pathway_group = pathway_name or pathway_id
            item = grouped.setdefault(
                pathway_group,
                {
                    "pathway_id": pathway_id,
                    "genes": set(),
                    "kegg_reactions": set(),
                    "kcat_count": 0,
                    "kcat_sum": 0.0,
                    "confidence_sum": 0.0,
                    "confidence_count": 0,
                    "highO2": 0.0,
                    "lowO2": 0.0,
                },
            )
            item["kegg_reactions"].add(kegg_reaction)
            if gene_id:
                item["genes"].add(gene_id)
            item["kcat_count"] += 1
            if kcat_value is not None:
                item["kcat_sum"] += kcat_value
            if confidence is not None:
                item["confidence_sum"] += confidence
                item["confidence_count"] += 1
            item["highO2"] += high_value
            item["lowO2"] += low_value
    output: list[dict[str, Any]] = []
    for pathway_group, item in sorted(
        grouped.items(),
        key=lambda entry: (entry[1]["highO2"] + entry[1]["lowO2"], entry[1]["kcat_count"]),
        reverse=True,
    ):
        kcat_count = int(item["kcat_count"])
        confidence_count = int(item["confidence_count"])
        high = float(item["highO2"])
        low = float(item["lowO2"])
        output.append(
            {
                "pathway_group": pathway_group,
                "pathway_id": item["pathway_id"],
                "allocation_source": "kcat_prior_plus_absolute_proteomics_proxy",
                "kcat_prior_count": str(kcat_count),
                "gene_count": str(len(item["genes"])),
                "reaction_count": str(len(item["kegg_reactions"])),
                "capacity_sum": "",
                "usage_sum": "",
                "highO2_protein_abundance": _format_float(high),
                "lowO2_protein_abundance": _format_float(low),
                "delta_low_minus_high": _format_float(low - high),
                "mean_kcat_per_s": _format_float(item["kcat_sum"] / kcat_count if kcat_count else None),
                "mean_kcat_confidence": _format_float(item["confidence_sum"] / confidence_count if confidence_count else None),
                "status": "proxy",
                "guidance": "Pathway enzyme allocation proxy from GotEnzymes2 kcat priors joined to absolute proteomics by gene and KEGG pathway.",
            }
        )
    return output[:40]


def _read_kcat_prior_rows(package: Path) -> list[dict[str, str]]:
    patterns = [
        "inputs/omics/*ml_priors*.csv",
        "normalized_inputs/omics/*ml_priors*.csv",
        "generated_constraints/kcat_priors.csv",
        "generated_constraints/kcat_prior_candidates.csv",
        "inputs/omics/*gotenzymes*.csv",
        "normalized_inputs/omics/*gotenzymes*.csv",
        "inputs/omics/*kcat_priors*.csv",
        "normalized_inputs/omics/*kcat_priors*.csv",
        "dlkcat_results/dlkcat_reaction_kcat_priors.csv",
        "inputs/omics/*kcat*.csv",
        "normalized_inputs/omics/*kcat*.csv",
    ]
    for pattern in patterns:
        for path in sorted(package.glob(pattern)):
            rows = _read_rows(path)
            usable = [
                row for row in rows
                if str(row.get("target_id") or row.get("kegg_reaction_id") or row.get("reaction_id") or "").strip()
            ]
            if usable:
                return usable
    return []


def _read_first_matching_rows(package: Path, *patterns: str) -> list[dict[str, str]]:
    for pattern in patterns:
        for path in sorted(package.glob(pattern)):
            rows = _read_rows(path)
            if rows:
                return rows
    return []


def _proteomics_abundance_by_gene_condition(rows: list[dict[str, str]]) -> dict[tuple[str, str], float]:
    if not rows:
        return {}
    average_rows = [row for row in rows if "average" in str(row.get("sample", "")).lower()]
    source_rows = average_rows or rows
    abundance: dict[tuple[str, str], float] = {}
    for row in source_rows:
        gene_id = str(row.get("gene_id") or row.get("protein_id") or "").strip()
        if not gene_id:
            continue
        condition_group = _condition_group(str(row.get("condition") or row.get("sample") or "unknown"))
        value = (
            _safe_float(row.get("mass_abundance_mg_gDCW"))
            or _safe_float(row.get("value"))
            or _safe_float(row.get("raw_fraction_total_protein"))
            or 0.0
        )
        key = (gene_id, condition_group)
        abundance[key] = max(abundance.get(key, 0.0), value)
    return abundance


def _comparison_chart_manifest_rows(
    *,
    condition_exchange_chart_rows: list[dict[str, Any]],
    pathway_flux_delta_chart_rows: list[dict[str, Any]],
    qc_matrix_rows: list[dict[str, Any]],
    enzyme_allocation_rows: list[dict[str, Any]],
    enzyme_pathway_allocation_chart_rows: list[dict[str, Any]],
    fva_flexibility_rows: list[dict[str, Any]],
    oxygen_sweep_rows: list[dict[str, Any]],
    targeted_essentiality_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        {
            "chart_id": "qc_matrix",
            "status": "ready" if qc_matrix_rows else "missing",
            "row_count": len(qc_matrix_rows),
            "guidance": "Traffic-light matrix for model fairness and construction readiness.",
        },
        {
            "chart_id": "condition_exchange_bars",
            "status": "ready" if any(str(row.get("status")) == "ready" for row in condition_exchange_chart_rows) else "missing",
            "row_count": len(condition_exchange_chart_rows),
            "guidance": "Grouped bars for growth objective, oxygen, CO2, and byproduct flux metrics.",
        },
        {
            "chart_id": "pathway_flux_delta",
            "status": "ready" if any(str(row.get("status")) == "ready" for row in pathway_flux_delta_chart_rows) else "partial" if pathway_flux_delta_chart_rows else "missing",
            "row_count": len(pathway_flux_delta_chart_rows),
            "guidance": "Top pathway flux delta chart for highO2 versus lowO2 oxygen conditions.",
        },
        {
            "chart_id": "enzyme_allocation",
            "status": "ready" if enzyme_allocation_rows else "optional_missing",
            "row_count": len(enzyme_allocation_rows),
            "guidance": "GECKO/proteome allocation chart remains independent of conventional GEM structural diff.",
        },
        {
            "chart_id": "enzyme_pathway_allocation",
            "status": "ready" if any(str(row.get("status")) in {"ready", "proxy"} for row in enzyme_pathway_allocation_chart_rows) else "optional_missing",
            "row_count": len(enzyme_pathway_allocation_chart_rows),
            "guidance": "Pathway-level enzyme resource distribution uses reaction-level capacity when available; otherwise kcat/proteomics pathway coverage proxy.",
        },
        {
            "chart_id": "sensitivity_strip",
            "status": "partial",
            "row_count": len(fva_flexibility_rows) + len(oxygen_sweep_rows) + len(targeted_essentiality_rows),
            "guidance": "Sensitivity strip shows available/planned/not_available states without implying full-model scans were run.",
        },
    ]


def _row_reaction_id(row: dict[str, Any]) -> str:
    return str(row.get("model_reaction_id") or row.get("reaction_id") or row.get("cobra_reaction_id") or "").strip()


def _normalize_reaction_id(reaction_id: str) -> str:
    raw = str(reaction_id or "").strip()
    if raw.startswith("R_"):
        raw = raw[2:]
    return raw


def _reaction_text(row: dict[str, Any]) -> str:
    return " ".join(
        str(row.get(key, ""))
        for key in ("reaction_id", "model_reaction_id", "cobra_reaction_id", "reaction_name", "name", "note", "source", "product_name")
    ).lower()


def _reaction_role(row: dict[str, Any]) -> str:
    text = _reaction_text(row)
    reaction_id = _row_reaction_id(row).lower()
    if "oxygen" in text or "o2" in reaction_id or "cpd00007" in reaction_id:
        return "oxygen"
    if "co2" in text or "carbon dioxide" in text or "cpd00011" in reaction_id:
        return "co2"
    if "lactate" in text or "cpd00159" in reaction_id:
        return "substrate"
    if "glucose" in text or "glc" in reaction_id:
        return "substrate"
    for role, marker in (
        ("acetate", "cpd00029"),
        ("formate", "cpd00047"),
        ("pyruvate", "cpd00020"),
        ("succinate", "cpd00036"),
    ):
        if role in text or marker in reaction_id:
            return role
    if _is_exchange_id(reaction_id):
        return "exchange"
    return "internal"


def _bound_for_role(rows: list[dict[str, str]], role: str, bound_key: str) -> str:
    for row in rows:
        if _reaction_role(row) == role:
            return str(row.get(bound_key, ""))
    return ""


def _flux_for_role(rows: list[dict[str, str]], role: str) -> str:
    values: list[float] = []
    for row in rows:
        if _reaction_role(row) != role:
            continue
        value = _safe_float(row.get("predicted_flux") or row.get("flux") or row.get("value"))
        if value is not None:
            values.append(value)
    if not values:
        return ""
    return _format_float(sum(values))


def _pathway_assignment_map(package: Path) -> dict[str, list[str]]:
    candidates = [
        package / "visualization" / "kegg_pathway_maps" / "reaction_kegg_pathway_assignment.csv",
        package.parent.parent / "case_studies" / "shewanella_gecko_case_study" / "visualization" / "kegg_pathway_maps" / "reaction_kegg_pathway_assignment.csv",
    ]
    mapping: dict[str, list[str]] = {}
    for path in candidates:
        for row in _read_rows(path):
            reaction_id = _normalize_reaction_id(str(row.get("reaction_id") or row.get("model_reaction_id") or row.get("kegg_reaction_id") or ""))
            pathway = str(row.get("pathway_name") or row.get("pathway_id") or row.get("pathway_group") or "").strip()
            if reaction_id and pathway:
                mapping.setdefault(reaction_id, [])
                if pathway not in mapping[reaction_id]:
                    mapping[reaction_id].append(pathway)
        if mapping:
            break
    return mapping


def _kegg_reaction_pathway_assignment_map(package: Path) -> dict[str, list[tuple[str, str]]]:
    candidates = [
        package / "visualization" / "kegg_pathway_maps" / "reaction_kegg_pathway_assignment.csv",
        package.parent.parent / "case_studies" / "shewanella_gecko_case_study" / "visualization" / "kegg_pathway_maps" / "reaction_kegg_pathway_assignment.csv",
    ]
    mapping: dict[str, list[tuple[str, str]]] = {}
    for path in candidates:
        for row in _read_rows(path):
            kegg_reaction_id = str(row.get("kegg_reaction_id") or "").strip()
            if not kegg_reaction_id:
                continue
            pathway_id = str(row.get("pathway_id") or "").strip()
            pathway_name = str(row.get("pathway_name") or row.get("pathway_group") or pathway_id).strip()
            if not pathway_name:
                continue
            pair = (pathway_id, pathway_name)
            mapping.setdefault(kegg_reaction_id, [])
            if pair not in mapping[kegg_reaction_id]:
                mapping[kegg_reaction_id].append(pair)
        if mapping:
            break
    return mapping


def _reaction_functional_group(reaction_id: str, reaction_name: str = "") -> str:
    text = f"{reaction_id} {reaction_name}".lower()
    if any(marker in text for marker in ("atp", "adp", "nad", "nadh", "quinone", "flavin", "cytochrome", "mtr", "oxygen", "o2")):
        return "redox_quinone_flavin_eet"
    if any(marker in text for marker in ("acetate", "formate", "pyruvate", "succinate", "lactate", "ethanol")):
        return "fermentation"
    if any(marker in text for marker in ("tca", "citrate", "aconit", "succinate", "fumarate", "malate")):
        return "TCA cycle"
    if any(marker in text for marker in ("glycol", "gapd", "pgk", "pfk", "pgi")):
        return "Glycolysis / Gluconeogenesis"
    if any(marker in text for marker in ("ppp", "ribose", "pentose")):
        return "Pentose phosphate pathway"
    if any(marker in text for marker in ("ex_", "exchange", "transport", "cpd")) and _is_exchange_id(reaction_id):
        return "transport_exchange"
    return "other_internal_flux"


def _summarize_fva_rows(condition: str, rows: list[dict[str, str]]) -> dict[str, Any]:
    comparable: list[dict[str, str]] = [
        row for row in rows if _safe_float(row.get("fva_minimum", "")) is not None and _safe_float(row.get("fva_maximum", "")) is not None
    ]
    widths = [
        (_safe_float(row.get("fva_maximum", "")) or 0.0) - (_safe_float(row.get("fva_minimum", "")) or 0.0)
        for row in comparable
    ]
    within = sum(1 for row in comparable if str(row.get("within_fva", "")).lower() == "true")
    return {
        "condition": condition,
        "condition_group": _condition_group(condition),
        "status": "ready" if comparable else "partial",
        "target_count": len(rows),
        "comparable_count": len(comparable),
        "within_fva_count": within,
        "within_fva_fraction": _format_float(within / len(comparable) if comparable else None),
        "mean_fva_width": _format_float(sum(widths) / len(widths) if widths else None),
        "guidance": "Targeted FVA summarizes flexibility for selected reactions only.",
    }


def _axis_row(layer: str, status: str, signal_count: int, warning_count: int, headline: Any, guidance: str) -> dict[str, Any]:
    return {
        "axis_layer": layer,
        "status": status,
        "signal_count": signal_count,
        "warning_count": warning_count,
        "headline": str(headline or ""),
        "guidance": guidance,
    }


def _story_card(order: int, layer: str, status: str, title: str, detail: str, next_step: str) -> dict[str, Any]:
    return {
        "order": order,
        "layer": layer,
        "status": status,
        "title": title,
        "detail": detail,
        "next_step": next_step,
    }


def _interpretation_row(
    layer: str,
    status: str,
    headline: str,
    detail: str,
    recommended_next_step: str,
) -> dict[str, str]:
    return {
        "layer": layer,
        "status": status,
        "headline": headline,
        "detail": detail,
        "recommended_next_step": recommended_next_step,
    }


def _layer_status_row(layer: str, status: str, signal_count: int, warning_count: int, summary: str) -> dict[str, Any]:
    return {
        "layer": layer,
        "status": status,
        "signal_count": signal_count,
        "warning_count": warning_count,
        "summary": summary,
    }


def _count_rows_with_value(rows: list[dict[str, Any]], key: str, value: str) -> int:
    return sum(1 for row in rows if str(row.get(key, "")) == value)


def _structural_headline(structural_change_count: int, same_source_count: int, skipped_count: int) -> str:
    if structural_change_count:
        return f"{structural_change_count} variant(s) have conventional GEM structural changes."
    if same_source_count:
        return "No conventional GEM structural change detected for same-source variants."
    if skipped_count:
        return "Structural diff is partial because some model files could not be parsed."
    return "No structural changes were detected in parsed conventional GEM fields."


def _structural_detail(rows: list[dict[str, Any]], changed_reaction_count: int) -> str:
    if not rows:
        return "No structural diff rows were generated yet."
    if changed_reaction_count == 0:
        return "Reaction, bound, objective, and GPR drilldown did not find conventional GEM changes."
    return f"{changed_reaction_count} reaction-level structural signal(s) are available for drilldown."


def _reaction_drilldown_rows(
    reaction_diff_rows: list[dict[str, Any]],
    gene_gpr_rows: list[dict[str, Any]],
    bound_objective_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    records: dict[tuple[str, str, str], dict[str, Any]] = {}

    def base_record(variant_id: str, reaction_id: str, change_type: str) -> dict[str, Any]:
        key = (variant_id, reaction_id, change_type)
        if key not in records:
            records[key] = {
                "variant_id": variant_id,
                "reaction_id": reaction_id,
                "change_type": change_type,
                "reaction_name": "",
                "reference_lower_bound": "",
                "reference_upper_bound": "",
                "model_lower_bound": "",
                "model_upper_bound": "",
                "reference_gpr": "",
                "model_gpr": "",
                "is_exchange": _is_exchange_id(reaction_id),
                "pathway_or_subsystem_hint": "",
                "evidence_signal": "",
                "production_signal": "",
                "gecko_signal": "",
                "guidance": "",
            }
        return records[key]

    for row in reaction_diff_rows:
        variant_id = str(row.get("variant_id", ""))
        reaction_id = str(row.get("reaction_id", ""))
        change_type = str(row.get("change_type", "reaction_changed"))
        record = base_record(variant_id, reaction_id, change_type)
        record.update(
            {
                "reaction_name": row.get("reaction_name", ""),
                "reference_lower_bound": row.get("reference_lower_bound", ""),
                "reference_upper_bound": row.get("reference_upper_bound", ""),
                "model_lower_bound": row.get("model_lower_bound", ""),
                "model_upper_bound": row.get("model_upper_bound", ""),
                "is_exchange": row.get("is_exchange", _is_exchange_id(reaction_id)),
                "guidance": "Review this reaction-level structural change before interpreting downstream behavior.",
            }
        )

    for row in gene_gpr_rows:
        reaction_id = str(row.get("reaction_id", ""))
        if not reaction_id:
            continue
        variant_id = str(row.get("variant_id", ""))
        record = base_record(variant_id, reaction_id, "gpr_changed")
        record["reaction_name"] = row.get("name", "")
        record["reference_gpr"] = row.get("reference_gpr", "")
        record["model_gpr"] = row.get("model_gpr", "")
        record["guidance"] = "GPR changed; inspect gene evidence and downstream analysis compatibility."

    for row in bound_objective_rows:
        variant_id = str(row.get("variant_id", ""))
        item_id = str(row.get("item_id", ""))
        change_type = str(row.get("change_type", "bounds_or_objective_changed"))
        reaction_id = item_id if str(row.get("item_type", "")) == "reaction_bounds" else "objective_reactions"
        record = base_record(variant_id, reaction_id, change_type)
        if change_type == "bounds_changed":
            reference_bounds = str(row.get("reference_value", ""))
            model_bounds = str(row.get("model_value", ""))
            record["reference_lower_bound"], record["reference_upper_bound"] = _split_bounds_text(reference_bounds)
            record["model_lower_bound"], record["model_upper_bound"] = _split_bounds_text(model_bounds)
        record["guidance"] = row.get("guidance", "") or "Review bound or objective changes before comparing behavior."

    return list(records.values())


def _split_bounds_text(text: str) -> tuple[str, str]:
    if ".." not in str(text):
        return str(text), ""
    lower, upper = str(text).split("..", 1)
    return lower, upper


@dataclass(slots=True)
class ParsedModelStructure:
    path: Path | None
    status: str
    message: str
    reactions: dict[str, dict[str, Any]]
    metabolites: dict[str, dict[str, str]]
    genes: dict[str, dict[str, str]]
    objective_reactions: set[str]


def _parse_model_structure(path: Path | None) -> ParsedModelStructure:
    empty = ParsedModelStructure(path, "skipped_missing_model_path", "No model path was registered.", {}, {}, {}, set())
    if path is None:
        return empty
    if not path.exists():
        return ParsedModelStructure(path, "skipped_missing_model_file", "Model file does not exist.", {}, {}, {}, set())
    if path.suffix.lower() not in {".xml", ".sbml"}:
        return ParsedModelStructure(path, "skipped_unsupported_model_format", f"Unsupported structural diff format: {path.suffix}", {}, {}, {}, set())
    try:
        root = ET.parse(path).getroot()
    except Exception as exc:
        return ParsedModelStructure(path, "skipped_parse_error", f"{type(exc).__name__}: {exc}", {}, {}, {}, set())
    parameters = _sbml_parameters(root)
    metabolites = {
        _clean_sbml_id(species.attrib.get("id", "")): {
            "name": species.attrib.get("name", ""),
            "compartment": species.attrib.get("compartment", ""),
        }
        for species in _children_by_local(root, "species")
        if species.attrib.get("id")
    }
    genes: dict[str, dict[str, str]] = {}
    for gene in _children_by_local(root, "geneProduct"):
        gene_id = _clean_sbml_id(_attr_by_local(gene, "id") or _attr_by_local(gene, "label") or _attr_by_local(gene, "name"))
        if gene_id:
            genes[gene_id] = {"label": _attr_by_local(gene, "label") or gene_id}
    reactions: dict[str, dict[str, Any]] = {}
    for reaction in _children_by_local(root, "reaction"):
        reaction_id = _clean_sbml_id(reaction.attrib.get("id", ""))
        if not reaction_id:
            continue
        gpr = sorted({_clean_sbml_id(_attr_by_local(ref, "geneProduct")) for ref in _children_by_local(reaction, "geneProductRef") if _attr_by_local(ref, "geneProduct")})
        for gene_id in gpr:
            genes.setdefault(gene_id, {"label": gene_id})
        reactions[reaction_id] = {
            "name": reaction.attrib.get("name", ""),
            "lower_bound": _bound_value(reaction, "lowerFluxBound", parameters),
            "upper_bound": _bound_value(reaction, "upperFluxBound", parameters),
            "reversible": reaction.attrib.get("reversible", ""),
            "gpr": ";".join(gpr),
        }
    objectives = {
        _clean_sbml_id(_attr_by_local(flux, "reaction"))
        for flux in _children_by_local(root, "fluxObjective")
        if _attr_by_local(flux, "reaction")
    }
    if not reactions and not metabolites:
        return ParsedModelStructure(path, "skipped_empty_model", "No reactions or metabolites were parsed from the model.", {}, {}, {}, set())
    return ParsedModelStructure(path, "parsed", "Model structure parsed.", reactions, metabolites, genes, objectives)


def _children_by_local(root: ET.Element, local_name: str) -> list[ET.Element]:
    return [element for element in root.iter() if _local_name(element.tag) == local_name]


def _local_name(name: str) -> str:
    return name.rsplit("}", 1)[-1] if "}" in name else name


def _attr_by_local(element: ET.Element, local_name: str) -> str:
    for key, value in element.attrib.items():
        if _local_name(key) == local_name:
            return value
    return ""


def _sbml_parameters(root: ET.Element) -> dict[str, str]:
    output: dict[str, str] = {}
    for parameter in _children_by_local(root, "parameter"):
        parameter_id = parameter.attrib.get("id", "")
        if parameter_id:
            output[parameter_id] = parameter.attrib.get("value", "")
    return output


def _bound_value(reaction: ET.Element, attr_name: str, parameters: dict[str, str]) -> str:
    ref = _attr_by_local(reaction, attr_name)
    return parameters.get(ref, ref)


def _clean_sbml_id(value: str) -> str:
    return str(value or "").strip()


def _compare_model_structures(variant_id: str, reference: ParsedModelStructure, model: ParsedModelStructure) -> dict[str, Any]:
    if reference.status != "parsed" or model.status != "parsed":
        return {
            "label": "skipped",
            "added_reactions": set(),
            "removed_reactions": set(),
            "changed_bounds": set(),
            "added_metabolites": set(),
            "removed_metabolites": set(),
            "added_genes": set(),
            "removed_genes": set(),
            "changed_gpr": set(),
            "objective_changed": False,
            "guidance": f"Structural diff skipped. Reference: {reference.status}; model: {model.status}.",
        }
    same_path = reference.path and model.path and reference.path.resolve() == model.path.resolve()
    reference_reactions = set(reference.reactions)
    model_reactions = set(model.reactions)
    common_reactions = reference_reactions & model_reactions
    changed_bounds = {
        rid
        for rid in common_reactions
        if (
            str(reference.reactions[rid].get("lower_bound", "")),
            str(reference.reactions[rid].get("upper_bound", "")),
        )
        != (
            str(model.reactions[rid].get("lower_bound", "")),
            str(model.reactions[rid].get("upper_bound", "")),
        )
    }
    changed_gpr = {
        rid
        for rid in common_reactions
        if str(reference.reactions[rid].get("gpr", "")) != str(model.reactions[rid].get("gpr", ""))
    }
    objective_changed = reference.objective_reactions != model.objective_reactions
    added_reactions = model_reactions - reference_reactions
    removed_reactions = reference_reactions - model_reactions
    added_metabolites = set(model.metabolites) - set(reference.metabolites)
    removed_metabolites = set(reference.metabolites) - set(model.metabolites)
    added_genes = set(model.genes) - set(reference.genes)
    removed_genes = set(reference.genes) - set(model.genes)
    has_change = any((added_reactions, removed_reactions, changed_bounds, added_metabolites, removed_metabolites, added_genes, removed_genes, changed_gpr, objective_changed))
    if same_path:
        label = "reference_model" if "baseline" in variant_id.lower() else "same_source_model"
        guidance = "Model points to the same file as the reference; no structural change is expected."
    elif has_change:
        label = "structural_change_detected"
        guidance = "Structural differences were detected; review added/removed reactions, bounds, objective, and GPR changes before interpretation."
    else:
        label = "no_structural_change"
        guidance = "No structural differences were detected from parsed SBML fields."
    return {
        "label": label,
        "added_reactions": added_reactions,
        "removed_reactions": removed_reactions,
        "changed_bounds": changed_bounds,
        "added_metabolites": added_metabolites,
        "removed_metabolites": removed_metabolites,
        "added_genes": added_genes,
        "removed_genes": removed_genes,
        "changed_gpr": changed_gpr,
        "objective_changed": objective_changed,
        "guidance": guidance,
    }


def _reaction_diff_rows(
    variant_id: str,
    reference: ParsedModelStructure,
    model: ParsedModelStructure,
    comparison: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for reaction_id in sorted(comparison["added_reactions"]):
        reaction = model.reactions.get(reaction_id, {})
        rows.append(_reaction_diff_row(variant_id, reaction_id, "added", reaction, {}, model.path))
    for reaction_id in sorted(comparison["removed_reactions"]):
        reaction = reference.reactions.get(reaction_id, {})
        rows.append(_reaction_diff_row(variant_id, reaction_id, "removed", {}, reaction, reference.path))
    for reaction_id in sorted(comparison["changed_bounds"]):
        rows.append(_reaction_diff_row(variant_id, reaction_id, "changed_bounds", model.reactions.get(reaction_id, {}), reference.reactions.get(reaction_id, {}), model.path))
    return rows


def _reaction_diff_row(
    variant_id: str,
    reaction_id: str,
    change_type: str,
    model_reaction: dict[str, Any],
    reference_reaction: dict[str, Any],
    model_path: Path | None,
) -> dict[str, Any]:
    return {
        "variant_id": variant_id,
        "reaction_id": reaction_id,
        "change_type": change_type,
        "reaction_name": model_reaction.get("name") or reference_reaction.get("name", ""),
        "reference_lower_bound": reference_reaction.get("lower_bound", ""),
        "reference_upper_bound": reference_reaction.get("upper_bound", ""),
        "model_lower_bound": model_reaction.get("lower_bound", ""),
        "model_upper_bound": model_reaction.get("upper_bound", ""),
        "is_exchange": _is_exchange_id(reaction_id),
        "model_path": str(model_path or ""),
    }


def _entity_diff_rows(
    variant_id: str,
    entity_type: str,
    added: set[str],
    removed: set[str],
    reference_entities: dict[str, dict[str, str]],
    model_entities: dict[str, dict[str, str]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for entity_id in sorted(added):
        rows.append({"variant_id": variant_id, f"{entity_type}_id": entity_id, "change_type": "added", "name": model_entities.get(entity_id, {}).get("name", "") or model_entities.get(entity_id, {}).get("label", "")})
    for entity_id in sorted(removed):
        rows.append({"variant_id": variant_id, f"{entity_type}_id": entity_id, "change_type": "removed", "name": reference_entities.get(entity_id, {}).get("name", "") or reference_entities.get(entity_id, {}).get("label", "")})
    return rows


def _gene_gpr_diff_rows(
    variant_id: str,
    reference: ParsedModelStructure,
    model: ParsedModelStructure,
    comparison: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for gene_id in sorted(comparison["added_genes"]):
        rows.append(
            {
                "variant_id": variant_id,
                "gene_id": gene_id,
                "reaction_id": "",
                "change_type": "gene_added",
                "reference_gpr": "",
                "model_gpr": "",
                "name": model.genes.get(gene_id, {}).get("label", ""),
            }
        )
    for gene_id in sorted(comparison["removed_genes"]):
        rows.append(
            {
                "variant_id": variant_id,
                "gene_id": gene_id,
                "reaction_id": "",
                "change_type": "gene_removed",
                "reference_gpr": "",
                "model_gpr": "",
                "name": reference.genes.get(gene_id, {}).get("label", ""),
            }
        )
    for reaction_id in sorted(comparison["changed_gpr"]):
        rows.append(
            {
                "variant_id": variant_id,
                "gene_id": "",
                "reaction_id": reaction_id,
                "change_type": "gpr_changed",
                "reference_gpr": reference.reactions.get(reaction_id, {}).get("gpr", ""),
                "model_gpr": model.reactions.get(reaction_id, {}).get("gpr", ""),
                "name": model.reactions.get(reaction_id, {}).get("name", "") or reference.reactions.get(reaction_id, {}).get("name", ""),
            }
        )
    return rows


def _bound_objective_diff_rows(
    variant_id: str,
    reference: ParsedModelStructure,
    model: ParsedModelStructure,
    comparison: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for reaction_id in sorted(comparison["changed_bounds"]):
        rows.append(
            {
                "variant_id": variant_id,
                "item_type": "reaction_bounds",
                "item_id": reaction_id,
                "change_type": "bounds_changed",
                "reference_value": _bounds_text(reference.reactions.get(reaction_id, {})),
                "model_value": _bounds_text(model.reactions.get(reaction_id, {})),
                "guidance": "Review whether bound changes come from condition setup or model generation.",
            }
        )
    if comparison["objective_changed"]:
        rows.append(
            {
                "variant_id": variant_id,
                "item_type": "objective",
                "item_id": "objective_reactions",
                "change_type": "objective_changed",
                "reference_value": ";".join(sorted(reference.objective_reactions)),
                "model_value": ";".join(sorted(model.objective_reactions)),
                "guidance": "Objective reaction changed; interpret FBA and production comparisons with care.",
            }
        )
    return rows


def _bounds_text(reaction: dict[str, Any]) -> str:
    return f"{reaction.get('lower_bound', '')}..{reaction.get('upper_bound', '')}"


def _is_exchange_id(reaction_id: str) -> bool:
    text = reaction_id.upper()
    return text.startswith("EX_") or text.startswith("R_EX_") or "EXCHANGE" in text


def _context_feasibility(sbml_path: str, cache: dict[str, dict[str, str]]) -> dict[str, str]:
    path_text = str(sbml_path or "").strip()
    if not path_text:
        return _feasibility_result("skipped_no_context_model", "", "No context SBML path is registered.")
    if path_text in cache:
        return cache[path_text]
    path = Path(path_text)
    if not path.exists():
        result = _feasibility_result("skipped_missing_context_model", "", "Context SBML file does not exist.")
        cache[path_text] = result
        return result
    try:
        from .cobra_runner import cobrapy_available

        if not cobrapy_available():
            result = _feasibility_result("skipped_cobrapy_missing", "", "COBRApy is not available.")
            cache[path_text] = result
            return result
        from cobra.io import read_sbml_model

        model = read_sbml_model(str(path))
        solution = model.optimize()
        cobra_status = str(getattr(solution, "status", ""))
        objective_value = getattr(solution, "objective_value", "")
        status = "feasible" if cobra_status == "optimal" else "infeasible"
        result = _feasibility_result(status, str(objective_value), f"COBRApy optimize status: {cobra_status}.")
    except Exception as exc:
        result = _feasibility_result("skipped_feasibility_error", "", f"{type(exc).__name__}: {exc}")
    cache[path_text] = result
    return result


def _feasibility_result(status: str, objective_value: str, message: str) -> dict[str, str]:
    return {
        "context_model_feasibility_status": status,
        "context_model_objective_value": objective_value,
        "context_model_feasibility_message": message,
    }


def _evidence_quality_label(
    *,
    confidence: str,
    context_available: bool,
    feasibility_status: str,
    fba_status: str,
) -> str:
    confidence_text = str(confidence or "").lower()
    if feasibility_status == "infeasible":
        return "usable_with_caution"
    if "strong" in confidence_text and fba_status in {"optimal", "completed"}:
        return "stronger_evidence"
    if "usable" in confidence_text or "caution" in confidence_text:
        return "usable_with_caution"
    if context_available and feasibility_status in {"feasible", "skipped_cobrapy_missing"}:
        return "usable_with_caution"
    if fba_status == "optimal":
        return "usable_with_caution"
    return "guidance_only"


def _variant_guidance(
    *,
    method: str,
    context_available: bool,
    feasibility_status: str,
    fba_status: str,
    quality: str,
) -> str:
    if method in {"fastcore", "consensus_evidence"} and not context_available:
        return "Context variant has no exportable SBML yet; use it as evidence guidance before model-backed analysis."
    if feasibility_status == "infeasible":
        return "Context SBML was exported but failed the lightweight feasibility check; inspect delete/core artifacts before downstream analysis."
    if fba_status == "missing":
        return f"Variant is registered with {quality} quality; run FBA/pFBA to compare objective behavior."
    if quality == "stronger_evidence":
        return "Variant has stronger evidence and model-backed analysis output."
    if quality == "usable_with_caution":
        return "Variant is usable with caution; review evidence quality, feasibility, and FBA status before interpreting targets."
    return "Variant is best treated as guidance-only until more evidence or model-backed analysis is available."
