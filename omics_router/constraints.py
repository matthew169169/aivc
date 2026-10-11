"""Build executable-ish constraint tables from omics CSV files.

This module deliberately uses only the Python standard library. It can inspect
SBML/FBC identifiers and produce normalized tables before COBRApy, TROPPO,
GECKO, or pyTFA runners are installed.
"""

from __future__ import annotations

import csv
import json
import math
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


CORE_NS = "{http://www.sbml.org/sbml/level3/version1/core}"
FBC_NS = "{http://www.sbml.org/sbml/level3/version1/fbc/version2}"


@dataclass(slots=True)
class SbmlModelIndex:
    """Small identifier index extracted from an SBML/FBC model."""

    path: str
    model_id: str = ""
    objective_reactions: list[str] = field(default_factory=list)
    reactions: set[str] = field(default_factory=set)
    reaction_aliases: dict[str, str] = field(default_factory=dict)
    metabolites: set[str] = field(default_factory=set)
    metabolite_aliases: dict[str, str] = field(default_factory=dict)
    genes: set[str] = field(default_factory=set)
    gene_aliases: dict[str, str] = field(default_factory=dict)

    def summary(self) -> dict[str, object]:
        return {
            "path": self.path,
            "model_id": self.model_id,
            "reaction_count": len(self.reactions),
            "metabolite_count": len(self.metabolites),
            "gene_count": len(self.genes),
            "objective_reactions": self.objective_reactions,
        }

    def resolve_reaction(self, reaction_id: str) -> tuple[str, str]:
        return _resolve_id(reaction_id, self.reaction_aliases, _canonical_reaction)

    def resolve_metabolite(self, metabolite_id: str) -> tuple[str, str]:
        return _resolve_id(metabolite_id, self.metabolite_aliases, _canonical_metabolite)

    def resolve_gene(self, gene_id: str) -> tuple[str, str]:
        return _resolve_id(gene_id, self.gene_aliases, lambda value: value)


@dataclass(slots=True)
class ReactionGeneRule:
    """Parsed FBC gene-product association for a reaction."""

    reaction_id: str
    name: str = ""
    rule: Any = None
    rule_text: str = ""
    genes: list[str] = field(default_factory=list)


def parse_sbml_index(path: str | Path) -> SbmlModelIndex:
    """Extract identifiers from an SBML/FBC model using streaming XML parsing."""

    model_path = Path(path)
    index = SbmlModelIndex(path=str(model_path))

    for _event, elem in ET.iterparse(model_path, events=("start",)):
        tag = elem.tag
        if tag == f"{CORE_NS}model":
            index.model_id = elem.attrib.get("id", "")
        elif tag == f"{FBC_NS}fluxObjective":
            reaction = elem.attrib.get(f"{FBC_NS}reaction") or elem.attrib.get("reaction")
            if reaction:
                index.objective_reactions.append(reaction)
        elif tag == f"{CORE_NS}reaction":
            reaction_id = elem.attrib.get("id", "")
            if reaction_id:
                index.reactions.add(reaction_id)
                _add_reaction_aliases(index.reaction_aliases, reaction_id)
        elif tag == f"{CORE_NS}species":
            species_id = elem.attrib.get("id", "")
            if species_id:
                index.metabolites.add(species_id)
                _add_metabolite_aliases(index.metabolite_aliases, species_id)
        elif tag == f"{FBC_NS}geneProduct":
            gene_id = elem.attrib.get(f"{FBC_NS}id") or elem.attrib.get("id") or ""
            label = elem.attrib.get(f"{FBC_NS}label") or elem.attrib.get("label") or ""
            name = elem.attrib.get(f"{FBC_NS}name") or elem.attrib.get("name") or ""
            model_gene = gene_id or label or name
            if model_gene:
                index.genes.add(model_gene)
            for value in (gene_id, label, name):
                if value:
                    index.gene_aliases[_normalize_id(value)] = model_gene

    return index


def parse_sbml_gpr_rules(path: str | Path) -> dict[str, ReactionGeneRule]:
    """Parse reaction-level FBC gene-product associations from SBML."""

    tree = ET.parse(path)
    root = tree.getroot()
    rules: dict[str, ReactionGeneRule] = {}
    for reaction in root.findall(f".//{CORE_NS}reaction"):
        reaction_id = reaction.attrib.get("id", "")
        if not reaction_id:
            continue
        association = reaction.find(f"{FBC_NS}geneProductAssociation")
        rule = None
        if association is not None and len(association):
            rule = _parse_gpr_node(list(association)[0])
        elif association is not None:
            rule = _parse_gpr_node(association)
        genes = sorted(_collect_gpr_genes(rule))
        rules[reaction_id] = ReactionGeneRule(
            reaction_id=reaction_id,
            name=reaction.attrib.get("name", ""),
            rule=rule,
            rule_text=_gpr_to_text(rule),
            genes=genes,
        )
    return rules


def build_reaction_expression_evidence(
    gene_evidence_csv: str | Path,
    sbml_path: str | Path,
    low_threshold: float = 10.0,
    high_threshold: float = 100.0,
) -> list[dict[str, object]]:
    """Aggregate gene expression evidence to reaction-level GPR evidence."""

    gpr_rules = parse_sbml_gpr_rules(sbml_path)
    gene_rows = read_csv_records(gene_evidence_csv)
    values_by_condition: dict[str, dict[str, float]] = {}
    for row in gene_rows:
        condition = row.get("condition") or row.get("sample") or "default"
        model_gene = row.get("model_gene_id") or row.get("gene_id") or ""
        value = _to_float(row.get("value"))
        if not model_gene or value is None:
            continue
        values_by_condition.setdefault(condition, {})[model_gene] = value

    rows: list[dict[str, object]] = []
    for condition, gene_values in sorted(values_by_condition.items()):
        for reaction_id, rule in sorted(gpr_rules.items()):
            score, measured_genes = _evaluate_gpr(rule.rule, gene_values)
            gene_count = len(rule.genes)
            measured_gene_count = len(measured_genes)
            coverage = measured_gene_count / gene_count if gene_count else None
            evidence = _reaction_evidence(score, gene_count, measured_gene_count, low_threshold, high_threshold)
            rows.append(
                {
                    "condition": condition,
                    "reaction_id": reaction_id,
                    "cobra_reaction_id": reaction_id[2:] if reaction_id.startswith("R_") else reaction_id,
                    "reaction_name": rule.name,
                    "reaction_score": score,
                    "evidence": evidence,
                    "gene_count": gene_count,
                    "measured_gene_count": measured_gene_count,
                    "gene_coverage": coverage,
                    "imat_weight": _imat_weight(evidence),
                    "fastcore_core": evidence == "high",
                    "corda_confidence": _corda_confidence(evidence),
                    "gpr_rule": rule.rule_text,
                    "measured_genes": ";".join(sorted(measured_genes)),
                    "status": _reaction_status(gene_count, measured_gene_count),
                }
            )
    return rows


def build_relative_protein_evidence_table(
    proteomics_csv: str | Path,
    model_index: SbmlModelIndex | None = None,
    low_log2_threshold: float = -1.0,
    high_log2_threshold: float = 1.0,
) -> list[dict[str, object]]:
    """Normalize relative proteomics rows and classify protein evidence."""

    rows = []
    for row in read_csv_records(proteomics_csv):
        protein_id = row.get("protein_id", "")
        gene_id = row.get("gene_id") or protein_id
        model_gene, mapping_status = model_index.resolve_gene(gene_id) if model_index else (gene_id, "not_checked")
        raw_value = _to_float(row.get("log2_fold_change") or row.get("value"))
        unit = row.get("unit") or "log2_fold_change"
        log2_fold_change = normalize_relative_protein_value(raw_value, unit)
        status = classify_relative_protein_status(model_gene, mapping_status, raw_value, log2_fold_change, unit)
        evidence = classify_relative_evidence(log2_fold_change, low_log2_threshold, high_log2_threshold)
        rows.append(
            {
                "condition": row.get("condition") or row.get("sample", ""),
                "sample": row.get("sample", ""),
                "protein_id": protein_id,
                "gene_id": gene_id,
                "model_gene_id": model_gene,
                "value": raw_value,
                "unit": unit,
                "log2_fold_change": log2_fold_change,
                "reference_condition": row.get("reference_condition", ""),
                "evidence": evidence,
                "status": status,
                "note": row.get("note", ""),
            }
        )
    return rows


def build_reaction_protein_evidence(
    protein_evidence_csv: str | Path,
    sbml_path: str | Path,
    low_log2_threshold: float = -1.0,
    high_log2_threshold: float = 1.0,
) -> list[dict[str, object]]:
    """Aggregate relative protein evidence to reaction-level GPR evidence."""

    gpr_rules = parse_sbml_gpr_rules(sbml_path)
    protein_rows = read_csv_records(protein_evidence_csv)
    values_by_condition: dict[str, dict[str, float]] = {}
    for row in protein_rows:
        if row.get("status") not in {"mapped", "not_checked", "", None}:
            continue
        condition = row.get("condition") or row.get("sample") or "default"
        model_gene = row.get("model_gene_id") or row.get("gene_id") or ""
        value = _to_float(row.get("log2_fold_change") or row.get("value"))
        if not model_gene or value is None:
            continue
        values_by_condition.setdefault(condition, {})[model_gene] = value

    rows: list[dict[str, object]] = []
    for condition, protein_values in sorted(values_by_condition.items()):
        for reaction_id, rule in sorted(gpr_rules.items()):
            score, measured_genes = _evaluate_gpr(rule.rule, protein_values)
            gene_count = len(rule.genes)
            measured_gene_count = len(measured_genes)
            coverage = measured_gene_count / gene_count if gene_count else None
            evidence = _reaction_evidence(score, gene_count, measured_gene_count, low_log2_threshold, high_log2_threshold)
            rows.append(
                {
                    "condition": condition,
                    "reaction_id": reaction_id,
                    "cobra_reaction_id": reaction_id[2:] if reaction_id.startswith("R_") else reaction_id,
                    "reaction_name": rule.name,
                    "reaction_score": score,
                    "evidence": evidence,
                    "gene_count": gene_count,
                    "measured_gene_count": measured_gene_count,
                    "gene_coverage": coverage,
                    "imat_weight": _imat_weight(evidence),
                    "fastcore_core": evidence == "high",
                    "corda_confidence": _corda_confidence(evidence),
                    "gpr_rule": rule.rule_text,
                    "measured_genes": ";".join(sorted(measured_genes)),
                    "status": _reaction_status(gene_count, measured_gene_count),
                }
            )
    return rows


def split_context_method_inputs(reaction_evidence_rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
    """Create method-specific input tables from reaction evidence rows."""

    imat = []
    fastcore = []
    corda = []
    for row in reaction_evidence_rows:
        imat.append(
            {
                "condition": row["condition"],
                "reaction_id": row["reaction_id"],
                "cobra_reaction_id": row["cobra_reaction_id"],
                "reaction_score": row["reaction_score"],
                "evidence": row["evidence"],
                "imat_weight": row["imat_weight"],
                "status": row["evidence"],
            }
        )
        if _truthy(row.get("fastcore_core")):
            fastcore.append(
                {
                    "condition": row["condition"],
                    "reaction_id": row["reaction_id"],
                    "cobra_reaction_id": row["cobra_reaction_id"],
                    "reaction_score": row["reaction_score"],
                    "status": "core",
                }
            )
        corda.append(
            {
                "condition": row["condition"],
                "reaction_id": row["reaction_id"],
                "cobra_reaction_id": row["cobra_reaction_id"],
                "confidence": row["corda_confidence"],
                "reaction_score": row["reaction_score"],
                "evidence": row["evidence"],
                "status": row["corda_confidence"],
            }
        )
    return {
        "imat_reaction_weights": imat,
        "fastcore_core_reactions": fastcore,
        "corda_reaction_confidence": corda,
    }


def build_exchange_bounds(
    extracellular_csv: str | Path,
    model_index: SbmlModelIndex | None = None,
    relative_tolerance: float = 0.10,
    zero_tolerance: float = 1e-6,
) -> list[dict[str, object]]:
    """Convert extracellular flux/metabolomics rows into exchange-bound rows."""

    rows = []
    for row in read_csv_records(extracellular_csv):
        metabolite_id = row.get("metabolite_id", "")
        measured = _to_float(row.get("value"))
        proposed_reaction = f"EX_{metabolite_id}" if metabolite_id else ""
        model_reaction_id, status = _resolve_exchange_reaction(proposed_reaction, model_index)
        lower, upper = _measurement_bounds(measured, relative_tolerance, zero_tolerance)
        rows.append(
            {
                "condition": row.get("condition") or row.get("sample", ""),
                "sample": row.get("sample", ""),
                "metabolite_id": metabolite_id,
                "proposed_reaction_id": proposed_reaction,
                "model_reaction_id": model_reaction_id,
                "measured_flux": measured,
                "unit": row.get("unit", ""),
                "lower_bound": lower,
                "upper_bound": upper,
                "status": status,
                "note": row.get("note", ""),
            }
        )
    return rows


def build_flux_validation_targets(
    fluxomics_csv: str | Path,
    model_index: SbmlModelIndex | None = None,
) -> list[dict[str, object]]:
    """Normalize measured fluxes and map them to model reaction ids."""

    rows = []
    for row in read_csv_records(fluxomics_csv):
        raw_reaction = row.get("reaction_id", "")
        model_reaction, status = (
            model_index.resolve_reaction(raw_reaction) if model_index else (_canonical_reaction(raw_reaction), "not_checked")
        )
        rows.append(
            {
                "condition": row.get("condition") or row.get("sample", ""),
                "sample": row.get("sample", ""),
                "reaction_id": raw_reaction,
                "model_reaction_id": model_reaction,
                "measured_flux": _to_float(row.get("flux")),
                "lower_ci": _to_float(row.get("lower_ci")),
                "upper_ci": _to_float(row.get("upper_ci")),
                "unit": row.get("unit", ""),
                "status": status,
                "note": row.get("note", ""),
            }
        )
    return rows


def build_kcat_prior_table(
    priors_csv: str | Path,
    model_index: SbmlModelIndex | None = None,
) -> list[dict[str, object]]:
    """Normalize kcat priors and map reaction targets to model reactions."""

    rows = []
    for row in read_csv_records(priors_csv):
        target_id = row.get("target_id", "")
        target_type = row.get("target_type", "")
        if target_type == "reaction" and model_index:
            model_target_id, status = model_index.resolve_reaction(target_id)
        elif target_type == "reaction":
            model_target_id, status = _canonical_reaction(target_id), "not_checked"
        else:
            model_target_id, status = target_id, "not_reaction"
        rows.append(
            {
                "target_id": target_id,
                "target_type": target_type,
                "model_target_id": model_target_id,
                "kcat": _to_float(row.get("value")),
                "unit": row.get("unit", ""),
                "confidence": _to_float(row.get("confidence")),
                "source_tier": row.get("source_tier", ""),
                "status": status,
                "note": row.get("note", ""),
            }
        )
    return rows


def build_gene_evidence_table(
    transcriptomics_csv: str | Path,
    model_index: SbmlModelIndex | None = None,
    low_threshold: float = 10.0,
    high_threshold: float = 100.0,
) -> list[dict[str, object]]:
    """Classify gene expression evidence for context-specific workflows."""

    rows = []
    for row in read_csv_records(transcriptomics_csv):
        gene_id = row.get("gene_id", "")
        model_gene, status = model_index.resolve_gene(gene_id) if model_index else (gene_id, "not_checked")
        value = _to_float(row.get("value"))
        if value is None:
            evidence = "missing"
            if status in {"mapped", "not_checked"}:
                status = "missing_value"
        elif value >= high_threshold:
            evidence = "high"
        elif value <= low_threshold:
            evidence = "low"
        else:
            evidence = "medium"
        rows.append(
            {
                "condition": row.get("condition") or row.get("sample", ""),
                "sample": row.get("sample", ""),
                "gene_id": gene_id,
                "model_gene_id": model_gene,
                "value": value,
                "unit": row.get("unit", ""),
                "evidence": evidence,
                "status": status,
                "note": row.get("note", ""),
            }
        )
    return rows


def build_protein_abundance_table(
    proteomics_csv: str | Path,
    model_index: SbmlModelIndex | None = None,
) -> list[dict[str, object]]:
    """Normalize absolute proteomics rows and map protein ids to model genes."""

    rows = []
    for row in read_csv_records(proteomics_csv):
        protein_id = row.get("protein_id", "")
        model_gene, status = model_index.resolve_gene(row.get("gene_id") or protein_id) if model_index else (protein_id, "not_checked")
        rows.append(
            {
                "condition": row.get("condition") or row.get("sample", ""),
                "sample": row.get("sample", ""),
                "protein_id": protein_id,
                "gene_id": row.get("gene_id") or protein_id,
                "model_gene_id": model_gene,
                "abundance": _to_float(row.get("value")),
                "unit": row.get("unit", ""),
                "status": status,
                "note": row.get("note", ""),
            }
        )
    return rows


def build_intracellular_concentration_table(
    metabolomics_csv: str | Path,
    model_index: SbmlModelIndex | None = None,
) -> list[dict[str, object]]:
    """Normalize intracellular metabolite concentrations for TFA/pyTFA setup."""

    rows = []
    for row in read_csv_records(metabolomics_csv):
        metabolite_id = row.get("metabolite_id", "")
        model_metabolite, status = model_index.resolve_metabolite(metabolite_id) if model_index else (_canonical_metabolite(metabolite_id), "not_checked")
        rows.append(
            {
                "condition": row.get("condition") or row.get("sample", ""),
                "sample": row.get("sample", ""),
                "metabolite_id": metabolite_id,
                "model_metabolite_id": model_metabolite,
                "compartment": row.get("compartment", ""),
                "concentration": _to_float(row.get("value")),
                "lower_bound": _to_float(row.get("lower_bound")),
                "upper_bound": _to_float(row.get("upper_bound")),
                "unit": row.get("unit", ""),
                "status": status,
                "note": row.get("note", ""),
            }
        )
    return rows


def _parse_gpr_node(node: ET.Element) -> Any:
    tag = node.tag
    if tag == f"{FBC_NS}geneProductRef":
        return ("gene", node.attrib.get(f"{FBC_NS}geneProduct") or node.attrib.get("geneProduct") or "")
    if tag == f"{FBC_NS}and":
        return ("and", [_parse_gpr_node(child) for child in list(node)])
    if tag == f"{FBC_NS}or":
        return ("or", [_parse_gpr_node(child) for child in list(node)])
    if tag == f"{FBC_NS}geneProductAssociation" and len(node):
        return _parse_gpr_node(list(node)[0])
    return None


def _collect_gpr_genes(rule: Any) -> set[str]:
    if rule is None:
        return set()
    kind = rule[0]
    if kind == "gene":
        return {rule[1]} if rule[1] else set()
    genes: set[str] = set()
    for child in rule[1]:
        genes.update(_collect_gpr_genes(child))
    return genes


def _gpr_to_text(rule: Any) -> str:
    if rule is None:
        return ""
    kind = rule[0]
    if kind == "gene":
        return rule[1]
    joiner = f" {kind.upper()} "
    return "(" + joiner.join(_gpr_to_text(child) for child in rule[1]) + ")"


def _evaluate_gpr(rule: Any, gene_values: dict[str, float]) -> tuple[float | None, set[str]]:
    if rule is None:
        return None, set()
    kind = rule[0]
    if kind == "gene":
        gene_id = rule[1]
        if gene_id in gene_values:
            return gene_values[gene_id], {gene_id}
        return None, set()

    values: list[float] = []
    measured: set[str] = set()
    for child in rule[1]:
        value, child_measured = _evaluate_gpr(child, gene_values)
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


def _reaction_evidence(
    score: float | None,
    gene_count: int,
    measured_gene_count: int,
    low_threshold: float,
    high_threshold: float,
) -> str:
    if gene_count == 0:
        return "no_gpr"
    if measured_gene_count == 0 or score is None:
        return "unknown"
    if score >= high_threshold:
        return "high"
    if score <= low_threshold:
        return "low"
    return "medium"


def _reaction_status(gene_count: int, measured_gene_count: int) -> str:
    if gene_count == 0:
        return "no_gpr"
    if measured_gene_count == 0:
        return "no_measured_gene"
    if measured_gene_count < gene_count:
        return "partial_gene_coverage"
    return "complete_gene_coverage"


def _imat_weight(evidence: str) -> int:
    if evidence == "high":
        return 1
    if evidence == "low":
        return -1
    return 0


def _corda_confidence(evidence: str) -> str:
    return {
        "high": "high",
        "medium": "medium",
        "low": "negative",
        "unknown": "unknown",
        "no_gpr": "unknown",
    }.get(evidence, "unknown")


def normalize_relative_protein_value(value: float | None, unit: str) -> float | None:
    """Normalize relative proteomics values to log2 fold-change."""

    if value is None:
        return None
    normalized_unit = unit.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized_unit in {"", "log2", "log2fc", "log2_fc", "log2_fold_change"}:
        return value
    if normalized_unit in {"fold_change", "foldchange", "ratio", "fc"}:
        if value <= 0:
            return None
        return math.log2(value)
    return None


def classify_relative_protein_status(
    model_gene_id: str,
    mapping_status: str,
    raw_value: float | None,
    log2_fold_change: float | None,
    unit: str,
) -> str:
    """Classify whether a relative proteomics row is usable."""

    if not model_gene_id:
        return "missing_gene"
    if mapping_status not in {"mapped", "not_checked", "", None}:
        return mapping_status
    if raw_value is None:
        return "missing_value"
    if log2_fold_change is None:
        return "unsupported_unit_or_value"
    return mapping_status or "mapped"


def classify_relative_evidence(
    log2_fold_change: float | None,
    low_log2_threshold: float = -1.0,
    high_log2_threshold: float = 1.0,
) -> str:
    """Classify relative protein change as high/medium/low evidence."""

    if log2_fold_change is None:
        return "unknown"
    if log2_fold_change >= high_log2_threshold:
        return "high"
    if log2_fold_change <= low_log2_threshold:
        return "low"
    return "medium"


def build_manifest(tables: dict[str, list[dict[str, object]]]) -> dict[str, object]:
    """Summarize generated constraint tables."""

    manifest: dict[str, object] = {}
    for name, rows in tables.items():
        status_counts: dict[str, int] = {}
        for row in rows:
            status = str(row.get("status", "unknown"))
            status_counts[status] = status_counts.get(status, 0) + 1
        manifest[name] = {
            "row_count": len(rows),
            "status_counts": status_counts,
        }
    return manifest


def read_csv_records(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    delimiter = "\t" if source.suffix.lower() in {".tsv", ".txt"} else ","
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def write_csv(path: str | Path, rows: list[dict[str, object]]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        output.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: str | Path, data: object) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def model_index_to_jsonable(index: SbmlModelIndex) -> dict[str, object]:
    data = asdict(index)
    data["reactions"] = sorted(index.reactions)
    data["metabolites"] = sorted(index.metabolites)
    data["genes"] = sorted(index.genes)
    return data


def _resolve_exchange_reaction(proposed_reaction: str, model_index: SbmlModelIndex | None) -> tuple[str, str]:
    if not proposed_reaction:
        return "", "missing_metabolite"
    if model_index is None:
        return _canonical_reaction(proposed_reaction), "not_checked"
    return model_index.resolve_reaction(proposed_reaction)


def _measurement_bounds(value: float | None, relative_tolerance: float, zero_tolerance: float) -> tuple[float | None, float | None]:
    if value is None:
        return None, None
    if abs(value) <= zero_tolerance:
        return -zero_tolerance, zero_tolerance
    delta = abs(value) * relative_tolerance
    return round(value - delta, 12), round(value + delta, 12)


def _resolve_id(raw_id: str, aliases: dict[str, str], canonical) -> tuple[str, str]:
    normalized = _normalize_id(raw_id)
    if normalized in aliases:
        return aliases[normalized], "mapped"
    return canonical(raw_id), "not_found"


def _add_reaction_aliases(aliases: dict[str, str], reaction_id: str) -> None:
    candidates = {reaction_id}
    if reaction_id.startswith("R_"):
        candidates.add(reaction_id[2:])
    else:
        candidates.add(f"R_{reaction_id}")
    for candidate in list(candidates):
        if candidate.startswith("R_EX_"):
            candidates.add(candidate[2:])
        if candidate.startswith("EX_"):
            candidates.add(f"R_{candidate}")
    for candidate in candidates:
        aliases[_normalize_id(candidate)] = reaction_id


def _add_metabolite_aliases(aliases: dict[str, str], species_id: str) -> None:
    candidates = {species_id}
    if species_id.startswith("M_"):
        candidates.add(species_id[2:])
    else:
        candidates.add(f"M_{species_id}")
    for candidate in candidates:
        aliases[_normalize_id(candidate)] = species_id


def _canonical_reaction(reaction_id: str) -> str:
    if not reaction_id:
        return ""
    return reaction_id if reaction_id.startswith("R_") else f"R_{reaction_id}"


def _canonical_metabolite(metabolite_id: str) -> str:
    if not metabolite_id:
        return ""
    return metabolite_id if metabolite_id.startswith("M_") else f"M_{metabolite_id}"


def _normalize_id(value: str) -> str:
    return value.strip().lower()


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}
