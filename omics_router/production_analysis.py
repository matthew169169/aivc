"""COBRApy-only production analysis and ecFactory-lite staging outputs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cobra_runner import (
    _redirect_cobra_cache,
    apply_exchange_bounds,
    cobrapy_available,
    get_cobra_reaction,
    group_by_condition,
)
from .constraints import parse_sbml_gpr_rules, parse_sbml_index, read_csv_records, write_csv, write_json


DEFAULT_BIOMASS_FRACTIONS = [0.0, 0.25, 0.5, 0.75, 0.9]
DEFAULT_FSEOF_FRACTIONS = [0.0, 0.25, 0.5, 0.75, 0.9]
MAX_FSEOF_CANDIDATES = 200
MAX_GROWTH_IMPACT_CANDIDATES = 80
PRODUCTION_TARGET_COLUMNS = ["condition", "reaction_id", "product_name", "target_type", "priority", "source", "note"]
PRODUCTION_DESIGN_COLUMNS = [
    "condition",
    "product_reaction_id",
    "product_name",
    "design_rank",
    "candidate_reaction_id",
    "recommended_action",
    "action_confidence",
    "intervention_score",
    "growth_loss_label",
    "growth_loss_fraction",
    "baseline_growth",
    "knockout_growth",
    "trend_slope",
    "baseline_flux",
    "final_flux",
    "semantic_label",
    "filter_status",
    "design_guidance",
]
PRODUCTION_GENE_TARGET_COLUMNS = [
    "condition",
    "product_reaction_id",
    "product_name",
    "gene_rank",
    "gene_id",
    "recommended_action",
    "action_confidence",
    "gene_target_score",
    "supporting_reaction_count",
    "supporting_reactions",
    "gpr_rule_count",
    "gpr_design_scope",
    "growth_loss_label",
    "semantic_label",
    "gene_mapping_status",
    "design_guidance",
]
PACKAGE_INPUT_MAP_COLUMNS = [
    "kind",
    "role",
    "original_name",
    "saved_name",
    "path",
    "relative_path",
    "size_bytes",
    "columns",
    "inspection_status",
    "details",
]


@dataclass(slots=True)
class ProductionAnalysisResult:
    """Summary returned by the optional production analysis workflow."""

    cobra_available: bool
    status: str
    output_dir: str
    message: str
    files: dict[str, str]


def locate_package_model_path(package_dir: str | Path) -> Path | None:
    """Return the staged GEM path for a user run package if one is mapped."""

    package = Path(package_dir)
    for row in _safe_read_csv(package / "input_file_map.csv"):
        if row.get("kind") != "model":
            continue
        path = _resolve_package_path(package, row)
        if path is not None:
            return path
    manifest_path = package / "upload_manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
        model_row = manifest.get("model") if isinstance(manifest, dict) else None
        if isinstance(model_row, dict):
            path = _resolve_package_path(package, model_row)
            if path is not None:
                return path
    return None


def infer_production_target_candidates(
    model_path: str | Path,
    include_low_confidence: bool = False,
    max_rows: int = 500,
) -> list[dict[str, object]]:
    """Infer exchange/demand/sink-like production target candidates from an SBML model."""

    reactions: list[tuple[str, str]] = []
    try:
        rules = parse_sbml_gpr_rules(model_path)
        reactions = [(reaction_id, rule.name) for reaction_id, rule in rules.items()]
    except Exception:
        try:
            model_index = parse_sbml_index(model_path)
            reactions = [(reaction_id, "") for reaction_id in sorted(model_index.reactions)]
        except Exception:
            return []

    candidates: list[dict[str, object]] = []
    low_confidence_rows: list[dict[str, object]] = []
    for reaction_id, reaction_name in reactions:
        candidate_type, confidence, reason = classify_production_candidate(reaction_id, reaction_name)
        row = {
            "selected": False,
            "reaction_id": reaction_id,
            "cobra_reaction_id": _cobra_reaction_id(reaction_id),
            "reaction_name": reaction_name,
            "product_name_hint": product_name_hint(reaction_id, reaction_name),
            "target_type": candidate_type,
            "confidence": confidence,
            "reason": reason,
        }
        if confidence in {"high", "medium"}:
            candidates.append(row)
        elif include_low_confidence:
            low_confidence_rows.append(row)

    candidates.sort(key=_production_candidate_sort_key)
    if not candidates and low_confidence_rows:
        candidates = low_confidence_rows
    elif include_low_confidence:
        candidates.extend(sorted(low_confidence_rows, key=_production_candidate_sort_key))
    return candidates[:max_rows]


def build_production_target_rows(
    selected_rows: list[dict[str, object]],
    condition: str = "ALL",
    priority: str = "medium",
    source: str = "streamlit_target_builder",
) -> list[dict[str, object]]:
    """Build a stable production_targets table from selected candidate rows."""

    target_rows: list[dict[str, object]] = []
    for row in selected_rows:
        reaction_id = str(row.get("reaction_id") or row.get("model_reaction_id") or "").strip()
        if not reaction_id:
            continue
        target_rows.append(
            {
                "condition": str(row.get("condition") or condition or "ALL"),
                "reaction_id": reaction_id,
                "product_name": str(row.get("product_name") or row.get("product_name_hint") or reaction_id),
                "target_type": str(row.get("target_type") or "product_exchange"),
                "priority": str(row.get("priority") or priority),
                "source": str(row.get("source") or source),
                "note": str(row.get("note") or row.get("reason") or ""),
            }
        )
    return _align_rows_to_columns(target_rows, PRODUCTION_TARGET_COLUMNS)


def write_production_targets_to_package(
    package_dir: str | Path,
    rows: list[dict[str, object]],
    filename: str = "production_targets_from_ui.csv",
    replace_existing: bool = True,
) -> Path:
    """Write UI-generated production targets and register them in the package input map."""

    package = Path(package_dir)
    target_dir = package / "inputs" / "omics"
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / filename
    aligned_rows = _align_rows_to_columns(rows, PRODUCTION_TARGET_COLUMNS)
    write_csv(path, aligned_rows)

    input_map_path = package / "input_file_map.csv"
    input_rows = _safe_read_csv(input_map_path)
    if replace_existing:
        input_rows = [row for row in input_rows if row.get("role") != "production_targets"]
    map_row = {
        "kind": "omics_table",
        "role": "production_targets",
        "original_name": filename,
        "saved_name": filename,
        "path": str(path),
        "relative_path": str(path.relative_to(package)),
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "columns": ";".join(PRODUCTION_TARGET_COLUMNS),
        "inspection_status": "ok",
        "details": "generated by Production Target Builder",
    }
    input_rows.append(map_row)
    write_csv(input_map_path, _align_rows_to_columns(input_rows, PACKAGE_INPUT_MAP_COLUMNS))
    _update_upload_manifest_with_production_targets(package, map_row, replace_existing=replace_existing)
    return path


def run_production_analysis(
    model_path: str | Path,
    exchange_bounds_path: str | Path,
    production_targets_path: str | Path,
    output_dir: str | Path,
    uniprot_model_check_dir: str | Path | None = None,
    require_cobra: bool = False,
    biomass_fractions: list[float] | None = None,
    fseof_fractions: list[float] | None = None,
    max_fseof_candidates: int = MAX_FSEOF_CANDIDATES,
    max_growth_impact_candidates: int = MAX_GROWTH_IMPACT_CANDIDATES,
) -> ProductionAnalysisResult:
    """Run production envelope and FSEOF-lite for configured product targets."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = production_output_files(output)
    targets = (
        normalize_production_targets(read_csv_records(production_targets_path))
        if Path(production_targets_path).exists() and Path(production_targets_path).stat().st_size > 0
        else []
    )
    semantic_labels = load_semantic_labels(uniprot_model_check_dir) if uniprot_model_check_dir else {}

    if not targets:
        return write_production_outputs(
            files,
            cobra_available=cobrapy_available(),
            status="skipped_no_targets",
            message="No production_targets table is configured; skipped production analysis.",
            model_path=model_path,
            exchange_bounds_path=exchange_bounds_path,
            production_targets_path=production_targets_path,
            semantic_labels=semantic_labels,
        )

    if not cobrapy_available():
        message = "COBRApy is not installed; skipped production analysis execution."
        if require_cobra:
            raise RuntimeError(message)
        return write_production_outputs(
            files,
            cobra_available=False,
            status="skipped_cobra_missing",
            message=message,
            model_path=model_path,
            exchange_bounds_path=exchange_bounds_path,
            production_targets_path=production_targets_path,
            semantic_labels=semantic_labels,
            target_count=len(targets),
        )

    _redirect_cobra_cache()
    from cobra.io import read_sbml_model

    model = read_sbml_model(str(model_path))
    exchange_by_condition = group_by_condition(read_csv_records(exchange_bounds_path))
    conditions = sorted(exchange_by_condition) or ["default"]
    expanded_targets = expand_targets_by_condition(targets, conditions)
    biomass_fractions = biomass_fractions or DEFAULT_BIOMASS_FRACTIONS
    fseof_fractions = fseof_fractions or DEFAULT_FSEOF_FRACTIONS

    envelope_rows: list[dict[str, object]] = []
    trend_rows: list[dict[str, object]] = []
    for condition in sorted(expanded_targets):
        bounds = exchange_by_condition.get(condition, [])
        for target in expanded_targets[condition]:
            envelope_rows.extend(
                build_production_envelope_for_target(
                    model,
                    condition=condition,
                    bounds=bounds,
                    target=target,
                    biomass_fractions=biomass_fractions,
                    semantic_labels=semantic_labels,
                )
            )
            trend_rows.extend(
                build_fseof_lite_for_target(
                    model,
                    condition=condition,
                    bounds=bounds,
                    target=target,
                    fseof_fractions=fseof_fractions,
                    semantic_labels=semantic_labels,
                    max_fseof_candidates=max_fseof_candidates,
                    max_growth_impact_candidates=max_growth_impact_candidates,
                )
            )

    design_rows = build_production_design_targets(trend_rows)
    gene_target_rows = build_production_gene_targets(design_rows, model_path)
    ranking_rows = build_production_target_ranking(envelope_rows, design_rows, semantic_labels)
    summary_rows = [
        build_production_summary(
            status="completed",
            message=f"Completed production analysis for {len(expanded_targets)} condition groups.",
            target_count=len(targets),
            envelope_rows=envelope_rows,
            trend_rows=trend_rows,
            design_rows=design_rows,
            gene_target_rows=gene_target_rows,
            ranking_rows=ranking_rows,
        )
    ]
    write_csv(files["summary"], summary_rows)
    write_csv(files["production_targets"], targets)
    write_csv(files["production_envelope"], envelope_rows)
    write_csv(files["production_target_ranking"], ranking_rows)
    write_csv(files["fseof_lite_reaction_targets"], trend_rows)
    write_csv(files["production_design_targets"], design_rows)
    write_csv(files["production_gene_targets"], gene_target_rows)
    write_json(
        files["manifest"],
        {
            "schema_version": "0.2.0",
            "cobra_available": True,
            "status": "completed",
            "model_path": str(model_path),
            "exchange_bounds_path": str(exchange_bounds_path),
            "production_targets_path": str(production_targets_path),
            "biomass_fractions": biomass_fractions,
            "fseof_fractions": fseof_fractions,
            "max_fseof_candidates": max_fseof_candidates,
            "max_growth_impact_candidates": max_growth_impact_candidates,
            "design_candidate_count": len(design_rows),
            "gene_target_count": len(gene_target_rows),
            "files": files,
        },
    )
    return ProductionAnalysisResult(
        cobra_available=True,
        status="completed",
        output_dir=str(output),
        message=f"Completed production analysis for {len(targets)} product target rows.",
        files=files,
    )


def build_production_envelope_for_target(
    model: Any,
    condition: str,
    bounds: list[dict[str, str]],
    target: dict[str, object],
    biomass_fractions: list[float],
    semantic_labels: dict[str, dict[str, str]],
) -> list[dict[str, object]]:
    """Maximize product secretion under increasing growth requirements."""

    rows: list[dict[str, object]] = []
    target_reaction_id = str(target.get("model_reaction_id") or target.get("reaction_id") or "")
    with model:
        applied, failed = apply_exchange_bounds(model, bounds)
        baseline_solution = model.optimize()
        baseline_status = str(getattr(baseline_solution, "status", "unknown"))
        baseline_objective = _safe_float(getattr(baseline_solution, "objective_value", None))
        objective_reaction = primary_objective_reaction(model)
        for fraction in biomass_fractions:
            with model:
                apply_exchange_bounds(model, bounds)
                target_reaction = _safe_get_reaction(model, target_reaction_id)
                if objective_reaction is not None and baseline_objective is not None:
                    current_objective = get_cobra_reaction(model, objective_reaction.id)
                    requirement = max(0.0, baseline_objective * fraction)
                    current_objective.lower_bound = max(current_objective.lower_bound, requirement)
                else:
                    requirement = None
                if target_reaction is not None:
                    model.objective = target_reaction
                    solution = model.optimize()
                    solve_status = str(getattr(solution, "status", "unknown"))
                    product_flux = _safe_float(getattr(solution, "objective_value", None))
                    cobra_reaction_id = target_reaction.id
                else:
                    solve_status = "target_reaction_not_found"
                    product_flux = None
                    cobra_reaction_id = ""
                semantic = semantic_for_reaction(target_reaction_id, semantic_labels)
                rows.append(
                    {
                        "condition": condition,
                        "product_reaction_id": target.get("reaction_id", target_reaction_id),
                        "model_product_reaction_id": target_reaction_id,
                        "cobra_product_reaction_id": cobra_reaction_id,
                        "product_name": target.get("product_name", ""),
                        "biomass_fraction": fraction,
                        "baseline_status": baseline_status,
                        "baseline_objective_value": baseline_objective,
                        "min_growth_requirement": requirement,
                        "max_product_flux": product_flux,
                        "solve_status": solve_status,
                        "exchange_bounds_applied": applied,
                        "exchange_bounds_failed": failed,
                        "semantic_label": semantic.get("semantic_label", ""),
                        "semantic_warning": semantic.get("semantic_warning", ""),
                    }
                )
    return rows


def build_fseof_lite_for_target(
    model: Any,
    condition: str,
    bounds: list[dict[str, str]],
    target: dict[str, object],
    fseof_fractions: list[float],
    semantic_labels: dict[str, dict[str, str]],
    max_fseof_candidates: int = MAX_FSEOF_CANDIDATES,
    max_growth_impact_candidates: int = MAX_GROWTH_IMPACT_CANDIDATES,
) -> list[dict[str, object]]:
    """Run an FSEOF-like scan by enforcing fractions of maximum product flux."""

    target_reaction_id = str(target.get("model_reaction_id") or target.get("reaction_id") or "")
    max_product = maximize_product_flux(model, bounds, target_reaction_id)
    if max_product is None or max_product <= 0:
        return []

    baseline_growth = baseline_growth_for_condition(model, bounds)
    flux_by_reaction: dict[str, list[tuple[float, float]]] = {}
    status_by_fraction: dict[float, str] = {}
    for fraction in fseof_fractions:
        with model:
            apply_exchange_bounds(model, bounds)
            target_reaction = _safe_get_reaction(model, target_reaction_id)
            if target_reaction is None:
                status_by_fraction[fraction] = "target_reaction_not_found"
                continue
            target_reaction.lower_bound = max(target_reaction.lower_bound, max_product * fraction)
            solution = model.optimize()
            status = str(getattr(solution, "status", "unknown"))
            status_by_fraction[fraction] = status
            if status != "optimal":
                continue
            for reaction_id, value in solution.fluxes.items():
                flux_by_reaction.setdefault(str(reaction_id), []).append((fraction, float(value)))

    rows: list[dict[str, object]] = []
    for reaction_id, points in flux_by_reaction.items():
        if len(points) < 2:
            continue
        slope = linear_slope([point[0] for point in points], [point[1] for point in points])
        if abs(slope) < 1e-9:
            continue
        first_flux = points[0][1]
        last_flux = points[-1][1]
        action = "OE_candidate" if slope > 0 else "KD_candidate"
        semantic = semantic_for_reaction(reaction_id, semantic_labels)
        rows.append(
            {
                "condition": condition,
                "product_reaction_id": target.get("reaction_id", target_reaction_id),
                "model_product_reaction_id": target_reaction_id,
                "product_name": target.get("product_name", ""),
                "candidate_reaction_id": reaction_id,
                "candidate_action": action,
                "trend_slope": slope,
                "baseline_flux": first_flux,
                "final_flux": last_flux,
                "feasible_points": len(points),
                "max_product_flux": max_product,
                "semantic_label": semantic.get("semantic_label", ""),
                "semantic_warning": semantic.get("semantic_warning", ""),
                "status": "fseof_lite_candidate",
            }
        )
    rows.sort(key=lambda row: abs(float(row["trend_slope"])), reverse=True)
    rows = rows[:max(1, int(max_fseof_candidates or MAX_FSEOF_CANDIDATES))]
    for index, row in enumerate(rows, start=1):
        if index <= max(0, int(max_growth_impact_candidates or 0)):
            growth_impact = estimate_knockout_growth_impact(
                model=model,
                bounds=bounds,
                candidate_reaction_id=str(row.get("candidate_reaction_id", "")),
                baseline_growth=baseline_growth,
            )
        else:
            growth_impact = {
                "baseline_growth": baseline_growth,
                "knockout_growth": None,
                "growth_loss_fraction": None,
                "growth_loss_label": "not_checked",
            }
        row.update(
            build_intervention_annotation(
                row=row,
                target_reaction_id=target_reaction_id,
                growth_impact=growth_impact,
            )
        )
    rows.sort(key=lambda row: (_safe_float(row.get("intervention_score")) or 0.0, abs(_safe_float(row.get("trend_slope")) or 0.0)), reverse=True)
    for index, row in enumerate(rows, start=1):
        row["candidate_rank"] = index
    return rows


def maximize_product_flux(model: Any, bounds: list[dict[str, str]], reaction_id: str) -> float | None:
    """Maximize the product reaction under condition bounds."""

    with model:
        apply_exchange_bounds(model, bounds)
        reaction = _safe_get_reaction(model, reaction_id)
        if reaction is None:
            return None
        model.objective = reaction
        solution = model.optimize()
        if str(getattr(solution, "status", "")) != "optimal":
            return None
        return _safe_float(getattr(solution, "objective_value", None))


def baseline_growth_for_condition(model: Any, bounds: list[dict[str, str]]) -> float | None:
    """Solve the model objective under condition bounds."""

    with model:
        apply_exchange_bounds(model, bounds)
        solution = model.optimize()
        if str(getattr(solution, "status", "")) != "optimal":
            return None
        return _safe_float(getattr(solution, "objective_value", None))


def estimate_knockout_growth_impact(
    model: Any,
    bounds: list[dict[str, str]],
    candidate_reaction_id: str,
    baseline_growth: float | None,
) -> dict[str, object]:
    """Estimate growth loss from constraining a candidate reaction to zero."""

    knockout_growth = None
    with model:
        apply_exchange_bounds(model, bounds)
        reaction = _safe_get_reaction(model, candidate_reaction_id)
        if reaction is None:
            return {
                "baseline_growth": baseline_growth,
                "knockout_growth": None,
                "growth_loss_fraction": None,
                "growth_loss_label": "reaction_not_found",
            }
        try:
            reaction.bounds = (0.0, 0.0)
        except Exception:
            reaction.lower_bound = min(reaction.lower_bound, 0.0)
            reaction.upper_bound = max(reaction.upper_bound, 0.0)
            reaction.bounds = (0.0, 0.0)
        solution = model.optimize()
        if str(getattr(solution, "status", "")) == "optimal":
            knockout_growth = _safe_float(getattr(solution, "objective_value", None))
    loss_fraction = growth_loss_fraction(baseline_growth, knockout_growth)
    return {
        "baseline_growth": baseline_growth,
        "knockout_growth": knockout_growth,
        "growth_loss_fraction": loss_fraction,
        "growth_loss_label": classify_growth_loss(baseline_growth, knockout_growth),
    }


def build_intervention_annotation(
    row: dict[str, object],
    target_reaction_id: str,
    growth_impact: dict[str, object],
) -> dict[str, object]:
    """Convert an FSEOF trend row into a ranked intervention suggestion."""

    candidate_id = str(row.get("candidate_reaction_id", ""))
    is_product_reaction = normalize_reaction_id(candidate_id) == normalize_reaction_id(target_reaction_id)
    recommended_action = recommend_intervention_action(
        candidate_action=str(row.get("candidate_action", "")),
        growth_loss_label=str(growth_impact.get("growth_loss_label", "")),
        is_product_reaction=is_product_reaction,
    )
    action_confidence = intervention_confidence(recommended_action, str(growth_impact.get("growth_loss_label", "")), row)
    score = intervention_score(
        trend_slope=_safe_float(row.get("trend_slope")),
        feasible_points=_safe_float(row.get("feasible_points")),
        recommended_action=recommended_action,
        action_confidence=action_confidence,
        growth_loss_label=str(growth_impact.get("growth_loss_label", "")),
        semantic_label=str(row.get("semantic_label", "")),
    )
    filter_status = intervention_filter_status(
        recommended_action=recommended_action,
        growth_loss_label=str(growth_impact.get("growth_loss_label", "")),
        semantic_label=str(row.get("semantic_label", "")),
        is_product_reaction=is_product_reaction,
    )
    return {
        "recommended_action": recommended_action,
        "action_confidence": action_confidence,
        "intervention_score": round(score, 6),
        "baseline_growth": growth_impact.get("baseline_growth"),
        "knockout_growth": growth_impact.get("knockout_growth"),
        "growth_loss_fraction": growth_impact.get("growth_loss_fraction"),
        "growth_loss_label": growth_impact.get("growth_loss_label", ""),
        "filter_status": filter_status,
        "design_guidance": intervention_guidance(recommended_action, str(growth_impact.get("growth_loss_label", "")), filter_status),
    }


def build_production_design_targets(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Build the user-facing KO/KD/OE target ranking table from enriched FSEOF rows."""

    ranked: list[dict[str, object]] = []
    for row in rows:
        if row.get("recommended_action") in {"", "do_not_rank"}:
            continue
        if row.get("filter_status") == "excluded_product_reaction":
            continue
        ranked.append(row)
    ranked.sort(
        key=lambda row: (
            _safe_float(row.get("intervention_score")) or 0.0,
            abs(_safe_float(row.get("trend_slope")) or 0.0),
        ),
        reverse=True,
    )
    design_rows: list[dict[str, object]] = []
    for index, row in enumerate(ranked, start=1):
        design_rows.append(
            {
                "condition": row.get("condition", ""),
                "product_reaction_id": row.get("product_reaction_id", ""),
                "product_name": row.get("product_name", ""),
                "design_rank": index,
                "candidate_reaction_id": row.get("candidate_reaction_id", ""),
                "recommended_action": row.get("recommended_action", ""),
                "action_confidence": row.get("action_confidence", ""),
                "intervention_score": row.get("intervention_score", ""),
                "growth_loss_label": row.get("growth_loss_label", ""),
                "growth_loss_fraction": row.get("growth_loss_fraction", ""),
                "baseline_growth": row.get("baseline_growth", ""),
                "knockout_growth": row.get("knockout_growth", ""),
                "trend_slope": row.get("trend_slope", ""),
                "baseline_flux": row.get("baseline_flux", ""),
                "final_flux": row.get("final_flux", ""),
                "semantic_label": row.get("semantic_label", ""),
                "filter_status": row.get("filter_status", ""),
                "design_guidance": row.get("design_guidance", ""),
            }
        )
    return _align_rows_to_columns(design_rows, PRODUCTION_DESIGN_COLUMNS)


def build_production_gene_targets(
    design_rows: list[dict[str, object]],
    model_path: str | Path,
) -> list[dict[str, object]]:
    """Aggregate reaction-level production design candidates to GPR gene targets."""

    if not design_rows:
        return []
    try:
        gpr_rules = parse_sbml_gpr_rules(model_path)
    except Exception:
        gpr_rules = {}
    rules_by_reaction = {normalize_reaction_id(reaction_id): rule for reaction_id, rule in gpr_rules.items()}
    grouped: dict[tuple[str, str, str, str], dict[str, object]] = {}
    for row in design_rows:
        candidate_reaction = str(row.get("candidate_reaction_id", ""))
        rule = rules_by_reaction.get(normalize_reaction_id(candidate_reaction))
        genes = list(rule.genes) if rule is not None else []
        if not genes:
            key = gene_target_key(row, "")
            current = grouped.setdefault(key, empty_gene_target_group(row, gene_id="", scope="no_gpr", mapping_status="no_gpr"))
            merge_gene_target_support(current, row, candidate_reaction, gpr_rule_text(rule))
            continue
        scope = classify_gpr_design_scope(rule.rule_text, len(genes))
        for gene_id in genes:
            key = gene_target_key(row, gene_id)
            current = grouped.setdefault(
                key,
                empty_gene_target_group(row, gene_id=gene_id, scope=scope, mapping_status="mapped"),
            )
            merge_gene_target_support(current, row, candidate_reaction, rule.rule_text)

    rows = [finalize_gene_target_group(group) for group in grouped.values()]
    rows.sort(
        key=lambda row: (
            str(row.get("gene_mapping_status", "")) != "mapped",
            -(_safe_float(row.get("gene_target_score")) or 0.0),
            str(row.get("gene_id", "")),
        )
    )
    for index, row in enumerate(rows, start=1):
        row["gene_rank"] = index
    return _align_rows_to_columns(rows, PRODUCTION_GENE_TARGET_COLUMNS)


def build_production_target_ranking(
    envelope_rows: list[dict[str, object]],
    trend_rows: list[dict[str, object]],
    semantic_labels: dict[str, dict[str, str]],
) -> list[dict[str, object]]:
    """Summarize product target potential and FSEOF-lite candidates."""

    grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in envelope_rows:
        key = (str(row.get("condition", "")), str(row.get("model_product_reaction_id", "")))
        grouped.setdefault(key, []).append(row)

    trend_grouped: dict[tuple[str, str], list[dict[str, object]]] = {}
    for row in trend_rows:
        key = (str(row.get("condition", "")), str(row.get("model_product_reaction_id", "")))
        trend_grouped.setdefault(key, []).append(row)

    rankings: list[dict[str, object]] = []
    for (condition, reaction_id), rows in sorted(grouped.items()):
        product_name = str(rows[0].get("product_name", ""))
        max_at_zero = value_at_fraction(rows, 0.0)
        max_at_half = value_at_fraction(rows, 0.5)
        max_at_high = value_at_fraction(rows, 0.9)
        candidates = trend_grouped.get((condition, reaction_id), [])
        semantic = semantic_for_reaction(reaction_id, semantic_labels)
        oe_count = sum(1 for row in candidates if row.get("recommended_action") == "OE" or row.get("candidate_action") == "OE_candidate")
        kd_count = sum(1 for row in candidates if row.get("recommended_action") == "KD" or row.get("candidate_action") == "KD_candidate")
        ko_count = sum(1 for row in candidates if row.get("recommended_action") == "KO")
        recommended_count = sum(1 for row in candidates if row.get("filter_status") == "recommended")
        rankings.append(
            {
                "condition": condition,
                "product_reaction_id": rows[0].get("product_reaction_id", reaction_id),
                "model_product_reaction_id": reaction_id,
                "product_name": product_name,
                "max_product_flux_at_zero_growth": max_at_zero,
                "max_product_flux_at_half_growth": max_at_half,
                "max_product_flux_at_high_growth": max_at_high,
                "growth_coupling_label": classify_growth_coupling(max_at_zero, max_at_half, max_at_high),
                "fseof_candidate_count": len(candidates),
                "oe_candidate_count": oe_count,
                "kd_candidate_count": kd_count,
                "ko_candidate_count": ko_count,
                "recommended_design_count": recommended_count,
                "semantic_label": semantic.get("semantic_label", ""),
                "semantic_warning": semantic.get("semantic_warning", ""),
                "guidance": production_guidance(max_at_zero, max_at_half, max_at_high, semantic),
            }
        )
    rankings.sort(
        key=lambda row: (
            _safe_float(row.get("max_product_flux_at_half_growth")) or -1,
            _safe_float(row.get("max_product_flux_at_zero_growth")) or -1,
        ),
        reverse=True,
    )
    return rankings


def gene_target_key(row: dict[str, object], gene_id: str) -> tuple[str, str, str, str]:
    return (
        str(row.get("condition", "")),
        str(row.get("product_reaction_id", "")),
        str(gene_id),
        str(row.get("recommended_action", "")),
    )


def empty_gene_target_group(
    row: dict[str, object],
    gene_id: str,
    scope: str,
    mapping_status: str,
) -> dict[str, object]:
    return {
        "condition": row.get("condition", ""),
        "product_reaction_id": row.get("product_reaction_id", ""),
        "product_name": row.get("product_name", ""),
        "gene_id": gene_id,
        "recommended_action": row.get("recommended_action", ""),
        "action_confidence": row.get("action_confidence", ""),
        "supporting_reactions": set(),
        "gpr_rules": set(),
        "scores": [],
        "growth_loss_labels": set(),
        "semantic_labels": set(),
        "scopes": {scope} if scope else set(),
        "gene_mapping_status": mapping_status,
        "guidance_fragments": set(),
    }


def merge_gene_target_support(
    group: dict[str, object],
    row: dict[str, object],
    candidate_reaction: str,
    gpr_rule: str,
) -> None:
    if candidate_reaction:
        group["supporting_reactions"].add(candidate_reaction)
    if gpr_rule:
        group["gpr_rules"].add(gpr_rule)
    score = _safe_float(row.get("intervention_score"))
    if score is not None:
        group["scores"].append(score)
    for target_key, source_key in (
        ("growth_loss_labels", "growth_loss_label"),
        ("semantic_labels", "semantic_label"),
        ("guidance_fragments", "design_guidance"),
    ):
        value = str(row.get(source_key, ""))
        if value:
            group[target_key].add(value)
    group["action_confidence"] = stronger_confidence(
        str(group.get("action_confidence", "")),
        str(row.get("action_confidence", "")),
    )


def finalize_gene_target_group(group: dict[str, object]) -> dict[str, object]:
    reactions = sorted(str(value) for value in group.get("supporting_reactions", set()) if value)
    rules = sorted(str(value) for value in group.get("gpr_rules", set()) if value)
    scores = list(group.get("scores", []))
    score = sum(scores) if scores else 0.0
    growth_loss_label = summarize_label_set(group.get("growth_loss_labels", set()), growth_loss_priority)
    semantic_label = summarize_label_set(group.get("semantic_labels", set()), semantic_priority)
    scopes = sorted(str(value) for value in group.get("scopes", set()) if value)
    mapping_status = str(group.get("gene_mapping_status", ""))
    guidance = gene_target_guidance(
        action=str(group.get("recommended_action", "")),
        mapping_status=mapping_status,
        scope=";".join(scopes),
        growth_loss_label=growth_loss_label,
        semantic_label=semantic_label,
    )
    return {
        "condition": group.get("condition", ""),
        "product_reaction_id": group.get("product_reaction_id", ""),
        "product_name": group.get("product_name", ""),
        "gene_rank": "",
        "gene_id": group.get("gene_id", ""),
        "recommended_action": group.get("recommended_action", ""),
        "action_confidence": group.get("action_confidence", ""),
        "gene_target_score": round(score, 6),
        "supporting_reaction_count": len(reactions),
        "supporting_reactions": ";".join(reactions),
        "gpr_rule_count": len(rules),
        "gpr_design_scope": ";".join(scopes),
        "growth_loss_label": growth_loss_label,
        "semantic_label": semantic_label,
        "gene_mapping_status": mapping_status,
        "design_guidance": guidance,
    }


def classify_gpr_design_scope(rule_text: str, gene_count: int) -> str:
    text = str(rule_text or "").lower()
    if not text or gene_count == 0:
        return "no_gpr"
    if " or " in text:
        return "isozyme_or_branch"
    if " and " in text:
        return "complex_subunit"
    if gene_count > 1:
        return "multi_gene_rule"
    return "single_gene"


def gpr_rule_text(rule: Any | None) -> str:
    return str(getattr(rule, "rule_text", "") or "") if rule is not None else ""


def stronger_confidence(current: str, candidate: str) -> str:
    rank = {"high": 4, "medium": 3, "low": 2, "exploratory": 1, "excluded": 0, "": -1}
    return candidate if rank.get(candidate, 0) > rank.get(current, 0) else current


def summarize_label_set(values: object, priority_fn) -> str:
    labels = [str(value) for value in values if str(value)]
    if not labels:
        return ""
    labels.sort(key=priority_fn)
    return labels[0]


def growth_loss_priority(label: str) -> int:
    order = {
        "essential": 0,
        "high_growth_loss": 1,
        "moderate_growth_loss": 2,
        "low_growth_loss": 3,
        "knockout_not_solved": 4,
        "not_checked": 5,
    }
    return order.get(label, 6)


def semantic_priority(label: str) -> int:
    order = {
        "review_required": 0,
        "inconclusive": 1,
        "usable_with_caution": 2,
        "usable": 3,
    }
    return order.get(label, 4)


def gene_target_guidance(
    action: str,
    mapping_status: str,
    scope: str,
    growth_loss_label: str,
    semantic_label: str,
) -> str:
    if mapping_status == "no_gpr":
        return "Reaction target has no GPR; inspect manually before converting to gene edits."
    if semantic_label == "review_required":
        return "Gene target is linked to a reaction with semantic QC warnings; verify annotation first."
    if "isozyme_or_branch" in scope:
        return "GPR contains OR/isozyme logic; single-gene edits may be buffered by alternative enzymes."
    if "complex_subunit" in scope:
        return "GPR contains AND/complex logic; coordinate edits across complex subunits."
    if action == "OE":
        return "Single-gene overexpression candidate supported by production design ranking."
    if action == "KO" and growth_loss_label == "low_growth_loss":
        return "Single-gene KO candidate with low predicted reaction-level growth loss."
    if action == "KD":
        return "Prefer knockdown or regulated reduction, especially if full KO may affect growth."
    return "Exploratory gene-level target derived from reaction-level design evidence."


def normalize_production_targets(
    rows: list[dict[str, str]],
    model_index: Any | None = None,
) -> list[dict[str, object]]:
    """Normalize flexible production target tables into stable columns."""

    normalized: list[dict[str, object]] = []
    for row in rows:
        raw_reaction = _first_value(row, ["model_reaction_id", "product_reaction_id", "reaction_id", "target_id"])
        if not raw_reaction:
            continue
        if model_index is not None:
            model_reaction, mapping_status = model_index.resolve_reaction(raw_reaction)
        else:
            model_reaction, mapping_status = _canonical_reaction(raw_reaction), "not_checked"
        normalized.append(
            {
                "condition": row.get("condition") or row.get("sample") or "ALL",
                "reaction_id": raw_reaction,
                "model_reaction_id": model_reaction,
                "product_name": row.get("product_name") or row.get("product") or row.get("name") or raw_reaction,
                "target_type": row.get("target_type") or "product_exchange",
                "priority": row.get("priority", ""),
                "mapping_status": mapping_status,
                "source": row.get("source", ""),
                "note": row.get("note", ""),
            }
        )
    return normalized


def expand_targets_by_condition(
    targets: list[dict[str, object]],
    conditions: list[str],
) -> dict[str, list[dict[str, object]]]:
    """Expand ALL/default target rows to available condition groups."""

    result: dict[str, list[dict[str, object]]] = {condition: [] for condition in conditions}
    for target in targets:
        condition = str(target.get("condition") or "ALL")
        if condition.upper() == "ALL":
            for current in conditions:
                result.setdefault(current, []).append({**target, "condition": current})
        else:
            result.setdefault(condition, []).append(target)
    return {condition: rows for condition, rows in result.items() if rows}


def load_semantic_labels(uniprot_model_check_dir: str | Path | None) -> dict[str, dict[str, str]]:
    """Load reaction-level semantic QC labels from UniProt/GPR check outputs."""

    if not uniprot_model_check_dir:
        return {}
    root = Path(uniprot_model_check_dir)
    gpr_rows = read_csv_records(root / "gpr_consistency_flags.csv") if (root / "gpr_consistency_flags.csv").exists() else []
    reaction_rows = (
        read_csv_records(root / "reaction_annotation_flags.csv")
        if (root / "reaction_annotation_flags.csv").exists()
        else []
    )
    by_reaction: dict[str, dict[str, str]] = {}
    for row in gpr_rows:
        reaction_id = str(row.get("reaction_id", ""))
        current = by_reaction.setdefault(normalize_reaction_id(reaction_id), {})
        current["gpr_flag"] = row.get("flag", "")
        current["gpr_severity"] = row.get("severity", "")
    for row in reaction_rows:
        reaction_id = str(row.get("reaction_id", ""))
        current = by_reaction.setdefault(normalize_reaction_id(reaction_id), {})
        current["reaction_annotation_flag"] = row.get("flag", "")
        current["annotation_severity"] = row.get("severity", "")
    for current in by_reaction.values():
        current["semantic_label"] = classify_semantic_label(current)
        current["semantic_warning"] = semantic_warning(current)
    return by_reaction


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


def semantic_for_reaction(reaction_id: str, semantic_labels: dict[str, dict[str, str]]) -> dict[str, str]:
    return semantic_labels.get(normalize_reaction_id(reaction_id), {})


def classify_growth_coupling(
    max_at_zero: float | None,
    max_at_half: float | None,
    max_at_high: float | None,
) -> str:
    if max_at_zero is None:
        return "not_solved"
    if max_at_zero <= 1e-9:
        return "no_product_flux"
    if max_at_high is not None and max_at_high > 1e-9:
        return "growth_coupled_possible"
    if max_at_half is not None and max_at_half > 1e-9:
        return "growth_tradeoff"
    return "product_only_without_growth"


def growth_loss_fraction(baseline_growth: float | None, knockout_growth: float | None) -> float | None:
    """Return relative growth loss from a knockout simulation."""

    if baseline_growth is None or knockout_growth is None or baseline_growth <= 1e-12:
        return None
    return max(0.0, min(1.0, (baseline_growth - knockout_growth) / baseline_growth))


def classify_growth_loss(baseline_growth: float | None, knockout_growth: float | None) -> str:
    """Classify whether a KO looks viable enough for production design."""

    if baseline_growth is None:
        return "baseline_not_solved"
    if baseline_growth <= 1e-12:
        return "no_baseline_growth"
    if knockout_growth is None:
        return "knockout_not_solved"
    loss = growth_loss_fraction(baseline_growth, knockout_growth)
    if loss is None:
        return "unknown"
    if knockout_growth <= 1e-12 or loss >= 0.95:
        return "essential"
    if loss >= 0.5:
        return "high_growth_loss"
    if loss >= 0.2:
        return "moderate_growth_loss"
    return "low_growth_loss"


def recommend_intervention_action(
    candidate_action: str,
    growth_loss_label: str,
    is_product_reaction: bool = False,
) -> str:
    """Convert FSEOF trend direction and KO viability into OE/KD/KO action."""

    if is_product_reaction:
        return "do_not_rank"
    if candidate_action == "OE_candidate":
        return "OE"
    if candidate_action == "KD_candidate":
        if growth_loss_label in {"low_growth_loss"}:
            return "KO"
        return "KD"
    return "review"


def intervention_confidence(
    recommended_action: str,
    growth_loss_label: str,
    row: dict[str, object],
) -> str:
    """Assign a practical confidence label to the intervention action."""

    if recommended_action == "do_not_rank":
        return "excluded"
    if row.get("semantic_label") == "review_required":
        return "low"
    if recommended_action == "OE":
        return "high" if growth_loss_label not in {"baseline_not_solved", "no_baseline_growth"} else "exploratory"
    if recommended_action == "KO":
        return "high" if growth_loss_label == "low_growth_loss" else "medium"
    if recommended_action == "KD":
        if growth_loss_label in {"essential", "high_growth_loss"}:
            return "low"
        if growth_loss_label in {"moderate_growth_loss", "not_checked", "knockout_not_solved", "reaction_not_found"}:
            return "medium"
        return "exploratory"
    return "exploratory"


def intervention_score(
    trend_slope: float | None,
    feasible_points: float | None,
    recommended_action: str,
    action_confidence: str,
    growth_loss_label: str,
    semantic_label: str,
) -> float:
    """Score candidate interventions for ranking while penalizing high-risk rows."""

    if recommended_action in {"", "do_not_rank"} or trend_slope is None:
        return 0.0
    score = abs(trend_slope) * max(1.0, feasible_points or 1.0)
    score *= {
        "high": 1.0,
        "medium": 0.7,
        "low": 0.35,
        "exploratory": 0.25,
        "excluded": 0.0,
    }.get(action_confidence, 0.4)
    score *= {
        "low_growth_loss": 1.0,
        "moderate_growth_loss": 0.75,
        "high_growth_loss": 0.4,
        "essential": 0.25,
        "not_checked": 0.6,
        "knockout_not_solved": 0.45,
        "reaction_not_found": 0.2,
        "baseline_not_solved": 0.4,
        "no_baseline_growth": 0.3,
    }.get(growth_loss_label, 0.5)
    score *= {
        "review_required": 0.25,
        "inconclusive": 0.6,
        "usable_with_caution": 0.8,
    }.get(semantic_label, 1.0)
    return score


def intervention_filter_status(
    recommended_action: str,
    growth_loss_label: str,
    semantic_label: str,
    is_product_reaction: bool,
) -> str:
    """Return the filtering/guidance status for a candidate intervention."""

    if is_product_reaction:
        return "excluded_product_reaction"
    if semantic_label == "review_required":
        return "caution_semantic_qc"
    if recommended_action == "KO" and growth_loss_label in {"low_growth_loss"}:
        return "recommended"
    if recommended_action == "KD" and growth_loss_label in {"essential", "high_growth_loss"}:
        return "caution_growth_loss"
    if growth_loss_label in {"baseline_not_solved", "no_baseline_growth", "knockout_not_solved", "not_checked"}:
        return "exploratory_unknown_growth"
    return "recommended"


def intervention_guidance(recommended_action: str, growth_loss_label: str, filter_status: str) -> str:
    """Short explanation for production design candidate rows."""

    if filter_status == "excluded_product_reaction":
        return "Product reaction itself is not ranked as an engineering intervention."
    if filter_status == "caution_semantic_qc":
        return "Semantic QC flagged this reaction; verify GPR/annotation before interpreting the target."
    if recommended_action == "OE":
        return "Flux increases as product demand rises; consider overexpression or capacity increase."
    if recommended_action == "KO":
        return "Flux decreases as product demand rises and KO has low predicted growth loss."
    if recommended_action == "KD":
        if growth_loss_label in {"essential", "high_growth_loss"}:
            return "Full KO is predicted to harm growth; prefer knockdown or regulated reduction."
        return "Flux decreases as product demand rises; knockdown is safer than assuming KO."
    return "Exploratory target; inspect flux trend and growth impact before use."


def production_guidance(
    max_at_zero: float | None,
    max_at_half: float | None,
    max_at_high: float | None,
    semantic: dict[str, str],
) -> str:
    semantic_label = semantic.get("semantic_label", "")
    if semantic_label == "review_required":
        return "Production target has high-risk semantic QC flags; review annotation/GPR first."
    coupling = classify_growth_coupling(max_at_zero, max_at_half, max_at_high)
    if coupling == "growth_coupled_possible":
        return "Product flux remains possible near high growth; suitable for deeper target ranking."
    if coupling == "growth_tradeoff":
        return "Product flux is possible but competes with growth; inspect FSEOF-lite candidates."
    if coupling == "product_only_without_growth":
        return "Product can be forced only when growth is relaxed; use as exploratory."
    return "No reliable product envelope was solved for this target."


def build_production_summary(
    status: str,
    message: str,
    target_count: int,
    envelope_rows: list[dict[str, object]],
    trend_rows: list[dict[str, object]],
    design_rows: list[dict[str, object]],
    gene_target_rows: list[dict[str, object]],
    ranking_rows: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "status": status,
        "message": message,
        "product_target_count": target_count,
        "production_envelope_row_count": len(envelope_rows),
        "ranked_product_count": len(ranking_rows),
        "fseof_candidate_count": len(trend_rows),
        "production_design_candidate_count": len(design_rows),
        "oe_design_count": sum(1 for row in design_rows if row.get("recommended_action") == "OE"),
        "kd_design_count": sum(1 for row in design_rows if row.get("recommended_action") == "KD"),
        "ko_design_count": sum(1 for row in design_rows if row.get("recommended_action") == "KO"),
        "production_gene_target_count": sum(1 for row in gene_target_rows if row.get("gene_mapping_status") == "mapped"),
        "unmapped_reaction_target_count": sum(1 for row in gene_target_rows if row.get("gene_mapping_status") != "mapped"),
        "review_required_target_count": sum(1 for row in ranking_rows if row.get("semantic_label") == "review_required"),
        "growth_coupled_target_count": sum(
            1 for row in ranking_rows if row.get("growth_coupling_label") == "growth_coupled_possible"
        ),
        "guidance": message,
    }


def write_production_outputs(
    files: dict[str, str],
    cobra_available: bool,
    status: str,
    message: str,
    model_path: str | Path,
    exchange_bounds_path: str | Path,
    production_targets_path: str | Path,
    semantic_labels: dict[str, dict[str, str]],
    target_count: int = 0,
) -> ProductionAnalysisResult:
    summary_rows = [
        build_production_summary(
            status=status,
            message=message,
            target_count=target_count,
            envelope_rows=[],
            trend_rows=[],
            design_rows=[],
            gene_target_rows=[],
            ranking_rows=[],
        )
    ]
    write_csv(files["summary"], summary_rows)
    write_csv(files["production_targets"], [])
    write_csv(files["production_envelope"], [])
    write_csv(files["production_target_ranking"], [])
    write_csv(files["fseof_lite_reaction_targets"], [])
    write_csv(files["production_design_targets"], [])
    write_csv(files["production_gene_targets"], [])
    write_json(
        files["manifest"],
        {
            "schema_version": "0.2.0",
            "cobra_available": cobra_available,
            "status": status,
            "message": message,
            "model_path": str(model_path),
            "exchange_bounds_path": str(exchange_bounds_path),
            "production_targets_path": str(production_targets_path),
            "semantic_label_count": len(semantic_labels),
            "files": files,
        },
    )
    return ProductionAnalysisResult(
        cobra_available=cobra_available,
        status="skipped",
        output_dir=str(Path(files["summary"]).parent),
        message=message,
        files=files,
    )


def production_output_files(output: Path) -> dict[str, str]:
    return {
        "summary": str(output / "production_analysis_summary.csv"),
        "production_targets": str(output / "production_targets.csv"),
        "production_envelope": str(output / "production_envelope.csv"),
        "production_target_ranking": str(output / "production_target_ranking.csv"),
        "fseof_lite_reaction_targets": str(output / "fseof_lite_reaction_targets.csv"),
        "production_design_targets": str(output / "production_design_targets.csv"),
        "production_gene_targets": str(output / "production_gene_targets.csv"),
        "manifest": str(output / "production_analysis_manifest.json"),
    }


def value_at_fraction(rows: list[dict[str, object]], fraction: float) -> float | None:
    for row in rows:
        if _safe_float(row.get("biomass_fraction")) == fraction:
            return _safe_float(row.get("max_product_flux"))
    return None


def linear_slope(xs: list[float], ys: list[float]) -> float:
    if len(xs) != len(ys) or len(xs) < 2:
        return 0.0
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        return 0.0
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denominator


def primary_objective_reaction(model: Any) -> Any | None:
    objective_reactions = [
        reaction
        for reaction in model.reactions
        if getattr(reaction, "objective_coefficient", 0) not in {0, 0.0, None}
    ]
    return objective_reactions[0] if objective_reactions else None


def prepare_production_targets_from_package(
    package_dir: str | Path,
    model_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Normalize a staged production target table, writing an empty table if absent."""

    package = Path(package_dir)
    output = Path(output_path)
    source = find_staged_table(package, "production_targets")
    if source is None:
        write_csv(output, [])
        return output
    try:
        model_index = parse_sbml_index(model_path)
    except Exception:
        model_index = None
    write_csv(output, normalize_production_targets(read_csv_records(source), model_index=model_index))
    return output


def find_staged_table(package: Path, role: str) -> Path | None:
    for map_path in (package / "normalized_inputs" / "normalized_input_map.csv", package / "input_file_map.csv"):
        if not map_path.exists() or map_path.stat().st_size == 0:
            continue
        for row in read_csv_records(map_path):
            if row.get("role") != role:
                continue
            path_text = row.get("path", "")
            path = Path(path_text) if path_text else Path()
            if path_text and path.exists():
                return path
            candidate = package / str(row.get("relative_path", ""))
            if candidate.exists():
                return candidate
    return None


def classify_production_candidate(reaction_id: str, reaction_name: str = "") -> tuple[str, str, str]:
    """Classify whether a reaction looks like a useful product target."""

    cobra_id = _cobra_reaction_id(reaction_id)
    upper_id = cobra_id.upper()
    lower_name = str(reaction_name or "").lower()
    if upper_id.startswith("EX_"):
        return "product_exchange", "high", "exchange reaction id prefix"
    if upper_id.startswith("DM_"):
        return "product_demand", "high", "demand reaction id prefix"
    if upper_id.startswith(("SK_", "SINK_")):
        return "product_sink", "high", "sink reaction id prefix"
    if "exchange" in lower_name:
        return "product_exchange", "medium", "reaction name contains exchange"
    if "demand" in lower_name:
        return "product_demand", "medium", "reaction name contains demand"
    if "sink" in lower_name:
        return "product_sink", "medium", "reaction name contains sink"
    return "reaction", "low", "not an exchange/demand/sink-like reaction"


def product_name_hint(reaction_id: str, reaction_name: str = "") -> str:
    """Create a compact product-name hint for a candidate reaction."""

    name = " ".join(str(reaction_name or "").replace("_", " ").split())
    lower = name.lower()
    for suffix in (" exchange", " demand", " sink"):
        if lower.endswith(suffix):
            return name[: -len(suffix)].strip() or reaction_id
    for prefix in ("exchange of ", "demand for ", "sink for "):
        if lower.startswith(prefix):
            return name[len(prefix) :].strip() or reaction_id
    cobra_id = _cobra_reaction_id(reaction_id)
    for prefix in ("EX_", "DM_", "SK_", "SINK_"):
        if cobra_id.upper().startswith(prefix):
            product = cobra_id[len(prefix) :]
            parts = product.split("_")
            if len(parts) > 1 and len(parts[-1]) <= 2:
                product = "_".join(parts[:-1])
            return product or reaction_id
    return name or reaction_id


def _production_candidate_sort_key(row: dict[str, object]) -> tuple[int, str, str]:
    confidence_rank = {"high": 0, "medium": 1, "low": 2}.get(str(row.get("confidence", "")), 3)
    return confidence_rank, str(row.get("target_type", "")), str(row.get("cobra_reaction_id", ""))


def _cobra_reaction_id(reaction_id: str) -> str:
    text = str(reaction_id or "").strip()
    return text[2:] if text.startswith("R_") else text


def _safe_read_csv(path: str | Path) -> list[dict[str, str]]:
    current = Path(path)
    if not current.exists() or current.stat().st_size == 0:
        return []
    return read_csv_records(current)


def _resolve_package_path(package: Path, row: dict[str, object]) -> Path | None:
    path_text = str(row.get("path") or "")
    if path_text:
        path = Path(path_text)
        if path.exists():
            return path
    relative_path = str(row.get("relative_path") or row.get("source_relative_path") or "")
    if relative_path:
        candidate = package / relative_path
        if candidate.exists():
            return candidate
    return None


def _align_rows_to_columns(rows: list[dict[str, object]], columns: list[str]) -> list[dict[str, object]]:
    return [{column: row.get(column, "") for column in columns} for row in rows]


def _update_upload_manifest_with_production_targets(
    package: Path,
    map_row: dict[str, object],
    replace_existing: bool = True,
) -> None:
    manifest_path = package / "upload_manifest.json"
    if not manifest_path.exists():
        return
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(manifest, dict):
        return
    omics_files = manifest.get("omics_files")
    if not isinstance(omics_files, list):
        omics_files = []
    if replace_existing:
        omics_files = [row for row in omics_files if not (isinstance(row, dict) and row.get("role") == "production_targets")]
    omics_files.append(map_row)
    manifest["omics_files"] = omics_files
    if "files" in manifest and isinstance(manifest["files"], dict):
        manifest["files"]["input_file_map"] = str(package / "input_file_map.csv")
    write_json(manifest_path, manifest)


def normalize_reaction_id(reaction_id: str) -> str:
    text = str(reaction_id or "").strip()
    if text.startswith("R_"):
        text = text[2:]
    return text.lower()


def _canonical_reaction(reaction_id: str) -> str:
    if not reaction_id:
        return ""
    return reaction_id if reaction_id.startswith("R_") else f"R_{reaction_id}"


def _safe_get_reaction(model: Any, reaction_id: str) -> Any | None:
    try:
        return get_cobra_reaction(model, reaction_id)
    except Exception:
        return None


def _first_value(row: dict[str, str], columns: list[str]) -> str:
    for column in columns:
        value = str(row.get(column, "")).strip()
        if value:
            return value
    return ""


def _safe_float(value: object) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
