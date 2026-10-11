"""Reaction-level lookup for E-Flux and delta-FBA-lite outputs."""

from __future__ import annotations

from pathlib import Path

from .constraints import read_csv_records
from .reaction_drilldown import normalize_reaction_id


def build_transcriptomics_flux_drilldown(
    reaction_id: str,
    transcriptomics_flux_results_dir: str | Path,
    condition: str = "",
) -> dict[str, object]:
    """Return E-Flux bounds, fluxes, and delta-FBA-lite rows for one reaction."""

    query = str(reaction_id or "").strip()
    normalized = normalize_reaction_id(query)
    if not normalized:
        return {
            "query": query,
            "normalized_reaction_id": "",
            "eflux_bound_rows": [],
            "eflux_flux_rows": [],
            "delta_expression_rows": [],
            "delta_flux_rows": [],
            "measured_delta_rows": [],
            "condition_pairs": [],
        }

    condition_filter = str(condition or "").strip()
    if condition_filter.upper() == "ALL":
        condition_filter = ""

    root = Path(transcriptomics_flux_results_dir)
    eflux_bound_rows = _matching_rows(
        _read_optional(root / "eflux_reaction_bounds.csv"),
        normalized,
        condition_filter,
    )
    eflux_flux_rows = _matching_rows(
        _read_optional(root / "eflux_fluxes.csv"),
        normalized,
        condition_filter,
    )
    delta_expression_rows = _matching_rows(
        _read_optional(root / "delta_fba_expression_deltas.csv"),
        normalized,
        condition_filter,
    )
    delta_flux_rows = _matching_rows(
        _read_optional(root / "delta_fba_flux_deltas.csv"),
        normalized,
        condition_filter,
    )
    measured_delta_rows = _matching_rows(
        _read_optional(root / "delta_fba_measured_delta_comparison.csv"),
        normalized,
        condition_filter,
    )
    condition_pairs = sorted(
        {
            str(row.get("condition_pair") or "")
            for row in [*delta_expression_rows, *delta_flux_rows, *measured_delta_rows]
            if row.get("condition_pair")
        }
    )
    return {
        "query": query,
        "normalized_reaction_id": normalized,
        "eflux_bound_rows": eflux_bound_rows,
        "eflux_flux_rows": eflux_flux_rows,
        "delta_expression_rows": delta_expression_rows,
        "delta_flux_rows": delta_flux_rows,
        "measured_delta_rows": measured_delta_rows,
        "condition_pairs": condition_pairs,
    }


def _matching_rows(
    rows: list[dict[str, str]],
    normalized_reaction_id: str,
    condition: str = "",
) -> list[dict[str, str]]:
    matches = []
    for row in rows:
        if condition and not _condition_matches(row, condition):
            continue
        row_ids = {
            normalize_reaction_id(row.get("reaction_id", "")),
            normalize_reaction_id(row.get("cobra_reaction_id", "")),
            normalize_reaction_id(row.get("model_reaction_id", "")),
        }
        if normalized_reaction_id in row_ids:
            matches.append(row)
    return matches


def _condition_matches(row: dict[str, str], condition: str) -> bool:
    values = {
        str(row.get("condition") or ""),
        str(row.get("reference_condition") or ""),
        str(row.get("target_condition") or ""),
    }
    return condition in values


def _read_optional(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return read_csv_records(path)
