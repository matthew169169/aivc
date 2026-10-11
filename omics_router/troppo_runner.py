"""Optional TROPPO runner for FASTcore context reconstruction.

The module is importable without TROPPO. Actual reconstruction is attempted
only inside ``run_troppo_fastcore_workflow``.
"""

from __future__ import annotations

import contextlib
import importlib
import importlib.util
import io
import os
import sys
import warnings
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
from .constraints import read_csv_records, write_csv, write_json
from .omics_qc import build_omics_signal_quality


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_TROPPO_DEPS = ROOT / ".deps_troppo"
WORKSPACE_COBRA_DEPS = ROOT / ".deps_cobra"
WORKSPACE_CACHE = ROOT / ".runtime_cache"


def _add_workspace_deps_if_needed(package_name: str, deps_path: Path, index: int = 0) -> None:
    """Use bundled deps only when the active environment has no package."""

    if not deps_path.exists() or str(deps_path) in sys.path:
        return
    if importlib.util.find_spec(package_name) is None:
        sys.path.insert(index, str(deps_path))


_add_workspace_deps_if_needed("troppo", WORKSPACE_TROPPO_DEPS, 0)
_add_workspace_deps_if_needed("cobra", WORKSPACE_COBRA_DEPS, 1)

WORKSPACE_CACHE.mkdir(exist_ok=True)
os.environ["LOCALAPPDATA"] = str(WORKSPACE_CACHE / "localappdata")
os.environ["XDG_CACHE_HOME"] = str(WORKSPACE_CACHE / "xdg_cache")


@dataclass(slots=True)
class TroppoWorkflowResult:
    """Summary returned by the optional TROPPO workflow."""

    troppo_available: bool
    cobra_available: bool
    status: str
    output_dir: str
    message: str
    files: dict[str, str]


@dataclass(slots=True)
class FastcoreConditionInput:
    """Prepared condition-specific input for TROPPO FASTcore."""

    S: Any
    lb: Any
    ub: Any
    reaction_ids: list[str]
    metabolite_ids: list[str]
    core_indices: list[int]
    core_rows: list[dict[str, object]]
    candidate_core_count: int
    filtered_core_count: int
    unresolved_core_count: int
    unresolved_exchange_count: int


def troppo_available() -> bool:
    """Return whether TROPPO FASTcore can be imported."""

    try:
        _import_fastcore()
        return True
    except Exception:
        return False


def run_troppo_fastcore_workflow(
    model_path: str | Path,
    core_reactions_path: str | Path,
    exchange_bounds_path: str | Path,
    output_dir: str | Path,
    gene_evidence_path: str | Path | None = None,
    reaction_evidence_path: str | Path | None = None,
    require_troppo: bool = False,
    solver: str = "GLPK",
    flux_threshold: float = 1e-4,
    protect_objective: bool = True,
    protect_exchange_bounds: bool = True,
    filter_inactive_core: bool = True,
    run_feasibility_check: bool = True,
) -> TroppoWorkflowResult:
    """Run condition-wise TROPPO FASTcore from prepared core reactions.

    The runner consumes ``fastcore_core_reactions.csv`` from the constraint
    builder and protects objective / measured exchange reactions by default so
    the reconstructed context model remains directly testable with COBRApy.
    """

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "summary": str(output / "troppo_fastcore_summary.csv"),
        "core_inputs": str(output / "troppo_fastcore_core_inputs.csv"),
        "selected_reactions": str(output / "troppo_fastcore_selected_reactions.csv"),
        "removed_reactions": str(output / "troppo_fastcore_removed_reactions.csv"),
        "omics_quality": str(output / "omics_signal_quality.csv"),
        "omics_recommendations": str(output / "omics_signal_recommendations.csv"),
        "manifest": str(output / "troppo_fastcore_manifest.json"),
    }

    cobra_ok = cobrapy_available()
    if not cobra_ok:
        message = "COBRApy is not installed; skipped TROPPO FASTcore execution."
        _write_skip_manifest(
            files["manifest"],
            message=message,
            cobra_available=False,
            troppo_available=False,
            model_path=model_path,
            core_reactions_path=core_reactions_path,
            exchange_bounds_path=exchange_bounds_path,
            solver=solver,
            flux_threshold=flux_threshold,
        )
        if require_troppo:
            raise RuntimeError(message)
        return TroppoWorkflowResult(
            troppo_available=False,
            cobra_available=False,
            status="skipped",
            output_dir=str(output),
            message=message,
            files={"manifest": files["manifest"]},
        )

    import_error = _troppo_import_error()
    if import_error:
        message = f"TROPPO FASTcore is not importable; skipped execution. {import_error}"
        _write_skip_manifest(
            files["manifest"],
            message=message,
            cobra_available=True,
            troppo_available=False,
            model_path=model_path,
            core_reactions_path=core_reactions_path,
            exchange_bounds_path=exchange_bounds_path,
            solver=solver,
            flux_threshold=flux_threshold,
        )
        if require_troppo:
            raise RuntimeError(message)
        return TroppoWorkflowResult(
            troppo_available=False,
            cobra_available=True,
            status="skipped",
            output_dir=str(output),
            message=message,
            files={"manifest": files["manifest"]},
        )

    _redirect_cobra_cache()
    FASTcore, FastcoreProperties = _import_fastcore()
    from cobra.io import read_sbml_model

    model = read_sbml_model(str(model_path))
    core_rows = read_csv_records(core_reactions_path)
    exchange_rows = read_csv_records(exchange_bounds_path)
    core_by_condition = group_by_condition(core_rows)
    exchange_by_condition = group_by_condition(exchange_rows)
    conditions = sorted(set(core_by_condition) | set(exchange_by_condition))

    summary_rows: list[dict[str, object]] = []
    all_core_input_rows: list[dict[str, object]] = []
    all_selected_rows: list[dict[str, object]] = []
    all_removed_rows: list[dict[str, object]] = []
    logs: dict[str, str] = {}

    for condition in conditions:
        log_path = output / f"{_safe_name(condition)}.fastcore.log"
        with model:
            applied_bounds, failed_bounds = apply_exchange_bounds(model, exchange_by_condition.get(condition, []))
            prepared = prepare_fastcore_condition(
                model=model,
                core_rows=core_by_condition.get(condition, []),
                exchange_rows=exchange_by_condition.get(condition, []),
                condition=condition,
                protect_objective=protect_objective,
                protect_exchange_bounds=protect_exchange_bounds,
                filter_inactive_core=filter_inactive_core,
                core_filter_threshold=flux_threshold,
            )
            all_core_input_rows.extend(prepared.core_rows)

            log_buffer = io.StringIO()
            selected_indices: list[int] = []
            run_status = "failed"
            run_message = ""
            feasibility_status = "skipped"
            feasibility_objective = None
            knocked_out_count = None
            try:
                properties = FastcoreProperties(
                    core=prepared.core_indices,
                    flux_threshold=flux_threshold,
                    solver=solver,
                )
                with contextlib.redirect_stdout(log_buffer):
                    selected_indices = normalize_selected_indices(
                        FASTcore(prepared.S, prepared.lb, prepared.ub, properties).run(),
                        len(prepared.reaction_ids),
                    )
                run_status = "completed"
                if run_feasibility_check:
                    feasibility_status, feasibility_objective, knocked_out_count = test_selected_model_feasibility(
                        model,
                        selected_indices,
                        minimum_objective=flux_threshold,
                    )
            except Exception as exc:
                run_message = f"{type(exc).__name__}: {exc}"
                log_buffer.write(run_message)

            log_text = log_buffer.getvalue()
            log_path.write_text(log_text, encoding="utf-8")
            logs[condition] = str(log_path)

            selected_set = set(selected_indices)
            source_by_index = {int(row["reaction_index"]): str(row["source"]) for row in prepared.core_rows}
            all_selected_rows.extend(
                build_selected_rows(condition, model, selected_indices, source_by_index, prepared.lb, prepared.ub)
            )
            all_removed_rows.extend(
                build_removed_rows(condition, model, selected_set, source_by_index, prepared.lb, prepared.ub)
            )

            summary_rows.append(
                {
                    "condition": condition,
                    "status": run_status,
                    "message": run_message,
                    "core_input_count": len(prepared.core_indices),
                    "candidate_core_count": prepared.candidate_core_count,
                    "filtered_core_count": prepared.filtered_core_count,
                    "selected_count": len(selected_indices),
                    "removed_count": len(prepared.reaction_ids) - len(selected_indices) if selected_indices else None,
                    "applied_exchange_bounds": applied_bounds,
                    "failed_exchange_bounds": failed_bounds,
                    "unresolved_core_count": prepared.unresolved_core_count,
                    "unresolved_protected_exchange_count": prepared.unresolved_exchange_count,
                    "feasibility_status": feasibility_status,
                    "feasibility_objective": feasibility_objective,
                    "knocked_out_reactions": knocked_out_count,
                    "log": str(log_path),
                }
            )

    write_csv(files["summary"], summary_rows)
    write_csv(files["core_inputs"], all_core_input_rows)
    write_csv(files["selected_reactions"], all_selected_rows)
    write_csv(files["removed_reactions"], all_removed_rows)
    qc_files = build_omics_signal_quality(
        gene_evidence_path=gene_evidence_path,
        reaction_evidence_path=reaction_evidence_path,
        fastcore_core_path=core_reactions_path,
        troppo_summary_path=files["summary"],
        troppo_selected_path=files["selected_reactions"],
        output_dir=output,
    )
    files["omics_quality"] = qc_files["quality"]
    files["omics_recommendations"] = qc_files["recommendations"]
    files["omics_quality_manifest"] = qc_files["quality_manifest"]

    overall_status = "completed"
    if any(row["status"] == "failed" for row in summary_rows):
        overall_status = "completed_with_failures"
    manifest = {
        "cobra_available": True,
        "troppo_available": True,
        "status": overall_status,
        "model_path": str(model_path),
        "core_reactions_path": str(core_reactions_path),
        "exchange_bounds_path": str(exchange_bounds_path),
        "gene_evidence_path": str(gene_evidence_path) if gene_evidence_path else "",
        "reaction_evidence_path": str(reaction_evidence_path) if reaction_evidence_path else "",
        "conditions": conditions,
        "solver": solver,
        "flux_threshold": flux_threshold,
        "protect_objective": protect_objective,
        "protect_exchange_bounds": protect_exchange_bounds,
        "filter_inactive_core": filter_inactive_core,
        "run_feasibility_check": run_feasibility_check,
        "logs": logs,
        "files": files,
    }
    write_json(files["manifest"], manifest)
    return TroppoWorkflowResult(
        troppo_available=True,
        cobra_available=True,
        status=overall_status,
        output_dir=str(output),
        message=f"Completed TROPPO FASTcore for {len(conditions)} conditions.",
        files=files,
    )


def prepare_fastcore_condition(
    model: Any,
    core_rows: list[dict[str, str]],
    exchange_rows: list[dict[str, str]],
    condition: str,
    protect_objective: bool = True,
    protect_exchange_bounds: bool = True,
    filter_inactive_core: bool = True,
    core_filter_threshold: float = 1e-4,
) -> FastcoreConditionInput:
    """Build S/lb/ub and core indices for one condition."""

    import numpy as np
    from cobra.util.array import create_stoichiometric_matrix

    reactions = list(model.reactions)
    metabolites = list(model.metabolites)
    S = np.asarray(create_stoichiometric_matrix(model, array_type="dense"), dtype=float)
    lb = np.asarray([reaction.lower_bound for reaction in reactions], dtype=float)
    ub = np.asarray([reaction.upper_bound for reaction in reactions], dtype=float)
    reaction_to_index = {reaction.id: index for index, reaction in enumerate(reactions)}
    sources: dict[int, set[str]] = {}
    scores: dict[int, object] = {}
    original_ids: dict[int, str] = {}
    unresolved_core = 0
    unresolved_exchange = 0

    for row in core_rows:
        if row.get("status") not in {"core", "", None}:
            continue
        raw_id = row.get("cobra_reaction_id") or row.get("reaction_id") or ""
        try:
            reaction = get_cobra_reaction(model, raw_id)
        except Exception:
            unresolved_core += 1
            continue
        index = reaction_to_index[reaction.id]
        sources.setdefault(index, set()).add("evidence_core")
        scores.setdefault(index, row.get("reaction_score", ""))
        original_ids.setdefault(index, row.get("reaction_id", raw_id))

    if protect_objective:
        for index, reaction in enumerate(reactions):
            coefficient = getattr(reaction, "objective_coefficient", 0) or 0
            if coefficient != 0:
                sources.setdefault(index, set()).add("protected_objective")

    if protect_exchange_bounds:
        for row in exchange_rows:
            if row.get("status") not in {"mapped", "", None}:
                continue
            raw_id = row.get("model_reaction_id") or row.get("reaction_id") or ""
            try:
                reaction = get_cobra_reaction(model, raw_id)
            except Exception:
                unresolved_exchange += 1
                continue
            index = reaction_to_index[reaction.id]
            sources.setdefault(index, set()).add("protected_exchange")
            original_ids.setdefault(index, raw_id)

    candidate_core_count = len(sources)
    filtered_core_count = 0
    if filter_inactive_core and sources:
        kept_indices, filtered_indices = filter_core_by_flux_capacity(
            model,
            sorted(sources),
            source_by_index={index: ";".join(sorted(source_set)) for index, source_set in sources.items()},
            threshold=core_filter_threshold,
        )
        sources = {index: sources[index] for index in kept_indices}
        filtered_core_count = len(filtered_indices)

    core_indices = sorted(sources)
    input_rows = []
    for index in core_indices:
        reaction = reactions[index]
        input_rows.append(
            {
                "condition": condition,
                "reaction_index": index,
                "reaction_id": original_ids.get(index, sbml_reaction_id(reaction.id)),
                "cobra_reaction_id": reaction.id,
                "source": ";".join(sorted(sources[index])),
                "reaction_score": scores.get(index, ""),
                "lower_bound": lb[index],
                "upper_bound": ub[index],
            }
        )

    return FastcoreConditionInput(
        S=S,
        lb=lb,
        ub=ub,
        reaction_ids=[reaction.id for reaction in reactions],
        metabolite_ids=[metabolite.id for metabolite in metabolites],
        core_indices=core_indices,
        core_rows=input_rows,
        candidate_core_count=candidate_core_count,
        filtered_core_count=filtered_core_count,
        unresolved_core_count=unresolved_core,
        unresolved_exchange_count=unresolved_exchange,
    )


def filter_core_by_flux_capacity(
    model: Any,
    core_indices: list[int],
    source_by_index: dict[int, str],
    threshold: float,
) -> tuple[list[int], list[int]]:
    """Remove FASTcore core candidates that cannot carry flux in this condition."""

    from cobra.flux_analysis import flux_variability_analysis

    reactions = list(model.reactions)
    reaction_list = [reactions[index] for index in core_indices]
    try:
        fva = flux_variability_analysis(
            model,
            reaction_list=reaction_list,
            fraction_of_optimum=0.0,
            processes=1,
        )
    except Exception:
        return core_indices, []

    kept = []
    filtered = []
    for index in core_indices:
        reaction = reactions[index]
        source = source_by_index.get(index, "")
        minimum = _lookup_fva_value(fva, reaction.id, "minimum")
        maximum = _lookup_fva_value(fva, reaction.id, "maximum")
        capacity = max(abs(minimum or 0.0), abs(maximum or 0.0))
        if "protected_objective" in source or capacity >= threshold * 0.99:
            kept.append(index)
        else:
            filtered.append(index)
    return kept, filtered


def test_selected_model_feasibility(
    model: Any,
    selected_indices: list[int],
    minimum_objective: float = 1e-6,
) -> tuple[str, float | None, int]:
    """Knock out non-selected reactions and run FBA on the current model."""

    selected = set(selected_indices)
    knocked_out = 0
    for index, reaction in enumerate(model.reactions):
        if index in selected:
            continue
        if reaction.lower_bound != 0 or reaction.upper_bound != 0:
            reaction.lower_bound = 0
            reaction.upper_bound = 0
            knocked_out += 1
    solution = model.optimize()
    status = str(getattr(solution, "status", "unknown"))
    objective = _safe_float(getattr(solution, "objective_value", None))
    if status == "optimal" and (objective is None or abs(objective) < minimum_objective):
        status = "optimal_zero_objective"
    return status, objective, knocked_out


def build_selected_rows(
    condition: str,
    model: Any,
    selected_indices: list[int],
    source_by_index: dict[int, str],
    lb: Any,
    ub: Any,
) -> list[dict[str, object]]:
    """Create CSV rows for selected FASTcore reactions."""

    rows = []
    for index in selected_indices:
        reaction = model.reactions[index]
        source = source_by_index.get(index, "supporting")
        rows.append(
            {
                "condition": condition,
                "reaction_index": index,
                "reaction_id": sbml_reaction_id(reaction.id),
                "cobra_reaction_id": reaction.id,
                "role": "core" if source != "supporting" else "supporting",
                "core_source": source,
                "lower_bound": _safe_float(lb[index]),
                "upper_bound": _safe_float(ub[index]),
            }
        )
    return rows


def build_removed_rows(
    condition: str,
    model: Any,
    selected_indices: set[int],
    source_by_index: dict[int, str],
    lb: Any,
    ub: Any,
) -> list[dict[str, object]]:
    """Create CSV rows for reactions removed from the context model."""

    rows = []
    for index, reaction in enumerate(model.reactions):
        if index in selected_indices:
            continue
        rows.append(
            {
                "condition": condition,
                "reaction_index": index,
                "reaction_id": sbml_reaction_id(reaction.id),
                "cobra_reaction_id": reaction.id,
                "was_core_input": index in source_by_index,
                "core_source": source_by_index.get(index, ""),
                "lower_bound": _safe_float(lb[index]),
                "upper_bound": _safe_float(ub[index]),
            }
        )
    return rows


def normalize_selected_indices(indices: Any, n_reactions: int) -> list[int]:
    """Return sorted, unique, in-range reaction indices."""

    if indices is None:
        return []
    normalized = []
    for value in list(indices):
        try:
            index = int(value)
        except (TypeError, ValueError):
            continue
        if 0 <= index < n_reactions:
            normalized.append(index)
    return sorted(set(normalized))


def sbml_reaction_id(cobra_reaction_id: str) -> str:
    """Return an SBML-style reaction id for COBRApy ids."""

    return cobra_reaction_id if cobra_reaction_id.startswith("R_") else f"R_{cobra_reaction_id}"


def _troppo_import_error() -> str:
    try:
        _import_fastcore()
        return ""
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"


def _import_fastcore() -> tuple[Any, Any]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        module = importlib.import_module("troppo.methods.reconstruction.fastcore")
    return module.FASTcore, module.FastcoreProperties


def _write_skip_manifest(
    manifest_path: str | Path,
    *,
    message: str,
    cobra_available: bool,
    troppo_available: bool,
    model_path: str | Path,
    core_reactions_path: str | Path,
    exchange_bounds_path: str | Path,
    solver: str,
    flux_threshold: float,
) -> None:
    write_json(
        manifest_path,
        {
            "cobra_available": cobra_available,
            "troppo_available": troppo_available,
            "status": "skipped",
            "message": message,
            "model_path": str(model_path),
            "core_reactions_path": str(core_reactions_path),
            "exchange_bounds_path": str(exchange_bounds_path),
            "solver": solver,
            "flux_threshold": flux_threshold,
        },
    )


def _safe_name(value: str) -> str:
    text = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
    return text or "default"


def _lookup_fva_value(fva_result: Any, reaction_id: str, column: str) -> float | None:
    try:
        return _safe_float(fva_result.loc[reaction_id, column])
    except Exception:
        return None


def _safe_float(value: object) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
