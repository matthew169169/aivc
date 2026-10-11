"""Readiness gate for production targets using semantic QC and GECKO/ecFactory evidence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .constraints import read_csv_records, write_csv, write_json


READINESS_LABELS = {
    "stronger_evidence": 3,
    "usable_with_caution": 2,
    "guidance_only": 1,
    "review_required": 0,
}
READINESS_LABEL_DISPLAY_ORDER = [
    "review_required",
    "stronger_evidence",
    "usable_with_caution",
    "guidance_only",
]
READINESS_SORT_MODES = [
    "attention_first",
    "readiness_score_high",
    "readiness_score_low",
    "enzyme_conflict_first",
]
READINESS_SORT_LABELS = {
    "attention_first": "attention first",
    "readiness_score_high": "readiness score high to low",
    "readiness_score_low": "readiness score low to high",
    "enzyme_conflict_first": "enzyme conflict first",
}
ENZYME_CONFLICT_LABELS = {
    "action_conflict_review",
    "enzyme_constraint_blocks_cobra_target",
}
UNIPROT_REVIEW_LABELS = {
    "review_required",
}
UNIPROT_STRONG_LABELS = {
    "reviewed_ec_consistent",
    "reviewed_with_ec",
}
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
KCAT_STRONG_TIERS = {
    "experimental",
    "curated_database",
    "organism_database",
}
KCAT_CAUTION_TIERS = {
    "homology_database",
    "user_supplied_unspecified",
    "dlkcat_predicted",
    "ml_predicted",
    "fallback",
}
KCAT_REVIEW_LABELS = {
    "conflict_review",
}


@dataclass(slots=True)
class ProductionReadinessResult:
    """Summary returned after production readiness tables are written."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]


def run_production_readiness_gate(
    production_results_dir: str | Path,
    uniprot_model_check_dir: str | Path | None = None,
    kcat_priors_path: str | Path | None = None,
    kcat_conflict_flags_path: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> ProductionReadinessResult:
    """Build target/design/gene readiness tables from production, GECKO, and semantic-QC outputs."""

    production_dir = Path(production_results_dir)
    uniprot_dir = Path(uniprot_model_check_dir) if uniprot_model_check_dir else None
    output = Path(output_dir) if output_dir else production_dir
    output.mkdir(parents=True, exist_ok=True)
    files = production_readiness_files(output)

    target_rows = _read_optional(production_dir / "production_target_ranking.csv")
    design_rows = _read_optional(production_dir / "production_design_targets.csv")
    gene_rows = _read_optional(production_dir / "production_gene_targets.csv")
    gecko_targets = _read_optional(production_dir / "production_gecko_target_comparison.csv")
    gecko_design = _read_optional(production_dir / "production_gecko_design_comparison.csv")
    semantic_index = load_semantic_qc_index(uniprot_dir)
    gene_uniprot_index = load_gene_uniprot_index(uniprot_dir)
    kcat_path = Path(kcat_priors_path) if kcat_priors_path else production_dir.parent / "generated_constraints" / "kcat_priors.csv"
    kcat_conflict_path = (
        Path(kcat_conflict_flags_path)
        if kcat_conflict_flags_path
        else production_dir.parent / "generated_constraints" / "kcat_conflict_flags.csv"
    )
    kcat_conflict_index = load_kcat_conflict_index(kcat_conflict_path)
    kcat_index = load_kcat_prior_index(kcat_path, kcat_conflict_index)

    target_readiness = build_target_readiness(target_rows, gecko_targets, semantic_index, kcat_index)
    design_readiness = build_design_readiness(design_rows, gecko_design, semantic_index, kcat_index)
    gene_readiness = build_gene_readiness(gene_rows, gecko_design, gene_uniprot_index, kcat_index)
    summary_rows = [
        build_readiness_summary(
            target_readiness=target_readiness,
            design_readiness=design_readiness,
            gene_readiness=gene_readiness,
            semantic_index=semantic_index,
        )
    ]

    write_csv(files["summary"], summary_rows)
    write_csv(files["target_readiness"], target_readiness)
    write_csv(files["design_readiness"], design_readiness)
    write_csv(files["gene_readiness"], gene_readiness)
    write_json(
        files["manifest"],
        {
            "schema_version": "0.1.0",
            "status": summary_rows[0]["status"],
            "production_results_dir": str(production_dir),
            "uniprot_model_check_dir": str(uniprot_dir) if uniprot_dir else "",
            "kcat_priors_path": str(kcat_path),
            "kcat_conflict_flags_path": str(kcat_conflict_path),
            "files": files,
            "input_counts": {
                "production_target_ranking": len(target_rows),
                "production_design_targets": len(design_rows),
                "production_gene_targets": len(gene_rows),
                "production_gecko_target_comparison": len(gecko_targets),
                "production_gecko_design_comparison": len(gecko_design),
                "semantic_qc_reactions": len(semantic_index),
                "uniprot_gene_evidence": len(gene_uniprot_index),
                "kcat_prior_reactions": len(kcat_index),
                "kcat_conflict_reactions": len(kcat_conflict_index),
            },
        },
    )
    return ProductionReadinessResult(
        status="completed",
        output_dir=str(output),
        message=str(summary_rows[0]["guidance"]),
        files=files,
    )


def build_target_readiness(
    target_rows: list[dict[str, str]],
    gecko_target_rows: list[dict[str, str]],
    semantic_index: dict[str, dict[str, str]],
    kcat_index: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, object]]:
    """Annotate product target ranking rows with readiness labels."""

    gecko_index = index_gecko_targets(gecko_target_rows)
    kcat_index = kcat_index or {}
    output: list[dict[str, object]] = []
    for row in target_rows:
        product_id = str(row.get("model_product_reaction_id") or row.get("product_reaction_id", ""))
        gecko = lookup_gecko_target(gecko_index, row)
        semantic = semantic_index.get(normalize_reaction_id(product_id), {})
        semantic_label = row.get("semantic_label") or semantic.get("semantic_label", "")
        uniprot_evidence = reaction_uniprot_evidence(semantic)
        kcat_evidence = kcat_evidence_for_reaction(product_id, kcat_index)
        label, reasons = classify_product_readiness(row, gecko, semantic_label, uniprot_evidence, kcat_evidence)
        output.append(
            {
                **row,
                "production_readiness_label": label,
                "readiness_score": READINESS_LABELS[label],
                "semantic_readiness_label": semantic_label,
                "semantic_warning": row.get("semantic_warning") or semantic.get("semantic_warning", ""),
                **uniprot_output_fields(uniprot_evidence),
                "enzyme_constraint_label": gecko.get("comparison_label", "not_available"),
                "enzyme_constraint_guidance": gecko.get("guidance", ""),
                **kcat_output_fields(kcat_evidence),
                "readiness_reasons": ";".join(reasons),
                "readiness_guidance": product_readiness_guidance(label, reasons),
            }
        )
    return output


def build_design_readiness(
    design_rows: list[dict[str, str]],
    gecko_design_rows: list[dict[str, str]],
    semantic_index: dict[str, dict[str, str]],
    kcat_index: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, object]]:
    """Annotate reaction-level production design targets with readiness labels."""

    gecko_index = index_gecko_design(gecko_design_rows)
    kcat_index = kcat_index or {}
    output: list[dict[str, object]] = []
    for row in design_rows:
        candidate_id = str(row.get("candidate_reaction_id", ""))
        gecko = lookup_gecko_design(gecko_index, row, "reaction", candidate_id)
        semantic = semantic_index.get(normalize_reaction_id(candidate_id), {})
        semantic_label = row.get("semantic_label") or semantic.get("semantic_label", "")
        uniprot_evidence = reaction_uniprot_evidence(semantic)
        kcat_evidence = kcat_evidence_for_reaction(candidate_id, kcat_index)
        label, reasons = classify_design_readiness(row, gecko, semantic_label, uniprot_evidence, kcat_evidence)
        output.append(
            {
                **row,
                "production_readiness_label": label,
                "readiness_score": READINESS_LABELS[label],
                "semantic_readiness_label": semantic_label,
                **uniprot_output_fields(uniprot_evidence),
                "enzyme_constraint_label": gecko.get("comparison_label", "not_available"),
                "enzyme_constraint_guidance": gecko.get("guidance", ""),
                **kcat_output_fields(kcat_evidence),
                "readiness_reasons": ";".join(reasons),
                "readiness_guidance": design_readiness_guidance(label, reasons),
            }
        )
    return output


def build_gene_readiness(
    gene_rows: list[dict[str, str]],
    gecko_design_rows: list[dict[str, str]],
    gene_uniprot_index: dict[str, dict[str, str]] | None = None,
    kcat_index: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, object]]:
    """Annotate gene-level production targets with readiness labels."""

    gecko_index = index_gecko_design(gecko_design_rows)
    gene_uniprot_index = gene_uniprot_index or {}
    kcat_index = kcat_index or {}
    output: list[dict[str, object]] = []
    for row in gene_rows:
        gene_id = str(row.get("gene_id", ""))
        gecko = lookup_gecko_design(gecko_index, row, "gene", gene_id)
        uniprot_evidence = gene_uniprot_evidence(gene_uniprot_index.get(normalize_gene_id(gene_id), {}))
        kcat_evidence = kcat_evidence_for_reactions(split_semicolon_values(row.get("supporting_reactions", "")), kcat_index)
        label, reasons = classify_gene_readiness(row, gecko, uniprot_evidence, kcat_evidence)
        output.append(
            {
                **row,
                "production_readiness_label": label,
                "readiness_score": READINESS_LABELS[label],
                "semantic_readiness_label": row.get("semantic_label", ""),
                **uniprot_output_fields(uniprot_evidence),
                "enzyme_constraint_label": gecko.get("comparison_label", "not_available"),
                "enzyme_constraint_guidance": gecko.get("guidance", ""),
                **kcat_output_fields(kcat_evidence),
                "readiness_reasons": ";".join(reasons),
                "readiness_guidance": gene_readiness_guidance(label, reasons),
            }
        )
    return output


def build_readiness_summary(
    *,
    target_readiness: list[dict[str, object]],
    design_readiness: list[dict[str, object]],
    gene_readiness: list[dict[str, object]],
    semantic_index: dict[str, dict[str, str]],
) -> dict[str, object]:
    all_rows = [*target_readiness, *design_readiness, *gene_readiness]
    counts = {label: sum(1 for row in all_rows if row.get("production_readiness_label") == label) for label in READINESS_LABELS}
    status = "completed" if all_rows else "skipped_no_production_rows"
    return {
        "status": status,
        "product_target_count": len(target_readiness),
        "reaction_design_target_count": len(design_readiness),
        "gene_design_target_count": len(gene_readiness),
        "stronger_evidence_count": counts["stronger_evidence"],
        "usable_with_caution_count": counts["usable_with_caution"],
        "guidance_only_count": counts["guidance_only"],
        "review_required_count": counts["review_required"],
        "semantic_qc_reaction_count": len(semantic_index),
        "uniprot_stronger_evidence_count": sum(
            1 for row in all_rows if row.get("uniprot_evidence_label") in UNIPROT_STRONG_LABELS
        ),
        "uniprot_caution_count": sum(
            1 for row in all_rows if row.get("uniprot_evidence_label") in UNIPROT_CAUTION_LABELS
        ),
        "uniprot_review_required_count": sum(
            1 for row in all_rows if row.get("uniprot_evidence_label") in UNIPROT_REVIEW_LABELS
        ),
        "uniprot_cache_issue_count": sum(1 for row in all_rows if row.get("uniprot_cache_status") in {"cache_error", "fetch_failed"}),
        "kcat_strong_evidence_count": sum(1 for row in all_rows if row.get("kcat_evidence_label") == "strong"),
        "kcat_caution_count": sum(1 for row in all_rows if row.get("kcat_evidence_label") == "caution"),
        "kcat_missing_count": sum(1 for row in all_rows if row.get("kcat_evidence_label") == "not_available"),
        "kcat_conflict_review_count": sum(1 for row in all_rows if row.get("kcat_conflict_flag") == "kcat_conflict_review"),
        "kcat_spread_caution_count": sum(1 for row in all_rows if row.get("kcat_conflict_flag") == "kcat_spread_caution"),
        "gecko_supported_count": sum(
            1 for row in all_rows if row.get("enzyme_constraint_label") == "supported_by_gecko_or_ecfactory"
        )
        + sum(1 for row in all_rows if row.get("enzyme_constraint_label") == "enzyme_constrained_supported"),
        "gecko_conflict_count": sum(1 for row in all_rows if row.get("enzyme_constraint_label") == "action_conflict_review"),
        "guidance": readiness_summary_guidance(counts, status),
    }


def classify_product_readiness(
    row: dict[str, str],
    gecko: dict[str, str],
    semantic_label: str,
    uniprot_evidence: dict[str, str] | None = None,
    kcat_evidence: dict[str, str] | None = None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    growth_label = str(row.get("growth_coupling_label", ""))
    recommended_count = _safe_int(row.get("recommended_design_count"))
    gecko_label = str(gecko.get("comparison_label", ""))
    uniprot_label = (uniprot_evidence or {}).get("uniprot_evidence_label", "")
    kcat_label = (kcat_evidence or {}).get("kcat_evidence_label", "")
    kcat_conflict_flag = (kcat_evidence or {}).get("kcat_conflict_flag", "")

    if semantic_label == "review_required":
        reasons.append("semantic_review_required")
    if uniprot_label in UNIPROT_REVIEW_LABELS:
        reasons.append("uniprot_review_required")
    if kcat_label in KCAT_REVIEW_LABELS or kcat_conflict_flag == "kcat_conflict_review":
        reasons.append("kcat_conflict_review")
    if gecko_label == "enzyme_constraint_blocks_cobra_target":
        reasons.append("enzyme_constraint_blocks_cobra_target")
    if reasons:
        return "review_required", reasons

    if growth_label == "no_product_flux":
        return "guidance_only", ["no_product_flux"]

    if gecko_label == "enzyme_constrained_supported" and semantic_label in {"", "usable"} and recommended_count > 0:
        reasons = ["enzyme_constrained_supported", "semantic_usable", "has_ranked_design_targets"]
        if uniprot_label in UNIPROT_STRONG_LABELS:
            reasons.append("uniprot_reviewed_ec_consistent")
        if kcat_label == "strong":
            reasons.append("kcat_strong_evidence")
        elif kcat_conflict_flag == "kcat_spread_caution":
            reasons.append("kcat_spread_caution")
            return "usable_with_caution", reasons
        elif kcat_label == "caution":
            reasons.append("kcat_caution")
            return "usable_with_caution", reasons
        return "stronger_evidence", reasons

    if (
        uniprot_label in UNIPROT_STRONG_LABELS
        and semantic_label in {"", "usable"}
        and recommended_count > 0
        and growth_label in {"growth_coupled_possible", "growth_tradeoff"}
    ):
        return "stronger_evidence", ["uniprot_reviewed_ec_consistent", "semantic_usable", "has_ranked_design_targets"]

    if gecko_label == "enzyme_constrained_supported":
        reasons.append("enzyme_constrained_supported")
    if kcat_label == "strong":
        reasons.append("kcat_strong_evidence")
    elif kcat_conflict_flag == "kcat_spread_caution":
        reasons.append("kcat_spread_caution")
    elif kcat_label == "caution":
        reasons.append("kcat_caution")
    if uniprot_label in UNIPROT_CAUTION_LABELS:
        reasons.append(uniprot_label)
    if semantic_label in {"inconclusive", "usable_with_caution"}:
        reasons.append(f"semantic_{semantic_label}")
    if gecko_label in {"cobra_only_no_gecko_target_result", "gecko_result_without_flux", "gecko_only_target"}:
        reasons.append(gecko_label)
    if growth_label in {"growth_coupled_possible", "growth_tradeoff"}:
        reasons.append(growth_label)
    if recommended_count == 0:
        reasons.append("no_ranked_design_targets")
    return "usable_with_caution" if reasons else "guidance_only", reasons or ["insufficient_supporting_evidence"]


def classify_design_readiness(
    row: dict[str, str],
    gecko: dict[str, str],
    semantic_label: str,
    uniprot_evidence: dict[str, str] | None = None,
    kcat_evidence: dict[str, str] | None = None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    action = str(row.get("recommended_action", ""))
    confidence = str(row.get("action_confidence", ""))
    growth_loss = str(row.get("growth_loss_label", ""))
    gecko_label = str(gecko.get("comparison_label", ""))
    uniprot_label = (uniprot_evidence or {}).get("uniprot_evidence_label", "")
    kcat_label = (kcat_evidence or {}).get("kcat_evidence_label", "")
    kcat_conflict_flag = (kcat_evidence or {}).get("kcat_conflict_flag", "")

    if semantic_label == "review_required":
        reasons.append("semantic_review_required")
    if uniprot_label in UNIPROT_REVIEW_LABELS:
        reasons.append("uniprot_review_required")
    if kcat_label in KCAT_REVIEW_LABELS or kcat_conflict_flag == "kcat_conflict_review":
        reasons.append("kcat_conflict_review")
    if gecko_label == "action_conflict_review":
        reasons.append("gecko_action_conflict")
    if action == "KO" and growth_loss in {"essential", "high_growth_loss"}:
        reasons.append(f"ko_{growth_loss}")
    if reasons:
        return "review_required", reasons

    if gecko_label == "supported_by_gecko_or_ecfactory" and semantic_label in {"", "usable"} and confidence in {"high", "medium"}:
        reasons = ["gecko_supported", "semantic_usable", f"{confidence}_confidence"]
        if uniprot_label in UNIPROT_STRONG_LABELS:
            reasons.append("uniprot_reviewed_ec_consistent")
        if kcat_label == "strong":
            reasons.append("kcat_strong_evidence")
        elif kcat_conflict_flag == "kcat_spread_caution":
            reasons.append("kcat_spread_caution")
            return "usable_with_caution", reasons
        elif kcat_label == "caution":
            reasons.append("kcat_caution")
            return "usable_with_caution", reasons
        return "stronger_evidence", reasons

    if uniprot_label in UNIPROT_STRONG_LABELS and semantic_label in {"", "usable"} and confidence in {"high", "medium"}:
        return "stronger_evidence", ["uniprot_reviewed_ec_consistent", "semantic_usable", f"{confidence}_confidence"]

    if gecko_label == "supported_by_gecko_or_ecfactory":
        reasons.append("gecko_supported")
    if kcat_label == "strong":
        reasons.append("kcat_strong_evidence")
    elif kcat_conflict_flag == "kcat_spread_caution":
        reasons.append("kcat_spread_caution")
    elif kcat_label == "caution":
        reasons.append("kcat_caution")
    if uniprot_label in UNIPROT_CAUTION_LABELS:
        reasons.append(uniprot_label)
    if semantic_label in {"inconclusive", "usable_with_caution"}:
        reasons.append(f"semantic_{semantic_label}")
    if gecko_label in {"cobra_only_no_gecko_design_result", "gecko_only_design_target", "not_available"}:
        reasons.append(gecko_label)
    if growth_loss in {"moderate_growth_loss", "high_growth_loss", "essential", "knockout_not_solved"}:
        reasons.append(growth_loss)
    if confidence in {"low", "exploratory"}:
        reasons.append(f"{confidence}_confidence")
    return "usable_with_caution" if reasons else "guidance_only", reasons or ["insufficient_supporting_evidence"]


def classify_gene_readiness(
    row: dict[str, str],
    gecko: dict[str, str],
    uniprot_evidence: dict[str, str] | None = None,
    kcat_evidence: dict[str, str] | None = None,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    mapping_status = str(row.get("gene_mapping_status", ""))
    semantic_label = str(row.get("semantic_label", ""))
    scope = str(row.get("gpr_design_scope", ""))
    confidence = str(row.get("action_confidence", ""))
    gecko_label = str(gecko.get("comparison_label", ""))
    uniprot_label = (uniprot_evidence or {}).get("uniprot_evidence_label", "")
    kcat_label = (kcat_evidence or {}).get("kcat_evidence_label", "")
    kcat_conflict_flag = (kcat_evidence or {}).get("kcat_conflict_flag", "")

    if mapping_status != "mapped":
        return "guidance_only", [mapping_status or "unmapped_gene_target"]
    if semantic_label == "review_required":
        reasons.append("semantic_review_required")
    if uniprot_label in UNIPROT_REVIEW_LABELS:
        reasons.append("uniprot_review_required")
    if kcat_label in KCAT_REVIEW_LABELS or kcat_conflict_flag == "kcat_conflict_review":
        reasons.append("kcat_conflict_review")
    if gecko_label == "action_conflict_review":
        reasons.append("gecko_action_conflict")
    if reasons:
        return "review_required", reasons

    if (
        gecko_label == "supported_by_gecko_or_ecfactory"
        and semantic_label in {"", "usable"}
        and confidence in {"high", "medium"}
        and scope == "single_gene"
    ):
        reasons = ["gecko_supported", "semantic_usable", "single_gene_gpr"]
        if uniprot_label in UNIPROT_STRONG_LABELS:
            reasons.append("uniprot_reviewed_with_ec")
        if kcat_label == "strong":
            reasons.append("kcat_strong_evidence")
        elif kcat_conflict_flag == "kcat_spread_caution":
            reasons.append("kcat_spread_caution")
            return "usable_with_caution", reasons
        elif kcat_label == "caution":
            reasons.append("kcat_caution")
            return "usable_with_caution", reasons
        return "stronger_evidence", reasons

    if (
        uniprot_label in UNIPROT_STRONG_LABELS
        and semantic_label in {"", "usable"}
        and confidence in {"high", "medium"}
        and scope == "single_gene"
    ):
        return "stronger_evidence", ["uniprot_reviewed_with_ec", "semantic_usable", "single_gene_gpr"]

    if gecko_label == "supported_by_gecko_or_ecfactory":
        reasons.append("gecko_supported")
    if kcat_label == "strong":
        reasons.append("kcat_strong_evidence")
    elif kcat_conflict_flag == "kcat_spread_caution":
        reasons.append("kcat_spread_caution")
    elif kcat_label == "caution":
        reasons.append("kcat_caution")
    if uniprot_label in UNIPROT_CAUTION_LABELS:
        reasons.append(uniprot_label)
    if semantic_label in {"inconclusive", "usable_with_caution"}:
        reasons.append(f"semantic_{semantic_label}")
    if scope in {"isozyme_or_branch", "complex_subunit", "multi_gene_rule"}:
        reasons.append(scope)
    if gecko_label in {"cobra_only_no_gecko_design_result", "gecko_only_design_target", "not_available"}:
        reasons.append(gecko_label)
    if confidence in {"low", "exploratory"}:
        reasons.append(f"{confidence}_confidence")
    return "usable_with_caution" if reasons else "guidance_only", reasons or ["insufficient_supporting_evidence"]


def production_readiness_files(output: Path) -> dict[str, str]:
    return {
        "summary": str(output / "production_readiness_summary.csv"),
        "target_readiness": str(output / "production_target_readiness.csv"),
        "design_readiness": str(output / "production_design_readiness.csv"),
        "gene_readiness": str(output / "production_gene_readiness.csv"),
        "manifest": str(output / "production_readiness_manifest.json"),
    }


def readiness_label_options(rows: list[dict[str, object]]) -> list[str]:
    """Return stable readiness label choices found in a row collection."""

    found = {str(row.get("production_readiness_label", "")) for row in rows if row.get("production_readiness_label")}
    ordered = [label for label in READINESS_LABEL_DISPLAY_ORDER if label in found]
    extras = sorted(label for label in found if label not in READINESS_LABEL_DISPLAY_ORDER)
    return [*ordered, *extras]


def filter_sort_readiness_rows(
    rows: list[dict[str, object]],
    selected_labels: list[str] | set[str] | tuple[str, ...] | None = None,
    sort_mode: str = "attention_first",
) -> list[dict[str, object]]:
    """Filter readiness rows by label and apply a stable user-facing sort order."""

    label_set = {str(label) for label in selected_labels or [] if str(label)}
    filtered = [
        row
        for row in rows
        if not label_set or str(row.get("production_readiness_label", "")) in label_set
    ]
    return sorted(filtered, key=lambda row: readiness_sort_key(row, sort_mode))


def readiness_sort_key(row: dict[str, object], sort_mode: str) -> tuple[object, ...]:
    label = str(row.get("production_readiness_label", ""))
    score = _safe_float(row.get("readiness_score"))
    score_value = score if score is not None else READINESS_LABELS.get(label, -1)
    enzyme_label = str(row.get("enzyme_constraint_label", ""))
    entity = (
        str(row.get("condition", "")),
        str(row.get("product_reaction_id", "")),
        str(row.get("candidate_reaction_id", "")),
        str(row.get("gene_id", "")),
    )
    if sort_mode == "readiness_score_high":
        return (-score_value, _attention_rank(label), *entity)
    if sort_mode == "readiness_score_low":
        return (score_value, _attention_rank(label), *entity)
    if sort_mode == "enzyme_conflict_first":
        return (0 if enzyme_label in ENZYME_CONFLICT_LABELS else 1, _attention_rank(label), -score_value, *entity)
    return (_attention_rank(label), -score_value, *entity)


def load_semantic_qc_index(uniprot_dir: Path | None) -> dict[str, dict[str, str]]:
    if uniprot_dir is None:
        return {}
    gpr_rows = _read_optional(uniprot_dir / "gpr_consistency_flags.csv")
    reaction_rows = _read_optional(uniprot_dir / "reaction_annotation_flags.csv")
    enrichment_index = load_uniprot_cache_status_index(uniprot_dir)
    index: dict[str, dict[str, str]] = {}
    for row in gpr_rows:
        key = normalize_reaction_id(row.get("reaction_id", ""))
        current = index.setdefault(key, {})
        current["gpr_flag"] = row.get("flag", "")
        current["gpr_severity"] = row.get("severity", "")
        current["gpr_status"] = row.get("status", "")
        current["gpr_uniprot_ids"] = row.get("uniprot_ids", "")
    for row in reaction_rows:
        key = normalize_reaction_id(row.get("reaction_id", ""))
        current = index.setdefault(key, {})
        current["reaction_annotation_flag"] = row.get("flag", "")
        current["annotation_severity"] = row.get("severity", "")
        current["reaction_annotation_status"] = row.get("status", "")
        current["reaction_uniprot_ids"] = row.get("reaction_uniprot_ids", "")
        current["gene_uniprot_ids"] = row.get("gene_uniprot_ids", "")
        current["gene_reviewed_status"] = row.get("gene_reviewed_status", "")
        current["reaction_ec_numbers"] = row.get("reaction_ec_numbers", "")
        current["gene_ec_numbers"] = row.get("gene_ec_numbers", "")
        current["ec_overlap"] = row.get("ec_overlap", "")
        current["gene_protein_names"] = row.get("gene_protein_names", "")
    for current in index.values():
        accession_ids = split_semicolon_values(current.get("reaction_uniprot_ids", "")) | split_semicolon_values(
            current.get("gene_uniprot_ids", "")
        ) | split_semicolon_values(current.get("gpr_uniprot_ids", ""))
        current["uniprot_cache_status"] = joined_cache_statuses(accession_ids, enrichment_index)
        current["semantic_label"] = classify_semantic_label(current)
        current["semantic_warning"] = semantic_warning(current)
    return index


def load_gene_uniprot_index(uniprot_dir: Path | None) -> dict[str, dict[str, str]]:
    if uniprot_dir is None:
        return {}
    enrichment_index = load_uniprot_cache_status_index(uniprot_dir)
    index: dict[str, dict[str, str]] = {}
    for row in _read_optional(uniprot_dir / "uniprot_gene_coverage.csv"):
        key = normalize_gene_id(row.get("gene_id", ""))
        current = {key: str(value) for key, value in row.items()}
        accession_ids = split_semicolon_values(current.get("uniprot_id", ""))
        current["uniprot_cache_status"] = joined_cache_statuses(accession_ids, enrichment_index)
        index[key] = current
    return index


def load_kcat_prior_index(
    kcat_priors_path: Path | None,
    conflict_index: dict[str, dict[str, str]] | None = None,
) -> dict[str, dict[str, str]]:
    """Load selected reaction-level kcat priors keyed by normalized reaction id."""

    if kcat_priors_path is None:
        return {}
    conflict_index = conflict_index or {}
    rows = _read_optional(kcat_priors_path)
    index: dict[str, dict[str, str]] = {}
    for row in rows:
        reaction_id = str(row.get("model_target_id") or row.get("target_id") or row.get("reaction_id", ""))
        key = normalize_reaction_id(reaction_id)
        if not key:
            continue
        merged = {**row, **conflict_index.get(key, {})}
        current = index.get(key)
        if current is None or kcat_priority_key(merged) > kcat_priority_key(current):
            index[key] = merged
    return index


def load_kcat_conflict_index(kcat_conflict_flags_path: Path | None) -> dict[str, dict[str, str]]:
    """Load kcat conflict flags keyed by normalized reaction id."""

    if kcat_conflict_flags_path is None:
        return {}
    index: dict[str, dict[str, str]] = {}
    for row in _read_optional(kcat_conflict_flags_path):
        key = normalize_reaction_id(row.get("model_target_id", ""))
        if key:
            index[key] = {
                "kcat_conflict_flag": row.get("flag", ""),
                "kcat_conflict_severity": row.get("severity", ""),
                "kcat_fold_range": row.get("fold_range", ""),
                "kcat_conflict_guidance": row.get("guidance", ""),
            }
    return index


def load_uniprot_cache_status_index(uniprot_dir: Path | None) -> dict[str, str]:
    if uniprot_dir is None:
        return {}
    index: dict[str, str] = {}
    for row in _read_optional(uniprot_dir / "uniprot_enrichment_records.csv"):
        accession = str(row.get("accession", "")).strip().upper()
        if accession:
            index[accession] = str(row.get("cache_status", ""))
    return index


def kcat_evidence_for_reaction(reaction_id: str, kcat_index: dict[str, dict[str, str]]) -> dict[str, str]:
    """Return kcat evidence for one reaction."""

    key = normalize_reaction_id(reaction_id)
    row = kcat_index.get(key, {})
    if not row:
        return {
            "kcat_evidence_tier": "not_available",
            "kcat_evidence_label": "not_available",
            "kcat_value_per_s": "",
            "kcat_unit": "",
            "kcat_confidence": "",
            "kcat_source_tier": "",
            "kcat_selection_status": "",
            "kcat_matched_reactions": "",
            "kcat_conflict_flag": "",
            "kcat_conflict_severity": "",
            "kcat_fold_range": "",
            "kcat_conflict_guidance": "",
            "kcat_evidence_guidance": kcat_evidence_guidance("not_available", ""),
        }
    tier = str(row.get("kcat_evidence_tier") or row.get("source_tier") or "user_supplied_unspecified")
    conflict_flag = str(row.get("kcat_conflict_flag", ""))
    label = kcat_evidence_label(tier, conflict_flag)
    model_target_id = str(row.get("model_target_id") or row.get("target_id") or reaction_id)
    return {
        "kcat_evidence_tier": tier,
        "kcat_evidence_label": label,
        "kcat_value_per_s": row.get("kcat", "") if str(row.get("unit", "")) == "per_s" else "",
        "kcat_unit": row.get("unit", ""),
        "kcat_confidence": row.get("confidence", ""),
        "kcat_source_tier": row.get("source_tier", ""),
        "kcat_selection_status": row.get("selection_status", ""),
        "kcat_matched_reactions": model_target_id,
        "kcat_conflict_flag": row.get("kcat_conflict_flag", ""),
        "kcat_conflict_severity": row.get("kcat_conflict_severity", ""),
        "kcat_fold_range": row.get("kcat_fold_range", ""),
        "kcat_conflict_guidance": row.get("kcat_conflict_guidance", ""),
        "kcat_evidence_guidance": kcat_evidence_guidance(label, tier),
    }


def kcat_evidence_for_reactions(
    reaction_ids: set[str],
    kcat_index: dict[str, dict[str, str]],
) -> dict[str, str]:
    """Return the strongest kcat evidence among a set of supporting reactions."""

    rows = []
    for reaction_id in reaction_ids:
        row = kcat_index.get(normalize_reaction_id(reaction_id))
        if row:
            rows.append(row)
    if not rows:
        return kcat_evidence_for_reaction("", kcat_index)
    best = sorted(
        rows,
        key=lambda row: (
            2 if row.get("kcat_conflict_flag") == "kcat_conflict_review" else 1 if row.get("kcat_conflict_flag") == "kcat_spread_caution" else 0,
            *kcat_priority_key(row),
        ),
        reverse=True,
    )[0]
    evidence = kcat_evidence_for_reaction(str(best.get("model_target_id") or best.get("target_id", "")), kcat_index)
    matched = sorted(
        str(row.get("model_target_id") or row.get("target_id") or row.get("reaction_id", ""))
        for row in rows
        if row.get("model_target_id") or row.get("target_id") or row.get("reaction_id")
    )
    evidence["kcat_matched_reactions"] = ";".join(matched)
    return evidence


def kcat_output_fields(evidence: dict[str, str]) -> dict[str, str]:
    return {
        "kcat_evidence_tier": evidence.get("kcat_evidence_tier", ""),
        "kcat_evidence_label": evidence.get("kcat_evidence_label", ""),
        "kcat_value_per_s": evidence.get("kcat_value_per_s", ""),
        "kcat_unit": evidence.get("kcat_unit", ""),
        "kcat_confidence": evidence.get("kcat_confidence", ""),
        "kcat_source_tier": evidence.get("kcat_source_tier", ""),
        "kcat_selection_status": evidence.get("kcat_selection_status", ""),
        "kcat_matched_reactions": evidence.get("kcat_matched_reactions", ""),
        "kcat_conflict_flag": evidence.get("kcat_conflict_flag", ""),
        "kcat_conflict_severity": evidence.get("kcat_conflict_severity", ""),
        "kcat_fold_range": evidence.get("kcat_fold_range", ""),
        "kcat_conflict_guidance": evidence.get("kcat_conflict_guidance", ""),
        "kcat_evidence_guidance": evidence.get("kcat_evidence_guidance", ""),
    }


def kcat_evidence_label(tier: str, conflict_flag: str = "") -> str:
    if conflict_flag == "kcat_conflict_review":
        return "conflict_review"
    if tier in KCAT_STRONG_TIERS:
        return "strong"
    if tier in KCAT_CAUTION_TIERS:
        return "caution"
    if tier == "not_available":
        return "not_available"
    return "caution"


def kcat_evidence_guidance(label: str, tier: str) -> str:
    if label == "conflict_review":
        return "kcat candidates have high within-reaction conflict; review before using as enzyme or hybrid evidence."
    if label == "strong":
        return "kcat prior is experimental or organism/curated database supported."
    if label == "caution":
        return f"kcat prior tier is {tier or 'unspecified'}; keep enzyme-constrained interpretation cautionary."
    return "No selected kcat prior was available for this target."


def kcat_priority_key(row: dict[str, str]) -> tuple[float, float, float]:
    return (
        _safe_float(row.get("kcat_evidence_rank")) or kcat_tier_rank(str(row.get("kcat_evidence_tier", ""))),
        _safe_float(row.get("confidence")) or 0.0,
        _safe_float(row.get("kcat")) or 0.0,
    )


def kcat_tier_rank(tier: str) -> float:
    ranks = {
        "experimental": 100,
        "curated_database": 90,
        "organism_database": 80,
        "homology_database": 70,
        "user_supplied_unspecified": 65,
        "dlkcat_predicted": 50,
        "ml_predicted": 40,
        "fallback": 10,
    }
    return float(ranks.get(tier, 0))


def reaction_uniprot_evidence(row: dict[str, str]) -> dict[str, str]:
    if not row:
        return {
            "uniprot_evidence_label": "not_available",
            "uniprot_reviewed_status": "",
            "uniprot_ec_status": "",
            "uniprot_cache_status": "",
            "uniprot_evidence_guidance": "No UniProt/GPR evidence was available for this reaction.",
            "uniprot_protein_name": "",
        }
    flag = str(row.get("reaction_annotation_flag", ""))
    severity = str(row.get("annotation_severity", ""))
    reviewed_status = str(row.get("gene_reviewed_status", ""))
    ec_overlap = str(row.get("ec_overlap", ""))
    cache_status = str(row.get("uniprot_cache_status", ""))
    if severity == "high" or flag in {"ec_mismatch_review", "missing_gpr"}:
        label = "review_required"
    elif has_cache_issue(cache_status):
        label = "cache_or_fetch_issue"
    elif flag == "ec_consistent" and ec_overlap and "reviewed" in split_semicolon_values(reviewed_status):
        label = "reviewed_ec_consistent"
    elif flag == "ec_consistent" and "unreviewed" in split_semicolon_values(reviewed_status):
        label = "ec_consistent_unreviewed"
    elif flag == "ec_consistent":
        label = "ec_consistent_unknown_review"
    elif flag in {"reaction_ec_missing", "gene_ec_missing", "annotation_missing", "inconclusive"}:
        label = "ec_missing_or_inconclusive"
    else:
        label = "not_available"
    return {
        "uniprot_evidence_label": label,
        "uniprot_reviewed_status": reviewed_status,
        "uniprot_ec_status": flag,
        "uniprot_cache_status": cache_status,
        "uniprot_evidence_guidance": uniprot_evidence_guidance(label),
        "uniprot_protein_name": str(row.get("gene_protein_names", "")),
    }


def gene_uniprot_evidence(row: dict[str, str]) -> dict[str, str]:
    if not row:
        return {
            "uniprot_evidence_label": "not_available",
            "uniprot_reviewed_status": "",
            "uniprot_ec_status": "",
            "uniprot_cache_status": "",
            "uniprot_evidence_guidance": "No UniProt evidence was available for this gene.",
            "uniprot_protein_name": "",
        }
    reviewed_statuses = split_semicolon_values(row.get("reviewed_status", ""))
    cache_status = str(row.get("uniprot_cache_status", ""))
    has_ec = _truthy_string(row.get("has_ec", "")) or bool(str(row.get("ec_numbers", "")).strip())
    has_uniprot = _truthy_string(row.get("has_uniprot", "")) or bool(str(row.get("uniprot_id", "")).strip())
    local_status = str(row.get("status", ""))
    if has_cache_issue(cache_status):
        label = "cache_or_fetch_issue"
    elif not has_uniprot or local_status == "annotation_missing":
        label = "annotation_missing"
    elif "reviewed" in reviewed_statuses and has_ec:
        label = "reviewed_with_ec"
    elif "reviewed" in reviewed_statuses:
        label = "reviewed_without_ec"
    elif "unreviewed" in reviewed_statuses and has_ec:
        label = "unreviewed_with_ec"
    elif "unreviewed" in reviewed_statuses:
        label = "unreviewed_or_missing_ec"
    elif has_ec:
        label = "ec_available_review_unknown"
    else:
        label = "unreviewed_or_missing_ec"
    return {
        "uniprot_evidence_label": label,
        "uniprot_reviewed_status": str(row.get("reviewed_status", "")),
        "uniprot_ec_status": "ec_available" if has_ec else "ec_missing",
        "uniprot_cache_status": cache_status,
        "uniprot_evidence_guidance": uniprot_evidence_guidance(label),
        "uniprot_protein_name": str(row.get("protein_name", "")),
    }


def uniprot_output_fields(evidence: dict[str, str]) -> dict[str, str]:
    return {
        "uniprot_evidence_label": evidence.get("uniprot_evidence_label", ""),
        "uniprot_reviewed_status": evidence.get("uniprot_reviewed_status", ""),
        "uniprot_ec_status": evidence.get("uniprot_ec_status", ""),
        "uniprot_cache_status": evidence.get("uniprot_cache_status", ""),
        "uniprot_protein_name": evidence.get("uniprot_protein_name", ""),
        "uniprot_evidence_guidance": evidence.get("uniprot_evidence_guidance", ""),
    }


def uniprot_evidence_guidance(label: str) -> str:
    if label in UNIPROT_STRONG_LABELS:
        return "Reviewed UniProt evidence with EC support increases confidence in this target."
    if label == "review_required":
        return "UniProt/GPR evidence has a high-risk conflict or missing GPR; review before prioritization."
    if label == "cache_or_fetch_issue":
        return "UniProt accession exists, but cache or REST enrichment did not complete cleanly."
    if label in UNIPROT_CAUTION_LABELS:
        return "UniProt evidence is partial, unreviewed, or missing EC support; treat as cautionary."
    return "UniProt evidence is unavailable or not decisive for this target."


def split_semicolon_values(value: object) -> set[str]:
    return {part.strip() for part in str(value or "").split(";") if part.strip()}


def joined_cache_statuses(accession_ids: set[str], enrichment_index: dict[str, str]) -> str:
    statuses = sorted({enrichment_index.get(accession.upper(), "") for accession in accession_ids if enrichment_index.get(accession.upper(), "")})
    return ";".join(statuses)


def has_cache_issue(cache_status: str) -> bool:
    return bool(split_semicolon_values(cache_status) & {"cache_error", "fetch_failed"})


def classify_semantic_label(row: dict[str, str]) -> str:
    if "high" in {row.get("gpr_severity"), row.get("annotation_severity")}:
        return "review_required"
    if row.get("reaction_annotation_flag") in {"annotation_missing", "inconclusive"}:
        return "inconclusive"
    if row.get("gpr_flag") in {"partial_uniprot_annotation", "gpr_without_uniprot_annotation"}:
        return "usable_with_caution"
    if row.get("reaction_annotation_flag") in {"reaction_ec_missing", "gene_ec_missing"}:
        return "usable_with_caution"
    if row:
        return "usable"
    return ""


def semantic_warning(row: dict[str, str]) -> str:
    label = row.get("semantic_label", "")
    if label == "review_required":
        return "review semantic QC before using this target for production claims"
    if label == "inconclusive":
        return "annotation is insufficient; use production result as exploratory"
    if label == "usable_with_caution":
        return "annotation coverage is partial"
    return ""


def index_gecko_targets(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    index = {}
    for row in rows:
        key = (str(row.get("condition", "")), normalize_reaction_id(row.get("product_reaction_id", "")))
        index.setdefault(key, row)
    return index


def lookup_gecko_target(index: dict[tuple[str, str], dict[str, str]], row: dict[str, str]) -> dict[str, str]:
    condition = str(row.get("condition", ""))
    product = normalize_reaction_id(str(row.get("product_reaction_id") or row.get("model_product_reaction_id", "")))
    return index.get((condition, product)) or index.get(("", product)) or index.get(("ALL", product)) or {}


def index_gecko_design(rows: list[dict[str, str]]) -> dict[tuple[str, str, str, str], dict[str, str]]:
    index = {}
    for row in rows:
        key = (
            str(row.get("condition", "")),
            normalize_reaction_id(row.get("product_reaction_id", "")),
            str(row.get("target_level", "")),
            normalize_entity_id(row.get("candidate_id", ""), str(row.get("target_level", ""))),
        )
        index.setdefault(key, row)
    return index


def lookup_gecko_design(
    index: dict[tuple[str, str, str, str], dict[str, str]],
    row: dict[str, str],
    target_level: str,
    candidate_id: str,
) -> dict[str, str]:
    condition = str(row.get("condition", ""))
    product = normalize_reaction_id(str(row.get("product_reaction_id", "")))
    candidate = normalize_entity_id(candidate_id, target_level)
    return (
        index.get((condition, product, target_level, candidate))
        or index.get((condition, "", target_level, candidate))
        or index.get(("", "", target_level, candidate))
        or index.get(("ALL", product, target_level, candidate))
        or {}
    )


def normalize_reaction_id(reaction_id: str) -> str:
    text = str(reaction_id or "").strip()
    if text.lower().startswith("r_"):
        text = text[2:]
    return text.lower()


def normalize_gene_id(gene_id: str) -> str:
    text = str(gene_id or "").strip()
    if text.lower().startswith("g_"):
        text = text[2:]
    return text.lower()


def normalize_entity_id(entity_id: str, target_level: str) -> str:
    if target_level == "gene":
        return normalize_gene_id(entity_id)
    return normalize_reaction_id(entity_id)


def product_readiness_guidance(label: str, reasons: list[str]) -> str:
    if label == "stronger_evidence":
        return "Product target is supported by COBRApy production potential, local semantic QC, and enzyme-constrained comparison."
    if label == "review_required":
        return "Review semantic or enzyme-constrained conflicts before treating this product target as actionable."
    if label == "usable_with_caution":
        return "Product target is usable as a prioritized hypothesis, but at least one evidence layer is incomplete or cautionary."
    return "Use this product target as guidance only until stronger production, annotation, or enzyme-constrained evidence is available."


def design_readiness_guidance(label: str, reasons: list[str]) -> str:
    if label == "stronger_evidence":
        return "Reaction intervention has aligned COBRApy, semantic, and GECKO/ecFactory support."
    if label == "review_required":
        return "Do not prioritize this intervention before resolving the listed semantic, growth, or enzyme-constrained conflict."
    if label == "usable_with_caution":
        return "Intervention remains plausible, but should be reviewed before experimental prioritization."
    return "Treat this intervention as exploratory guidance rather than a ranked actionable target."


def gene_readiness_guidance(label: str, reasons: list[str]) -> str:
    if label == "stronger_evidence":
        return "Gene target is a single-gene GPR candidate with aligned enzyme-constrained support."
    if label == "review_required":
        return "Review gene annotation, GPR logic, or enzyme-constrained action conflicts before prioritization."
    if label == "usable_with_caution":
        return "Gene target is interpretable, but GPR structure or supporting evidence warrants caution."
    return "Gene target should be used as explanatory guidance only."


def readiness_summary_guidance(counts: dict[str, int], status: str) -> str:
    if status != "completed":
        return "No production rows were available for readiness gating."
    if counts["review_required"]:
        return f"Readiness gate completed with {counts['review_required']} review-required rows; inspect these before prioritization."
    if counts["stronger_evidence"]:
        return f"Readiness gate completed with {counts['stronger_evidence']} stronger-evidence rows."
    return "Readiness gate completed; current production candidates are mostly cautionary or guidance-only."


def _safe_int(value: object) -> int:
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: object) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _truthy_string(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _attention_rank(label: str) -> int:
    order = {
        "review_required": 0,
        "stronger_evidence": 1,
        "usable_with_caution": 2,
        "guidance_only": 3,
    }
    return order.get(label, 99)


def _read_optional(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return read_csv_records(path)
