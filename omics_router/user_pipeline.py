"""Minimal execution pipeline for staged user run packages."""

from __future__ import annotations

import json
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .cobra_runner import run_fba_workflow
from .constraints import (
    build_protein_abundance_table,
    build_gene_evidence_table,
    build_kcat_prior_table,
    build_reaction_expression_evidence,
    build_reaction_protein_evidence,
    build_relative_protein_evidence_table,
    parse_sbml_index,
    read_csv_records,
    read_package_input_map,
    resolve_package_input_path,
    split_context_method_inputs,
    write_csv,
    write_json,
)
from .context import build_context_reaction_policy, protected_reactions_from_outputs, split_context_policy
from .dlkcat_bridge import run_dlkcat_bridge
from .dlkcat_runner import run_dlkcat_external_workflow
from .evidence_comparison import run_evidence_mode_comparison
from .id_mapping import run_id_mapping_review
from .interpretation import run_condition_interpretation_dashboard
from .enzyme_constraints import run_enzyme_constraint_workflow
from .gecko_export import export_gecko_package
from .hybrid_graph_adapter import run_hybrid_graph_adapter
from .hybrid_runner import run_lightweight_hybrid_runner
from .hybrid_readiness import run_readiness_hybrid_export
from .ml_analysis import run_ml_analysis
from .ml_features import run_ml_feature_matrix
from .minn_export import run_minn_export
from .kcat_prior_merge import run_kcat_prior_merge
from .model_qc import run_model_qc_workflow
from .model_generation import (
    build_analysis_variant_context,
    normalize_analysis_parameters,
    normalize_analysis_modules,
    normalize_model_generation_parameters,
    normalize_model_generation_methods,
    normalize_selected_model_variant_ids,
    read_model_variant_registry,
    safe_variant_dir_name,
    write_analysis_parameters,
    write_model_generation_parameters,
    write_analysis_variant_context,
    write_analysis_selection,
    write_context_model_artifacts,
    write_model_variant_registry,
)
from .omics_conflict import build_multi_omics_conflict_tables
from .pipeline import build_backend_status, build_pipeline_message, classify_pipeline_status
from .production_analysis import prepare_production_targets_from_package, run_production_analysis
from .production_gecko_bridge import run_production_gecko_bridge
from .production_readiness import run_production_readiness_gate
from .report import build_cobra_report
from .report_builder import build_report_bundle
from .transcriptomics_flux import run_transcriptomics_flux_workflow
from .troppo_runner import run_troppo_fastcore_workflow
from .uniprot_model_check import run_uniprot_model_check
from .variant_comparison import run_variant_comparison


@dataclass(slots=True)
class UserPipelineResult:
    """Summary returned after running a staged user package."""

    status: str
    package_dir: str
    message: str
    files: dict[str, str]
    step_rows: list[dict[str, object]]


@dataclass(slots=True)
class SimpleStepResult:
    """Small result object for internally skipped custom steps."""

    status: str
    message: str


def run_user_package_minimal(
    package_dir: str | Path,
    require_cobra: bool = False,
    run_pfba: bool = True,
    run_fva: bool = False,
    run_eflux: bool = True,
    run_troppo: bool = True,
    run_evidence_comparison_step: bool = True,
    enable_uniprot_rest: bool = False,
    run_dlkcat_external: bool = False,
    model_generation_methods: list[str] | str | None = None,
    analysis_modules: list[str] | str | None = None,
    selected_model_variant_id: list[str] | str | None = "",
    report_preset: str = "full_audit_report",
    analysis_parameters: dict[str, Any] | None = None,
    model_generation_parameters: dict[str, Any] | None = None,
    gecko_adapter_parameters: dict[str, Any] | None = None,
    gecko_ec_model_mode: str = "full_ecModel",
) -> UserPipelineResult:
    """Run a staged user workflow with explicit model-generation and analysis selections."""

    package = Path(package_dir)
    pipeline_dir = package / "pipeline_results"
    workflow_dir = package / "workflow_results"
    constraints_dir = package / "generated_constraints"
    model_qc_dir = package / "model_qc_results"
    uniprot_model_check_dir = package / "uniprot_model_check"
    dlkcat_results_dir = package / "dlkcat_results"
    id_mapping_dir = package / "id_mapping_results"
    cobra_results_dir = package / "cobra_results"
    variant_cobra_results_dir = package / "variant_cobra_results"
    variant_comparison_dir = package / "variant_comparison"
    report_results_dir = package / "report_results"
    transcriptomics_flux_dir = package / "transcriptomics_flux_results"
    troppo_dir = package / "troppo_results"
    evidence_mode_dir = package / "evidence_mode_results"
    interpretation_dir = package / "interpretation_results"
    ml_results_dir = package / "ml_results"
    minn_export_dir = package / "minn_export"
    hybrid_results_dir = package / "hybrid_results"
    hybrid_adapter_dir = package / "hybrid_adapter_results"
    production_results_dir = package / "production_results"
    enzyme_results_dir = package / "enzyme_results"
    gecko_package_dir = package / "gecko_package"
    gecko_run_dir = package / "gecko_run_results"
    selected_model_generation_methods = normalize_model_generation_methods(model_generation_methods)
    selected_analysis_modules = normalize_analysis_modules(analysis_modules)
    selected_model_variant_ids = normalize_selected_model_variant_ids(selected_model_variant_id)
    resolved_model_generation_parameters = normalize_model_generation_parameters(model_generation_parameters)
    resolved_analysis_parameters = normalize_analysis_parameters(
        analysis_parameters,
        run_pfba=run_pfba,
        run_fva=run_fva,
        enable_uniprot_rest=enable_uniprot_rest,
        run_dlkcat_external=run_dlkcat_external,
    )
    eflux_generation_parameters = resolved_model_generation_parameters["eflux"]
    fastcore_generation_parameters = resolved_model_generation_parameters["fastcore"]
    gecko_generation_parameters = resolved_model_generation_parameters["enzyme_gecko"]
    fba_parameters = resolved_analysis_parameters["fba_pfba"]
    eflux_parameters = resolved_analysis_parameters["eflux_delta_fba"]
    ml_parameters = resolved_analysis_parameters["ml_pca_lasso"]
    production_parameters = resolved_analysis_parameters["production_ecfactory"]
    run_pfba = bool(fba_parameters["run_pfba"])
    run_fva = bool(fba_parameters["run_fva"])
    fva_fraction_of_optimum = float(fba_parameters["fva_fraction_of_optimum"])
    run_eflux_pfba = bool(eflux_parameters["run_pfba"])
    if "run_pfba" in eflux_generation_parameters:
        run_eflux_pfba = bool(eflux_generation_parameters["run_pfba"])
    enable_uniprot_rest = bool(resolved_analysis_parameters["uniprot_model_check"]["enable_uniprot_rest"])
    run_dlkcat_external = bool(resolved_analysis_parameters["dlkcat_external"]["run_dlkcat_external"])
    gecko_ec_model_mode = str(gecko_ec_model_mode or gecko_generation_parameters.get("ec_model_mode") or "full_ecModel")
    primary_selected_model_variant_id = selected_model_variant_ids[0] if selected_model_variant_ids else ""
    selected_model_generation_set = set(selected_model_generation_methods)
    selected_analysis_set = set(selected_analysis_modules)
    needs_transcriptomics_model = bool(
        {"eflux", "fastcore", "consensus_evidence"} & selected_model_generation_set
        or {"eflux_delta_fba", "evidence_comparison"} & selected_analysis_set
    )
    needs_fastcore_model = "fastcore" in selected_model_generation_set
    needs_consensus_model = "consensus_evidence" in selected_model_generation_set or "evidence_comparison" in selected_analysis_set
    needs_enzyme_model = "enzyme_gecko" in selected_model_generation_set
    needs_fba_analysis = "fba_pfba" in selected_analysis_set
    needs_ml_analysis = bool({"ml_pca_lasso", "evidence_comparison", "minn_export", "hybrid_minn", "hybrid_graph_adapter"} & selected_analysis_set)
    needs_condition_interpretation = "condition_interpretation" in selected_analysis_set
    needs_production_analysis = bool({"production_ecfactory", "readiness_gate", "hybrid_minn", "hybrid_graph_adapter"} & selected_analysis_set)
    needs_readiness_gate = bool({"readiness_gate", "hybrid_minn", "hybrid_graph_adapter"} & selected_analysis_set)
    needs_minn_export = bool({"minn_export", "hybrid_minn", "hybrid_graph_adapter"} & selected_analysis_set)
    needs_hybrid_runner = "hybrid_minn" in selected_analysis_set
    needs_hybrid_adapter = "hybrid_graph_adapter" in selected_analysis_set
    for directory in (
        pipeline_dir,
        workflow_dir,
        constraints_dir,
        model_qc_dir,
        uniprot_model_check_dir,
        dlkcat_results_dir,
        id_mapping_dir,
        cobra_results_dir,
        variant_cobra_results_dir,
        variant_comparison_dir,
        report_results_dir,
        transcriptomics_flux_dir,
        troppo_dir,
        evidence_mode_dir,
        interpretation_dir,
        ml_results_dir,
        minn_export_dir,
        hybrid_results_dir,
        hybrid_adapter_dir,
        production_results_dir,
        enzyme_results_dir,
        gecko_package_dir,
        gecko_run_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    step_rows: list[dict[str, object]] = []
    write_custom_input_overview(package, pipeline_dir)
    write_analysis_selection(
        workflow_dir,
        selected_model_generation_methods=selected_model_generation_methods,
        selected_analysis_modules=selected_analysis_modules,
        selected_model_variant_id=selected_model_variant_id,
        report_preset=report_preset,
        selected_report_variant_ids=selected_model_variant_ids,
    )
    write_analysis_parameters(workflow_dir, resolved_analysis_parameters)
    write_model_generation_parameters(workflow_dir, resolved_model_generation_parameters)
    model_path = find_staged_model_path(package)
    if model_path is None:
        step_rows.append(
            build_step_row(
                step_index=1,
                step_id="input_check",
                status="input_missing",
                message="No staged model file was found in the user package.",
            )
        )
        return finalize_user_pipeline(package, pipeline_dir, step_rows, status_override="failed")

    exchange_bounds_path = prepare_exchange_bounds(package, constraints_dir)
    flux_targets_path = constraints_dir / "flux_validation_targets.csv"
    if not flux_targets_path.exists():
        write_csv(flux_targets_path, [])
    production_targets_path = constraints_dir / "production_targets.csv"
    if not production_targets_path.exists():
        write_csv(production_targets_path, [])

    step_rows.append(
        build_step_row(
            step_index=1,
            step_id="input_check",
            status="completed",
            message="Located staged model and prepared condition exchange bounds.",
        )
    )

    step_rows.append(
        run_callable_step(
            step_index=2,
            step_id="id_mapping",
            label="Review uploaded identifier mapping",
            callback=lambda: run_id_mapping_review(package, id_mapping_dir),
        )
    )

    step_rows.append(
        run_callable_step(
            step_index=3,
            step_id="model_qc",
            label="Run lightweight model QC",
            callback=lambda: run_model_qc_workflow(
                model_path=model_path,
                output_dir=model_qc_dir,
                require_cobra=require_cobra,
                run_blocked_check=False,
                run_mass_balance_check=True,
            ),
        )
    )

    step_rows.append(
        run_callable_step(
            step_index=4,
            step_id="uniprot_model_check",
            label="Run local UniProt / GPR model check",
            callback=lambda: run_uniprot_model_check(
                model_path=model_path,
                package_dir=package,
                output_dir=uniprot_model_check_dir,
                enable_uniprot_rest=enable_uniprot_rest,
                uniprot_cache_dir=package / "uniprot_cache",
            ),
        )
    )

    step_rows.append(
        run_callable_step(
            step_index=5,
            step_id="dlkcat_bridge",
            label="Prepare DLKcat kcat prediction bridge",
            callback=lambda: run_dlkcat_bridge(
                model_path=model_path,
                package_dir=package,
                output_dir=dlkcat_results_dir,
            ),
        )
    )

    step_rows.append(
        run_callable_step(
            step_index=6,
            step_id="dlkcat_external_run",
            label="Optionally run external GECKO/DLKcat prediction",
            callback=lambda: run_dlkcat_external_workflow(
                dlkcat_results_dir=dlkcat_results_dir,
                model_path=model_path,
                package_dir=package,
                enabled=run_dlkcat_external,
            ),
        )
    )

    step_rows.append(
        run_callable_step(
            step_index=7,
            step_id="kcat_prior_merge",
            label="Merge kcat priors and DLKcat predictions",
            callback=lambda: run_kcat_prior_merge(
                package_dir=package,
                model_path=model_path,
                output_dir=constraints_dir,
                dlkcat_results_dir=dlkcat_results_dir,
            ),
        )
    )

    step_rows.append(
        (
            run_callable_step(
                step_index=8,
                step_id="enzyme_gecko_export",
                label="Generate enzyme-capacity / GECKO-ready model variant",
                callback=lambda: run_custom_enzyme_gecko_export(
                    package_dir=package,
                    model_path=model_path,
                    constraints_dir=constraints_dir,
                    enzyme_results_dir=enzyme_results_dir,
                    gecko_package_dir=gecko_package_dir,
                    gecko_adapter_parameters=gecko_adapter_parameters,
                    gecko_ec_model_mode=gecko_ec_model_mode,
                ),
            )
            if needs_enzyme_model
            else build_not_selected_row(
                8,
                "enzyme_gecko_export",
                "Enzyme-capacity / GECKO-ready model generation was not selected.",
                label="Generate enzyme-capacity / GECKO-ready model variant",
            )
        )
    )

    step_rows.append(
        (
            run_transcriptomics_step(
                step_index=9,
                package_dir=package,
                model_path=model_path,
                constraints_dir=constraints_dir,
                output_dir=transcriptomics_flux_dir,
                require_cobra=require_cobra,
                run_pfba=run_eflux_pfba,
                min_expression_fraction=float(eflux_generation_parameters["min_expression_fraction"]),
                reference_condition=str(eflux_parameters.get("reference_condition") or eflux_generation_parameters.get("reference_condition") or ""),
                up_log2_threshold=float(eflux_parameters.get("up_log2_threshold") or eflux_generation_parameters.get("up_log2_threshold") or 1.0),
                down_log2_threshold=float(eflux_parameters.get("down_log2_threshold") or eflux_generation_parameters.get("down_log2_threshold") or -1.0),
                enabled=run_eflux,
            )
            if needs_transcriptomics_model
            else build_not_selected_row(
                9,
                "transcriptomics_flux",
                "E-Flux / transcriptomics model generation was not selected.",
                label="Generate / analyze E-Flux transcriptomics model variant",
            )
        )
    )

    step_rows.append(
        (
            run_callable_step(
                step_index=10,
                step_id="troppo_fastcore",
                label="Generate TROPPO FASTcore context model variant",
                callback=lambda: run_custom_troppo_fastcore(
                    package_dir=package,
                    model_path=model_path,
                    constraints_dir=constraints_dir,
                    output_dir=troppo_dir,
                    solver=str(fastcore_generation_parameters["solver"]),
                    flux_threshold=float(fastcore_generation_parameters["flux_threshold"]),
                    protect_objective=bool(fastcore_generation_parameters["protect_objective"]),
                    protect_exchange_bounds=bool(fastcore_generation_parameters["protect_exchange_bounds"]),
                    filter_inactive_core=bool(fastcore_generation_parameters["filter_inactive_core"]),
                    run_feasibility_check=bool(fastcore_generation_parameters["run_feasibility_check"]),
                    enabled=run_troppo,
                ),
            )
            if needs_fastcore_model
            else build_not_selected_row(
                10,
                "troppo_fastcore",
                "TROPPO FASTcore model generation was not selected.",
                label="Generate TROPPO FASTcore context model variant",
            )
        )
    )

    step_rows.append(
        (
            run_callable_step(
                step_index=11,
                step_id="ml_feature_matrix",
                label="Build ML + GEM feature matrix",
                callback=lambda: run_ml_feature_matrix(package, ml_results_dir),
            )
            if needs_ml_analysis
            else build_not_selected_row(
                11,
                "ml_feature_matrix",
                "ML feature matrix analysis was not selected.",
                label="Build ML + GEM feature matrix",
            )
        )
    )

    step_rows.append(
        (
            run_callable_step(
                step_index=12,
                step_id="ml_analysis",
                label="Run selected ML PCA / LASSO-lite analysis",
                callback=lambda: run_ml_analysis(
                    package,
                    ml_results_dir,
                    min_overlap=int(ml_parameters["min_overlap"]),
                    prior_threshold=float(ml_parameters["prior_threshold"]),
                    max_clusters=int(ml_parameters["max_clusters"]),
                    max_lasso_features=int(ml_parameters["max_lasso_features"]),
                ),
            )
            if needs_ml_analysis
            else build_not_selected_row(
                12,
                "ml_analysis",
                "ML PCA / LASSO-lite analysis was not selected.",
                label="Run selected ML PCA / LASSO-lite analysis",
            )
        )
    )

    step_rows.append(
        (
            run_callable_step(
                step_index=13,
                step_id="evidence_mode_comparison",
                label="Generate / compare consensus evidence model variants",
                callback=lambda: run_custom_evidence_mode_comparison(
                    package_dir=package,
                    model_path=model_path,
                    constraints_dir=constraints_dir,
                    output_dir=evidence_mode_dir,
                    enabled=run_evidence_comparison_step,
                ),
            )
            if needs_consensus_model
            else build_not_selected_row(
                13,
                "evidence_mode_comparison",
                "Consensus evidence model generation / Evidence Mode Comparison was not selected.",
                label="Generate / compare consensus evidence model variants",
            )
        )
    )

    step_rows.append(
        run_callable_step(
            step_index=14,
            step_id="context_model_artifacts",
            label="Build standardized context model artifact packages",
            callback=lambda: write_context_model_artifacts(
                workflow_dir,
                package_dir=package,
                model_path=model_path,
                constraints_dir=constraints_dir,
                troppo_dir=troppo_dir,
                selected_methods=selected_model_generation_methods,
            ),
        )
    )

    step_rows.append(
        run_callable_step(
            step_index=15,
            step_id="model_variant_registry",
            label="Register generated model variants for downstream analysis",
            callback=lambda: write_model_variant_registry(
                workflow_dir,
                package_dir=package,
                model_path=model_path,
                constraints_dir=constraints_dir,
                cobra_results_dir=cobra_results_dir,
                transcriptomics_flux_dir=transcriptomics_flux_dir,
                troppo_dir=troppo_dir,
                evidence_mode_dir=evidence_mode_dir,
                enzyme_results_dir=enzyme_results_dir,
                gecko_package_dir=gecko_package_dir,
                model_artifacts_dir=workflow_dir / "model_artifacts",
                selected_methods=selected_model_generation_methods,
            ),
        )
    )
    model_variant_registry_rows = read_model_variant_registry(package)
    analysis_variant_context_rows = build_analysis_variant_context(
        model_variant_registry_rows,
        selected_analysis_modules=selected_analysis_modules,
        selected_model_variant_id=primary_selected_model_variant_id,
    )
    step_rows.append(
        run_callable_step(
            step_index=16,
            step_id="analysis_variant_context",
            label="Resolve active model variant for selected analyses",
            callback=lambda: write_analysis_variant_context(workflow_dir, analysis_variant_context_rows),
        )
    )
    analysis_compatible = {
        str(row.get("analysis_module", "")): str(row.get("compatible", "")).lower() == "true"
        for row in analysis_variant_context_rows
    }
    active_variant_id = analysis_active_variant_id(analysis_variant_context_rows) or "baseline_gem__default"
    fba_model_path = analysis_active_model_path(analysis_variant_context_rows, model_path, module_id="fba_pfba")
    production_model_path = analysis_active_model_path(
        analysis_variant_context_rows,
        model_path,
        module_id="production_ecfactory",
    )
    fba_variant_ids = selected_model_variant_ids or ([active_variant_id] if active_variant_id else [])

    step_rows.append(
        (
            run_callable_step(
                step_index=17,
                step_id="cobra",
                label="Run selected variant FBA / pFBA analysis",
                callback=lambda: run_batch_variant_fba_workflow(
                    registry_rows=model_variant_registry_rows,
                    selected_variant_ids=fba_variant_ids,
                    selected_analysis_modules=selected_analysis_modules,
                    fallback_model_path=model_path,
                    exchange_bounds_path=exchange_bounds_path,
                    flux_targets_path=flux_targets_path,
                    variant_results_root=variant_cobra_results_dir,
                    require_cobra=require_cobra,
                    run_pfba=run_pfba,
                    run_fva=run_fva,
                    fva_fraction_of_optimum=fva_fraction_of_optimum,
                    objective_reaction_id=str(fba_parameters.get("objective_reaction_id") or ""),
                    objective_direction=str(fba_parameters.get("objective_direction") or "max"),
                    fva_reaction_scope=str(fba_parameters.get("fva_reaction_scope") or "targets"),
                    loopless=bool(fba_parameters.get("loopless")),
                    pfba_factor=fba_parameters.get("pfba_factor"),
                    fva_processes=int(fba_parameters.get("fva_processes") or 1),
                ),
            )
            if needs_fba_analysis
            else build_not_selected_row(
                17,
                "cobra",
                analysis_skip_message("fba_pfba", needs_fba_analysis, analysis_compatible, analysis_variant_context_rows),
                label="Run selected variant FBA / pFBA analysis",
            )
        )
    )

    step_rows.append(
        run_callable_step(
            step_index=18,
            step_id="condition_interpretation",
            label="Build condition-level interpretation dashboard",
            callback=lambda: run_condition_interpretation_dashboard(
                constraints_dir=constraints_dir,
                evidence_mode_results_dir=evidence_mode_dir,
                context_results_dir=package / "context_results",
                troppo_results_dir=troppo_dir,
                ml_results_dir=ml_results_dir,
                output_dir=interpretation_dir,
            ),
        )
        if needs_condition_interpretation and analysis_compatible.get("condition_interpretation", True)
        else build_not_selected_row(
            18,
            "condition_interpretation",
            analysis_skip_message(
                "condition_interpretation",
                needs_condition_interpretation,
                analysis_compatible,
                analysis_variant_context_rows,
            ),
            label="Build condition-level interpretation dashboard",
        )
    )

    step_rows.append(
        (
            run_callable_step(
                step_index=19,
                step_id="minn_export",
                label="Export selected MINN-style graph, feature tensor, and labels",
                callback=lambda: run_minn_export(
                    model_path=model_path,
                    package_dir=package,
                    output_dir=minn_export_dir,
                ),
            )
            if needs_minn_export and analysis_compatible.get("minn_export", True)
            else build_not_selected_row(
                19,
                "minn_export",
                analysis_skip_message("minn_export", needs_minn_export, analysis_compatible, analysis_variant_context_rows),
                label="Export selected MINN-style graph, feature tensor, and labels",
            )
        )
    )

    step_rows.append(
        (
            run_callable_step(
                step_index=20,
                step_id="production_analysis",
                label="Run selected Production Analysis / ecFactory-lite",
                callback=lambda: run_production_analysis(
                    model_path=production_model_path,
                    exchange_bounds_path=exchange_bounds_path,
                    production_targets_path=prepare_production_targets_from_package(
                        package,
                        production_model_path,
                        production_targets_path,
                    ),
                    output_dir=production_results_dir,
                    uniprot_model_check_dir=uniprot_model_check_dir,
                    require_cobra=require_cobra,
                    biomass_fractions=list(production_parameters["biomass_fractions"]),
                    fseof_fractions=list(production_parameters["fseof_fractions"]),
                    max_fseof_candidates=int(production_parameters.get("max_candidates") or 200),
                    max_growth_impact_candidates=int(production_parameters.get("max_growth_impact_candidates") or 80),
                ),
            )
            if needs_production_analysis and analysis_compatible.get("production_ecfactory", True)
            else build_not_selected_row(
                20,
                "production_analysis",
                analysis_skip_message(
                    "production_ecfactory",
                    needs_production_analysis,
                    analysis_compatible,
                    analysis_variant_context_rows,
                ),
                label="Run selected Production Analysis / ecFactory-lite",
            )
        )
    )

    step_rows.append(
        (
            run_callable_step(
                step_index=21,
                step_id="production_gecko_bridge",
                label="Compare production targets with GECKO / ecFactory outputs",
                callback=lambda: run_production_gecko_bridge(
                    production_results_dir=production_results_dir,
                    gecko_package_dir=gecko_package_dir,
                    gecko_run_dir=gecko_run_dir,
                    output_dir=production_results_dir,
                ),
            )
            if needs_production_analysis and analysis_compatible.get("production_ecfactory", True)
            else build_not_selected_row(
                21,
                "production_gecko_bridge",
                analysis_skip_message(
                    "production_ecfactory",
                    needs_production_analysis,
                    analysis_compatible,
                    analysis_variant_context_rows,
                ),
                label="Compare production targets with GECKO / ecFactory outputs",
            )
        )
    )

    step_rows.append(
        (
            run_callable_step(
                step_index=22,
                step_id="production_readiness_gate",
                label="Grade production targets with semantic and enzyme-constrained evidence",
                callback=lambda: run_production_readiness_gate(
                    production_results_dir=production_results_dir,
                    uniprot_model_check_dir=uniprot_model_check_dir,
                    output_dir=production_results_dir,
                ),
            )
            if needs_readiness_gate and analysis_compatible.get("readiness_gate", True)
            else build_not_selected_row(
                22,
                "production_readiness_gate",
                analysis_skip_message("readiness_gate", needs_readiness_gate, analysis_compatible, analysis_variant_context_rows),
                label="Grade production targets with semantic and enzyme-constrained evidence",
            )
        )
    )

    step_rows.append(
        (
            run_callable_step(
                step_index=23,
                step_id="readiness_hybrid_export",
                label="Export readiness-aware ML/GEM hybrid target priors",
                callback=lambda: run_readiness_hybrid_export(
                    package_dir=package,
                    output_dir=minn_export_dir,
                ),
            )
            if (needs_hybrid_runner or needs_hybrid_adapter)
            and (analysis_compatible.get("hybrid_minn", True) or analysis_compatible.get("hybrid_graph_adapter", True))
            else build_not_selected_row(
                23,
                "readiness_hybrid_export",
                analysis_skip_message("hybrid_minn", needs_hybrid_runner, analysis_compatible, analysis_variant_context_rows),
                label="Export readiness-aware ML/GEM hybrid target priors",
            )
        )
    )

    step_rows.append(
        (
            run_callable_step(
                step_index=24,
                step_id="lightweight_hybrid_runner",
                label="Run selected lightweight ML/GEM hybrid baseline scorer",
                callback=lambda: run_lightweight_hybrid_runner(
                    package_dir=package,
                    output_dir=hybrid_results_dir,
                ),
            )
            if needs_hybrid_runner and analysis_compatible.get("hybrid_minn", True)
            else build_not_selected_row(
                24,
                "lightweight_hybrid_runner",
                analysis_skip_message("hybrid_minn", needs_hybrid_runner, analysis_compatible, analysis_variant_context_rows),
                label="Run selected lightweight ML/GEM hybrid baseline scorer",
            )
        )
    )

    step_rows.append(
        (
            run_callable_step(
                step_index=25,
                step_id="hybrid_graph_adapter",
                label="Build selected PyG/DGL hybrid graph adapter dry-run package",
                callback=lambda: run_hybrid_graph_adapter(
                    package_dir=package,
                    output_dir=hybrid_adapter_dir,
                ),
            )
            if needs_hybrid_adapter and analysis_compatible.get("hybrid_graph_adapter", True)
            else build_not_selected_row(
                25,
                "hybrid_graph_adapter",
                analysis_skip_message(
                    "hybrid_graph_adapter",
                    needs_hybrid_adapter,
                    analysis_compatible,
                    analysis_variant_context_rows,
                ),
                label="Build selected PyG/DGL hybrid graph adapter dry-run package",
            )
        )
    )

    step_rows.append(
        run_callable_step(
            step_index=26,
            step_id="variant_comparison",
            label="Build multi-variant comparison tables",
            callback=lambda: run_variant_comparison(package, variant_comparison_dir),
        )
    )

    step_rows.append(
        run_callable_step(
            step_index=27,
            step_id="report",
            label="Build selected report bundle",
            callback=lambda: build_custom_report_outputs(
                package_dir=package,
                cobra_results_dir=cobra_results_dir,
                report_preset=report_preset,
                active_variant_id=selected_model_variant_ids or [active_variant_id],
            ),
        )
    )

    return finalize_user_pipeline(package, pipeline_dir, step_rows)


def find_staged_model_path(package_dir: str | Path) -> Path | None:
    """Return the staged model path from input_file_map.csv."""

    package = Path(package_dir)
    for row in read_input_map(package):
        if row.get("kind") == "model":
            path = resolve_package_input_path(package, row)
            if path is not None:
                return path
    return None


def prepare_exchange_bounds(package_dir: str | Path, constraints_dir: str | Path) -> Path:
    """Copy staged condition exchange bounds into the constraints directory."""

    package = Path(package_dir)
    output = Path(constraints_dir) / "exchange_bounds.csv"
    input_rows = [*read_normalized_input_map(package), *read_input_map(package)]
    condition_bounds = [
        row
        for row in input_rows
        if row.get("kind") == "condition_table" and row.get("role") == "condition_exchange_bounds"
    ]
    if condition_bounds:
        source_text = condition_bounds[0].get("path", "")
        source = Path(source_text) if source_text else Path()
        if source_text and source.exists():
            output.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, output)
            return output
    write_csv(output, [])
    return output


def find_staged_omics_path(package_dir: str | Path, role: str) -> Path | None:
    """Return the first staged omics table matching a role."""

    package = Path(package_dir)
    for row in [*read_normalized_input_map(package), *read_input_map(package)]:
        if row.get("kind") == "omics_table" and row.get("role") == role:
            path = resolve_package_input_path(package, row)
            if path is not None:
                return path
    return None


def prepare_transcriptomics_constraints(
    package_dir: str | Path,
    model_path: str | Path,
    constraints_dir: str | Path,
) -> dict[str, object]:
    """Build transcriptomics gene and reaction evidence for a user package."""

    package = Path(package_dir)
    output = Path(constraints_dir)
    transcriptomics_path = find_staged_omics_path(package, "transcriptomics")
    if transcriptomics_path is None:
        return {
            "status": "skipped",
            "message": "No transcriptomics table is attached to this user package.",
            "files": {},
        }

    model_index = parse_sbml_index(model_path)
    gene_rows = build_gene_evidence_table(transcriptomics_path, model_index=model_index)
    gene_path = output / "gene_expression_evidence.csv"
    reaction_path = output / "reaction_expression_evidence.csv"
    write_csv(gene_path, gene_rows)
    reaction_rows = build_reaction_expression_evidence(gene_path, model_path)
    write_csv(reaction_path, reaction_rows)
    return {
        "status": "completed",
        "message": f"Prepared transcriptomics evidence for {len(reaction_rows)} reaction-condition rows.",
        "files": {
            "gene_expression_evidence": str(gene_path),
            "reaction_expression_evidence": str(reaction_path),
            "transcriptomics_input": str(transcriptomics_path),
        },
    }


def prepare_relative_proteomics_constraints(
    package_dir: str | Path,
    model_path: str | Path,
    constraints_dir: str | Path,
) -> dict[str, object]:
    """Build relative protein and reaction evidence for a user package."""

    package = Path(package_dir)
    output = Path(constraints_dir)
    proteomics_path = find_staged_omics_path(package, "relative_proteomics")
    if proteomics_path is None:
        return {
            "status": "skipped",
            "message": "No relative proteomics table is attached to this user package.",
            "files": {},
        }

    model_index = parse_sbml_index(model_path)
    protein_rows = build_relative_protein_evidence_table(proteomics_path, model_index=model_index)
    protein_path = output / "relative_protein_evidence.csv"
    reaction_path = output / "relative_protein_reaction_evidence.csv"
    write_csv(protein_path, protein_rows)
    reaction_rows = build_reaction_protein_evidence(protein_path, model_path)
    write_csv(reaction_path, reaction_rows)
    return {
        "status": "completed",
        "message": f"Prepared relative proteomics evidence for {len(reaction_rows)} reaction-condition rows.",
        "files": {
            "relative_protein_evidence": str(protein_path),
            "relative_protein_reaction_evidence": str(reaction_path),
            "relative_proteomics_input": str(proteomics_path),
        },
    }


def run_custom_enzyme_gecko_export(
    package_dir: str | Path,
    model_path: str | Path,
    constraints_dir: str | Path,
    enzyme_results_dir: str | Path,
    gecko_package_dir: str | Path,
    gecko_adapter_parameters: dict[str, Any] | None = None,
    gecko_ec_model_mode: str = "full_ecModel",
) -> Any:
    """Build enzyme-capacity QC and GECKO export package when inputs exist."""

    package = Path(package_dir)
    constraints = Path(constraints_dir)
    enzyme_output = Path(enzyme_results_dir)
    gecko_output = Path(gecko_package_dir)
    proteomics_path = find_staged_omics_path(package, "absolute_proteomics")
    if proteomics_path is None:
        return SimpleStepResult("skipped", "No absolute proteomics table is attached; enzyme/GECKO export skipped.")

    kcat_priors_path = constraints / "kcat_priors.csv"
    if not kcat_priors_path.exists() or kcat_priors_path.stat().st_size == 0:
        return SimpleStepResult("skipped", "No merged kcat priors are available; enzyme/GECKO export skipped.")

    model_index = parse_sbml_index(model_path)
    protein_rows = build_protein_abundance_table(proteomics_path, model_index=model_index)
    protein_path = constraints / "protein_abundance.csv"
    write_csv(protein_path, protein_rows)
    if not protein_rows:
        return SimpleStepResult("skipped", "Absolute proteomics table did not yield protein abundance rows.")

    enzyme_result = run_enzyme_constraint_workflow(
        model_path=model_path,
        protein_abundance_path=protein_path,
        kcat_priors_path=kcat_priors_path,
        output_dir=enzyme_output,
        predicted_fluxes_path=constraints / "flux_validation_targets.csv",
    )
    gecko_result = export_gecko_package(
        model_path=model_path,
        protein_abundance_path=protein_path,
        kcat_priors_path=kcat_priors_path,
        enzyme_results_dir=enzyme_output,
        output_dir=gecko_output,
        model_id=model_index.model_id or "custom_model",
        adapter_parameters=gecko_adapter_parameters,
        ec_model_mode=gecko_ec_model_mode,
    )
    return SimpleStepResult(
        "completed",
        f"{enzyme_result.message} {gecko_result.message}",
    )


def prepare_fastcore_inputs(
    package_dir: str | Path,
    model_path: str | Path,
    constraints_dir: str | Path,
) -> dict[str, object]:
    """Build FASTcore and context-policy inputs from transcriptomics evidence."""

    output = Path(constraints_dir)
    reaction_path = output / "reaction_expression_evidence.csv"
    gene_path = output / "gene_expression_evidence.csv"
    if not reaction_path.exists() or reaction_path.stat().st_size == 0:
        prepared = prepare_transcriptomics_constraints(package_dir, model_path, constraints_dir)
        if prepared["status"] == "skipped":
            return prepared

    reaction_rows = read_csv_records(reaction_path)
    method_inputs = split_context_method_inputs(reaction_rows)
    fastcore_path = output / "fastcore_core_reactions.csv"
    write_csv(fastcore_path, method_inputs["fastcore_core_reactions"])

    model_index = parse_sbml_index(model_path)
    exchange_rows = read_csv_records(output / "exchange_bounds.csv") if (output / "exchange_bounds.csv").exists() else []
    protected = protected_reactions_from_outputs(model_index.objective_reactions, exchange_rows)
    context_policy = build_context_reaction_policy(reaction_path, protected)
    context_outputs = split_context_policy(context_policy)
    write_csv(output / "context_reaction_policy.csv", context_policy)
    for name, rows in context_outputs.items():
        write_csv(output / f"{name}.csv", rows)

    return {
        "status": "completed",
        "message": f"Prepared {len(method_inputs['fastcore_core_reactions'])} FASTcore core rows.",
        "files": {
            "gene_expression_evidence": str(gene_path),
            "reaction_expression_evidence": str(reaction_path),
            "fastcore_core_reactions": str(fastcore_path),
            "context_reaction_policy": str(output / "context_reaction_policy.csv"),
        },
    }


def run_custom_troppo_fastcore(
    package_dir: str | Path,
    model_path: str | Path,
    constraints_dir: str | Path,
    output_dir: str | Path,
    enabled: bool = True,
    solver: str = "GLPK",
    flux_threshold: float = 1e-4,
    protect_objective: bool = True,
    protect_exchange_bounds: bool = True,
    filter_inactive_core: bool = True,
    run_feasibility_check: bool = True,
) -> Any:
    """Prepare and run custom TROPPO FASTcore when transcriptomics evidence exists."""

    if not enabled:
        return SimpleStepResult("skipped", "Custom TROPPO FASTcore is disabled.")
    prepared = prepare_fastcore_inputs(package_dir, model_path, constraints_dir)
    if prepared["status"] == "skipped":
        return SimpleStepResult("skipped", str(prepared["message"]))
    return run_troppo_fastcore_workflow(
        model_path=model_path,
        core_reactions_path=Path(constraints_dir) / "fastcore_core_reactions.csv",
        exchange_bounds_path=Path(constraints_dir) / "exchange_bounds.csv",
        gene_evidence_path=Path(constraints_dir) / "gene_expression_evidence.csv",
        reaction_evidence_path=Path(constraints_dir) / "reaction_expression_evidence.csv",
        output_dir=output_dir,
        require_troppo=False,
        solver=solver,
        flux_threshold=flux_threshold,
        protect_objective=protect_objective,
        protect_exchange_bounds=protect_exchange_bounds,
        filter_inactive_core=filter_inactive_core,
        run_feasibility_check=run_feasibility_check,
    )


def prepare_consensus_evidence_modes(
    package_dir: str | Path,
    model_path: str | Path,
    constraints_dir: str | Path,
) -> dict[str, object]:
    """Prepare relative proteomics, consensus evidence, and evidence-mode inputs."""

    output = Path(constraints_dir)
    transcript_path = output / "reaction_expression_evidence.csv"
    if not transcript_path.exists() or transcript_path.stat().st_size == 0:
        transcript_prepared = prepare_transcriptomics_constraints(package_dir, model_path, constraints_dir)
        if transcript_prepared["status"] == "skipped":
            return transcript_prepared
    transcript_mode_prepared = prepare_fastcore_inputs(package_dir, model_path, constraints_dir)
    if transcript_mode_prepared["status"] == "skipped":
        return transcript_mode_prepared

    protein_prepared = prepare_relative_proteomics_constraints(package_dir, model_path, constraints_dir)
    if protein_prepared["status"] == "skipped":
        return {
            "status": "completed_with_skips",
            "message": "Relative proteomics is missing; evidence comparison will use available transcriptomics and ML-derived modes.",
            "files": {},
        }

    transcript_rows = read_csv_records(transcript_path)
    protein_path = output / "relative_protein_reaction_evidence.csv"
    protein_rows = read_csv_records(protein_path)
    multi_omics_tables = build_multi_omics_conflict_tables(transcript_rows, protein_rows)
    for name, rows in multi_omics_tables.items():
        write_csv(output / f"{name}.csv", rows)

    model_index = parse_sbml_index(model_path)
    exchange_rows = read_csv_records(output / "exchange_bounds.csv") if (output / "exchange_bounds.csv").exists() else []
    protected = protected_reactions_from_outputs(model_index.objective_reactions, exchange_rows)

    relative_method_inputs = {
        f"relative_protein_{name}": rows
        for name, rows in split_context_method_inputs(protein_rows).items()
    }
    for name, rows in relative_method_inputs.items():
        write_csv(output / f"{name}.csv", rows)
    relative_context_policy = build_context_reaction_policy(protein_path, protected)
    write_csv(output / "relative_protein_context_reaction_policy.csv", relative_context_policy)
    for name, rows in split_context_policy(relative_context_policy).items():
        write_csv(output / f"relative_protein_{name}.csv", rows)

    consensus_path = output / "multi_omics_consensus_reaction_evidence.csv"
    consensus_rows = multi_omics_tables["multi_omics_consensus_reaction_evidence"]
    consensus_method_inputs = {
        f"consensus_{name}": rows
        for name, rows in split_context_method_inputs(consensus_rows).items()
    }
    for name, rows in consensus_method_inputs.items():
        write_csv(output / f"{name}.csv", rows)
    consensus_context_policy = build_context_reaction_policy(consensus_path, protected)
    write_csv(output / "consensus_context_reaction_policy.csv", consensus_context_policy)
    for name, rows in split_context_policy(consensus_context_policy).items():
        write_csv(output / f"consensus_{name}.csv", rows)

    return {
        "status": "completed",
        "message": f"Prepared consensus evidence for {len(consensus_rows)} reaction-condition rows.",
        "files": {
            "relative_protein_reaction_evidence": str(protein_path),
            "multi_omics_consensus_reaction_evidence": str(consensus_path),
            "multi_omics_conflict_summary": str(output / "multi_omics_conflict_summary.csv"),
        },
    }


def run_custom_evidence_mode_comparison(
    package_dir: str | Path,
    model_path: str | Path,
    constraints_dir: str | Path,
    output_dir: str | Path,
    enabled: bool = True,
) -> Any:
    """Prepare consensus evidence modes and run the comparison report."""

    if not enabled:
        return SimpleStepResult("skipped", "Custom Evidence Mode Comparison is disabled.")
    prepared = prepare_consensus_evidence_modes(package_dir, model_path, constraints_dir)
    if prepared["status"] == "skipped":
        return SimpleStepResult("skipped", str(prepared["message"]))
    prepare_ml_derived_evidence_mode(package_dir, constraints_dir)
    return run_evidence_mode_comparison(constraints_dir, output_dir)


def prepare_ml_derived_evidence_mode(
    package_dir: str | Path,
    constraints_dir: str | Path,
) -> dict[str, object]:
    """Convert ML prior scores into a soft evidence mode for comparison."""

    package = Path(package_dir)
    output = Path(constraints_dir)
    prior_path = package / "ml_results" / "ml_prior_scores.csv"
    if not prior_path.exists() or prior_path.stat().st_size == 0:
        return {"status": "skipped", "message": "No ML prior scores are available.", "files": {}}

    prior_rows = read_csv_records(prior_path)
    reaction_priors = [row for row in prior_rows if row.get("target_type") == "reaction"]
    if not reaction_priors:
        return {"status": "skipped", "message": "No reaction-level ML prior scores are available.", "files": {}}

    conditions = _evidence_conditions(output)
    reaction_rows: list[dict[str, object]] = []
    context_rows: list[dict[str, object]] = []
    core_rows: list[dict[str, object]] = []
    for condition in conditions:
        for row in reaction_priors:
            reaction_id = _ml_reaction_id(row)
            if not reaction_id:
                continue
            evidence = _ml_prior_evidence(row)
            decision = _ml_prior_decision(row)
            cobra_reaction_id = reaction_id[2:] if reaction_id.startswith("R_") else reaction_id
            reaction_rows.append(
                {
                    "condition": condition,
                    "reaction_id": reaction_id,
                    "cobra_reaction_id": cobra_reaction_id,
                    "reaction_name": reaction_id,
                    "reaction_score": row.get("score", ""),
                    "evidence": evidence,
                    "gene_count": "",
                    "measured_gene_count": "",
                    "gene_coverage": "",
                    "imat_weight": 1 if evidence == "high" else -1 if evidence == "low" else 0,
                    "fastcore_core": decision == "support",
                    "corda_confidence": "high" if evidence == "high" else "low" if evidence == "low" else "medium",
                    "gpr_rule": "",
                    "measured_genes": "",
                    "status": "ml_soft_prior",
                    "source_feature_id": row.get("source_feature_id", ""),
                    "target_feature_id": row.get("target_feature_id", ""),
                    "sample_status": row.get("sample_status", ""),
                    "note": row.get("note", ""),
                }
            )
            context_rows.append(
                {
                    "condition": condition,
                    "reaction_id": reaction_id,
                    "cobra_reaction_id": cobra_reaction_id,
                    "decision": "support" if decision == "support" else "penalize_candidate" if decision == "penalize" else "neutral",
                    "status": "ml_soft_policy",
                    "penalty": row.get("reaction_penalty", ""),
                    "ml_score": row.get("score", ""),
                    "source_feature_id": row.get("source_feature_id", ""),
                    "target_feature_id": row.get("target_feature_id", ""),
                    "note": row.get("note", ""),
                }
            )
            if decision == "support":
                core_rows.append(
                    {
                        "condition": condition,
                        "reaction_id": reaction_id,
                        "cobra_reaction_id": cobra_reaction_id,
                        "reaction_score": row.get("score", ""),
                        "status": "core",
                    }
                )

    files = {
        "reaction_evidence": str(output / "ml_derived_reaction_evidence.csv"),
        "context_policy": str(output / "ml_derived_context_reaction_policy.csv"),
        "core_reactions": str(output / "ml_derived_fastcore_core_reactions.csv"),
    }
    write_csv(files["reaction_evidence"], reaction_rows)
    write_csv(files["context_policy"], context_rows)
    write_csv(files["core_reactions"], core_rows)
    return {
        "status": "completed",
        "message": f"Prepared ML-derived evidence for {len(reaction_rows)} reaction-condition rows.",
        "files": files,
    }


def _evidence_conditions(constraints_dir: Path) -> list[str]:
    """Return evidence conditions to which global ML priors should be applied."""

    candidates = [
        constraints_dir / "reaction_expression_evidence.csv",
        constraints_dir / "multi_omics_consensus_reaction_evidence.csv",
        constraints_dir / "relative_protein_reaction_evidence.csv",
    ]
    conditions: set[str] = set()
    for path in candidates:
        if not path.exists() or path.stat().st_size == 0:
            continue
        for row in read_csv_records(path):
            condition = row.get("condition") or row.get("sample") or "default"
            if condition and condition != "ALL":
                conditions.add(condition)
    return sorted(conditions) or ["ALL"]


def _ml_reaction_id(row: dict[str, str]) -> str:
    reaction_id = row.get("model_target_id") or row.get("target_id") or ""
    if not reaction_id:
        return ""
    return reaction_id if reaction_id.startswith("R_") else f"R_{reaction_id}"


def _ml_prior_evidence(row: dict[str, str]) -> str:
    action = row.get("context_action", "")
    if action == "support":
        return "high"
    if action == "penalize":
        return "low"
    return "medium"


def _ml_prior_decision(row: dict[str, str]) -> str:
    action = row.get("context_action", "")
    if action in {"support", "penalize"}:
        return action
    return "neutral"


def run_transcriptomics_step(
    step_index: int,
    package_dir: Path,
    model_path: Path,
    constraints_dir: Path,
    output_dir: Path,
    require_cobra: bool,
    run_pfba: bool,
    enabled: bool,
    min_expression_fraction: float = 0.05,
    reference_condition: str = "",
    up_log2_threshold: float = 1.0,
    down_log2_threshold: float = -1.0,
) -> dict[str, object]:
    """Prepare transcriptomics constraints and run the E-Flux workflow."""

    if not enabled:
        return build_step_row(step_index, "transcriptomics_flux", "skipped", "Custom E-Flux is disabled.")
    started = time.perf_counter()
    try:
        prepared = prepare_transcriptomics_constraints(package_dir, model_path, constraints_dir)
        if prepared["status"] == "skipped":
            return build_step_row(
                step_index,
                "transcriptomics_flux",
                "skipped",
                str(prepared["message"]),
                round(time.perf_counter() - started, 3),
                label="Run custom transcriptomics E-Flux",
            )
        result = run_transcriptomics_flux_workflow(
            model_path=model_path,
            exchange_bounds_path=constraints_dir / "exchange_bounds.csv",
            reaction_expression_path=constraints_dir / "reaction_expression_evidence.csv",
            flux_targets_path=constraints_dir / "flux_validation_targets.csv",
            output_dir=output_dir,
            reference_condition=reference_condition or None,
            require_cobra=require_cobra,
            min_expression_fraction=min_expression_fraction,
            up_log2_threshold=up_log2_threshold,
            down_log2_threshold=down_log2_threshold,
            run_pfba=run_pfba,
        )
        status = result.status
        if status == "completed_no_conditions":
            status = "skipped"
        return build_step_row(
            step_index,
            "transcriptomics_flux",
            status,
            result.message,
            round(time.perf_counter() - started, 3),
            label="Run custom transcriptomics E-Flux",
        )
    except Exception as exc:
        return build_step_row(
            step_index,
            "transcriptomics_flux",
            "failed",
            f"{type(exc).__name__}: {exc}",
            round(time.perf_counter() - started, 3),
            label="Run custom transcriptomics E-Flux",
        )


def read_input_map(package_dir: str | Path) -> list[dict[str, str]]:
    """Read a staged package input map."""

    return read_package_input_map(package_dir)


def read_normalized_input_map(package_dir: str | Path) -> list[dict[str, str]]:
    """Read alias-normalized input map when available."""
    return read_package_input_map(package_dir, normalized=True)


def write_custom_input_overview(package_dir: str | Path, pipeline_dir: str | Path) -> list[dict[str, object]]:
    """Write a compact input overview table for UI and HTML reports."""

    rows = build_custom_input_overview(read_input_map(package_dir))
    write_csv(Path(pipeline_dir) / "custom_input_overview.csv", rows)
    return rows


def build_custom_input_overview(input_rows: list[dict[str, str]]) -> list[dict[str, object]]:
    """Build stable overview rows from upload-package input rows."""

    overview: list[dict[str, object]] = []
    for index, row in enumerate(input_rows, start=1):
        kind = str(row.get("kind", ""))
        role = str(row.get("role", ""))
        overview.append(
            {
                "input_index": index,
                "input_group": input_group_label(kind),
                "kind": kind,
                "role": role,
                "original_name": row.get("original_name", ""),
                "saved_name": row.get("saved_name", ""),
                "relative_path": row.get("relative_path", ""),
                "size_bytes": row.get("size_bytes", ""),
                "inspection_status": row.get("inspection_status", ""),
                "details": row.get("details", ""),
                "usage_note": input_usage_note(kind, role),
            }
        )
    return overview


def input_group_label(kind: str) -> str:
    """Return a user-facing group label for a staged input kind."""

    return {
        "model": "GEM model",
        "omics_table": "Omics data",
        "condition_table": "Condition setup",
    }.get(kind, kind or "unknown")


def input_usage_note(kind: str, role: str) -> str:
    """Describe how a staged input is currently used by the custom runner."""

    if kind == "model":
        return "Used by model QC, COBRApy baseline, E-Flux, and report generation."
    if kind == "condition_table" and role == "condition_exchange_bounds":
        return "Used as exchange_bounds.csv for condition-specific FBA/E-Flux."
    if role == "production_targets":
        return "Used by Production Analysis / ecFactory-lite to define product exchange reactions."
    if kind == "condition_table":
        return "Recorded for condition documentation and downstream workflow expansion."
    if kind == "omics_table" and role == "transcriptomics":
        return "Used to build gene/reaction expression evidence and custom E-Flux."
    if kind == "omics_table" and role == "uniprot_annotation":
        return "Used by UniProt / GPR Model Check to review gene, reaction, EC, and UniProt annotation coverage."
    if kind == "omics_table" and role == "dlkcat_annotation":
        return "Used by the DLKcat bridge to provide protein sequences, substrate names, substrate SMILES, and EC hints."
    if kind == "omics_table" and role == "id_alias_table":
        return "Used by ID Mapping Review to compare direct GEM matches with alias-assisted matches."
    if kind == "omics_table":
        return "Staged for downstream modules; not yet consumed by the minimal custom runner."
    return "Recorded in the user run package."


def run_callable_step(step_index: int, step_id: str, label: str, callback) -> dict[str, object]:
    """Run one in-process pipeline step and convert the result to a step row."""

    started = time.perf_counter()
    try:
        result = callback()
        elapsed = round(time.perf_counter() - started, 3)
        status = str(getattr(result, "status", "completed"))
        message = str(getattr(result, "message", "Command completed."))
        if isinstance(result, Path):
            status = "completed"
            message = f"Report written to {result}"
        return build_step_row(step_index, step_id, status, message, elapsed, label=label)
    except Exception as exc:
        elapsed = round(time.perf_counter() - started, 3)
        return build_step_row(
            step_index,
            step_id,
            "failed",
            f"{type(exc).__name__}: {exc}",
            elapsed,
            label=label,
        )


def build_step_row(
    step_index: int,
    step_id: str,
    status: str,
    message: str,
    elapsed_seconds: float | None = None,
    label: str = "",
) -> dict[str, object]:
    """Build a pipeline step row matching the existing dashboard shape."""

    return {
        "step_index": step_index,
        "step_id": step_id,
        "label": label or step_id,
        "status": status,
        "message": message,
        "optional": False,
        "return_code": "",
        "elapsed_seconds": elapsed_seconds if elapsed_seconds is not None else "",
    }


def build_not_selected_row(step_index: int, step_id: str, message: str, label: str = "") -> dict[str, object]:
    """Build a row for workflow modules the user intentionally did not select."""

    status = "skipped" if str(message).startswith("variant_incompatible") else "not_selected"
    return build_step_row(
        step_index=step_index,
        step_id=step_id,
        status=status,
        message=message,
        label=label,
    )


def analysis_skip_message(
    analysis_module: str,
    selected: bool,
    compatibility: dict[str, bool],
    context_rows: list[dict[str, object]],
) -> str:
    """Return a clear skip reason for unselected or variant-incompatible analysis."""

    if not selected:
        return f"{analysis_module} analysis was not selected."
    if compatibility.get(analysis_module, True):
        return f"{analysis_module} analysis was not selected."
    for row in context_rows:
        if row.get("analysis_module") == analysis_module:
            guidance = str(row.get("guidance", "")).strip()
            return f"variant_incompatible: {guidance}" if guidance else "variant_incompatible"
    return "variant_incompatible"


def analysis_active_context_model_path(context_rows: list[dict[str, object]]) -> Path | None:
    """Return the active context SBML path when variant dispatch produced one."""

    for row in context_rows:
        path_text = str(row.get("context_model_sbml", "")).strip()
        if path_text and Path(path_text).exists():
            return Path(path_text)
    return None


def analysis_active_variant_id(context_rows: list[dict[str, object]], module_id: str = "fba_pfba") -> str:
    """Return the active model variant ID chosen for downstream analysis."""

    preferred = _analysis_context_row(context_rows, module_id)
    if preferred:
        return str(preferred.get("active_variant_id", "")).strip()
    if context_rows:
        return str(context_rows[0].get("active_variant_id", "")).strip()
    return ""


def analysis_active_model_path(
    context_rows: list[dict[str, object]],
    fallback_model_path: Path,
    module_id: str = "fba_pfba",
) -> Path:
    """Return the model path that should be used by the selected analysis."""

    row = _analysis_context_row(context_rows, module_id) or (context_rows[0] if context_rows else {})
    for key in ("active_model_path", "context_model_sbml"):
        path_text = str(row.get(key, "")).strip()
        if path_text and Path(path_text).exists():
            return Path(path_text)
    return fallback_model_path


def run_batch_variant_fba_workflow(
    *,
    registry_rows: list[dict[str, str]],
    selected_variant_ids: list[str],
    selected_analysis_modules: list[str],
    fallback_model_path: Path,
    exchange_bounds_path: Path,
    flux_targets_path: Path,
    variant_results_root: Path,
    require_cobra: bool,
    run_pfba: bool,
    run_fva: bool,
    fva_fraction_of_optimum: float = 0.95,
    objective_reaction_id: str = "",
    objective_direction: str = "max",
    fva_reaction_scope: str = "targets",
    loopless: bool = False,
    pfba_factor: float | str | None = None,
    fva_processes: int = 1,
) -> SimpleStepResult:
    """Run FBA/pFBA for one or more compatible model variants."""

    variant_results_root.mkdir(parents=True, exist_ok=True)
    registry_by_id = {str(row.get("variant_id", "")).strip(): row for row in registry_rows}
    variant_ids = selected_variant_ids or [str(row.get("variant_id", "")).strip() for row in registry_rows[:1]]
    if not registry_rows or not variant_ids:
        write_variant_fba_index(variant_results_root)
        return SimpleStepResult(status="skipped", message="No model variants were available for FBA/pFBA analysis.")

    statuses: list[str] = []
    messages: list[str] = []
    for variant_id in variant_ids:
        if variant_id and variant_id not in registry_by_id:
            output_dir = variant_results_root / safe_variant_dir_name(variant_id)
            output_dir.mkdir(parents=True, exist_ok=True)
            write_variant_fba_metadata(
                output_dir=output_dir,
                variant_results_root=variant_results_root,
                active_variant_id=variant_id,
                active_model_path=fallback_model_path,
                analysis_variant_context_rows=[],
                status="skipped",
                message="Selected model variant was not found in model_variant_registry.csv.",
            )
            statuses.append("skipped")
            messages.append(f"{variant_id}: missing registry row")
            continue
        context_rows = build_analysis_variant_context(
            registry_rows,
            selected_analysis_modules=["fba_pfba"],
            selected_model_variant_id=variant_id,
        )
        active_variant_id = analysis_active_variant_id(context_rows) or variant_id or "baseline_gem__default"
        compatible = str((_analysis_context_row(context_rows, "fba_pfba") or {}).get("compatible", "")).lower() == "true"
        output_dir = variant_results_root / safe_variant_dir_name(active_variant_id)
        active_model_path = analysis_active_model_path(context_rows, fallback_model_path, module_id="fba_pfba")
        if not compatible:
            message = analysis_skip_message(
                "fba_pfba",
                True,
                {"fba_pfba": False},
                context_rows,
            )
            output_dir.mkdir(parents=True, exist_ok=True)
            write_variant_fba_metadata(
                output_dir=output_dir,
                variant_results_root=variant_results_root,
                active_variant_id=active_variant_id,
                active_model_path=active_model_path,
                analysis_variant_context_rows=context_rows,
                status="skipped",
                message=message,
            )
            statuses.append("skipped")
            messages.append(f"{active_variant_id}: skipped")
            continue
        result = run_variant_fba_workflow(
            model_path=active_model_path,
            exchange_bounds_path=exchange_bounds_path,
            flux_targets_path=flux_targets_path,
            output_dir=output_dir,
            variant_results_root=variant_results_root,
            active_variant_id=active_variant_id,
            active_model_path=active_model_path,
            analysis_variant_context_rows=context_rows,
            require_cobra=require_cobra,
            run_pfba=run_pfba,
            run_fva=run_fva,
            fva_fraction_of_optimum=fva_fraction_of_optimum,
            objective_reaction_id=objective_reaction_id,
            objective_direction=objective_direction,
            fva_reaction_scope=fva_reaction_scope,
            loopless=loopless,
            pfba_factor=pfba_factor,
            fva_processes=fva_processes,
        )
        statuses.append(result.status)
        messages.append(f"{active_variant_id}: {result.status}")

    write_variant_fba_index(variant_results_root)
    if any(status == "failed" for status in statuses):
        status = "failed"
    elif any(status == "skipped" for status in statuses):
        status = "completed_with_failures" if any(status != "skipped" for status in statuses) else "skipped"
    else:
        status = "completed"
    return SimpleStepResult(
        status=status,
        message="Batch FBA/pFBA results: " + "; ".join(messages),
    )


def run_variant_fba_workflow(
    *,
    model_path: Path,
    exchange_bounds_path: Path,
    flux_targets_path: Path,
    output_dir: Path,
    variant_results_root: Path,
    active_variant_id: str,
    active_model_path: Path,
    analysis_variant_context_rows: list[dict[str, object]],
    require_cobra: bool,
    run_pfba: bool,
    run_fva: bool,
    fva_fraction_of_optimum: float = 0.95,
    objective_reaction_id: str = "",
    objective_direction: str = "max",
    fva_reaction_scope: str = "targets",
    loopless: bool = False,
    pfba_factor: float | str | None = None,
    fva_processes: int = 1,
) -> SimpleStepResult:
    """Run FBA/pFBA for the active model variant and write variant metadata."""

    output_dir.mkdir(parents=True, exist_ok=True)
    result = run_fba_workflow(
        model_path=model_path,
        exchange_bounds_path=exchange_bounds_path,
        flux_targets_path=flux_targets_path,
        output_dir=output_dir,
        require_cobra=require_cobra,
        run_pfba=run_pfba,
        run_fva=run_fva,
        fva_fraction_of_optimum=fva_fraction_of_optimum,
        objective_reaction_id=objective_reaction_id,
        objective_direction=objective_direction,
        fva_reaction_scope=fva_reaction_scope,
        loopless=loopless,
        pfba_factor=pfba_factor,
        fva_processes=fva_processes,
    )
    status = str(getattr(result, "status", "completed"))
    message = str(getattr(result, "message", "Command completed."))
    write_variant_fba_metadata(
        output_dir=output_dir,
        variant_results_root=variant_results_root,
        active_variant_id=active_variant_id,
        active_model_path=active_model_path,
        analysis_variant_context_rows=analysis_variant_context_rows,
        status=status,
        message=message,
        parameters={
            "run_pfba": run_pfba,
            "run_fva": run_fva,
            "fva_fraction_of_optimum": fva_fraction_of_optimum,
            "objective_reaction_id": objective_reaction_id,
            "objective_direction": objective_direction,
            "fva_reaction_scope": fva_reaction_scope,
            "loopless": loopless,
            "pfba_factor": pfba_factor,
            "fva_processes": fva_processes,
        },
    )
    return SimpleStepResult(status=status, message=f"{message} Variant output: {output_dir}")


def write_variant_fba_metadata(
    *,
    output_dir: Path,
    variant_results_root: Path,
    active_variant_id: str,
    active_model_path: Path,
    analysis_variant_context_rows: list[dict[str, object]],
    status: str,
    message: str,
    parameters: dict[str, object] | None = None,
) -> None:
    """Write per-variant FBA summary files and refresh the package-level index."""

    context_row = _analysis_context_row(analysis_variant_context_rows, "fba_pfba") or {}
    manifest_path = output_dir / "variant_fba_manifest.json"
    write_json(
        manifest_path,
        {
            "schema_version": "0.1.0",
            "analysis_module": "fba_pfba",
            "active_variant_id": active_variant_id,
            "active_generation_method": context_row.get("active_generation_method", ""),
            "active_generation_method_label": context_row.get("active_generation_method_label", ""),
            "active_model_path": str(active_model_path),
            "active_model_source": context_row.get("active_model_source", ""),
            "output_dir": str(output_dir),
            "status": status,
            "message": message,
            "parameters": parameters or {},
        },
    )
    fba_rows = read_csv_records(output_dir / "fba_summary.csv") if (output_dir / "fba_summary.csv").exists() else []
    variant_rows = _variant_fba_rows(
        fba_rows,
        active_variant_id=active_variant_id,
        active_model_path=active_model_path,
        output_dir=output_dir,
        status=status,
        message=message,
        context_row=context_row,
    )
    write_csv(output_dir / "variant_fba_summary.csv", variant_rows)
    write_variant_fba_index(variant_results_root)


def write_variant_fba_index(variant_results_root: Path) -> Path:
    """Collect per-variant FBA summaries into a package-level index."""

    rows: list[dict[str, object]] = []
    if variant_results_root.exists():
        for summary_path in sorted(variant_results_root.glob("*/variant_fba_summary.csv")):
            rows.extend(read_csv_records(summary_path))
    index_path = variant_results_root / "variant_fba_summary.csv"
    write_csv(index_path, rows)
    return index_path


def build_custom_report_outputs(
    *,
    package_dir: Path,
    cobra_results_dir: Path,
    report_preset: str,
    active_variant_id: list[str] | str | None,
) -> SimpleStepResult:
    """Write the legacy full audit report and the selected report preset bundle."""

    legacy_path = build_cobra_report(
        cobra_results_dir,
        cobra_results_dir / "report.html",
        title="Custom COBRA Report",
    )
    bundle = build_report_bundle(
        package_dir,
        preset=report_preset,
        active_variant_id=active_variant_id,
    )
    return SimpleStepResult(
        status="completed",
        message=f"Built legacy report {legacy_path} and selected report bundle {bundle.report_path}.",
    )


def _variant_fba_rows(
    rows: list[dict[str, str]],
    *,
    active_variant_id: str,
    active_model_path: Path,
    output_dir: Path,
    status: str,
    message: str,
    context_row: dict[str, object],
) -> list[dict[str, object]]:
    base = {
        "variant_id": active_variant_id,
        "analysis_module": "fba_pfba",
        "active_generation_method": context_row.get("active_generation_method", ""),
        "active_generation_method_label": context_row.get("active_generation_method_label", ""),
        "active_model_path": str(active_model_path),
        "active_model_source": context_row.get("active_model_source", ""),
        "output_dir": str(output_dir),
        "run_status": status,
        "run_message": message,
    }
    if not rows:
        return [{**base, "condition": "", "status": status, "objective_value": ""}]
    variant_rows: list[dict[str, object]] = []
    for row in rows:
        merged = {**base, **row}
        if not merged.get("status"):
            merged["status"] = status
        variant_rows.append(merged)
    return variant_rows


def _analysis_context_row(context_rows: list[dict[str, object]], module_id: str) -> dict[str, object]:
    for row in context_rows:
        if str(row.get("analysis_module", "")).strip() == module_id:
            return row
    return {}


def finalize_user_pipeline(
    package_dir: Path,
    pipeline_dir: Path,
    step_rows: list[dict[str, object]],
    status_override: str | None = None,
) -> UserPipelineResult:
    """Write pipeline metadata and return a result object."""

    status = status_override or classify_pipeline_status(step_rows)
    message = build_pipeline_message(step_rows, status)
    files = {
        "manifest": str(pipeline_dir / "pipeline_run_manifest.json"),
        "steps": str(pipeline_dir / "pipeline_steps.csv"),
        "backend_status": str(pipeline_dir / "pipeline_backend_status.csv"),
        "input_overview": str(pipeline_dir / "custom_input_overview.csv"),
        "workflow_selection": str(package_dir / "workflow_results" / "workflow_selection.csv"),
        "model_generation_parameters": str(package_dir / "workflow_results" / "model_generation_parameters.json"),
        "model_generation_parameters_summary": str(package_dir / "workflow_results" / "model_generation_parameters_summary.csv"),
        "model_variant_registry": str(package_dir / "workflow_results" / "model_variant_registry.csv"),
        "model_variant_registry_manifest": str(package_dir / "workflow_results" / "model_variant_registry_manifest.json"),
        "analysis_variant_context": str(package_dir / "workflow_results" / "analysis_variant_context.csv"),
        "analysis_parameters": str(package_dir / "workflow_results" / "analysis_parameters.json"),
        "analysis_parameters_summary": str(package_dir / "workflow_results" / "analysis_parameters_summary.csv"),
        "context_model_artifact_summary": str(package_dir / "workflow_results" / "context_model_artifact_summary.csv"),
        "context_model_artifact_manifest": str(package_dir / "workflow_results" / "context_model_artifact_manifest.json"),
        "variant_cobra_results_root": str(package_dir / "variant_cobra_results"),
        "variant_fba_summary": str(package_dir / "variant_cobra_results" / "variant_fba_summary.csv"),
        "variant_comparison_summary": str(package_dir / "variant_comparison" / "variant_comparison_summary.csv"),
        "variant_flux_comparison": str(package_dir / "variant_comparison" / "variant_flux_comparison.csv"),
        "variant_evidence_quality": str(package_dir / "variant_comparison" / "variant_evidence_quality.csv"),
        "variant_comparison_manifest": str(package_dir / "variant_comparison" / "variant_comparison_manifest.json"),
        "id_mapping_summary": str(package_dir / "id_mapping_results" / "id_mapping_summary.csv"),
        "id_mapping_detail": str(package_dir / "id_mapping_results" / "id_mapping_detail.csv"),
        "uniprot_gene_coverage": str(package_dir / "uniprot_model_check" / "uniprot_gene_coverage.csv"),
        "gpr_consistency_flags": str(package_dir / "uniprot_model_check" / "gpr_consistency_flags.csv"),
        "reaction_annotation_flags": str(package_dir / "uniprot_model_check" / "reaction_annotation_flags.csv"),
        "uniprot_enrichment_summary": str(package_dir / "uniprot_model_check" / "uniprot_enrichment_summary.csv"),
        "uniprot_enrichment_records": str(package_dir / "uniprot_model_check" / "uniprot_enrichment_records.csv"),
        "uniprot_model_check_summary": str(package_dir / "uniprot_model_check" / "uniprot_model_check_summary.csv"),
        "uniprot_model_check_manifest": str(package_dir / "uniprot_model_check" / "uniprot_model_check_manifest.json"),
        "dlkcat_input": str(package_dir / "dlkcat_results" / "dlkcat_input.tsv"),
        "dlkcat_input_coverage": str(package_dir / "dlkcat_results" / "dlkcat_input_coverage.csv"),
        "dlkcat_prediction_import_template": str(package_dir / "dlkcat_results" / "dlkcat_prediction_import_template.csv"),
        "dlkcat_prediction_import": str(package_dir / "dlkcat_results" / "dlkcat_prediction_import.csv"),
        "dlkcat_prediction_normalized": str(package_dir / "dlkcat_results" / "dlkcat_prediction_normalized.csv"),
        "dlkcat_reaction_kcat_priors": str(package_dir / "dlkcat_results" / "dlkcat_reaction_kcat_priors.csv"),
        "dlkcat_bridge_summary": str(package_dir / "dlkcat_results" / "dlkcat_bridge_summary.csv"),
        "dlkcat_bridge_manifest": str(package_dir / "dlkcat_results" / "dlkcat_bridge_manifest.json"),
        "dlkcat_external_run_summary": str(package_dir / "dlkcat_results" / "dlkcat_external_run_summary.csv"),
        "dlkcat_external_run_manifest": str(package_dir / "dlkcat_results" / "dlkcat_external_run_manifest.json"),
        "dlkcat_gecko_protocol": str(package_dir / "dlkcat_results" / "dlkcat_gecko_protocol.m"),
        "dlkcat_gecko_command": str(package_dir / "dlkcat_results" / "dlkcat_gecko_command.txt"),
        "dlkcat_gecko_stdout": str(package_dir / "dlkcat_results" / "dlkcat_gecko_stdout.log"),
        "dlkcat_gecko_stderr": str(package_dir / "dlkcat_results" / "dlkcat_gecko_stderr.log"),
        "dlkcat_gecko_input": str(package_dir / "dlkcat_results" / "dlkcat_gecko_input.tsv"),
        "dlkcat_gecko_output": str(package_dir / "dlkcat_results" / "dlkcat_gecko_output.tsv"),
        "kcat_priors": str(package_dir / "generated_constraints" / "kcat_priors.csv"),
        "kcat_prior_candidates": str(package_dir / "generated_constraints" / "kcat_prior_candidates.csv"),
        "kcat_conflict_flags": str(package_dir / "generated_constraints" / "kcat_conflict_flags.csv"),
        "kcat_prior_merge_summary": str(package_dir / "generated_constraints" / "kcat_prior_merge_summary.csv"),
        "kcat_prior_merge_manifest": str(package_dir / "generated_constraints" / "kcat_prior_merge_manifest.json"),
        "protein_abundance": str(package_dir / "generated_constraints" / "protein_abundance.csv"),
        "enzyme_reaction_capacity": str(package_dir / "enzyme_results" / "reaction_enzyme_capacity.csv"),
        "enzyme_flux_capacity_check": str(package_dir / "enzyme_results" / "enzyme_flux_capacity_check.csv"),
        "enzyme_qc_summary": str(package_dir / "enzyme_results" / "enzyme_qc_summary.csv"),
        "enzyme_qc_recommendations": str(package_dir / "enzyme_results" / "enzyme_qc_recommendations.csv"),
        "enzyme_constraint_manifest": str(package_dir / "enzyme_results" / "enzyme_constraint_manifest.json"),
        "gecko_export_summary": str(package_dir / "gecko_package" / "gecko_export_summary.csv"),
        "gecko_export_manifest": str(package_dir / "gecko_package" / "gecko_export_manifest.json"),
        "gecko_kcat_table": str(package_dir / "gecko_package" / "kcat_table.tsv"),
        "gecko_protein_abundance": str(package_dir / "gecko_package" / "protein_abundance.tsv"),
        "gecko_protocol_template": str(package_dir / "gecko_package" / "protocol_template.m"),
        "gecko_adapter_config": str(package_dir / "gecko_package" / "gecko_adapter_config.json"),
        "gecko_adapter_summary": str(package_dir / "gecko_package" / "gecko_adapter_summary.csv"),
        "gecko_generated_adapter": str(package_dir / "gecko_package" / "generated_adapter.m"),
        "gecko_adapter_readiness": str(package_dir / "gecko_package" / "gecko_adapter_readiness.csv"),
        "gecko_protocol_config": str(package_dir / "gecko_package" / "gecko_protocol_config.json"),
        "ml_feature_matrix": str(package_dir / "ml_results" / "ml_feature_matrix.csv"),
        "ml_feature_summary": str(package_dir / "ml_results" / "ml_feature_summary.csv"),
        "ml_correlations": str(package_dir / "ml_results" / "feature_phenotype_correlations.csv"),
        "ml_prior_scores": str(package_dir / "ml_results" / "ml_prior_scores.csv"),
        "ml_diagnostic_summary": str(package_dir / "ml_results" / "ml_diagnostic_summary.csv"),
        "ml_pca_scores": str(package_dir / "ml_results" / "ml_pca_scores.csv"),
        "ml_condition_clusters": str(package_dir / "ml_results" / "ml_condition_clusters.csv"),
        "ml_lasso_lite_coefficients": str(package_dir / "ml_results" / "ml_lasso_lite_coefficients.csv"),
        "condition_interpretation_summary": str(package_dir / "interpretation_results" / "condition_interpretation_summary.csv"),
        "condition_interpretation_recommendations": str(package_dir / "interpretation_results" / "condition_interpretation_recommendations.csv"),
        "minn_export_summary": str(package_dir / "minn_export" / "minn_export_summary.csv"),
        "minn_graph_nodes": str(package_dir / "minn_export" / "minn_graph_nodes.csv"),
        "minn_graph_edges": str(package_dir / "minn_export" / "minn_graph_edges.csv"),
        "minn_omics_feature_tensor": str(package_dir / "minn_export" / "minn_omics_feature_tensor.csv"),
        "minn_phenotype_labels": str(package_dir / "minn_export" / "minn_phenotype_labels.csv"),
        "minn_readiness_summary": str(package_dir / "minn_export" / "minn_readiness_summary.csv"),
        "minn_readiness_target_priors": str(package_dir / "minn_export" / "minn_readiness_target_priors.csv"),
        "minn_readiness_sample_weights": str(package_dir / "minn_export" / "minn_readiness_sample_weights.csv"),
        "minn_readiness_manifest": str(package_dir / "minn_export" / "minn_readiness_manifest.json"),
        "hybrid_runner_summary": str(package_dir / "hybrid_results" / "hybrid_runner_summary.csv"),
        "hybrid_target_scores": str(package_dir / "hybrid_results" / "hybrid_target_scores.csv"),
        "hybrid_feature_attributions": str(package_dir / "hybrid_results" / "hybrid_feature_attributions.csv"),
        "hybrid_loocv_evaluation": str(package_dir / "hybrid_results" / "hybrid_loocv_evaluation.csv"),
        "hybrid_loocv_summary": str(package_dir / "hybrid_results" / "hybrid_loocv_summary.csv"),
        "hybrid_runner_schema": str(package_dir / "hybrid_results" / "hybrid_runner_schema.json"),
        "hybrid_runner_metadata": str(package_dir / "hybrid_results" / "hybrid_runner_metadata.json"),
        "hybrid_runner_manifest": str(package_dir / "hybrid_results" / "hybrid_runner_manifest.json"),
        "hybrid_graph_adapter_summary": str(package_dir / "hybrid_adapter_results" / "hybrid_graph_adapter_summary.csv"),
        "hybrid_graph_adapter_nodes": str(package_dir / "hybrid_adapter_results" / "hybrid_graph_adapter_nodes.csv"),
        "hybrid_graph_adapter_edge_index": str(package_dir / "hybrid_adapter_results" / "hybrid_graph_adapter_edge_index.csv"),
        "hybrid_graph_adapter_feature_tensor": str(package_dir / "hybrid_adapter_results" / "hybrid_graph_adapter_feature_tensor.csv"),
        "hybrid_graph_adapter_labels": str(package_dir / "hybrid_adapter_results" / "hybrid_graph_adapter_labels.csv"),
        "hybrid_graph_adapter_targets": str(package_dir / "hybrid_adapter_results" / "hybrid_graph_adapter_targets.csv"),
        "hybrid_graph_adapter_validation_flags": str(package_dir / "hybrid_adapter_results" / "hybrid_graph_adapter_validation_flags.csv"),
        "hybrid_graph_adapter_dense_feature_vocabulary": str(package_dir / "hybrid_adapter_results" / "hybrid_graph_adapter_dense_feature_vocabulary.csv"),
        "hybrid_graph_adapter_dense_feature_matrix": str(package_dir / "hybrid_adapter_results" / "hybrid_graph_adapter_dense_feature_matrix.csv"),
        "hybrid_graph_adapter_dense_feature_summary": str(package_dir / "hybrid_adapter_results" / "hybrid_graph_adapter_dense_feature_summary.csv"),
        "hybrid_graph_adapter_payload_stub": str(package_dir / "hybrid_adapter_results" / "hybrid_graph_adapter_payload_stub.json"),
        "hybrid_graph_adapter_pyg_summary": str(package_dir / "hybrid_adapter_results" / "hybrid_graph_adapter_pyg_summary.csv"),
        "hybrid_graph_adapter_pyg_data": str(package_dir / "hybrid_adapter_results" / "hybrid_graph_adapter_pyg_data.pt"),
        "hybrid_graph_adapter_condition_pyg_summary": str(package_dir / "hybrid_adapter_results" / "hybrid_graph_adapter_condition_pyg_summary.csv"),
        "hybrid_graph_adapter_condition_pyg_manifest": str(package_dir / "hybrid_adapter_results" / "hybrid_graph_adapter_condition_pyg_manifest.json"),
        "hybrid_graph_adapter_dgl_summary": str(package_dir / "hybrid_adapter_results" / "hybrid_graph_adapter_dgl_summary.csv"),
        "hybrid_graph_adapter_dgl_graph": str(package_dir / "hybrid_adapter_results" / "hybrid_graph_adapter_dgl_graph.bin"),
        "hybrid_graph_adapter_condition_dgl_summary": str(package_dir / "hybrid_adapter_results" / "hybrid_graph_adapter_condition_dgl_summary.csv"),
        "hybrid_graph_adapter_condition_dgl_manifest": str(package_dir / "hybrid_adapter_results" / "hybrid_graph_adapter_condition_dgl_manifest.json"),
        "hybrid_graph_adapter_manifest": str(package_dir / "hybrid_adapter_results" / "hybrid_graph_adapter_manifest.json"),
        "production_analysis_summary": str(package_dir / "production_results" / "production_analysis_summary.csv"),
        "production_envelope": str(package_dir / "production_results" / "production_envelope.csv"),
        "production_target_ranking": str(package_dir / "production_results" / "production_target_ranking.csv"),
        "fseof_lite_reaction_targets": str(package_dir / "production_results" / "fseof_lite_reaction_targets.csv"),
        "production_design_targets": str(package_dir / "production_results" / "production_design_targets.csv"),
        "production_gene_targets": str(package_dir / "production_results" / "production_gene_targets.csv"),
        "production_gecko_comparison_summary": str(package_dir / "production_results" / "production_gecko_comparison_summary.csv"),
        "production_gecko_target_comparison": str(package_dir / "production_results" / "production_gecko_target_comparison.csv"),
        "production_gecko_design_comparison": str(package_dir / "production_results" / "production_gecko_design_comparison.csv"),
        "production_gecko_bridge_manifest": str(package_dir / "production_results" / "production_gecko_bridge_manifest.json"),
        "production_readiness_summary": str(package_dir / "production_results" / "production_readiness_summary.csv"),
        "production_target_readiness": str(package_dir / "production_results" / "production_target_readiness.csv"),
        "production_design_readiness": str(package_dir / "production_results" / "production_design_readiness.csv"),
        "production_gene_readiness": str(package_dir / "production_results" / "production_gene_readiness.csv"),
        "production_readiness_manifest": str(package_dir / "production_results" / "production_readiness_manifest.json"),
        "production_analysis_manifest": str(package_dir / "production_results" / "production_analysis_manifest.json"),
        "report": str(package_dir / "cobra_results" / "report.html"),
        "report_results_dir": str(package_dir / "report_results"),
        "report_bundle_manifest": str(package_dir / "report_results" / "report_manifest.json"),
        "report_selection": str(package_dir / "report_results" / "report_selection.csv"),
    }
    backend_rows = build_backend_status(sys.executable)
    write_csv(files["steps"], step_rows)
    write_csv(files["backend_status"], backend_rows)
    write_json(
        files["manifest"],
        {
            "schema_version": "0.1.0",
            "status": status,
            "message": message,
            "package_dir": str(package_dir),
            "workflow_selection": files["workflow_selection"],
            "model_variant_registry": files["model_variant_registry"],
            "step_count": len(step_rows),
            "files": files,
            "steps": step_rows,
        },
    )
    return UserPipelineResult(
        status=status,
        package_dir=str(package_dir),
        message=message,
        files=files,
        step_rows=step_rows,
    )
