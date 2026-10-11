"""Quality diagnostics for omics evidence used in context reconstruction."""

from __future__ import annotations

from pathlib import Path

from .cobra_runner import group_by_condition
from .constraints import read_csv_records, write_csv, write_json


def build_omics_signal_quality(
    gene_evidence_path: str | Path | None,
    reaction_evidence_path: str | Path | None,
    fastcore_core_path: str | Path | None,
    troppo_summary_path: str | Path | None,
    troppo_selected_path: str | Path | None,
    output_dir: str | Path,
) -> dict[str, str]:
    """Build condition-wise diagnostics for omics-derived reconstruction signal."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "quality": str(output / "omics_signal_quality.csv"),
        "recommendations": str(output / "omics_signal_recommendations.csv"),
        "quality_manifest": str(output / "omics_signal_quality_manifest.json"),
    }

    gene_rows = _read_existing(gene_evidence_path)
    reaction_rows = _read_existing(reaction_evidence_path)
    fastcore_rows = _read_existing(fastcore_core_path)
    troppo_summary_rows = _read_existing(troppo_summary_path)
    selected_rows = _read_existing(troppo_selected_path)

    gene_by_condition = group_by_condition(gene_rows)
    reaction_by_condition = group_by_condition(reaction_rows)
    fastcore_by_condition = group_by_condition(fastcore_rows)
    selected_by_condition = group_by_condition(selected_rows)
    summary_by_condition = {
        row.get("condition") or "default": row
        for row in troppo_summary_rows
    }

    conditions = sorted(
        set(gene_by_condition)
        | set(reaction_by_condition)
        | set(fastcore_by_condition)
        | set(selected_by_condition)
        | set(summary_by_condition)
    )

    quality_rows = []
    recommendation_rows = []
    for condition in conditions:
        gene_stats = summarize_gene_evidence(gene_by_condition.get(condition, []))
        reaction_stats = summarize_reaction_evidence(reaction_by_condition.get(condition, []))
        selected_stats = summarize_selected_reactions(selected_by_condition.get(condition, []))
        summary = summary_by_condition.get(condition, {})
        fastcore_candidate_count = len(fastcore_by_condition.get(condition, []))
        candidate_core_count = _to_int(summary.get("candidate_core_count")) or fastcore_candidate_count
        filtered_core_count = _to_int(summary.get("filtered_core_count")) or 0
        selected_count = _to_int(summary.get("selected_count")) or selected_stats["selected_count"]
        filtered_core_fraction = _fraction(filtered_core_count, candidate_core_count)
        supporting_fraction = _fraction(selected_stats["supporting_count"], selected_count)
        core_retention_fraction = _fraction(selected_stats["core_selected_count"], candidate_core_count)
        quality_label = classify_signal_quality(
            reaction_coverage_fraction=reaction_stats["measured_gpr_fraction"],
            fastcore_candidate_count=fastcore_candidate_count,
            filtered_core_fraction=filtered_core_fraction,
            supporting_fraction=supporting_fraction,
            feasibility_status=summary.get("feasibility_status", ""),
        )
        recommendations = build_recommendations(
            quality_label=quality_label,
            reaction_coverage_fraction=reaction_stats["measured_gpr_fraction"],
            fastcore_candidate_count=fastcore_candidate_count,
            filtered_core_fraction=filtered_core_fraction,
            supporting_fraction=supporting_fraction,
            feasibility_status=summary.get("feasibility_status", ""),
        )
        quality_rows.append(
            {
                "condition": condition,
                **gene_stats,
                **reaction_stats,
                "fastcore_candidate_count": fastcore_candidate_count,
                "troppo_candidate_core_count": candidate_core_count,
                "troppo_filtered_core_count": filtered_core_count,
                "troppo_filtered_core_fraction": filtered_core_fraction,
                **selected_stats,
                "core_retention_fraction": core_retention_fraction,
                "supporting_fraction": supporting_fraction,
                "feasibility_status": summary.get("feasibility_status", ""),
                "signal_quality": quality_label,
                "primary_recommendation": recommendations[0]["recommendation"] if recommendations else "",
            }
        )
        recommendation_rows.extend({"condition": condition, **row} for row in recommendations)

    write_csv(files["quality"], quality_rows)
    write_csv(files["recommendations"], recommendation_rows)
    write_json(
        files["quality_manifest"],
        {
            "status": "completed",
            "conditions": conditions,
            "gene_evidence_path": str(gene_evidence_path) if gene_evidence_path else "",
            "reaction_evidence_path": str(reaction_evidence_path) if reaction_evidence_path else "",
            "fastcore_core_path": str(fastcore_core_path) if fastcore_core_path else "",
            "troppo_summary_path": str(troppo_summary_path) if troppo_summary_path else "",
            "troppo_selected_path": str(troppo_selected_path) if troppo_selected_path else "",
            "files": files,
        },
    )
    return files


def summarize_gene_evidence(rows: list[dict[str, str]]) -> dict[str, object]:
    """Summarize gene-level evidence counts and mapping."""

    total = len(rows)
    high = _count_value(rows, "evidence", "high")
    medium = _count_value(rows, "evidence", "medium")
    low = _count_value(rows, "evidence", "low")
    mapped = sum(1 for row in rows if row.get("status") == "mapped")
    return {
        "gene_count": total,
        "mapped_gene_count": mapped,
        "mapped_gene_fraction": _fraction(mapped, total),
        "high_gene_count": high,
        "high_gene_fraction": _fraction(high, total),
        "medium_gene_count": medium,
        "medium_gene_fraction": _fraction(medium, total),
        "low_gene_count": low,
        "low_gene_fraction": _fraction(low, total),
    }


def summarize_reaction_evidence(rows: list[dict[str, str]]) -> dict[str, object]:
    """Summarize reaction-level GPR evidence and omics coverage."""

    total = len(rows)
    gpr_rows = [row for row in rows if (_to_int(row.get("gene_count")) or 0) > 0]
    measured_gpr = [row for row in gpr_rows if (_to_int(row.get("measured_gene_count")) or 0) > 0]
    high = _count_value(rows, "evidence", "high")
    medium = _count_value(rows, "evidence", "medium")
    low = _count_value(rows, "evidence", "low")
    unknown = _count_value(rows, "evidence", "unknown")
    no_gpr = _count_value(rows, "evidence", "no_gpr")
    coverages = [_to_float(row.get("gene_coverage")) for row in measured_gpr]
    coverages = [value for value in coverages if value is not None]
    return {
        "reaction_count": total,
        "gpr_reaction_count": len(gpr_rows),
        "measured_gpr_reaction_count": len(measured_gpr),
        "measured_gpr_fraction": _fraction(len(measured_gpr), len(gpr_rows)),
        "mean_measured_gene_coverage": sum(coverages) / len(coverages) if coverages else None,
        "high_reaction_count": high,
        "high_reaction_fraction": _fraction(high, total),
        "medium_reaction_count": medium,
        "medium_reaction_fraction": _fraction(medium, total),
        "low_reaction_count": low,
        "low_reaction_fraction": _fraction(low, total),
        "unknown_reaction_count": unknown,
        "unknown_reaction_fraction": _fraction(unknown, total),
        "no_gpr_reaction_count": no_gpr,
        "no_gpr_reaction_fraction": _fraction(no_gpr, total),
    }


def summarize_selected_reactions(rows: list[dict[str, str]]) -> dict[str, int]:
    """Summarize TROPPO-selected reactions by role."""

    selected = len(rows)
    core_selected = sum(1 for row in rows if row.get("role") == "core")
    supporting = sum(1 for row in rows if row.get("role") == "supporting")
    return {
        "selected_count": selected,
        "core_selected_count": core_selected,
        "supporting_count": supporting,
    }


def classify_signal_quality(
    reaction_coverage_fraction: float | None,
    fastcore_candidate_count: int,
    filtered_core_fraction: float | None,
    supporting_fraction: float | None,
    feasibility_status: str,
) -> str:
    """Classify whether the omics signal is exploratory, usable, or strong."""

    coverage = reaction_coverage_fraction or 0.0
    filtered = filtered_core_fraction or 0.0
    supporting = supporting_fraction or 0.0
    if fastcore_candidate_count < 20 or coverage < 0.05:
        return "exploratory"
    if filtered >= 0.4 or supporting >= 0.9 or feasibility_status == "optimal_zero_objective":
        return "guidance_only"
    if coverage >= 0.25 and fastcore_candidate_count >= 100 and filtered < 0.2:
        return "strong"
    return "usable_with_caution"


def build_recommendations(
    quality_label: str,
    reaction_coverage_fraction: float | None,
    fastcore_candidate_count: int,
    filtered_core_fraction: float | None,
    supporting_fraction: float | None,
    feasibility_status: str,
) -> list[dict[str, str]]:
    """Create human-readable QC recommendations."""

    recommendations = []
    if quality_label in {"exploratory", "guidance_only"}:
        recommendations.append(
            {
                "severity": "high",
                "topic": "interpretation",
                "recommendation": "Use the omics evidence as directional guidance; avoid treating the context model as a definitive phenotype-specific GEM.",
            }
        )
    if fastcore_candidate_count < 50:
        recommendations.append(
            {
                "severity": "medium",
                "topic": "coverage",
                "recommendation": "FASTcore has few omics-supported core reactions; add broader transcriptomics/proteomics coverage or use less brittle methods such as CORDA/iMAT comparison.",
            }
        )
    if (reaction_coverage_fraction or 0.0) < 0.1:
        recommendations.append(
            {
                "severity": "medium",
                "topic": "gene_coverage",
                "recommendation": "Only a small fraction of model GPR reactions have measured genes; report this as sparse evidence rather than a full context reconstruction.",
            }
        )
    if (filtered_core_fraction or 0.0) >= 0.3:
        recommendations.append(
            {
                "severity": "medium",
                "topic": "media_consistency",
                "recommendation": "Many high-expression core reactions cannot carry flux under the current exchange bounds; check condition/media consistency and threshold choices.",
            }
        )
    if (supporting_fraction or 0.0) >= 0.85:
        recommendations.append(
            {
                "severity": "low",
                "topic": "network_support",
                "recommendation": "Most selected reactions are supporting reactions added for network consistency, so omics specificity is limited.",
            }
        )
    if feasibility_status == "optimal_zero_objective":
        recommendations.append(
            {
                "severity": "low",
                "topic": "growth",
                "recommendation": "The context model is feasible but does not support positive biomass; do not over-interpret growth from this omics set.",
            }
        )
    if not recommendations:
        recommendations.append(
            {
                "severity": "info",
                "topic": "signal",
                "recommendation": "Omics signal is internally consistent enough for context reconstruction, while still requiring biological validation.",
            }
        )
    return recommendations


def _read_existing(path: str | Path | None) -> list[dict[str, str]]:
    if not path:
        return []
    table = Path(path)
    if not table.exists() or table.stat().st_size == 0:
        return []
    return read_csv_records(table)


def _count_value(rows: list[dict[str, str]], key: str, value: str) -> int:
    return sum(1 for row in rows if row.get(key) == value)


def _fraction(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _to_int(value: object) -> int | None:
    try:
        if value in {None, ""}:
            return None
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _to_float(value: object) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(str(value))
    except (TypeError, ValueError):
        return None
