"""Framework-neutral dry-run adapter for ML + GEM graph payloads.

This module keeps PyTorch Geometric optional. It prepares stable node, edge,
feature, label, and target tables, then exports a real PyG ``Data`` object only
when torch and torch_geometric are importable in the local environment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .constraints import read_csv_records, write_csv, write_json


@dataclass(slots=True)
class HybridGraphAdapterResult:
    """Summary returned after building a dry-run graph adapter package."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]
    summary_rows: list[dict[str, object]]


def run_hybrid_graph_adapter(
    package_dir: str | Path,
    output_dir: str | Path | None = None,
) -> HybridGraphAdapterResult:
    """Create framework-neutral files for future PyG/DGL adapters."""

    package = Path(package_dir)
    output = Path(output_dir) if output_dir else package / "hybrid_adapter_results"
    output.mkdir(parents=True, exist_ok=True)
    files = hybrid_graph_adapter_files(output)
    minn_dir = package / "minn_export"
    hybrid_dir = package / "hybrid_results"

    source = {
        "nodes": _read_optional(minn_dir / "minn_graph_nodes.csv"),
        "edges": _read_optional(minn_dir / "minn_graph_edges.csv"),
        "features": _read_optional(minn_dir / "minn_omics_feature_tensor.csv"),
        "labels": _read_optional(minn_dir / "minn_phenotype_labels.csv"),
        "target_priors": _read_optional(minn_dir / "minn_readiness_target_priors.csv"),
        "target_scores": _read_optional(hybrid_dir / "hybrid_target_scores.csv"),
        "schema": _read_json_optional(hybrid_dir / "hybrid_runner_schema.json"),
        "metadata": _read_json_optional(hybrid_dir / "hybrid_runner_metadata.json"),
    }
    node_rows, node_flags = build_adapter_node_rows(
        source["nodes"],
        source["edges"],
        source["features"],
        source["labels"],
        source["target_priors"],
        source["target_scores"],
    )
    node_index = {str(row["node_id"]): int(row["node_index"]) for row in node_rows}
    feature_vocab = build_feature_vocabulary(source["features"])
    edge_rows, edge_flags = build_adapter_edge_rows(source["edges"], node_index)
    feature_rows, feature_flags = build_adapter_feature_rows(source["features"], node_index, feature_vocab)
    label_rows, label_flags = build_adapter_label_rows(source["labels"], node_index)
    target_rows, target_flags = build_adapter_target_rows(source["target_priors"], source["target_scores"], node_index)
    feature_vocabulary_rows = build_feature_vocabulary_rows(feature_vocab)
    dense_matrix_rows = build_dense_feature_matrix_rows(node_rows, feature_rows, feature_vocab)
    dense_summary_rows = [summarize_dense_feature_matrix(dense_matrix_rows, node_rows, feature_vocab)]
    validation_flags = [
        *build_source_validation_flags(source),
        *node_flags,
        *edge_flags,
        *feature_flags,
        *label_flags,
        *target_flags,
    ]
    summary_rows = [
        summarize_adapter(
            node_rows=node_rows,
            edge_rows=edge_rows,
            feature_rows=feature_rows,
            label_rows=label_rows,
            target_rows=target_rows,
            feature_vocab=feature_vocab,
            validation_flags=validation_flags,
        )
    ]
    payload_stub = build_payload_stub(files, summary_rows[0], feature_vocab, source)
    pyg_summary_rows = [
        export_optional_pyg_data(
            files=files,
            dry_run_summary=summary_rows[0],
            node_rows=node_rows,
            edge_rows=edge_rows,
            feature_rows=feature_rows,
            label_rows=label_rows,
            target_rows=target_rows,
            feature_vocab=feature_vocab,
        )
    ]
    condition_pyg_rows, condition_pyg_manifest = export_optional_condition_pyg_data(
        files=files,
        dry_run_summary=summary_rows[0],
        node_rows=node_rows,
        edge_rows=edge_rows,
        feature_rows=feature_rows,
        label_rows=label_rows,
        target_rows=target_rows,
        feature_vocab=feature_vocab,
    )
    dgl_summary_rows = [
        export_optional_dgl_graph(
            files=files,
            dry_run_summary=summary_rows[0],
            node_rows=node_rows,
            edge_rows=edge_rows,
            feature_rows=feature_rows,
            label_rows=label_rows,
            target_rows=target_rows,
            feature_vocab=feature_vocab,
        )
    ]
    condition_dgl_rows, condition_dgl_manifest = export_optional_condition_dgl_graphs(
        files=files,
        dry_run_summary=summary_rows[0],
        node_rows=node_rows,
        edge_rows=edge_rows,
        feature_rows=feature_rows,
        label_rows=label_rows,
        target_rows=target_rows,
        feature_vocab=feature_vocab,
    )

    write_csv(files["summary"], summary_rows)
    write_csv(files["nodes"], node_rows)
    write_csv(files["edge_index"], edge_rows)
    write_csv(files["feature_tensor"], feature_rows)
    write_csv(files["labels"], label_rows)
    write_csv(files["targets"], target_rows)
    write_csv(files["validation_flags"], validation_flags)
    write_csv(files["dense_feature_vocabulary"], feature_vocabulary_rows)
    write_csv(files["dense_feature_matrix"], dense_matrix_rows)
    write_csv(files["dense_feature_summary"], dense_summary_rows)
    write_csv(files["pyg_summary"], pyg_summary_rows)
    write_csv(files["condition_pyg_summary"], condition_pyg_rows)
    write_csv(files["dgl_summary"], dgl_summary_rows)
    write_csv(files["condition_dgl_summary"], condition_dgl_rows)
    write_json(files["payload_stub"], payload_stub)
    write_json(files["condition_pyg_manifest"], condition_pyg_manifest)
    write_json(files["condition_dgl_manifest"], condition_dgl_manifest)
    write_json(
        files["manifest"],
        {
            "schema_version": "0.1.0",
            "status": summary_rows[0]["status"],
            "pyg_export_status": pyg_summary_rows[0]["status"],
            "condition_pyg_export_status": summarize_condition_pyg_status(condition_pyg_rows),
            "condition_pyg_export_count": len(condition_pyg_rows),
            "dgl_export_status": dgl_summary_rows[0]["status"],
            "condition_dgl_export_status": summarize_condition_pyg_status(condition_dgl_rows),
            "condition_dgl_export_count": len(condition_dgl_rows),
            "dense_feature_matrix_status": dense_summary_rows[0]["status"],
            "dense_feature_matrix_row_count": len(dense_matrix_rows),
            "dense_feature_vocabulary_count": len(feature_vocabulary_rows),
            "package_dir": str(package),
            "source_files": {
                "minn_graph_nodes": str(minn_dir / "minn_graph_nodes.csv"),
                "minn_graph_edges": str(minn_dir / "minn_graph_edges.csv"),
                "minn_omics_feature_tensor": str(minn_dir / "minn_omics_feature_tensor.csv"),
                "minn_phenotype_labels": str(minn_dir / "minn_phenotype_labels.csv"),
                "minn_readiness_target_priors": str(minn_dir / "minn_readiness_target_priors.csv"),
                "hybrid_target_scores": str(hybrid_dir / "hybrid_target_scores.csv"),
                "hybrid_runner_schema": str(hybrid_dir / "hybrid_runner_schema.json"),
                "hybrid_runner_metadata": str(hybrid_dir / "hybrid_runner_metadata.json"),
            },
            "files": files,
        },
    )
    return HybridGraphAdapterResult(
        status="completed",
        output_dir=str(output),
        message=str(summary_rows[0]["guidance"]),
        files=files,
        summary_rows=summary_rows,
    )


def hybrid_graph_adapter_files(output: Path) -> dict[str, str]:
    return {
        "summary": str(output / "hybrid_graph_adapter_summary.csv"),
        "nodes": str(output / "hybrid_graph_adapter_nodes.csv"),
        "edge_index": str(output / "hybrid_graph_adapter_edge_index.csv"),
        "feature_tensor": str(output / "hybrid_graph_adapter_feature_tensor.csv"),
        "labels": str(output / "hybrid_graph_adapter_labels.csv"),
        "targets": str(output / "hybrid_graph_adapter_targets.csv"),
        "validation_flags": str(output / "hybrid_graph_adapter_validation_flags.csv"),
        "dense_feature_vocabulary": str(output / "hybrid_graph_adapter_dense_feature_vocabulary.csv"),
        "dense_feature_matrix": str(output / "hybrid_graph_adapter_dense_feature_matrix.csv"),
        "dense_feature_summary": str(output / "hybrid_graph_adapter_dense_feature_summary.csv"),
        "payload_stub": str(output / "hybrid_graph_adapter_payload_stub.json"),
        "pyg_summary": str(output / "hybrid_graph_adapter_pyg_summary.csv"),
        "pyg_data": str(output / "hybrid_graph_adapter_pyg_data.pt"),
        "condition_pyg_summary": str(output / "hybrid_graph_adapter_condition_pyg_summary.csv"),
        "condition_pyg_manifest": str(output / "hybrid_graph_adapter_condition_pyg_manifest.json"),
        "condition_pyg_dir": str(output / "condition_pyg_data"),
        "dgl_summary": str(output / "hybrid_graph_adapter_dgl_summary.csv"),
        "dgl_graph": str(output / "hybrid_graph_adapter_dgl_graph.bin"),
        "condition_dgl_summary": str(output / "hybrid_graph_adapter_condition_dgl_summary.csv"),
        "condition_dgl_manifest": str(output / "hybrid_graph_adapter_condition_dgl_manifest.json"),
        "condition_dgl_dir": str(output / "condition_dgl_data"),
        "manifest": str(output / "hybrid_graph_adapter_manifest.json"),
    }


def build_adapter_node_rows(
    node_rows: list[dict[str, str]],
    edge_rows: list[dict[str, str]],
    feature_rows: list[dict[str, str]],
    label_rows: list[dict[str, str]],
    target_prior_rows: list[dict[str, str]],
    target_score_rows: list[dict[str, str]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    nodes: dict[str, dict[str, object]] = {}

    def add_node(node_id: object, node_type: object = "", model_id: object = "", name: object = "", source: str = "") -> None:
        text = str(node_id or "").strip()
        if not text:
            return
        row = nodes.setdefault(
            text,
            {
                "node_id": text,
                "node_type": "",
                "model_id": "",
                "name": "",
                "compartment": "",
                "sources": set(),
            },
        )
        if node_type and not row["node_type"]:
            row["node_type"] = str(node_type)
        if model_id and not row["model_id"]:
            row["model_id"] = str(model_id)
        if name and not row["name"]:
            row["name"] = str(name)
        if source:
            row["sources"].add(source)

    for row in node_rows:
        node_id = row.get("node_id", "")
        add_node(node_id, row.get("node_type", ""), row.get("model_id", ""), row.get("name", ""), "explicit_minn_node")
        if node_id and str(node_id).strip() in nodes:
            nodes[str(node_id).strip()]["compartment"] = row.get("compartment", "")
    for row in edge_rows:
        add_node(row.get("source_node_id", ""), source="edge_source")
        add_node(row.get("target_node_id", ""), source="edge_target")
    for row in feature_rows:
        add_node(row.get("node_id", ""), row.get("node_type", ""), source="feature_tensor")
    for row in label_rows:
        add_node(row.get("target_node_id") or canonical_reaction(row.get("target_id", "")), source="phenotype_label")
    for row in target_prior_rows:
        add_node(row.get("node_id", ""), row.get("target_level", ""), source="target_prior")
    for row in target_score_rows:
        add_node(row.get("node_id", ""), row.get("target_level", ""), source="hybrid_target_score")

    rows = []
    flags = []
    for index, node_id in enumerate(sorted(nodes)):
        record = nodes[node_id]
        sources = sorted(record["sources"])
        explicit = "explicit_minn_node" in sources
        if not explicit:
            flags.append(
                validation_flag(
                    "warning",
                    "inferred_node",
                    "node",
                    node_id,
                    "Node was inferred from edges/features/labels/targets because it was absent from minn_graph_nodes.csv.",
                )
            )
        rows.append(
            {
                "node_index": index,
                "node_id": node_id,
                "node_type": record.get("node_type", "") or "unknown",
                "model_id": record.get("model_id", ""),
                "name": record.get("name", ""),
                "compartment": record.get("compartment", ""),
                "source_status": "explicit" if explicit else "inferred",
                "sources": ";".join(sources),
            }
        )
    return rows, flags


def build_adapter_edge_rows(
    rows: list[dict[str, str]],
    node_index: dict[str, int],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    edge_rows = []
    flags = []
    for edge_index, row in enumerate(rows):
        source = str(row.get("source_node_id", "")).strip()
        target = str(row.get("target_node_id", "")).strip()
        if not source or not target:
            flags.append(validation_flag("error", "missing_edge_endpoint", "edge", str(edge_index), "Edge row is missing a source or target node id."))
            continue
        if source not in node_index or target not in node_index:
            flags.append(validation_flag("error", "unresolved_edge_endpoint", "edge", f"{source}->{target}", "Edge endpoint was not resolvable in node index."))
            continue
        weight = _to_float(row.get("stoichiometry"))
        edge_rows.append(
            {
                "edge_index": len(edge_rows),
                "source_index": node_index[source],
                "target_index": node_index[target],
                "source_node_id": source,
                "target_node_id": target,
                "edge_type": row.get("edge_type", ""),
                "edge_weight": weight if weight is not None else 1.0,
                "role": row.get("role", ""),
                "status": "edge_ready",
            }
        )
    if not rows:
        flags.append(validation_flag("warning", "missing_graph_edges", "edge_index", "", "No graph edges were available; downstream graph object will contain isolated nodes."))
    return edge_rows, flags


def build_adapter_feature_rows(
    rows: list[dict[str, str]],
    node_index: dict[str, int],
    feature_vocab: dict[str, int],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    feature_rows = []
    flags = []
    for row_index, row in enumerate(rows):
        node_id = str(row.get("node_id", "")).strip()
        value = _to_float(row.get("value"))
        if not node_id:
            flags.append(validation_flag("error", "missing_feature_node", "feature", str(row_index), "Feature row is missing node_id."))
            continue
        if node_id not in node_index:
            flags.append(validation_flag("error", "unresolved_feature_node", "feature", node_id, "Feature node was not resolvable in node index."))
            continue
        if value is None:
            flags.append(validation_flag("warning", "non_numeric_feature_value", "feature", node_id, "Feature value is not numeric and was skipped."))
            continue
        feature_key = feature_key_from_row(row)
        if not feature_key:
            flags.append(validation_flag("warning", "missing_feature_key", "feature", node_id, "Feature row has no feature_channel or feature_id and was skipped."))
            continue
        feature_rows.append(
            {
                "condition": row.get("condition", "") or "ALL",
                "node_index": node_index[node_id],
                "node_id": node_id,
                "feature_index": feature_vocab[feature_key],
                "feature_key": feature_key,
                "feature_channel": row.get("feature_channel", ""),
                "feature_id": row.get("feature_id", ""),
                "value": round(value, 8),
                "source": row.get("source", ""),
                "status": "feature_ready",
            }
        )
    if not rows:
        flags.append(validation_flag("warning", "missing_feature_tensor", "feature_tensor", "", "No omics feature tensor rows were available."))
    return feature_rows, flags


def build_adapter_label_rows(
    rows: list[dict[str, str]],
    node_index: dict[str, int],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    label_rows = []
    flags = []
    for row_index, row in enumerate(rows):
        node_id = str(row.get("target_node_id") or canonical_reaction(row.get("target_id", ""))).strip()
        value = _to_float(row.get("value"))
        if not node_id:
            flags.append(validation_flag("warning", "missing_label_node", "label", str(row_index), "Label row has no target_node_id or target_id."))
            continue
        if node_id not in node_index:
            flags.append(validation_flag("error", "unresolved_label_node", "label", node_id, "Label target node was not resolvable in node index."))
            continue
        if value is None:
            flags.append(validation_flag("warning", "non_numeric_label_value", "label", node_id, "Label value is not numeric and was skipped."))
            continue
        label_rows.append(
            {
                "condition": row.get("condition", "") or "ALL",
                "label_index": len(label_rows),
                "node_index": node_index[node_id],
                "node_id": node_id,
                "target_id": row.get("target_id", ""),
                "label_type": row.get("label_type", ""),
                "value": round(value, 8),
                "unit": row.get("unit", ""),
                "status": "label_ready",
            }
        )
    if not rows:
        flags.append(validation_flag("warning", "missing_phenotype_labels", "label", "", "No phenotype labels were available; adapter is unsupervised/dry-run only."))
    return label_rows, flags


def build_adapter_target_rows(
    target_prior_rows: list[dict[str, str]],
    target_score_rows: list[dict[str, str]],
    node_index: dict[str, int],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rows = []
    flags = []
    seen: set[tuple[str, str, str]] = set()
    for score in target_score_rows:
        row, flag = adapter_target_row(score, node_index, "hybrid_target_score")
        if flag:
            flags.append(flag)
            continue
        key = (str(row["condition"]), str(row["node_id"]), str(row["target_id"]))
        seen.add(key)
        rows.append(row)
    for prior in target_prior_rows:
        key = (str(prior.get("condition", "")), str(prior.get("node_id", "")), str(prior.get("target_id", "")))
        if key in seen:
            continue
        row, flag = adapter_target_row(prior, node_index, "readiness_target_prior")
        if flag:
            flags.append(flag)
            continue
        rows.append(row)
    if not target_prior_rows and not target_score_rows:
        flags.append(validation_flag("warning", "missing_target_priors", "target", "", "No readiness target priors or hybrid target scores were available."))
    return rows, flags


def adapter_target_row(
    row: dict[str, str],
    node_index: dict[str, int],
    target_source: str,
) -> tuple[dict[str, object], dict[str, object] | None]:
    node_id = str(row.get("node_id", "")).strip()
    if not node_id:
        return {}, validation_flag("warning", "missing_target_node", "target", str(row.get("target_id", "")), "Target row has no node_id.")
    if node_id not in node_index:
        return {}, validation_flag("error", "unresolved_target_node", "target", node_id, "Target node was not resolvable in node index.")
    return (
        {
            "condition": row.get("condition", "") or "ALL",
            "node_index": node_index[node_id],
            "node_id": node_id,
            "target_level": row.get("target_level", ""),
            "target_id": row.get("target_id", ""),
            "recommended_action": row.get("recommended_action", ""),
            "hybrid_rank_score": row.get("hybrid_rank_score", ""),
            "prediction_label": row.get("prediction_label", ""),
            "candidate_target_label": row.get("candidate_target_label", ""),
            "production_readiness_label": row.get("production_readiness_label", ""),
            "training_role": row.get("training_role", ""),
            "target_source": target_source,
            "status": "target_ready",
        },
        None,
    )


def summarize_adapter(
    *,
    node_rows: list[dict[str, object]],
    edge_rows: list[dict[str, object]],
    feature_rows: list[dict[str, object]],
    label_rows: list[dict[str, object]],
    target_rows: list[dict[str, object]],
    feature_vocab: dict[str, int],
    validation_flags: list[dict[str, object]],
) -> dict[str, object]:
    severity_counts = count_by(validation_flags, "severity")
    error_count = severity_counts.get("error", 0)
    warning_count = severity_counts.get("warning", 0)
    if not node_rows:
        status = "dry_run_failed_no_nodes"
    elif error_count:
        status = "dry_run_failed_validation"
    elif warning_count:
        status = "dry_run_ready_with_warnings"
    else:
        status = "dry_run_ready"
    return {
        "status": status,
        "node_count": len(node_rows),
        "explicit_node_count": sum(1 for row in node_rows if row.get("source_status") == "explicit"),
        "inferred_node_count": sum(1 for row in node_rows if row.get("source_status") == "inferred"),
        "edge_count": len(edge_rows),
        "feature_tensor_row_count": len(feature_rows),
        "feature_dim": len(feature_vocab),
        "condition_count": len(unique_values(feature_rows + label_rows + target_rows, "condition")),
        "label_count": len(label_rows),
        "target_count": len(target_rows),
        "validation_flag_count": len(validation_flags),
        "error_count": error_count,
        "warning_count": warning_count,
        "pyg_ready": bool(node_rows and not error_count),
        "dgl_ready": bool(node_rows and not error_count),
        "guidance": adapter_guidance(status),
    }


def build_payload_stub(
    files: dict[str, str],
    summary: dict[str, object],
    feature_vocab: dict[str, int],
    source: dict[str, object],
) -> dict[str, object]:
    schema = source.get("schema") if isinstance(source.get("schema"), dict) else {}
    metadata = source.get("metadata") if isinstance(source.get("metadata"), dict) else {}
    return {
        "schema_version": "0.1.0",
        "status": summary.get("status", ""),
        "contract_source_schema_version": schema.get("schema_version", ""),
        "contract_source_metadata_version": metadata.get("schema_version", ""),
        "shape": {
            "node_count": summary.get("node_count", 0),
            "edge_count": summary.get("edge_count", 0),
            "feature_dim": summary.get("feature_dim", 0),
            "label_count": summary.get("label_count", 0),
            "target_count": summary.get("target_count", 0),
        },
        "feature_vocabulary": [
            {"feature_index": index, "feature_key": key, "feature_column": feature_column_name(index)}
            for key, index in sorted(feature_vocab.items(), key=lambda item: item[1])
        ],
        "dense_feature_matrix": {
            "matrix_table": files["dense_feature_matrix"],
            "vocabulary_table": files["dense_feature_vocabulary"],
            "summary_table": files["dense_feature_summary"],
            "row_keys": ["condition", "node_index", "node_id"],
            "feature_columns": "f0000, f0001, ... mapped by hybrid_graph_adapter_dense_feature_vocabulary.csv",
            "condition_rule": "Rows are condition-specific; ALL features are included in each concrete condition.",
        },
        "pytorch_geometric_stub": {
            "object_hint": "torch_geometric.data.Data or HeteroData",
            "node_index_table": files["nodes"],
            "edge_index_table": files["edge_index"],
            "sparse_feature_table": files["feature_tensor"],
            "label_table": files["labels"],
            "target_table": files["targets"],
            "construction_note": "Map node_index to rows, stack feature_index/value into x, and use source_index/target_index as edge_index.",
        },
        "dgl_stub": {
            "object_hint": "dgl.graph plus node/edge feature frames",
            "node_index_table": files["nodes"],
            "edge_index_table": files["edge_index"],
            "sparse_feature_table": files["feature_tensor"],
            "label_table": files["labels"],
            "target_table": files["targets"],
            "optional_global_graph": files["dgl_graph"],
            "optional_condition_graph_dir": files["condition_dgl_dir"],
            "construction_note": "Build graph from source_index and target_index, then attach sparse or pivoted feature frames by node_index.",
        },
    }


def export_optional_pyg_data(
    *,
    files: dict[str, str],
    dry_run_summary: dict[str, object],
    node_rows: list[dict[str, object]],
    edge_rows: list[dict[str, object]],
    feature_rows: list[dict[str, object]],
    label_rows: list[dict[str, object]],
    target_rows: list[dict[str, object]],
    feature_vocab: dict[str, int],
) -> dict[str, object]:
    """Write a real PyG Data object when optional dependencies are installed."""

    dependency = pyg_dependency_status()
    base = {
        "torch_available": dependency["torch_available"],
        "torch_geometric_available": dependency["torch_geometric_available"],
        "node_count": len(node_rows),
        "edge_count": len(edge_rows),
        "feature_dim": len(feature_vocab),
        "feature_tensor_row_count": len(feature_rows),
        "label_count": len(label_rows),
        "target_count": len(target_rows),
        "object_type": "torch_geometric.data.Data",
        "data_path": "",
    }
    if not dependency["available"]:
        return {
            **base,
            "status": "skipped_missing_dependency",
            "message": dependency["message"],
            "feature_aggregation": "",
            "guidance": "PyTorch Geometric export was skipped; install torch and torch_geometric to create a .pt Data object.",
        }
    if not node_rows:
        return {
            **base,
            "status": "skipped_no_nodes",
            "message": "No adapter nodes were available.",
            "feature_aggregation": "",
            "guidance": "Run MINN export or provide feature/target rows before exporting PyG data.",
        }
    if not truthy(dry_run_summary.get("pyg_ready")):
        return {
            **base,
            "status": "skipped_dry_run_not_ready",
            "message": "Dry-run validation reported unresolved errors.",
            "feature_aggregation": "",
            "guidance": "Review adapter validation flags before exporting PyG data.",
        }
    try:
        import torch
        from torch_geometric.data import Data

        data = build_pyg_data_object(
            torch_module=torch,
            data_cls=Data,
            node_rows=node_rows,
            edge_rows=edge_rows,
            feature_rows=feature_rows,
            label_rows=label_rows,
            target_rows=target_rows,
            feature_vocab=feature_vocab,
            selected_condition="ALL_CONDITIONS",
            feature_aggregation="mean_by_node_feature_across_conditions",
        )
        torch.save(data, files["pyg_data"])
    except Exception as exc:  # pragma: no cover - depends on optional local packages
        return {
            **base,
            "status": "failed_pyg_export",
            "message": str(exc),
            "feature_aggregation": "mean_by_node_feature_across_conditions",
            "guidance": "PyTorch Geometric dependencies were detected, but Data export failed; review the exception message.",
        }
    return {
        **base,
        "status": "completed",
        "message": "PyTorch Geometric Data object was exported.",
        "feature_aggregation": "mean_by_node_feature_across_conditions",
        "data_path": files["pyg_data"],
        "guidance": "A real torch_geometric.data.Data object is available for downstream prototype training.",
    }


def build_feature_vocabulary_rows(feature_vocab: dict[str, int]) -> list[dict[str, object]]:
    rows = []
    for key, index in sorted(feature_vocab.items(), key=lambda item: item[1]):
        channel, feature_id = split_feature_key(key)
        rows.append(
            {
                "feature_index": index,
                "feature_column": feature_column_name(index),
                "feature_key": key,
                "feature_channel": channel,
                "feature_id": feature_id,
                "status": "feature_column_ready",
            }
        )
    return rows


def build_dense_feature_matrix_rows(
    node_rows: list[dict[str, object]],
    feature_rows: list[dict[str, object]],
    feature_vocab: dict[str, int],
) -> list[dict[str, object]]:
    """Return one wide feature row per condition and graph node."""

    if not node_rows:
        return []
    conditions = adapter_conditions(feature_rows, [], []) or ["ALL"]
    feature_columns = [feature_column_name(index) for _key, index in sorted(feature_vocab.items(), key=lambda item: item[1])]
    rows = []
    for condition in conditions:
        selected_features = rows_for_condition(feature_rows, condition)
        grouped = aggregate_dense_features(selected_features)
        for node in node_rows:
            node_index = int(node.get("node_index", 0))
            values = grouped.get(node_index, {})
            row: dict[str, object] = {
                "condition": condition,
                "node_index": node_index,
                "node_id": node.get("node_id", ""),
                "node_type": node.get("node_type", ""),
                "source_status": node.get("source_status", ""),
                "feature_count": len(values),
            }
            for column in feature_columns:
                row[column] = values.get(column, 0.0)
            row["status"] = "dense_features_available" if values else "dense_features_zero"
            rows.append(row)
    rows.sort(key=lambda row: (str(row.get("condition", "")), int(row.get("node_index", 0))))
    return rows


def aggregate_dense_features(rows: list[dict[str, object]]) -> dict[int, dict[str, float]]:
    sums: dict[tuple[int, str], float] = {}
    counts: dict[tuple[int, str], int] = {}
    for row in rows:
        node_index = int(row.get("node_index", 0))
        feature_index = int(row.get("feature_index", 0))
        value = _to_float(row.get("value"))
        if value is None:
            continue
        key = (node_index, feature_column_name(feature_index))
        sums[key] = sums.get(key, 0.0) + value
        counts[key] = counts.get(key, 0) + 1
    grouped: dict[int, dict[str, float]] = {}
    for (node_index, column), total in sums.items():
        grouped.setdefault(node_index, {})[column] = round(total / counts[(node_index, column)], 8)
    return grouped


def summarize_dense_feature_matrix(
    rows: list[dict[str, object]],
    node_rows: list[dict[str, object]],
    feature_vocab: dict[str, int],
) -> dict[str, object]:
    if not node_rows:
        status = "skipped_no_nodes"
        guidance = "No graph nodes were available for dense feature matrix export."
    elif not feature_vocab:
        status = "completed_no_features"
        guidance = "Dense matrix rows were written, but no numeric feature columns were available."
    else:
        status = "completed"
        guidance = "Dense feature matrix is available for tabular ML baselines and adapter checks."
    return {
        "status": status,
        "row_count": len(rows),
        "node_count": len(node_rows),
        "condition_count": len(unique_values(rows, "condition")),
        "feature_dim": len(feature_vocab),
        "nonzero_row_count": sum(1 for row in rows if int(row.get("feature_count", 0)) > 0),
        "zero_row_count": sum(1 for row in rows if int(row.get("feature_count", 0)) == 0),
        "row_grain": "condition_x_node",
        "feature_column_prefix": "f",
        "guidance": guidance,
    }


def export_optional_condition_pyg_data(
    *,
    files: dict[str, str],
    dry_run_summary: dict[str, object],
    node_rows: list[dict[str, object]],
    edge_rows: list[dict[str, object]],
    feature_rows: list[dict[str, object]],
    label_rows: list[dict[str, object]],
    target_rows: list[dict[str, object]],
    feature_vocab: dict[str, int],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Export one optional PyG Data object per condition when dependencies exist."""

    output_dir = Path(files["condition_pyg_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    conditions = adapter_conditions(feature_rows, label_rows, target_rows)
    dependency = pyg_dependency_status()
    rows: list[dict[str, object]] = []
    generated_files: dict[str, str] = {}
    for condition in conditions:
        condition_features = rows_for_condition(feature_rows, condition)
        condition_labels = rows_for_condition(label_rows, condition)
        condition_targets = rows_for_condition(target_rows, condition)
        data_path = output_dir / f"hybrid_graph_adapter_pyg_data__{safe_condition_name(condition)}.pt"
        base = {
            "condition": condition,
            "torch_available": dependency["torch_available"],
            "torch_geometric_available": dependency["torch_geometric_available"],
            "node_count": len(node_rows),
            "edge_count": len(edge_rows),
            "feature_dim": len(feature_vocab),
            "feature_tensor_row_count": len(condition_features),
            "label_count": len(condition_labels),
            "target_count": len(condition_targets),
            "object_type": "torch_geometric.data.Data",
            "data_path": "",
        }
        if not dependency["available"]:
            rows.append(
                {
                    **base,
                    "status": "skipped_missing_dependency",
                    "message": dependency["message"],
                    "feature_aggregation": "",
                    "guidance": "Condition-specific PyG export was skipped; install torch and torch_geometric to create per-condition .pt files.",
                }
            )
            continue
        if not node_rows:
            rows.append(
                {
                    **base,
                    "status": "skipped_no_nodes",
                    "message": "No adapter nodes were available.",
                    "feature_aggregation": "",
                    "guidance": "Run MINN export or provide feature/target rows before exporting condition-specific PyG data.",
                }
            )
            continue
        if not truthy(dry_run_summary.get("pyg_ready")):
            rows.append(
                {
                    **base,
                    "status": "skipped_dry_run_not_ready",
                    "message": "Dry-run validation reported unresolved errors.",
                    "feature_aggregation": "",
                    "guidance": "Review adapter validation flags before exporting condition-specific PyG data.",
                }
            )
            continue
        try:
            import torch
            from torch_geometric.data import Data

            data = build_pyg_data_object(
                torch_module=torch,
                data_cls=Data,
                node_rows=node_rows,
                edge_rows=edge_rows,
                feature_rows=condition_features,
                label_rows=condition_labels,
                target_rows=condition_targets,
                feature_vocab=feature_vocab,
                selected_condition=condition,
                feature_aggregation="condition_specific_exact_or_all",
            )
            torch.save(data, data_path)
        except Exception as exc:  # pragma: no cover - depends on optional local packages
            rows.append(
                {
                    **base,
                    "status": "failed_pyg_export",
                    "message": str(exc),
                    "feature_aggregation": "condition_specific_exact_or_all",
                    "guidance": "PyG dependencies were detected, but condition-specific export failed; review the exception message.",
                }
            )
            continue
        generated_files[condition] = str(data_path)
        rows.append(
            {
                **base,
                "status": "completed",
                "message": "Condition-specific PyTorch Geometric Data object was exported.",
                "feature_aggregation": "condition_specific_exact_or_all",
                "data_path": str(data_path),
                "guidance": "A per-condition PyG Data object is available without cross-condition feature averaging.",
            }
        )
    if not rows:
        rows.append(
            {
                "condition": "",
                "status": "skipped_no_conditions",
                "torch_available": dependency["torch_available"],
                "torch_geometric_available": dependency["torch_geometric_available"],
                "node_count": len(node_rows),
                "edge_count": len(edge_rows),
                "feature_dim": len(feature_vocab),
                "feature_tensor_row_count": 0,
                "label_count": 0,
                "target_count": 0,
                "object_type": "torch_geometric.data.Data",
                "data_path": "",
                "message": "No condition-bearing feature, label, or target rows were available.",
                "feature_aggregation": "",
                "guidance": "Provide condition-aware omics features, labels, or target priors before condition-specific export.",
            }
        )
    return rows, {
        "schema_version": "0.1.0",
        "status": summarize_condition_pyg_status(rows),
        "condition_count": len([row for row in rows if row.get("condition")]),
        "generated_files": generated_files,
        "summary_file": files["condition_pyg_summary"],
        "output_dir": str(output_dir),
    }


def export_optional_dgl_graph(
    *,
    files: dict[str, str],
    dry_run_summary: dict[str, object],
    node_rows: list[dict[str, object]],
    edge_rows: list[dict[str, object]],
    feature_rows: list[dict[str, object]],
    label_rows: list[dict[str, object]],
    target_rows: list[dict[str, object]],
    feature_vocab: dict[str, int],
) -> dict[str, object]:
    """Write a real DGL graph when optional dependencies are installed."""

    dependency = dgl_dependency_status()
    base = {
        "torch_available": dependency["torch_available"],
        "dgl_available": dependency["dgl_available"],
        "node_count": len(node_rows),
        "edge_count": len(edge_rows),
        "feature_dim": len(feature_vocab),
        "feature_tensor_row_count": len(feature_rows),
        "label_count": len(label_rows),
        "target_count": len(target_rows),
        "object_type": "dgl.DGLGraph",
        "graph_path": "",
    }
    if not dependency["available"]:
        return {
            **base,
            "status": "skipped_missing_dependency",
            "message": dependency["message"],
            "feature_aggregation": "",
            "guidance": "DGL export was skipped; install torch and dgl to create a graph .bin file.",
        }
    if not node_rows:
        return {
            **base,
            "status": "skipped_no_nodes",
            "message": "No adapter nodes were available.",
            "feature_aggregation": "",
            "guidance": "Run MINN export or provide feature/target rows before exporting DGL graph.",
        }
    if not truthy(dry_run_summary.get("dgl_ready")):
        return {
            **base,
            "status": "skipped_dry_run_not_ready",
            "message": "Dry-run validation reported unresolved errors.",
            "feature_aggregation": "",
            "guidance": "Review adapter validation flags before exporting DGL graph.",
        }
    try:
        import dgl
        import torch

        graph = build_dgl_graph_object(
            torch_module=torch,
            dgl_module=dgl,
            node_rows=node_rows,
            edge_rows=edge_rows,
            feature_rows=feature_rows,
            label_rows=label_rows,
            target_rows=target_rows,
            feature_vocab=feature_vocab,
            selected_condition="ALL_CONDITIONS",
            feature_aggregation="mean_by_node_feature_across_conditions",
        )
        dgl.save_graphs(files["dgl_graph"], [graph])
    except Exception as exc:  # pragma: no cover - depends on optional local packages
        return {
            **base,
            "status": "failed_dgl_export",
            "message": str(exc),
            "feature_aggregation": "mean_by_node_feature_across_conditions",
            "guidance": "DGL dependencies were detected, but graph export failed; review the exception message.",
        }
    return {
        **base,
        "status": "completed",
        "message": "DGL graph object was exported.",
        "feature_aggregation": "mean_by_node_feature_across_conditions",
        "graph_path": files["dgl_graph"],
        "guidance": "A real DGL graph is available for downstream prototype training.",
    }


def export_optional_condition_dgl_graphs(
    *,
    files: dict[str, str],
    dry_run_summary: dict[str, object],
    node_rows: list[dict[str, object]],
    edge_rows: list[dict[str, object]],
    feature_rows: list[dict[str, object]],
    label_rows: list[dict[str, object]],
    target_rows: list[dict[str, object]],
    feature_vocab: dict[str, int],
) -> tuple[list[dict[str, object]], dict[str, object]]:
    """Export one optional DGL graph per condition when dependencies exist."""

    output_dir = Path(files["condition_dgl_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    conditions = adapter_conditions(feature_rows, label_rows, target_rows)
    dependency = dgl_dependency_status()
    rows: list[dict[str, object]] = []
    generated_files: dict[str, str] = {}
    for condition in conditions:
        condition_features = rows_for_condition(feature_rows, condition)
        condition_labels = rows_for_condition(label_rows, condition)
        condition_targets = rows_for_condition(target_rows, condition)
        graph_path = output_dir / f"hybrid_graph_adapter_dgl_graph__{safe_condition_name(condition)}.bin"
        base = {
            "condition": condition,
            "torch_available": dependency["torch_available"],
            "dgl_available": dependency["dgl_available"],
            "node_count": len(node_rows),
            "edge_count": len(edge_rows),
            "feature_dim": len(feature_vocab),
            "feature_tensor_row_count": len(condition_features),
            "label_count": len(condition_labels),
            "target_count": len(condition_targets),
            "object_type": "dgl.DGLGraph",
            "graph_path": "",
        }
        if not dependency["available"]:
            rows.append(
                {
                    **base,
                    "status": "skipped_missing_dependency",
                    "message": dependency["message"],
                    "feature_aggregation": "",
                    "guidance": "Condition-specific DGL export was skipped; install torch and dgl to create per-condition graph files.",
                }
            )
            continue
        if not node_rows:
            rows.append(
                {
                    **base,
                    "status": "skipped_no_nodes",
                    "message": "No adapter nodes were available.",
                    "feature_aggregation": "",
                    "guidance": "Run MINN export or provide feature/target rows before exporting condition-specific DGL graphs.",
                }
            )
            continue
        if not truthy(dry_run_summary.get("dgl_ready")):
            rows.append(
                {
                    **base,
                    "status": "skipped_dry_run_not_ready",
                    "message": "Dry-run validation reported unresolved errors.",
                    "feature_aggregation": "",
                    "guidance": "Review adapter validation flags before exporting condition-specific DGL graphs.",
                }
            )
            continue
        try:
            import dgl
            import torch

            graph = build_dgl_graph_object(
                torch_module=torch,
                dgl_module=dgl,
                node_rows=node_rows,
                edge_rows=edge_rows,
                feature_rows=condition_features,
                label_rows=condition_labels,
                target_rows=condition_targets,
                feature_vocab=feature_vocab,
                selected_condition=condition,
                feature_aggregation="condition_specific_exact_or_all",
            )
            dgl.save_graphs(str(graph_path), [graph])
        except Exception as exc:  # pragma: no cover - depends on optional local packages
            rows.append(
                {
                    **base,
                    "status": "failed_dgl_export",
                    "message": str(exc),
                    "feature_aggregation": "condition_specific_exact_or_all",
                    "guidance": "DGL dependencies were detected, but condition-specific export failed; review the exception message.",
                }
            )
            continue
        generated_files[condition] = str(graph_path)
        rows.append(
            {
                **base,
                "status": "completed",
                "message": "Condition-specific DGL graph was exported.",
                "feature_aggregation": "condition_specific_exact_or_all",
                "graph_path": str(graph_path),
                "guidance": "A per-condition DGL graph is available without cross-condition feature averaging.",
            }
        )
    if not rows:
        rows.append(
            {
                "condition": "",
                "status": "skipped_no_conditions",
                "torch_available": dependency["torch_available"],
                "dgl_available": dependency["dgl_available"],
                "node_count": len(node_rows),
                "edge_count": len(edge_rows),
                "feature_dim": len(feature_vocab),
                "feature_tensor_row_count": 0,
                "label_count": 0,
                "target_count": 0,
                "object_type": "dgl.DGLGraph",
                "graph_path": "",
                "message": "No condition-bearing feature, label, or target rows were available.",
                "feature_aggregation": "",
                "guidance": "Provide condition-aware omics features, labels, or target priors before condition-specific DGL export.",
            }
        )
    return rows, {
        "schema_version": "0.1.0",
        "status": summarize_condition_pyg_status(rows),
        "condition_count": len([row for row in rows if row.get("condition")]),
        "generated_files": generated_files,
        "summary_file": files["condition_dgl_summary"],
        "output_dir": str(output_dir),
    }


def build_pyg_data_object(
    *,
    torch_module: object,
    data_cls: object,
    node_rows: list[dict[str, object]],
    edge_rows: list[dict[str, object]],
    feature_rows: list[dict[str, object]],
    label_rows: list[dict[str, object]],
    target_rows: list[dict[str, object]],
    feature_vocab: dict[str, int],
    selected_condition: str,
    feature_aggregation: str,
) -> object:
    """Build a torch_geometric Data-like object from adapter rows."""

    torch = torch_module
    node_count = len(node_rows)
    feature_dim = len(feature_vocab)
    x = torch.zeros((node_count, feature_dim), dtype=torch.float32)
    feature_counts = torch.zeros((node_count, feature_dim), dtype=torch.float32)
    for row in feature_rows:
        node_index = int(row.get("node_index", 0))
        feature_index = int(row.get("feature_index", 0))
        value = float(row.get("value", 0.0))
        if node_index < node_count and feature_index < feature_dim:
            x[node_index, feature_index] += value
            feature_counts[node_index, feature_index] += 1.0
    x = torch.where(feature_counts > 0, x / torch.clamp(feature_counts, min=1.0), x)

    if edge_rows:
        edge_index = torch.tensor(
            [
                [int(row.get("source_index", 0)) for row in edge_rows],
                [int(row.get("target_index", 0)) for row in edge_rows],
            ],
            dtype=torch.long,
        )
        edge_weight = torch.tensor([float(row.get("edge_weight", 1.0)) for row in edge_rows], dtype=torch.float32)
    else:
        edge_index = torch.empty((2, 0), dtype=torch.long)
        edge_weight = torch.empty((0,), dtype=torch.float32)

    label_node_index = torch.tensor([int(row.get("node_index", 0)) for row in label_rows], dtype=torch.long)
    label_value = torch.tensor([float(row.get("value", 0.0)) for row in label_rows], dtype=torch.float32)
    target_node_index = torch.tensor([int(row.get("node_index", 0)) for row in target_rows], dtype=torch.long)
    target_score = torch.tensor(
        [_to_float(row.get("hybrid_rank_score")) or 0.0 for row in target_rows],
        dtype=torch.float32,
    )
    data = data_cls(x=x, edge_index=edge_index, edge_weight=edge_weight)
    data.node_ids = [str(row.get("node_id", "")) for row in node_rows]
    data.node_types = [str(row.get("node_type", "")) for row in node_rows]
    data.feature_keys = [key for key, _index in sorted(feature_vocab.items(), key=lambda item: item[1])]
    data.conditions = sorted(unique_values(feature_rows + label_rows + target_rows, "condition"))
    data.selected_condition = selected_condition
    data.label_node_index = label_node_index
    data.label_value = label_value
    data.label_types = [str(row.get("label_type", "")) for row in label_rows]
    data.label_conditions = [str(row.get("condition", "")) for row in label_rows]
    data.target_node_index = target_node_index
    data.target_score = target_score
    data.target_ids = [str(row.get("target_id", "")) for row in target_rows]
    data.target_conditions = [str(row.get("condition", "")) for row in target_rows]
    data.target_prediction_labels = [str(row.get("prediction_label", "")) for row in target_rows]
    data.omics_gem_metadata = {
        "schema_version": "0.1.0",
        "source": "omics_router.hybrid_graph_adapter",
        "selected_condition": selected_condition,
        "feature_aggregation": feature_aggregation,
        "node_count": node_count,
        "edge_count": len(edge_rows),
        "feature_dim": feature_dim,
        "label_count": len(label_rows),
        "target_count": len(target_rows),
    }
    return data


def build_dgl_graph_object(
    *,
    torch_module: object,
    dgl_module: object,
    node_rows: list[dict[str, object]],
    edge_rows: list[dict[str, object]],
    feature_rows: list[dict[str, object]],
    label_rows: list[dict[str, object]],
    target_rows: list[dict[str, object]],
    feature_vocab: dict[str, int],
    selected_condition: str,
    feature_aggregation: str,
) -> object:
    """Build a DGL graph object from adapter rows."""

    torch = torch_module
    dgl = dgl_module
    node_count = len(node_rows)
    x = build_node_feature_tensor(torch, node_count, len(feature_vocab), feature_rows)
    if edge_rows:
        source = torch.tensor([int(row.get("source_index", 0)) for row in edge_rows], dtype=torch.int64)
        target = torch.tensor([int(row.get("target_index", 0)) for row in edge_rows], dtype=torch.int64)
        edge_weight = torch.tensor([float(row.get("edge_weight", 1.0)) for row in edge_rows], dtype=torch.float32)
    else:
        source = torch.empty((0,), dtype=torch.int64)
        target = torch.empty((0,), dtype=torch.int64)
        edge_weight = torch.empty((0,), dtype=torch.float32)
    graph = dgl.graph((source, target), num_nodes=node_count)
    graph.ndata["x"] = x
    graph.edata["weight"] = edge_weight
    label_value, label_mask = node_value_and_mask(torch, node_count, label_rows, "value")
    target_score, target_mask = node_value_and_mask(torch, node_count, target_rows, "hybrid_rank_score")
    graph.ndata["label_value"] = label_value
    graph.ndata["label_mask"] = label_mask
    graph.ndata["target_score"] = target_score
    graph.ndata["target_mask"] = target_mask
    graph.ndata["node_index"] = torch.arange(node_count, dtype=torch.int64)
    graph.graph_data = {
        "schema_version": "0.1.0",
        "source": "omics_router.hybrid_graph_adapter",
        "selected_condition": selected_condition,
        "feature_aggregation": feature_aggregation,
        "node_ids": [str(row.get("node_id", "")) for row in node_rows],
        "node_types": [str(row.get("node_type", "")) for row in node_rows],
        "feature_keys": [key for key, _index in sorted(feature_vocab.items(), key=lambda item: item[1])],
        "label_types": [str(row.get("label_type", "")) for row in label_rows],
        "target_ids": [str(row.get("target_id", "")) for row in target_rows],
    }
    return graph


def build_node_feature_tensor(
    torch_module: object,
    node_count: int,
    feature_dim: int,
    feature_rows: list[dict[str, object]],
) -> object:
    torch = torch_module
    x = torch.zeros((node_count, feature_dim), dtype=torch.float32)
    feature_counts = torch.zeros((node_count, feature_dim), dtype=torch.float32)
    for row in feature_rows:
        node_index = int(row.get("node_index", 0))
        feature_index = int(row.get("feature_index", 0))
        value = float(row.get("value", 0.0))
        if node_index < node_count and feature_index < feature_dim:
            x[node_index, feature_index] += value
            feature_counts[node_index, feature_index] += 1.0
    return torch.where(feature_counts > 0, x / torch.clamp(feature_counts, min=1.0), x)


def node_value_and_mask(
    torch_module: object,
    node_count: int,
    rows: list[dict[str, object]],
    value_key: str,
) -> tuple[object, object]:
    torch = torch_module
    sums = torch.zeros((node_count,), dtype=torch.float32)
    counts = torch.zeros((node_count,), dtype=torch.float32)
    for row in rows:
        node_index = int(row.get("node_index", 0))
        value = _to_float(row.get(value_key))
        if value is None or node_index >= node_count:
            continue
        sums[node_index] += float(value)
        counts[node_index] += 1.0
    mask = counts > 0
    values = torch.where(mask, sums / torch.clamp(counts, min=1.0), torch.zeros((node_count,), dtype=torch.float32))
    return values, mask


def pyg_dependency_status() -> dict[str, object]:
    """Return optional dependency availability without importing at module load."""

    try:
        import torch  # noqa: F401
    except Exception as exc:  # pragma: no cover - environment dependent
        return {
            "available": False,
            "torch_available": False,
            "torch_geometric_available": False,
            "message": f"torch import failed: {exc}",
        }
    try:
        import torch_geometric  # noqa: F401
    except Exception as exc:  # pragma: no cover - environment dependent
        return {
            "available": False,
            "torch_available": True,
            "torch_geometric_available": False,
            "message": f"torch_geometric import failed: {exc}",
        }
    return {
        "available": True,
        "torch_available": True,
        "torch_geometric_available": True,
        "message": "torch and torch_geometric are importable.",
    }


def dgl_dependency_status() -> dict[str, object]:
    """Return optional DGL dependency availability without importing at module load."""

    try:
        import torch  # noqa: F401
    except Exception as exc:  # pragma: no cover - environment dependent
        return {
            "available": False,
            "torch_available": False,
            "dgl_available": False,
            "message": f"torch import failed: {exc}",
        }
    try:
        import dgl  # noqa: F401
    except Exception as exc:  # pragma: no cover - environment dependent
        return {
            "available": False,
            "torch_available": True,
            "dgl_available": False,
            "message": f"dgl import failed: {exc}",
        }
    return {
        "available": True,
        "torch_available": True,
        "dgl_available": True,
        "message": "torch and dgl are importable.",
    }


def build_source_validation_flags(source: dict[str, object]) -> list[dict[str, object]]:
    flags = []
    if not source.get("schema"):
        flags.append(validation_flag("warning", "missing_hybrid_runner_schema", "schema", "", "hybrid_runner_schema.json was not available."))
    if not source.get("metadata"):
        flags.append(validation_flag("warning", "missing_hybrid_runner_metadata", "metadata", "", "hybrid_runner_metadata.json was not available."))
    return flags


def build_feature_vocabulary(rows: list[dict[str, str]]) -> dict[str, int]:
    keys = sorted({feature_key_from_row(row) for row in rows if feature_key_from_row(row)})
    return {key: index for index, key in enumerate(keys)}


def feature_key_from_row(row: dict[str, str]) -> str:
    channel = str(row.get("feature_channel", "")).strip()
    feature_id = str(row.get("feature_id", "")).strip()
    if channel and feature_id:
        return f"{channel}::{feature_id}"
    return channel or feature_id


def split_feature_key(key: str) -> tuple[str, str]:
    if "::" in key:
        channel, feature_id = key.split("::", 1)
        return channel, feature_id
    return key, ""


def feature_column_name(index: int) -> str:
    return f"f{index:04d}"


def validation_flag(
    severity: str,
    flag: str,
    entity_type: str,
    entity_id: str,
    message: str,
) -> dict[str, object]:
    return {
        "severity": severity,
        "flag": flag,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "message": message,
    }


def adapter_guidance(status: str) -> str:
    if status == "dry_run_ready":
        return "Framework-neutral graph payload is ready for a dependency-specific PyG/DGL adapter."
    if status == "dry_run_ready_with_warnings":
        return "Graph payload can be constructed, but warnings should be reviewed before training."
    if status == "dry_run_failed_validation":
        return "Graph payload has unresolved validation errors; review validation flags before adapter use."
    return "No graph nodes were available for adapter construction."


def count_by(rows: list[dict[str, object]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, "")).strip()
        if value:
            counts[value] = counts.get(value, 0) + 1
    return counts


def unique_values(rows: list[dict[str, object]], key: str) -> list[str]:
    return sorted({str(row.get(key, "")).strip() for row in rows if str(row.get(key, "")).strip()})


def adapter_conditions(
    feature_rows: list[dict[str, object]],
    label_rows: list[dict[str, object]],
    target_rows: list[dict[str, object]],
) -> list[str]:
    values = unique_values(feature_rows + label_rows + target_rows, "condition")
    specific = [value for value in values if value != "ALL"]
    return specific or values


def rows_for_condition(rows: list[dict[str, object]], condition: str) -> list[dict[str, object]]:
    if condition == "ALL":
        return [row for row in rows if str(row.get("condition", "")) == "ALL"]
    return [row for row in rows if str(row.get("condition", "")) in {condition, "ALL"}]


def summarize_condition_pyg_status(rows: list[dict[str, object]]) -> str:
    statuses = {str(row.get("status", "")) for row in rows}
    if not rows:
        return "skipped_no_conditions"
    if statuses == {"completed"}:
        return "completed"
    if "completed" in statuses:
        return "partial"
    if "failed_pyg_export" in statuses or "failed_dgl_export" in statuses:
        return "failed"
    if "skipped_missing_dependency" in statuses:
        return "skipped_missing_dependency"
    if "skipped_no_conditions" in statuses:
        return "skipped_no_conditions"
    return sorted(statuses)[0] if statuses else "unknown"


def safe_condition_name(condition: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in condition.strip())
    return safe or "condition"


def truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def canonical_reaction(reaction_id: object) -> str:
    text = str(reaction_id or "").strip()
    if not text:
        return ""
    return text if text.startswith("R_") else f"R_{text}"


def _to_float(value: object) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None


def _read_optional(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return read_csv_records(path)


def _read_json_optional(path: Path) -> dict[str, object]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))
