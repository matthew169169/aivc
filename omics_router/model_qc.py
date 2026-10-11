"""Lightweight GEM quality checks built on optional COBRApy."""

from __future__ import annotations

import os
import sys
import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cobra_runner import _redirect_cobra_cache, cobrapy_available
from .constraints import write_csv, write_json


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_DEPS = ROOT / ".deps_cobra"
WORKSPACE_CACHE = ROOT / ".runtime_cache"

if (
    WORKSPACE_DEPS.exists()
    and str(WORKSPACE_DEPS) not in sys.path
    and importlib.util.find_spec("cobra") is None
):
    sys.path.insert(0, str(WORKSPACE_DEPS))

WORKSPACE_CACHE.mkdir(exist_ok=True)
os.environ["LOCALAPPDATA"] = str(WORKSPACE_CACHE / "localappdata")
os.environ["XDG_CACHE_HOME"] = str(WORKSPACE_CACHE / "xdg_cache")


@dataclass(slots=True)
class ModelQcResult:
    """Summary returned by the optional model QC workflow."""

    cobra_available: bool
    status: str
    output_dir: str
    message: str
    files: dict[str, str]


def run_model_qc_workflow(
    model_path: str | Path,
    output_dir: str | Path,
    require_cobra: bool = False,
    run_blocked_check: bool = True,
    run_mass_balance_check: bool = True,
    open_exchanges_for_blocked_check: bool = False,
) -> ModelQcResult:
    """Run lightweight GEM structure and consistency QC."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "summary": str(output / "model_qc_summary.csv"),
        "objective": str(output / "model_qc_objective_reactions.csv"),
        "compartments": str(output / "model_qc_compartments.csv"),
        "reaction_flags": str(output / "model_qc_reaction_flags.csv"),
        "recommendations": str(output / "model_qc_recommendations.csv"),
        "manifest": str(output / "model_qc_manifest.json"),
    }

    if not cobrapy_available():
        message = "COBRApy is not installed; skipped model QC execution."
        write_json(
            files["manifest"],
            {
                "cobra_available": False,
                "status": "skipped",
                "message": message,
                "model_path": str(model_path),
                "run_blocked_check": run_blocked_check,
                "run_mass_balance_check": run_mass_balance_check,
            },
        )
        if require_cobra:
            raise RuntimeError(message)
        return ModelQcResult(
            cobra_available=False,
            status="skipped",
            output_dir=str(output),
            message=message,
            files={"manifest": files["manifest"]},
        )

    _redirect_cobra_cache()
    from cobra.io import read_sbml_model

    model = read_sbml_model(str(model_path))
    blocked_ids = set()
    blocked_status = "skipped"
    if run_blocked_check:
        blocked_ids, blocked_status = find_blocked_reaction_ids(model, open_exchanges_for_blocked_check)
    reaction_flags = build_reaction_flags(model, blocked_ids, run_mass_balance_check)
    summary = build_model_qc_summary(model, reaction_flags, blocked_status)
    recommendations = build_model_qc_recommendations(summary)

    write_csv(files["summary"], [summary])
    write_csv(files["objective"], build_objective_rows(model))
    write_csv(files["compartments"], build_compartment_rows(model))
    write_csv(files["reaction_flags"], reaction_flags)
    write_csv(files["recommendations"], recommendations)
    write_json(
        files["manifest"],
        {
            "cobra_available": True,
            "status": "completed",
            "model_path": str(model_path),
            "run_blocked_check": run_blocked_check,
            "run_mass_balance_check": run_mass_balance_check,
            "open_exchanges_for_blocked_check": open_exchanges_for_blocked_check,
            "files": files,
        },
    )
    return ModelQcResult(
        cobra_available=True,
        status="completed",
        output_dir=str(output),
        message="Completed model QC.",
        files=files,
    )


def find_blocked_reaction_ids(model: Any, open_exchanges: bool = False) -> tuple[set[str], str]:
    """Find blocked reactions with COBRApy, returning ids and status."""

    try:
        from cobra.flux_analysis import find_blocked_reactions

        blocked = find_blocked_reactions(
            model,
            open_exchanges=open_exchanges,
            processes=1,
        )
        return {getattr(reaction, "id", str(reaction)) for reaction in blocked}, "completed"
    except Exception as exc:
        return set(), f"failed: {type(exc).__name__}: {exc}"


def build_model_qc_summary(
    model: Any,
    reaction_flags: list[dict[str, object]],
    blocked_status: str,
) -> dict[str, object]:
    """Build one-row model QC summary."""

    reaction_count = len(model.reactions)
    metabolite_count = len(model.metabolites)
    gene_count = len(model.genes)
    objective_rows = build_objective_rows(model)
    exchange_count = sum(1 for reaction in model.reactions if is_exchange_reaction(reaction))
    boundary_count = sum(1 for reaction in model.reactions if getattr(reaction, "boundary", False))
    gpr_count = sum(1 for row in reaction_flags if row["has_gpr"] is True)
    blocked_count = sum(1 for row in reaction_flags if row["blocked"] is True)
    mass_imbalanced_count = sum(1 for row in reaction_flags if row["mass_balance_status"] == "imbalanced")
    missing_formula_count = sum(1 for metabolite in model.metabolites if not getattr(metabolite, "formula", None))
    missing_charge_count = sum(1 for metabolite in model.metabolites if getattr(metabolite, "charge", None) is None)
    fba_status, objective_value = optimize_model(model)
    summary = {
        "model_id": getattr(model, "id", "") or "",
        "reaction_count": reaction_count,
        "metabolite_count": metabolite_count,
        "gene_count": gene_count,
        "objective_reaction_count": len(objective_rows),
        "exchange_reaction_count": exchange_count,
        "boundary_reaction_count": boundary_count,
        "gpr_reaction_count": gpr_count,
        "gpr_reaction_fraction": _fraction(gpr_count, reaction_count),
        "blocked_check_status": blocked_status,
        "blocked_reaction_count": blocked_count,
        "blocked_reaction_fraction": _fraction(blocked_count, reaction_count),
        "mass_imbalanced_reaction_count": mass_imbalanced_count,
        "mass_imbalanced_reaction_fraction": _fraction(mass_imbalanced_count, reaction_count),
        "missing_formula_metabolite_count": missing_formula_count,
        "missing_formula_metabolite_fraction": _fraction(missing_formula_count, metabolite_count),
        "missing_charge_metabolite_count": missing_charge_count,
        "missing_charge_metabolite_fraction": _fraction(missing_charge_count, metabolite_count),
        "baseline_fba_status": fba_status,
        "baseline_objective_value": objective_value,
    }
    summary["qc_label"] = classify_model_qc(summary)
    summary["primary_recommendation"] = build_model_qc_recommendations(summary)[0]["recommendation"]
    return summary


def build_reaction_flags(
    model: Any,
    blocked_ids: set[str],
    run_mass_balance_check: bool = True,
) -> list[dict[str, object]]:
    """Build per-reaction QC flags."""

    rows = []
    for reaction in model.reactions:
        mass_balance_status = "skipped"
        mass_balance_issue_count = None
        if run_mass_balance_check and not getattr(reaction, "boundary", False):
            mass_balance_status, mass_balance_issue_count = check_reaction_mass_balance(reaction)
        rows.append(
            {
                "reaction_id": reaction.id,
                "name": getattr(reaction, "name", ""),
                "lower_bound": getattr(reaction, "lower_bound", None),
                "upper_bound": getattr(reaction, "upper_bound", None),
                "has_gpr": bool(str(getattr(reaction, "gene_reaction_rule", "")).strip()),
                "is_exchange": is_exchange_reaction(reaction),
                "is_boundary": bool(getattr(reaction, "boundary", False)),
                "blocked": reaction.id in blocked_ids,
                "mass_balance_status": mass_balance_status,
                "mass_balance_issue_count": mass_balance_issue_count,
            }
        )
    return rows


def check_reaction_mass_balance(reaction: Any) -> tuple[str, int | None]:
    """Return mass-balance status for a reaction."""

    try:
        imbalance = reaction.check_mass_balance()
    except Exception:
        return "unknown", None
    if imbalance:
        return "imbalanced", len(imbalance)
    return "balanced", 0


def build_objective_rows(model: Any) -> list[dict[str, object]]:
    """List objective reactions and coefficients."""

    rows = []
    for reaction in model.reactions:
        coefficient = getattr(reaction, "objective_coefficient", 0) or 0
        if coefficient == 0:
            continue
        rows.append(
            {
                "reaction_id": reaction.id,
                "name": getattr(reaction, "name", ""),
                "objective_coefficient": coefficient,
                "lower_bound": getattr(reaction, "lower_bound", None),
                "upper_bound": getattr(reaction, "upper_bound", None),
            }
        )
    return rows


def build_compartment_rows(model: Any) -> list[dict[str, object]]:
    """Summarize metabolites by compartment."""

    grouped: dict[str, dict[str, int]] = {}
    for metabolite in model.metabolites:
        compartment = getattr(metabolite, "compartment", "") or "unknown"
        row = grouped.setdefault(
            compartment,
            {
                "compartment": compartment,
                "metabolite_count": 0,
                "missing_formula_count": 0,
                "missing_charge_count": 0,
            },
        )
        row["metabolite_count"] += 1
        if not getattr(metabolite, "formula", None):
            row["missing_formula_count"] += 1
        if getattr(metabolite, "charge", None) is None:
            row["missing_charge_count"] += 1
    rows = []
    for row in sorted(grouped.values(), key=lambda value: value["compartment"]):
        total = row["metabolite_count"]
        rows.append(
            {
                **row,
                "missing_formula_fraction": _fraction(row["missing_formula_count"], total),
                "missing_charge_fraction": _fraction(row["missing_charge_count"], total),
            }
        )
    return rows


def build_model_qc_recommendations(summary: dict[str, object]) -> list[dict[str, str]]:
    """Create practical model QC recommendations."""

    recommendations = []
    if summary.get("baseline_fba_status") != "optimal":
        recommendations.append(
            {
                "severity": "high",
                "topic": "baseline_fba",
                "recommendation": "Baseline FBA is not optimal; fix objective/media feasibility before running omics-specific reconstruction.",
            }
        )
    if str(summary.get("blocked_check_status", "")).startswith("failed"):
        recommendations.append(
            {
                "severity": "low",
                "topic": "blocked_reactions",
                "recommendation": "Blocked-reaction check failed in the local solver environment; rerun QC with --skip-blocked-check or inspect solver logs.",
            }
        )
    if (_to_float(summary.get("gpr_reaction_fraction")) or 0.0) < 0.4:
        recommendations.append(
            {
                "severity": "medium",
                "topic": "gpr_coverage",
                "recommendation": "GPR coverage is limited, so gene-expression integration will leave many reactions without direct evidence.",
            }
        )
    if (_to_float(summary.get("blocked_reaction_fraction")) or 0.0) > 0.25:
        recommendations.append(
            {
                "severity": "medium",
                "topic": "blocked_reactions",
                "recommendation": "A large fraction of reactions are blocked under default bounds; interpret context extraction with media and exchange bounds in mind.",
            }
        )
    if (_to_float(summary.get("mass_imbalanced_reaction_fraction")) or 0.0) > 0.1:
        recommendations.append(
            {
                "severity": "medium",
                "topic": "mass_balance",
                "recommendation": "Many internal reactions are mass or charge imbalanced; thermodynamic or enzyme-constrained extensions may need curation first.",
            }
        )
    if (_to_float(summary.get("missing_formula_metabolite_fraction")) or 0.0) > 0.1:
        recommendations.append(
            {
                "severity": "low",
                "topic": "metabolite_annotation",
                "recommendation": "Some metabolites lack formulas, which limits mass-balance and thermodynamic diagnostics.",
            }
        )
    if not recommendations:
        recommendations.append(
            {
                "severity": "info",
                "topic": "model_structure",
                "recommendation": "Model structure is suitable for the next integration modules, with normal biological validation still required.",
            }
        )
    return recommendations


def classify_model_qc(summary: dict[str, object]) -> str:
    """Assign a compact model QC label."""

    if summary.get("baseline_fba_status") != "optimal":
        return "needs_repair"
    if str(summary.get("blocked_check_status", "")).startswith("failed"):
        return "usable_with_caution"
    blocked_fraction = _to_float(summary.get("blocked_reaction_fraction")) or 0.0
    gpr_fraction = _to_float(summary.get("gpr_reaction_fraction")) or 0.0
    imbalance_fraction = _to_float(summary.get("mass_imbalanced_reaction_fraction")) or 0.0
    if blocked_fraction > 0.4 or gpr_fraction < 0.25 or imbalance_fraction > 0.2:
        return "needs_review"
    if blocked_fraction > 0.25 or gpr_fraction < 0.4 or imbalance_fraction > 0.1:
        return "usable_with_caution"
    return "ready"


def is_exchange_reaction(reaction: Any) -> bool:
    """Return whether a reaction is an exchange reaction."""

    reaction_id = getattr(reaction, "id", "")
    if reaction_id.startswith("EX_") or reaction_id.startswith("R_EX_"):
        return True
    try:
        return bool(getattr(reaction, "boundary", False) and len(reaction.metabolites) == 1)
    except Exception:
        return False


def optimize_model(model: Any) -> tuple[str, float | None]:
    """Run baseline FBA and return status/objective."""

    try:
        solution = model.optimize()
        return str(getattr(solution, "status", "unknown")), _to_float(getattr(solution, "objective_value", None))
    except Exception as exc:
        return f"failed: {type(exc).__name__}: {exc}", None


def _fraction(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _to_float(value: object) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
