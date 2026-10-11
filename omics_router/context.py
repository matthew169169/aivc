"""Lightweight context-specific reaction policy generation."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from .constraints import read_csv_records


def build_context_reaction_policy(
    reaction_evidence_csv: str | Path,
    protected_reactions: set[str] | None = None,
) -> list[dict[str, object]]:
    """Convert reaction evidence into a transparent context policy table.

    This is not a replacement for iMAT/FASTCORE/CORDA. It is a conservative
    pre-run layer that labels reactions as keep/support/penalize/delete
    candidates while protecting objectives and measured exchange reactions.
    """

    protected = {_normalize_reaction_id(reaction) for reaction in (protected_reactions or set())}
    rows: list[dict[str, object]] = []
    for row in read_csv_records(reaction_evidence_csv):
        reaction_id = row.get("reaction_id", "")
        cobra_reaction_id = row.get("cobra_reaction_id", "")
        evidence = row.get("evidence", "")
        status = row.get("status", "")
        normalized_ids = {_normalize_reaction_id(reaction_id), _normalize_reaction_id(cobra_reaction_id)}

        if normalized_ids & protected:
            decision = "protect"
            reason = "objective_or_measured_exchange"
        elif evidence == "high":
            decision = "keep"
            reason = "high_expression_support"
        elif evidence == "medium":
            decision = "support"
            reason = "medium_expression_support"
        elif evidence == "low" and status == "complete_gene_coverage":
            decision = "delete_candidate"
            reason = "low_expression_complete_gpr"
        elif evidence == "low":
            decision = "penalize_candidate"
            reason = "low_expression_partial_gpr"
        else:
            decision = "neutral"
            reason = evidence or status or "unknown"

        rows.append(
            {
                "condition": row.get("condition", ""),
                "reaction_id": reaction_id,
                "cobra_reaction_id": cobra_reaction_id,
                "reaction_name": row.get("reaction_name", ""),
                "reaction_score": row.get("reaction_score", ""),
                "evidence": evidence,
                "gene_coverage": row.get("gene_coverage", ""),
                "gpr_status": status,
                "decision": decision,
                "reason": reason,
                "gpr_rule": row.get("gpr_rule", ""),
                "status": decision,
            }
        )
    return rows


def split_context_policy(policy_rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    """Create condition-specific retain/delete/helper lists."""

    keep_decisions = {"protect", "keep", "support"}
    delete_decisions = {"delete_candidate"}
    penalize_decisions = {"penalize_candidate"}

    return {
        "context_keep_reactions": _filter_policy(policy_rows, keep_decisions),
        "context_delete_candidates": _filter_policy(policy_rows, delete_decisions),
        "context_penalize_candidates": _filter_policy(policy_rows, penalize_decisions),
        "context_policy_summary": summarize_context_policy(policy_rows),
    }


def summarize_context_policy(policy_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Summarize context policy decisions by condition and overall."""

    by_condition: dict[str, list[dict[str, object]]] = {}
    for row in policy_rows:
        by_condition.setdefault(str(row.get("condition") or "default"), []).append(row)

    summary = [_summarize_one(condition, rows) for condition, rows in sorted(by_condition.items())]
    if policy_rows:
        summary.append(_summarize_one("ALL", policy_rows))
    return summary


def protected_reactions_from_outputs(
    objective_reactions: list[str] | None,
    exchange_bounds_rows: list[dict[str, object]] | None,
) -> set[str]:
    """Collect protected reactions from objectives and measured exchanges."""

    protected = set(objective_reactions or [])
    for row in exchange_bounds_rows or []:
        reaction_id = str(row.get("model_reaction_id") or row.get("reaction_id") or "")
        if reaction_id:
            protected.add(reaction_id)
    return protected


def _filter_policy(policy_rows: list[dict[str, object]], decisions: set[str]) -> list[dict[str, object]]:
    return [
        {
            "condition": row["condition"],
            "reaction_id": row["reaction_id"],
            "cobra_reaction_id": row["cobra_reaction_id"],
            "decision": row["decision"],
            "reason": row["reason"],
            "reaction_score": row["reaction_score"],
            "evidence": row["evidence"],
            "status": row["decision"],
        }
        for row in policy_rows
        if row.get("decision") in decisions
    ]


def _summarize_one(condition: str, rows: list[dict[str, object]]) -> dict[str, object]:
    counts = Counter(str(row.get("decision") or "unknown") for row in rows)
    return {
        "condition": condition,
        "reaction_count": len(rows),
        "protect": counts.get("protect", 0),
        "keep": counts.get("keep", 0),
        "support": counts.get("support", 0),
        "penalize_candidate": counts.get("penalize_candidate", 0),
        "delete_candidate": counts.get("delete_candidate", 0),
        "neutral": counts.get("neutral", 0),
        "status": "summary",
    }


def _normalize_reaction_id(reaction_id: str) -> str:
    text = str(reaction_id or "").strip()
    if text.startswith("R_"):
        text = text[2:]
    return text.lower()
