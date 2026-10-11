"""Reaction-level lookup across evidence modes and downstream results."""

from __future__ import annotations

from pathlib import Path

from .constraints import read_csv_records
from .evidence_modes import EVIDENCE_MODES, evidence_mode_paths


def build_reaction_drilldown(
    reaction_id: str,
    constraints_dir: str | Path,
    evidence_mode_results_dir: str | Path,
    context_results_dir: str | Path,
    troppo_results_dir: str | Path,
    ml_results_dir: str | Path | None = None,
    uniprot_model_check_dir: str | Path | None = None,
    production_results_dir: str | Path | None = None,
    condition: str = "",
) -> dict[str, object]:
    """Return mode, delta, context, and TROPPO rows for one reaction."""

    query = str(reaction_id or "").strip()
    normalized = normalize_reaction_id(query)
    if not normalized:
        return {
            "query": query,
            "normalized_reaction_id": "",
            "mode_rows": [],
            "delta_rows": [],
            "context_knockout_rows": [],
            "troppo_rows": [],
            "ml_prior_rows": [],
            "ml_lasso_lite_rows": [],
            "ml_loading_rows": [],
            "uniprot_semantic_rows": [],
            "uniprot_gpr_rows": [],
            "uniprot_reaction_rows": [],
            "uniprot_gene_rows": [],
            "production_gecko_summary_rows": [],
            "production_gecko_target_rows": [],
            "production_gecko_design_rows": [],
            "production_readiness_summary_rows": [],
            "production_target_readiness_rows": [],
            "production_design_readiness_rows": [],
            "production_gene_readiness_rows": [],
            "kcat_prior_summary_rows": [],
            "kcat_prior_rows": [],
            "kcat_candidate_rows": [],
            "kcat_conflict_rows": [],
            "enzyme_capacity_rows": [],
            "enzyme_flux_capacity_rows": [],
            "summary_rows": [],
            "conditions": [],
        }

    condition_filter = str(condition or "").strip()
    if condition_filter.upper() == "ALL":
        condition_filter = ""

    mode_rows = build_mode_rows(normalized, constraints_dir, condition_filter)
    delta_rows = _matching_rows(
        _read_optional(Path(evidence_mode_results_dir) / "evidence_mode_reaction_deltas.csv"),
        normalized,
        condition_filter,
    )
    context_knockout_rows = _matching_rows(
        _read_optional(Path(context_results_dir) / "context_knockouts.csv"),
        normalized,
        condition_filter,
    )
    troppo_rows = build_troppo_membership_rows(normalized, troppo_results_dir, condition_filter)
    ml_prior_rows = build_ml_prior_rows(normalized, ml_results_dir) if ml_results_dir else []
    ml_lasso_lite_rows = build_ml_lasso_lite_rows(normalized, ml_results_dir) if ml_results_dir else []
    ml_loading_rows = build_ml_loading_rows(normalized, ml_results_dir) if ml_results_dir else []
    uniprot_gpr_rows = build_uniprot_gpr_rows(normalized, uniprot_model_check_dir) if uniprot_model_check_dir else []
    uniprot_reaction_rows = (
        build_uniprot_reaction_rows(normalized, uniprot_model_check_dir) if uniprot_model_check_dir else []
    )
    uniprot_gene_rows = (
        build_uniprot_gene_rows(uniprot_gpr_rows, uniprot_model_check_dir) if uniprot_model_check_dir else []
    )
    uniprot_semantic_rows = build_uniprot_semantic_rows(
        normalized,
        uniprot_gpr_rows,
        uniprot_reaction_rows,
        uniprot_gene_rows,
    )
    gpr_gene_ids = extract_gpr_gene_ids(uniprot_gpr_rows)
    production_gecko_rows = (
        build_production_gecko_rows(
            normalized,
            production_results_dir,
            condition_filter,
            gene_ids=gpr_gene_ids,
        )
        if production_results_dir
        else {
            "summary_rows": [],
            "target_rows": [],
            "design_rows": [],
        }
    )
    production_readiness_rows = (
        build_production_readiness_rows(
            query,
            normalized,
            production_results_dir,
            condition_filter,
            gene_ids=gpr_gene_ids,
        )
        if production_results_dir
        else {
            "summary_rows": [],
            "target_rows": [],
            "design_rows": [],
            "gene_rows": [],
        }
    )
    kcat_prior_summary_rows = build_kcat_prior_summary_rows(constraints_dir)
    kcat_prior_rows = build_kcat_prior_rows(normalized, constraints_dir)
    kcat_candidate_rows = build_kcat_candidate_rows(normalized, constraints_dir)
    kcat_conflict_rows = build_kcat_conflict_rows(normalized, constraints_dir)
    enzyme_results_dir = Path(constraints_dir).parent / "enzyme_results"
    enzyme_capacity_rows = build_enzyme_capacity_rows(normalized, enzyme_results_dir, condition_filter)
    enzyme_flux_capacity_rows = build_enzyme_flux_capacity_rows(normalized, enzyme_results_dir, condition_filter)
    conditions = sorted(
        {
            str(row.get("condition") or "default")
            for row in [
                *mode_rows,
                *delta_rows,
                *context_knockout_rows,
                *troppo_rows,
                *production_gecko_rows["target_rows"],
                *production_gecko_rows["design_rows"],
                *production_readiness_rows["target_rows"],
                *production_readiness_rows["design_rows"],
                *production_readiness_rows["gene_rows"],
                *enzyme_capacity_rows,
                *enzyme_flux_capacity_rows,
            ]
        }
    )
    summary_rows = build_summary_rows(
        query,
        normalized,
        conditions,
        mode_rows,
        delta_rows,
        context_knockout_rows,
        troppo_rows,
        ml_prior_rows,
        ml_lasso_lite_rows,
        uniprot_semantic_rows,
        production_gecko_rows["summary_rows"],
        production_gecko_rows["target_rows"],
        production_gecko_rows["design_rows"],
        production_readiness_rows["summary_rows"],
        production_readiness_rows["target_rows"],
        production_readiness_rows["design_rows"],
        production_readiness_rows["gene_rows"],
        kcat_prior_rows,
        kcat_candidate_rows,
        kcat_conflict_rows,
        enzyme_capacity_rows,
        enzyme_flux_capacity_rows,
    )
    return {
        "query": query,
        "normalized_reaction_id": normalized,
        "mode_rows": mode_rows,
        "delta_rows": delta_rows,
        "context_knockout_rows": context_knockout_rows,
        "troppo_rows": troppo_rows,
        "ml_prior_rows": ml_prior_rows,
        "ml_lasso_lite_rows": ml_lasso_lite_rows,
        "ml_loading_rows": ml_loading_rows,
        "uniprot_semantic_rows": uniprot_semantic_rows,
        "uniprot_gpr_rows": uniprot_gpr_rows,
        "uniprot_reaction_rows": uniprot_reaction_rows,
        "uniprot_gene_rows": uniprot_gene_rows,
        "production_gecko_summary_rows": production_gecko_rows["summary_rows"],
        "production_gecko_target_rows": production_gecko_rows["target_rows"],
        "production_gecko_design_rows": production_gecko_rows["design_rows"],
        "production_readiness_summary_rows": production_readiness_rows["summary_rows"],
        "production_target_readiness_rows": production_readiness_rows["target_rows"],
        "production_design_readiness_rows": production_readiness_rows["design_rows"],
        "production_gene_readiness_rows": production_readiness_rows["gene_rows"],
        "kcat_prior_summary_rows": kcat_prior_summary_rows,
        "kcat_prior_rows": kcat_prior_rows,
        "kcat_candidate_rows": kcat_candidate_rows,
        "kcat_conflict_rows": kcat_conflict_rows,
        "enzyme_capacity_rows": enzyme_capacity_rows,
        "enzyme_flux_capacity_rows": enzyme_flux_capacity_rows,
        "summary_rows": summary_rows,
        "conditions": conditions,
    }


def build_mode_rows(
    normalized_reaction_id: str,
    constraints_dir: str | Path,
    condition: str = "",
) -> list[dict[str, object]]:
    """Build per-evidence-mode rows for one normalized reaction id."""

    rows: list[dict[str, object]] = []
    for mode in EVIDENCE_MODES:
        paths = evidence_mode_paths(constraints_dir, mode)
        evidence_rows = _matching_rows(_read_optional(paths.reaction_evidence), normalized_reaction_id, condition)
        policy_rows = _matching_rows(_read_optional(paths.context_policy), normalized_reaction_id, condition)
        core_rows = _matching_rows(_read_optional(paths.core_reactions), normalized_reaction_id, condition)
        conditions = sorted(
            {
                str(row.get("condition") or "default")
                for row in [*evidence_rows, *policy_rows, *core_rows]
            }
        )
        for current_condition in conditions:
            evidence = _first_for_condition(evidence_rows, current_condition)
            policy = _first_for_condition(policy_rows, current_condition)
            core = _first_for_condition(core_rows, current_condition)
            source = evidence or policy or core
            rows.append(
                {
                    "condition": current_condition,
                    "evidence_mode": mode,
                    "reaction_id": source.get("reaction_id", ""),
                    "cobra_reaction_id": source.get("cobra_reaction_id", ""),
                    "reaction_name": source.get("reaction_name", ""),
                    "evidence": evidence.get("evidence", ""),
                    "reaction_score": evidence.get("reaction_score", ""),
                    "gene_coverage": evidence.get("gene_coverage", ""),
                    "measured_genes": evidence.get("measured_genes", ""),
                    "context_decision": policy.get("decision", ""),
                    "context_reason": policy.get("reason", ""),
                    "context_penalty": policy.get("penalty", ""),
                    "fastcore_core": bool(core),
                    "ml_score": evidence.get("ml_score", policy.get("ml_score", "")),
                    "ml_source_feature_id": evidence.get("source_feature_id", policy.get("source_feature_id", "")),
                    "ml_target_feature_id": evidence.get("target_feature_id", policy.get("target_feature_id", "")),
                    "confidence": evidence.get("confidence", ""),
                    "sample_status": evidence.get("sample_status", ""),
                    "source_status": evidence.get("status", policy.get("status", core.get("status", ""))),
                }
            )
    return rows


def build_troppo_membership_rows(
    normalized_reaction_id: str,
    troppo_results_dir: str | Path,
    condition: str = "",
) -> list[dict[str, object]]:
    """Return whether the reaction was selected or removed by TROPPO."""

    root = Path(troppo_results_dir)
    selected_rows = _matching_rows(_read_optional(root / "troppo_fastcore_selected_reactions.csv"), normalized_reaction_id, condition)
    removed_rows = _matching_rows(_read_optional(root / "troppo_fastcore_removed_reactions.csv"), normalized_reaction_id, condition)
    conditions = sorted(
        {
            str(row.get("condition") or "default")
            for row in [*selected_rows, *removed_rows]
        }
    )
    rows: list[dict[str, object]] = []
    for current_condition in conditions:
        selected = _first_for_condition(selected_rows, current_condition)
        removed = _first_for_condition(removed_rows, current_condition)
        source = selected or removed
        membership = "selected" if selected else "removed"
        rows.append(
            {
                "condition": current_condition,
                "reaction_id": source.get("reaction_id", ""),
                "cobra_reaction_id": source.get("cobra_reaction_id", ""),
                "troppo_membership": membership,
                "role": selected.get("role", ""),
                "core_source": selected.get("core_source", removed.get("core_source", "")),
                "lower_bound": source.get("lower_bound", ""),
                "upper_bound": source.get("upper_bound", ""),
            }
        )
    return rows


def build_ml_prior_rows(
    normalized_reaction_id: str,
    ml_results_dir: str | Path,
) -> list[dict[str, object]]:
    """Return ML prior rows that target or use the queried reaction."""

    rows = []
    for row in _read_optional(Path(ml_results_dir) / "ml_prior_scores.csv"):
        if not _ml_prior_matches_reaction(row, normalized_reaction_id):
            continue
        rows.append(
            {
                "target_feature_id": row.get("target_feature_id", ""),
                "source_feature_id": row.get("source_feature_id", ""),
                "target_type": row.get("target_type", ""),
                "target_id": row.get("target_id", ""),
                "model_target_id": row.get("model_target_id", ""),
                "score": row.get("score", ""),
                "abs_score": row.get("abs_score", ""),
                "ml_evidence": row.get("ml_evidence", ""),
                "context_action": row.get("context_action", ""),
                "reaction_penalty": row.get("reaction_penalty", ""),
                "confidence": row.get("confidence", ""),
                "sample_status": row.get("sample_status", ""),
                "note": row.get("note", ""),
            }
        )
    return rows


def build_ml_lasso_lite_rows(
    normalized_reaction_id: str,
    ml_results_dir: str | Path,
) -> list[dict[str, object]]:
    """Return sparse-screen rows involving the queried reaction."""

    rows = []
    for row in _read_optional(Path(ml_results_dir) / "ml_lasso_lite_coefficients.csv"):
        if not (
            _feature_matches_reaction(row.get("feature_id", ""), normalized_reaction_id)
            or _feature_matches_reaction(row.get("target_feature_id", ""), normalized_reaction_id)
            or normalize_reaction_id(row.get("entity_id", "")) == normalized_reaction_id
        ):
            continue
        rows.append(row)
    return rows


def build_ml_loading_rows(
    normalized_reaction_id: str,
    ml_results_dir: str | Path,
) -> list[dict[str, object]]:
    """Return PCA loading rows for features involving the queried reaction."""

    rows = []
    for row in _read_optional(Path(ml_results_dir) / "ml_feature_loadings.csv"):
        if _feature_matches_reaction(row.get("feature_id", ""), normalized_reaction_id) or normalize_reaction_id(row.get("entity_id", "")) == normalized_reaction_id:
            rows.append(row)
    return rows


def build_uniprot_gpr_rows(
    normalized_reaction_id: str,
    uniprot_model_check_dir: str | Path,
) -> list[dict[str, str]]:
    """Return UniProt/GPR consistency rows for the queried reaction."""

    return _matching_rows(
        _read_optional(Path(uniprot_model_check_dir) / "gpr_consistency_flags.csv"),
        normalized_reaction_id,
    )


def build_uniprot_reaction_rows(
    normalized_reaction_id: str,
    uniprot_model_check_dir: str | Path,
) -> list[dict[str, str]]:
    """Return reaction annotation consistency rows for the queried reaction."""

    return _matching_rows(
        _read_optional(Path(uniprot_model_check_dir) / "reaction_annotation_flags.csv"),
        normalized_reaction_id,
    )


def build_uniprot_gene_rows(
    uniprot_gpr_rows: list[dict[str, str]],
    uniprot_model_check_dir: str | Path,
) -> list[dict[str, str]]:
    """Return gene coverage rows referenced by the reaction GPR."""

    gene_ids = {
        gene.strip()
        for row in uniprot_gpr_rows
        for gene in str(row.get("genes", "")).split(";")
        if gene.strip()
    }
    if not gene_ids:
        return []
    normalized_genes = {gene.lower() for gene in gene_ids}
    rows = []
    for row in _read_optional(Path(uniprot_model_check_dir) / "uniprot_gene_coverage.csv"):
        gene_id = str(row.get("gene_id", ""))
        if gene_id in gene_ids or gene_id.lower() in normalized_genes:
            rows.append(row)
    return rows


def build_uniprot_semantic_rows(
    normalized_reaction_id: str,
    uniprot_gpr_rows: list[dict[str, str]],
    uniprot_reaction_rows: list[dict[str, str]],
    uniprot_gene_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    """Build a compact semantic QC row from UniProt/GPR check outputs."""

    if not any([uniprot_gpr_rows, uniprot_reaction_rows, uniprot_gene_rows]):
        return []
    gpr = uniprot_gpr_rows[0] if uniprot_gpr_rows else {}
    reaction = uniprot_reaction_rows[0] if uniprot_reaction_rows else {}
    label = _semantic_label(gpr, reaction)
    return [
        {
            "reaction_id": gpr.get("reaction_id", reaction.get("reaction_id", normalized_reaction_id)),
            "reaction_name": gpr.get("reaction_name", reaction.get("reaction_name", "")),
            "semantic_label": label,
            "gpr_flag": gpr.get("flag", ""),
            "gpr_severity": gpr.get("severity", ""),
            "reaction_annotation_flag": reaction.get("flag", ""),
            "annotation_severity": reaction.get("severity", ""),
            "has_gpr": gpr.get("has_gpr", reaction.get("has_gpr", "")),
            "gene_count": gpr.get("gene_count", reaction.get("gene_count", "")),
            "annotated_gene_count": gpr.get("annotated_gene_count", ""),
            "uniprot_coverage_fraction": gpr.get("uniprot_coverage_fraction", ""),
            "genes": gpr.get("genes", ""),
            "gpr_rule": gpr.get("gpr_rule", ""),
            "reaction_ec_numbers": reaction.get("reaction_ec_numbers", ""),
            "gene_ec_numbers": reaction.get("gene_ec_numbers", ""),
            "ec_overlap": reaction.get("ec_overlap", ""),
            "gene_uniprot_ids": reaction.get("gene_uniprot_ids", ""),
            "guidance": _semantic_guidance(label, gpr, reaction),
        }
    ]


def build_production_gecko_rows(
    normalized_reaction_id: str,
    production_results_dir: str | Path,
    condition: str = "",
    gene_ids: set[str] | None = None,
) -> dict[str, list[dict[str, object]]]:
    """Return GECKO/ecFactory production comparison rows relevant to a reaction."""

    root = Path(production_results_dir)
    summary_rows = _read_optional(root / "production_gecko_comparison_summary.csv")
    target_rows = []
    for row in _read_optional(root / "production_gecko_target_comparison.csv"):
        if not _condition_matches(row, condition):
            continue
        if normalize_reaction_id(row.get("product_reaction_id", "")) == normalized_reaction_id:
            target_rows.append(row)

    normalized_genes = {normalize_gene_id(gene_id) for gene_id in gene_ids or set() if str(gene_id).strip()}
    design_rows: list[dict[str, object]] = []
    for row in _read_optional(root / "production_gecko_design_comparison.csv"):
        if not _condition_matches(row, condition):
            continue
        match_reason = production_gecko_design_match_reason(row, normalized_reaction_id, normalized_genes)
        if not match_reason:
            continue
        design_rows.append({**row, "match_reason": match_reason})

    return {
        "summary_rows": summary_rows,
        "target_rows": target_rows,
        "design_rows": design_rows,
    }


def build_production_readiness_rows(
    query: str,
    normalized_reaction_id: str,
    production_results_dir: str | Path,
    condition: str = "",
    gene_ids: set[str] | None = None,
) -> dict[str, list[dict[str, object]]]:
    """Return production readiness rows relevant to a reaction lookup."""

    root = Path(production_results_dir)
    summary_rows = _read_optional(root / "production_readiness_summary.csv")
    target_rows = []
    for row in _read_optional(root / "production_target_readiness.csv"):
        if not _condition_matches(row, condition):
            continue
        if readiness_product_matches(row, normalized_reaction_id):
            target_rows.append({**row, "match_reason": "product_reaction"})

    normalized_genes = {normalize_gene_id(gene_id) for gene_id in gene_ids or set() if str(gene_id).strip()}
    query_gene = normalize_gene_id(query)
    design_rows: list[dict[str, object]] = []
    for row in _read_optional(root / "production_design_readiness.csv"):
        if not _condition_matches(row, condition):
            continue
        match_reason = production_design_readiness_match_reason(row, normalized_reaction_id)
        if not match_reason:
            continue
        design_rows.append({**row, "match_reason": match_reason})

    gene_rows: list[dict[str, object]] = []
    for row in _read_optional(root / "production_gene_readiness.csv"):
        if not _condition_matches(row, condition):
            continue
        match_reason = production_gene_readiness_match_reason(
            row,
            normalized_reaction_id,
            normalized_genes,
            query_gene,
        )
        if not match_reason:
            continue
        gene_rows.append({**row, "match_reason": match_reason})

    return {
        "summary_rows": summary_rows,
        "target_rows": target_rows,
        "design_rows": design_rows,
        "gene_rows": gene_rows,
    }


def build_kcat_prior_summary_rows(constraints_dir: str | Path) -> list[dict[str, object]]:
    """Return global kcat prior merge summary rows when available."""

    return _read_optional(Path(constraints_dir) / "kcat_prior_merge_summary.csv")


def build_kcat_prior_rows(
    normalized_reaction_id: str,
    constraints_dir: str | Path,
) -> list[dict[str, object]]:
    """Return selected kcat prior rows for the queried reaction."""

    return _matching_rows(_read_optional(Path(constraints_dir) / "kcat_priors.csv"), normalized_reaction_id)


def build_kcat_candidate_rows(
    normalized_reaction_id: str,
    constraints_dir: str | Path,
) -> list[dict[str, object]]:
    """Return all kcat candidate rows for the queried reaction."""

    return _matching_rows(_read_optional(Path(constraints_dir) / "kcat_prior_candidates.csv"), normalized_reaction_id)


def build_kcat_conflict_rows(
    normalized_reaction_id: str,
    constraints_dir: str | Path,
) -> list[dict[str, object]]:
    """Return kcat conflict rows for the queried reaction."""

    return _matching_rows(_read_optional(Path(constraints_dir) / "kcat_conflict_flags.csv"), normalized_reaction_id)


def build_enzyme_capacity_rows(
    normalized_reaction_id: str,
    enzyme_results_dir: str | Path,
    condition: str = "",
) -> list[dict[str, object]]:
    """Return enzyme-capacity rows for the queried reaction."""

    return _matching_rows(
        _read_optional(Path(enzyme_results_dir) / "reaction_enzyme_capacity.csv"),
        normalized_reaction_id,
        condition,
    )


def build_enzyme_flux_capacity_rows(
    normalized_reaction_id: str,
    enzyme_results_dir: str | Path,
    condition: str = "",
) -> list[dict[str, object]]:
    """Return flux-vs-enzyme-capacity rows for the queried reaction."""

    return _matching_rows(
        _read_optional(Path(enzyme_results_dir) / "enzyme_flux_capacity_check.csv"),
        normalized_reaction_id,
        condition,
    )


def build_summary_rows(
    query: str,
    normalized_reaction_id: str,
    conditions: list[str],
    mode_rows: list[dict[str, object]],
    delta_rows: list[dict[str, str]],
    context_knockout_rows: list[dict[str, str]],
    troppo_rows: list[dict[str, object]],
    ml_prior_rows: list[dict[str, object]],
    ml_lasso_lite_rows: list[dict[str, object]],
    uniprot_semantic_rows: list[dict[str, object]] | None = None,
    production_gecko_summary_rows: list[dict[str, object]] | None = None,
    production_gecko_target_rows: list[dict[str, object]] | None = None,
    production_gecko_design_rows: list[dict[str, object]] | None = None,
    production_readiness_summary_rows: list[dict[str, object]] | None = None,
    production_target_readiness_rows: list[dict[str, object]] | None = None,
    production_design_readiness_rows: list[dict[str, object]] | None = None,
    production_gene_readiness_rows: list[dict[str, object]] | None = None,
    kcat_prior_rows: list[dict[str, object]] | None = None,
    kcat_candidate_rows: list[dict[str, object]] | None = None,
    kcat_conflict_rows: list[dict[str, object]] | None = None,
    enzyme_capacity_rows: list[dict[str, object]] | None = None,
    enzyme_flux_capacity_rows: list[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    """Build compact per-condition interpretation rows for the queried reaction."""

    summary_conditions = conditions or ["ALL"]
    rows: list[dict[str, object]] = []
    for current_condition in summary_conditions:
        transcriptomics = _first_mode_row(mode_rows, current_condition, "transcriptomics")
        relative_proteomics = _first_mode_row(mode_rows, current_condition, "relative_proteomics")
        consensus = _first_mode_row(mode_rows, current_condition, "consensus")
        ml_derived = _first_mode_row(mode_rows, current_condition, "ml_derived") or _first_mode_row(mode_rows, "ALL", "ml_derived")
        delta = _first_for_condition(delta_rows, current_condition) or _first_for_condition(delta_rows, "ALL")
        context = _first_for_condition(context_knockout_rows, current_condition) or _first_for_condition(context_knockout_rows, "ALL")
        troppo = _first_for_condition(troppo_rows, current_condition) or _first_for_condition(troppo_rows, "ALL")
        semantic = (uniprot_semantic_rows or [{}])[0]
        gecko_summary = (production_gecko_summary_rows or [{}])[0]
        gecko_target = _first_for_condition(production_gecko_target_rows or [], current_condition) or _first_for_condition(
            production_gecko_target_rows or [],
            "ALL",
        )
        gecko_design_rows = _rows_for_condition(production_gecko_design_rows or [], current_condition)
        readiness_summary = (production_readiness_summary_rows or [{}])[0]
        readiness_targets = _rows_for_condition(production_target_readiness_rows or [], current_condition)
        readiness_designs = _rows_for_condition(production_design_readiness_rows or [], current_condition)
        readiness_genes = _rows_for_condition(production_gene_readiness_rows or [], current_condition)
        readiness_rows = [*readiness_targets, *readiness_designs, *readiness_genes]
        selected_kcat = _best_kcat_row(kcat_prior_rows or [])
        kcat_conflict = (kcat_conflict_rows or [{}])[0]
        selected_kcat_for_guidance = {
            **selected_kcat,
            "kcat_conflict_flag": kcat_conflict.get("flag", selected_kcat.get("kcat_conflict_flag", "")),
            "kcat_fold_range": kcat_conflict.get("fold_range", selected_kcat.get("kcat_fold_range", "")),
        }
        enzyme_capacities = _rows_for_condition(enzyme_capacity_rows or [], current_condition)
        enzyme_flux_checks = _rows_for_condition(enzyme_flux_capacity_rows or [], current_condition)
        enzyme_status = _enzyme_capacity_status(enzyme_capacities, enzyme_flux_checks)
        rows.append(
            {
                "condition": current_condition,
                "query": query,
                "normalized_reaction_id": normalized_reaction_id,
                "transcriptomics_evidence": transcriptomics.get("evidence", ""),
                "relative_proteomics_evidence": relative_proteomics.get("evidence", ""),
                "consensus_evidence": consensus.get("evidence", ""),
                "ml_derived_evidence": ml_derived.get("evidence", ""),
                "consensus_decision": consensus.get("context_decision", ""),
                "ml_derived_decision": ml_derived.get("context_decision", ""),
                "delta_status": delta.get("delta_status", ""),
                "in_context_knockout": bool(context),
                "troppo_membership": troppo.get("troppo_membership", ""),
                "semantic_label": semantic.get("semantic_label", ""),
                "gpr_flag": semantic.get("gpr_flag", ""),
                "reaction_annotation_flag": semantic.get("reaction_annotation_flag", ""),
                "uniprot_coverage_fraction": semantic.get("uniprot_coverage_fraction", ""),
                "gecko_bridge_status": gecko_summary.get("status", ""),
                "gecko_target_comparison_label": gecko_target.get("comparison_label", ""),
                "gecko_design_match_count": len(gecko_design_rows),
                "gecko_design_supported_count": sum(
                    1 for row in gecko_design_rows if row.get("comparison_label") == "supported_by_gecko_or_ecfactory"
                ),
                "gecko_design_conflict_count": sum(
                    1 for row in gecko_design_rows if row.get("comparison_label") == "action_conflict_review"
                ),
                "readiness_gate_status": readiness_summary.get("status", ""),
                "product_readiness_label": _best_or_first_readiness_label(readiness_targets),
                "design_readiness_match_count": len(readiness_designs),
                "gene_readiness_match_count": len(readiness_genes),
                "readiness_stronger_evidence_count": _readiness_count(readiness_rows, "stronger_evidence"),
                "readiness_review_required_count": _readiness_count(readiness_rows, "review_required"),
                "kcat_evidence_tier": selected_kcat.get("kcat_evidence_tier", ""),
                "selected_kcat_per_s": selected_kcat.get("kcat", ""),
                "kcat_source_tier": selected_kcat.get("source_tier", ""),
                "kcat_selection_status": selected_kcat.get("selection_status", ""),
                "kcat_candidate_count": len(kcat_candidate_rows or []),
                "kcat_conflict_flag": kcat_conflict.get("flag", selected_kcat.get("kcat_conflict_flag", "")),
                "kcat_fold_range": kcat_conflict.get("fold_range", selected_kcat.get("kcat_fold_range", "")),
                "enzyme_capacity_status": enzyme_status["status"],
                "enzyme_capacity_ready_count": enzyme_status["ready_count"],
                "enzyme_capacity_exceeds_count": enzyme_status["exceeds_count"],
                "enzyme_capacity_max_usage_fraction": enzyme_status["max_usage_fraction"],
                "ml_prior_count": len(ml_prior_rows),
                "ml_lasso_lite_count": len(ml_lasso_lite_rows),
                "guidance": _summary_guidance(
                    consensus,
                    ml_derived,
                    delta,
                    context,
                    troppo,
                    ml_prior_rows,
                    gecko_target,
                    gecko_design_rows,
                    readiness_rows,
                    selected_kcat_for_guidance,
                    enzyme_status,
                ),
            }
        )
    return rows


def normalize_reaction_id(reaction_id: str) -> str:
    """Normalize SBML/COBRA reaction ids for lookup."""

    text = str(reaction_id or "").strip()
    if text.lower().startswith("r_"):
        text = text[2:]
    return text.lower()


def normalize_gene_id(gene_id: str) -> str:
    """Normalize common SBML/COBRA gene id variants for lookup."""

    text = str(gene_id or "").strip()
    if text.lower().startswith("g_"):
        text = text[2:]
    return text.lower()


def extract_gpr_gene_ids(uniprot_gpr_rows: list[dict[str, str]]) -> set[str]:
    """Return gene ids referenced by the queried reaction's GPR rows."""

    return {
        gene.strip()
        for row in uniprot_gpr_rows
        for gene in str(row.get("genes", "")).split(";")
        if gene.strip()
    }


def _matching_rows(rows: list[dict[str, str]], normalized_reaction_id: str, condition: str = "") -> list[dict[str, str]]:
    matches = []
    for row in rows:
        if not _condition_matches(row, condition):
            continue
        row_ids = {
            normalize_reaction_id(row.get("reaction_id", "")),
            normalize_reaction_id(row.get("cobra_reaction_id", "")),
            normalize_reaction_id(row.get("model_reaction_id", "")),
            normalize_reaction_id(row.get("target_id", "")),
            normalize_reaction_id(row.get("model_target_id", "")),
        }
        if normalized_reaction_id in row_ids:
            matches.append(row)
    return matches


def _condition_matches(row: dict[str, object], condition: str = "") -> bool:
    row_condition = str(row.get("condition") or "default")
    return not condition or row_condition in {condition, "ALL"}


def _first_for_condition(rows: list[dict[str, str]], condition: str) -> dict[str, str]:
    for row in rows:
        if str(row.get("condition") or "default") == condition:
            return row
    return {}


def _rows_for_condition(rows: list[dict[str, object]], condition: str) -> list[dict[str, object]]:
    return [
        row
        for row in rows
        if str(row.get("condition") or "default") == condition or str(row.get("condition") or "") == "ALL"
    ]


def _first_mode_row(rows: list[dict[str, object]], condition: str, mode: str) -> dict[str, object]:
    for row in rows:
        if str(row.get("condition") or "default") == condition and row.get("evidence_mode") == mode:
            return row
    return {}


def _ml_prior_matches_reaction(row: dict[str, str], normalized_reaction_id: str) -> bool:
    if str(row.get("target_type", "")) == "reaction":
        row_ids = {
            normalize_reaction_id(row.get("model_target_id", "")),
            normalize_reaction_id(row.get("target_id", "")),
        }
        if normalized_reaction_id in row_ids:
            return True
    return (
        _feature_matches_reaction(row.get("source_feature_id", ""), normalized_reaction_id)
        or _feature_matches_reaction(row.get("target_feature_id", ""), normalized_reaction_id)
    )


def _feature_matches_reaction(feature_id: str, normalized_reaction_id: str) -> bool:
    text = str(feature_id or "")
    if "::" not in text:
        return False
    feature_type, entity_id = text.split("::", 1)
    reaction_like_types = ("reaction", "flux")
    if not any(token in feature_type for token in reaction_like_types):
        return False
    return normalize_reaction_id(entity_id) == normalized_reaction_id


def production_gecko_design_match_reason(
    row: dict[str, object],
    normalized_reaction_id: str,
    normalized_gene_ids: set[str],
) -> str:
    """Return why a GECKO/ecFactory design row belongs in this reaction lookup."""

    if normalize_reaction_id(row.get("product_reaction_id", "")) == normalized_reaction_id:
        return "product_reaction"
    target_level = str(row.get("target_level", "")).lower()
    candidate_id = str(row.get("candidate_id", ""))
    if target_level == "gene":
        if normalize_gene_id(candidate_id) in normalized_gene_ids:
            return "gpr_gene_target"
        return ""
    if normalize_reaction_id(candidate_id) == normalized_reaction_id:
        return "candidate_reaction"
    return ""


def readiness_product_matches(row: dict[str, object], normalized_reaction_id: str) -> bool:
    return normalized_reaction_id in {
        normalize_reaction_id(row.get("product_reaction_id", "")),
        normalize_reaction_id(row.get("model_product_reaction_id", "")),
    }


def production_design_readiness_match_reason(
    row: dict[str, object],
    normalized_reaction_id: str,
) -> str:
    if readiness_product_matches(row, normalized_reaction_id):
        return "product_reaction"
    if normalize_reaction_id(row.get("candidate_reaction_id", "")) == normalized_reaction_id:
        return "candidate_reaction"
    return ""


def production_gene_readiness_match_reason(
    row: dict[str, object],
    normalized_reaction_id: str,
    normalized_gene_ids: set[str],
    normalized_query_gene_id: str,
) -> str:
    if readiness_product_matches(row, normalized_reaction_id):
        return "product_reaction"
    supporting_reactions = {
        normalize_reaction_id(reaction)
        for reaction in str(row.get("supporting_reactions", "")).split(";")
        if reaction.strip()
    }
    if normalized_reaction_id in supporting_reactions:
        return "supporting_reaction"
    gene_id = normalize_gene_id(row.get("gene_id", ""))
    if gene_id and gene_id in normalized_gene_ids:
        return "gpr_gene_target"
    if gene_id and gene_id == normalized_query_gene_id:
        return "gene_query"
    return ""


def _best_or_first_readiness_label(rows: list[dict[str, object]]) -> str:
    labels = [str(row.get("production_readiness_label", "")) for row in rows if row.get("production_readiness_label")]
    if not labels:
        return ""
    priority = {
        "review_required": 0,
        "stronger_evidence": 1,
        "usable_with_caution": 2,
        "guidance_only": 3,
    }
    labels.sort(key=lambda label: priority.get(label, 99))
    return labels[0]


def _readiness_count(rows: list[dict[str, object]], label: str) -> int:
    return sum(1 for row in rows if row.get("production_readiness_label") == label)


def _best_kcat_row(rows: list[dict[str, object]]) -> dict[str, object]:
    selected = [row for row in rows if row.get("selection_status") == "selected"]
    candidates = selected or rows
    if not candidates:
        return {}
    return sorted(
        candidates,
        key=lambda row: (_to_float(row.get("kcat_evidence_rank")) or 0, _to_float(row.get("confidence")) or 0),
        reverse=True,
    )[0]


def _enzyme_capacity_status(
    capacity_rows: list[dict[str, object]],
    flux_rows: list[dict[str, object]],
) -> dict[str, object]:
    ready_count = sum(1 for row in capacity_rows if row.get("status") == "ready")
    exceeds_count = sum(1 for row in flux_rows if row.get("status") == "exceeds_capacity")
    usage_values = [_to_float(row.get("usage_fraction")) for row in flux_rows]
    usage_values = [value for value in usage_values if value is not None]
    if exceeds_count:
        status = "capacity_exceeded"
    elif ready_count:
        status = "ready"
    elif capacity_rows:
        status = str(capacity_rows[0].get("status") or "not_ready")
    elif flux_rows:
        status = str(flux_rows[0].get("status") or "not_ready")
    else:
        status = ""
    return {
        "status": status,
        "ready_count": ready_count,
        "exceeds_count": exceeds_count,
        "max_usage_fraction": max(usage_values) if usage_values else "",
    }


def _to_float(value: object) -> float | None:
    if value in {"", None}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _summary_guidance(
    consensus: dict[str, object],
    ml_derived: dict[str, object],
    delta: dict[str, str],
    context: dict[str, str],
    troppo: dict[str, object],
    ml_prior_rows: list[dict[str, object]],
    gecko_target: dict[str, object] | None = None,
    gecko_design_rows: list[dict[str, object]] | None = None,
    readiness_rows: list[dict[str, object]] | None = None,
    selected_kcat: dict[str, object] | None = None,
    enzyme_status: dict[str, object] | None = None,
) -> str:
    gecko_target = gecko_target or {}
    gecko_design_rows = gecko_design_rows or []
    readiness_rows = readiness_rows or []
    selected_kcat = selected_kcat or {}
    enzyme_status = enzyme_status or {}
    if enzyme_status.get("exceeds_count"):
        return "Enzyme-capacity check flags this reaction as exceeding capacity; review kcat source, protein abundance, and predicted flux together."
    if selected_kcat.get("kcat_conflict_flag") == "kcat_conflict_review":
        return "kcat candidate values conflict strongly for this reaction; review sources before using enzyme or hybrid interpretation."
    if any(row.get("production_readiness_label") == "review_required" for row in readiness_rows):
        return "Production readiness gate marks this target as review_required; inspect semantic, growth, and enzyme-constrained evidence before prioritization."
    if any(row.get("production_readiness_label") == "stronger_evidence" for row in readiness_rows):
        return "Production readiness gate found stronger_evidence for this target; inspect matched product/reaction/gene rows for the evidence chain."
    if readiness_rows:
        return "Production readiness rows matched this reaction; use the readiness labels to interpret production-design confidence."
    if selected_kcat and enzyme_status.get("status") == "ready":
        return "Selected kcat prior and enzyme-capacity rows are available; this reaction can be interpreted with enzyme-capacity context."
    if selected_kcat:
        return "Selected kcat prior is available, but enzyme-capacity evidence is incomplete for this condition."
    if any(row.get("comparison_label") == "action_conflict_review" for row in gecko_design_rows):
        return "GECKO/ecFactory comparison reports an action conflict for this target; review enzyme constraints before prioritizing it."
    if gecko_target.get("comparison_label") == "enzyme_constraint_blocks_cobra_target":
        return "COBRApy predicts product potential here, but enzyme-constrained output blocks it; treat the production target as high-review."
    if gecko_target or gecko_design_rows:
        return "GECKO/ecFactory comparison rows are available for this reaction; use them to qualify COBRApy-only production suggestions."
    delta_status = str(delta.get("delta_status", ""))
    if delta_status == "ml_consensus_disagreement":
        return "ML-derived prior disagrees with consensus; treat as a review hypothesis, not a hard edit."
    if delta_status == "ml_soft_prior_added":
        return "Only ML-derived soft evidence is available here; keep interpretation exploratory."
    if context:
        return "Reaction appears in context knockout/delete-candidate output; inspect feasibility before removal."
    if troppo.get("troppo_membership") == "selected":
        return "TROPPO selected this reaction, usually because evidence or protected context supports it."
    consensus_evidence = str(consensus.get("evidence", ""))
    ml_evidence = str(ml_derived.get("evidence", ""))
    if ml_prior_rows and not ml_evidence:
        return "Raw ML prior rows involve this reaction, but no ML-derived evidence-mode row was generated."
    if consensus_evidence and ml_evidence and consensus_evidence == ml_evidence:
        return "Consensus and ML-derived evidence point in the same direction."
    if consensus_evidence:
        return "Consensus evidence is available; compare with omics mode details before changing constraints."
    if ml_prior_rows:
        return "ML prior evidence is available; use it as soft exploratory support."
    return "No strong downstream interpretation row was found for this reaction."


def _semantic_label(gpr: dict[str, str], reaction: dict[str, str]) -> str:
    gpr_flag = str(gpr.get("flag", ""))
    reaction_flag = str(reaction.get("flag", ""))
    severities = {str(gpr.get("severity", "")), str(reaction.get("severity", ""))}
    if "high" in severities or reaction_flag == "ec_mismatch_review" or gpr_flag == "missing_gpr":
        return "review_required"
    if reaction_flag in {"annotation_missing", "inconclusive"} or reaction.get("status") == "inconclusive":
        return "inconclusive"
    if gpr_flag in {"partial_uniprot_annotation", "gpr_without_uniprot_annotation"}:
        return "usable_with_caution"
    if reaction_flag in {"reaction_ec_missing", "gene_ec_missing"}:
        return "usable_with_caution"
    if gpr or reaction:
        return "usable"
    return ""


def _semantic_guidance(label: str, gpr: dict[str, str], reaction: dict[str, str]) -> str:
    if label == "review_required":
        if reaction.get("flag") == "ec_mismatch_review":
            return "Reaction-level and gene-level EC annotations disagree; review before using this reaction in optimization claims."
        if gpr.get("flag") == "missing_gpr":
            return "Reaction has no GPR, so omics-derived gene evidence cannot directly support it."
        return "High-risk semantic QC flag is present; inspect GPR and annotation before downstream edits."
    if label == "inconclusive":
        return "Local annotation is missing or insufficient; absence of evidence should not be treated as a model error."
    if label == "usable_with_caution":
        return "Some annotation is available, but coverage is partial; use as supportive context rather than hard evidence."
    if label == "usable":
        return "GPR/annotation check does not show a high-risk local conflict for this reaction."
    return ""


def _read_optional(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return read_csv_records(path)
