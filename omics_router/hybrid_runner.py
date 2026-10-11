"""Lightweight ML + GEM hybrid baseline runner.

This v0 runner intentionally avoids deep-learning dependencies. It combines
readiness-aware target priors with node-aligned omics features to create a
transparent baseline score for later MINN/GNN prototypes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .constraints import read_csv_records, write_csv, write_json


@dataclass(slots=True)
class HybridRunnerResult:
    """Summary returned after running the lightweight hybrid baseline."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]
    summary_rows: list[dict[str, object]]


def run_lightweight_hybrid_runner(
    package_dir: str | Path,
    output_dir: str | Path | None = None,
) -> HybridRunnerResult:
    """Score readiness-prior targets with node-aligned omics feature support."""

    package = Path(package_dir)
    output = Path(output_dir) if output_dir else package / "hybrid_results"
    output.mkdir(parents=True, exist_ok=True)
    files = hybrid_runner_files(output)
    minn_dir = package / "minn_export"

    target_priors = _read_optional(minn_dir / "minn_readiness_target_priors.csv")
    tensor_rows = _read_optional(minn_dir / "minn_omics_feature_tensor.csv")
    node_rows = _read_optional(minn_dir / "minn_graph_nodes.csv")
    edge_rows = _read_optional(minn_dir / "minn_graph_edges.csv")
    phenotype_labels = _read_optional(minn_dir / "minn_phenotype_labels.csv")
    target_scores, attribution_rows = build_hybrid_target_scores(target_priors, tensor_rows, edge_rows)
    loocv_rows = build_loocv_evaluation(target_scores, phenotype_labels)
    loocv_summary_rows = [summarize_loocv_evaluation(loocv_rows, phenotype_labels)]
    summary_rows = [summarize_hybrid_runner(target_priors, tensor_rows, target_scores, loocv_rows)]
    schema_doc = build_hybrid_runner_schema(files)
    metadata = build_hybrid_runner_metadata(
        package=package,
        files=files,
        target_priors=target_priors,
        tensor_rows=tensor_rows,
        node_rows=node_rows,
        edge_rows=edge_rows,
        phenotype_labels=phenotype_labels,
        target_scores=target_scores,
        attribution_rows=attribution_rows,
        loocv_rows=loocv_rows,
        loocv_summary=loocv_summary_rows[0],
    )

    write_csv(files["summary"], summary_rows)
    write_csv(files["target_scores"], target_scores)
    write_csv(files["feature_attributions"], attribution_rows)
    write_csv(files["loocv_evaluation"], loocv_rows)
    write_csv(files["loocv_summary"], loocv_summary_rows)
    write_json(files["schema"], schema_doc)
    write_json(files["metadata"], metadata)
    write_json(
        files["manifest"],
        {
            "schema_version": "0.2.0",
            "status": summary_rows[0]["status"],
            "package_dir": str(package),
            "target_prior_count": len(target_priors),
            "feature_tensor_row_count": len(tensor_rows),
            "graph_node_count": len(node_rows),
            "graph_edge_count": len(edge_rows),
            "target_score_count": len(target_scores),
            "feature_attribution_count": len(attribution_rows),
            "phenotype_label_count": len(phenotype_labels),
            "loocv_evaluation_count": len(loocv_rows),
            "schema_file": files["schema"],
            "metadata_file": files["metadata"],
            "files": files,
        },
    )
    return HybridRunnerResult(
        status="completed",
        output_dir=str(output),
        message=str(summary_rows[0]["guidance"]),
        files=files,
        summary_rows=summary_rows,
    )


def hybrid_runner_files(output: Path) -> dict[str, str]:
    return {
        "summary": str(output / "hybrid_runner_summary.csv"),
        "target_scores": str(output / "hybrid_target_scores.csv"),
        "feature_attributions": str(output / "hybrid_feature_attributions.csv"),
        "loocv_evaluation": str(output / "hybrid_loocv_evaluation.csv"),
        "loocv_summary": str(output / "hybrid_loocv_summary.csv"),
        "schema": str(output / "hybrid_runner_schema.json"),
        "metadata": str(output / "hybrid_runner_metadata.json"),
        "manifest": str(output / "hybrid_runner_manifest.json"),
    }


def build_hybrid_runner_schema(files: dict[str, str] | None = None) -> dict[str, object]:
    """Describe the CSV/JSON contract for downstream GNN-oriented runners."""

    files = files or {}
    return {
        "schema_version": "0.2.0",
        "name": "lightweight_hybrid_runner_v0",
        "description": (
            "A stable local contract for passing MINN-style graph, feature tensor, "
            "readiness priors, hybrid baseline scores, and LOOCV sanity-check rows "
            "to future PyTorch Geometric, DGL, or custom ML + GEM runners."
        ),
        "intended_use": (
            "Use node_id as the stable graph key, join condition-aware omics features "
            "and phenotype labels onto graph nodes, and treat hybrid scores as transparent "
            "baseline predictions rather than final biological truth."
        ),
        "tables": {
            "minn_graph_nodes": _table_schema(
                role="input",
                path_hint="minn_export/minn_graph_nodes.csv",
                description="Graph node table exported from the GEM and mapped omics entities.",
                primary_key=["node_id"],
                columns=[
                    _column("node_id", "string", "Stable graph node key used by all downstream joins."),
                    _column("node_type", "string", "Node class such as reaction, gene, or metabolite."),
                    _column("model_id", "string", "Original model identifier when available."),
                    _column("name", "string", "Human-readable node name."),
                    _column("compartment", "string", "Model compartment hint for metabolite/reaction nodes."),
                ],
            ),
            "minn_graph_edges": _table_schema(
                role="input",
                path_hint="minn_export/minn_graph_edges.csv",
                description="Graph edge table for reaction/metabolite/gene connectivity.",
                primary_key=["source_node_id", "target_node_id", "edge_type"],
                columns=[
                    _column("source_node_id", "string", "Source node_id for edge_index construction."),
                    _column("target_node_id", "string", "Target node_id for edge_index construction."),
                    _column("edge_type", "string", "Relationship type such as gene_to_reaction or metabolite_to_reaction."),
                    _column("stoichiometry", "number", "Stoichiometric coefficient when the edge represents a metabolite relation."),
                    _column("role", "string", "Edge role such as reactant, product, regulator, or evidence link."),
                ],
            ),
            "minn_omics_feature_tensor": _table_schema(
                role="input",
                path_hint="minn_export/minn_omics_feature_tensor.csv",
                description="Condition-aware node feature table produced from normalized omics evidence.",
                primary_key=["condition", "node_id", "feature_channel", "feature_id"],
                columns=[
                    _column("condition", "string", "Experimental or scenario condition; ALL means shared across conditions."),
                    _column("node_id", "string", "Graph node receiving the feature."),
                    _column("node_type", "string", "Node class for the feature row."),
                    _column("feature_channel", "string", "Feature channel such as tx_gene, tx_reaction, protein, flux, or metabolite."),
                    _column("feature_id", "string", "Stable feature identifier within the channel."),
                    _column("source", "string", "Input source or processing module that created the feature."),
                    _column("value", "number", "Numeric feature value used by the baseline scorer and future tensors."),
                    _column("status", "string", "Mapping or feature-generation status."),
                    _column("evidence", "string", "Optional evidence label propagated from upstream modules."),
                    _column("note", "string", "Optional human-readable processing note."),
                ],
            ),
            "minn_phenotype_labels": _table_schema(
                role="input",
                path_hint="minn_export/minn_phenotype_labels.csv",
                description="Condition-aware labels for supervised checks or later hybrid training.",
                primary_key=["condition", "label_type", "target_node_id"],
                columns=[
                    _column("condition", "string", "Condition matching feature tensor rows."),
                    _column("label_type", "string", "Label source such as measured_flux, growth_rate, or phenotype."),
                    _column("target_node_id", "string", "Graph node receiving the label."),
                    _column("target_id", "string", "Original target identifier when different from target_node_id."),
                    _column("value", "number", "Numeric label value for LOOCV or later supervised modeling."),
                    _column("unit", "string", "Optional label unit."),
                    _column("lower_ci", "number", "Optional lower confidence interval."),
                    _column("upper_ci", "number", "Optional upper confidence interval."),
                    _column("status", "string", "Label availability or mapping status."),
                ],
            ),
            "minn_readiness_target_priors": _table_schema(
                role="input",
                path_hint="minn_export/minn_readiness_target_priors.csv",
                description="Readiness-gated target priors from ML, production, UniProt, and enzyme evidence.",
                primary_key=["condition", "target_level", "target_id"],
                columns=[
                    _column("condition", "string", "Condition for the target prior."),
                    _column("target_level", "string", "Target type such as reaction, gene, or product."),
                    _column("target_id", "string", "Human-facing target identifier."),
                    _column("node_id", "string", "Graph node key used for feature joins."),
                    _column("recommended_action", "string", "Suggested action such as OE, KD, or KO."),
                    _column("candidate_target_label", "string", "Readiness-aware target class."),
                    _column("combined_target_prior_score", "number", "Combined prior score before feature support."),
                    _column("sample_weight", "number", "Training/sample weight derived from readiness evidence."),
                    _column("production_readiness_label", "string", "Production readiness gate label."),
                    _column("kcat_evidence_label", "string", "kcat evidence quality label propagated from production readiness."),
                    _column("kcat_evidence_tier", "string", "kcat source tier such as experimental, curated_database, or dlkcat_predicted."),
                    _column("kcat_conflict_flag", "string", "kcat candidate conflict flag when available."),
                    _column("training_role", "string", "Suggested role for future supervised training."),
                ],
            ),
            "hybrid_target_scores": _table_schema(
                role="output",
                path_hint=files.get("target_scores", "hybrid_results/hybrid_target_scores.csv"),
                description="Transparent baseline target scores combining priors with direct and neighbor feature support.",
                primary_key=["condition", "target_level", "target_id"],
                columns=[
                    _column("condition", "string", "Condition for the predicted target score."),
                    _column("target_level", "string", "Target class carried from the prior table."),
                    _column("target_id", "string", "Human-facing target identifier."),
                    _column("node_id", "string", "Graph node scored by the baseline."),
                    _column("hybrid_rank_score", "number", "Final baseline rank score after sample weighting."),
                    _column("prediction_label", "string", "Human-readable priority label for the baseline score."),
                    _column("direct_feature_count", "integer", "Number of condition-matched direct node features."),
                    _column("neighbor_feature_count", "integer", "Number of condition-matched neighboring node features."),
                    _column("kcat_quality_multiplier", "number", "Multiplier applied from kcat evidence quality."),
                    _column("top_feature_channels", "string", "Semicolon-delimited feature channels contributing most signal."),
                    _column("status", "string", "Score-generation status."),
                    _column("guidance", "string", "Interpretation note for the score row."),
                ],
            ),
            "hybrid_feature_attributions": _table_schema(
                role="output",
                path_hint=files.get("feature_attributions", "hybrid_results/hybrid_feature_attributions.csv"),
                description="Top direct and neighbor feature rows that contributed to each baseline target score.",
                primary_key=["condition", "target_id", "feature_node_id", "feature_id", "contribution_type"],
                columns=[
                    _column("condition", "string", "Condition for the target and feature."),
                    _column("target_id", "string", "Target receiving the feature contribution."),
                    _column("target_node_id", "string", "Graph node for the target."),
                    _column("feature_node_id", "string", "Graph node where the feature was observed."),
                    _column("feature_channel", "string", "Feature channel."),
                    _column("feature_value", "number", "Original feature value."),
                    _column("contribution_type", "string", "direct or neighbor contribution."),
                    _column("contribution_score", "number", "Absolute bounded signal multiplied by contribution weight."),
                ],
            ),
            "hybrid_loocv_evaluation": _table_schema(
                role="output",
                path_hint=files.get("loocv_evaluation", "hybrid_results/hybrid_loocv_evaluation.csv"),
                description="Leave-one-condition-out sanity check comparing score direction with held-out labels.",
                primary_key=["condition", "target_node_id", "label_type"],
                columns=[
                    _column("condition", "string", "Held-out condition."),
                    _column("target_node_id", "string", "Label and score graph node."),
                    _column("heldout_value", "number", "Observed label value in the held-out condition."),
                    _column("train_label_mean", "number", "Mean label value across other conditions."),
                    _column("observed_direction", "string", "Observed label direction against the training mean."),
                    _column("hybrid_rank_score", "number", "Baseline score for the held-out condition."),
                    _column("predicted_direction", "string", "Predicted direction from the hybrid score."),
                    _column("direction_match", "string", "match, mismatch, or inconclusive."),
                    _column("status", "string", "Evaluation status for the row."),
                ],
            ),
            "hybrid_runner_summary": _table_schema(
                role="output",
                path_hint=files.get("summary", "hybrid_results/hybrid_runner_summary.csv"),
                description="One-row baseline runner summary for UI and report display.",
                primary_key=["status"],
                columns=[
                    _column("status", "string", "Overall runner status."),
                    _column("target_prior_count", "integer", "Number of readiness target priors consumed."),
                    _column("feature_tensor_row_count", "integer", "Number of feature tensor rows consumed."),
                    _column("target_score_count", "integer", "Number of target scores produced."),
                    _column("loocv_evaluated_count", "integer", "Number of evaluable LOOCV rows."),
                    _column("loocv_direction_match_fraction", "number", "Fraction of evaluable LOOCV rows with matching direction."),
                    _column("guidance", "string", "Summary interpretation."),
                ],
            ),
            "hybrid_loocv_summary": _table_schema(
                role="output",
                path_hint=files.get("loocv_summary", "hybrid_results/hybrid_loocv_summary.csv"),
                description="One-row LOOCV sanity-check summary.",
                primary_key=["status"],
                columns=[
                    _column("status", "string", "LOOCV summary status."),
                    _column("phenotype_label_count", "integer", "Number of phenotype labels consumed."),
                    _column("loocv_row_count", "integer", "Number of LOOCV rows produced."),
                    _column("evaluated_count", "integer", "Number of evaluated LOOCV rows."),
                    _column("direction_match_count", "integer", "Rows where predicted and observed directions agree."),
                    _column("direction_mismatch_count", "integer", "Rows where predicted and observed directions disagree."),
                    _column("direction_match_fraction", "number", "Direction-match fraction among evaluated rows."),
                    _column("guidance", "string", "Summary interpretation."),
                ],
            ),
        },
        "downstream_contract": {
            "node_key": "node_id",
            "edge_source_key": "source_node_id",
            "edge_target_key": "target_node_id",
            "feature_join_keys": ["condition", "node_id"],
            "label_join_keys": ["condition", "target_node_id"],
            "target_prior_join_keys": ["condition", "node_id"],
            "pyg_node_index": "Map minn_graph_nodes.node_id to contiguous integer node indices.",
            "pyg_edge_index": "Map source_node_id and target_node_id through the node index mapping.",
            "feature_tensor": "Pivot feature_channel/feature_id values per condition and node_id.",
            "label_tensor": "Join labels by condition and target_node_id for supervised training or evaluation.",
        },
    }


def build_hybrid_runner_metadata(
    *,
    package: Path,
    files: dict[str, str],
    target_priors: list[dict[str, str]],
    tensor_rows: list[dict[str, str]],
    node_rows: list[dict[str, str]],
    edge_rows: list[dict[str, str]],
    phenotype_labels: list[dict[str, str]],
    target_scores: list[dict[str, object]],
    attribution_rows: list[dict[str, object]],
    loocv_rows: list[dict[str, object]],
    loocv_summary: dict[str, object],
) -> dict[str, object]:
    """Return compact row counts and category summaries for downstream runners."""

    all_condition_rows: list[dict[str, object]] = [
        *target_priors,
        *tensor_rows,
        *phenotype_labels,
        *target_scores,
    ]
    target_node_ids = {
        str(row.get("target_node_id") or row.get("node_id") or "")
        for row in [*phenotype_labels, *target_scores]
        if str(row.get("target_node_id") or row.get("node_id") or "")
    }
    return {
        "schema_version": "0.2.0",
        "status": hybrid_metadata_status(target_priors, tensor_rows, target_scores),
        "package_dir": str(package),
        "inputs": {
            "minn_readiness_target_priors": _table_metadata("minn_export/minn_readiness_target_priors.csv", target_priors),
            "minn_omics_feature_tensor": _table_metadata("minn_export/minn_omics_feature_tensor.csv", tensor_rows),
            "minn_graph_nodes": _table_metadata("minn_export/minn_graph_nodes.csv", node_rows),
            "minn_graph_edges": _table_metadata("minn_export/minn_graph_edges.csv", edge_rows),
            "minn_phenotype_labels": _table_metadata("minn_export/minn_phenotype_labels.csv", phenotype_labels),
        },
        "outputs": {
            "hybrid_runner_summary": _table_metadata(files["summary"], [], row_count=1),
            "hybrid_target_scores": _table_metadata(files["target_scores"], target_scores),
            "hybrid_feature_attributions": _table_metadata(files["feature_attributions"], attribution_rows),
            "hybrid_loocv_evaluation": _table_metadata(files["loocv_evaluation"], loocv_rows),
            "hybrid_loocv_summary": _table_metadata(files["loocv_summary"], [], row_count=1),
            "hybrid_runner_schema": _table_metadata(files["schema"], [], row_count=1),
            "hybrid_runner_metadata": _table_metadata(files["metadata"], [], row_count=1),
        },
        "graph": {
            "node_count": len(node_rows),
            "edge_count": len(edge_rows),
            "node_type_counts": _count_nonempty_by(node_rows, "node_type"),
            "edge_type_counts": _count_nonempty_by(edge_rows, "edge_type"),
        },
        "features": {
            "feature_tensor_row_count": len(tensor_rows),
            "condition_count": len(_unique_values(all_condition_rows, "condition")),
            "conditions": _unique_values(all_condition_rows, "condition"),
            "feature_channels": _unique_values(tensor_rows, "feature_channel"),
            "feature_channel_counts": _count_nonempty_by(tensor_rows, "feature_channel"),
            "node_type_counts": _count_nonempty_by(tensor_rows, "node_type"),
        },
        "labels": {
            "phenotype_label_count": len(phenotype_labels),
            "label_type_counts": _count_nonempty_by(phenotype_labels, "label_type"),
            "target_node_count": len(target_node_ids),
        },
        "target_priors": {
            "target_prior_count": len(target_priors),
            "target_level_counts": _count_nonempty_by(target_priors, "target_level"),
            "candidate_target_label_counts": _count_nonempty_by(target_priors, "candidate_target_label"),
            "production_readiness_label_counts": _count_nonempty_by(target_priors, "production_readiness_label"),
            "training_role_counts": _count_nonempty_by(target_priors, "training_role"),
            "kcat_evidence_label_counts": _count_nonempty_by(target_priors, "kcat_evidence_label"),
        },
        "scores": {
            "target_score_count": len(target_scores),
            "prediction_label_counts": _count_nonempty_by(target_scores, "prediction_label"),
            "feature_match_status_counts": _count_nonempty_by(target_scores, "feature_match_status"),
            "kcat_evidence_label_counts": _count_nonempty_by(target_scores, "kcat_evidence_label"),
            "blocked_count": _count_nonempty_by(target_scores, "prediction_label").get("blocked_by_readiness", 0),
            "score_fields": [
                "prior_score",
                "sample_weight",
                "kcat_quality_multiplier",
                "feature_support_score",
                "baseline_evidence_score",
                "hybrid_rank_score",
            ],
        },
        "loocv": {
            "row_count": len(loocv_rows),
            "status_counts": _count_nonempty_by(loocv_rows, "status"),
            "direction_match_counts": _count_nonempty_by(loocv_rows, "direction_match"),
            "summary": loocv_summary,
        },
        "downstream_contract": {
            "node_key": "node_id",
            "edge_source_key": "source_node_id",
            "edge_target_key": "target_node_id",
            "feature_join_keys": ["condition", "node_id"],
            "label_join_keys": ["condition", "target_node_id"],
            "target_join_keys": ["condition", "node_id"],
            "recommended_external_formats": ["PyTorch Geometric Data/HeteroData", "DGLGraph", "tabular baseline matrices"],
        },
    }


def build_hybrid_target_scores(
    target_priors: list[dict[str, str]],
    tensor_rows: list[dict[str, str]],
    edge_rows: list[dict[str, str]] | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Return baseline hybrid scores and per-feature attributions."""

    feature_index = index_tensor_features(tensor_rows)
    neighbor_index = index_graph_neighbors(edge_rows or [])
    score_rows: list[dict[str, object]] = []
    attribution_rows: list[dict[str, object]] = []
    for row in target_priors:
        node_id = str(row.get("node_id", ""))
        condition = str(row.get("condition", ""))
        direct_features, direct_match = select_features_for_condition(feature_index.get(node_id, []), condition)
        neighbor_features = []
        for neighbor in sorted(neighbor_index.get(node_id, set())):
            selected, _match = select_features_for_condition(feature_index.get(neighbor, []), condition)
            neighbor_features.extend(selected)

        direct_stats = feature_signal_stats(direct_features)
        neighbor_stats = feature_signal_stats(neighbor_features)
        feature_support_score = round(0.75 * direct_stats["mean_abs_signal"] + 0.25 * neighbor_stats["mean_abs_signal"], 6)
        prior_score = _to_float(row.get("combined_target_prior_score")) or _to_float(row.get("target_prior_score")) or 0.0
        sample_weight = _to_float(row.get("sample_weight")) or 0.0
        kcat_multiplier = kcat_quality_multiplier(row)
        baseline_evidence_score = round(clamp(0.65 * prior_score + 0.25 * direct_stats["mean_abs_signal"] + 0.10 * neighbor_stats["mean_abs_signal"], 0.0, 1.0), 6)
        hybrid_rank_score = round(clamp(baseline_evidence_score * sample_weight * kcat_multiplier, 0.0, 1.0), 6)
        prediction_label = classify_hybrid_prediction(row, hybrid_rank_score, direct_stats, neighbor_stats)
        score_rows.append(
            {
                "condition": condition,
                "target_level": row.get("target_level", ""),
                "target_id": row.get("target_id", ""),
                "node_id": node_id,
                "recommended_action": row.get("recommended_action", ""),
                "candidate_target_label": row.get("candidate_target_label", ""),
                "production_readiness_label": row.get("production_readiness_label", ""),
                "kcat_evidence_tier": row.get("kcat_evidence_tier", ""),
                "kcat_evidence_label": row.get("kcat_evidence_label", ""),
                "kcat_conflict_flag": row.get("kcat_conflict_flag", ""),
                "kcat_fold_range": row.get("kcat_fold_range", ""),
                "kcat_quality_multiplier": round(kcat_multiplier, 6),
                "prior_score": round(prior_score, 6),
                "sample_weight": round(sample_weight, 6),
                "direct_feature_count": direct_stats["count"],
                "neighbor_feature_count": neighbor_stats["count"],
                "direct_feature_signal": direct_stats["mean_abs_signal"],
                "neighbor_feature_signal": neighbor_stats["mean_abs_signal"],
                "feature_support_score": feature_support_score,
                "baseline_evidence_score": baseline_evidence_score,
                "hybrid_rank_score": hybrid_rank_score,
                "prediction_label": prediction_label,
                "feature_match_status": direct_match,
                "top_feature_channels": ";".join(top_feature_channels([*direct_features, *neighbor_features])),
                "training_role": row.get("training_role", ""),
                "status": "hybrid_score_available" if node_id else "missing_target_node",
                "guidance": hybrid_score_guidance(prediction_label),
            }
        )
        attribution_rows.extend(
            build_feature_attribution_rows(
                target=row,
                direct_features=direct_features,
                neighbor_features=neighbor_features,
            )
        )
    score_rows.sort(key=lambda item: (-float(item.get("hybrid_rank_score", 0)), str(item.get("condition", "")), str(item.get("target_id", ""))))
    attribution_rows.sort(
        key=lambda item: (
            str(item.get("condition", "")),
            str(item.get("target_id", "")),
            -float(item.get("contribution_score", 0)),
            str(item.get("feature_id", "")),
        )
    )
    return score_rows, attribution_rows


def index_tensor_features(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    index: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        node_id = str(row.get("node_id", ""))
        if node_id:
            index.setdefault(node_id, []).append(row)
    return index


def index_graph_neighbors(rows: list[dict[str, str]]) -> dict[str, set[str]]:
    index: dict[str, set[str]] = {}
    for row in rows:
        source = str(row.get("source_node_id", ""))
        target = str(row.get("target_node_id", ""))
        if source and target:
            index.setdefault(source, set()).add(target)
            index.setdefault(target, set()).add(source)
    return index


def select_features_for_condition(
    rows: list[dict[str, str]],
    condition: str,
) -> tuple[list[dict[str, str]], str]:
    if not rows:
        return [], "no_node_features"
    condition = str(condition or "")
    exact = [row for row in rows if str(row.get("condition", "")) == condition]
    all_condition = [row for row in rows if str(row.get("condition", "")) in {"ALL", ""}]
    if exact:
        return [*exact, *all_condition], "exact_condition"
    if all_condition:
        return all_condition, "all_condition"
    return rows, "condition_fallback_all"


def feature_signal_stats(rows: list[dict[str, str]]) -> dict[str, object]:
    signals = []
    for row in rows:
        value = _to_float(row.get("value"))
        if value is None:
            continue
        signals.append(bounded_signal(value))
    if not signals:
        return {
            "count": 0,
            "mean_abs_signal": 0.0,
            "mean_signed_signal": 0.0,
        }
    return {
        "count": len(signals),
        "mean_abs_signal": round(sum(abs(value) for value in signals) / len(signals), 6),
        "mean_signed_signal": round(sum(signals) / len(signals), 6),
    }


def build_feature_attribution_rows(
    *,
    target: dict[str, str],
    direct_features: list[dict[str, str]],
    neighbor_features: list[dict[str, str]],
    max_rows_per_type: int = 8,
) -> list[dict[str, object]]:
    rows = []
    rows.extend(
        one_feature_attribution(target, feature, "direct", 0.75)
        for feature in top_signal_features(direct_features, max_rows=max_rows_per_type)
    )
    rows.extend(
        one_feature_attribution(target, feature, "neighbor", 0.25)
        for feature in top_signal_features(neighbor_features, max_rows=max_rows_per_type)
    )
    return rows


def one_feature_attribution(
    target: dict[str, str],
    feature: dict[str, str],
    contribution_type: str,
    weight: float,
) -> dict[str, object]:
    value = _to_float(feature.get("value")) or 0.0
    signal = bounded_signal(value)
    return {
        "condition": target.get("condition", ""),
        "target_level": target.get("target_level", ""),
        "target_id": target.get("target_id", ""),
        "target_node_id": target.get("node_id", ""),
        "feature_node_id": feature.get("node_id", ""),
        "feature_id": feature.get("feature_id", ""),
        "feature_channel": feature.get("feature_channel", ""),
        "feature_value": feature.get("value", ""),
        "bounded_signal": round(signal, 6),
        "contribution_type": contribution_type,
        "contribution_weight": weight,
        "contribution_score": round(abs(signal) * weight, 6),
        "source": feature.get("source", ""),
        "status": "feature_attribution_available",
    }


def summarize_hybrid_runner(
    target_priors: list[dict[str, str]],
    tensor_rows: list[dict[str, str]],
    target_scores: list[dict[str, object]],
    loocv_rows: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    labels = _count_by(target_scores, "prediction_label")
    kcat_labels = _count_by(target_scores, "kcat_evidence_label")
    kcat_conflicts = _count_by(target_scores, "kcat_conflict_flag")
    loocv_rows = loocv_rows or []
    evaluated = [row for row in loocv_rows if row.get("status") == "evaluated"]
    direction_matches = sum(1 for row in evaluated if row.get("direction_match") == "match")
    if not target_priors:
        status = "skipped_no_target_priors"
    elif not tensor_rows:
        status = "completed_no_feature_tensor"
    else:
        status = "completed"
    return {
        "status": status,
        "target_prior_count": len(target_priors),
        "feature_tensor_row_count": len(tensor_rows),
        "target_score_count": len(target_scores),
        "direct_feature_supported_count": sum(1 for row in target_scores if _to_float(row.get("direct_feature_signal")) and _to_float(row.get("direct_feature_signal")) > 0),
        "neighbor_feature_supported_count": sum(1 for row in target_scores if _to_float(row.get("neighbor_feature_signal")) and _to_float(row.get("neighbor_feature_signal")) > 0),
        "high_priority_count": labels.get("high_priority_hybrid_candidate", 0),
        "medium_priority_count": labels.get("medium_priority_hybrid_candidate", 0),
        "exploratory_count": labels.get("exploratory_hybrid_candidate", 0),
        "blocked_count": labels.get("blocked_by_readiness", 0),
        "kcat_strong_score_count": kcat_labels.get("strong", 0),
        "kcat_caution_score_count": kcat_labels.get("caution", 0),
        "kcat_conflict_review_score_count": kcat_labels.get("conflict_review", 0),
        "kcat_spread_caution_score_count": kcat_conflicts.get("kcat_spread_caution", 0),
        "loocv_evaluation_count": len(loocv_rows),
        "loocv_evaluated_count": len(evaluated),
        "loocv_direction_match_fraction": round(direction_matches / len(evaluated), 6) if evaluated else "",
        "guidance": hybrid_runner_guidance(status, labels),
    }


def build_loocv_evaluation(
    target_scores: list[dict[str, object]],
    phenotype_labels: list[dict[str, str]],
) -> list[dict[str, object]]:
    """Compare held-out phenotype labels with condition-specific hybrid score direction."""

    score_index = index_scores_by_condition_node(target_scores)
    label_groups = group_numeric_labels_by_node(phenotype_labels)
    score_groups = group_numeric_scores_by_node(target_scores)
    rows: list[dict[str, object]] = []
    for label in phenotype_labels:
        condition = str(label.get("condition", ""))
        node_id = str(label.get("target_node_id") or canonical_reaction(label.get("target_id", "")))
        heldout_value = _to_float(label.get("value"))
        score = score_index.get((condition, node_id))
        if heldout_value is None:
            rows.append(loocv_skip_row(label, node_id, "non_numeric_label", "Phenotype label value is not numeric."))
            continue
        if score is None:
            rows.append(loocv_skip_row(label, node_id, "missing_hybrid_score", "No hybrid score matched this condition and target node."))
            continue

        train_label_values = [
            value
            for train_condition, value in label_groups.get(node_id, [])
            if train_condition != condition
        ]
        if not train_label_values:
            rows.append(
                loocv_skip_row(
                    label,
                    node_id,
                    "insufficient_holdout_labels",
                    "No other condition labels were available for leave-one-condition-out comparison.",
                    score=score,
                )
            )
            continue

        train_score_values = [
            value
            for train_condition, value in score_groups.get(node_id, [])
            if train_condition != condition
        ]
        train_label_mean = mean(train_label_values)
        observed_delta = heldout_value - train_label_mean
        observed_direction = direction_from_delta(observed_delta, tolerance=max(abs(train_label_mean) * 0.05, 1e-9))
        hybrid_score = _to_float(score.get("hybrid_rank_score")) or 0.0
        if train_score_values:
            train_score_mean = mean(train_score_values)
            predicted_delta = hybrid_score - train_score_mean
            predicted_direction = direction_from_delta(predicted_delta, tolerance=0.05)
            prediction_baseline = "other_condition_score_mean"
        else:
            train_score_mean = None
            predicted_delta = hybrid_score - 0.5
            predicted_direction = direction_from_score_threshold(hybrid_score)
            prediction_baseline = "absolute_score_threshold"
        direction_match = compare_directions(observed_direction, predicted_direction)
        status = "evaluated" if direction_match in {"match", "mismatch"} else "direction_inconclusive"
        rows.append(
            {
                "condition": condition,
                "target_node_id": node_id,
                "target_id": label.get("target_id", ""),
                "label_type": label.get("label_type", ""),
                "heldout_value": round(heldout_value, 6),
                "train_label_mean": round(train_label_mean, 6),
                "train_label_count": len(train_label_values),
                "observed_delta": round(observed_delta, 6),
                "observed_direction": observed_direction,
                "hybrid_rank_score": round(hybrid_score, 6),
                "train_score_mean": round(train_score_mean, 6) if train_score_mean is not None else "",
                "train_score_count": len(train_score_values),
                "predicted_delta": round(predicted_delta, 6),
                "predicted_direction": predicted_direction,
                "prediction_baseline": prediction_baseline,
                "direction_match": direction_match,
                "prediction_label": score.get("prediction_label", ""),
                "production_readiness_label": score.get("production_readiness_label", ""),
                "status": status,
                "guidance": loocv_guidance(status, direction_match),
            }
        )
    rows.sort(key=lambda row: (str(row.get("status", "")), str(row.get("condition", "")), str(row.get("target_node_id", ""))))
    return rows


def summarize_loocv_evaluation(
    loocv_rows: list[dict[str, object]],
    phenotype_labels: list[dict[str, str]],
) -> dict[str, object]:
    evaluated = [row for row in loocv_rows if row.get("status") == "evaluated"]
    matches = sum(1 for row in evaluated if row.get("direction_match") == "match")
    mismatches = sum(1 for row in evaluated if row.get("direction_match") == "mismatch")
    status_counts = _count_by(loocv_rows, "status")
    if not phenotype_labels:
        status = "skipped_no_phenotype_labels"
    elif not evaluated:
        status = "completed_no_evaluable_holdouts"
    else:
        status = "completed"
    return {
        "status": status,
        "phenotype_label_count": len(phenotype_labels),
        "loocv_row_count": len(loocv_rows),
        "evaluated_count": len(evaluated),
        "direction_match_count": matches,
        "direction_mismatch_count": mismatches,
        "direction_match_fraction": round(matches / len(evaluated), 6) if evaluated else "",
        "inconclusive_count": status_counts.get("direction_inconclusive", 0),
        "missing_hybrid_score_count": status_counts.get("missing_hybrid_score", 0),
        "insufficient_holdout_label_count": status_counts.get("insufficient_holdout_labels", 0),
        "guidance": loocv_summary_guidance(status, matches, mismatches),
    }


def classify_hybrid_prediction(
    row: dict[str, str],
    hybrid_rank_score: float,
    direct_stats: dict[str, object],
    neighbor_stats: dict[str, object],
) -> str:
    if (
        str(row.get("production_readiness_label", "")) == "review_required"
        or str(row.get("kcat_evidence_label", "")) == "conflict_review"
        or (_to_float(row.get("sample_weight")) or 0.0) <= 0
    ):
        return "blocked_by_readiness"
    feature_count = int(direct_stats.get("count") or 0) + int(neighbor_stats.get("count") or 0)
    if str(row.get("kcat_evidence_label", "")) == "caution" and hybrid_rank_score >= 0.75:
        return "medium_priority_hybrid_candidate"
    if hybrid_rank_score >= 0.75 and feature_count:
        return "high_priority_hybrid_candidate"
    if hybrid_rank_score >= 0.45:
        return "medium_priority_hybrid_candidate"
    if hybrid_rank_score > 0:
        return "exploratory_hybrid_candidate"
    return "insufficient_hybrid_evidence"


def kcat_quality_multiplier(row: dict[str, str]) -> float:
    label = str(row.get("kcat_evidence_label", ""))
    if label == "strong":
        return 1.03
    if label == "caution":
        return 0.85
    if label == "conflict_review":
        return 0.0
    return 1.0


def hybrid_score_guidance(label: str) -> str:
    if label == "high_priority_hybrid_candidate":
        return "Strong readiness prior with omics feature support; suitable as a high-priority hybrid baseline candidate."
    if label == "medium_priority_hybrid_candidate":
        return "Moderate hybrid support; review feature attributions before downstream modeling."
    if label == "exploratory_hybrid_candidate":
        return "Low-weight or sparse-feature candidate; keep as exploratory evidence."
    if label == "blocked_by_readiness":
        return "Readiness gate blocks this candidate from training until conflicts are reviewed."
    return "Insufficient hybrid evidence for ranking."


def hybrid_runner_guidance(status: str, labels: dict[str, int]) -> str:
    if status == "skipped_no_target_priors":
        return "No readiness-aware target priors were available; run readiness hybrid export first."
    if status == "completed_no_feature_tensor":
        return "Target priors were scored without omics feature tensor support."
    if labels.get("high_priority_hybrid_candidate", 0):
        return "Hybrid baseline scores are available with high-priority candidates."
    return "Hybrid baseline scores are available; current candidates are moderate, exploratory, or blocked."


def loocv_skip_row(
    label: dict[str, str],
    node_id: str,
    status: str,
    guidance: str,
    score: dict[str, object] | None = None,
) -> dict[str, object]:
    score = score or {}
    return {
        "condition": label.get("condition", ""),
        "target_node_id": node_id,
        "target_id": label.get("target_id", ""),
        "label_type": label.get("label_type", ""),
        "heldout_value": label.get("value", ""),
        "train_label_mean": "",
        "train_label_count": 0,
        "observed_delta": "",
        "observed_direction": "",
        "hybrid_rank_score": score.get("hybrid_rank_score", ""),
        "train_score_mean": "",
        "train_score_count": 0,
        "predicted_delta": "",
        "predicted_direction": "",
        "prediction_baseline": "",
        "direction_match": "",
        "prediction_label": score.get("prediction_label", ""),
        "production_readiness_label": score.get("production_readiness_label", ""),
        "status": status,
        "guidance": guidance,
    }


def index_scores_by_condition_node(rows: list[dict[str, object]]) -> dict[tuple[str, str], dict[str, object]]:
    index: dict[tuple[str, str], dict[str, object]] = {}
    for row in rows:
        condition = str(row.get("condition", ""))
        node_id = str(row.get("node_id", ""))
        if condition and node_id:
            index[(condition, node_id)] = row
    return index


def group_numeric_labels_by_node(rows: list[dict[str, str]]) -> dict[str, list[tuple[str, float]]]:
    grouped: dict[str, list[tuple[str, float]]] = {}
    for row in rows:
        value = _to_float(row.get("value"))
        node_id = str(row.get("target_node_id") or canonical_reaction(row.get("target_id", "")))
        condition = str(row.get("condition", ""))
        if value is not None and node_id and condition:
            grouped.setdefault(node_id, []).append((condition, value))
    return grouped


def group_numeric_scores_by_node(rows: list[dict[str, object]]) -> dict[str, list[tuple[str, float]]]:
    grouped: dict[str, list[tuple[str, float]]] = {}
    for row in rows:
        value = _to_float(row.get("hybrid_rank_score"))
        node_id = str(row.get("node_id", ""))
        condition = str(row.get("condition", ""))
        if value is not None and node_id and condition:
            grouped.setdefault(node_id, []).append((condition, value))
    return grouped


def direction_from_delta(delta: float, tolerance: float) -> str:
    if delta > tolerance:
        return "higher_than_training_mean"
    if delta < -tolerance:
        return "lower_than_training_mean"
    return "near_training_mean"


def direction_from_score_threshold(score: float) -> str:
    if score >= 0.55:
        return "higher_than_training_mean"
    if score <= 0.25:
        return "lower_than_training_mean"
    return "near_training_mean"


def compare_directions(observed: str, predicted: str) -> str:
    if observed == "near_training_mean" or predicted == "near_training_mean":
        return "inconclusive"
    return "match" if observed == predicted else "mismatch"


def loocv_guidance(status: str, direction_match: str) -> str:
    if status == "evaluated" and direction_match == "match":
        return "Hybrid score direction agrees with the held-out phenotype direction."
    if status == "evaluated" and direction_match == "mismatch":
        return "Hybrid score direction disagrees with the held-out phenotype direction; inspect feature attribution."
    if status == "direction_inconclusive":
        return "Held-out phenotype or hybrid score was near its comparison baseline."
    return "Holdout row was not evaluable."


def loocv_summary_guidance(status: str, matches: int, mismatches: int) -> str:
    if status == "skipped_no_phenotype_labels":
        return "No phenotype labels were available for leave-one-condition-out evaluation."
    if status == "completed_no_evaluable_holdouts":
        return "Phenotype labels were available, but no label had both a matching hybrid score and another condition baseline."
    if mismatches:
        return f"LOOCV sanity check found {mismatches} direction mismatches; inspect feature attributions before trusting the baseline."
    return f"LOOCV sanity check completed with {matches} direction matches."


def mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def canonical_reaction(reaction_id: object) -> str:
    text = str(reaction_id or "").strip()
    if not text:
        return ""
    return text if text.startswith("R_") else f"R_{text}"


def top_signal_features(rows: list[dict[str, str]], max_rows: int) -> list[dict[str, str]]:
    return sorted(
        rows,
        key=lambda row: (-abs(bounded_signal(_to_float(row.get("value")) or 0.0)), str(row.get("feature_id", ""))),
    )[:max_rows]


def top_feature_channels(rows: list[dict[str, str]], max_channels: int = 5) -> list[str]:
    scores: dict[str, float] = {}
    for row in rows:
        channel = str(row.get("feature_channel", ""))
        value = _to_float(row.get("value"))
        if not channel or value is None:
            continue
        scores[channel] = scores.get(channel, 0.0) + abs(bounded_signal(value))
    return [
        channel
        for channel, _score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:max_channels]
    ]


def bounded_signal(value: float) -> float:
    return value / (abs(value) + 1.0)


def clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _count_by(rows: list[dict[str, object]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, ""))
        counts[value] = counts.get(value, 0) + 1
    return counts


def _count_nonempty_by(rows: list[dict[str, object]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key, "")).strip()
        if value:
            counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _unique_values(rows: list[dict[str, object]], key: str) -> list[str]:
    return sorted({str(row.get(key, "")).strip() for row in rows if str(row.get(key, "")).strip()})


def _column(name: str, kind: str, description: str) -> dict[str, str]:
    return {
        "name": name,
        "type": kind,
        "description": description,
    }


def _table_schema(
    *,
    role: str,
    path_hint: str,
    description: str,
    primary_key: list[str],
    columns: list[dict[str, str]],
) -> dict[str, object]:
    return {
        "role": role,
        "path_hint": path_hint,
        "description": description,
        "primary_key": primary_key,
        "columns": columns,
    }


def _table_metadata(
    path: str | Path,
    rows: list[dict[str, object]],
    row_count: int | None = None,
) -> dict[str, object]:
    return {
        "path": str(path),
        "row_count": len(rows) if row_count is None else row_count,
    }


def hybrid_metadata_status(
    target_priors: list[dict[str, str]],
    tensor_rows: list[dict[str, str]],
    target_scores: list[dict[str, object]],
) -> str:
    if not target_priors:
        return "skipped_no_target_priors"
    if not target_scores:
        return "completed_no_scores"
    if not tensor_rows:
        return "completed_no_feature_tensor"
    return "completed"


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
