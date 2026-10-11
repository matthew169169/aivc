"""Prepare enzyme-capacity inputs for GECKO/sMOMENT-style workflows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cobra_runner import group_by_condition
from .constraints import parse_sbml_gpr_rules, read_csv_records, write_csv, write_json


SECONDS_PER_HOUR = 3600.0


@dataclass(slots=True)
class EnzymeWorkflowResult:
    """Summary returned by the enzyme-constraint preparation workflow."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]


def run_enzyme_constraint_workflow(
    model_path: str | Path,
    protein_abundance_path: str | Path,
    kcat_priors_path: str | Path,
    output_dir: str | Path,
    predicted_fluxes_path: str | Path | None = None,
) -> EnzymeWorkflowResult:
    """Build enzyme-capacity tables and QC recommendations."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "capacities": str(output / "reaction_enzyme_capacity.csv"),
        "flux_capacity_check": str(output / "enzyme_flux_capacity_check.csv"),
        "summary": str(output / "enzyme_qc_summary.csv"),
        "recommendations": str(output / "enzyme_qc_recommendations.csv"),
        "manifest": str(output / "enzyme_constraint_manifest.json"),
    }

    protein_rows = read_csv_records(protein_abundance_path)
    kcat_rows = read_csv_records(kcat_priors_path)
    gpr_rules = parse_sbml_gpr_rules(model_path)
    capacities = build_reaction_enzyme_capacities(protein_rows, kcat_rows, gpr_rules)
    flux_checks = build_flux_capacity_checks(capacities, _read_optional(predicted_fluxes_path))
    summary_rows = summarize_enzyme_constraints(protein_rows, kcat_rows, capacities, flux_checks)
    recommendation_rows = build_enzyme_recommendations(summary_rows)

    write_csv(files["capacities"], capacities)
    write_csv(files["flux_capacity_check"], flux_checks)
    write_csv(files["summary"], summary_rows)
    write_csv(files["recommendations"], recommendation_rows)
    write_json(
        files["manifest"],
        {
            "status": "completed",
            "model_path": str(model_path),
            "protein_abundance_path": str(protein_abundance_path),
            "kcat_priors_path": str(kcat_priors_path),
            "predicted_fluxes_path": str(predicted_fluxes_path) if predicted_fluxes_path else "",
            "files": files,
        },
    )
    return EnzymeWorkflowResult(
        status="completed",
        output_dir=str(output),
        message=f"Built enzyme-capacity inputs for {len(summary_rows)} conditions.",
        files=files,
    )


def build_reaction_enzyme_capacities(
    protein_rows: list[dict[str, str]],
    kcat_rows: list[dict[str, str]],
    gpr_rules: dict[str, Any],
) -> list[dict[str, object]]:
    """Combine condition-wise protein abundance with reaction-level kcat priors."""

    proteins_by_condition = build_protein_abundance_maps(protein_rows)
    rows = []
    for condition, proteins in sorted(proteins_by_condition.items()):
        for kcat_row in kcat_rows:
            reaction_id = kcat_row.get("model_target_id") or kcat_row.get("target_id") or ""
            if not reaction_id:
                continue
            rule = gpr_rules.get(reaction_id) or gpr_rules.get(sbml_reaction_id(reaction_id))
            kcat = _to_float(kcat_row.get("kcat") or kcat_row.get("value"))
            unit = kcat_row.get("unit", "")
            abundance, measured_genes = evaluate_gpr_abundance(getattr(rule, "rule", None), proteins)
            gene_count = len(getattr(rule, "genes", [])) if rule else 0
            measured_gene_count = len(measured_genes)
            protein_coverage = measured_gene_count / gene_count if gene_count else None
            capacity = calculate_capacity(abundance, kcat, unit)
            status = classify_capacity_status(rule, abundance, kcat, unit, gene_count, measured_gene_count)
            rows.append(
                {
                    "condition": condition,
                    "reaction_id": sbml_reaction_id(reaction_id),
                    "cobra_reaction_id": cobra_reaction_id(reaction_id),
                    "target_id": kcat_row.get("target_id", ""),
                    "kcat_per_s": kcat if _is_per_second_unit(unit) else None,
                    "kcat_unit": unit,
                    "kcat_confidence": _to_float(kcat_row.get("confidence")),
                    "source_tier": kcat_row.get("source_tier", ""),
                    "kcat_evidence_tier": kcat_row.get("kcat_evidence_tier", ""),
                    "gene_count": gene_count,
                    "measured_gene_count": measured_gene_count,
                    "protein_coverage": protein_coverage,
                    "limiting_abundance_mmol_per_gDW": abundance,
                    "enzyme_capacity_mmol_per_gDW_per_h": capacity,
                    "gpr_rule": getattr(rule, "rule_text", "") if rule else "",
                    "measured_genes": ";".join(sorted(measured_genes)),
                    "status": status,
                    "note": kcat_row.get("note", ""),
                }
            )
    return rows


def build_protein_abundance_maps(rows: list[dict[str, str]]) -> dict[str, dict[str, float]]:
    """Return condition -> model gene -> abundance."""

    grouped: dict[str, dict[str, float]] = {}
    for row in rows:
        if row.get("status") not in {"mapped", "", None}:
            continue
        value = _to_float(row.get("abundance") or row.get("value"))
        if value is None:
            continue
        gene_id = row.get("model_gene_id") or row.get("gene_id") or row.get("protein_id") or ""
        if not gene_id:
            continue
        condition = row.get("condition") or row.get("sample") or "default"
        grouped.setdefault(condition, {})[gene_id] = value
    return grouped


def evaluate_gpr_abundance(rule: Any, protein_values: dict[str, float]) -> tuple[float | None, set[str]]:
    """Evaluate GPR abundance with AND=min and OR=max semantics."""

    if rule is None:
        return None, set()
    kind = rule[0]
    if kind == "gene":
        gene_id = rule[1]
        if gene_id in protein_values:
            return protein_values[gene_id], {gene_id}
        return None, set()

    values = []
    measured: set[str] = set()
    for child in rule[1]:
        value, child_measured = evaluate_gpr_abundance(child, protein_values)
        measured.update(child_measured)
        if value is not None:
            values.append(value)
    if not values:
        return None, measured
    if kind == "and":
        return min(values), measured
    if kind == "or":
        return max(values), measured
    return None, measured


def calculate_capacity(abundance_mmol_per_gdw: float | None, kcat: float | None, unit: str) -> float | None:
    """Calculate mmol/gDW/h capacity from mmol/gDW abundance and kcat."""

    if abundance_mmol_per_gdw is None or kcat is None or not _is_per_second_unit(unit):
        return None
    return abundance_mmol_per_gdw * kcat * SECONDS_PER_HOUR


def build_flux_capacity_checks(
    capacity_rows: list[dict[str, object]],
    flux_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    """Compare predicted flux demand with enzyme capacity when fluxes are available."""

    flux_lookup = {}
    for row in flux_rows:
        condition = row.get("condition") or "default"
        reaction_id = row.get("reaction_id", "")
        flux = _to_float(row.get("predicted_flux"))
        if not reaction_id or flux is None:
            continue
        flux_lookup[(condition, reaction_id)] = flux
        flux_lookup[(condition, sbml_reaction_id(reaction_id))] = flux
        flux_lookup[(condition, cobra_reaction_id(reaction_id))] = flux

    rows = []
    for capacity in capacity_rows:
        condition = str(capacity.get("condition", "default"))
        reaction_id = str(capacity.get("cobra_reaction_id", ""))
        predicted_flux = flux_lookup.get((condition, reaction_id))
        enzyme_capacity = _to_float(capacity.get("enzyme_capacity_mmol_per_gDW_per_h"))
        usage_fraction = None
        status = "no_flux"
        if predicted_flux is not None and enzyme_capacity is not None and enzyme_capacity > 0:
            usage_fraction = abs(predicted_flux) / enzyme_capacity
            status = "within_capacity" if usage_fraction <= 1.0 else "exceeds_capacity"
        elif enzyme_capacity is None:
            status = "no_capacity"
        rows.append(
            {
                "condition": condition,
                "reaction_id": capacity.get("reaction_id", ""),
                "cobra_reaction_id": reaction_id,
                "predicted_flux": predicted_flux,
                "enzyme_capacity_mmol_per_gDW_per_h": enzyme_capacity,
                "usage_fraction": usage_fraction,
                "status": status,
            }
        )
    return rows


def summarize_enzyme_constraints(
    protein_rows: list[dict[str, str]],
    kcat_rows: list[dict[str, str]],
    capacity_rows: list[dict[str, object]],
    flux_checks: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Summarize enzyme-capacity readiness by condition."""

    protein_by_condition = group_by_condition(protein_rows)
    capacity_by_condition = group_by_condition([{k: str(v) if v is not None else "" for k, v in row.items()} for row in capacity_rows])
    flux_by_condition = group_by_condition([{k: str(v) if v is not None else "" for k, v in row.items()} for row in flux_checks])
    conditions = sorted(set(protein_by_condition) | set(capacity_by_condition))
    summary = []
    mapped_kcats = [row for row in kcat_rows if row.get("status") in {"mapped", "", None}]
    confidences = [_to_float(row.get("confidence")) for row in mapped_kcats]
    confidences = [value for value in confidences if value is not None]
    for condition in conditions:
        proteins = protein_by_condition.get(condition, [])
        capacities = capacity_by_condition.get(condition, [])
        checks = flux_by_condition.get(condition, [])
        mapped_proteins = [row for row in proteins if row.get("status") == "mapped"]
        ready = [row for row in capacities if row.get("status") == "ready"]
        exceeds_capacity = [row for row in checks if row.get("status") == "exceeds_capacity"]
        summary.append(
            {
                "condition": condition,
                "protein_count": len(proteins),
                "mapped_protein_count": len(mapped_proteins),
                "mapped_protein_fraction": _fraction(len(mapped_proteins), len(proteins)),
                "kcat_prior_count": len(kcat_rows),
                "mapped_kcat_prior_count": len(mapped_kcats),
                "mapped_kcat_prior_fraction": _fraction(len(mapped_kcats), len(kcat_rows)),
                "capacity_reaction_count": len(capacities),
                "ready_capacity_count": len(ready),
                "ready_capacity_fraction": _fraction(len(ready), len(capacities)),
                "mean_kcat_confidence": sum(confidences) / len(confidences) if confidences else None,
                "exceeds_capacity_count": len(exceeds_capacity),
                "enzyme_readiness": classify_enzyme_readiness(len(ready), len(capacities), len(proteins), len(kcat_rows)),
            }
        )
    return summary


def build_enzyme_recommendations(summary_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Create recommendations for enzyme-constrained workflows."""

    rows = []
    for summary in summary_rows:
        condition = summary["condition"]
        readiness = summary.get("enzyme_readiness")
        if readiness in {"insufficient", "guidance_only"}:
            rows.append(
                {
                    "condition": condition,
                    "severity": "high" if readiness == "insufficient" else "medium",
                    "topic": "coverage",
                    "recommendation": "Treat enzyme constraints as guidance; add broader absolute proteomics and curated kcat values before building a production ecGEM.",
                }
            )
        if (_to_float(summary.get("ready_capacity_fraction")) or 0.0) < 0.5:
            rows.append(
                {
                    "condition": condition,
                    "severity": "medium",
                    "topic": "reaction_capacity",
                    "recommendation": "Few kcat priors have matching measured proteins through GPRs, so many reactions cannot receive direct enzyme bounds.",
                }
            )
        if (_to_float(summary.get("mean_kcat_confidence")) or 0.0) < 0.7:
            rows.append(
                {
                    "condition": condition,
                    "severity": "low",
                    "topic": "kcat_confidence",
                    "recommendation": "Mean kcat confidence is modest; keep source tiers and confidence scores visible in downstream GECKO/sMOMENT runs.",
                }
            )
        if int(summary.get("exceeds_capacity_count") or 0) > 0:
            rows.append(
                {
                    "condition": condition,
                    "severity": "medium",
                    "topic": "flux_capacity",
                    "recommendation": "Some predicted fluxes exceed enzyme capacity priors; inspect units, kcat directionality, and isoenzyme assumptions.",
                }
            )
        if not any(row["condition"] == condition for row in rows):
            rows.append(
                {
                    "condition": condition,
                    "severity": "info",
                    "topic": "enzyme_constraints",
                    "recommendation": "Enzyme-capacity inputs are ready for a lightweight ecGEM prototype.",
                }
            )
    return rows


def classify_enzyme_readiness(
    ready_count: int,
    capacity_count: int,
    protein_count: int,
    kcat_count: int,
) -> str:
    """Classify enzyme-constraint readiness."""

    if protein_count == 0 or kcat_count == 0 or capacity_count == 0:
        return "insufficient"
    ready_fraction = _fraction(ready_count, capacity_count) or 0.0
    if ready_count < 5 or ready_fraction < 0.25:
        return "guidance_only"
    if ready_fraction < 0.6:
        return "prototype"
    return "ready"


def sbml_reaction_id(reaction_id: str) -> str:
    if not reaction_id:
        return ""
    return reaction_id if reaction_id.startswith("R_") else f"R_{reaction_id}"


def cobra_reaction_id(reaction_id: str) -> str:
    if not reaction_id:
        return ""
    return reaction_id[2:] if reaction_id.startswith("R_") else reaction_id


def classify_capacity_status(
    rule: Any,
    abundance: float | None,
    kcat: float | None,
    unit: str,
    gene_count: int = 0,
    measured_gene_count: int = 0,
) -> str:
    if rule is None:
        return "missing_gpr"
    if not _is_per_second_unit(unit):
        return "unsupported_kcat_unit"
    if kcat is None:
        return "missing_kcat"
    if abundance is None:
        return "no_measured_protein"
    if gene_count > 0 and measured_gene_count < gene_count:
        return "partial_protein_coverage"
    return "ready"


def _is_per_second_unit(unit: str) -> bool:
    normalized = str(unit or "").strip().lower().replace(" ", "")
    return normalized in {"per_s", "1/s", "s^-1", "s-1", "sec^-1", "sec-1", "persecond"}


def _read_optional(path: str | Path | None) -> list[dict[str, str]]:
    if path is None:
        return []
    table = Path(path)
    if not table.exists() or table.stat().st_size == 0:
        return []
    return read_csv_records(table)


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
