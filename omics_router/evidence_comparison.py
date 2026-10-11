"""Compare downstream inputs produced by different evidence modes."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .constraints import read_csv_records, write_csv, write_json
from .evidence_modes import EVIDENCE_MODES, evidence_mode_paths


MEANINGFUL_EVIDENCE = {"high", "medium", "low"}
DECISIONS = ("protect", "keep", "support", "penalize_candidate", "delete_candidate", "neutral")


@dataclass(slots=True)
class EvidenceComparisonResult:
    """Summary returned after writing evidence-mode comparison outputs."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]


@dataclass(slots=True)
class ModeTables:
    """Loaded constraint tables for one evidence mode."""

    reactions: list[dict[str, str]]
    context: list[dict[str, str]]
    core: list[dict[str, str]]


def run_evidence_mode_comparison(
    constraints_dir: str | Path,
    output_dir: str | Path,
    modes: tuple[str, ...] = EVIDENCE_MODES,
) -> EvidenceComparisonResult:
    """Build and write comparison tables for available evidence modes."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "summary": str(output / "evidence_mode_summary.csv"),
        "delta_summary": str(output / "evidence_mode_delta_summary.csv"),
        "reaction_deltas": str(output / "evidence_mode_reaction_deltas.csv"),
        "recommendations": str(output / "evidence_mode_recommendations.csv"),
        "manifest": str(output / "evidence_mode_comparison_manifest.json"),
    }
    tables = build_evidence_mode_comparison_tables(constraints_dir, modes=modes)
    write_csv(files["summary"], tables["summary"])
    write_csv(files["delta_summary"], tables["delta_summary"])
    write_csv(files["reaction_deltas"], tables["reaction_deltas"])
    write_csv(files["recommendations"], tables["recommendations"])
    write_json(
        files["manifest"],
        {
            "status": "completed",
            "constraints_dir": str(constraints_dir),
            "modes": list(modes),
            "summary_rows": len(tables["summary"]),
            "reaction_delta_rows": len(tables["reaction_deltas"]),
            "files": files,
        },
    )
    return EvidenceComparisonResult(
        status="completed",
        output_dir=str(output),
        message=f"Compared {len(modes)} evidence modes; found {len(tables['reaction_deltas'])} changed reaction rows.",
        files=files,
    )


def build_evidence_mode_comparison_tables(
    constraints_dir: str | Path,
    modes: tuple[str, ...] = EVIDENCE_MODES,
) -> dict[str, list[dict[str, object]]]:
    """Return summary, reaction-delta, and recommendation tables."""

    loaded = {mode: load_mode_tables(constraints_dir, mode) for mode in modes}
    summary_rows = build_mode_summary_rows(loaded)
    reaction_delta_rows = build_reaction_delta_rows(loaded, modes=modes)
    delta_summary_rows = summarize_reaction_deltas(reaction_delta_rows, loaded, modes=modes)
    recommendation_rows = build_evidence_mode_recommendations(delta_summary_rows)
    return {
        "summary": summary_rows,
        "delta_summary": delta_summary_rows,
        "reaction_deltas": reaction_delta_rows,
        "recommendations": recommendation_rows,
    }


def load_mode_tables(constraints_dir: str | Path, mode: str) -> ModeTables:
    """Load reaction evidence, context policy, and FASTcore core rows."""

    paths = evidence_mode_paths(constraints_dir, mode)
    return ModeTables(
        reactions=_read_optional(paths.reaction_evidence),
        context=_read_optional(paths.context_policy),
        core=_read_optional(paths.core_reactions),
    )


def build_mode_summary_rows(loaded: dict[str, ModeTables]) -> list[dict[str, object]]:
    """Summarize evidence, context decisions, and core counts per mode."""

    conditions = sorted(
        set().union(
            *[
                {row.get("condition") or "default" for row in tables.reactions + tables.context + tables.core}
                for tables in loaded.values()
            ]
        )
    )
    rows: list[dict[str, object]] = []
    for mode, tables in loaded.items():
        for condition in conditions:
            rows.append(summarize_mode_condition(mode, condition, tables))
        rows.append(summarize_mode_condition(mode, "ALL", tables))
    return rows


def summarize_mode_condition(mode: str, condition: str, tables: ModeTables) -> dict[str, object]:
    """Summarize one mode/condition pair."""

    reaction_rows = _rows_for_condition(tables.reactions, condition)
    context_rows = _rows_for_condition(tables.context, condition)
    core_rows = _rows_for_condition(tables.core, condition)
    evidence_counts = Counter(row.get("evidence") or "unknown" for row in reaction_rows)
    decision_counts = Counter(row.get("decision") or "neutral" for row in context_rows)
    measured_gpr = [
        row for row in reaction_rows
        if _to_int(row.get("gene_count")) and (_to_int(row.get("measured_gene_count")) or 0) > 0
    ]
    gpr_rows = [row for row in reaction_rows if _to_int(row.get("gene_count"))]
    status = "available" if reaction_rows or context_rows or core_rows else "missing"
    summary = {
        "evidence_mode": mode,
        "condition": condition,
        "status": status,
        "reaction_count": len(reaction_rows),
        "measured_gpr_reaction_count": len(measured_gpr),
        "measured_gpr_fraction": _fraction(len(measured_gpr), len(gpr_rows)),
        "fastcore_core_count": len(core_rows),
        "high_reaction_count": evidence_counts.get("high", 0),
        "medium_reaction_count": evidence_counts.get("medium", 0),
        "low_reaction_count": evidence_counts.get("low", 0),
        "unknown_reaction_count": evidence_counts.get("unknown", 0),
        "no_gpr_reaction_count": evidence_counts.get("no_gpr", 0),
    }
    for decision in DECISIONS:
        summary[f"context_{decision}_count"] = decision_counts.get(decision, 0)
    return summary


def build_reaction_delta_rows(
    loaded: dict[str, ModeTables],
    modes: tuple[str, ...] = EVIDENCE_MODES,
) -> list[dict[str, object]]:
    """Build changed reaction rows across evidence modes."""

    reaction_maps = {mode: _key_by_condition_reaction(tables.reactions) for mode, tables in loaded.items()}
    context_maps = {mode: _key_by_condition_reaction(tables.context) for mode, tables in loaded.items()}
    core_sets = {mode: set(_key_by_condition_reaction(tables.core)) for mode, tables in loaded.items()}
    keys = sorted(set().union(*(set(mapping) for mapping in reaction_maps.values())))

    rows: list[dict[str, object]] = []
    for condition, reaction_id in keys:
        evidence = {mode: reaction_maps.get(mode, {}).get((condition, reaction_id), {}).get("evidence", "") for mode in modes}
        decisions = {mode: context_maps.get(mode, {}).get((condition, reaction_id), {}).get("decision", "") for mode in modes}
        core = {mode: (condition, reaction_id) in core_sets.get(mode, set()) for mode in modes}
        available_modes = [mode for mode in modes if evidence.get(mode)]
        evidence_change = _has_change(evidence.values())
        decision_change = _has_change(decisions.values())
        core_change = len({core[mode] for mode in available_modes}) > 1
        if not (evidence_change or decision_change or core_change):
            continue

        source_row = _first_row(reaction_maps, modes, (condition, reaction_id))
        status = classify_delta_status(evidence, decisions, core)
        rows.append(
            {
                "condition": condition,
                "reaction_id": reaction_id,
                "cobra_reaction_id": source_row.get("cobra_reaction_id", ""),
                "reaction_name": source_row.get("reaction_name", ""),
                **{f"{mode}_evidence": evidence.get(mode, "") for mode in modes},
                **{f"{mode}_decision": decisions.get(mode, "") for mode in modes},
                **{f"{mode}_core": core.get(mode, False) for mode in modes},
                "available_modes": ";".join(available_modes),
                "evidence_change": evidence_change,
                "decision_change": decision_change,
                "core_change": core_change,
                "delta_status": status,
                "recommendation": delta_recommendation(status),
            }
        )
    return rows


def summarize_reaction_deltas(
    reaction_delta_rows: list[dict[str, object]],
    loaded: dict[str, ModeTables],
    modes: tuple[str, ...] = EVIDENCE_MODES,
) -> list[dict[str, object]]:
    """Summarize reaction-level differences by condition."""

    conditions = sorted(
        set(row.get("condition") or "default" for row in reaction_delta_rows)
        | _all_conditions(loaded)
    )
    rows = [_summarize_delta_condition(condition, reaction_delta_rows, loaded, modes) for condition in conditions]
    rows.append(_summarize_delta_condition("ALL", reaction_delta_rows, loaded, modes))
    return rows


def build_evidence_mode_recommendations(delta_summary_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Create compact interpretation notes for evidence-mode differences."""

    rows: list[dict[str, object]] = []
    for summary in delta_summary_rows:
        condition = summary["condition"]
        if summary["condition"] == "ALL":
            continue
        if int(summary["relative_proteomics_missing_reaction_count"]) > 0:
            rows.append(
                {
                    "condition": condition,
                    "severity": "medium",
                    "topic": "mode_coverage",
                    "recommendation": "Relative proteomics is unavailable for this condition; consensus evidence will mostly follow available modalities.",
                }
            )
        if int(summary["conflict_softened_count"]) > 0:
            rows.append(
                {
                    "condition": condition,
                    "severity": "high",
                    "topic": "multi_omics_conflict",
                    "recommendation": "Consensus softened high/low modality conflicts; avoid hard keep/delete decisions for these reactions without biological review.",
                }
            )
        if int(summary["core_change_count"]) > 0:
            rows.append(
                {
                    "condition": condition,
                    "severity": "medium",
                    "topic": "context_reconstruction",
                    "recommendation": "FASTcore core candidates differ between evidence modes; compare reconstructed context models before interpreting phenotype-specific deletions.",
                }
            )
        if int(summary.get("ml_consensus_disagreement_count", 0)) > 0:
            rows.append(
                {
                    "condition": condition,
                    "severity": "medium",
                    "topic": "ml_evidence",
                    "recommendation": "ML-derived priors disagree with consensus for some reactions; use these as review hypotheses, not hard constraints.",
                }
            )
        if int(summary["reaction_delta_count"]) == 0:
            rows.append(
                {
                    "condition": condition,
                    "severity": "info",
                    "topic": "mode_agreement",
                    "recommendation": "Evidence modes produce the same downstream inputs for comparable reactions in this condition.",
                }
            )
    return rows


def classify_delta_status(
    evidence: dict[str, str],
    decisions: dict[str, str],
    core: dict[str, bool],
) -> str:
    """Classify why a reaction differs across evidence modes."""

    transcript = evidence.get("transcriptomics", "")
    protein = evidence.get("relative_proteomics", "")
    consensus = evidence.get("consensus", "")
    ml = evidence.get("ml_derived", "")
    if {transcript, protein} == {"high", "low"} and consensus == "medium":
        return "conflict_softened_by_consensus"
    if ml in {"high", "low"} and consensus in {"high", "low"} and ml != consensus:
        return "ml_consensus_disagreement"
    if ml and not consensus:
        return "ml_soft_prior_added"
    if decisions.get("transcriptomics") == "delete_candidate" and decisions.get("consensus") != "delete_candidate":
        return "delete_candidate_softened"
    if core.get("transcriptomics") != core.get("consensus"):
        return "core_membership_changed"
    if _has_change(evidence.values()):
        return "evidence_changed"
    if _has_change(decisions.values()):
        return "context_decision_changed"
    return "core_membership_changed"


def delta_recommendation(status: str) -> str:
    """Return a short recommendation for a reaction-level delta."""

    return {
        "conflict_softened_by_consensus": "Review before hard keep/delete; consensus treats this as medium support.",
        "delete_candidate_softened": "Consensus removed a transcript-only deletion candidate; prefer guidance-level interpretation.",
        "core_membership_changed": "Core status changed; compare FASTcore reconstruction outputs for this reaction.",
        "ml_consensus_disagreement": "ML-derived soft evidence disagrees with consensus; treat as hypothesis for review rather than a direct edit.",
        "ml_soft_prior_added": "ML-derived soft evidence is available without consensus support; keep it exploratory.",
        "evidence_changed": "Evidence tier changed between modes; inspect source omics coverage.",
        "context_decision_changed": "Context policy changed between modes; avoid treating one mode as definitive.",
    }.get(status, "Inspect mode-specific evidence before interpretation.")


def _summarize_delta_condition(
    condition: str,
    rows: list[dict[str, object]],
    loaded: dict[str, ModeTables],
    modes: tuple[str, ...],
) -> dict[str, object]:
    condition_rows = rows if condition == "ALL" else [row for row in rows if row.get("condition") == condition]
    return {
        "condition": condition,
        "reaction_delta_count": len(condition_rows),
        "evidence_change_count": _count_truthy(condition_rows, "evidence_change"),
        "decision_change_count": _count_truthy(condition_rows, "decision_change"),
        "core_change_count": _count_truthy(condition_rows, "core_change"),
        "conflict_softened_count": _count_value(condition_rows, "delta_status", "conflict_softened_by_consensus"),
        "delete_candidate_softened_count": _count_value(condition_rows, "delta_status", "delete_candidate_softened"),
        "ml_consensus_disagreement_count": _count_value(condition_rows, "delta_status", "ml_consensus_disagreement"),
        "ml_soft_prior_added_count": _count_value(condition_rows, "delta_status", "ml_soft_prior_added"),
        "relative_proteomics_missing_reaction_count": _missing_mode_count(loaded, condition, "relative_proteomics", modes),
        "status": "summary",
    }


def _missing_mode_count(
    loaded: dict[str, ModeTables],
    condition: str,
    missing_mode: str,
    modes: tuple[str, ...],
) -> int:
    reference_modes = [mode for mode in modes if mode != missing_mode]
    missing_keys = set(_key_by_condition_reaction(loaded.get(missing_mode, ModeTables([], [], [])).reactions))
    reference_keys = set().union(
        *[
            set(_key_by_condition_reaction(loaded.get(mode, ModeTables([], [], [])).reactions))
            for mode in reference_modes
        ]
    )
    if condition != "ALL":
        reference_keys = {key for key in reference_keys if key[0] == condition}
        missing_keys = {key for key in missing_keys if key[0] == condition}
    return len(reference_keys - missing_keys)


def _rows_for_condition(rows: list[dict[str, str]], condition: str) -> list[dict[str, str]]:
    if condition == "ALL":
        return rows
    return [row for row in rows if (row.get("condition") or "default") == condition]


def _key_by_condition_reaction(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    return {
        (row.get("condition") or "default", row.get("reaction_id") or row.get("cobra_reaction_id") or ""): row
        for row in rows
        if row.get("reaction_id") or row.get("cobra_reaction_id")
    }


def _all_conditions(loaded: dict[str, ModeTables]) -> set[str]:
    conditions = set()
    for tables in loaded.values():
        for row in tables.reactions + tables.context + tables.core:
            conditions.add(row.get("condition") or "default")
    return conditions


def _first_row(
    reaction_maps: dict[str, dict[tuple[str, str], dict[str, str]]],
    modes: tuple[str, ...],
    key: tuple[str, str],
) -> dict[str, str]:
    for mode in modes:
        row = reaction_maps.get(mode, {}).get(key)
        if row:
            return row
    return {}


def _has_change(values) -> bool:
    meaningful = {value for value in values if value not in {"", None, "unknown", "no_gpr"}}
    return len(meaningful) > 1


def _read_optional(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return read_csv_records(path)


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


def _count_truthy(rows: list[dict[str, object]], key: str) -> int:
    return sum(1 for row in rows if row.get(key) is True or str(row.get(key)).lower() == "true")


def _count_value(rows: list[dict[str, object]], key: str, value: str) -> int:
    return sum(1 for row in rows if row.get(key) == value)
