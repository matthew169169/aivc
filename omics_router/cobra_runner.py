"""Optional COBRApy runner for baseline FBA and flux validation.

The module is importable without COBRApy. Actual model solving is attempted
only inside ``run_fba_workflow``.
"""

from __future__ import annotations

import importlib.util
import importlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constraints import read_csv_records, write_csv, write_json


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_DEPS = ROOT / ".deps_cobra"
WORKSPACE_CACHE = ROOT / ".runtime_cache"


def _add_workspace_deps_if_needed(package_name: str, deps_path: Path, index: int = 0) -> None:
    """Use bundled deps only when the active environment has no package."""

    if not deps_path.exists() or str(deps_path) in sys.path:
        return
    if importlib.util.find_spec(package_name) is None:
        sys.path.insert(index, str(deps_path))


_add_workspace_deps_if_needed("cobra", WORKSPACE_DEPS)

WORKSPACE_CACHE.mkdir(exist_ok=True)
os.environ["LOCALAPPDATA"] = str(WORKSPACE_CACHE / "localappdata")
os.environ["XDG_CACHE_HOME"] = str(WORKSPACE_CACHE / "xdg_cache")


@dataclass(slots=True)
class FbaWorkflowResult:
    """Summary returned by the optional COBRApy workflow."""

    cobra_available: bool
    status: str
    output_dir: str
    message: str
    files: dict[str, str]


def cobrapy_available() -> bool:
    """Return whether COBRApy can be imported in the current Python env."""

    _redirect_cobra_cache()
    try:
        importlib.import_module("cobra")
        importlib.import_module("cobra.io")
    except Exception:
        return False
    return True


def run_fba_workflow(
    model_path: str | Path,
    exchange_bounds_path: str | Path,
    flux_targets_path: str | Path,
    output_dir: str | Path,
    require_cobra: bool = False,
    run_pfba: bool = True,
    run_fva: bool = True,
    fva_fraction_of_optimum: float = 0.95,
    objective_reaction_id: str = "",
    objective_direction: str = "max",
    fva_reaction_scope: str = "targets",
    loopless: bool = False,
    pfba_factor: float | str | None = None,
    fva_processes: int = 1,
) -> FbaWorkflowResult:
    """Run condition-wise FBA and compare predicted fluxes with targets.

    If COBRApy is unavailable and ``require_cobra`` is false, a skip manifest is
    written and the function returns a successful degraded result.
    """

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    if not cobrapy_available():
        message = "COBRApy is not installed; skipped FBA execution."
        manifest = {
            "cobra_available": False,
            "status": "skipped",
            "message": message,
            "model_path": str(model_path),
            "exchange_bounds_path": str(exchange_bounds_path),
            "flux_targets_path": str(flux_targets_path),
            "run_pfba": run_pfba,
            "run_fva": run_fva,
            "fva_fraction_of_optimum": fva_fraction_of_optimum,
            "objective_reaction_id": objective_reaction_id,
            "objective_direction": objective_direction,
            "fva_reaction_scope": fva_reaction_scope,
            "loopless": loopless,
            "pfba_factor": pfba_factor,
            "fva_processes": fva_processes,
        }
        manifest_path = output / "cobra_runner_manifest.json"
        write_json(manifest_path, manifest)
        if require_cobra:
            raise RuntimeError(message)
        return FbaWorkflowResult(
            cobra_available=False,
            status="skipped",
            output_dir=str(output),
            message=message,
            files={"manifest": str(manifest_path)},
        )

    _redirect_cobra_cache()
    from cobra.io import read_sbml_model
    from cobra.flux_analysis import flux_variability_analysis, pfba

    model = read_sbml_model(str(model_path))
    exchange_rows = read_csv_records(exchange_bounds_path)
    target_rows = read_csv_records(flux_targets_path)
    exchange_by_condition = group_by_condition(exchange_rows)
    targets_by_condition = group_by_condition(target_rows)

    fba_summary: list[dict[str, object]] = []
    predicted_rows: list[dict[str, object]] = []
    comparison_rows: list[dict[str, object]] = []
    pfba_rows: list[dict[str, object]] = []
    pfba_comparison_rows: list[dict[str, object]] = []
    fva_rows: list[dict[str, object]] = []

    conditions = sorted(set(exchange_by_condition) | set(targets_by_condition))
    if not conditions:
        conditions = ["default"]
    for condition in conditions:
        bounds = exchange_by_condition.get(condition, [])
        targets = targets_by_condition.get(condition, [])

        with model:
            applied, failed = apply_exchange_bounds(model, bounds)
            objective_override_status = apply_objective_override(
                model,
                objective_reaction_id=objective_reaction_id,
                objective_direction=objective_direction,
            )
            solution = model.optimize()
            status = getattr(solution, "status", "unknown")
            objective_value = _safe_float(getattr(solution, "objective_value", None))
            flux_map = {}
            predicted_flux_map = {}
            pfba_status = "skipped"
            pfba_total_flux_objective = None
            fva_status = "skipped"
            if status == "optimal":
                flux_map = {reaction_id: _safe_float(value) for reaction_id, value in solution.fluxes.items()}
                predicted_flux_map = with_cobra_id_aliases(flux_map)

                if run_pfba:
                    try:
                        pfba_solution = pfba(model)
                        pfba_status = getattr(pfba_solution, "status", "unknown")
                        pfba_total_flux_objective = _safe_float(getattr(pfba_solution, "objective_value", None))
                        pfba_flux_map = {
                            reaction_id: _safe_float(value) for reaction_id, value in pfba_solution.fluxes.items()
                        }
                        pfba_predicted_map = with_cobra_id_aliases(pfba_flux_map)
                        for reaction_id, flux in pfba_flux_map.items():
                            pfba_rows.append(
                                {
                                    "condition": condition,
                                    "reaction_id": reaction_id,
                                    "predicted_flux": flux,
                                }
                            )
                        pfba_comparison_rows.extend(
                            compare_flux_targets(condition, pfba_predicted_map, targets, pfba_status, method="pFBA")
                        )
                    except Exception as exc:
                        pfba_status = f"failed: {type(exc).__name__}: {exc}"

                if run_fva:
                    try:
                        target_reactions = resolve_fva_reactions(
                            model,
                            targets,
                            scope=fva_reaction_scope,
                            objective_reaction_id=objective_reaction_id,
                        )
                        if target_reactions:
                            fva_kwargs = {
                                "reaction_list": target_reactions,
                                "fraction_of_optimum": fva_fraction_of_optimum,
                                "loopless": loopless,
                                "processes": max(1, int(fva_processes or 1)),
                            }
                            pfba_factor_value = _to_float(pfba_factor)
                            if pfba_factor_value is not None:
                                fva_kwargs["pfba_factor"] = pfba_factor_value
                            fva_result = flux_variability_analysis(model, **fva_kwargs)
                            fva_rows.extend(
                                build_target_fva_rows(
                                    condition,
                                    targets,
                                    fva_result,
                                    fva_fraction_of_optimum,
                                )
                            )
                            fva_status = "completed"
                        else:
                            fva_status = "no_target_reactions"
                    except Exception as exc:
                        fva_status = f"failed: {type(exc).__name__}: {exc}"

            fba_summary.append(
                {
                    "condition": condition,
                    "status": status,
                    "objective_value": objective_value,
                    "pfba_status": pfba_status,
                    "pfba_total_flux_objective": pfba_total_flux_objective,
                    "fva_status": fva_status,
                    "objective_override_status": objective_override_status,
                    "applied_bounds": applied,
                    "failed_bounds": failed,
                }
            )

            for reaction_id, flux in flux_map.items():
                predicted_rows.append(
                    {
                        "condition": condition,
                        "reaction_id": reaction_id,
                        "predicted_flux": flux,
                    }
                )

            comparison_rows.extend(compare_flux_targets(condition, predicted_flux_map, targets, status, method="FBA"))

    files = {
        "summary": str(output / "fba_summary.csv"),
        "predicted_fluxes": str(output / "predicted_fluxes.csv"),
        "flux_validation": str(output / "flux_validation_comparison.csv"),
        "flux_validation_summary": str(output / "flux_validation_summary.csv"),
        "pfba_fluxes": str(output / "pfba_fluxes.csv"),
        "pfba_validation": str(output / "pfba_validation_comparison.csv"),
        "pfba_validation_summary": str(output / "pfba_validation_summary.csv"),
        "target_fva": str(output / "target_fva.csv"),
        "target_fva_summary": str(output / "target_fva_summary.csv"),
        "manifest": str(output / "cobra_runner_manifest.json"),
    }
    write_csv(files["summary"], fba_summary)
    write_csv(files["predicted_fluxes"], predicted_rows)
    write_csv(files["flux_validation"], comparison_rows)
    write_csv(files["flux_validation_summary"], summarize_flux_comparison(comparison_rows))
    write_csv(files["pfba_fluxes"], pfba_rows)
    write_csv(files["pfba_validation"], pfba_comparison_rows)
    write_csv(files["pfba_validation_summary"], summarize_flux_comparison(pfba_comparison_rows))
    write_csv(files["target_fva"], fva_rows)
    write_csv(files["target_fva_summary"], summarize_fva_coverage(fva_rows))

    manifest = {
        "cobra_available": True,
        "status": "completed",
        "model_path": str(model_path),
        "exchange_bounds_path": str(exchange_bounds_path),
        "flux_targets_path": str(flux_targets_path),
        "condition_count": len(conditions),
        "conditions": conditions,
        "run_pfba": run_pfba,
        "run_fva": run_fva,
        "fva_fraction_of_optimum": fva_fraction_of_optimum,
        "objective_reaction_id": objective_reaction_id,
        "objective_direction": objective_direction,
        "fva_reaction_scope": fva_reaction_scope,
        "loopless": loopless,
        "pfba_factor": pfba_factor,
        "fva_processes": fva_processes,
        "files": files,
    }
    write_json(files["manifest"], manifest)
    return FbaWorkflowResult(
        cobra_available=True,
        status="completed",
        output_dir=str(output),
        message=f"Completed FBA for {len(conditions)} conditions.",
        files=files,
    )


def run_context_feasibility_workflow(
    model_path: str | Path,
    exchange_bounds_path: str | Path,
    context_policy_path: str | Path,
    output_dir: str | Path,
    knockout_decisions: set[str] | None = None,
    require_cobra: bool = False,
) -> FbaWorkflowResult:
    """Apply lightweight context delete candidates and test FBA feasibility."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    if knockout_decisions is None:
        knockout_decisions = {"delete_candidate"}

    if not cobrapy_available():
        message = "COBRApy is not installed; skipped context feasibility execution."
        manifest_path = output / "context_feasibility_manifest.json"
        write_json(
            manifest_path,
            {
                "cobra_available": False,
                "status": "skipped",
                "message": message,
                "model_path": str(model_path),
                "exchange_bounds_path": str(exchange_bounds_path),
                "context_policy_path": str(context_policy_path),
            },
        )
        if require_cobra:
            raise RuntimeError(message)
        return FbaWorkflowResult(
            cobra_available=False,
            status="skipped",
            output_dir=str(output),
            message=message,
            files={"manifest": str(manifest_path)},
        )

    _redirect_cobra_cache()
    from cobra.io import read_sbml_model

    model = read_sbml_model(str(model_path))
    exchange_by_condition = group_by_condition(read_csv_records(exchange_bounds_path))
    policy_by_condition = group_by_condition(read_csv_records(context_policy_path))

    summary_rows: list[dict[str, object]] = []
    knockout_rows: list[dict[str, object]] = []
    conditions = sorted(set(exchange_by_condition) | set(policy_by_condition))

    for condition in conditions:
        bounds = exchange_by_condition.get(condition, [])
        policy_rows = policy_by_condition.get(condition, [])
        with model:
            applied, failed = apply_exchange_bounds(model, bounds)
            knocked_out, knockout_failed = apply_context_knockouts(model, policy_rows, knockout_decisions)
            solution = model.optimize()
            status = getattr(solution, "status", "unknown")
            objective_value = _safe_float(getattr(solution, "objective_value", None))
            summary_rows.append(
                {
                    "condition": condition,
                    "status": status,
                    "objective_value": objective_value,
                    "exchange_bounds_applied": applied,
                    "exchange_bounds_failed": failed,
                    "knockout_count": len(knocked_out),
                    "knockout_failed": knockout_failed,
                }
            )
            for row in knocked_out:
                knockout_rows.append(row)

    files = {
        "summary": str(output / "context_feasibility_summary.csv"),
        "knockouts": str(output / "context_knockouts.csv"),
        "manifest": str(output / "context_feasibility_manifest.json"),
    }
    write_csv(files["summary"], summary_rows)
    write_csv(files["knockouts"], knockout_rows)
    write_json(
        files["manifest"],
        {
            "cobra_available": True,
            "status": "completed",
            "model_path": str(model_path),
            "exchange_bounds_path": str(exchange_bounds_path),
            "context_policy_path": str(context_policy_path),
            "conditions": conditions,
            "knockout_decisions": sorted(knockout_decisions),
            "files": files,
        },
    )
    return FbaWorkflowResult(
        cobra_available=True,
        status="completed",
        output_dir=str(output),
        message=f"Completed context feasibility for {len(conditions)} conditions.",
        files=files,
    )


def group_by_condition(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    """Group CSV rows by condition, falling back to sample."""

    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        condition = row.get("condition") or row.get("sample") or "default"
        grouped.setdefault(condition, []).append(row)
    return grouped


def apply_exchange_bounds(model: Any, rows: list[dict[str, str]]) -> tuple[int, int]:
    """Apply exchange bounds to a COBRApy model, returning applied/failed counts."""

    applied = 0
    failed = 0
    for row in rows:
        if row.get("status") not in {"mapped", "", None}:
            continue
        reaction_id = row.get("model_reaction_id") or row.get("reaction_id")
        if not reaction_id:
            failed += 1
            continue
        try:
            reaction = get_cobra_reaction(model, reaction_id)
            lower = _to_float(row.get("lower_bound"))
            upper = _to_float(row.get("upper_bound"))
            if lower is not None:
                reaction.lower_bound = lower
            if upper is not None:
                reaction.upper_bound = upper
            applied += 1
        except Exception:
            failed += 1
    return applied, failed


def apply_context_knockouts(
    model: Any,
    policy_rows: list[dict[str, str]],
    knockout_decisions: set[str],
) -> tuple[list[dict[str, object]], int]:
    """Set selected context policy reactions to zero flux."""

    knocked_out: list[dict[str, object]] = []
    failed = 0
    for row in policy_rows:
        if row.get("decision") not in knockout_decisions:
            continue
        reaction_id = row.get("cobra_reaction_id") or row.get("reaction_id", "")
        try:
            reaction = get_cobra_reaction(model, reaction_id)
            old_lower, old_upper = reaction.bounds
            reaction.lower_bound = 0
            reaction.upper_bound = 0
            knocked_out.append(
                {
                    "condition": row.get("condition", ""),
                    "reaction_id": row.get("reaction_id", ""),
                    "cobra_reaction_id": reaction.id,
                    "decision": row.get("decision", ""),
                    "reason": row.get("reason", ""),
                    "old_lower_bound": old_lower,
                    "old_upper_bound": old_upper,
                }
            )
        except Exception:
            failed += 1
    return knocked_out, failed


def compare_flux_targets(
    condition: str,
    predicted_fluxes: dict[str, float | None],
    target_rows: list[dict[str, str]],
    solve_status: str = "optimal",
    method: str = "FBA",
) -> list[dict[str, object]]:
    """Compare predicted fluxes against measured flux targets."""

    rows: list[dict[str, object]] = []
    for target in target_rows:
        reaction_id = target.get("model_reaction_id") or target.get("reaction_id", "")
        measured = _to_float(target.get("measured_flux") or target.get("flux"))
        predicted = predicted_fluxes.get(reaction_id)
        lower_ci = _to_float(target.get("lower_ci"))
        upper_ci = _to_float(target.get("upper_ci"))
        residual = None
        abs_residual = None
        within_ci = None
        if predicted is not None and measured is not None:
            residual = predicted - measured
            abs_residual = abs(residual)
        if predicted is not None and lower_ci is not None and upper_ci is not None:
            within_ci = lower_ci <= predicted <= upper_ci

        rows.append(
            {
                "method": method,
                "condition": condition,
                "sample": target.get("sample", ""),
                "reaction_id": target.get("reaction_id", ""),
                "model_reaction_id": reaction_id,
                "measured_flux": measured,
                "predicted_flux": predicted,
                "residual": residual,
                "abs_residual": abs_residual,
                "lower_ci": lower_ci,
                "upper_ci": upper_ci,
                "within_ci": within_ci,
                "unit": target.get("unit", ""),
                "solve_status": solve_status,
                "mapping_status": target.get("status", ""),
                "note": target.get("note", ""),
            }
        )
    return rows


def resolve_target_reactions(model: Any, target_rows: list[dict[str, str]]) -> list[Any]:
    """Resolve unique validation target reactions for targeted FVA."""

    reactions = []
    seen: set[str] = set()
    for target in target_rows:
        reaction_id = target.get("model_reaction_id") or target.get("reaction_id", "")
        if not reaction_id:
            continue
        try:
            reaction = get_cobra_reaction(model, reaction_id)
        except Exception:
            continue
        if reaction.id in seen:
            continue
        seen.add(reaction.id)
        reactions.append(reaction)
    return reactions


def resolve_fva_reactions(
    model: Any,
    target_rows: list[dict[str, str]],
    *,
    scope: str = "targets",
    objective_reaction_id: str = "",
) -> list[Any]:
    """Resolve the reaction scope requested for FVA."""

    if scope == "all_reactions":
        return list(model.reactions)
    reactions = resolve_target_reactions(model, target_rows)
    if scope == "objective_and_targets":
        objective_reaction = resolve_objective_reaction(model, objective_reaction_id)
        if objective_reaction is not None and objective_reaction.id not in {reaction.id for reaction in reactions}:
            reactions.append(objective_reaction)
    return reactions


def apply_objective_override(
    model: Any,
    *,
    objective_reaction_id: str = "",
    objective_direction: str = "max",
) -> str:
    """Apply an optional objective reaction override for one solve context."""

    if not objective_reaction_id:
        return "default_objective"
    reaction = resolve_objective_reaction(model, objective_reaction_id)
    if reaction is None:
        return "objective_override_not_found"
    model.objective = reaction
    try:
        model.objective_direction = "min" if objective_direction == "min" else "max"
    except Exception:
        return f"objective_override_applied_direction_unsupported:{reaction.id}"
    return f"objective_override_applied:{reaction.id}:{model.objective_direction}"


def resolve_objective_reaction(model: Any, reaction_id: str) -> Any | None:
    """Resolve a user-entered objective reaction ID without raising."""

    if reaction_id:
        try:
            return get_cobra_reaction(model, reaction_id)
        except Exception:
            return None
    return None


def build_target_fva_rows(
    condition: str,
    target_rows: list[dict[str, str]],
    fva_result: Any,
    fraction_of_optimum: float,
) -> list[dict[str, object]]:
    """Join targeted FVA ranges back onto measured flux targets."""

    rows: list[dict[str, object]] = []
    for target in target_rows:
        model_reaction_id = target.get("model_reaction_id") or target.get("reaction_id", "")
        cobra_reaction_id = model_reaction_id[2:] if model_reaction_id.startswith("R_") else model_reaction_id
        measured = _to_float(target.get("measured_flux") or target.get("flux"))
        minimum = _lookup_fva_value(fva_result, cobra_reaction_id, "minimum")
        maximum = _lookup_fva_value(fva_result, cobra_reaction_id, "maximum")
        within_fva = None
        if measured is not None and minimum is not None and maximum is not None:
            within_fva = minimum <= measured <= maximum

        rows.append(
            {
                "condition": condition,
                "sample": target.get("sample", ""),
                "reaction_id": target.get("reaction_id", ""),
                "model_reaction_id": model_reaction_id,
                "cobra_reaction_id": cobra_reaction_id,
                "measured_flux": measured,
                "fva_minimum": minimum,
                "fva_maximum": maximum,
                "within_fva": within_fva,
                "fraction_of_optimum": fraction_of_optimum,
                "unit": target.get("unit", ""),
                "mapping_status": target.get("status", ""),
                "note": target.get("note", ""),
            }
        )
    return rows


def _lookup_fva_value(fva_result: Any, reaction_id: str, column: str) -> float | None:
    try:
        return _safe_float(fva_result.loc[reaction_id, column])
    except Exception:
        return None


def summarize_flux_comparison(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Summarize flux validation comparison by condition and overall."""

    by_condition: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        by_condition.setdefault(str(row.get("condition") or "default"), []).append(row)

    summary = [_summarize_one(condition, condition_rows) for condition, condition_rows in sorted(by_condition.items())]
    if rows:
        summary.append(_summarize_one("ALL", rows))
    return summary


def summarize_fva_coverage(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Summarize measured-flux coverage by FVA ranges."""

    by_condition: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        by_condition.setdefault(str(row.get("condition") or "default"), []).append(row)

    summary = [_summarize_fva_one(condition, condition_rows) for condition, condition_rows in sorted(by_condition.items())]
    if rows:
        summary.append(_summarize_fva_one("ALL", rows))
    return summary


def _summarize_fva_one(condition: str, rows: list[dict[str, object]]) -> dict[str, object]:
    comparable = [
        row
        for row in rows
        if row.get("measured_flux") is not None
        and row.get("fva_minimum") is not None
        and row.get("fva_maximum") is not None
    ]
    within_fva = [row for row in comparable if row.get("within_fva") is True]
    widths = [
        float(row["fva_maximum"]) - float(row["fva_minimum"])
        for row in comparable
        if row.get("fva_minimum") is not None and row.get("fva_maximum") is not None
    ]
    return {
        "condition": condition,
        "target_count": len(rows),
        "comparable_count": len(comparable),
        "within_fva_count": len(within_fva),
        "within_fva_fraction": len(within_fva) / len(comparable) if comparable else None,
        "mean_fva_width": sum(widths) / len(widths) if widths else None,
    }


def _summarize_one(condition: str, rows: list[dict[str, object]]) -> dict[str, object]:
    comparable = [row for row in rows if row.get("predicted_flux") is not None and row.get("measured_flux") is not None]
    within_ci = [row for row in comparable if row.get("within_ci") is True]
    abs_residuals = [float(row["abs_residual"]) for row in comparable if row.get("abs_residual") is not None]
    mean_abs_residual = sum(abs_residuals) / len(abs_residuals) if abs_residuals else None
    return {
        "condition": condition,
        "target_count": len(rows),
        "comparable_count": len(comparable),
        "within_ci_count": len(within_ci),
        "within_ci_fraction": len(within_ci) / len(comparable) if comparable else None,
        "mean_abs_residual": mean_abs_residual,
    }


def with_cobra_id_aliases(fluxes: dict[str, float | None]) -> dict[str, float | None]:
    """Add SBML-style R_ aliases for COBRApy reaction ids."""

    aliased = dict(fluxes)
    for reaction_id, value in fluxes.items():
        if reaction_id.startswith("R_"):
            aliased.setdefault(reaction_id[2:], value)
        else:
            aliased.setdefault(f"R_{reaction_id}", value)
    return aliased


def get_cobra_reaction(model: Any, reaction_id: str) -> Any:
    """Resolve a reaction id against COBRApy's often prefix-stripped ids."""

    candidates = [reaction_id]
    if reaction_id.startswith("R_"):
        candidates.append(reaction_id[2:])
    else:
        candidates.append(f"R_{reaction_id}")
    last_error: Exception | None = None
    for candidate in candidates:
        try:
            return model.reactions.get_by_id(candidate)
        except Exception as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    raise KeyError(reaction_id)


def _redirect_cobra_cache() -> None:
    """Force COBRApy/appdirs cache writes into the project workspace."""

    try:
        import appdirs

        cache_dir = WORKSPACE_CACHE / "cobrapy"
        cache_dir.mkdir(parents=True, exist_ok=True)

        def user_cache_dir(*_args, **_kwargs):
            return str(cache_dir)

        appdirs.user_cache_dir = user_cache_dir
    except Exception:
        return


def _safe_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: object) -> float | None:
    return _safe_float(value)
