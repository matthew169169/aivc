"""Merge user, database, ML, and DLKcat kcat priors into one ranked table."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constraints import build_kcat_prior_table, parse_sbml_index, read_csv_records, write_csv, write_json


KCAT_PRIOR_SCHEMA_VERSION = "0.2.0"
KCAT_CONFLICT_CAUTION_RATIO = 3.0
KCAT_CONFLICT_REVIEW_RATIO = 10.0
TIER_RANKS = {
    "experimental": 100,
    "curated_database": 90,
    "organism_database": 80,
    "homology_database": 70,
    "user_supplied_unspecified": 65,
    "dlkcat_predicted": 50,
    "ml_predicted": 40,
    "fallback": 10,
}
DEFAULT_CONFIDENCE = {
    "experimental": 0.95,
    "curated_database": 0.85,
    "organism_database": 0.8,
    "homology_database": 0.65,
    "user_supplied_unspecified": 0.6,
    "dlkcat_predicted": 0.5,
    "ml_predicted": 0.4,
    "fallback": 0.1,
}


@dataclass(slots=True)
class KcatPriorMergeResult:
    """Summary returned by the kcat prior merge workflow."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]


def run_kcat_prior_merge(
    package_dir: str | Path,
    model_path: str | Path,
    output_dir: str | Path,
    dlkcat_results_dir: str | Path | None = None,
) -> KcatPriorMergeResult:
    """Merge uploaded kcat priors with DLKcat-derived kcat priors."""

    package = Path(package_dir)
    output = Path(output_dir)
    dlkcat_dir = Path(dlkcat_results_dir) if dlkcat_results_dir else package / "dlkcat_results"
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "selected_priors": str(output / "kcat_priors.csv"),
        "candidates": str(output / "kcat_prior_candidates.csv"),
        "conflict_flags": str(output / "kcat_conflict_flags.csv"),
        "summary": str(output / "kcat_prior_merge_summary.csv"),
        "manifest": str(output / "kcat_prior_merge_manifest.json"),
    }

    model_index = parse_sbml_index(model_path)
    candidates = collect_kcat_prior_candidates(package, model_index)
    candidates.extend(collect_dlkcat_candidates(dlkcat_dir))
    ranked_candidates = rank_kcat_candidates(candidates)
    selected = select_best_kcat_priors(ranked_candidates)
    conflict_flags = build_kcat_conflict_flags(ranked_candidates, selected)
    selected = annotate_selected_kcat_conflicts(selected, conflict_flags)
    summary = summarize_kcat_merge(ranked_candidates, selected, conflict_flags)

    write_csv(files["candidates"], ranked_candidates)
    write_csv(files["selected_priors"], selected)
    write_csv(files["conflict_flags"], conflict_flags)
    write_csv(files["summary"], summary)
    write_json(
        files["manifest"],
        {
            "schema_version": KCAT_PRIOR_SCHEMA_VERSION,
            "status": summary[0]["status"] if summary else "no_candidates",
            "package_dir": str(package),
            "model_path": str(model_path),
            "dlkcat_results_dir": str(dlkcat_dir),
            "files": files,
            "summary": summary[0] if summary else {},
        },
    )
    status = "completed" if selected else "skipped"
    message = (
        f"Merged {len(ranked_candidates)} kcat candidates into {len(selected)} selected priors."
        if selected
        else "No kcat prior candidates were available."
    )
    return KcatPriorMergeResult(status=status, output_dir=str(output), message=message, files=files)


def collect_kcat_prior_candidates(package_dir: Path, model_index: Any) -> list[dict[str, object]]:
    """Collect user-uploaded kcat/ML prior tables from a staged package."""

    candidates: list[dict[str, object]] = []
    seen_paths: set[str] = set()
    for row in package_sources(package_dir):
        if row.get("role") != "ml_priors":
            continue
        path_text = str(row.get("path", "") or "")
        source = Path(path_text) if path_text else Path("")
        if (not path_text or not source.exists()) and row.get("relative_path"):
            source = package_dir / str(row.get("relative_path", ""))
        if not path_text and not row.get("relative_path"):
            continue
        if not source.exists() or source.is_dir() or str(source) in seen_paths:
            continue
        seen_paths.add(str(source))
        for normalized in build_kcat_prior_table(source, model_index=model_index):
            if not normalized.get("model_target_id") or normalized.get("target_type") != "reaction":
                continue
            candidate = dict(normalized)
            candidate["original_source"] = "uploaded_ml_priors"
            candidate["source_file"] = str(source)
            candidates.append(candidate)
    return candidates


def collect_dlkcat_candidates(dlkcat_results_dir: Path) -> list[dict[str, object]]:
    """Collect DLKcat-derived kcat priors when available."""

    path = dlkcat_results_dir / "dlkcat_reaction_kcat_priors.csv"
    if not path.exists() or path.stat().st_size == 0:
        return []
    candidates: list[dict[str, object]] = []
    for row in read_csv_records(path):
        candidate = dict(row)
        candidate["original_source"] = "dlkcat_bridge"
        candidate["source_file"] = str(path)
        candidate["source_tier"] = candidate.get("source_tier") or "dlkcat_predicted"
        candidate["target_type"] = candidate.get("target_type") or "reaction"
        candidates.append(candidate)
    return candidates


def rank_kcat_candidates(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Add evidence tiers, ranks, and normalized confidence to candidate rows."""

    ranked: list[dict[str, object]] = []
    for row in rows:
        kcat = to_float(row.get("kcat") or row.get("value"))
        unit = str(row.get("unit", "") or "per_s")
        if kcat is None or not row.get("model_target_id"):
            continue
        evidence_tier = classify_kcat_evidence_tier(row)
        confidence = to_float(row.get("confidence"))
        if confidence is None:
            confidence = DEFAULT_CONFIDENCE.get(evidence_tier, 0.5)
        ranked.append(
            {
                "target_id": row.get("target_id", ""),
                "target_type": row.get("target_type", "reaction"),
                "model_target_id": row.get("model_target_id", ""),
                "kcat": kcat,
                "unit": unit,
                "confidence": confidence,
                "source_tier": row.get("source_tier", ""),
                "kcat_evidence_tier": evidence_tier,
                "kcat_evidence_rank": TIER_RANKS.get(evidence_tier, 0),
                "original_source": row.get("original_source", ""),
                "source_file": row.get("source_file", ""),
                "status": row.get("status", ""),
                "selection_status": "",
                "gene_id": row.get("gene_id", ""),
                "substrate_id": row.get("substrate_id", ""),
                "substrate_name": row.get("substrate_name", ""),
                "source_query_id": row.get("source_query_id", ""),
                "note": row.get("note", ""),
            }
        )
    return ranked


def select_best_kcat_priors(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Select one best kcat prior per model reaction."""

    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("model_target_id", "")), []).append(row)
    selected: list[dict[str, object]] = []
    selected_keys: set[tuple[str, str, float]] = set()
    for reaction_id, reaction_rows in sorted(grouped.items()):
        best = sorted(
            reaction_rows,
            key=lambda row: (
                int(row.get("kcat_evidence_rank") or 0),
                float(row.get("confidence") or 0),
                float(row.get("kcat") or 0),
            ),
            reverse=True,
        )[0]
        selected_row = dict(best)
        selected_row["selection_status"] = "selected"
        selected.append(selected_row)
        selected_keys.add((reaction_id, str(best.get("source_file", "")), float(best.get("kcat") or 0)))
    for row in rows:
        key = (str(row.get("model_target_id", "")), str(row.get("source_file", "")), float(row.get("kcat") or 0))
        row["selection_status"] = "selected" if key in selected_keys else "superseded_by_higher_evidence"
    return selected


def build_kcat_conflict_flags(
    candidates: list[dict[str, object]],
    selected: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Flag reactions where kcat candidates disagree by large fold ranges."""

    selected_by_reaction = {str(row.get("model_target_id", "")): row for row in selected}
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in candidates:
        reaction_id = str(row.get("model_target_id", ""))
        if reaction_id:
            grouped.setdefault(reaction_id, []).append(row)

    rows: list[dict[str, object]] = []
    for reaction_id, reaction_rows in sorted(grouped.items()):
        per_s_rows = [
            row
            for row in reaction_rows
            if str(row.get("unit") or "per_s") == "per_s" and (to_float(row.get("kcat")) or 0.0) > 0
        ]
        values = sorted(float(row.get("kcat") or 0) for row in per_s_rows)
        selected_row = selected_by_reaction.get(reaction_id, {})
        min_value = values[0] if values else None
        max_value = values[-1] if values else None
        min_row = min(per_s_rows, key=lambda row: float(row.get("kcat") or 0), default={})
        max_row = max(per_s_rows, key=lambda row: float(row.get("kcat") or 0), default={})
        fold_range = (max_value / min_value) if min_value and max_value else None
        flag, severity, status = classify_kcat_conflict(len(reaction_rows), len(values), fold_range)
        rows.append(
            {
                "model_target_id": reaction_id,
                "target_id": selected_row.get("target_id", reaction_id),
                "candidate_count": len(reaction_rows),
                "positive_candidate_count": len(values),
                "min_kcat_per_s": min_value,
                "max_kcat_per_s": max_value,
                "min_candidate_evidence_tier": min_row.get("kcat_evidence_tier", ""),
                "min_candidate_source_tier": min_row.get("source_tier", ""),
                "min_candidate_original_source": min_row.get("original_source", ""),
                "max_candidate_evidence_tier": max_row.get("kcat_evidence_tier", ""),
                "max_candidate_source_tier": max_row.get("source_tier", ""),
                "max_candidate_original_source": max_row.get("original_source", ""),
                "fold_range": round(fold_range, 6) if fold_range is not None else "",
                "log10_range": round(_log10(fold_range), 6) if fold_range is not None else "",
                "selected_kcat_per_s": selected_row.get("kcat", ""),
                "selected_kcat_evidence_tier": selected_row.get("kcat_evidence_tier", ""),
                "selected_source_tier": selected_row.get("source_tier", ""),
                "flag": flag,
                "severity": severity,
                "status": status,
                "guidance": kcat_conflict_guidance(flag, fold_range),
            }
        )
    return rows


def filter_kcat_conflict_rows(
    rows: list[dict[str, object]],
    selected_flags: list[str] | set[str] | tuple[str, ...] | None = None,
    selected_tiers: list[str] | set[str] | tuple[str, ...] | None = None,
) -> list[dict[str, object]]:
    """Filter kcat conflict rows by flag and selected kcat evidence tier."""

    flag_set = {str(flag) for flag in selected_flags or [] if str(flag)}
    tier_set = {str(tier) for tier in selected_tiers or [] if str(tier)}
    filtered = []
    for row in rows:
        if flag_set and str(row.get("flag", "")) not in flag_set:
            continue
        tier = str(row.get("selected_kcat_evidence_tier") or row.get("kcat_evidence_tier", ""))
        if tier_set and tier not in tier_set:
            continue
        filtered.append(row)
    return filtered


def build_kcat_conflict_drilldown(
    reaction_id: str,
    conflict_rows: list[dict[str, object]],
    candidate_rows: list[dict[str, object]],
    selected_rows: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    """Return conflict, selected, candidate, and min/max source rows for one reaction."""

    normalized = normalize_reaction_id(reaction_id)
    selected_rows = selected_rows or []
    matched_conflicts = [row for row in conflict_rows if row_matches_reaction(row, normalized)]
    matched_candidates = [row for row in candidate_rows if row_matches_reaction(row, normalized)]
    matched_selected = [row for row in selected_rows if row_matches_reaction(row, normalized)]
    sorted_candidates = sorted(
        matched_candidates,
        key=lambda row: (to_float(row.get("kcat")) is None, to_float(row.get("kcat")) or 0.0),
    )
    numeric_candidates = [row for row in sorted_candidates if to_float(row.get("kcat")) is not None]
    extreme_rows: list[dict[str, object]] = []
    if numeric_candidates:
        min_row = numeric_candidates[0]
        max_row = numeric_candidates[-1]
        extreme_rows = [
            kcat_extreme_row("min_kcat", min_row),
            kcat_extreme_row("max_kcat", max_row),
        ]
    explanation_rows = [
        build_kcat_conflict_explanation_row(matched_conflicts[0], extreme_rows)
    ] if matched_conflicts else []
    return {
        "query": reaction_id,
        "normalized_reaction_id": normalized,
        "conflict_rows": matched_conflicts,
        "selected_rows": matched_selected,
        "candidate_rows": sorted_candidates,
        "extreme_rows": extreme_rows,
        "explanation_rows": explanation_rows,
    }


def build_kcat_conflict_explanation_row(
    conflict: dict[str, object],
    extreme_rows: list[dict[str, object]],
) -> dict[str, object]:
    """Build a compact human-facing explanation row for kcat conflict drill-down."""

    min_row = next((row for row in extreme_rows if row.get("extreme") == "min_kcat"), {})
    max_row = next((row for row in extreme_rows if row.get("extreme") == "max_kcat"), {})
    return {
        "model_target_id": conflict.get("model_target_id", ""),
        "flag": conflict.get("flag", ""),
        "severity": conflict.get("severity", ""),
        "fold_range": conflict.get("fold_range", ""),
        "min_kcat_per_s": conflict.get("min_kcat_per_s", min_row.get("kcat", "")),
        "min_source": min_row.get("original_source", conflict.get("min_candidate_original_source", "")),
        "min_evidence_tier": min_row.get("kcat_evidence_tier", conflict.get("min_candidate_evidence_tier", "")),
        "max_kcat_per_s": conflict.get("max_kcat_per_s", max_row.get("kcat", "")),
        "max_source": max_row.get("original_source", conflict.get("max_candidate_original_source", "")),
        "max_evidence_tier": max_row.get("kcat_evidence_tier", conflict.get("max_candidate_evidence_tier", "")),
        "selected_kcat_per_s": conflict.get("selected_kcat_per_s", ""),
        "selected_kcat_evidence_tier": conflict.get("selected_kcat_evidence_tier", ""),
        "guidance": conflict.get("guidance", ""),
    }


def kcat_extreme_row(extreme: str, row: dict[str, object]) -> dict[str, object]:
    """Return selected columns for a min/max kcat candidate."""

    return {
        "extreme": extreme,
        "model_target_id": row.get("model_target_id", ""),
        "target_id": row.get("target_id", ""),
        "kcat": row.get("kcat", ""),
        "unit": row.get("unit", ""),
        "confidence": row.get("confidence", ""),
        "kcat_evidence_tier": row.get("kcat_evidence_tier", ""),
        "source_tier": row.get("source_tier", ""),
        "original_source": row.get("original_source", ""),
        "selection_status": row.get("selection_status", ""),
        "source_query_id": row.get("source_query_id", ""),
        "gene_id": row.get("gene_id", ""),
        "substrate_name": row.get("substrate_name", ""),
    }


def annotate_selected_kcat_conflicts(
    selected: list[dict[str, object]],
    conflict_flags: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Add conflict fields to selected kcat priors for downstream gates."""

    flag_index = {str(row.get("model_target_id", "")): row for row in conflict_flags}
    rows = []
    for row in selected:
        conflict = flag_index.get(str(row.get("model_target_id", "")), {})
        rows.append(
            {
                **row,
                "kcat_conflict_flag": conflict.get("flag", ""),
                "kcat_conflict_severity": conflict.get("severity", ""),
                "kcat_fold_range": conflict.get("fold_range", ""),
                "kcat_conflict_guidance": conflict.get("guidance", ""),
            }
        )
    return rows


def classify_kcat_conflict(
    candidate_count: int,
    positive_candidate_count: int,
    fold_range: float | None,
) -> tuple[str, str, str]:
    """Classify within-reaction kcat candidate spread."""

    if candidate_count <= 1:
        return "single_kcat_candidate", "info", "usable"
    if positive_candidate_count < 2 or fold_range is None:
        return "insufficient_numeric_kcat_candidates", "low", "inconclusive"
    if fold_range >= KCAT_CONFLICT_REVIEW_RATIO:
        return "kcat_conflict_review", "high", "review_required"
    if fold_range >= KCAT_CONFLICT_CAUTION_RATIO:
        return "kcat_spread_caution", "medium", "usable_with_caution"
    return "kcat_candidates_consistent", "info", "usable"


def kcat_conflict_guidance(flag: str, fold_range: float | None) -> str:
    """Return concise guidance for kcat conflict flags."""

    if flag == "kcat_conflict_review":
        return f"kcat candidates differ by {fold_range:.2f}-fold; review source, substrate, organism, and unit assumptions before using this target."
    if flag == "kcat_spread_caution":
        return f"kcat candidates differ by {fold_range:.2f}-fold; use the selected kcat as caution-tier evidence."
    if flag == "kcat_candidates_consistent":
        return "Multiple kcat candidates are broadly consistent for this reaction."
    if flag == "single_kcat_candidate":
        return "Only one kcat candidate is available; no within-reaction conflict can be assessed."
    return "Numeric kcat candidates are insufficient for conflict assessment."


def summarize_kcat_merge(
    candidates: list[dict[str, object]],
    selected: list[dict[str, object]],
    conflict_flags: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    """Summarize merged kcat prior evidence tiers."""

    conflict_flags = conflict_flags or []
    tier_counts: dict[str, int] = {}
    selected_tier_counts: dict[str, int] = {}
    for row in candidates:
        tier = str(row.get("kcat_evidence_tier", ""))
        tier_counts[tier] = tier_counts.get(tier, 0) + 1
    for row in selected:
        tier = str(row.get("kcat_evidence_tier", ""))
        selected_tier_counts[tier] = selected_tier_counts.get(tier, 0) + 1
    return [
        {
            "status": "merged" if selected else "no_kcat_candidates",
            "candidate_count": len(candidates),
            "selected_prior_count": len(selected),
            "experimental_candidate_count": tier_counts.get("experimental", 0),
            "database_candidate_count": sum(
                tier_counts.get(tier, 0)
                for tier in ["curated_database", "organism_database", "homology_database"]
            ),
            "dlkcat_candidate_count": tier_counts.get("dlkcat_predicted", 0),
            "ml_candidate_count": tier_counts.get("ml_predicted", 0),
            "selected_experimental_count": selected_tier_counts.get("experimental", 0),
            "selected_database_count": sum(
                selected_tier_counts.get(tier, 0)
                for tier in ["curated_database", "organism_database", "homology_database"]
            ),
            "selected_dlkcat_count": selected_tier_counts.get("dlkcat_predicted", 0),
            "selected_ml_count": selected_tier_counts.get("ml_predicted", 0),
            "kcat_conflict_review_count": sum(1 for row in conflict_flags if row.get("flag") == "kcat_conflict_review"),
            "kcat_spread_caution_count": sum(1 for row in conflict_flags if row.get("flag") == "kcat_spread_caution"),
            "guidance": kcat_merge_guidance(selected_tier_counts, conflict_flags),
        }
    ]


def classify_kcat_evidence_tier(row: dict[str, object]) -> str:
    """Classify evidence quality from source tier and origin text."""

    source_text = " ".join(
        str(row.get(key, "")).lower()
        for key in ["source_tier", "original_source", "note", "source_file"]
    )
    if "dlkcat" in source_text:
        return "dlkcat_predicted"
    if "experimental" in source_text or "exp" == str(row.get("source_tier", "")).lower():
        return "experimental"
    if any(token in source_text for token in ["brenda", "sabio", "sabiork", "kegg", "curated"]):
        return "curated_database"
    if "organism" in source_text:
        return "organism_database"
    if any(token in source_text for token in ["homolog", "homology", "ortholog"]):
        return "homology_database"
    if any(token in source_text for token in ["ml", "machine", "predicted", "prediction"]):
        return "ml_predicted"
    if "fallback" in source_text or "default" in source_text:
        return "fallback"
    return "user_supplied_unspecified"


def kcat_merge_guidance(
    selected_tier_counts: dict[str, int],
    conflict_flags: list[dict[str, object]] | None = None,
) -> str:
    """Return concise guidance for reports and UI."""

    conflict_flags = conflict_flags or []
    if any(row.get("flag") == "kcat_conflict_review" for row in conflict_flags):
        return "Some reactions have high kcat candidate conflicts; review conflict flags before enzyme-constrained or hybrid interpretation."
    if any(row.get("flag") == "kcat_spread_caution" for row in conflict_flags):
        return "Some reactions have moderate kcat spread; treat selected priors as cautionary where flagged."
    if selected_tier_counts.get("experimental", 0):
        return "Experimental kcat values are available; keep predicted values as lower-tier supplements."
    if any(selected_tier_counts.get(tier, 0) for tier in ["curated_database", "organism_database", "homology_database"]):
        return "Database kcat values are available; review organism and substrate specificity before production ecGEM use."
    if selected_tier_counts.get("dlkcat_predicted", 0):
        return "Selected kcat priors are mainly DLKcat predictions; use them as provisional enzyme constraints."
    if selected_tier_counts.get("ml_predicted", 0):
        return "Selected kcat priors are ML-derived and should be treated as guidance."
    return "No selected kcat priors are available."


def package_sources(package_dir: Path) -> list[dict[str, str]]:
    """Return staged package source rows from normalized and raw input maps."""

    rows: list[dict[str, str]] = []
    for map_path in [package_dir / "normalized_inputs" / "normalized_input_map.csv", package_dir / "input_file_map.csv"]:
        if map_path.exists() and map_path.stat().st_size > 0:
            rows.extend(read_csv_records(map_path))
    return rows


def row_matches_reaction(row: dict[str, object], normalized_reaction_id: str) -> bool:
    row_ids = {
        normalize_reaction_id(row.get("model_target_id", "")),
        normalize_reaction_id(row.get("target_id", "")),
        normalize_reaction_id(row.get("reaction_id", "")),
    }
    return normalized_reaction_id in row_ids


def normalize_reaction_id(reaction_id: object) -> str:
    text = str(reaction_id or "").strip().lower()
    if text.startswith("r_"):
        text = text[2:]
    return text


def to_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _log10(value: float | None) -> float:
    if value is None or value <= 0:
        return 0.0
    import math

    return math.log10(value)
