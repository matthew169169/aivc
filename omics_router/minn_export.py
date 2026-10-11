"""MINN-style data export for ML + GEM hybrid prototypes."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from .constraints import CORE_NS, parse_sbml_gpr_rules, read_csv_records, write_csv, write_json


@dataclass(slots=True)
class MinnExportResult:
    """Summary returned after exporting graph, tensor, and label tables."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]
    summary_rows: list[dict[str, object]]


def run_minn_export(
    model_path: str | Path,
    package_dir: str | Path,
    output_dir: str | Path | None = None,
) -> MinnExportResult:
    """Export graph/tensor/label tables for MINN-style downstream work."""

    model = Path(model_path)
    package = Path(package_dir)
    output = Path(output_dir) if output_dir else package / "minn_export"
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "summary": str(output / "minn_export_summary.csv"),
        "graph_nodes": str(output / "minn_graph_nodes.csv"),
        "graph_edges": str(output / "minn_graph_edges.csv"),
        "feature_tensor": str(output / "minn_omics_feature_tensor.csv"),
        "phenotype_labels": str(output / "minn_phenotype_labels.csv"),
        "manifest": str(output / "minn_export_manifest.json"),
    }

    nodes, edges = build_gem_graph_tables(model)
    graph_node_ids = {str(row.get("node_id", "")) for row in nodes}
    tensor_rows = build_feature_tensor_rows(package / "ml_results" / "ml_feature_long.csv", graph_node_ids)
    label_rows = build_phenotype_label_rows(package / "generated_constraints" / "flux_validation_targets.csv")
    summary_rows = summarize_minn_export(nodes, edges, tensor_rows, label_rows)

    write_csv(files["graph_nodes"], nodes)
    write_csv(files["graph_edges"], edges)
    write_csv(files["feature_tensor"], tensor_rows)
    write_csv(files["phenotype_labels"], label_rows)
    write_csv(files["summary"], summary_rows)
    write_json(
        files["manifest"],
        {
            "schema_version": "0.1.0",
            "status": "completed",
            "model_path": str(model),
            "package_dir": str(package),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "feature_tensor_row_count": len(tensor_rows),
            "phenotype_label_count": len(label_rows),
            "files": files,
        },
    )
    return MinnExportResult(
        status="completed",
        output_dir=str(output),
        message=(
            f"Exported MINN-style tables with {len(nodes)} graph nodes, "
            f"{len(edges)} graph edges, {len(tensor_rows)} feature rows, and {len(label_rows)} labels."
        ),
        files=files,
        summary_rows=summary_rows,
    )


def build_gem_graph_tables(model_path: str | Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Return node and edge tables from SBML species, reactions, and GPR rules."""

    model = Path(model_path)
    tree = ET.parse(model)
    root = tree.getroot()
    nodes: dict[str, dict[str, object]] = {}
    edges: list[dict[str, object]] = []

    for species in root.findall(f".//{CORE_NS}species"):
        species_id = species.attrib.get("id", "")
        if not species_id:
            continue
        node_id = _canonical_metabolite(species_id)
        nodes[node_id] = {
            "node_id": node_id,
            "node_type": "metabolite",
            "model_id": species_id,
            "cobra_id": species_id[2:] if species_id.startswith("M_") else species_id,
            "name": species.attrib.get("name", ""),
            "compartment": species.attrib.get("compartment", ""),
            "status": "model_node",
        }

    for reaction in root.findall(f".//{CORE_NS}reaction"):
        reaction_id = reaction.attrib.get("id", "")
        if not reaction_id:
            continue
        reaction_node_id = _canonical_reaction(reaction_id)
        nodes.setdefault(
            reaction_node_id,
            {
                "node_id": reaction_node_id,
                "node_type": "reaction",
                "model_id": reaction_id,
                "cobra_id": reaction_id[2:] if reaction_id.startswith("R_") else reaction_id,
                "name": reaction.attrib.get("name", ""),
                "compartment": "",
                "status": "model_node",
            },
        )
        edges.extend(_reaction_species_edges(reaction, reaction_node_id, "reactant", -1.0))
        edges.extend(_reaction_species_edges(reaction, reaction_node_id, "product", 1.0))

    for reaction_id, rule in sorted(parse_sbml_gpr_rules(model).items()):
        reaction_node_id = _canonical_reaction(reaction_id)
        for gene_id in rule.genes:
            gene_node_id = _canonical_gene(gene_id)
            nodes.setdefault(
                gene_node_id,
                {
                    "node_id": gene_node_id,
                    "node_type": "gene",
                    "model_id": gene_id,
                    "cobra_id": gene_id,
                    "name": gene_id,
                    "compartment": "",
                    "status": "model_node",
                },
            )
            edges.append(
                {
                    "source_node_id": gene_node_id,
                    "target_node_id": reaction_node_id,
                    "edge_type": "gene_to_reaction",
                    "stoichiometry": "",
                    "role": "gpr_gene",
                    "reaction_id": reaction_node_id,
                    "metabolite_id": "",
                    "gene_id": gene_node_id,
                    "gpr_rule": rule.rule_text,
                    "status": "model_edge",
                }
            )

    return sorted(nodes.values(), key=lambda row: (str(row["node_type"]), str(row["node_id"]))), edges


def build_feature_tensor_rows(
    feature_long_path: str | Path,
    graph_node_ids: set[str] | None = None,
) -> list[dict[str, object]]:
    """Convert ml_feature_long.csv into a node-aligned long tensor table."""

    path = Path(feature_long_path)
    if not path.exists() or path.stat().st_size == 0:
        return []
    graph_node_ids = graph_node_ids or set()
    rows: list[dict[str, object]] = []
    for record in read_csv_records(path):
        feature_id = record.get("feature_id", "")
        feature_type, entity_id = _split_feature_id(feature_id)
        if feature_type.startswith("phenotype_"):
            continue
        node_type, node_id = _feature_node(feature_type, entity_id)
        if not node_type or not node_id:
            continue
        rows.append(
            {
                "condition": record.get("condition", ""),
                "node_id": node_id,
                "node_type": node_type,
                "feature_channel": feature_type,
                "feature_id": feature_id,
                "source": record.get("source", ""),
                "value": record.get("value", ""),
                "status": "feature_node_aligned" if not graph_node_ids or node_id in graph_node_ids else "feature_node_not_in_graph",
                "evidence": record.get("evidence", ""),
                "note": record.get("note", ""),
            }
        )
    return rows


def build_phenotype_label_rows(flux_targets_path: str | Path) -> list[dict[str, object]]:
    """Build supervised labels from measured flux/phenotype targets."""

    path = Path(flux_targets_path)
    if not path.exists() or path.stat().st_size == 0:
        return []
    rows: list[dict[str, object]] = []
    for record in read_csv_records(path):
        condition = record.get("condition") or record.get("sample") or "default"
        reaction_id = record.get("model_reaction_id") or record.get("reaction_id") or ""
        value = record.get("measured_flux") or record.get("flux") or record.get("value") or ""
        if not reaction_id or str(value).strip() == "":
            continue
        rows.append(
            {
                "condition": condition,
                "label_type": "measured_flux",
                "target_node_id": _canonical_reaction(reaction_id),
                "target_id": reaction_id,
                "value": value,
                "unit": record.get("unit", ""),
                "lower_ci": record.get("lower_ci", ""),
                "upper_ci": record.get("upper_ci", ""),
                "source": "flux_validation_targets",
                "status": "label_available",
            }
        )
    return rows


def summarize_minn_export(
    nodes: list[dict[str, object]],
    edges: list[dict[str, object]],
    tensor_rows: list[dict[str, object]],
    label_rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Summarize graph, tensor, and label coverage."""

    node_types = _count_by(nodes, "node_type")
    edge_types = _count_by(edges, "edge_type")
    conditions = {str(row.get("condition", "")) for row in tensor_rows + label_rows if row.get("condition")}
    feature_channels = {str(row.get("feature_channel", "")) for row in tensor_rows if row.get("feature_channel")}
    return [
        {
            "status": "completed",
            "node_count": len(nodes),
            "reaction_node_count": node_types.get("reaction", 0),
            "metabolite_node_count": node_types.get("metabolite", 0),
            "gene_node_count": node_types.get("gene", 0),
            "edge_count": len(edges),
            "stoichiometric_edge_count": edge_types.get("metabolite_to_reaction", 0) + edge_types.get("reaction_to_metabolite", 0),
            "gene_reaction_edge_count": edge_types.get("gene_to_reaction", 0),
            "condition_count": len(conditions),
            "feature_tensor_row_count": len(tensor_rows),
            "feature_channel_count": len(feature_channels),
            "phenotype_label_count": len(label_rows),
            "guidance": _summary_guidance(tensor_rows, label_rows),
        }
    ]


def _reaction_species_edges(
    reaction: ET.Element,
    reaction_node_id: str,
    role: str,
    sign: float,
) -> list[dict[str, object]]:
    tag = "listOfReactants" if role == "reactant" else "listOfProducts"
    direction = "metabolite_to_reaction" if role == "reactant" else "reaction_to_metabolite"
    edges: list[dict[str, object]] = []
    list_node = reaction.find(f"{CORE_NS}{tag}")
    if list_node is None:
        return edges
    for species_ref in list_node.findall(f"{CORE_NS}speciesReference"):
        species_id = species_ref.attrib.get("species", "")
        if not species_id:
            continue
        metabolite_node_id = _canonical_metabolite(species_id)
        stoich = _to_float(species_ref.attrib.get("stoichiometry")) or 1.0
        source = metabolite_node_id if role == "reactant" else reaction_node_id
        target = reaction_node_id if role == "reactant" else metabolite_node_id
        edges.append(
            {
                "source_node_id": source,
                "target_node_id": target,
                "edge_type": direction,
                "stoichiometry": sign * stoich,
                "role": role,
                "reaction_id": reaction_node_id,
                "metabolite_id": metabolite_node_id,
                "gene_id": "",
                "gpr_rule": "",
                "status": "model_edge",
            }
        )
    return edges


def _feature_node(feature_type: str, entity_id: str) -> tuple[str, str]:
    if not entity_id:
        return "", ""
    if feature_type.endswith("_gene"):
        return "gene", _canonical_gene(entity_id)
    if feature_type.endswith("_reaction") or feature_type.endswith("_flux"):
        return "reaction", _canonical_reaction(entity_id)
    if feature_type.endswith("_metabolite"):
        return "metabolite", _canonical_metabolite(entity_id)
    return "", ""


def _split_feature_id(feature_id: str) -> tuple[str, str]:
    if "::" not in feature_id:
        return feature_id, ""
    feature_type, entity_id = feature_id.split("::", 1)
    return feature_type, entity_id


def _canonical_reaction(reaction_id: str) -> str:
    text = str(reaction_id or "").strip()
    if not text:
        return ""
    return text if text.startswith("R_") else f"R_{text}"


def _canonical_metabolite(metabolite_id: str) -> str:
    text = str(metabolite_id or "").strip()
    if not text:
        return ""
    return text if text.startswith("M_") else f"M_{text}"


def _canonical_gene(gene_id: str) -> str:
    text = str(gene_id or "").strip()
    if not text:
        return ""
    return text if text.startswith("G_") else f"G_{text}"


def _count_by(rows: list[dict[str, object]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, ""))
        counts[value] = counts.get(value, 0) + 1
    return counts


def _summary_guidance(tensor_rows: list[dict[str, object]], label_rows: list[dict[str, object]]) -> str:
    if not tensor_rows and not label_rows:
        return "Graph exported, but no ML feature tensor or phenotype labels are available yet."
    if not label_rows:
        return "Feature tensor is available; add flux or phenotype labels before supervised hybrid modeling."
    if not tensor_rows:
        return "Phenotype labels are available; add omics/GEM feature rows before hybrid modeling."
    return "Graph, feature tensor, and phenotype labels are ready for MINN-style prototype experiments."


def _to_float(value: object) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(str(value))
    except (TypeError, ValueError):
        return None
