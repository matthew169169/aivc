"""Transcriptomics-driven flux workflows: E-Flux and delta-FBA-lite."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cobra_runner import (
    _redirect_cobra_cache,
    apply_exchange_bounds,
    cobrapy_available,
    compare_flux_targets,
    get_cobra_reaction,
    group_by_condition,
    summarize_flux_comparison,
    with_cobra_id_aliases,
)
from .constraints import parse_sbml_index, read_csv_records, write_csv, write_json
from .context import protected_reactions_from_outputs


@dataclass(slots=True)
class TranscriptomicsFluxResult:
    """Summary returned by the transcriptomics flux workflow."""

    cobra_available: bool
    status: str
    output_dir: str
    message: str
    files: dict[str, str]


def run_transcriptomics_flux_workflow(
    model_path: str | Path,
    exchange_bounds_path: str | Path,
    reaction_expression_path: str | Path,
    flux_targets_path: str | Path,
    output_dir: str | Path,
    reference_condition: str | None = None,
    require_cobra: bool = False,
    min_expression_fraction: float = 0.05,
    up_log2_threshold: float = 1.0,
    down_log2_threshold: float = -1.0,
    run_pfba: bool = True,
) -> TranscriptomicsFluxResult:
    """Run E-Flux and delta-FBA-lite tables from reaction expression evidence."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = _workflow_files(output)

    if not cobrapy_available():
        message = "COBRApy is not installed; skipped transcriptomics flux execution."
        write_json(
            files["manifest"],
            {
                "cobra_available": False,
                "status": "skipped",
                "message": message,
                "model_path": str(model_path),
                "exchange_bounds_path": str(exchange_bounds_path),
                "reaction_expression_path": str(reaction_expression_path),
                "flux_targets_path": str(flux_targets_path),
            },
        )
        if require_cobra:
            raise RuntimeError(message)
        return TranscriptomicsFluxResult(False, "skipped", str(output), message, {"manifest": files["manifest"]})

    _redirect_cobra_cache()
    from cobra.io import read_sbml_model

    model = read_sbml_model(str(model_path))
    exchange_rows = read_csv_records(exchange_bounds_path)
    reaction_rows = read_csv_records(reaction_expression_path)
    target_rows = read_csv_records(flux_targets_path)

    model_index = parse_sbml_index(model_path)
    protected = protected_reactions_from_outputs(model_index.objective_reactions, exchange_rows)
    model_bounds = collect_model_reaction_bounds(model)
    eflux_bounds = build_eflux_bound_rows(
        reaction_rows,
        model_bounds,
        protected_reactions=protected,
        min_expression_fraction=min_expression_fraction,
    )

    eflux_result = solve_eflux_conditions(
        model=model,
        exchange_rows=exchange_rows,
        eflux_bounds=eflux_bounds,
        target_rows=target_rows,
        run_pfba=run_pfba,
    )

    delta_result = build_delta_fba_tables(
        reaction_rows=reaction_rows,
        condition_fluxes=eflux_result["condition_fluxes"],
        condition_solve_status=eflux_result["condition_solve_status"],
        target_rows=target_rows,
        reference_condition=reference_condition,
        up_log2_threshold=up_log2_threshold,
        down_log2_threshold=down_log2_threshold,
    )

    write_csv(files["eflux_bounds"], eflux_bounds)
    write_csv(files["eflux_summary"], eflux_result["summary"])
    write_csv(files["eflux_fluxes"], eflux_result["fluxes"])
    write_csv(files["eflux_validation"], eflux_result["validation"])
    write_csv(files["eflux_validation_summary"], summarize_flux_comparison(eflux_result["validation"]))
    write_csv(files["delta_expression"], delta_result["expression_deltas"])
    write_csv(files["delta_fluxes"], delta_result["flux_deltas"])
    write_csv(files["delta_validation"], delta_result["measured_delta_comparison"])
    write_csv(files["delta_summary"], delta_result["summary"])

    status = "completed" if eflux_result["summary"] else "completed_no_conditions"
    message = (
        f"Completed E-Flux for {len(eflux_result['summary'])} conditions and "
        f"delta-FBA-lite for {len(delta_result['summary'])} condition pairs."
    )
    write_json(
        files["manifest"],
        {
            "cobra_available": True,
            "status": status,
            "message": message,
            "model_path": str(model_path),
            "exchange_bounds_path": str(exchange_bounds_path),
            "reaction_expression_path": str(reaction_expression_path),
            "flux_targets_path": str(flux_targets_path),
            "reference_condition": delta_result["reference_condition"],
            "min_expression_fraction": min_expression_fraction,
            "up_log2_threshold": up_log2_threshold,
            "down_log2_threshold": down_log2_threshold,
            "run_pfba": run_pfba,
            "files": files,
        },
    )
    return TranscriptomicsFluxResult(True, status, str(output), message, files)


def build_eflux_bound_rows(
    reaction_rows: list[dict[str, str]],
    model_bounds: dict[str, tuple[float, float]],
    protected_reactions: set[str] | None = None,
    min_expression_fraction: float = 0.05,
) -> list[dict[str, object]]:
    """Map reaction expression scores to E-Flux capacity bounds."""

    protected = {_normalize_reaction_id(reaction) for reaction in (protected_reactions or set())}
    rows: list[dict[str, object]] = []
    for condition, condition_rows in sorted(group_by_condition(reaction_rows).items()):
        scored_rows = [
            row for row in condition_rows
            if _usable_expression_score(row) is not None and _usable_expression_score(row) >= 0
            and _normalize_reaction_id(row.get("cobra_reaction_id") or row.get("reaction_id", "")) not in protected
        ]
        max_score = max((_usable_expression_score(row) or 0.0) for row in scored_rows) if scored_rows else None
        for row in condition_rows:
            raw_id = row.get("cobra_reaction_id") or row.get("reaction_id", "")
            normalized_id = _normalize_reaction_id(raw_id)
            reaction_score = _usable_expression_score(row)
            original_bounds = model_bounds.get(normalized_id)
            is_protected = normalized_id in protected
            expression_fraction = None
            eflux_lower = None
            eflux_upper = None
            bound_tightened = False
            status = "not_constrained"
            note = ""

            if original_bounds is None:
                status = "reaction_not_in_model"
                note = "Reaction evidence could not be resolved to model bounds."
            elif is_protected:
                status = "protected"
                note = "Objective or measured exchange reaction was not constrained by E-Flux."
            elif reaction_score is None or max_score in {None, 0}:
                status = "no_expression_score"
                note = "No measured GPR expression score for this condition."
            else:
                lower, upper = original_bounds
                expression_fraction = max(min_expression_fraction, min(1.0, reaction_score / float(max_score)))
                capacity = max(abs(lower), abs(upper))
                expression_capacity = capacity * expression_fraction
                eflux_lower = max(lower, -expression_capacity) if lower < 0 else lower
                eflux_upper = min(upper, expression_capacity) if upper > 0 else upper
                bound_tightened = eflux_lower > lower + 1e-9 or eflux_upper < upper - 1e-9
                status = "constrained" if bound_tightened else "not_tightened"

            rows.append(
                {
                    "condition": condition,
                    "reaction_id": row.get("reaction_id", ""),
                    "cobra_reaction_id": raw_id,
                    "reaction_name": row.get("reaction_name", ""),
                    "reaction_score": reaction_score,
                    "evidence": row.get("evidence", ""),
                    "gene_count": row.get("gene_count", ""),
                    "measured_gene_count": row.get("measured_gene_count", ""),
                    "gene_coverage": row.get("gene_coverage", ""),
                    "expression_fraction": expression_fraction,
                    "original_lower_bound": original_bounds[0] if original_bounds else None,
                    "original_upper_bound": original_bounds[1] if original_bounds else None,
                    "eflux_lower_bound": eflux_lower,
                    "eflux_upper_bound": eflux_upper,
                    "bound_tightened": bound_tightened,
                    "status": status,
                    "note": note,
                }
            )
    return rows


def solve_eflux_conditions(
    model: Any,
    exchange_rows: list[dict[str, str]],
    eflux_bounds: list[dict[str, object]],
    target_rows: list[dict[str, str]],
    run_pfba: bool = True,
) -> dict[str, object]:
    """Solve condition-wise E-Flux models and return tables plus flux maps."""

    exchange_by_condition = group_by_condition(exchange_rows)
    bounds_by_condition = group_by_condition([{key: str(value) for key, value in row.items()} for row in eflux_bounds])
    targets_by_condition = group_by_condition(target_rows)
    conditions = sorted(set(exchange_by_condition) | set(bounds_by_condition) | set(targets_by_condition))

    summary_rows: list[dict[str, object]] = []
    flux_rows: list[dict[str, object]] = []
    validation_rows: list[dict[str, object]] = []
    condition_fluxes: dict[str, dict[str, float | None]] = {}
    condition_solve_status: dict[str, str] = {}

    for condition in conditions:
        with model:
            applied_exchange, failed_exchange = apply_exchange_bounds(model, exchange_by_condition.get(condition, []))
            applied_eflux, failed_eflux = apply_eflux_bounds(model, bounds_by_condition.get(condition, []))
            solved = solve_flux_map(model, run_pfba=run_pfba)
            condition_fluxes[condition] = solved["flux_map"]
            condition_solve_status[condition] = str(solved["status"])
            aliased = with_cobra_id_aliases(solved["flux_map"])
            validation_rows.extend(
                compare_flux_targets(
                    condition,
                    aliased,
                    targets_by_condition.get(condition, []),
                    solve_status=str(solved["status"]),
                    method="E-Flux",
                )
            )
            for reaction_id, flux in solved["flux_map"].items():
                flux_rows.append(
                    {
                        "condition": condition,
                        "reaction_id": reaction_id,
                        "predicted_flux": flux,
                        "solution_source": solved["solution_source"],
                    }
                )

            condition_bounds = bounds_by_condition.get(condition, [])
            measured_gpr = [
                row for row in condition_bounds
                if (_to_int(row.get("gene_count")) or 0) > 0 and (_to_int(row.get("measured_gene_count")) or 0) > 0
            ]
            gpr_rows = [row for row in condition_bounds if (_to_int(row.get("gene_count")) or 0) > 0]
            summary_rows.append(
                {
                    "condition": condition,
                    "status": solved["status"],
                    "objective_value": solved["objective_value"],
                    "solution_source": solved["solution_source"],
                    "pfba_status": solved["pfba_status"],
                    "pfba_total_flux_objective": solved["pfba_total_flux_objective"],
                    "exchange_bounds_applied": applied_exchange,
                    "exchange_bounds_failed": failed_exchange,
                    "eflux_bounds_applied": applied_eflux,
                    "eflux_bounds_failed": failed_eflux,
                    "constrained_reaction_count": sum(1 for row in condition_bounds if row.get("status") == "constrained"),
                    "measured_gpr_reaction_count": len(measured_gpr),
                    "measured_gpr_fraction": len(measured_gpr) / len(gpr_rows) if gpr_rows else None,
                }
            )

    return {
        "summary": summary_rows,
        "fluxes": flux_rows,
        "validation": validation_rows,
        "condition_fluxes": condition_fluxes,
        "condition_solve_status": condition_solve_status,
    }


def build_delta_fba_tables(
    reaction_rows: list[dict[str, str]],
    condition_fluxes: dict[str, dict[str, float | None]],
    condition_solve_status: dict[str, str],
    target_rows: list[dict[str, str]],
    reference_condition: str | None = None,
    up_log2_threshold: float = 1.0,
    down_log2_threshold: float = -1.0,
    flux_threshold: float = 1e-6,
) -> dict[str, object]:
    """Build delta-FBA-lite comparison tables from E-Flux condition fluxes."""

    available_conditions = sorted(condition_fluxes)
    reference = choose_reference_condition(available_conditions, reference_condition)
    if not reference:
        return {
            "reference_condition": "",
            "expression_deltas": [],
            "flux_deltas": [],
            "measured_delta_comparison": [],
            "summary": [],
        }

    expression_deltas = build_expression_delta_rows(
        reaction_rows,
        reference,
        [condition for condition in available_conditions if condition != reference],
        up_log2_threshold=up_log2_threshold,
        down_log2_threshold=down_log2_threshold,
    )
    flux_deltas = build_flux_delta_rows(condition_fluxes, reference, flux_threshold=flux_threshold)
    measured_delta_comparison = build_measured_delta_comparison(
        target_rows,
        condition_fluxes,
        reference,
    )
    summary = summarize_delta_fba_pairs(
        expression_deltas,
        flux_deltas,
        measured_delta_comparison,
        reference,
        condition_solve_status,
    )
    return {
        "reference_condition": reference,
        "expression_deltas": expression_deltas,
        "flux_deltas": flux_deltas,
        "measured_delta_comparison": measured_delta_comparison,
        "summary": summary,
    }


def build_expression_delta_rows(
    reaction_rows: list[dict[str, str]],
    reference_condition: str,
    target_conditions: list[str],
    up_log2_threshold: float = 1.0,
    down_log2_threshold: float = -1.0,
    pseudocount: float = 1.0,
) -> list[dict[str, object]]:
    """Compare reaction expression scores between a reference and targets."""

    rows_by_condition = group_by_condition(reaction_rows)
    reference_rows = {_reaction_key(row): row for row in rows_by_condition.get(reference_condition, [])}
    output: list[dict[str, object]] = []
    for target_condition in target_conditions:
        target_map = {_reaction_key(row): row for row in rows_by_condition.get(target_condition, [])}
        for key in sorted(set(reference_rows) & set(target_map)):
            reference_row = reference_rows[key]
            target_row = target_map[key]
            reference_score = _usable_expression_score(reference_row)
            target_score = _usable_expression_score(target_row)
            log2_fold_change = None
            direction = "insufficient_expression"
            if reference_score is not None and target_score is not None:
                log2_fold_change = math.log2((target_score + pseudocount) / (reference_score + pseudocount))
                direction = classify_expression_delta(log2_fold_change, up_log2_threshold, down_log2_threshold)
            output.append(
                {
                    "reference_condition": reference_condition,
                    "target_condition": target_condition,
                    "condition_pair": f"{reference_condition}->{target_condition}",
                    "reaction_id": target_row.get("reaction_id", reference_row.get("reaction_id", "")),
                    "cobra_reaction_id": target_row.get("cobra_reaction_id", reference_row.get("cobra_reaction_id", "")),
                    "reaction_name": target_row.get("reaction_name", reference_row.get("reaction_name", "")),
                    "reference_score": reference_score,
                    "target_score": target_score,
                    "log2_fold_change": log2_fold_change,
                    "expression_direction": direction,
                    "reference_evidence": reference_row.get("evidence", ""),
                    "target_evidence": target_row.get("evidence", ""),
                    "status": direction,
                }
            )
    return output


def build_flux_delta_rows(
    condition_fluxes: dict[str, dict[str, float | None]],
    reference_condition: str,
    flux_threshold: float = 1e-6,
) -> list[dict[str, object]]:
    """Compare predicted fluxes against a reference condition."""

    reference_fluxes = condition_fluxes.get(reference_condition, {})
    output: list[dict[str, object]] = []
    for target_condition, target_fluxes in sorted(condition_fluxes.items()):
        if target_condition == reference_condition:
            continue
        for reaction_id in sorted(set(reference_fluxes) | set(target_fluxes)):
            reference_flux = reference_fluxes.get(reaction_id)
            target_flux = target_fluxes.get(reaction_id)
            signed_delta = _subtract_optional(target_flux, reference_flux)
            activity_delta = None
            if reference_flux is not None and target_flux is not None:
                activity_delta = abs(target_flux) - abs(reference_flux)
            output.append(
                {
                    "reference_condition": reference_condition,
                    "target_condition": target_condition,
                    "condition_pair": f"{reference_condition}->{target_condition}",
                    "reaction_id": reaction_id,
                    "cobra_reaction_id": reaction_id,
                    "reference_flux": reference_flux,
                    "target_flux": target_flux,
                    "predicted_flux_delta": signed_delta,
                    "predicted_activity_delta": activity_delta,
                    "predicted_activity_direction": classify_activity_delta(activity_delta, flux_threshold),
                    "status": "predicted" if signed_delta is not None else "missing_flux",
                }
            )
    return output


def build_measured_delta_comparison(
    target_rows: list[dict[str, str]],
    condition_fluxes: dict[str, dict[str, float | None]],
    reference_condition: str,
) -> list[dict[str, object]]:
    """Compare predicted flux deltas against paired measured flux deltas."""

    targets_by_condition = group_by_condition(target_rows)
    reference_targets = {
        _normalize_reaction_id(row.get("model_reaction_id") or row.get("reaction_id", "")): row
        for row in targets_by_condition.get(reference_condition, [])
    }
    reference_fluxes = with_cobra_id_aliases(condition_fluxes.get(reference_condition, {}))
    output: list[dict[str, object]] = []
    for target_condition, rows in sorted(targets_by_condition.items()):
        if target_condition == reference_condition:
            continue
        target_fluxes = with_cobra_id_aliases(condition_fluxes.get(target_condition, {}))
        for target in rows:
            reaction_id = target.get("model_reaction_id") or target.get("reaction_id", "")
            reference_target = reference_targets.get(_normalize_reaction_id(reaction_id))
            if reference_target is None:
                continue
            measured_reference = _to_float(reference_target.get("measured_flux") or reference_target.get("flux"))
            measured_target = _to_float(target.get("measured_flux") or target.get("flux"))
            predicted_reference = reference_fluxes.get(reaction_id)
            predicted_target = target_fluxes.get(reaction_id)
            measured_delta = _subtract_optional(measured_target, measured_reference)
            predicted_delta = _subtract_optional(predicted_target, predicted_reference)
            residual = _subtract_optional(predicted_delta, measured_delta)
            output.append(
                {
                    "reference_condition": reference_condition,
                    "target_condition": target_condition,
                    "condition_pair": f"{reference_condition}->{target_condition}",
                    "reaction_id": target.get("reaction_id", ""),
                    "model_reaction_id": reaction_id,
                    "measured_reference_flux": measured_reference,
                    "measured_target_flux": measured_target,
                    "measured_flux_delta": measured_delta,
                    "predicted_reference_flux": predicted_reference,
                    "predicted_target_flux": predicted_target,
                    "predicted_flux_delta": predicted_delta,
                    "delta_residual": residual,
                    "abs_delta_residual": abs(residual) if residual is not None else None,
                    "unit": target.get("unit", ""),
                    "status": "comparable" if residual is not None else "missing_predicted_or_measured_delta",
                }
            )
    return output


def summarize_delta_fba_pairs(
    expression_deltas: list[dict[str, object]],
    flux_deltas: list[dict[str, object]],
    measured_delta_comparison: list[dict[str, object]],
    reference_condition: str,
    condition_solve_status: dict[str, str],
) -> list[dict[str, object]]:
    """Summarize delta-FBA-lite direction and measured-delta agreement."""

    expression_by_pair = _group_by_key(expression_deltas, "condition_pair")
    flux_by_pair = _group_by_key(flux_deltas, "condition_pair")
    measured_by_pair = _group_by_key(measured_delta_comparison, "condition_pair")
    summary: list[dict[str, object]] = []
    for pair in sorted(set(expression_by_pair) | set(flux_by_pair) | set(measured_by_pair)):
        target_condition = pair.split("->", 1)[1] if "->" in pair else ""
        expression_rows = expression_by_pair.get(pair, [])
        flux_map = {
            _normalize_reaction_id(str(row.get("reaction_id", ""))): row
            for row in flux_by_pair.get(pair, [])
        }
        directional_rows = [
            row for row in expression_rows
            if row.get("expression_direction") in {"up", "down"}
        ]
        comparable = []
        agreement = []
        for row in directional_rows:
            flux_row = flux_map.get(_normalize_reaction_id(str(row.get("cobra_reaction_id") or row.get("reaction_id") or "")))
            predicted_direction = flux_row.get("predicted_activity_direction") if flux_row else ""
            if predicted_direction in {"up", "down"}:
                comparable.append(row)
                if predicted_direction == row.get("expression_direction"):
                    agreement.append(row)
        measured_comparable = [
            row for row in measured_by_pair.get(pair, [])
            if row.get("status") == "comparable" and row.get("abs_delta_residual") is not None
        ]
        abs_residuals = [float(row["abs_delta_residual"]) for row in measured_comparable]
        summary.append(
            {
                "condition_pair": pair,
                "reference_condition": reference_condition,
                "target_condition": target_condition,
                "reference_solve_status": condition_solve_status.get(reference_condition, ""),
                "target_solve_status": condition_solve_status.get(target_condition, ""),
                "expression_delta_count": len(directional_rows),
                "upregulated_reaction_count": sum(1 for row in directional_rows if row.get("expression_direction") == "up"),
                "downregulated_reaction_count": sum(1 for row in directional_rows if row.get("expression_direction") == "down"),
                "direction_comparable_count": len(comparable),
                "direction_agreement_count": len(agreement),
                "direction_agreement_fraction": len(agreement) / len(comparable) if comparable else None,
                "measured_delta_comparable_count": len(measured_comparable),
                "mean_abs_delta_residual": sum(abs_residuals) / len(abs_residuals) if abs_residuals else None,
                "status": classify_delta_fba_status(len(directional_rows), len(comparable), condition_solve_status.get(target_condition, "")),
            }
        )
    return summary


def apply_eflux_bounds(model: Any, rows: list[dict[str, str]]) -> tuple[int, int]:
    """Apply E-Flux reaction bounds to a COBRApy model."""

    applied = 0
    failed = 0
    for row in rows:
        if row.get("status") != "constrained":
            continue
        reaction_id = row.get("cobra_reaction_id") or row.get("reaction_id") or ""
        lower = _to_float(row.get("eflux_lower_bound"))
        upper = _to_float(row.get("eflux_upper_bound"))
        try:
            reaction = get_cobra_reaction(model, reaction_id)
            if lower is not None:
                reaction.lower_bound = lower
            if upper is not None:
                reaction.upper_bound = upper
            applied += 1
        except Exception:
            failed += 1
    return applied, failed


def solve_flux_map(model: Any, run_pfba: bool = True) -> dict[str, object]:
    """Solve a model and optionally use pFBA fluxes for deterministic output."""

    solution = model.optimize()
    status = getattr(solution, "status", "unknown")
    objective_value = _to_float(getattr(solution, "objective_value", None))
    flux_map: dict[str, float | None] = {}
    solution_source = "FBA"
    pfba_status = "skipped"
    pfba_total_flux_objective = None
    if status == "optimal":
        flux_map = {reaction_id: _to_float(value) for reaction_id, value in solution.fluxes.items()}
        if run_pfba:
            try:
                from cobra.flux_analysis import pfba

                pfba_solution = pfba(model)
                pfba_status = getattr(pfba_solution, "status", "unknown")
                if pfba_status == "optimal":
                    flux_map = {reaction_id: _to_float(value) for reaction_id, value in pfba_solution.fluxes.items()}
                    solution_source = "pFBA"
                pfba_total_flux_objective = _to_float(getattr(pfba_solution, "objective_value", None))
            except Exception as exc:
                pfba_status = f"failed: {type(exc).__name__}: {exc}"
    return {
        "status": status,
        "objective_value": objective_value,
        "flux_map": flux_map,
        "solution_source": solution_source,
        "pfba_status": pfba_status,
        "pfba_total_flux_objective": pfba_total_flux_objective,
    }


def collect_model_reaction_bounds(model: Any) -> dict[str, tuple[float, float]]:
    """Return reaction bounds indexed by normalized COBRA and SBML-style ids."""

    bounds: dict[str, tuple[float, float]] = {}
    for reaction in model.reactions:
        value = (float(reaction.lower_bound), float(reaction.upper_bound))
        for candidate in {reaction.id, f"R_{reaction.id}"}:
            bounds[_normalize_reaction_id(candidate)] = value
    return bounds


def choose_reference_condition(conditions: list[str], requested: str | None = None) -> str:
    """Choose a stable reference condition for condition-pair delta analysis."""

    if requested and requested in conditions:
        return requested
    if "glucose_aerobic" in conditions:
        return "glucose_aerobic"
    return conditions[0] if conditions else ""


def classify_expression_delta(value: float | None, up_threshold: float, down_threshold: float) -> str:
    if value is None:
        return "insufficient_expression"
    if value >= up_threshold:
        return "up"
    if value <= down_threshold:
        return "down"
    return "stable"


def classify_activity_delta(value: float | None, flux_threshold: float = 1e-6) -> str:
    if value is None:
        return "missing_flux"
    if value > flux_threshold:
        return "up"
    if value < -flux_threshold:
        return "down"
    return "stable"


def classify_delta_fba_status(expression_delta_count: int, comparable_count: int, target_solve_status: str) -> str:
    if target_solve_status != "optimal":
        return "solve_not_optimal"
    if expression_delta_count == 0:
        return "no_large_expression_deltas"
    if comparable_count == 0:
        return "flux_direction_not_comparable"
    return "completed"


def _workflow_files(output: Path) -> dict[str, str]:
    return {
        "eflux_bounds": str(output / "eflux_reaction_bounds.csv"),
        "eflux_summary": str(output / "eflux_summary.csv"),
        "eflux_fluxes": str(output / "eflux_fluxes.csv"),
        "eflux_validation": str(output / "eflux_flux_validation_comparison.csv"),
        "eflux_validation_summary": str(output / "eflux_flux_validation_summary.csv"),
        "delta_expression": str(output / "delta_fba_expression_deltas.csv"),
        "delta_fluxes": str(output / "delta_fba_flux_deltas.csv"),
        "delta_validation": str(output / "delta_fba_measured_delta_comparison.csv"),
        "delta_summary": str(output / "delta_fba_summary.csv"),
        "manifest": str(output / "transcriptomics_flux_manifest.json"),
    }


def _usable_expression_score(row: dict[str, str]) -> float | None:
    if row.get("status") in {"no_gpr", "no_measured_gene"}:
        return None
    return _to_float(row.get("reaction_score"))


def _reaction_key(row: dict[str, str]) -> str:
    return _normalize_reaction_id(row.get("cobra_reaction_id") or row.get("reaction_id", ""))


def _normalize_reaction_id(reaction_id: str) -> str:
    text = str(reaction_id or "").strip()
    if text.startswith("R_"):
        text = text[2:]
    return text.lower()


def _group_by_key(rows: list[dict[str, object]], key: str) -> dict[str, list[dict[str, object]]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get(key) or ""), []).append(row)
    return grouped


def _subtract_optional(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def _to_float(value: object) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: object) -> int | None:
    try:
        if value in {None, ""}:
            return None
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None
