"""Prepare DLKcat kcat-prediction inputs and import predicted kcat values."""

from __future__ import annotations

import csv
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constraints import read_package_input_map
from .constraints import CORE_NS, parse_sbml_gpr_rules, parse_sbml_index, read_csv_records, write_csv, write_json


DLKCAT_SCHEMA_VERSION = "0.1.0"
DLKCAT_PREDICTION_IMPORT = "dlkcat_prediction_import.csv"


@dataclass(slots=True)
class DLKcatBridgeResult:
    """Summary returned by the DLKcat bridge workflow."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]


def run_dlkcat_bridge(
    model_path: str | Path,
    package_dir: str | Path,
    output_dir: str | Path,
) -> DLKcatBridgeResult:
    """Create DLKcat input rows and normalize optional prediction outputs.

    This v1 bridge is deliberately offline. It does not call DLKcat itself; it
    prepares reproducible input rows and folds user-imported predictions back
    into reaction-level kcat-prior tables for GECKO/enzyme workflows.
    """

    package = Path(package_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "input": str(output / "dlkcat_input.tsv"),
        "input_coverage": str(output / "dlkcat_input_coverage.csv"),
        "prediction_import_template": str(output / "dlkcat_prediction_import_template.csv"),
        "prediction_import": str(output / DLKCAT_PREDICTION_IMPORT),
        "prediction_normalized": str(output / "dlkcat_prediction_normalized.csv"),
        "reaction_kcat_priors": str(output / "dlkcat_reaction_kcat_priors.csv"),
        "summary": str(output / "dlkcat_bridge_summary.csv"),
        "manifest": str(output / "dlkcat_bridge_manifest.json"),
    }

    model_index = parse_sbml_index(model_path)
    reactions = parse_sbml_reactants(model_path)
    gpr_rules = parse_sbml_gpr_rules(model_path)
    annotations = collect_dlkcat_annotations(package, model_index)

    input_rows = build_dlkcat_input_rows(reactions, gpr_rules, annotations)
    coverage_rows = build_input_coverage_rows(input_rows)
    import_rows = read_csv_records(files["prediction_import"]) if Path(files["prediction_import"]).exists() else []
    normalized_predictions = normalize_dlkcat_predictions(import_rows, input_rows, model_index)
    kcat_priors = build_reaction_kcat_prior_rows(normalized_predictions)
    summary_rows = summarize_dlkcat_bridge(input_rows, coverage_rows, import_rows, normalized_predictions, kcat_priors)

    write_tsv(files["input"], input_rows)
    write_csv(files["input_coverage"], coverage_rows)
    write_csv(files["prediction_import_template"], dlkcat_output_template_rows())
    write_csv(files["prediction_normalized"], normalized_predictions)
    write_csv(files["reaction_kcat_priors"], kcat_priors)
    write_csv(files["summary"], summary_rows)
    write_json(
        files["manifest"],
        {
            "schema_version": DLKCAT_SCHEMA_VERSION,
            "status": "completed",
            "model_path": str(model_path),
            "package_dir": str(package),
            "annotation_sources": annotations["sources"],
            "files": files,
            "summary": summary_rows[0] if summary_rows else {},
        },
    )
    message = build_dlkcat_message(summary_rows[0] if summary_rows else {})
    return DLKcatBridgeResult(status="completed", output_dir=str(output), message=message, files=files)


def dlkcat_output_template_columns() -> list[str]:
    """Return accepted columns for user-imported DLKcat prediction tables."""

    return [
        "query_id",
        "reaction_id",
        "gene_id",
        "substrate_id",
        "substrate_name",
        "substrate_smiles",
        "predicted_kcat",
        "unit",
        "confidence",
        "dlkcat_status",
        "note",
    ]


def dlkcat_output_template_rows() -> list[dict[str, object]]:
    """Return a one-row template for Streamlit download."""

    return [
        {
            "query_id": "R_PFK__b3916__M_f6p_c",
            "reaction_id": "R_PFK",
            "gene_id": "b3916",
            "substrate_id": "M_f6p_c",
            "substrate_name": "D-fructose 6-phosphate",
            "substrate_smiles": "C(C(C(C(C(C=O)O)O)O)O)OP(=O)(O)O",
            "predicted_kcat": "42.0",
            "unit": "per_s",
            "confidence": "0.5",
            "dlkcat_status": "predicted",
            "note": "Example row; replace with DLKcat output.",
        }
    ]


def write_dlkcat_prediction_import_to_package(package_dir: str | Path, rows: list[dict[str, object]]) -> Path:
    """Save user-imported DLKcat predictions into the package-local bridge dir."""

    output = Path(package_dir) / "dlkcat_results"
    output.mkdir(parents=True, exist_ok=True)
    path = output / DLKCAT_PREDICTION_IMPORT
    normalized = [{column: row.get(column, "") for column in dlkcat_output_template_columns()} for row in rows]
    write_csv(path, normalized)
    return path


def parse_sbml_reactants(path: str | Path) -> list[dict[str, object]]:
    """Extract reaction reactants and metabolite names from an SBML model."""

    tree = ET.parse(path)
    root = tree.getroot()
    metabolite_names = {
        species.attrib.get("id", ""): species.attrib.get("name", "")
        for species in root.findall(f".//{CORE_NS}species")
        if species.attrib.get("id")
    }
    reactions: list[dict[str, object]] = []
    for reaction in root.findall(f".//{CORE_NS}reaction"):
        reaction_id = reaction.attrib.get("id", "")
        if not reaction_id:
            continue
        reactants = []
        for reference in reaction.findall(f"./{CORE_NS}listOfReactants/{CORE_NS}speciesReference"):
            species_id = reference.attrib.get("species", "")
            if species_id:
                reactants.append(
                    {
                        "substrate_id": species_id,
                        "substrate_name": metabolite_names.get(species_id, ""),
                    }
                )
        reactions.append(
            {
                "reaction_id": reaction_id,
                "cobra_reaction_id": cobra_reaction_id(reaction_id),
                "reaction_name": reaction.attrib.get("name", ""),
                "reactants": reactants,
            }
        )
    return reactions


def collect_dlkcat_annotations(package_dir: Path, model_index: Any) -> dict[str, Any]:
    """Collect sequence, EC, UniProt, and SMILES hints from package-local tables."""

    annotations: dict[str, Any] = {
        "genes": {},
        "substrates": {},
        "substrate_names": {},
        "reactions": {},
        "sources": [],
    }
    uniprot_gene_coverage = package_dir / "uniprot_model_check" / "uniprot_gene_coverage.csv"
    if uniprot_gene_coverage.exists():
        rows = read_csv_records(uniprot_gene_coverage)
        annotations["sources"].append({"role": "uniprot_gene_coverage", "path": str(uniprot_gene_coverage), "rows": len(rows)})
        for row in rows:
            gene_id = row.get("model_gene_id") or row.get("gene_id") or ""
            if not gene_id:
                continue
            merge_gene_annotation(
                annotations,
                gene_id,
                {
                    "uniprot_id": row.get("uniprot_id") or row.get("uniprot") or "",
                    "ec_number": row.get("ec_number") or row.get("ec_numbers") or "",
                    "protein_name": row.get("protein_name", ""),
                    "reviewed_status": row.get("reviewed_status", ""),
                },
            )

    for source in package_annotation_sources(package_dir):
        role = source["role"]
        path = Path(source["path"])
        if role not in {"uniprot_annotation", "dlkcat_annotation", "id_alias_table", "ml_priors"}:
            continue
        rows = read_csv_records(path)
        annotations["sources"].append({"role": role, "path": str(path), "rows": len(rows)})
        consume_annotation_rows(rows, annotations, model_index)
    return annotations


def package_annotation_sources(package_dir: Path) -> list[dict[str, str]]:
    """Return staged annotation-like input files from package maps."""

    sources: list[dict[str, str]] = []
    for map_path in [package_dir / "normalized_inputs" / "normalized_input_map.csv", package_dir / "input_file_map.csv"]:
        if not map_path.exists():
            continue
        for row in read_package_input_map(package_dir, normalized=map_path.parent.name == "normalized_inputs"):
            path_text = row.get("path", "")
            path = Path(path_text) if path_text else package_dir / str(row.get("relative_path", ""))
            if path.exists():
                sources.append({"role": row.get("role", ""), "path": str(path)})
    return sources


def consume_annotation_rows(rows: list[dict[str, str]], annotations: dict[str, Any], model_index: Any) -> None:
    """Merge flexible user annotation rows into gene/substrate indexes."""

    for row in rows:
        normalized = {normalize_column(key): value for key, value in row.items()}
        gene_id = first_value(normalized, ["model_gene_id", "gene_id", "protein_id", "gene"])
        if gene_id:
            model_gene, _status = model_index.resolve_gene(gene_id)
            merge_gene_annotation(
                annotations,
                model_gene or gene_id,
                {
                    "uniprot_id": first_value(normalized, ["uniprot_id", "uniprot", "accession"]),
                    "ec_number": first_value(normalized, ["ec_number", "ec", "ec_numbers"]),
                    "protein_sequence": first_value(
                        normalized,
                        ["protein_sequence", "sequence", "aa_sequence", "amino_acid_sequence"],
                    ),
                    "protein_name": first_value(normalized, ["protein_name", "name", "description"]),
                    "reviewed_status": first_value(normalized, ["reviewed_status", "reviewed"]),
                },
            )

        reaction_id = first_value(normalized, ["model_reaction_id", "reaction_id", "cobra_reaction_id"])
        if reaction_id:
            model_reaction, _status = model_index.resolve_reaction(reaction_id)
            merge_reaction_annotation(
                annotations,
                model_reaction or reaction_id,
                {
                    "ec_number": first_value(normalized, ["ec_number", "ec", "ec_numbers"]),
                    "substrate_name": first_value(normalized, ["substrate_name", "metabolite_name"]),
                    "substrate_smiles": first_value(normalized, ["substrate_smiles", "smiles", "metabolite_smiles"]),
                },
            )

        substrate_id = first_value(normalized, ["substrate_id", "metabolite_id", "species_id"])
        substrate_name = first_value(normalized, ["substrate_name", "metabolite_name"])
        substrate_smiles = first_value(normalized, ["substrate_smiles", "smiles", "metabolite_smiles"])
        if substrate_id:
            for alias in substrate_aliases(substrate_id):
                merge_substrate_annotation(
                    annotations["substrates"],
                    alias,
                    {"substrate_name": substrate_name, "substrate_smiles": substrate_smiles},
                )
        if substrate_name:
            merge_substrate_annotation(
                annotations["substrate_names"],
                substrate_name.lower(),
                {"substrate_name": substrate_name, "substrate_smiles": substrate_smiles},
            )


def build_dlkcat_input_rows(
    reactions: list[dict[str, object]],
    gpr_rules: dict[str, Any],
    annotations: dict[str, Any],
) -> list[dict[str, object]]:
    """Build one DLKcat query row per reaction-gene-substrate tuple."""

    rows: list[dict[str, object]] = []
    for reaction in reactions:
        reaction_id = str(reaction["reaction_id"])
        rule = gpr_rules.get(reaction_id)
        genes = list(getattr(rule, "genes", []) or [""])
        reactants = list(reaction.get("reactants") or [])
        if not reactants:
            reactants = [{"substrate_id": "", "substrate_name": ""}]
        for gene_id in genes:
            gene_annotation = annotations["genes"].get(gene_id, {})
            for reactant in reactants:
                substrate_id = str(reactant.get("substrate_id", ""))
                substrate_name = str(reactant.get("substrate_name", ""))
                substrate_annotation = lookup_substrate_annotation(annotations, substrate_id, substrate_name)
                reaction_annotation = annotations["reactions"].get(reaction_id, {})
                protein_sequence = gene_annotation.get("protein_sequence", "")
                resolved_substrate_name = substrate_annotation.get("substrate_name") or reaction_annotation.get("substrate_name") or substrate_name
                substrate_smiles = substrate_annotation.get("substrate_smiles") or reaction_annotation.get("substrate_smiles", "")
                sequence_status = "sequence_available" if protein_sequence else "missing_sequence"
                substrate_status = "substrate_available" if (substrate_smiles or resolved_substrate_name) else "missing_substrate"
                if not gene_id:
                    input_status = "missing_gpr"
                elif protein_sequence and (substrate_smiles or resolved_substrate_name):
                    input_status = "ready_for_dlkcat"
                elif not protein_sequence and substrate_status == "missing_substrate":
                    input_status = "missing_sequence_and_substrate"
                elif not protein_sequence:
                    input_status = "missing_sequence"
                else:
                    input_status = "missing_substrate"
                query_id = make_query_id(reaction_id, gene_id, substrate_id or resolved_substrate_name)
                rows.append(
                    {
                        "query_id": query_id,
                        "reaction_id": reaction_id,
                        "cobra_reaction_id": reaction.get("cobra_reaction_id", ""),
                        "reaction_name": reaction.get("reaction_name", ""),
                        "gene_id": gene_id,
                        "uniprot_id": gene_annotation.get("uniprot_id", ""),
                        "ec_number": gene_annotation.get("ec_number") or reaction_annotation.get("ec_number", ""),
                        "substrate_id": substrate_id,
                        "substrate_name": resolved_substrate_name,
                        "substrate_smiles": substrate_smiles,
                        "protein_sequence": protein_sequence,
                        "sequence_status": sequence_status,
                        "substrate_status": substrate_status,
                        "input_status": input_status,
                        "gpr_rule": getattr(rule, "rule_text", "") if rule else "",
                        "note": input_guidance(input_status),
                    }
                )
    return rows


def build_input_coverage_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Summarize DLKcat readiness per reaction."""

    grouped: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("reaction_id", "")), []).append(row)
    output = []
    for reaction_id, reaction_rows in sorted(grouped.items()):
        ready = [row for row in reaction_rows if row.get("input_status") == "ready_for_dlkcat"]
        missing_sequence = [row for row in reaction_rows if "missing_sequence" in str(row.get("input_status", ""))]
        missing_substrate = [row for row in reaction_rows if "missing_substrate" in str(row.get("input_status", ""))]
        output.append(
            {
                "reaction_id": reaction_id,
                "cobra_reaction_id": reaction_rows[0].get("cobra_reaction_id", ""),
                "reaction_name": reaction_rows[0].get("reaction_name", ""),
                "query_count": len(reaction_rows),
                "ready_query_count": len(ready),
                "missing_sequence_count": len(missing_sequence),
                "missing_substrate_count": len(missing_substrate),
                "ready_fraction": len(ready) / len(reaction_rows) if reaction_rows else "",
                "status": "ready" if ready else "needs_annotation",
            }
        )
    return output


def normalize_dlkcat_predictions(
    prediction_rows: list[dict[str, str]],
    input_rows: list[dict[str, object]],
    model_index: Any,
) -> list[dict[str, object]]:
    """Normalize user-imported DLKcat outputs and map them back to input rows."""

    input_by_query = {str(row.get("query_id", "")): row for row in input_rows if row.get("query_id")}
    normalized: list[dict[str, object]] = []
    for row in prediction_rows:
        normalized_row = {normalize_column(key): value for key, value in row.items()}
        query_id = first_value(normalized_row, ["query_id"])
        input_row = input_by_query.get(query_id, {})
        raw_reaction = first_value(normalized_row, ["reaction_id", "model_reaction_id"]) or str(input_row.get("reaction_id", ""))
        model_reaction, reaction_status = model_index.resolve_reaction(raw_reaction) if raw_reaction else ("", "missing_reaction")
        kcat = to_float(first_value(normalized_row, ["predicted_kcat", "kcat", "value", "kcat_per_s"]))
        unit = normalize_kcat_unit(first_value(normalized_row, ["unit", "kcat_unit"]) or "per_s")
        prediction_status = first_value(normalized_row, ["dlkcat_status", "status"]) or ("predicted" if kcat is not None else "missing_kcat")
        mapping_status = "mapped" if model_reaction and kcat is not None else "unmapped"
        if query_id and query_id not in input_by_query:
            mapping_status = "unmatched_query_id"
        normalized.append(
            {
                "query_id": query_id or str(input_row.get("query_id", "")),
                "reaction_id": model_reaction,
                "cobra_reaction_id": cobra_reaction_id(model_reaction),
                "gene_id": first_value(normalized_row, ["gene_id", "model_gene_id"]) or input_row.get("gene_id", ""),
                "substrate_id": first_value(normalized_row, ["substrate_id", "metabolite_id"]) or input_row.get("substrate_id", ""),
                "substrate_name": first_value(normalized_row, ["substrate_name", "metabolite_name"]) or input_row.get("substrate_name", ""),
                "substrate_smiles": first_value(normalized_row, ["substrate_smiles", "smiles"]) or input_row.get("substrate_smiles", ""),
                "predicted_kcat_per_s": kcat if unit == "per_s" else "",
                "unit": unit,
                "confidence": to_float(first_value(normalized_row, ["confidence", "score"])),
                "dlkcat_status": prediction_status,
                "mapping_status": mapping_status,
                "reaction_mapping_status": reaction_status,
                "note": first_value(normalized_row, ["note"]),
            }
        )
    return normalized


def build_reaction_kcat_prior_rows(prediction_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Convert normalized DLKcat predictions into reaction-level kcat priors."""

    rows = []
    for row in prediction_rows:
        kcat = to_float(row.get("predicted_kcat_per_s"))
        reaction_id = str(row.get("reaction_id", ""))
        if not reaction_id or kcat is None or row.get("unit") != "per_s":
            continue
        rows.append(
            {
                "target_id": row.get("cobra_reaction_id", ""),
                "target_type": "reaction",
                "model_target_id": reaction_id,
                "kcat": kcat,
                "unit": "per_s",
                "confidence": row.get("confidence", ""),
                "source_tier": "dlkcat_predicted",
                "status": row.get("mapping_status", ""),
                "source_query_id": row.get("query_id", ""),
                "gene_id": row.get("gene_id", ""),
                "substrate_id": row.get("substrate_id", ""),
                "substrate_name": row.get("substrate_name", ""),
                "note": "Predicted by DLKcat; review before production ecGEM use.",
            }
        )
    return rows


def summarize_dlkcat_bridge(
    input_rows: list[dict[str, object]],
    coverage_rows: list[dict[str, object]],
    import_rows: list[dict[str, str]],
    prediction_rows: list[dict[str, object]],
    kcat_priors: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Build one compact summary row for reports and manifests."""

    ready = [row for row in input_rows if row.get("input_status") == "ready_for_dlkcat"]
    missing_sequence = [row for row in input_rows if "missing_sequence" in str(row.get("input_status", ""))]
    missing_substrate = [row for row in input_rows if "missing_substrate" in str(row.get("input_status", ""))]
    mapped_predictions = [row for row in prediction_rows if row.get("mapping_status") == "mapped"]
    if mapped_predictions:
        status = "predictions_imported"
        guidance = "DLKcat predictions were imported and converted to reaction-level kcat priors."
    elif ready:
        status = "ready_for_external_dlkcat"
        guidance = "Export dlkcat_input.tsv, run DLKcat externally, then import predictions."
    else:
        status = "needs_sequence_or_smiles"
        guidance = "Provide protein sequences and substrate names or SMILES before running DLKcat."
    return [
        {
            "status": status,
            "input_query_count": len(input_rows),
            "ready_query_count": len(ready),
            "reaction_count": len(coverage_rows),
            "ready_reaction_count": len([row for row in coverage_rows if row.get("status") == "ready"]),
            "missing_sequence_count": len(missing_sequence),
            "missing_substrate_count": len(missing_substrate),
            "prediction_import_row_count": len(import_rows),
            "prediction_mapped_count": len(mapped_predictions),
            "reaction_kcat_prior_count": len(kcat_priors),
            "guidance": guidance,
        }
    ]


def build_dlkcat_message(summary: dict[str, object]) -> str:
    """Return a user-facing pipeline message."""

    return (
        "DLKcat bridge completed: "
        f"{summary.get('ready_query_count', 0)}/{summary.get('input_query_count', 0)} queries ready; "
        f"{summary.get('prediction_mapped_count', 0)} predictions mapped."
    )


def merge_gene_annotation(annotations: dict[str, Any], gene_id: str, values: dict[str, str]) -> None:
    target = annotations["genes"].setdefault(gene_id, {})
    for key, value in values.items():
        if value and not target.get(key):
            target[key] = value


def merge_reaction_annotation(annotations: dict[str, Any], reaction_id: str, values: dict[str, str]) -> None:
    target = annotations["reactions"].setdefault(reaction_id, {})
    for key, value in values.items():
        if value and not target.get(key):
            target[key] = value


def merge_substrate_annotation(index: dict[str, dict[str, str]], key: str, values: dict[str, str]) -> None:
    if not key:
        return
    target = index.setdefault(key, {})
    for field, value in values.items():
        if value and not target.get(field):
            target[field] = value


def lookup_substrate_annotation(annotations: dict[str, Any], substrate_id: str, substrate_name: str) -> dict[str, str]:
    for alias in substrate_aliases(substrate_id):
        if alias in annotations["substrates"]:
            return annotations["substrates"][alias]
    if substrate_name and substrate_name.lower() in annotations["substrate_names"]:
        return annotations["substrate_names"][substrate_name.lower()]
    return {}


def substrate_aliases(substrate_id: str) -> list[str]:
    aliases = [substrate_id]
    if substrate_id.startswith("M_"):
        aliases.append(substrate_id[2:])
    match = re.match(r"^M_(.+)_[a-z][a-z0-9]?$", substrate_id)
    if match:
        aliases.append(match.group(1))
    return [alias for alias in aliases if alias]


def input_guidance(status: str) -> str:
    return {
        "ready_for_dlkcat": "Ready for DLKcat prediction.",
        "missing_gpr": "Reaction has no GPR gene; DLKcat needs a protein sequence.",
        "missing_sequence": "Add protein_sequence for this gene in dlkcat_annotation or uniprot_annotation.",
        "missing_substrate": "Add substrate_name or substrate_smiles for this substrate.",
        "missing_sequence_and_substrate": "Add both protein_sequence and substrate annotation.",
    }.get(status, "")


def make_query_id(reaction_id: str, gene_id: str, substrate_id: str) -> str:
    return "__".join(safe_query_part(value) for value in [reaction_id, gene_id or "no_gene", substrate_id or "no_substrate"])


def safe_query_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()) or "unknown"


def normalize_column(column: str) -> str:
    return column.strip().lower().replace("-", "_").replace(" ", "_")


def first_value(row: dict[str, Any], columns: list[str]) -> str:
    for column in columns:
        value = row.get(column)
        if value not in {None, ""}:
            return str(value)
    return ""


def cobra_reaction_id(reaction_id: str) -> str:
    return reaction_id[2:] if reaction_id.startswith("R_") else reaction_id


def normalize_kcat_unit(unit: str) -> str:
    value = unit.strip().lower().replace(" ", "")
    if value in {"per_s", "s^-1", "1/s", "sec^-1", "persecond", "s-1"}:
        return "per_s"
    return unit or "per_s"


def to_float(value: Any) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def write_tsv(path: str | Path, rows: list[dict[str, object]]) -> None:
    """Write TSV rows using stable headers."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        target.write_text("", encoding="utf-8")
        return
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
