"""Readiness-aware target priors for ML + GEM hybrid prototypes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .constraints import read_csv_records, write_csv, write_json


READINESS_PRIOR_BASE = {
    "stronger_evidence": 0.95,
    "usable_with_caution": 0.6,
    "guidance_only": 0.25,
    "review_required": 0.0,
}
READINESS_SAMPLE_WEIGHT_BASE = {
    "stronger_evidence": 1.0,
    "usable_with_caution": 0.55,
    "guidance_only": 0.25,
    "review_required": 0.0,
}
READINESS_TARGET_LABEL = {
    "stronger_evidence": "stronger_evidence_target",
    "usable_with_caution": "caution_target",
    "guidance_only": "guidance_only_target",
    "review_required": "review_required_target",
}
UNIPROT_STRONG_LABELS = {"reviewed_ec_consistent", "reviewed_with_ec"}
UNIPROT_CAUTION_LABELS = {
    "annotation_missing",
    "cache_or_fetch_issue",
    "ec_available_review_unknown",
    "ec_consistent_unknown_review",
    "ec_consistent_unreviewed",
    "ec_missing_or_inconclusive",
    "reviewed_without_ec",
    "unreviewed_or_missing_ec",
    "unreviewed_with_ec",
}
ENZYME_SUPPORT_LABELS = {"enzyme_constrained_supported", "supported_by_gecko_or_ecfactory"}
ENZYME_CONFLICT_LABELS = {"action_conflict_review", "enzyme_constraint_blocks_cobra_target"}
KCAT_STRONG_LABELS = {"strong"}
KCAT_CAUTION_LABELS = {"caution"}
KCAT_REVIEW_LABELS = {"conflict_review"}


@dataclass(slots=True)
class ReadinessHybridExportResult:
    """Summary returned after writing readiness-aware hybrid target tables."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]
    summary_rows: list[dict[str, object]]


def run_readiness_hybrid_export(
    package_dir: str | Path,
    output_dir: str | Path | None = None,
) -> ReadinessHybridExportResult:
    """Export readiness labels as target priors, sample weights, and candidate labels."""

    package = Path(package_dir)
    output = Path(output_dir) if output_dir else package / "minn_export"
    output.mkdir(parents=True, exist_ok=True)
    files = readiness_hybrid_files(output)
    production_dir = package / "production_results"
    ml_results_dir = package / "ml_results"

    ml_prior_index = index_ml_priors(_read_optional(ml_results_dir / "ml_prior_scores.csv"))
    target_rows = build_readiness_target_prior_rows(
        target_readiness=_read_optional(production_dir / "production_target_readiness.csv"),
        design_readiness=_read_optional(production_dir / "production_design_readiness.csv"),
        gene_readiness=_read_optional(production_dir / "production_gene_readiness.csv"),
        ml_prior_index=ml_prior_index,
    )
    sample_weight_rows = build_readiness_sample_weight_rows(target_rows)
    summary_rows = [summarize_readiness_hybrid_export(target_rows, sample_weight_rows)]

    write_csv(files["summary"], summary_rows)
    write_csv(files["target_priors"], target_rows)
    write_csv(files["sample_weights"], sample_weight_rows)
    write_json(
        files["manifest"],
        {
            "schema_version": "0.1.0",
            "status": summary_rows[0]["status"],
            "package_dir": str(package),
            "target_prior_count": len(target_rows),
            "sample_weight_count": len(sample_weight_rows),
            "files": files,
        },
    )
    return ReadinessHybridExportResult(
        status="completed",
        output_dir=str(output),
        message=str(summary_rows[0]["guidance"]),
        files=files,
        summary_rows=summary_rows,
    )


def readiness_hybrid_files(output: Path) -> dict[str, str]:
    return {
        "summary": str(output / "minn_readiness_summary.csv"),
        "target_priors": str(output / "minn_readiness_target_priors.csv"),
        "sample_weights": str(output / "minn_readiness_sample_weights.csv"),
        "manifest": str(output / "minn_readiness_manifest.json"),
    }


def build_readiness_target_prior_rows(
    *,
    target_readiness: list[dict[str, str]],
    design_readiness: list[dict[str, str]],
    gene_readiness: list[dict[str, str]],
    ml_prior_index: dict[tuple[str, str], dict[str, str]] | None = None,
) -> list[dict[str, object]]:
    """Convert product/reaction/gene readiness rows into supervised target-prior rows."""

    ml_prior_index = ml_prior_index or {}
    rows: list[dict[str, object]] = []
    for row in target_readiness:
        target_id = str(row.get("model_product_reaction_id") or row.get("product_reaction_id", ""))
        if not target_id:
            continue
        rows.append(
            build_one_target_prior_row(
                row=row,
                source_table="production_target_readiness",
                target_level="product_reaction",
                target_id=target_id,
                node_id=canonical_reaction(target_id),
                recommended_action="product_target",
                ml_prior_index=ml_prior_index,
            )
        )
    for row in design_readiness:
        target_id = str(row.get("candidate_reaction_id", ""))
        if not target_id:
            continue
        rows.append(
            build_one_target_prior_row(
                row=row,
                source_table="production_design_readiness",
                target_level="reaction",
                target_id=target_id,
                node_id=canonical_reaction(target_id),
                recommended_action=str(row.get("recommended_action", "")),
                ml_prior_index=ml_prior_index,
            )
        )
    for row in gene_readiness:
        target_id = str(row.get("gene_id", ""))
        if not target_id:
            continue
        rows.append(
            build_one_target_prior_row(
                row=row,
                source_table="production_gene_readiness",
                target_level="gene",
                target_id=target_id,
                node_id=canonical_gene(target_id),
                recommended_action=str(row.get("recommended_action", "")),
                ml_prior_index=ml_prior_index,
            )
        )
    rows.sort(key=lambda item: (str(item.get("condition", "")), -float(item.get("sample_weight", 0)), str(item.get("target_level", "")), str(item.get("target_id", ""))))
    return rows


def build_one_target_prior_row(
    *,
    row: dict[str, str],
    source_table: str,
    target_level: str,
    target_id: str,
    node_id: str,
    recommended_action: str,
    ml_prior_index: dict[tuple[str, str], dict[str, str]],
) -> dict[str, object]:
    readiness_label = str(row.get("production_readiness_label", ""))
    ml_target_type = "reaction" if target_level in {"product_reaction", "reaction"} else "gene"
    ml_prior = ml_prior_index.get((ml_target_type, normalize_entity_id(target_id, ml_target_type)), {})
    readiness_prior_score = readiness_prior(readiness_label)
    kcat_adjustment = kcat_prior_adjustment(row)
    target_prior_score = round(clamp(readiness_prior_score + kcat_adjustment, 0.0, 1.0), 6)
    sample_weight = readiness_sample_weight(row)
    combined_score = combined_prior_score(readiness_label, target_prior_score, ml_prior)
    return {
        "condition": row.get("condition", ""),
        "target_level": target_level,
        "target_id": target_id,
        "model_target_id": target_id,
        "node_id": node_id,
        "product_reaction_id": row.get("product_reaction_id", ""),
        "recommended_action": recommended_action,
        "candidate_target_label": candidate_target_label(readiness_label),
        "readiness_prior_score": readiness_prior_score,
        "kcat_prior_adjustment": kcat_adjustment,
        "target_prior_score": target_prior_score,
        "combined_target_prior_score": combined_score,
        "sample_weight": sample_weight,
        "production_readiness_label": readiness_label,
        "readiness_score": row.get("readiness_score", ""),
        "readiness_reasons": row.get("readiness_reasons", ""),
        "semantic_readiness_label": row.get("semantic_readiness_label", ""),
        "uniprot_evidence_label": row.get("uniprot_evidence_label", ""),
        "uniprot_reviewed_status": row.get("uniprot_reviewed_status", ""),
        "uniprot_ec_status": row.get("uniprot_ec_status", ""),
        "uniprot_cache_status": row.get("uniprot_cache_status", ""),
        "enzyme_constraint_label": row.get("enzyme_constraint_label", ""),
        "kcat_evidence_tier": row.get("kcat_evidence_tier", ""),
        "kcat_evidence_label": row.get("kcat_evidence_label", ""),
        "kcat_value_per_s": row.get("kcat_value_per_s", ""),
        "kcat_confidence": row.get("kcat_confidence", ""),
        "kcat_matched_reactions": row.get("kcat_matched_reactions", ""),
        "kcat_conflict_flag": row.get("kcat_conflict_flag", ""),
        "kcat_conflict_severity": row.get("kcat_conflict_severity", ""),
        "kcat_fold_range": row.get("kcat_fold_range", ""),
        "ml_prior_score": ml_prior.get("score", ""),
        "ml_abs_score": ml_prior.get("abs_score", ""),
        "ml_evidence": ml_prior.get("ml_evidence", ""),
        "ml_context_action": ml_prior.get("context_action", ""),
        "ml_sample_status": ml_prior.get("sample_status", ""),
        "source_table": source_table,
        "training_role": training_role(target_level, readiness_label),
        "status": target_prior_status(readiness_label, sample_weight),
        "guidance": target_prior_guidance(readiness_label, row, bool(ml_prior)),
    }


def build_readiness_sample_weight_rows(target_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Build a compact table that can be used directly as supervised sample weights."""

    rows: list[dict[str, object]] = []
    for row in target_rows:
        rows.append(
            {
                "condition": row.get("condition", ""),
                "target_level": row.get("target_level", ""),
                "target_id": row.get("target_id", ""),
                "node_id": row.get("node_id", ""),
                "candidate_target_label": row.get("candidate_target_label", ""),
                "sample_weight": row.get("sample_weight", ""),
                "combined_target_prior_score": row.get("combined_target_prior_score", ""),
                "production_readiness_label": row.get("production_readiness_label", ""),
                "kcat_evidence_label": row.get("kcat_evidence_label", ""),
                "kcat_evidence_tier": row.get("kcat_evidence_tier", ""),
                "kcat_conflict_flag": row.get("kcat_conflict_flag", ""),
                "ml_abs_score": row.get("ml_abs_score", ""),
                "weight_reason": weight_reason(row),
                "status": "sample_weight_available" if _to_float(row.get("sample_weight")) is not None else "sample_weight_missing",
            }
        )
    return rows


def summarize_readiness_hybrid_export(
    target_rows: list[dict[str, object]],
    sample_weight_rows: list[dict[str, object]],
) -> dict[str, object]:
    labels = _count_by(target_rows, "production_readiness_label")
    uniprot_labels = _count_by(target_rows, "uniprot_evidence_label")
    kcat_labels = _count_by(target_rows, "kcat_evidence_label")
    kcat_conflicts = _count_by(target_rows, "kcat_conflict_flag")
    status = "completed" if target_rows else "skipped_no_readiness_rows"
    return {
        "status": status,
        "target_prior_count": len(target_rows),
        "sample_weight_count": len(sample_weight_rows),
        "stronger_evidence_target_count": labels.get("stronger_evidence", 0),
        "usable_with_caution_target_count": labels.get("usable_with_caution", 0),
        "guidance_only_target_count": labels.get("guidance_only", 0),
        "review_required_target_count": labels.get("review_required", 0),
        "ml_prior_matched_count": sum(1 for row in target_rows if row.get("ml_abs_score") not in {"", None}),
        "uniprot_strong_target_count": sum(uniprot_labels.get(label, 0) for label in UNIPROT_STRONG_LABELS),
        "uniprot_caution_target_count": sum(uniprot_labels.get(label, 0) for label in UNIPROT_CAUTION_LABELS),
        "kcat_strong_target_count": sum(kcat_labels.get(label, 0) for label in KCAT_STRONG_LABELS),
        "kcat_caution_target_count": sum(kcat_labels.get(label, 0) for label in KCAT_CAUTION_LABELS),
        "kcat_conflict_review_target_count": sum(kcat_labels.get(label, 0) for label in KCAT_REVIEW_LABELS),
        "kcat_spread_caution_target_count": kcat_conflicts.get("kcat_spread_caution", 0),
        "kcat_missing_target_count": kcat_labels.get("not_available", 0),
        "training_candidate_count": sum(1 for row in target_rows if _to_float(row.get("sample_weight")) and str(row.get("production_readiness_label")) != "review_required"),
        "guidance": readiness_hybrid_guidance(target_rows),
    }


def index_ml_priors(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    index: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        target_type = str(row.get("target_type") or row.get("entity_type", ""))
        if target_type not in {"gene", "reaction"}:
            continue
        target_id = str(row.get("model_target_id") or row.get("target_id") or row.get("entity_id", ""))
        key = (target_type, normalize_entity_id(target_id, target_type))
        current = index.get(key)
        if current is None or (_to_float(row.get("abs_score")) or 0.0) > (_to_float(current.get("abs_score")) or 0.0):
            index[key] = row
    return index


def readiness_prior(readiness_label: str) -> float:
    return READINESS_PRIOR_BASE.get(readiness_label, 0.2)


def readiness_sample_weight(row: dict[str, str]) -> float:
    readiness_label = str(row.get("production_readiness_label", ""))
    if readiness_label == "review_required":
        return 0.0
    if str(row.get("kcat_evidence_label", "")) in KCAT_REVIEW_LABELS:
        return 0.0
    weight = READINESS_SAMPLE_WEIGHT_BASE.get(readiness_label, 0.2)
    uniprot_label = str(row.get("uniprot_evidence_label", ""))
    enzyme_label = str(row.get("enzyme_constraint_label", ""))
    kcat_label = str(row.get("kcat_evidence_label", ""))
    sample_status = str(row.get("sample_status") or row.get("ml_sample_status", ""))
    if uniprot_label in UNIPROT_STRONG_LABELS:
        weight += 0.05
    elif uniprot_label in UNIPROT_CAUTION_LABELS:
        weight -= 0.1
    if enzyme_label in ENZYME_SUPPORT_LABELS:
        weight += 0.05
    elif enzyme_label in ENZYME_CONFLICT_LABELS:
        weight = min(weight, 0.1)
    if kcat_label in KCAT_STRONG_LABELS:
        weight += 0.05
    elif kcat_label in KCAT_CAUTION_LABELS:
        weight -= 0.1
        if enzyme_label in ENZYME_SUPPORT_LABELS:
            weight = min(weight, 0.75)
    if sample_status == "low_n_exploratory":
        weight -= 0.05
    return round(clamp(weight, 0.0, 1.0), 6)


def kcat_prior_adjustment(row: dict[str, str]) -> float:
    label = str(row.get("kcat_evidence_label", ""))
    if label in KCAT_REVIEW_LABELS:
        return -0.2
    if label in KCAT_STRONG_LABELS:
        return 0.03
    if label in KCAT_CAUTION_LABELS:
        return -0.08
    return 0.0


def combined_prior_score(
    readiness_label: str,
    readiness_prior_score: float,
    ml_prior: dict[str, str],
) -> float:
    if readiness_label == "review_required":
        return 0.0
    ml_abs = _to_float(ml_prior.get("abs_score"))
    if ml_abs is None:
        return round(readiness_prior_score, 6)
    return round(clamp(0.7 * readiness_prior_score + 0.3 * ml_abs, 0.0, 1.0), 6)


def candidate_target_label(readiness_label: str) -> str:
    return READINESS_TARGET_LABEL.get(readiness_label, "unclassified_target")


def training_role(target_level: str, readiness_label: str) -> str:
    if readiness_label == "review_required":
        return "exclude_until_reviewed"
    if target_level == "product_reaction":
        return "product_context_prior"
    return "candidate_target_prior"


def target_prior_status(readiness_label: str, sample_weight: float) -> str:
    if readiness_label == "review_required":
        return "blocked_by_readiness_review"
    if sample_weight <= 0:
        return "blocked_by_kcat_conflict_or_readiness"
    if sample_weight >= 0.8:
        return "training_candidate_strong"
    if sample_weight > 0:
        return "training_candidate_caution"
    return "guidance_only"


def target_prior_guidance(readiness_label: str, row: dict[str, str], has_ml_prior: bool) -> str:
    if readiness_label == "review_required" or str(row.get("kcat_evidence_label", "")) in KCAT_REVIEW_LABELS:
        return "Exclude from supervised target training until semantic, UniProt, growth, or enzyme conflicts are reviewed."
    suffix = " ML prior is also available." if has_ml_prior else " No matching ML prior was found."
    kcat_label = str(row.get("kcat_evidence_label", ""))
    if kcat_label == "strong":
        suffix += " kcat evidence is strong."
    elif kcat_label == "conflict_review":
        suffix += " kcat conflict requires review."
    elif kcat_label == "caution":
        suffix += " kcat evidence is caution-tier."
    if readiness_label == "stronger_evidence":
        return "Use as a high-weight positive candidate target for hybrid ML/GEM prototypes." + suffix
    if readiness_label == "usable_with_caution":
        return "Use as a lower-weight candidate target; keep caution flags visible in model interpretation." + suffix
    return "Use as weak guidance or product context, not as a confident supervised target." + suffix


def weight_reason(row: dict[str, object]) -> str:
    parts = [str(row.get("production_readiness_label", ""))]
    if row.get("uniprot_evidence_label"):
        parts.append(f"uniprot={row.get('uniprot_evidence_label')}")
    if row.get("enzyme_constraint_label"):
        parts.append(f"enzyme={row.get('enzyme_constraint_label')}")
    if row.get("kcat_evidence_label"):
        parts.append(f"kcat={row.get('kcat_evidence_label')}")
    if row.get("kcat_conflict_flag"):
        parts.append(f"kcat_conflict={row.get('kcat_conflict_flag')}")
    if row.get("ml_abs_score") not in {"", None}:
        parts.append(f"ml_abs={row.get('ml_abs_score')}")
    return ";".join(part for part in parts if part)


def readiness_hybrid_guidance(target_rows: list[dict[str, object]]) -> str:
    if not target_rows:
        return "No production readiness rows were available; run production readiness gate before hybrid target export."
    if any(row.get("production_readiness_label") == "stronger_evidence" for row in target_rows):
        return "Readiness-aware target priors are available for ML + GEM hybrid prototypes."
    return "Readiness-aware target priors were exported, but current candidates are cautionary or guidance-only."


def canonical_reaction(reaction_id: str) -> str:
    text = str(reaction_id or "").strip()
    if not text:
        return ""
    return text if text.startswith("R_") else f"R_{text}"


def canonical_gene(gene_id: str) -> str:
    text = str(gene_id or "").strip()
    if not text:
        return ""
    return text if text.startswith("G_") else f"G_{text}"


def normalize_entity_id(value: str, target_type: str) -> str:
    text = str(value or "").strip().lower()
    if target_type == "reaction" and text.startswith("r_"):
        return text[2:]
    if target_type == "gene" and text.startswith("g_"):
        return text[2:]
    return text


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _count_by(rows: list[dict[str, object]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, ""))
        counts[value] = counts.get(value, 0) + 1
    return counts


def _to_float(value: object) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _read_optional(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return read_csv_records(path)
