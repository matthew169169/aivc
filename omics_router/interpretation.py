"""Condition-level interpretation dashboard for multi-omics GEM workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .constraints import read_csv_records, write_csv, write_json


@dataclass(slots=True)
class InterpretationDashboardResult:
    """Summary returned after writing condition-level interpretation tables."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]


def run_condition_interpretation_dashboard(
    constraints_dir: str | Path,
    evidence_mode_results_dir: str | Path,
    context_results_dir: str | Path,
    troppo_results_dir: str | Path,
    output_dir: str | Path,
    ml_results_dir: str | Path | None = None,
) -> InterpretationDashboardResult:
    """Build and write condition-level interpretation tables."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "summary": str(output / "condition_interpretation_summary.csv"),
        "recommendations": str(output / "condition_interpretation_recommendations.csv"),
        "manifest": str(output / "condition_interpretation_manifest.json"),
    }
    tables = build_condition_interpretation_tables(
        constraints_dir=constraints_dir,
        evidence_mode_results_dir=evidence_mode_results_dir,
        context_results_dir=context_results_dir,
        troppo_results_dir=troppo_results_dir,
        ml_results_dir=ml_results_dir,
    )
    write_csv(files["summary"], tables["summary"])
    write_csv(files["recommendations"], tables["recommendations"])
    write_json(
        files["manifest"],
        {
            "status": "completed",
            "constraints_dir": str(constraints_dir),
            "evidence_mode_results_dir": str(evidence_mode_results_dir),
            "context_results_dir": str(context_results_dir),
            "troppo_results_dir": str(troppo_results_dir),
            "ml_results_dir": str(ml_results_dir) if ml_results_dir else "",
            "summary_rows": len(tables["summary"]),
            "recommendation_rows": len(tables["recommendations"]),
            "files": files,
        },
    )
    return InterpretationDashboardResult(
        status="completed",
        output_dir=str(output),
        message=f"Built condition interpretation for {len(tables['summary'])} conditions.",
        files=files,
    )


def build_condition_interpretation_tables(
    constraints_dir: str | Path,
    evidence_mode_results_dir: str | Path,
    context_results_dir: str | Path,
    troppo_results_dir: str | Path,
    ml_results_dir: str | Path | None = None,
) -> dict[str, list[dict[str, object]]]:
    """Return condition-level summary and recommendation rows."""

    constraints = Path(constraints_dir)
    evidence_dir = Path(evidence_mode_results_dir)
    context_dir = Path(context_results_dir)
    troppo_dir = Path(troppo_results_dir)
    ml_dir = Path(ml_results_dir) if ml_results_dir else None

    conflict_summary = _by_condition(_read_optional(constraints / "multi_omics_conflict_summary.csv"))
    mode_summary_rows = _read_optional(evidence_dir / "evidence_mode_summary.csv")
    mode_summary = {
        (row.get("evidence_mode", ""), row.get("condition", "")): row
        for row in mode_summary_rows
    }
    delta_summary = _by_condition(_read_optional(evidence_dir / "evidence_mode_delta_summary.csv"))
    context_summary = _by_condition(_read_optional(context_dir / "context_feasibility_summary.csv"))
    omics_quality = _by_condition(_read_optional(troppo_dir / "omics_signal_quality.csv"))
    ml_diagnostic = _first_row(_read_optional(ml_dir / "ml_diagnostic_summary.csv") if ml_dir else [])
    ml_clusters = _by_condition(_read_optional(ml_dir / "ml_condition_clusters.csv") if ml_dir else [])

    conditions = sorted(
        (
            set(conflict_summary)
            | {row.get("condition", "") for row in mode_summary_rows}
            | set(delta_summary)
            | set(context_summary)
            | set(omics_quality)
            | set(ml_clusters)
        )
        - {"", "ALL"}
    )

    summary_rows = []
    recommendation_rows = []
    for condition in conditions:
        row = build_condition_summary_row(
            condition=condition,
            conflict=conflict_summary.get(condition, {}),
            consensus_mode=mode_summary.get(("consensus", condition), {}),
            relative_mode=mode_summary.get(("relative_proteomics", condition), {}),
            delta=delta_summary.get(condition, {}),
            context=context_summary.get(condition, {}),
            omics=omics_quality.get(condition, {}),
            ml_diagnostic=ml_diagnostic,
            ml_cluster=ml_clusters.get(condition, {}),
        )
        summary_rows.append(row)
        recommendation_rows.extend(build_condition_recommendations(row))

    return {"summary": summary_rows, "recommendations": recommendation_rows}


def build_condition_summary_row(
    *,
    condition: str,
    conflict: dict[str, str],
    consensus_mode: dict[str, str],
    relative_mode: dict[str, str],
    delta: dict[str, str],
    context: dict[str, str],
    omics: dict[str, str],
    ml_diagnostic: dict[str, str] | None = None,
    ml_cluster: dict[str, str] | None = None,
) -> dict[str, object]:
    """Build one condition-level interpretation row."""

    measured_gpr_fraction = _first_float(omics, consensus_mode, key="measured_gpr_fraction")
    conflict_fraction = _to_float(conflict.get("conflict_fraction"))
    supporting_fraction = _to_float(omics.get("supporting_fraction"))
    filtered_core_fraction = _to_float(omics.get("troppo_filtered_core_fraction"))
    conflict_softened_count = _to_int(delta.get("conflict_softened_count")) or 0
    missing_protein_count = _to_int(delta.get("relative_proteomics_missing_reaction_count")) or 0
    consensus_core_count = _to_int(consensus_mode.get("fastcore_core_count")) or 0
    consensus_delete_count = _to_int(consensus_mode.get("context_delete_candidate_count")) or 0
    context_objective = _to_float(context.get("objective_value"))
    ml_diagnostic = ml_diagnostic or {}
    ml_cluster = ml_cluster or {}
    ml_consensus_disagreement_count = _to_int(delta.get("ml_consensus_disagreement_count")) or 0
    ml_soft_prior_added_count = _to_int(delta.get("ml_soft_prior_added_count")) or 0
    ml_sample_status = ml_cluster.get("sample_status") or ml_diagnostic.get("sample_status", "")
    flags = condition_risk_flags(
        signal_quality=omics.get("signal_quality", ""),
        measured_gpr_fraction=measured_gpr_fraction,
        supporting_fraction=supporting_fraction,
        filtered_core_fraction=filtered_core_fraction,
        feasibility_status=omics.get("feasibility_status", ""),
        conflict_fraction=conflict_fraction,
        conflict_softened_count=conflict_softened_count,
        missing_protein_count=missing_protein_count,
        ml_sample_status=ml_sample_status,
        ml_consensus_disagreement_count=ml_consensus_disagreement_count,
        ml_soft_prior_added_count=ml_soft_prior_added_count,
    )
    level = classify_condition_interpretation(flags)
    return {
        "condition": condition,
        "interpretation_level": level,
        "primary_message": primary_message(level, flags),
        "risk_flags": ";".join(flags),
        "signal_quality": omics.get("signal_quality", ""),
        "measured_gpr_fraction": measured_gpr_fraction,
        "conflict_fraction": conflict_fraction,
        "conflict_count": _to_int(conflict.get("conflict_count")) or 0,
        "conflict_softened_count": conflict_softened_count,
        "evidence_mode_delta_count": _to_int(delta.get("reaction_delta_count")) or 0,
        "relative_proteomics_status": relative_mode.get("status", "missing"),
        "relative_proteomics_missing_reaction_count": missing_protein_count,
        "ml_diagnostic_status": ml_diagnostic.get("status", ""),
        "ml_sample_status": ml_sample_status,
        "ml_cluster_id": ml_cluster.get("cluster_id", ""),
        "ml_cluster_distance_to_centroid": _to_float(ml_cluster.get("distance_to_centroid")),
        "ml_consensus_disagreement_count": ml_consensus_disagreement_count,
        "ml_soft_prior_added_count": ml_soft_prior_added_count,
        "ml_lasso_lite_feature_count": _to_int(ml_diagnostic.get("lasso_lite_feature_count")) or 0,
        "consensus_fastcore_core_count": consensus_core_count,
        "consensus_delete_candidate_count": consensus_delete_count,
        "context_feasibility_status": context.get("status", ""),
        "context_objective_value": context_objective,
        "context_knockout_count": _to_int(context.get("knockout_count")) or 0,
        "troppo_feasibility_status": omics.get("feasibility_status", ""),
        "troppo_supporting_fraction": supporting_fraction,
        "troppo_filtered_core_fraction": filtered_core_fraction,
        "core_retention_fraction": _to_float(omics.get("core_retention_fraction")),
        "primary_recommendation": omics.get("primary_recommendation", ""),
        "status": "summary",
    }


def condition_risk_flags(
    *,
    signal_quality: str,
    measured_gpr_fraction: float | None,
    supporting_fraction: float | None,
    filtered_core_fraction: float | None,
    feasibility_status: str,
    conflict_fraction: float | None,
    conflict_softened_count: int,
    missing_protein_count: int,
    ml_sample_status: str = "",
    ml_consensus_disagreement_count: int = 0,
    ml_soft_prior_added_count: int = 0,
) -> list[str]:
    """Return stable interpretation flags for one condition."""

    flags: list[str] = []
    if signal_quality in {"exploratory", "guidance_only"}:
        flags.append("sparse_omics_signal")
    if (measured_gpr_fraction or 0.0) < 0.05:
        flags.append("low_gpr_coverage")
    if (supporting_fraction or 0.0) >= 0.9:
        flags.append("mostly_network_support")
    if (filtered_core_fraction or 0.0) >= 0.3:
        flags.append("many_core_candidates_filtered")
    if feasibility_status == "optimal_zero_objective":
        flags.append("troppo_zero_objective")
    if (conflict_fraction or 0.0) >= 0.10 or conflict_softened_count > 0:
        flags.append("multi_omics_conflict_review")
    if missing_protein_count > 0:
        flags.append("missing_relative_proteomics")
    if ml_sample_status in {"low_n_exploratory", "insufficient_n"}:
        flags.append("ml_low_n_exploratory")
    if ml_consensus_disagreement_count > 0:
        flags.append("ml_consensus_disagreement_review")
    if ml_soft_prior_added_count > 0:
        flags.append("ml_soft_prior_only")
    return flags or ["usable_with_caution"]


def classify_condition_interpretation(flags: list[str]) -> str:
    """Classify condition interpretation as red/yellow/green."""

    red_flags = {"sparse_omics_signal", "low_gpr_coverage", "mostly_network_support", "troppo_zero_objective"}
    yellow_flags = {
        "many_core_candidates_filtered",
        "multi_omics_conflict_review",
        "missing_relative_proteomics",
        "ml_low_n_exploratory",
        "ml_consensus_disagreement_review",
        "ml_soft_prior_only",
    }
    if any(flag in red_flags for flag in flags):
        return "red_guidance_only"
    if any(flag in yellow_flags for flag in flags):
        return "yellow_review_needed"
    return "green_usable_with_caution"


def primary_message(level: str, flags: list[str]) -> str:
    """Return a compact message for the condition-level dashboard."""

    if level == "red_guidance_only":
        return "Treat this condition as directional guidance; omics coverage or reconstruction specificity is too weak for definitive context claims."
    if "ml_consensus_disagreement_review" in flags:
        return "Usable with caution, but ML-derived priors disagree with consensus for some reactions."
    if "multi_omics_conflict_review" in flags:
        return "Usable for comparison, but inspect softened transcript/protein conflicts before interpreting reaction-level changes."
    if "ml_low_n_exploratory" in flags:
        return "ML diagnostics are exploratory because the condition count is small."
    if "missing_relative_proteomics" in flags:
        return "Consensus mostly follows available modalities because relative proteomics is missing for this condition."
    return "Evidence is internally consistent enough for cautious downstream interpretation."


def build_condition_recommendations(row: dict[str, object]) -> list[dict[str, object]]:
    """Build human-readable recommendations from a condition summary row."""

    condition = str(row.get("condition", ""))
    flags = set(str(row.get("risk_flags", "")).split(";"))
    recommendations: list[dict[str, object]] = []
    if {"sparse_omics_signal", "low_gpr_coverage"} & flags:
        recommendations.append(_recommendation(condition, "high", "coverage", "Add broader transcriptomics/proteomics coverage before treating this as a phenotype-specific GEM."))
    if "mostly_network_support" in flags or "troppo_zero_objective" in flags:
        recommendations.append(_recommendation(condition, "high", "context_model", "Use TROPPO output as a consistency-guided draft; most retained reactions are supporting reactions or biomass is zero."))
    if "multi_omics_conflict_review" in flags:
        recommendations.append(_recommendation(condition, "medium", "omics_conflict", "Inspect consensus-softened reactions before hard keep/delete decisions."))
    if "many_core_candidates_filtered" in flags:
        recommendations.append(_recommendation(condition, "medium", "media_consistency", "Check media/exchange bounds and thresholds because many core candidates cannot carry flux."))
    if "missing_relative_proteomics" in flags:
        recommendations.append(_recommendation(condition, "medium", "modality_coverage", "Relative proteomics is missing for this condition, so consensus evidence is effectively single-modality."))
    if "ml_consensus_disagreement_review" in flags:
        recommendations.append(_recommendation(condition, "medium", "ml_evidence", "Review reactions where ML-derived priors disagree with consensus before using ML evidence as a constraint hint."))
    if "ml_low_n_exploratory" in flags:
        recommendations.append(_recommendation(condition, "medium", "ml_diagnostics", "Treat PCA, clustering, and LASSO-lite diagnostics as exploratory because the sample size is small."))
    if "ml_soft_prior_only" in flags:
        recommendations.append(_recommendation(condition, "info", "ml_evidence", "Some reactions only have ML-derived soft priors; use them as hypotheses rather than hard edits."))
    if not recommendations:
        recommendations.append(_recommendation(condition, "info", "interpretation", "Proceed with cautious interpretation and keep phenotype/flux validation in the loop."))
    return recommendations


def _recommendation(condition: str, severity: str, topic: str, recommendation: str) -> dict[str, object]:
    return {
        "condition": condition,
        "severity": severity,
        "topic": topic,
        "recommendation": recommendation,
        "status": "recommendation",
    }


def _by_condition(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    return {row.get("condition", ""): row for row in rows if row.get("condition")}


def _first_row(rows: list[dict[str, str]]) -> dict[str, str]:
    return rows[0] if rows else {}


def _read_optional(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return read_csv_records(path)


def _first_float(primary: dict[str, str], fallback: dict[str, str], *, key: str) -> float | None:
    value = _to_float(primary.get(key))
    return value if value is not None else _to_float(fallback.get(key))


def _to_float(value: object) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _to_int(value: object) -> int | None:
    try:
        if value in {None, ""}:
            return None
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None
