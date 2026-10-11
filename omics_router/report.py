"""Static HTML reporting for COBRApy result tables."""

from __future__ import annotations

import html
import json
from pathlib import Path

from .constraints import read_csv_records


def build_cobra_report(
    results_dir: str | Path,
    output_path: str | Path | None = None,
    title: str = "E. coli COBRA Report",
) -> Path:
    """Build a compact HTML report from COBRA runner outputs."""

    results = Path(results_dir)
    output = Path(output_path) if output_path else results / "report.html"

    fba_summary = _read_optional(results / "fba_summary.csv")
    flux_summary = _read_optional(results / "flux_validation_summary.csv")
    pfba_summary = _read_optional(results / "pfba_validation_summary.csv")
    fva_summary = _read_optional(results / "target_fva_summary.csv")
    flux_comparison = _read_optional(results / "flux_validation_comparison.csv")
    pfba_comparison = _read_optional(results / "pfba_validation_comparison.csv")
    constraints_dir = results.parent / "generated_constraints"
    pipeline_dir = results.parent / "pipeline_results"
    workflow_dir = results.parent / "workflow_results"
    id_mapping_dir = results.parent / "id_mapping_results"
    normalized_inputs_dir = results.parent / "normalized_inputs"
    ml_results_dir = results.parent / "ml_results"
    minn_export_dir = results.parent / "minn_export"
    context_dir = results.parent / "context_results"
    troppo_dir = results.parent / "troppo_results"
    troppo_method_dir = results.parent / "troppo_method_results"
    transcriptomics_flux_dir = results.parent / "transcriptomics_flux_results"
    evidence_mode_dir = results.parent / "evidence_mode_results"
    interpretation_dir = results.parent / "interpretation_results"
    model_qc_dir = results.parent / "model_qc_results"
    uniprot_model_check_dir = results.parent / "uniprot_model_check"
    production_results_dir = results.parent / "production_results"
    memote_dir = results.parent / "memote_results"
    enzyme_dir = results.parent / "enzyme_results"
    gecko_dir = results.parent / "gecko_package"
    gecko_run_dir = results.parent / "gecko_run_results"
    pytfa_dir = results.parent / "pytfa_package"
    pytfa_run_dir = results.parent / "pytfa_run_results"
    pipeline_steps = _read_optional(pipeline_dir / "pipeline_steps.csv")
    pipeline_backend_status = _read_optional(pipeline_dir / "pipeline_backend_status.csv")
    custom_input_overview = _read_optional(pipeline_dir / "custom_input_overview.csv")
    workflow_selection = _read_optional(workflow_dir / "workflow_selection.csv")
    context_model_artifacts = _read_optional(workflow_dir / "context_model_artifact_summary.csv")
    model_variant_registry = _read_optional(workflow_dir / "model_variant_registry.csv")
    analysis_variant_context = _read_optional(workflow_dir / "analysis_variant_context.csv")
    variant_fba_summary = _read_variant_fba_results(results.parent / "variant_cobra_results")
    variant_comparison_dir = results.parent / "variant_comparison"
    variant_comparison_summary = _read_optional(variant_comparison_dir / "variant_comparison_summary.csv")
    variant_flux_comparison = _read_optional(variant_comparison_dir / "variant_flux_comparison.csv")
    variant_evidence_quality = _read_optional(variant_comparison_dir / "variant_evidence_quality.csv")
    id_mapping_summary = _read_optional(id_mapping_dir / "id_mapping_summary.csv")
    id_mapping_detail = _read_optional(id_mapping_dir / "id_mapping_detail.csv")
    normalized_input_map = _read_optional(normalized_inputs_dir / "normalized_input_map.csv")
    ml_feature_summary = _read_optional(ml_results_dir / "ml_feature_summary.csv")
    ml_feature_long = _read_optional(ml_results_dir / "ml_feature_long.csv")
    ml_analysis_summary = _read_optional(ml_results_dir / "ml_analysis_summary.csv")
    ml_correlations = _read_optional(ml_results_dir / "feature_phenotype_correlations.csv")
    ml_prior_scores = _read_optional(ml_results_dir / "ml_prior_scores.csv")
    ml_diagnostic_summary = _read_optional(ml_results_dir / "ml_diagnostic_summary.csv")
    ml_pca_scores = _read_optional(ml_results_dir / "ml_pca_scores.csv")
    ml_condition_clusters = _read_optional(ml_results_dir / "ml_condition_clusters.csv")
    ml_lasso_lite = _read_optional(ml_results_dir / "ml_lasso_lite_coefficients.csv")
    minn_summary = _read_optional(minn_export_dir / "minn_export_summary.csv")
    minn_nodes = _read_optional(minn_export_dir / "minn_graph_nodes.csv")
    minn_edges = _read_optional(minn_export_dir / "minn_graph_edges.csv")
    minn_tensor = _read_optional(minn_export_dir / "minn_omics_feature_tensor.csv")
    minn_labels = _read_optional(minn_export_dir / "minn_phenotype_labels.csv")
    minn_readiness_summary = _read_optional(minn_export_dir / "minn_readiness_summary.csv")
    minn_readiness_priors = _read_optional(minn_export_dir / "minn_readiness_target_priors.csv")
    minn_readiness_weights = _read_optional(minn_export_dir / "minn_readiness_sample_weights.csv")
    hybrid_results_dir = results.parent / "hybrid_results"
    hybrid_summary = _read_optional(hybrid_results_dir / "hybrid_runner_summary.csv")
    hybrid_target_scores = _read_optional(hybrid_results_dir / "hybrid_target_scores.csv")
    hybrid_feature_attributions = _read_optional(hybrid_results_dir / "hybrid_feature_attributions.csv")
    hybrid_loocv_summary = _read_optional(hybrid_results_dir / "hybrid_loocv_summary.csv")
    hybrid_loocv_evaluation = _read_optional(hybrid_results_dir / "hybrid_loocv_evaluation.csv")
    hybrid_schema = _read_json_optional(hybrid_results_dir / "hybrid_runner_schema.json")
    hybrid_metadata = _read_json_optional(hybrid_results_dir / "hybrid_runner_metadata.json")
    hybrid_adapter_dir = results.parent / "hybrid_adapter_results"
    hybrid_adapter_summary = _read_optional(hybrid_adapter_dir / "hybrid_graph_adapter_summary.csv")
    hybrid_adapter_flags = _read_optional(hybrid_adapter_dir / "hybrid_graph_adapter_validation_flags.csv")
    hybrid_adapter_targets = _read_optional(hybrid_adapter_dir / "hybrid_graph_adapter_targets.csv")
    hybrid_adapter_payload = _read_json_optional(hybrid_adapter_dir / "hybrid_graph_adapter_payload_stub.json")
    hybrid_adapter_dense_summary = _read_optional(hybrid_adapter_dir / "hybrid_graph_adapter_dense_feature_summary.csv")
    hybrid_adapter_dense_vocabulary = _read_optional(hybrid_adapter_dir / "hybrid_graph_adapter_dense_feature_vocabulary.csv")
    hybrid_adapter_dense_matrix = _read_optional(hybrid_adapter_dir / "hybrid_graph_adapter_dense_feature_matrix.csv")
    hybrid_adapter_pyg_summary = _read_optional(hybrid_adapter_dir / "hybrid_graph_adapter_pyg_summary.csv")
    hybrid_adapter_condition_pyg_summary = _read_optional(hybrid_adapter_dir / "hybrid_graph_adapter_condition_pyg_summary.csv")
    hybrid_adapter_dgl_summary = _read_optional(hybrid_adapter_dir / "hybrid_graph_adapter_dgl_summary.csv")
    hybrid_adapter_condition_dgl_summary = _read_optional(hybrid_adapter_dir / "hybrid_graph_adapter_condition_dgl_summary.csv")
    relative_protein_evidence = _read_optional(constraints_dir / "relative_protein_reaction_evidence.csv")
    multi_omics_conflict_summary = _read_optional(constraints_dir / "multi_omics_conflict_summary.csv")
    multi_omics_conflict_detail = _read_optional(constraints_dir / "multi_omics_conflict_detail.csv")
    evidence_mode_summary = _read_optional(evidence_mode_dir / "evidence_mode_summary.csv")
    evidence_mode_delta_summary = _read_optional(evidence_mode_dir / "evidence_mode_delta_summary.csv")
    evidence_mode_reaction_deltas = _read_optional(evidence_mode_dir / "evidence_mode_reaction_deltas.csv")
    evidence_mode_recommendations = _read_optional(evidence_mode_dir / "evidence_mode_recommendations.csv")
    condition_interpretation = _read_optional(interpretation_dir / "condition_interpretation_summary.csv")
    condition_recommendations = _read_optional(interpretation_dir / "condition_interpretation_recommendations.csv")
    consensus_context_summary = _read_optional(constraints_dir / "consensus_context_policy_summary.csv")
    consensus_delete_candidates = _read_optional(constraints_dir / "consensus_context_delete_candidates.csv")
    context_policy_summary = _read_optional(constraints_dir / "context_policy_summary.csv")
    context_feasibility = _read_optional(context_dir / "context_feasibility_summary.csv")
    context_knockouts = _read_optional(context_dir / "context_knockouts.csv")
    model_qc_summary = _read_optional(model_qc_dir / "model_qc_summary.csv")
    model_qc_recommendations = _read_optional(model_qc_dir / "model_qc_recommendations.csv")
    model_qc_compartments = _read_optional(model_qc_dir / "model_qc_compartments.csv")
    uniprot_check_summary = _read_optional(uniprot_model_check_dir / "uniprot_model_check_summary.csv")
    uniprot_gene_coverage = _read_optional(uniprot_model_check_dir / "uniprot_gene_coverage.csv")
    gpr_consistency_flags = _read_optional(uniprot_model_check_dir / "gpr_consistency_flags.csv")
    reaction_annotation_flags = _read_optional(uniprot_model_check_dir / "reaction_annotation_flags.csv")
    uniprot_enrichment_summary = _read_optional(uniprot_model_check_dir / "uniprot_enrichment_summary.csv")
    uniprot_enrichment_records = _read_optional(uniprot_model_check_dir / "uniprot_enrichment_records.csv")
    dlkcat_dir = results.parent / "dlkcat_results"
    dlkcat_summary = _read_optional(dlkcat_dir / "dlkcat_bridge_summary.csv")
    dlkcat_external_summary = _read_optional(dlkcat_dir / "dlkcat_external_run_summary.csv")
    dlkcat_input_coverage = _read_optional(dlkcat_dir / "dlkcat_input_coverage.csv")
    dlkcat_predictions = _read_optional(dlkcat_dir / "dlkcat_prediction_normalized.csv")
    dlkcat_kcat_priors = _read_optional(dlkcat_dir / "dlkcat_reaction_kcat_priors.csv")
    kcat_prior_merge_summary = _read_optional(constraints_dir / "kcat_prior_merge_summary.csv")
    kcat_prior_candidates = _read_optional(constraints_dir / "kcat_prior_candidates.csv")
    kcat_conflict_flags = _read_optional(constraints_dir / "kcat_conflict_flags.csv")
    kcat_priors = _read_optional(constraints_dir / "kcat_priors.csv")
    memote_run_summary = _read_optional(memote_dir / "memote_external_run_summary.csv")
    enzyme_summary = _read_optional(enzyme_dir / "enzyme_qc_summary.csv")
    enzyme_recommendations = _read_optional(enzyme_dir / "enzyme_qc_recommendations.csv")
    enzyme_capacity = _read_optional(enzyme_dir / "reaction_enzyme_capacity.csv")
    gecko_summary = _read_optional(gecko_dir / "gecko_export_summary.csv")
    gecko_run_summary = _read_optional(gecko_run_dir / "gecko_external_run_summary.csv")
    thermo_summary = _read_optional(pytfa_dir / "thermo_qc_summary.csv")
    thermo_recommendations = _read_optional(pytfa_dir / "thermo_qc_recommendations.csv")
    pytfa_summary = _read_optional(pytfa_dir / "pytfa_export_summary.csv")
    pytfa_run_summary = _read_optional(pytfa_run_dir / "pytfa_external_run_summary.csv")
    troppo_summary = _read_optional(troppo_dir / "troppo_fastcore_summary.csv")
    troppo_selected = _read_optional(troppo_dir / "troppo_fastcore_selected_reactions.csv")
    omics_quality = _read_optional(troppo_dir / "omics_signal_quality.csv")
    omics_recommendations = _read_optional(troppo_dir / "omics_signal_recommendations.csv")
    troppo_method_summary = _read_optional(troppo_method_dir / "troppo_method_input_summary.csv")
    troppo_method_matrix = _read_optional(troppo_method_dir / "troppo_method_run_matrix.csv")
    eflux_summary = _read_optional(transcriptomics_flux_dir / "eflux_summary.csv")
    eflux_validation_summary = _read_optional(transcriptomics_flux_dir / "eflux_flux_validation_summary.csv")
    delta_fba_summary = _read_optional(transcriptomics_flux_dir / "delta_fba_summary.csv")
    production_summary = _read_optional(production_results_dir / "production_analysis_summary.csv")
    production_envelope = _read_optional(production_results_dir / "production_envelope.csv")
    production_target_ranking = _read_optional(production_results_dir / "production_target_ranking.csv")
    fseof_lite_targets = _read_optional(production_results_dir / "fseof_lite_reaction_targets.csv")
    production_design_targets = _read_optional(production_results_dir / "production_design_targets.csv")
    production_gene_targets = _read_optional(production_results_dir / "production_gene_targets.csv")
    production_gecko_summary = _read_optional(production_results_dir / "production_gecko_comparison_summary.csv")
    production_gecko_target_comparison = _read_optional(production_results_dir / "production_gecko_target_comparison.csv")
    production_gecko_design_comparison = _read_optional(production_results_dir / "production_gecko_design_comparison.csv")
    production_readiness_summary = _read_optional(production_results_dir / "production_readiness_summary.csv")
    production_target_readiness = _read_optional(production_results_dir / "production_target_readiness.csv")
    production_design_readiness = _read_optional(production_results_dir / "production_design_readiness.csv")
    production_gene_readiness = _read_optional(production_results_dir / "production_gene_readiness.csv")

    html_text = _render_report(
        title=title,
        fba_summary=fba_summary,
        flux_summary=flux_summary,
        pfba_summary=pfba_summary,
        fva_summary=fva_summary,
        flux_comparison=flux_comparison,
        pfba_comparison=pfba_comparison,
        pipeline_steps=pipeline_steps,
        pipeline_backend_status=pipeline_backend_status,
        custom_input_overview=custom_input_overview,
        workflow_selection=workflow_selection,
        context_model_artifacts=context_model_artifacts,
        model_variant_registry=model_variant_registry,
        analysis_variant_context=analysis_variant_context,
        variant_fba_summary=variant_fba_summary,
        variant_comparison_summary=variant_comparison_summary,
        variant_flux_comparison=variant_flux_comparison,
        variant_evidence_quality=variant_evidence_quality,
        id_mapping_summary=id_mapping_summary,
        id_mapping_detail=id_mapping_detail,
        normalized_input_map=normalized_input_map,
        ml_feature_summary=ml_feature_summary,
        ml_feature_long=ml_feature_long,
        ml_analysis_summary=ml_analysis_summary,
        ml_correlations=ml_correlations,
        ml_prior_scores=ml_prior_scores,
        ml_diagnostic_summary=ml_diagnostic_summary,
        ml_pca_scores=ml_pca_scores,
        ml_condition_clusters=ml_condition_clusters,
        ml_lasso_lite=ml_lasso_lite,
        minn_summary=minn_summary,
        minn_nodes=minn_nodes,
        minn_edges=minn_edges,
        minn_tensor=minn_tensor,
        minn_labels=minn_labels,
        minn_readiness_summary=minn_readiness_summary,
        minn_readiness_priors=minn_readiness_priors,
        minn_readiness_weights=minn_readiness_weights,
        hybrid_summary=hybrid_summary,
        hybrid_target_scores=hybrid_target_scores,
        hybrid_feature_attributions=hybrid_feature_attributions,
        hybrid_loocv_summary=hybrid_loocv_summary,
        hybrid_loocv_evaluation=hybrid_loocv_evaluation,
        hybrid_schema=hybrid_schema,
        hybrid_metadata=hybrid_metadata,
        hybrid_adapter_summary=hybrid_adapter_summary,
        hybrid_adapter_flags=hybrid_adapter_flags,
        hybrid_adapter_targets=hybrid_adapter_targets,
        hybrid_adapter_payload=hybrid_adapter_payload,
        hybrid_adapter_dense_summary=hybrid_adapter_dense_summary,
        hybrid_adapter_dense_vocabulary=hybrid_adapter_dense_vocabulary,
        hybrid_adapter_dense_matrix=hybrid_adapter_dense_matrix,
        hybrid_adapter_pyg_summary=hybrid_adapter_pyg_summary,
        hybrid_adapter_condition_pyg_summary=hybrid_adapter_condition_pyg_summary,
        hybrid_adapter_dgl_summary=hybrid_adapter_dgl_summary,
        hybrid_adapter_condition_dgl_summary=hybrid_adapter_condition_dgl_summary,
        relative_protein_evidence=relative_protein_evidence,
        multi_omics_conflict_summary=multi_omics_conflict_summary,
        multi_omics_conflict_detail=multi_omics_conflict_detail,
        evidence_mode_summary=evidence_mode_summary,
        evidence_mode_delta_summary=evidence_mode_delta_summary,
        evidence_mode_reaction_deltas=evidence_mode_reaction_deltas,
        evidence_mode_recommendations=evidence_mode_recommendations,
        condition_interpretation=condition_interpretation,
        condition_recommendations=condition_recommendations,
        consensus_context_summary=consensus_context_summary,
        consensus_delete_candidates=consensus_delete_candidates,
        context_policy_summary=context_policy_summary,
        context_feasibility=context_feasibility,
        context_knockouts=context_knockouts,
        model_qc_summary=model_qc_summary,
        model_qc_recommendations=model_qc_recommendations,
        model_qc_compartments=model_qc_compartments,
        uniprot_check_summary=uniprot_check_summary,
        uniprot_gene_coverage=uniprot_gene_coverage,
        gpr_consistency_flags=gpr_consistency_flags,
        reaction_annotation_flags=reaction_annotation_flags,
        uniprot_enrichment_summary=uniprot_enrichment_summary,
        uniprot_enrichment_records=uniprot_enrichment_records,
        dlkcat_summary=dlkcat_summary,
        dlkcat_external_summary=dlkcat_external_summary,
        dlkcat_input_coverage=dlkcat_input_coverage,
        dlkcat_predictions=dlkcat_predictions,
        dlkcat_kcat_priors=dlkcat_kcat_priors,
        kcat_prior_merge_summary=kcat_prior_merge_summary,
        kcat_prior_candidates=kcat_prior_candidates,
        kcat_conflict_flags=kcat_conflict_flags,
        kcat_priors=kcat_priors,
        memote_run_summary=memote_run_summary,
        enzyme_summary=enzyme_summary,
        enzyme_recommendations=enzyme_recommendations,
        enzyme_capacity=enzyme_capacity,
        gecko_summary=gecko_summary,
        gecko_run_summary=gecko_run_summary,
        thermo_summary=thermo_summary,
        thermo_recommendations=thermo_recommendations,
        pytfa_summary=pytfa_summary,
        pytfa_run_summary=pytfa_run_summary,
        troppo_summary=troppo_summary,
        troppo_selected=troppo_selected,
        omics_quality=omics_quality,
        omics_recommendations=omics_recommendations,
        troppo_method_summary=troppo_method_summary,
        troppo_method_matrix=troppo_method_matrix,
        eflux_summary=eflux_summary,
        eflux_validation_summary=eflux_validation_summary,
        delta_fba_summary=delta_fba_summary,
        production_summary=production_summary,
        production_envelope=production_envelope,
        production_target_ranking=production_target_ranking,
        fseof_lite_targets=fseof_lite_targets,
        production_design_targets=production_design_targets,
        production_gene_targets=production_gene_targets,
        production_gecko_summary=production_gecko_summary,
        production_gecko_target_comparison=production_gecko_target_comparison,
        production_gecko_design_comparison=production_gecko_design_comparison,
        production_readiness_summary=production_readiness_summary,
        production_target_readiness=production_target_readiness,
        production_design_readiness=production_design_readiness,
        production_gene_readiness=production_gene_readiness,
    )
    output.write_text(html_text, encoding="utf-8")
    return output


def _render_report(
    *,
    title: str,
    fba_summary: list[dict[str, str]],
    flux_summary: list[dict[str, str]],
    pfba_summary: list[dict[str, str]],
    fva_summary: list[dict[str, str]],
    flux_comparison: list[dict[str, str]],
    pfba_comparison: list[dict[str, str]],
    pipeline_steps: list[dict[str, str]],
    pipeline_backend_status: list[dict[str, str]],
    custom_input_overview: list[dict[str, str]],
    workflow_selection: list[dict[str, str]],
    context_model_artifacts: list[dict[str, str]],
    model_variant_registry: list[dict[str, str]],
    analysis_variant_context: list[dict[str, str]],
    variant_fba_summary: list[dict[str, str]],
    variant_comparison_summary: list[dict[str, str]],
    variant_flux_comparison: list[dict[str, str]],
    variant_evidence_quality: list[dict[str, str]],
    id_mapping_summary: list[dict[str, str]],
    id_mapping_detail: list[dict[str, str]],
    normalized_input_map: list[dict[str, str]],
    ml_feature_summary: list[dict[str, str]],
    ml_feature_long: list[dict[str, str]],
    ml_analysis_summary: list[dict[str, str]],
    ml_correlations: list[dict[str, str]],
    ml_prior_scores: list[dict[str, str]],
    ml_diagnostic_summary: list[dict[str, str]],
    ml_pca_scores: list[dict[str, str]],
    ml_condition_clusters: list[dict[str, str]],
    ml_lasso_lite: list[dict[str, str]],
    minn_summary: list[dict[str, str]],
    minn_nodes: list[dict[str, str]],
    minn_edges: list[dict[str, str]],
    minn_tensor: list[dict[str, str]],
    minn_labels: list[dict[str, str]],
    minn_readiness_summary: list[dict[str, str]],
    minn_readiness_priors: list[dict[str, str]],
    minn_readiness_weights: list[dict[str, str]],
    hybrid_summary: list[dict[str, str]],
    hybrid_target_scores: list[dict[str, str]],
    hybrid_feature_attributions: list[dict[str, str]],
    hybrid_loocv_summary: list[dict[str, str]],
    hybrid_loocv_evaluation: list[dict[str, str]],
    hybrid_schema: dict[str, object],
    hybrid_metadata: dict[str, object],
    hybrid_adapter_summary: list[dict[str, str]],
    hybrid_adapter_flags: list[dict[str, str]],
    hybrid_adapter_targets: list[dict[str, str]],
    hybrid_adapter_payload: dict[str, object],
    hybrid_adapter_dense_summary: list[dict[str, str]],
    hybrid_adapter_dense_vocabulary: list[dict[str, str]],
    hybrid_adapter_dense_matrix: list[dict[str, str]],
    hybrid_adapter_pyg_summary: list[dict[str, str]],
    hybrid_adapter_condition_pyg_summary: list[dict[str, str]],
    hybrid_adapter_dgl_summary: list[dict[str, str]],
    hybrid_adapter_condition_dgl_summary: list[dict[str, str]],
    relative_protein_evidence: list[dict[str, str]],
    multi_omics_conflict_summary: list[dict[str, str]],
    multi_omics_conflict_detail: list[dict[str, str]],
    evidence_mode_summary: list[dict[str, str]],
    evidence_mode_delta_summary: list[dict[str, str]],
    evidence_mode_reaction_deltas: list[dict[str, str]],
    evidence_mode_recommendations: list[dict[str, str]],
    condition_interpretation: list[dict[str, str]],
    condition_recommendations: list[dict[str, str]],
    consensus_context_summary: list[dict[str, str]],
    consensus_delete_candidates: list[dict[str, str]],
    context_policy_summary: list[dict[str, str]],
    context_feasibility: list[dict[str, str]],
    context_knockouts: list[dict[str, str]],
    model_qc_summary: list[dict[str, str]],
    model_qc_recommendations: list[dict[str, str]],
    model_qc_compartments: list[dict[str, str]],
    uniprot_check_summary: list[dict[str, str]],
    uniprot_gene_coverage: list[dict[str, str]],
    gpr_consistency_flags: list[dict[str, str]],
    reaction_annotation_flags: list[dict[str, str]],
    uniprot_enrichment_summary: list[dict[str, str]],
    uniprot_enrichment_records: list[dict[str, str]],
    dlkcat_summary: list[dict[str, str]],
    dlkcat_external_summary: list[dict[str, str]],
    dlkcat_input_coverage: list[dict[str, str]],
    dlkcat_predictions: list[dict[str, str]],
    dlkcat_kcat_priors: list[dict[str, str]],
    kcat_prior_merge_summary: list[dict[str, str]],
    kcat_prior_candidates: list[dict[str, str]],
    kcat_conflict_flags: list[dict[str, str]],
    kcat_priors: list[dict[str, str]],
    memote_run_summary: list[dict[str, str]],
    enzyme_summary: list[dict[str, str]],
    enzyme_recommendations: list[dict[str, str]],
    enzyme_capacity: list[dict[str, str]],
    gecko_summary: list[dict[str, str]],
    gecko_run_summary: list[dict[str, str]],
    thermo_summary: list[dict[str, str]],
    thermo_recommendations: list[dict[str, str]],
    pytfa_summary: list[dict[str, str]],
    pytfa_run_summary: list[dict[str, str]],
    troppo_summary: list[dict[str, str]],
    troppo_selected: list[dict[str, str]],
    omics_quality: list[dict[str, str]],
    omics_recommendations: list[dict[str, str]],
    troppo_method_summary: list[dict[str, str]],
    troppo_method_matrix: list[dict[str, str]],
    eflux_summary: list[dict[str, str]],
    eflux_validation_summary: list[dict[str, str]],
    delta_fba_summary: list[dict[str, str]],
    production_summary: list[dict[str, str]],
    production_envelope: list[dict[str, str]],
    production_target_ranking: list[dict[str, str]],
    fseof_lite_targets: list[dict[str, str]],
    production_design_targets: list[dict[str, str]],
    production_gene_targets: list[dict[str, str]],
    production_gecko_summary: list[dict[str, str]],
    production_gecko_target_comparison: list[dict[str, str]],
    production_gecko_design_comparison: list[dict[str, str]],
    production_readiness_summary: list[dict[str, str]],
    production_target_readiness: list[dict[str, str]],
    production_design_readiness: list[dict[str, str]],
    production_gene_readiness: list[dict[str, str]],
) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_e(title)}</title>
  <style>
    :root {{
      --bg: #f6f8fb;
      --panel: #ffffff;
      --ink: #172026;
      --muted: #5b6b73;
      --line: #d9e2e7;
      --teal: #087f7b;
      --blue: #2f66c9;
      --red: #b42318;
      --amber: #9a6700;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
      letter-spacing: 0;
    }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px 20px 42px; }}
    h1 {{ margin: 0 0 8px; font-size: 28px; letter-spacing: 0; }}
    h2 {{ margin: 26px 0 12px; font-size: 20px; letter-spacing: 0; }}
    p {{ margin: 0; line-height: 1.55; color: var(--muted); }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; margin-top: 16px; }}
    .card {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 14px;
      box-shadow: 0 8px 22px rgba(26, 43, 54, 0.07);
    }}
    .metric {{ font-size: 24px; font-weight: 800; margin-top: 6px; }}
    .label {{ color: var(--muted); font-size: 13px; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      overflow: hidden;
      font-size: 13px;
    }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 8px 9px; text-align: left; vertical-align: top; }}
    th {{ background: #edf3f6; color: #263942; }}
    tr:last-child td {{ border-bottom: 0; }}
    .bar {{ height: 8px; background: #dce5ea; border-radius: 999px; overflow: hidden; min-width: 80px; }}
    .fill {{ height: 100%; background: var(--teal); }}
    .bad {{ color: var(--red); font-weight: 700; }}
    .ok {{ color: var(--teal); font-weight: 700; }}
    .warn {{ color: var(--amber); font-weight: 700; }}
    @media (max-width: 720px) {{ main {{ padding: 18px 12px; }} table {{ font-size: 12px; }} }}
  </style>
</head>
<body>
  <main>
    <h1>{_e(title)}</h1>
    <p>由 Omics-GEM Router 生成。FVA 为 fluxomics 验证反应的 targeted FVA，不是全模型 FVA。</p>
    {_render_metrics(fba_summary, flux_summary, pfba_summary, fva_summary)}
    <h2>Custom Input Overview</h2>
    {_render_custom_input_overview(custom_input_overview)}
    <h2>Workflow Selection</h2>
    {_render_workflow_selection(workflow_selection)}
    <h2>Context Model Artifacts</h2>
    {_render_context_model_artifacts(context_model_artifacts)}
    <h2>Model Variant Registry</h2>
    {_render_model_variant_registry(model_variant_registry)}
    <h2>Analysis Variant Context</h2>
    {_render_analysis_variant_context(analysis_variant_context)}
    <h2>Variant FBA / pFBA Results</h2>
    {_render_variant_fba_summary(variant_fba_summary)}
    <h2>Multi-Variant Comparison</h2>
    {_render_variant_comparison(variant_comparison_summary, variant_flux_comparison, variant_evidence_quality)}
    <h2>ID Mapping Review</h2>
    {_render_id_mapping_summary(id_mapping_summary)}
    {_render_id_mapping_detail(id_mapping_detail)}
    {_render_normalized_input_map(normalized_input_map)}
    <h2>Pipeline Overview</h2>
    {_render_pipeline_steps(pipeline_steps)}
    {_render_backend_status(pipeline_backend_status)}
    <h2>ML + GEM Feature Matrix</h2>
    {_render_ml_feature_summary(ml_feature_summary)}
    {_render_ml_feature_examples(ml_feature_long)}
    <h2>ML Correlation / Prior Bridge</h2>
    {_render_ml_analysis_summary(ml_analysis_summary)}
    {_render_ml_prior_scores(ml_prior_scores)}
    {_render_ml_correlations(ml_correlations)}
    <h2>ML Exploratory Diagnostics</h2>
    {_render_ml_diagnostic_summary(ml_diagnostic_summary)}
    {_render_ml_pca_scores(ml_pca_scores)}
    {_render_ml_condition_clusters(ml_condition_clusters)}
    {_render_ml_lasso_lite(ml_lasso_lite)}
    <h2>MINN-style Hybrid Export</h2>
    {_render_minn_summary(minn_summary)}
    {_render_minn_tensor(minn_tensor)}
    {_render_minn_labels(minn_labels)}
    {_render_minn_readiness_summary(minn_readiness_summary)}
    {_render_minn_readiness_priors(minn_readiness_priors)}
    {_render_minn_readiness_weights(minn_readiness_weights)}
    {_render_minn_graph_examples(minn_nodes, minn_edges)}
    <h2>Lightweight Hybrid ML + GEM Runner</h2>
    {_render_hybrid_runner_summary(hybrid_summary)}
    {_render_hybrid_target_scores(hybrid_target_scores)}
    {_render_hybrid_feature_attributions(hybrid_feature_attributions)}
    {_render_hybrid_loocv_summary(hybrid_loocv_summary)}
    {_render_hybrid_loocv_evaluation(hybrid_loocv_evaluation)}
    {_render_hybrid_runner_metadata(hybrid_metadata, hybrid_schema)}
    {_render_hybrid_graph_adapter(hybrid_adapter_summary, hybrid_adapter_flags, hybrid_adapter_targets, hybrid_adapter_payload, hybrid_adapter_dense_summary, hybrid_adapter_dense_vocabulary, hybrid_adapter_dense_matrix, hybrid_adapter_pyg_summary, hybrid_adapter_condition_pyg_summary, hybrid_adapter_dgl_summary, hybrid_adapter_condition_dgl_summary)}
    <h2>GEM Model QC</h2>
    {_render_model_qc(model_qc_summary)}
    {_render_model_qc_recommendations(model_qc_recommendations)}
    {_render_compartment_qc(model_qc_compartments)}
    {_render_memote_run_summary(memote_run_summary)}
    <h2>UniProt / GPR Model Check</h2>
    {_render_uniprot_check_summary(uniprot_check_summary)}
    {_render_uniprot_enrichment_summary(uniprot_enrichment_summary)}
    {_render_uniprot_enrichment_records(uniprot_enrichment_records)}
    {_render_uniprot_high_risk_flags(gpr_consistency_flags, reaction_annotation_flags)}
    {_render_uniprot_inconclusive_rows(reaction_annotation_flags)}
    {_render_uniprot_gene_coverage(uniprot_gene_coverage)}
    <h2>DLKcat kcat Prediction Bridge</h2>
    {_render_dlkcat_bridge(dlkcat_summary, dlkcat_external_summary, dlkcat_input_coverage, dlkcat_predictions, dlkcat_kcat_priors)}
    <h2>kcat Prior Evidence Merge</h2>
    {_render_kcat_prior_merge(kcat_prior_merge_summary, kcat_prior_candidates, kcat_conflict_flags, kcat_priors)}
    <h2>Production Analysis / ecFactory-lite</h2>
    {_render_production_summary(production_summary)}
    {_render_production_readiness_summary(production_readiness_summary)}
    {_render_production_target_readiness(production_target_readiness)}
    {_render_production_design_readiness(production_design_readiness)}
    {_render_production_gene_readiness(production_gene_readiness)}
    {_render_production_target_ranking(production_target_ranking)}
    {_render_production_design_targets(production_design_targets)}
    {_render_production_gene_targets(production_gene_targets)}
    {_render_production_gecko_summary(production_gecko_summary)}
    {_render_production_gecko_target_comparison(production_gecko_target_comparison)}
    {_render_production_gecko_design_comparison(production_gecko_design_comparison)}
    {_render_production_envelope(production_envelope)}
    {_render_fseof_lite_targets(fseof_lite_targets)}
    <h2>FBA / pFBA / FVA 摘要</h2>
    {_render_table(fba_summary)}
    <h2>FBA Flux Validation</h2>
    {_render_summary_table(flux_summary, "within_ci_fraction")}
    {_render_comparison_table(flux_comparison)}
    <h2>pFBA Flux Validation</h2>
    {_render_summary_table(pfba_summary, "within_ci_fraction")}
    {_render_comparison_table(pfba_comparison)}
    <h2>Transcriptomics Flux Methods</h2>
    {_render_eflux_summary(eflux_summary)}
    {_render_summary_table(eflux_validation_summary, "within_ci_fraction")}
    {_render_delta_fba_summary(delta_fba_summary)}
    <h2>Targeted FVA Coverage</h2>
    {_render_summary_table(fva_summary, "within_fva_fraction")}
    <h2>Thermodynamic Constraint Bridge</h2>
    {_render_thermo_summary(thermo_summary)}
    {_render_thermo_recommendations(thermo_recommendations)}
    <h2>pyTFA Export Package</h2>
    {_render_pytfa_summary(pytfa_summary)}
    {_render_pytfa_run_summary(pytfa_run_summary)}
    <h2>Enzyme Constraint Bridge</h2>
    {_render_enzyme_summary(enzyme_summary)}
    {_render_enzyme_recommendations(enzyme_recommendations)}
    {_render_enzyme_capacity(enzyme_capacity)}
    <h2>GECKO Export Package</h2>
    {_render_gecko_summary(gecko_summary)}
    {_render_gecko_run_summary(gecko_run_summary)}
    <h2>Relative Proteomics Evidence</h2>
    {_render_relative_protein_evidence(relative_protein_evidence)}
    <h2>Multi-Omics Evidence Conflict QC</h2>
    {_render_multi_omics_conflict_summary(multi_omics_conflict_summary)}
    {_render_multi_omics_conflict_detail(multi_omics_conflict_detail)}
    <h2>Evidence Mode Comparison</h2>
    {_render_condition_interpretation(condition_interpretation)}
    {_render_condition_recommendations(condition_recommendations)}
    {_render_evidence_mode_delta_summary(evidence_mode_delta_summary)}
    {_render_evidence_mode_recommendations(evidence_mode_recommendations)}
    {_render_evidence_mode_summary(evidence_mode_summary)}
    {_render_evidence_mode_deltas(evidence_mode_reaction_deltas)}
    <h2>Consensus Context Policy</h2>
    {_render_table(consensus_context_summary)}
    {_render_context_knockouts(consensus_delete_candidates)}
    <h2>Context-Specific Lightweight Policy</h2>
    {_render_table(context_policy_summary)}
    <h2>Context Feasibility After Delete Candidates</h2>
    {_render_table(context_feasibility)}
    {_render_context_knockouts(context_knockouts)}
    <h2>TROPPO FASTcore</h2>
    {_render_table(troppo_summary)}
    <h2>TROPPO Method Matrix</h2>
    {_render_troppo_method_matrix(troppo_method_matrix)}
    {_render_troppo_method_summary(troppo_method_summary)}
    <h2>Omics Signal Quality</h2>
    {_render_omics_quality(omics_quality)}
    {_render_recommendations(omics_recommendations)}
    {_render_troppo_selected(troppo_selected)}
  </main>
</body>
</html>
"""


def _render_metrics(
    fba_summary: list[dict[str, str]],
    flux_summary: list[dict[str, str]],
    pfba_summary: list[dict[str, str]],
    fva_summary: list[dict[str, str]],
) -> str:
    all_flux = _find_all(flux_summary)
    all_pfba = _find_all(pfba_summary)
    all_fva = _find_all(fva_summary)
    cards = [
        ("Conditions", str(len(fba_summary)), "求解的 condition 数"),
        ("FBA within CI", _percent(all_flux.get("within_ci_fraction")), "FBA 预测落入实验 CI 的比例"),
        ("pFBA within CI", _percent(all_pfba.get("within_ci_fraction")), "pFBA 预测落入实验 CI 的比例"),
        ("FVA coverage", _percent(all_fva.get("within_fva_fraction")), "实测 flux 落入 targeted FVA 范围的比例"),
    ]
    return '<div class="grid">' + "".join(
        f'<div class="card"><div class="label">{_e(title)}</div><div class="metric">{_e(value)}</div><p>{_e(note)}</p></div>'
        for title, value, note in cards
    ) + "</div>"


def _render_custom_input_overview(rows: list[dict[str, str]], limit: int = 20) -> str:
    if not rows:
        return "<p>No custom input overview. Demo reports may not have staged user-upload metadata.</p>"
    headers = [
        "input_group",
        "role",
        "original_name",
        "inspection_status",
        "usage_note",
        "relative_path",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "inspection_status":
                klass = "ok" if value in {"ok", "not_checked"} else "warn"
                body += f'<td class="{klass}">{_e(value)}</td>'
            else:
                body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_workflow_selection(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return "<p>No explicit workflow selection has been recorded for this report.</p>"
    headers = [
        "selection_type",
        "selection_id",
        "label",
        "selected",
        "selected_model_variant_id",
        "description",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "selected":
                klass = "ok" if str(value).lower() == "true" else "warn"
                body += f'<td class="{klass}">{_e(value)}</td>'
            else:
                body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_model_variant_registry(rows: list[dict[str, str]], limit: int = 40) -> str:
    if not rows:
        return "<p>No model variant registry has been generated for this report.</p>"
    headers = [
        "variant_id",
        "method",
        "generation_method_label",
        "condition",
        "evidence_mode",
        "generation_status",
        "confidence",
        "primary_model_path",
        "generated_files",
        "compatible_analyses",
        "recommended_next_analyses",
        "guidance",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "generation_status":
                klass = "ok" if value in {"generated", "staged"} else "warn"
                body += f'<td class="{klass}">{_e(value)}</td>'
            else:
                body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_context_model_artifacts(rows: list[dict[str, str]], limit: int = 40) -> str:
    if not rows:
        return "<p>No context model artifact package has been generated for this report.</p>"
    headers = [
        "variant_id",
        "generation_method",
        "condition",
        "artifact_status",
        "artifact_format",
        "context_model_export_status",
        "selected_count",
        "keep_count",
        "delete_count",
        "penalize_count",
        "core_count",
        "removed_reaction_count",
        "missing_delete_reaction_count",
        "guidance",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "artifact_status":
                klass = "ok" if value == "generated" else "warn"
                body += f'<td class="{klass}">{_e(value)}</td>'
            else:
                body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_analysis_variant_context(rows: list[dict[str, str]], limit: int = 40) -> str:
    if not rows:
        return "<p>No active analysis variant context has been generated for this report.</p>"
    headers = [
        "analysis_module",
        "analysis_label",
        "active_variant_id",
        "active_generation_method_label",
        "compatible",
        "execution_scope",
        "active_model_path",
        "active_model_source",
        "context_model_sbml",
        "guidance",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "compatible":
                klass = "ok" if str(value).lower() == "true" else "warn"
                body += f'<td class="{klass}">{_e(value)}</td>'
            else:
                body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_variant_fba_summary(rows: list[dict[str, str]], limit: int = 40) -> str:
    if not rows:
        return "<p>No variant-specific FBA/pFBA result has been generated for this report.</p>"
    headers = [
        "variant_id",
        "analysis_module",
        "condition",
        "status",
        "objective_value",
        "active_generation_method_label",
        "active_model_path",
        "output_dir",
        "run_status",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header in {"status", "run_status"}:
                klass = "ok" if value in {"completed", "optimal"} else "warn" if value else ""
                body += f'<td class="{klass}">{_e(value)}</td>'
            elif header == "objective_value":
                body += f"<td>{_e(_short_number(value))}</td>"
            else:
                body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_variant_comparison(
    summary_rows: list[dict[str, str]],
    flux_rows: list[dict[str, str]],
    evidence_rows: list[dict[str, str]],
) -> str:
    if not summary_rows and not flux_rows and not evidence_rows:
        return "<p>No multi-variant comparison data has been generated for this report.</p>"
    parts: list[str] = []
    if summary_rows:
        summary_headers = [
            "variant_id",
            "generation_method_label",
            "condition",
            "generation_status",
            "context_model_sbml_available",
            "context_model_feasibility_status",
            "fba_status",
            "fba_objective_value",
            "evidence_quality_label",
            "guidance",
        ]
        parts.append("<h3>Variant comparison summary</h3>" + _render_selected_columns(summary_rows, summary_headers, limit=40))
    if flux_rows:
        flux_headers = [
            "variant_id",
            "condition",
            "status",
            "objective_value",
            "active_generation_method_label",
            "active_model_path",
        ]
        parts.append("<h3>Variant flux comparison</h3>" + _render_selected_columns(flux_rows, flux_headers, limit=40))
    if evidence_rows:
        evidence_headers = [
            "variant_id",
            "condition",
            "evidence_mode",
            "confidence",
            "evidence_quality_label",
            "multi_omics_conflict_fraction",
            "context_model_feasibility_status",
            "fba_status",
        ]
        parts.append("<h3>Variant evidence quality</h3>" + _render_selected_columns(evidence_rows, evidence_headers, limit=40))
    return "".join(parts)


def _render_selected_columns(rows: list[dict[str, str]], headers: list[str], limit: int = 40) -> str:
    body = ""
    for row in rows[:limit]:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header in {"context_model_sbml_available"}:
                klass = "ok" if str(value).lower() == "true" else "warn"
                body += f'<td class="{klass}">{_e(value)}</td>'
            elif header in {"fba_status", "context_model_feasibility_status", "evidence_quality_label"}:
                text = str(value)
                klass = "ok" if text in {"optimal", "feasible", "stronger_evidence"} else "warn" if text else ""
                body += f'<td class="{klass}">{_e(value)}</td>'
            elif header == "objective_value":
                body += f"<td>{_e(_short_number(value))}</td>"
            elif header.endswith("fraction"):
                body += f"<td>{_percent(value)}</td>"
            else:
                body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_id_mapping_summary(rows: list[dict[str, str]], limit: int = 20) -> str:
    if not rows:
        return "<p>No ID mapping review has been generated for this report.</p>"
    headers = [
        "input_role",
        "entity_type",
        "source_file",
        "before_mapped_fraction",
        "after_mapped_fraction",
        "alias_mapped_count",
        "mapping_label",
        "after_mapped_count",
        "total_count",
        "guidance",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>"
        for header in headers:
            value = _id_mapping_value(row, header)
            if header in {"before_mapped_fraction", "after_mapped_fraction"}:
                body += f"<td>{_percent(value)}</td>"
            elif header == "mapping_label":
                klass = "ok" if value == "strong_mapping" else "warn" if value == "usable_with_caution" else "bad"
                body += f'<td class="{klass}">{_e(value)}</td>'
            else:
                body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _id_mapping_value(row: dict[str, str], header: str) -> str:
    if header == "before_mapped_fraction":
        return row.get(header) or row.get("mapped_fraction", "")
    if header == "after_mapped_fraction":
        return row.get(header) or row.get("mapped_fraction", "")
    if header == "after_mapped_count":
        return row.get(header) or row.get("mapped_count", "")
    return row.get(header, "")


def _render_id_mapping_detail(rows: list[dict[str, str]], limit: int = 40) -> str:
    if not rows:
        return ""
    headers = [
        "input_role",
        "entity_type",
        "source_id",
        "model_id",
        "mapping_status",
        "alias_model_id",
        "alias_source",
        "source_file",
        "source_row_index",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "mapping_status":
                klass = "ok" if value == "mapped" else "warn" if value == "not_checked" else "bad"
                body += f'<td class="{klass}">{_e(value)}</td>'
            else:
                body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return (
        "<h3>Identifier detail</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_normalized_input_map(rows: list[dict[str, str]], limit: int = 20) -> str:
    if not rows:
        return ""
    headers = [
        "role",
        "source_relative_path",
        "relative_path",
        "row_count",
        "direct_mapped_count",
        "alias_mapped_count",
        "not_found_count",
        "status",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
    return (
        "<h3>Alias-normalized input tables</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_ml_feature_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No ML feature matrix has been generated for this report.</p>"
    headers = ["source", "condition_count", "feature_count", "value_count", "status"]
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in rows
    )
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_ml_feature_examples(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return ""
    headers = ["condition", "feature_id", "feature_type", "source", "value", "status"]
    body = ""
    for row in rows[:limit]:
        body += "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
    return (
        "<h3>Feature examples</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_ml_analysis_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No ML correlation analysis has been generated for this report.</p>"
    headers = ["status", "target_count", "candidate_feature_count", "correlation_count", "prior_count", "guidance"]
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in rows
    )
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_ml_prior_scores(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return "<p>No ML-derived priors passed the current soft-evidence threshold.</p>"
    headers = [
        "target_feature_id",
        "source_feature_id",
        "target_type",
        "model_target_id",
        "score",
        "ml_evidence",
        "context_action",
        "confidence",
        "sample_status",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
    return (
        "<h3>ML-derived soft priors</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_ml_correlations(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return ""
    headers = [
        "target_feature_id",
        "feature_id",
        "entity_type",
        "overlap_count",
        "pearson_r",
        "association_strength",
        "sample_status",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
    return (
        "<h3>Top feature-phenotype correlations</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_ml_diagnostic_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No ML exploratory diagnostics have been generated for this report.</p>"
    headers = [
        "status",
        "condition_count",
        "numeric_feature_count",
        "target_count",
        "pca_component_count",
        "cluster_count",
        "lasso_lite_feature_count",
        "sample_status",
        "guidance",
    ]
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in rows
    )
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_ml_pca_scores(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return ""
    headers = ["condition", "pc1", "pc2", "explained_variance_pc1", "explained_variance_pc2", "sample_status"]
    body = ""
    for row in rows[:limit]:
        body += "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
    return (
        "<h3>PCA condition scores</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_ml_condition_clusters(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return ""
    headers = ["condition", "cluster_id", "pc1", "pc2", "distance_to_centroid", "sample_status", "status"]
    body = ""
    for row in rows[:limit]:
        body += "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
    return (
        "<h3>Condition clusters</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_ml_lasso_lite(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return ""
    headers = [
        "target_feature_id",
        "feature_id",
        "entity_type",
        "coefficient",
        "abs_coefficient",
        "selection_rank",
        "selection_status",
        "sample_status",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
    return (
        "<h3>LASSO-lite sparse feature screen</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_minn_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No MINN-style hybrid export has been generated for this report.</p>"
    headers = [
        "status",
        "node_count",
        "reaction_node_count",
        "metabolite_node_count",
        "gene_node_count",
        "edge_count",
        "feature_tensor_row_count",
        "phenotype_label_count",
        "guidance",
    ]
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in rows
    )
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_minn_tensor(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return "<p>No MINN-style feature tensor rows are available yet.</p>"
    headers = ["condition", "node_id", "node_type", "feature_channel", "source", "value", "status"]
    body = ""
    for row in rows[:limit]:
        body += "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
    return (
        "<h3>Feature tensor examples</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_minn_labels(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return "<p>No MINN-style phenotype/flux labels are available yet.</p>"
    headers = ["condition", "label_type", "target_node_id", "value", "unit", "lower_ci", "upper_ci", "status"]
    body = ""
    for row in rows[:limit]:
        body += "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
    return (
        "<h3>Phenotype / flux labels</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_minn_readiness_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No readiness-aware hybrid target priors have been generated yet.</p>"
    headers = [
        "status",
        "target_prior_count",
        "sample_weight_count",
        "stronger_evidence_target_count",
        "usable_with_caution_target_count",
        "review_required_target_count",
        "ml_prior_matched_count",
        "uniprot_strong_target_count",
        "kcat_strong_target_count",
        "kcat_caution_target_count",
        "kcat_conflict_review_target_count",
        "kcat_spread_caution_target_count",
        "guidance",
    ]
    body = ""
    for row in rows:
        body += "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
    return (
        "<h3>Readiness-aware hybrid target priors</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_minn_readiness_priors(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return ""
    headers = [
        "condition",
        "target_level",
        "target_id",
        "recommended_action",
        "candidate_target_label",
        "combined_target_prior_score",
        "sample_weight",
        "production_readiness_label",
        "uniprot_evidence_label",
        "enzyme_constraint_label",
        "kcat_evidence_label",
        "kcat_evidence_tier",
        "kcat_conflict_flag",
        "ml_abs_score",
        "training_role",
        "status",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
    return (
        "<h3>Readiness target-prior examples</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_minn_readiness_weights(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return ""
    headers = [
        "condition",
        "target_level",
        "target_id",
        "candidate_target_label",
        "sample_weight",
        "combined_target_prior_score",
        "production_readiness_label",
        "kcat_evidence_label",
        "kcat_conflict_flag",
        "weight_reason",
        "status",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
    return (
        "<h3>Readiness sample weights</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_minn_graph_examples(
    node_rows: list[dict[str, str]],
    edge_rows: list[dict[str, str]],
    limit: int = 20,
) -> str:
    if not node_rows and not edge_rows:
        return ""
    node_headers = ["node_id", "node_type", "model_id", "name", "compartment"]
    edge_headers = ["source_node_id", "target_node_id", "edge_type", "stoichiometry", "role"]
    node_body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in node_headers) + "</tr>"
        for row in node_rows[:limit]
    )
    edge_body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in edge_headers) + "</tr>"
        for row in edge_rows[:limit]
    )
    return (
        "<h3>Graph node examples</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in node_headers)
        + f"</tr></thead><tbody>{node_body}</tbody></table>"
        + "<h3>Graph edge examples</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in edge_headers)
        + f"</tr></thead><tbody>{edge_body}</tbody></table>"
    )


def _render_hybrid_runner_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No lightweight hybrid runner output has been generated yet.</p>"
    headers = [
        "status",
        "target_prior_count",
        "feature_tensor_row_count",
        "target_score_count",
        "direct_feature_supported_count",
        "neighbor_feature_supported_count",
        "high_priority_count",
        "medium_priority_count",
        "exploratory_count",
        "blocked_count",
        "kcat_conflict_review_score_count",
        "kcat_spread_caution_score_count",
        "guidance",
    ]
    body = ""
    for row in rows:
        body += "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
    return (
        "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_hybrid_target_scores(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return ""
    headers = [
        "condition",
        "target_level",
        "target_id",
        "recommended_action",
        "hybrid_rank_score",
        "prediction_label",
        "prior_score",
        "sample_weight",
        "kcat_quality_multiplier",
        "direct_feature_signal",
        "neighbor_feature_signal",
        "top_feature_channels",
        "production_readiness_label",
        "kcat_evidence_label",
        "kcat_conflict_flag",
        "status",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
    return (
        "<h3>Hybrid target scores</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_hybrid_feature_attributions(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return ""
    headers = [
        "condition",
        "target_id",
        "feature_node_id",
        "feature_channel",
        "feature_value",
        "bounded_signal",
        "contribution_type",
        "contribution_score",
        "source",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
    return (
        "<h3>Hybrid feature attributions</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_hybrid_loocv_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No hybrid leave-one-condition-out evaluation has been generated yet.</p>"
    headers = [
        "status",
        "phenotype_label_count",
        "loocv_row_count",
        "evaluated_count",
        "direction_match_count",
        "direction_mismatch_count",
        "direction_match_fraction",
        "missing_hybrid_score_count",
        "insufficient_holdout_label_count",
        "guidance",
    ]
    body = ""
    for row in rows:
        body += "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
    return (
        "<h3>Leave-one-condition-out sanity check</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_hybrid_loocv_evaluation(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return ""
    headers = [
        "condition",
        "target_node_id",
        "heldout_value",
        "train_label_mean",
        "observed_direction",
        "hybrid_rank_score",
        "train_score_mean",
        "predicted_direction",
        "direction_match",
        "prediction_label",
        "status",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
    return (
        "<h3>LOOCV evaluation rows</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_hybrid_runner_metadata(metadata: dict[str, object], schema: dict[str, object]) -> str:
    if not metadata and not schema:
        return ""
    graph = metadata.get("graph", {}) if isinstance(metadata.get("graph"), dict) else {}
    features = metadata.get("features", {}) if isinstance(metadata.get("features"), dict) else {}
    labels = metadata.get("labels", {}) if isinstance(metadata.get("labels"), dict) else {}
    scores = metadata.get("scores", {}) if isinstance(metadata.get("scores"), dict) else {}
    loocv = metadata.get("loocv", {}) if isinstance(metadata.get("loocv"), dict) else {}
    tables = schema.get("tables", {}) if isinstance(schema.get("tables"), dict) else {}
    contract = schema.get("downstream_contract", {}) if isinstance(schema.get("downstream_contract"), dict) else {}
    rows = [
        {"item": "schema_version", "value": metadata.get("schema_version") or schema.get("schema_version", "")},
        {"item": "schema_table_count", "value": len(tables)},
        {"item": "graph_nodes", "value": graph.get("node_count", "")},
        {"item": "graph_edges", "value": graph.get("edge_count", "")},
        {"item": "conditions", "value": ";".join(features.get("conditions", [])) if isinstance(features.get("conditions"), list) else ""},
        {
            "item": "feature_channels",
            "value": ";".join(features.get("feature_channels", [])) if isinstance(features.get("feature_channels"), list) else "",
        },
        {"item": "phenotype_labels", "value": labels.get("phenotype_label_count", "")},
        {"item": "target_scores", "value": scores.get("target_score_count", "")},
        {"item": "loocv_rows", "value": loocv.get("row_count", "")},
        {"item": "node_key", "value": contract.get("node_key", "")},
        {"item": "edge_keys", "value": f"{contract.get('edge_source_key', '')} -> {contract.get('edge_target_key', '')}"},
    ]
    body = "".join("<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in ["item", "value"]) + "</tr>" for row in rows)
    return (
        "<h3>Hybrid runner schema / metadata</h3>"
        "<p>Machine-readable contract for downstream PyTorch Geometric, DGL, or tabular ML runners.</p>"
        "<table><thead><tr><th>item</th><th>value</th></tr></thead>"
        f"<tbody>{body}</tbody></table>"
    )


def _render_hybrid_graph_adapter(
    summary_rows: list[dict[str, str]],
    flag_rows: list[dict[str, str]],
    target_rows: list[dict[str, str]],
    payload: dict[str, object],
    dense_summary_rows: list[dict[str, str]],
    dense_vocabulary_rows: list[dict[str, str]],
    dense_matrix_rows: list[dict[str, str]],
    pyg_summary_rows: list[dict[str, str]],
    condition_pyg_summary_rows: list[dict[str, str]],
    dgl_summary_rows: list[dict[str, str]],
    condition_dgl_summary_rows: list[dict[str, str]],
    limit: int = 30,
) -> str:
    if (
        not summary_rows
        and not flag_rows
        and not target_rows
        and not payload
        and not dense_summary_rows
        and not dense_vocabulary_rows
        and not dense_matrix_rows
        and not pyg_summary_rows
        and not condition_pyg_summary_rows
        and not dgl_summary_rows
        and not condition_dgl_summary_rows
    ):
        return "<p>No PyG/DGL graph adapter dry-run package has been generated yet.</p>"
    summary_html = ""
    if summary_rows:
        headers = [
            "status",
            "node_count",
            "edge_count",
            "feature_tensor_row_count",
            "feature_dim",
            "label_count",
            "target_count",
            "validation_flag_count",
            "pyg_ready",
            "dgl_ready",
            "guidance",
        ]
        body = "".join("<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>" for row in summary_rows)
        summary_html = (
            "<h3>PyG / DGL graph adapter dry-run</h3>"
            + "<table><thead><tr>"
            + "".join(f"<th>{_e(header)}</th>" for header in headers)
            + f"</tr></thead><tbody>{body}</tbody></table>"
        )
    payload_html = ""
    if payload:
        shape = payload.get("shape", {}) if isinstance(payload.get("shape"), dict) else {}
        rows = [
            {"item": "payload_schema_version", "value": payload.get("schema_version", "")},
            {"item": "feature_dim", "value": shape.get("feature_dim", "")},
            {"item": "node_count", "value": shape.get("node_count", "")},
            {"item": "edge_count", "value": shape.get("edge_count", "")},
            {"item": "pyg_object_hint", "value": _nested_value(payload, "pytorch_geometric_stub", "object_hint")},
            {"item": "dgl_object_hint", "value": _nested_value(payload, "dgl_stub", "object_hint")},
        ]
        body = "".join("<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in ["item", "value"]) + "</tr>" for row in rows)
        payload_html = "<table><thead><tr><th>item</th><th>value</th></tr></thead>" + f"<tbody>{body}</tbody></table>"
    dense_html = _render_dense_adapter_matrix(dense_summary_rows, dense_vocabulary_rows, dense_matrix_rows)
    pyg_html = ""
    if pyg_summary_rows:
        headers = [
            "status",
            "torch_available",
            "torch_geometric_available",
            "node_count",
            "edge_count",
            "feature_dim",
            "label_count",
            "target_count",
            "data_path",
            "guidance",
        ]
        body = "".join("<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>" for row in pyg_summary_rows)
        pyg_html = (
            "<h3>Optional PyTorch Geometric Data export</h3>"
            + "<table><thead><tr>"
            + "".join(f"<th>{_e(header)}</th>" for header in headers)
            + f"</tr></thead><tbody>{body}</tbody></table>"
        )
    condition_pyg_html = ""
    if condition_pyg_summary_rows:
        headers = [
            "condition",
            "status",
            "feature_tensor_row_count",
            "label_count",
            "target_count",
            "data_path",
            "feature_aggregation",
            "guidance",
        ]
        body = "".join(
            "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
            for row in condition_pyg_summary_rows[:limit]
        )
        condition_pyg_html = (
            "<h3>Condition-specific PyTorch Geometric exports</h3>"
            + "<table><thead><tr>"
            + "".join(f"<th>{_e(header)}</th>" for header in headers)
            + f"</tr></thead><tbody>{body}</tbody></table>"
        )
    dgl_html = ""
    if dgl_summary_rows:
        headers = [
            "status",
            "torch_available",
            "dgl_available",
            "node_count",
            "edge_count",
            "feature_dim",
            "label_count",
            "target_count",
            "graph_path",
            "guidance",
        ]
        body = "".join("<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>" for row in dgl_summary_rows)
        dgl_html = (
            "<h3>Optional DGL graph export</h3>"
            + "<table><thead><tr>"
            + "".join(f"<th>{_e(header)}</th>" for header in headers)
            + f"</tr></thead><tbody>{body}</tbody></table>"
        )
    condition_dgl_html = ""
    if condition_dgl_summary_rows:
        headers = [
            "condition",
            "status",
            "feature_tensor_row_count",
            "label_count",
            "target_count",
            "graph_path",
            "feature_aggregation",
            "guidance",
        ]
        body = "".join(
            "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
            for row in condition_dgl_summary_rows[:limit]
        )
        condition_dgl_html = (
            "<h3>Condition-specific DGL graph exports</h3>"
            + "<table><thead><tr>"
            + "".join(f"<th>{_e(header)}</th>" for header in headers)
            + f"</tr></thead><tbody>{body}</tbody></table>"
        )
    flags_html = ""
    if flag_rows:
        headers = ["severity", "flag", "entity_type", "entity_id", "message"]
        body = "".join("<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>" for row in flag_rows[:limit])
        flags_html = (
            "<h3>Graph adapter validation flags</h3>"
            + "<table><thead><tr>"
            + "".join(f"<th>{_e(header)}</th>" for header in headers)
            + f"</tr></thead><tbody>{body}</tbody></table>"
        )
    targets_html = ""
    if target_rows:
        headers = ["condition", "node_index", "node_id", "target_id", "hybrid_rank_score", "prediction_label", "target_source", "status"]
        body = "".join("<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>" for row in target_rows[:limit])
        targets_html = (
            "<h3>Adapter target rows</h3>"
            + "<table><thead><tr>"
            + "".join(f"<th>{_e(header)}</th>" for header in headers)
            + f"</tr></thead><tbody>{body}</tbody></table>"
        )
    return summary_html + payload_html + dense_html + pyg_html + condition_pyg_html + dgl_html + condition_dgl_html + flags_html + targets_html


def _render_dense_adapter_matrix(
    summary_rows: list[dict[str, str]],
    vocabulary_rows: list[dict[str, str]],
    matrix_rows: list[dict[str, str]],
    limit: int = 10,
) -> str:
    if not summary_rows and not vocabulary_rows and not matrix_rows:
        return ""
    summary_html = ""
    if summary_rows:
        headers = [
            "status",
            "row_count",
            "node_count",
            "condition_count",
            "feature_dim",
            "nonzero_row_count",
            "zero_row_count",
            "guidance",
        ]
        body = "".join("<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>" for row in summary_rows)
        summary_html = (
            "<h3>Dense feature matrix export</h3>"
            + "<table><thead><tr>"
            + "".join(f"<th>{_e(header)}</th>" for header in headers)
            + f"</tr></thead><tbody>{body}</tbody></table>"
        )
    vocab_html = ""
    if vocabulary_rows:
        headers = ["feature_index", "feature_column", "feature_key", "feature_channel", "feature_id", "status"]
        body = "".join("<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>" for row in vocabulary_rows[:limit])
        vocab_html = (
            "<h3>Dense feature vocabulary</h3>"
            + "<table><thead><tr>"
            + "".join(f"<th>{_e(header)}</th>" for header in headers)
            + f"</tr></thead><tbody>{body}</tbody></table>"
        )
    matrix_html = ""
    if matrix_rows:
        feature_headers = [header for header in matrix_rows[0].keys() if header.startswith("f")][:5]
        headers = ["condition", "node_index", "node_id", "node_type", "feature_count", *feature_headers, "status"]
        body = "".join("<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>" for row in matrix_rows[:limit])
        matrix_html = (
            "<h3>Dense feature matrix preview</h3>"
            + "<table><thead><tr>"
            + "".join(f"<th>{_e(header)}</th>" for header in headers)
            + f"</tr></thead><tbody>{body}</tbody></table>"
        )
    return summary_html + vocab_html + matrix_html


def _render_uniprot_check_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No UniProt / GPR model check has been generated for this report.</p>"
    headers = [
        "status",
        "gene_count",
        "gene_uniprot_coverage_fraction",
        "reaction_count",
        "reaction_with_gpr_fraction",
        "missing_gpr_count",
        "ec_mismatch_count",
        "annotation_missing_count",
        "high_risk_flag_count",
        "inconclusive_reaction_count",
        "uniprot_enrichment_status",
        "uniprot_cache_hit_count",
        "uniprot_fetched_count",
        "uniprot_reviewed_count",
        "guidance",
    ]
    body = ""
    for row in rows:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header.endswith("fraction"):
                value = _percent(value)
            elif header == "status":
                klass = "bad" if "review" in str(value) else "warn" if "inconclusive" in str(value) else "ok"
                body += f'<td class="{klass}">{_e(value)}</td>'
                continue
            body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_uniprot_enrichment_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No UniProt cache / REST enrichment summary.</p>"
    headers = [
        "status",
        "network_access",
        "requested_accession_count",
        "cache_hit_count",
        "fetched_count",
        "missing_not_fetched_count",
        "fetch_failed_count",
        "reviewed_count",
        "with_ec_count",
        "guidance",
    ]
    body = ""
    for row in rows:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "status":
                klass = "warn" if "failure" in str(value) or value == "cache_only" else "ok"
                body += f'<td class="{klass}">{_e(value)}</td>'
            else:
                body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return (
        "<h3>UniProt cache / REST enrichment</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_uniprot_enrichment_records(rows: list[dict[str, str]], limit: int = 20) -> str:
    if not rows:
        return ""
    headers = ["accession", "cache_status", "reviewed_status", "protein_name", "ec_numbers", "organism", "error"]
    body = ""
    for row in rows[:limit]:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "cache_status":
                klass = "ok" if value in {"cache_hit", "fetched"} else "warn"
                body += f'<td class="{klass}">{_e(value)}</td>'
            else:
                body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return (
        "<h3>UniProt enrichment records</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_uniprot_high_risk_flags(
    gpr_rows: list[dict[str, str]],
    reaction_rows: list[dict[str, str]],
    limit: int = 20,
) -> str:
    combined = [
        {"table": "gpr_consistency", **row}
        for row in gpr_rows
        if row.get("severity") == "high"
    ] + [
        {"table": "reaction_annotation", **row}
        for row in reaction_rows
        if row.get("severity") == "high"
    ]
    if not combined:
        return "<p>No high-risk UniProt/GPR flags.</p>"
    headers = ["table", "reaction_id", "reaction_name", "flag", "severity", "status", "note"]
    body = ""
    for row in combined[:limit]:
        body += "<tr>"
        for header in headers:
            klass = ' class="bad"' if header in {"flag", "severity"} else ""
            body += f"<td{klass}>{_e(row.get(header, ''))}</td>"
        body += "</tr>"
    return (
        "<h3>High-risk flags</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_uniprot_inconclusive_rows(rows: list[dict[str, str]], limit: int = 20) -> str:
    inconclusive = [row for row in rows if row.get("status") == "inconclusive"]
    if not inconclusive:
        return "<p>No inconclusive reaction annotation rows.</p>"
    headers = ["reaction_id", "reaction_name", "flag", "status", "reaction_ec_numbers", "gene_ec_numbers", "note"]
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in inconclusive[:limit]
    )
    return (
        "<h3>Inconclusive annotation rows</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_uniprot_gene_coverage(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return "<p>No gene-level UniProt coverage rows.</p>"
    headers = [
        "gene_id",
        "has_uniprot",
        "uniprot_id",
        "reviewed_status",
        "protein_name",
        "has_ec",
        "ec_numbers",
        "annotation_sources",
        "status",
    ]
    missing_first = sorted(rows, key=lambda row: 0 if row.get("status") == "annotation_missing" else 1)
    body = ""
    for row in missing_first[:limit]:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "status":
                klass = "warn" if value != "annotated" else "ok"
                body += f'<td class="{klass}">{_e(value)}</td>'
            else:
                body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return (
        "<h3>Gene annotation coverage</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_dlkcat_bridge(
    summary_rows: list[dict[str, str]],
    external_rows: list[dict[str, str]],
    coverage_rows: list[dict[str, str]],
    prediction_rows: list[dict[str, str]],
    kcat_prior_rows: list[dict[str, str]],
    limit: int = 20,
) -> str:
    if not summary_rows:
        return "<p>No DLKcat bridge output has been generated for this report.</p>"
    summary_headers = [
        "status",
        "input_query_count",
        "ready_query_count",
        "reaction_count",
        "ready_reaction_count",
        "missing_sequence_count",
        "missing_substrate_count",
        "prediction_import_row_count",
        "prediction_mapped_count",
        "reaction_kcat_prior_count",
        "guidance",
    ]
    summary_html = (
        "<h3>DLKcat bridge summary</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in summary_headers)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>"
            + "".join(
                f'<td class="{"ok" if header == "status" and row.get(header) == "predictions_imported" else "warn" if header == "status" else ""}">{_e(row.get(header, ""))}</td>'
                for header in summary_headers
            )
            + "</tr>"
            for row in summary_rows
        )
        + "</tbody></table>"
    )
    external_html = ""
    if external_rows:
        headers = [
            "status",
            "input_status",
            "ready_query_count",
            "matlab_path",
            "gecko_home_exists",
            "docker_path",
            "return_code",
            "message",
        ]
        external_html = (
            "<h3>GECKO / DLKcat external runner</h3>"
            + "<table><thead><tr>"
            + "".join(f"<th>{_e(header)}</th>" for header in headers)
            + "</tr></thead><tbody>"
            + "".join(
                "<tr>"
                + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers)
                + "</tr>"
                for row in external_rows
            )
            + "</tbody></table>"
        )
    coverage_html = ""
    if coverage_rows:
        headers = [
            "reaction_id",
            "reaction_name",
            "query_count",
            "ready_query_count",
            "missing_sequence_count",
            "missing_substrate_count",
            "ready_fraction",
            "status",
        ]
        body = ""
        for row in coverage_rows[:limit]:
            body += "<tr>"
            for header in headers:
                value = _percent(row.get(header, "")) if header == "ready_fraction" else row.get(header, "")
                klass = ' class="ok"' if header == "status" and value == "ready" else ' class="warn"' if header == "status" else ""
                body += f"<td{klass}>{_e(value)}</td>"
            body += "</tr>"
        coverage_html = (
            "<h3>DLKcat input coverage</h3>"
            + "<table><thead><tr>"
            + "".join(f"<th>{_e(header)}</th>" for header in headers)
            + f"</tr></thead><tbody>{body}</tbody></table>"
        )
    prediction_html = ""
    if prediction_rows:
        headers = ["query_id", "reaction_id", "gene_id", "substrate_name", "predicted_kcat_per_s", "mapping_status"]
        prediction_html = (
            "<h3>Normalized DLKcat predictions</h3>"
            + "<table><thead><tr>"
            + "".join(f"<th>{_e(header)}</th>" for header in headers)
            + "</tr></thead><tbody>"
            + "".join(
                "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
                for row in prediction_rows[:limit]
            )
            + "</tbody></table>"
        )
    prior_html = ""
    if kcat_prior_rows:
        headers = ["target_id", "model_target_id", "kcat", "unit", "confidence", "source_tier", "gene_id", "substrate_name"]
        prior_html = (
            "<h3>DLKcat-derived reaction kcat priors</h3>"
            + "<table><thead><tr>"
            + "".join(f"<th>{_e(header)}</th>" for header in headers)
            + "</tr></thead><tbody>"
            + "".join(
                "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
                for row in kcat_prior_rows[:limit]
            )
            + "</tbody></table>"
        )
    return summary_html + external_html + coverage_html + prediction_html + prior_html


def _render_kcat_prior_merge(
    summary_rows: list[dict[str, str]],
    candidate_rows: list[dict[str, str]],
    conflict_rows: list[dict[str, str]],
    selected_rows: list[dict[str, str]],
    limit: int = 20,
) -> str:
    if not summary_rows:
        return "<p>No merged kcat prior evidence table has been generated for this report.</p>"
    summary_headers = [
        "status",
        "candidate_count",
        "selected_prior_count",
        "experimental_candidate_count",
        "database_candidate_count",
        "dlkcat_candidate_count",
        "ml_candidate_count",
        "selected_experimental_count",
        "selected_database_count",
        "selected_dlkcat_count",
        "selected_ml_count",
        "kcat_conflict_review_count",
        "kcat_spread_caution_count",
        "guidance",
    ]
    summary_html = (
        "<h3>kcat prior evidence summary</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in summary_headers)
        + "</tr></thead><tbody>"
        + "".join(
            "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in summary_headers) + "</tr>"
            for row in summary_rows
        )
        + "</tbody></table>"
    )
    selected_html = ""
    if selected_rows:
        headers = [
            "target_id",
            "model_target_id",
            "kcat",
            "unit",
            "confidence",
            "kcat_evidence_tier",
            "kcat_conflict_flag",
            "kcat_fold_range",
            "source_tier",
            "selection_status",
        ]
        selected_html = (
            "<h3>Selected kcat priors for enzyme / GECKO workflows</h3>"
            + "<table><thead><tr>"
            + "".join(f"<th>{_e(header)}</th>" for header in headers)
            + "</tr></thead><tbody>"
            + "".join(
                "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
                for row in selected_rows[:limit]
            )
            + "</tbody></table>"
        )
    conflict_html = ""
    if conflict_rows:
        headers = [
            "model_target_id",
            "candidate_count",
            "min_kcat_per_s",
            "max_kcat_per_s",
            "fold_range",
            "flag",
            "min_candidate_evidence_tier",
            "max_candidate_evidence_tier",
            "min_candidate_original_source",
            "max_candidate_original_source",
            "severity",
            "status",
            "guidance",
        ]
        conflict_html = (
            "<h3>kcat conflict flags</h3>"
            + "<table><thead><tr>"
            + "".join(f"<th>{_e(header)}</th>" for header in headers)
            + "</tr></thead><tbody>"
            + "".join(
                "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
                for row in conflict_rows[:limit]
            )
            + "</tbody></table>"
        )
    candidate_html = ""
    if candidate_rows:
        headers = [
            "target_id",
            "model_target_id",
            "kcat",
            "confidence",
            "kcat_evidence_tier",
            "original_source",
            "selection_status",
        ]
        candidate_html = (
            "<h3>kcat prior candidates</h3>"
            + "<table><thead><tr>"
            + "".join(f"<th>{_e(header)}</th>" for header in headers)
            + "</tr></thead><tbody>"
            + "".join(
                "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
                for row in candidate_rows[:limit]
            )
            + "</tbody></table>"
        )
    return summary_html + selected_html + conflict_html + candidate_html


def _render_production_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No production analysis has been generated for this report.</p>"
    headers = [
        "status",
        "product_target_count",
        "production_envelope_row_count",
        "ranked_product_count",
        "fseof_candidate_count",
        "production_design_candidate_count",
        "oe_design_count",
        "kd_design_count",
        "ko_design_count",
        "production_gene_target_count",
        "unmapped_reaction_target_count",
        "review_required_target_count",
        "growth_coupled_target_count",
        "guidance",
    ]
    body = ""
    for row in rows:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "status":
                klass = "ok" if value == "completed" else "warn"
                body += f'<td class="{klass}">{_e(value)}</td>'
            else:
                body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_production_readiness_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No production readiness gate has been generated.</p>"
    headers = [
        "status",
        "product_target_count",
        "reaction_design_target_count",
        "gene_design_target_count",
        "stronger_evidence_count",
        "usable_with_caution_count",
        "guidance_only_count",
        "review_required_count",
        "uniprot_stronger_evidence_count",
        "uniprot_caution_count",
        "uniprot_review_required_count",
        "uniprot_cache_issue_count",
        "kcat_strong_evidence_count",
        "kcat_caution_count",
        "kcat_missing_count",
        "kcat_conflict_review_count",
        "kcat_spread_caution_count",
        "gecko_supported_count",
        "gecko_conflict_count",
        "guidance",
    ]
    body = ""
    for row in rows:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "review_required_count" and str(value) not in {"", "0"}:
                body += f'<td class="bad">{_e(value)}</td>'
            elif header == "stronger_evidence_count" and str(value) not in {"", "0"}:
                body += f'<td class="ok">{_e(value)}</td>'
            else:
                body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return (
        "<h3>Production target readiness gate</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_production_target_readiness(rows: list[dict[str, str]], limit: int = 20) -> str:
    if not rows:
        return ""
    headers = [
        "condition",
        "product_reaction_id",
        "product_name",
        "growth_coupling_label",
        "recommended_design_count",
        "semantic_readiness_label",
        "uniprot_evidence_label",
        "uniprot_reviewed_status",
        "uniprot_ec_status",
        "uniprot_cache_status",
        "enzyme_constraint_label",
        "kcat_evidence_tier",
        "kcat_evidence_label",
        "kcat_conflict_flag",
        "production_readiness_label",
        "readiness_reasons",
        "readiness_guidance",
    ]
    return _render_readiness_table("Product target readiness", rows, headers, limit)


def _render_production_design_readiness(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return ""
    headers = [
        "condition",
        "product_reaction_id",
        "candidate_reaction_id",
        "recommended_action",
        "action_confidence",
        "growth_loss_label",
        "semantic_readiness_label",
        "uniprot_evidence_label",
        "uniprot_reviewed_status",
        "uniprot_ec_status",
        "uniprot_cache_status",
        "enzyme_constraint_label",
        "kcat_evidence_tier",
        "kcat_evidence_label",
        "kcat_conflict_flag",
        "production_readiness_label",
        "readiness_reasons",
        "readiness_guidance",
    ]
    return _render_readiness_table("Reaction design readiness", rows, headers, limit)


def _render_production_gene_readiness(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return ""
    headers = [
        "condition",
        "product_reaction_id",
        "gene_id",
        "recommended_action",
        "action_confidence",
        "gpr_design_scope",
        "gene_mapping_status",
        "semantic_readiness_label",
        "uniprot_evidence_label",
        "uniprot_reviewed_status",
        "uniprot_ec_status",
        "uniprot_cache_status",
        "enzyme_constraint_label",
        "kcat_evidence_tier",
        "kcat_evidence_label",
        "kcat_conflict_flag",
        "production_readiness_label",
        "readiness_reasons",
        "readiness_guidance",
    ]
    return _render_readiness_table("Gene design readiness", rows, headers, limit)


def _render_readiness_table(
    title: str,
    rows: list[dict[str, str]],
    headers: list[str],
    limit: int,
) -> str:
    body = ""
    for row in rows[:limit]:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "production_readiness_label":
                klass = _readiness_class(value)
                body += f'<td class="{klass}">{_e(value)}</td>'
            else:
                body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return (
        f"<h3>{_e(title)}</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _readiness_class(label: str) -> str:
    if label == "stronger_evidence":
        return "ok"
    if label == "review_required":
        return "bad"
    if label == "usable_with_caution":
        return "warn"
    return ""


def _render_production_target_ranking(rows: list[dict[str, str]], limit: int = 12) -> str:
    if not rows:
        return "<p>No production target ranking rows.</p>"
    headers = [
        "condition",
        "product_reaction_id",
        "product_name",
        "max_product_flux_at_zero_growth",
        "max_product_flux_at_half_growth",
        "max_product_flux_at_high_growth",
        "growth_coupling_label",
        "fseof_candidate_count",
        "recommended_design_count",
        "oe_candidate_count",
        "kd_candidate_count",
        "ko_candidate_count",
        "semantic_label",
        "guidance",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header.startswith("max_product_flux"):
                value = _short_number(value)
            elif header == "semantic_label":
                klass = "bad" if value == "review_required" else "warn" if value in {"usable_with_caution", "inconclusive"} else "ok"
                body += f'<td class="{klass}">{_e(value)}</td>'
                continue
            body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return (
        "<h3>Product target ranking</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_production_design_targets(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return "<p>No production design target rows.</p>"
    headers = [
        "condition",
        "product_reaction_id",
        "candidate_reaction_id",
        "recommended_action",
        "action_confidence",
        "intervention_score",
        "growth_loss_label",
        "growth_loss_fraction",
        "semantic_label",
        "filter_status",
        "design_guidance",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header in {"intervention_score", "growth_loss_fraction"}:
                value = _short_number(value)
            elif header in {"recommended_action", "action_confidence", "filter_status"}:
                klass = "ok" if value in {"OE", "KO", "KD", "high", "recommended"} else "warn"
                body += f'<td class="{klass}">{_e(value)}</td>'
                continue
            body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return (
        "<h3>Production design targets</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_production_gene_targets(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return "<p>No production gene target rows.</p>"
    headers = [
        "condition",
        "product_reaction_id",
        "gene_id",
        "recommended_action",
        "action_confidence",
        "gene_target_score",
        "supporting_reaction_count",
        "supporting_reactions",
        "gpr_design_scope",
        "growth_loss_label",
        "gene_mapping_status",
        "design_guidance",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "gene_target_score":
                value = _short_number(value)
            elif header in {"recommended_action", "gene_mapping_status"}:
                klass = "ok" if value in {"OE", "KO", "KD", "mapped"} else "warn"
                body += f'<td class="{klass}">{_e(value)}</td>'
                continue
            body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return (
        "<h3>Production gene targets</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_production_gecko_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No GECKO/ecFactory production comparison has been generated.</p>"
    headers = [
        "status",
        "gecko_export_status",
        "gecko_external_status",
        "cobra_product_count",
        "cobra_design_count",
        "cobra_gene_target_count",
        "gecko_target_result_count",
        "gecko_design_result_count",
        "supported_design_count",
        "conflict_design_count",
        "guidance",
    ]
    body = ""
    for row in rows:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "status":
                klass = "ok" if value == "gecko_comparison_available" else "warn"
                body += f'<td class="{klass}">{_e(value)}</td>'
                continue
            body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return (
        "<h3>GECKO / ecFactory production comparison</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_production_gecko_target_comparison(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return "<p>No GECKO/ecFactory product target comparison rows.</p>"
    headers = [
        "condition",
        "product_reaction_id",
        "cobra_growth_coupling_label",
        "cobra_max_product_flux_at_high_growth",
        "gecko_max_product_flux",
        "flux_ratio_gecko_to_cobra",
        "comparison_label",
        "guidance",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header in {"cobra_max_product_flux_at_high_growth", "gecko_max_product_flux", "flux_ratio_gecko_to_cobra"}:
                value = _short_number(value)
            elif header == "comparison_label":
                klass = "ok" if value == "enzyme_constrained_supported" else "warn"
                body += f'<td class="{klass}">{_e(value)}</td>'
                continue
            body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return (
        "<h3>GECKO product target comparison</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_production_gecko_design_comparison(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return "<p>No GECKO/ecFactory design target comparison rows.</p>"
    headers = [
        "condition",
        "product_reaction_id",
        "target_level",
        "candidate_id",
        "cobra_action",
        "gecko_action",
        "cobra_score",
        "gecko_score",
        "comparison_label",
        "guidance",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header in {"cobra_score", "gecko_score"}:
                value = _short_number(value)
            elif header == "comparison_label":
                klass = "ok" if value == "supported_by_gecko_or_ecfactory" else "warn"
                body += f'<td class="{klass}">{_e(value)}</td>'
                continue
            body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return (
        "<h3>GECKO design target comparison</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_production_envelope(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return "<p>No production envelope rows.</p>"
    headers = [
        "condition",
        "product_reaction_id",
        "product_name",
        "biomass_fraction",
        "baseline_objective_value",
        "min_growth_requirement",
        "max_product_flux",
        "solve_status",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header in {"baseline_objective_value", "min_growth_requirement", "max_product_flux"}:
                value = _short_number(value)
            body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return (
        "<h3>Production envelope</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_fseof_lite_targets(rows: list[dict[str, str]], limit: int = 30) -> str:
    if not rows:
        return "<p>No FSEOF-lite candidate rows.</p>"
    headers = [
        "condition",
        "product_reaction_id",
        "candidate_reaction_id",
        "candidate_action",
        "recommended_action",
        "growth_loss_label",
        "trend_slope",
        "baseline_flux",
        "final_flux",
        "feasible_points",
        "semantic_label",
    ]
    body = ""
    for row in rows[:limit]:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header in {"trend_slope", "baseline_flux", "final_flux"}:
                value = _short_number(value)
            body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return (
        "<h3>FSEOF-lite candidate reactions</h3>"
        + "<table><thead><tr>"
        + "".join(f"<th>{_e(header)}</th>" for header in headers)
        + f"</tr></thead><tbody>{body}</tbody></table>"
    )


def _render_table(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>无数据。</p>"
    headers = list(rows[0].keys())
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in rows
    )
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_summary_table(rows: list[dict[str, str]], fraction_key: str) -> str:
    if not rows:
        return "<p>无摘要数据。</p>"
    headers = list(rows[0].keys())
    body = ""
    for row in rows:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == fraction_key:
                frac = _to_float(value)
                width = 0 if frac is None else max(0, min(100, frac * 100))
                body += f'<td>{_percent(value)}<div class="bar"><div class="fill" style="width:{width:.1f}%"></div></div></td>'
            else:
                body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_comparison_table(rows: list[dict[str, str]], limit: int = 12) -> str:
    if not rows:
        return "<p>无比较数据。</p>"
    headers = [
        "condition",
        "reaction_id",
        "measured_flux",
        "predicted_flux",
        "abs_residual",
        "within_ci",
        "unit",
    ]
    sorted_rows = sorted(rows, key=lambda row: _to_float(row.get("abs_residual")) or -1, reverse=True)[:limit]
    body = ""
    for row in sorted_rows:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "within_ci":
                klass = "ok" if value == "True" else "bad" if value == "False" else "warn"
                body += f'<td class="{klass}">{_e(value)}</td>'
            else:
                body += f"<td>{_e(_short_number(value))}</td>"
        body += "</tr>"
    return "<p>按绝对残差显示前几项。</p><table><thead><tr>" + "".join(
        f"<th>{_e(header)}</th>" for header in headers
    ) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_eflux_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No E-Flux result data.</p>"
    headers = [
        "condition",
        "status",
        "objective_value",
        "solution_source",
        "eflux_bounds_applied",
        "constrained_reaction_count",
        "measured_gpr_fraction",
    ]
    body = ""
    for row in rows:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "measured_gpr_fraction":
                value = _percent(value)
            elif header == "objective_value":
                value = _short_number(value)
            body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_delta_fba_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No delta-FBA-lite summary data.</p>"
    headers = [
        "condition_pair",
        "reference_solve_status",
        "target_solve_status",
        "expression_delta_count",
        "direction_comparable_count",
        "direction_agreement_fraction",
        "measured_delta_comparable_count",
        "mean_abs_delta_residual",
        "status",
    ]
    body = ""
    for row in rows:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "direction_agreement_fraction":
                value = _percent(value)
            elif header == "mean_abs_delta_residual":
                value = _short_number(value)
            body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_context_knockouts(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>没有 context knockout 数据。</p>"
    headers = ["condition", "reaction_id", "cobra_reaction_id", "decision", "reason"]
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in rows
    )
    return "<p>按当前轻量策略敲除的 delete candidates。</p><table><thead><tr>" + "".join(
        f"<th>{_e(header)}</th>" for header in headers
    ) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_troppo_selected(rows: list[dict[str, str]], limit: int = 16) -> str:
    if not rows:
        return "<p>No TROPPO FASTcore selected-reaction data.</p>"
    headers = ["condition", "reaction_id", "cobra_reaction_id", "role", "core_source"]
    display_rows = [row for row in rows if row.get("role") == "core"][:limit]
    if not display_rows:
        display_rows = rows[:limit]
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in display_rows
    )
    return "<p>Showing protected/core reactions from the reconstructed context models.</p><table><thead><tr>" + "".join(
        f"<th>{_e(header)}</th>" for header in headers
    ) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_troppo_method_matrix(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No TROPPO method matrix data.</p>"
    headers = [
        "method",
        "algorithm_class",
        "properties_class",
        "input_strategy",
        "execution_status",
        "entry_point",
    ]
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in rows
    )
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_troppo_method_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No TROPPO method input summary.</p>"
    headers = [
        "condition",
        "method",
        "implementation_status",
        "measured_gpr_fraction",
        "positive_input_count",
        "low_or_negative_input_count",
        "protected_reaction_count",
        "primary_input_property",
        "status",
    ]
    body = ""
    for row in rows:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "measured_gpr_fraction":
                value = _percent(value)
            body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_omics_quality(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No omics signal quality data.</p>"
    headers = [
        "condition",
        "signal_quality",
        "measured_gpr_fraction",
        "fastcore_candidate_count",
        "troppo_filtered_core_fraction",
        "supporting_fraction",
        "feasibility_status",
    ]
    body = ""
    for row in rows:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header.endswith("fraction"):
                value = _percent(value)
            body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_pipeline_steps(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No pipeline run data.</p>"
    headers = ["step_index", "step_id", "status", "message", "elapsed_seconds"]
    body = ""
    for row in rows:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "status":
                klass = _status_class(value)
                body += f'<td class="{klass}">{_e(value)}</td>'
            else:
                body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_backend_status(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No backend availability data.</p>"
    headers = ["backend", "available", "status", "detail", "path"]
    body = ""
    for row in rows:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "status":
                klass = "ok" if value == "available" else "warn"
                body += f'<td class="{klass}">{_e(value)}</td>'
            else:
                body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_model_qc(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No model QC data.</p>"
    headers = [
        "model_id",
        "qc_label",
        "baseline_fba_status",
        "baseline_objective_value",
        "reaction_count",
        "gpr_reaction_fraction",
        "blocked_reaction_fraction",
        "mass_imbalanced_reaction_fraction",
        "missing_formula_metabolite_fraction",
    ]
    body = ""
    for row in rows:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header.endswith("fraction"):
                value = _percent(value)
            elif header == "baseline_objective_value":
                value = _short_number(value)
            body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_model_qc_recommendations(rows: list[dict[str, str]], limit: int = 8) -> str:
    if not rows:
        return "<p>No model QC recommendations.</p>"
    headers = ["severity", "topic", "recommendation"]
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in rows[:limit]
    )
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_compartment_qc(rows: list[dict[str, str]], limit: int = 8) -> str:
    if not rows:
        return "<p>No compartment QC data.</p>"
    headers = ["compartment", "metabolite_count", "missing_formula_fraction", "missing_charge_fraction"]
    body = ""
    for row in rows[:limit]:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header.endswith("fraction"):
                value = _percent(value)
            body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_memote_run_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No MEMOTE external run data.</p>"
    headers = [
        "status",
        "model_exists",
        "memote_path",
        "report_html",
        "report_exists",
        "return_code",
        "message",
    ]
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in rows
    )
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_thermo_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No thermodynamic concentration data.</p>"
    headers = [
        "condition",
        "thermo_readiness",
        "metabolite_count",
        "mapped_fraction",
        "ready_concentration_count",
        "ready_concentration_fraction",
        "unsupported_unit_count",
        "invalid_bound_count",
        "compartment_count",
    ]
    body = ""
    for row in rows:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header.endswith("fraction"):
                value = _percent(value)
            body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_thermo_recommendations(rows: list[dict[str, str]], limit: int = 8) -> str:
    if not rows:
        return "<p>No thermodynamic recommendations.</p>"
    headers = ["condition", "severity", "topic", "recommendation"]
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in rows[:limit]
    )
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_pytfa_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No pyTFA export package data.</p>"
    headers = ["file_role", "path", "exists", "size_bytes"]
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(_short_number(row.get(header, '')) if header == 'size_bytes' else row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in rows
    )
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_pytfa_run_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No pyTFA external run data.</p>"
    headers = [
        "status",
        "package_status",
        "python_path",
        "cobra_available",
        "pytfa_available",
        "thermo_db",
        "thermo_db_exists",
        "return_code",
        "message",
    ]
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in rows
    )
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_enzyme_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No enzyme constraint data.</p>"
    headers = [
        "condition",
        "enzyme_readiness",
        "protein_count",
        "mapped_protein_fraction",
        "kcat_prior_count",
        "ready_capacity_fraction",
        "mean_kcat_confidence",
        "exceeds_capacity_count",
    ]
    body = ""
    for row in rows:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header.endswith("fraction") or header == "mean_kcat_confidence":
                value = _percent(value)
            body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_enzyme_recommendations(rows: list[dict[str, str]], limit: int = 8) -> str:
    if not rows:
        return "<p>No enzyme constraint recommendations.</p>"
    headers = ["condition", "severity", "topic", "recommendation"]
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in rows[:limit]
    )
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_enzyme_capacity(rows: list[dict[str, str]], limit: int = 12) -> str:
    if not rows:
        return "<p>No enzyme capacity rows.</p>"
    headers = [
        "condition",
        "reaction_id",
        "kcat_per_s",
        "protein_coverage",
        "limiting_abundance_mmol_per_gDW",
        "enzyme_capacity_mmol_per_gDW_per_h",
        "status",
    ]
    display_rows = rows[:limit]
    body = ""
    for row in display_rows:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "protein_coverage":
                value = _percent(value)
            elif header in {"kcat_per_s", "limiting_abundance_mmol_per_gDW", "enzyme_capacity_mmol_per_gDW_per_h"}:
                value = _short_number(value)
            body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_gecko_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No GECKO export package data.</p>"
    headers = ["file_role", "path", "exists", "size_bytes"]
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(_short_number(row.get(header, '')) if header == 'size_bytes' else row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in rows
    )
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_gecko_run_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No GECKO external run data.</p>"
    headers = ["status", "package_status", "matlab_path", "gecko_home", "gecko_home_exists", "return_code", "message"]
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in rows
    )
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_relative_protein_evidence(rows: list[dict[str, str]], limit: int = 12) -> str:
    if not rows:
        return "<p>No relative proteomics reaction evidence.</p>"
    headers = [
        "condition",
        "reaction_id",
        "reaction_score",
        "evidence",
        "gene_coverage",
        "measured_genes",
    ]
    display_rows = [
        row for row in rows if row.get("evidence") in {"high", "low"} and row.get("measured_gene_count") not in {"0", 0, ""}
    ][:limit]
    if not display_rows:
        display_rows = rows[:limit]
    body = ""
    for row in display_rows:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "gene_coverage":
                value = _percent(value)
            elif header == "reaction_score":
                value = _short_number(value)
            body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_multi_omics_conflict_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No multi-omics conflict summary.</p>"
    headers = [
        "condition",
        "comparable_reaction_count",
        "agreement_count",
        "partial_disagreement_count",
        "conflict_count",
        "conflict_fraction",
        "transcript_low_protein_high_count",
        "transcript_high_protein_low_count",
    ]
    body = ""
    for row in rows:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "conflict_fraction":
                value = _percent(value)
            body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_multi_omics_conflict_detail(rows: list[dict[str, str]], limit: int = 10) -> str:
    if not rows:
        return "<p>No comparable multi-omics conflict detail.</p>"
    headers = [
        "condition",
        "reaction_id",
        "transcript_evidence",
        "protein_evidence",
        "conflict_type",
        "recommendation",
    ]
    conflicts = [row for row in rows if row.get("status") == "conflict"]
    display_rows = (conflicts or rows)[:limit]
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in display_rows
    )
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_evidence_mode_delta_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No evidence-mode comparison summary.</p>"
    headers = [
        "condition",
        "reaction_delta_count",
        "evidence_change_count",
        "decision_change_count",
        "core_change_count",
        "conflict_softened_count",
        "delete_candidate_softened_count",
        "ml_consensus_disagreement_count",
        "ml_soft_prior_added_count",
        "relative_proteomics_missing_reaction_count",
    ]
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in rows
    )
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_condition_interpretation(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No condition-level interpretation dashboard.</p>"
    headers = [
        "condition",
        "interpretation_level",
        "primary_message",
        "signal_quality",
        "measured_gpr_fraction",
        "conflict_fraction",
        "conflict_softened_count",
        "ml_sample_status",
        "ml_cluster_id",
        "ml_consensus_disagreement_count",
        "ml_soft_prior_added_count",
        "relative_proteomics_status",
        "context_feasibility_status",
        "troppo_supporting_fraction",
        "risk_flags",
    ]
    body = ""
    for row in rows:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header.endswith("fraction"):
                value = _percent(value)
            elif header == "interpretation_level":
                klass = "bad" if str(value).startswith("red") else "warn" if str(value).startswith("yellow") else "ok"
                body += f'<td class="{klass}">{_e(value)}</td>'
                continue
            body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_condition_recommendations(rows: list[dict[str, str]], limit: int = 12) -> str:
    if not rows:
        return "<p>No condition-level interpretation recommendations.</p>"
    headers = ["condition", "severity", "topic", "recommendation"]
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in rows[:limit]
    )
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_evidence_mode_summary(rows: list[dict[str, str]]) -> str:
    if not rows:
        return "<p>No evidence-mode summary table.</p>"
    headers = [
        "evidence_mode",
        "condition",
        "status",
        "measured_gpr_fraction",
        "fastcore_core_count",
        "high_reaction_count",
        "medium_reaction_count",
        "low_reaction_count",
        "context_keep_count",
        "context_support_count",
        "context_delete_candidate_count",
    ]
    body = ""
    for row in rows:
        body += "<tr>"
        for header in headers:
            value = row.get(header, "")
            if header == "measured_gpr_fraction":
                value = _percent(value)
            body += f"<td>{_e(value)}</td>"
        body += "</tr>"
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_evidence_mode_deltas(rows: list[dict[str, str]], limit: int = 16) -> str:
    if not rows:
        return "<p>No reaction-level evidence-mode deltas.</p>"
    headers = [
        "condition",
        "reaction_id",
        "transcriptomics_evidence",
        "relative_proteomics_evidence",
        "consensus_evidence",
        "ml_derived_evidence",
        "transcriptomics_decision",
        "relative_proteomics_decision",
        "consensus_decision",
        "ml_derived_decision",
        "delta_status",
        "recommendation",
    ]
    priority = {
        "conflict_softened_by_consensus": 0,
        "delete_candidate_softened": 1,
        "core_membership_changed": 2,
        "ml_consensus_disagreement": 3,
        "ml_soft_prior_added": 4,
        "evidence_changed": 5,
        "context_decision_changed": 6,
    }
    display_rows = sorted(rows, key=lambda row: priority.get(row.get("delta_status", ""), 99))[:limit]
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in display_rows
    )
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_evidence_mode_recommendations(rows: list[dict[str, str]], limit: int = 10) -> str:
    if not rows:
        return "<p>No evidence-mode recommendations.</p>"
    headers = ["condition", "severity", "topic", "recommendation"]
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in rows[:limit]
    )
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _render_recommendations(rows: list[dict[str, str]], limit: int = 10) -> str:
    if not rows:
        return "<p>No omics QC recommendations.</p>"
    headers = ["condition", "severity", "topic", "recommendation"]
    body = "".join(
        "<tr>" + "".join(f"<td>{_e(row.get(header, ''))}</td>" for header in headers) + "</tr>"
        for row in rows[:limit]
    )
    return "<table><thead><tr>" + "".join(f"<th>{_e(header)}</th>" for header in headers) + f"</tr></thead><tbody>{body}</tbody></table>"


def _read_optional(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return read_csv_records(path)


def _read_variant_fba_results(root: Path) -> list[dict[str, str]]:
    index_path = root / "variant_fba_summary.csv"
    if index_path.exists() and index_path.stat().st_size > 0:
        return read_csv_records(index_path)
    if not root.exists():
        return []
    rows: list[dict[str, str]] = []
    for summary_path in sorted(root.glob("*/variant_fba_summary.csv")):
        rows.extend(read_csv_records(summary_path))
    return rows


def _read_json_optional(path: Path) -> dict[str, object]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _nested_value(data: dict[str, object], *keys: str) -> object:
    current: object = data
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key, "")
    return current


def _find_all(rows: list[dict[str, str]]) -> dict[str, str]:
    for row in rows:
        if row.get("condition") == "ALL":
            return row
    return {}


def _percent(value: object) -> str:
    number = _to_float(value)
    if number is None:
        return "NA"
    return f"{number * 100:.1f}%"


def _short_number(value: object) -> str:
    number = _to_float(value)
    if number is None:
        return str(value)
    return f"{number:.4g}"


def _to_float(value: object) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _status_class(value: object) -> str:
    text = str(value)
    if text in {"completed", "ready", "available"}:
        return "ok"
    if text in {"failed", "input_missing", "missing_outputs", "needs_repair"}:
        return "bad"
    return "warn"


def _e(value: object) -> str:
    return html.escape(str(value))
