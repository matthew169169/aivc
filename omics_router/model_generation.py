"""Model-generation workflow registry for staged user packages."""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .constraints import read_csv_records, write_csv, write_json
from .model_edit import attach_edit_artifact_paths, write_model_edit_artifacts


MODEL_GENERATION_METHODS: dict[str, dict[str, str]] = {
    "baseline_gem": {
        "label": "Baseline GEM",
        "description": "Register the uploaded GEM as the unmodified baseline model.",
        "recommended_next_analyses": "fba_pfba;model_qc;production_ecfactory",
    },
    "eflux": {
        "label": "E-Flux / Delta-FBA-ready model",
        "description": "Use transcriptomics evidence to build reaction-level expression constraints.",
        "recommended_next_analyses": "eflux_delta_fba;evidence_comparison;condition_interpretation",
    },
    "fastcore": {
        "label": "TROPPO FASTcore context model",
        "description": "Use high-confidence reactions as FASTcore core reactions for a context-specific model.",
        "recommended_next_analyses": "reaction_drilldown;production_ecfactory;readiness_gate",
    },
    "consensus_evidence": {
        "label": "Consensus evidence context model",
        "description": "Combine transcriptomics, relative proteomics, and ML-derived evidence modes.",
        "recommended_next_analyses": "evidence_comparison;reaction_drilldown;readiness_gate",
    },
    "enzyme_gecko": {
        "label": "Enzyme-capacity / GECKO-ready model",
        "description": "Use absolute proteomics and kcat priors to prepare enzyme capacity checks and GECKO input.",
        "recommended_next_analyses": "enzyme_capacity;production_ecfactory;readiness_gate",
    },
}


ANALYSIS_MODULES: dict[str, dict[str, str]] = {
    "fba_pfba": {
        "label": "FBA / pFBA / optional FVA",
        "description": "Run condition-specific COBRApy baseline flux analysis.",
    },
    "eflux_delta_fba": {
        "label": "E-Flux / Delta-FBA",
        "description": "Analyze transcriptomics-constrained flux changes.",
    },
    "evidence_comparison": {
        "label": "Evidence Mode Comparison",
        "description": "Compare transcriptomics, relative proteomics, consensus, and ML-derived evidence modes.",
    },
    "ml_pca_lasso": {
        "label": "ML PCA / LASSO-lite",
        "description": "Build feature matrices, PCA summaries, clusters, and LASSO-lite coefficients.",
    },
    "condition_interpretation": {
        "label": "Condition Interpretation Dashboard",
        "description": "Summarize omics coverage, conflicts, consensus softening, and guidance labels.",
    },
    "minn_export": {
        "label": "MINN-style Export",
        "description": "Export graph nodes, edges, omics tensor, labels, and target priors.",
    },
    "production_ecfactory": {
        "label": "Production Analysis / ecFactory-lite",
        "description": "Run production envelope, FSEOF-lite, KO/KD/OE ranking, and gene target aggregation.",
    },
    "readiness_gate": {
        "label": "Production Readiness Gate",
        "description": "Grade production targets using semantic, UniProt, kcat, and enzyme-constrained evidence.",
    },
    "hybrid_minn": {
        "label": "ML + GEM Hybrid Runner",
        "description": "Score targets with readiness priors, omics features, graph neighbors, and LOOCV sanity checks.",
    },
    "hybrid_graph_adapter": {
        "label": "PyG / DGL Graph Adapter",
        "description": "Export sparse/dense graph artifacts and optional PyG/DGL objects.",
    },
}


DEFAULT_MODEL_GENERATION_METHODS: tuple[str, ...] = tuple(MODEL_GENERATION_METHODS)
DEFAULT_ANALYSIS_MODULES: tuple[str, ...] = tuple(ANALYSIS_MODULES)
ANALYSIS_PARAMETER_DEFAULTS: dict[str, dict[str, object]] = {
    "uniprot_model_check": {
        "enable_uniprot_rest": False,
        "reviewed_only": False,
        "cache_policy": "use_cache_then_fetch",
    },
    "kcat_conflict": {
        "conflict_ratio_threshold": 2.0,
        "reviewed_source_bonus": True,
    },
    "dlkcat_external": {
        "run_dlkcat_external": False,
        "batch_size": 64,
        "timeout_seconds": 1800,
    },
    "memote_external": {
        "run_memote": False,
        "test_scope": "core",
        "config_path": "",
    },
    "pytfa_external": {
        "run_pytfa_external": False,
        "thermo_db_path": "",
        "temperature_kelvin": 298.15,
        "ph": 7.0,
        "ionic_strength_m": 0.25,
    },
    "fba_pfba": {
        "run_pfba": True,
        "run_fva": False,
        "fva_fraction_of_optimum": 0.95,
        "objective_reaction_id": "",
        "objective_direction": "max",
        "condition_filter": "",
        "fva_reaction_scope": "targets",
        "loopless": False,
        "pfba_factor": "",
        "fva_processes": 1,
    },
    "eflux_delta_fba": {
        "run_pfba": True,
        "reference_condition": "",
        "up_log2_threshold": 1.0,
        "down_log2_threshold": -1.0,
        "use_pfba_flux": True,
    },
    "ml_pca_lasso": {
        "min_overlap": 2,
        "prior_threshold": 0.5,
        "max_clusters": 2,
        "max_lasso_features": 5,
    },
    "production_ecfactory": {
        "biomass_fractions": [0.0, 0.25, 0.5, 0.75, 0.9],
        "fseof_fractions": [0.0, 0.25, 0.5, 0.75, 0.9],
        "biomass_reaction_id": "",
        "product_reaction_ids": "",
        "minimum_growth_fraction": 0.1,
        "max_candidates": 200,
        "max_growth_impact_candidates": 80,
        "intervention_strategy": "ko_kd_oe",
        "growth_loss_tolerance": 0.2,
    },
    "ml_hybrid_profile": {
        "task_type": "auto",
        "target_column": "",
        "feature_sources": "omics;flux;kcat_readiness;production",
        "benchmark_feature_sets": "all_features;omics_only;flux_only;readiness_or_kcat;production_related",
        "max_features": 50,
    },
}

MODEL_GENERATION_PARAMETER_DEFAULTS: dict[str, dict[str, object]] = {
    "baseline_gem": {
        "register_original_model": True,
        "baseline_label": "uploaded_baseline",
    },
    "eflux": {
        "min_expression_fraction": 0.05,
        "expression_scaling_mode": "max_per_condition",
        "protected_reaction_strategy": "objective_and_measured_exchange",
        "reference_condition": "",
        "up_log2_threshold": 1.0,
        "down_log2_threshold": -1.0,
        "run_pfba": True,
    },
    "fastcore": {
        "evidence_mode": "transcriptomics",
        "core_evidence_threshold": "high",
        "solver": "GLPK",
        "flux_threshold": 1e-4,
        "protect_objective": True,
        "protect_exchange_bounds": True,
        "filter_inactive_core": True,
        "run_feasibility_check": True,
    },
    "consensus_evidence": {
        "transcriptomics_weight": 1.0,
        "proteomics_weight": 1.0,
        "ml_prior_weight": 0.5,
        "conflict_strategy": "soften_by_consensus",
        "keep_threshold": 0.65,
        "delete_threshold": 0.2,
        "penalize_threshold": 0.4,
    },
    "troppo_methods": {
        "evidence_mode": "consensus",
        "imat_high_threshold": 2.0,
        "imat_low_threshold": 0.0,
        "imat_epsilon": 1e-4,
        "gimme_expression_threshold": 1.0,
        "gimme_objective_fraction": 0.9,
        "gimme_required_objective": "",
        "corda_hc_threshold": 2.0,
        "corda_mc_threshold": 1.0,
        "corda_nc_threshold": 0.0,
        "corda_negative_confidence_cost": 1.0,
        "metabolic_task_file": "",
        "protect_reactions": True,
        "execution_mode": "input_package_only",
    },
    "enzyme_gecko": {
        "ec_model_mode": "full_ecModel",
        "run_gecko_probe": False,
        "run_gecko_external": False,
    },
    "pytfa_export": {
        "concentration_unit_policy": "auto_convert_to_molar",
        "default_bound_strategy": "use_provided_bounds",
        "compartment_filter": "",
        "temperature_kelvin": 298.15,
        "ph": 7.0,
        "ionic_strength_m": 0.25,
        "thermo_db_path": "",
        "run_pytfa_external": False,
    },
}
MODEL_BACKED_ANALYSIS_METHODS: dict[str, set[str]] = {
    "fba_pfba": {"baseline_gem", "fastcore", "consensus_evidence"},
    "eflux_delta_fba": {"eflux"},
    "evidence_comparison": {"consensus_evidence", "eflux"},
    "ml_pca_lasso": set(MODEL_GENERATION_METHODS),
    "condition_interpretation": set(MODEL_GENERATION_METHODS),
    "minn_export": set(MODEL_GENERATION_METHODS),
    "production_ecfactory": {"baseline_gem", "enzyme_gecko", "fastcore", "consensus_evidence"},
    "readiness_gate": {"baseline_gem", "enzyme_gecko", "fastcore", "consensus_evidence"},
    "hybrid_minn": set(MODEL_GENERATION_METHODS),
    "hybrid_graph_adapter": set(MODEL_GENERATION_METHODS),
}


def normalize_model_generation_methods(methods: Iterable[str] | str | None) -> list[str]:
    """Return stable method IDs, preserving default behavior when methods is None."""

    return _normalize_selection(methods, MODEL_GENERATION_METHODS, DEFAULT_MODEL_GENERATION_METHODS)


def normalize_analysis_modules(modules: Iterable[str] | str | None) -> list[str]:
    """Return stable analysis module IDs, preserving default behavior when modules is None."""

    return _normalize_selection(modules, ANALYSIS_MODULES, DEFAULT_ANALYSIS_MODULES)


def normalize_model_generation_parameters(parameters: dict[str, Any] | None = None) -> dict[str, dict[str, object]]:
    """Return typed, bounded model-generation parameters."""

    normalized = _copy_nested_defaults(MODEL_GENERATION_PARAMETER_DEFAULTS)
    if parameters:
        for method_id, values in parameters.items():
            if not isinstance(values, dict):
                continue
            bucket = normalized.setdefault(str(method_id), {})
            for key, value in values.items():
                bucket[str(key)] = value

    eflux = normalized["eflux"]
    eflux["min_expression_fraction"] = _bounded_float(eflux.get("min_expression_fraction"), default=0.05, minimum=0.0, maximum=1.0)
    eflux["expression_scaling_mode"] = _one_of(eflux.get("expression_scaling_mode"), {"max_per_condition", "global_max"}, "max_per_condition")
    eflux["protected_reaction_strategy"] = _one_of(
        eflux.get("protected_reaction_strategy"),
        {"objective_and_measured_exchange", "objective_only", "none"},
        "objective_and_measured_exchange",
    )
    eflux["reference_condition"] = str(eflux.get("reference_condition") or "")
    eflux["up_log2_threshold"] = _bounded_float(eflux.get("up_log2_threshold"), default=1.0, minimum=0.0, maximum=20.0)
    eflux["down_log2_threshold"] = _bounded_float(eflux.get("down_log2_threshold"), default=-1.0, minimum=-20.0, maximum=0.0)
    eflux["run_pfba"] = _as_bool(eflux.get("run_pfba"), default=True)

    fastcore = normalized["fastcore"]
    fastcore["evidence_mode"] = _one_of(fastcore.get("evidence_mode"), {"transcriptomics", "consensus"}, "transcriptomics")
    fastcore["core_evidence_threshold"] = _one_of(fastcore.get("core_evidence_threshold"), {"high", "medium_or_high"}, "high")
    fastcore["solver"] = str(fastcore.get("solver") or "GLPK")
    fastcore["flux_threshold"] = _bounded_float(fastcore.get("flux_threshold"), default=1e-4, minimum=0.0, maximum=1.0)
    for key in ("protect_objective", "protect_exchange_bounds", "filter_inactive_core", "run_feasibility_check"):
        fastcore[key] = _as_bool(fastcore.get(key), default=True)

    consensus = normalized["consensus_evidence"]
    for key, default in (("transcriptomics_weight", 1.0), ("proteomics_weight", 1.0), ("ml_prior_weight", 0.5)):
        consensus[key] = _bounded_float(consensus.get(key), default=default, minimum=0.0, maximum=10.0)
    consensus["conflict_strategy"] = _one_of(
        consensus.get("conflict_strategy"),
        {"soften_by_consensus", "prefer_transcriptomics", "prefer_proteomics", "strict_conflict"},
        "soften_by_consensus",
    )
    for key, default in (("keep_threshold", 0.65), ("delete_threshold", 0.2), ("penalize_threshold", 0.4)):
        consensus[key] = _bounded_float(consensus.get(key), default=default, minimum=0.0, maximum=1.0)

    troppo = normalized["troppo_methods"]
    troppo["evidence_mode"] = _one_of(troppo.get("evidence_mode"), {"transcriptomics", "relative_proteomics", "consensus"}, "consensus")
    troppo["imat_high_threshold"] = _bounded_float(troppo.get("imat_high_threshold"), default=2.0, minimum=-100.0, maximum=100.0)
    troppo["imat_low_threshold"] = _bounded_float(troppo.get("imat_low_threshold"), default=0.0, minimum=-100.0, maximum=100.0)
    troppo["imat_epsilon"] = _bounded_float(troppo.get("imat_epsilon"), default=1e-4, minimum=0.0, maximum=1.0)
    troppo["gimme_expression_threshold"] = _bounded_float(troppo.get("gimme_expression_threshold"), default=1.0, minimum=-100.0, maximum=100.0)
    troppo["gimme_objective_fraction"] = _bounded_float(troppo.get("gimme_objective_fraction"), default=0.9, minimum=0.0, maximum=1.0)
    troppo["corda_hc_threshold"] = _bounded_float(troppo.get("corda_hc_threshold"), default=2.0, minimum=-100.0, maximum=100.0)
    troppo["corda_mc_threshold"] = _bounded_float(troppo.get("corda_mc_threshold"), default=1.0, minimum=-100.0, maximum=100.0)
    troppo["corda_nc_threshold"] = _bounded_float(troppo.get("corda_nc_threshold"), default=0.0, minimum=-100.0, maximum=100.0)
    troppo["corda_negative_confidence_cost"] = _bounded_float(troppo.get("corda_negative_confidence_cost"), default=1.0, minimum=0.0, maximum=100.0)
    troppo["protect_reactions"] = _as_bool(troppo.get("protect_reactions"), default=True)
    troppo["execution_mode"] = _one_of(troppo.get("execution_mode"), {"input_package_only", "optional_runner"}, "input_package_only")

    enzyme = normalized["enzyme_gecko"]
    enzyme["ec_model_mode"] = _one_of(enzyme.get("ec_model_mode"), {"full_ecModel", "light_ecModel"}, "full_ecModel")
    enzyme["run_gecko_probe"] = _as_bool(enzyme.get("run_gecko_probe"), default=False)
    enzyme["run_gecko_external"] = _as_bool(enzyme.get("run_gecko_external"), default=False)

    pytfa = normalized["pytfa_export"]
    pytfa["temperature_kelvin"] = _bounded_float(pytfa.get("temperature_kelvin"), default=298.15, minimum=250.0, maximum=330.0)
    pytfa["ph"] = _bounded_float(pytfa.get("ph"), default=7.0, minimum=0.0, maximum=14.0)
    pytfa["ionic_strength_m"] = _bounded_float(pytfa.get("ionic_strength_m"), default=0.25, minimum=0.0, maximum=2.0)
    pytfa["run_pytfa_external"] = _as_bool(pytfa.get("run_pytfa_external"), default=False)

    return normalized


def normalize_analysis_parameters(
    parameters: dict[str, Any] | None = None,
    *,
    run_pfba: bool = True,
    run_fva: bool = False,
    enable_uniprot_rest: bool = False,
    run_dlkcat_external: bool = False,
) -> dict[str, dict[str, object]]:
    """Return typed, bounded analysis parameters while preserving legacy flags."""

    normalized = _copy_parameter_defaults()
    normalized["fba_pfba"]["run_pfba"] = _as_bool(run_pfba)
    normalized["fba_pfba"]["run_fva"] = _as_bool(run_fva)
    normalized["eflux_delta_fba"]["run_pfba"] = _as_bool(run_pfba)
    normalized["uniprot_model_check"]["enable_uniprot_rest"] = _as_bool(enable_uniprot_rest)
    normalized["dlkcat_external"]["run_dlkcat_external"] = _as_bool(run_dlkcat_external)

    if parameters:
        for module_id, values in parameters.items():
            if not isinstance(values, dict):
                continue
            bucket = normalized.setdefault(str(module_id), {})
            for key, value in values.items():
                bucket[str(key)] = value

    normalized["fba_pfba"]["run_pfba"] = _as_bool(normalized["fba_pfba"].get("run_pfba"), default=True)
    normalized["fba_pfba"]["run_fva"] = _as_bool(normalized["fba_pfba"].get("run_fva"), default=False)
    normalized["fba_pfba"]["fva_fraction_of_optimum"] = _bounded_float(
        normalized["fba_pfba"].get("fva_fraction_of_optimum"),
        default=0.95,
        minimum=0.0,
        maximum=1.0,
    )
    normalized["fba_pfba"]["objective_reaction_id"] = str(normalized["fba_pfba"].get("objective_reaction_id") or "")
    normalized["fba_pfba"]["objective_direction"] = _one_of(normalized["fba_pfba"].get("objective_direction"), {"max", "min"}, "max")
    normalized["fba_pfba"]["condition_filter"] = str(normalized["fba_pfba"].get("condition_filter") or "")
    normalized["fba_pfba"]["fva_reaction_scope"] = _one_of(
        normalized["fba_pfba"].get("fva_reaction_scope"),
        {"targets", "all_reactions", "objective_and_targets"},
        "targets",
    )
    normalized["fba_pfba"]["loopless"] = _as_bool(normalized["fba_pfba"].get("loopless"), default=False)
    normalized["fba_pfba"]["pfba_factor"] = _optional_bounded_float(
        normalized["fba_pfba"].get("pfba_factor"),
        minimum=1.0,
        maximum=100.0,
    )
    normalized["fba_pfba"]["fva_processes"] = _bounded_int(
        normalized["fba_pfba"].get("fva_processes"),
        default=1,
        minimum=1,
        maximum=16,
    )
    normalized["eflux_delta_fba"]["run_pfba"] = _as_bool(
        normalized["eflux_delta_fba"].get("run_pfba"),
        default=bool(normalized["fba_pfba"]["run_pfba"]),
    )
    normalized["eflux_delta_fba"]["reference_condition"] = str(normalized["eflux_delta_fba"].get("reference_condition") or "")
    normalized["eflux_delta_fba"]["up_log2_threshold"] = _bounded_float(
        normalized["eflux_delta_fba"].get("up_log2_threshold"),
        default=1.0,
        minimum=0.0,
        maximum=20.0,
    )
    normalized["eflux_delta_fba"]["down_log2_threshold"] = _bounded_float(
        normalized["eflux_delta_fba"].get("down_log2_threshold"),
        default=-1.0,
        minimum=-20.0,
        maximum=0.0,
    )
    normalized["eflux_delta_fba"]["use_pfba_flux"] = _as_bool(normalized["eflux_delta_fba"].get("use_pfba_flux"), default=True)
    normalized["ml_pca_lasso"]["min_overlap"] = _bounded_int(
        normalized["ml_pca_lasso"].get("min_overlap"),
        default=2,
        minimum=2,
        maximum=1000,
    )
    normalized["ml_pca_lasso"]["prior_threshold"] = _bounded_float(
        normalized["ml_pca_lasso"].get("prior_threshold"),
        default=0.5,
        minimum=0.0,
        maximum=1.0,
    )
    normalized["ml_pca_lasso"]["max_clusters"] = _bounded_int(
        normalized["ml_pca_lasso"].get("max_clusters"),
        default=2,
        minimum=1,
        maximum=20,
    )
    normalized["ml_pca_lasso"]["max_lasso_features"] = _bounded_int(
        normalized["ml_pca_lasso"].get("max_lasso_features"),
        default=5,
        minimum=1,
        maximum=500,
    )
    normalized["production_ecfactory"]["biomass_fractions"] = _fraction_list(
        normalized["production_ecfactory"].get("biomass_fractions"),
        default=[0.0, 0.25, 0.5, 0.75, 0.9],
    )
    normalized["production_ecfactory"]["fseof_fractions"] = _fraction_list(
        normalized["production_ecfactory"].get("fseof_fractions"),
        default=[0.0, 0.25, 0.5, 0.75, 0.9],
    )
    normalized["production_ecfactory"]["biomass_reaction_id"] = str(normalized["production_ecfactory"].get("biomass_reaction_id") or "")
    normalized["production_ecfactory"]["product_reaction_ids"] = str(normalized["production_ecfactory"].get("product_reaction_ids") or "")
    normalized["production_ecfactory"]["minimum_growth_fraction"] = _bounded_float(
        normalized["production_ecfactory"].get("minimum_growth_fraction"),
        default=0.1,
        minimum=0.0,
        maximum=1.0,
    )
    normalized["production_ecfactory"]["max_candidates"] = _bounded_int(
        normalized["production_ecfactory"].get("max_candidates"),
        default=200,
        minimum=1,
        maximum=5000,
    )
    normalized["production_ecfactory"]["max_growth_impact_candidates"] = _bounded_int(
        normalized["production_ecfactory"].get("max_growth_impact_candidates"),
        default=80,
        minimum=0,
        maximum=1000,
    )
    normalized["production_ecfactory"]["intervention_strategy"] = _one_of(
        normalized["production_ecfactory"].get("intervention_strategy"),
        {"ko_kd_oe", "oe_only", "ko_kd_only"},
        "ko_kd_oe",
    )
    normalized["production_ecfactory"]["growth_loss_tolerance"] = _bounded_float(
        normalized["production_ecfactory"].get("growth_loss_tolerance"),
        default=0.2,
        minimum=0.0,
        maximum=1.0,
    )
    normalized["uniprot_model_check"]["enable_uniprot_rest"] = _as_bool(
        normalized["uniprot_model_check"].get("enable_uniprot_rest"),
        default=False,
    )
    normalized["uniprot_model_check"]["reviewed_only"] = _as_bool(
        normalized["uniprot_model_check"].get("reviewed_only"),
        default=False,
    )
    normalized["uniprot_model_check"]["cache_policy"] = _one_of(
        normalized["uniprot_model_check"].get("cache_policy"),
        {"use_cache_then_fetch", "cache_only", "refresh_failed"},
        "use_cache_then_fetch",
    )
    normalized["kcat_conflict"]["conflict_ratio_threshold"] = _bounded_float(
        normalized["kcat_conflict"].get("conflict_ratio_threshold"),
        default=2.0,
        minimum=1.0,
        maximum=1000.0,
    )
    normalized["kcat_conflict"]["reviewed_source_bonus"] = _as_bool(normalized["kcat_conflict"].get("reviewed_source_bonus"), default=True)
    normalized["dlkcat_external"]["run_dlkcat_external"] = _as_bool(
        normalized["dlkcat_external"].get("run_dlkcat_external"),
        default=False,
    )
    normalized["dlkcat_external"]["batch_size"] = _bounded_int(normalized["dlkcat_external"].get("batch_size"), default=64, minimum=1, maximum=1024)
    normalized["dlkcat_external"]["timeout_seconds"] = _bounded_int(normalized["dlkcat_external"].get("timeout_seconds"), default=1800, minimum=30, maximum=86400)
    normalized["memote_external"]["run_memote"] = _as_bool(normalized["memote_external"].get("run_memote"), default=False)
    normalized["memote_external"]["test_scope"] = _one_of(normalized["memote_external"].get("test_scope"), {"core", "full", "custom_config"}, "core")
    normalized["pytfa_external"]["run_pytfa_external"] = _as_bool(normalized["pytfa_external"].get("run_pytfa_external"), default=False)
    normalized["pytfa_external"]["temperature_kelvin"] = _bounded_float(normalized["pytfa_external"].get("temperature_kelvin"), default=298.15, minimum=250.0, maximum=330.0)
    normalized["pytfa_external"]["ph"] = _bounded_float(normalized["pytfa_external"].get("ph"), default=7.0, minimum=0.0, maximum=14.0)
    normalized["pytfa_external"]["ionic_strength_m"] = _bounded_float(normalized["pytfa_external"].get("ionic_strength_m"), default=0.25, minimum=0.0, maximum=2.0)
    normalized["ml_hybrid_profile"]["task_type"] = _one_of(normalized["ml_hybrid_profile"].get("task_type"), {"auto", "regression", "classification", "survival", "multi_task"}, "auto")
    normalized["ml_hybrid_profile"]["max_features"] = _bounded_int(normalized["ml_hybrid_profile"].get("max_features"), default=50, minimum=1, maximum=5000)
    return normalized


def analysis_parameter_summary_rows(parameters: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    """Flatten nested analysis parameters into a stable CSV-friendly table."""

    rows: list[dict[str, object]] = []
    for module_id in sorted(parameters):
        for key, value in sorted(parameters[module_id].items()):
            rows.append(
                {
                    "analysis_module": module_id,
                    "parameter": key,
                    "value": _parameter_value_text(value),
                    "value_type": type(value).__name__,
                }
            )
    return rows


def write_analysis_parameters(
    output_dir: str | Path,
    parameters: dict[str, dict[str, object]],
) -> dict[str, str]:
    """Write explicit analysis parameter choices for UI, reports, and tests."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "analysis_parameters.json"
    summary_path = output / "analysis_parameters_summary.csv"
    write_json(json_path, {"schema_version": "0.1.0", "analysis_parameters": parameters})
    write_csv(summary_path, analysis_parameter_summary_rows(parameters))
    return {"json": str(json_path), "summary": str(summary_path)}


def model_generation_parameter_summary_rows(parameters: dict[str, dict[str, object]]) -> list[dict[str, object]]:
    """Flatten nested model-generation parameters into a stable CSV-friendly table."""

    rows: list[dict[str, object]] = []
    for method_id in sorted(parameters):
        for key, value in sorted(parameters[method_id].items()):
            rows.append(
                {
                    "model_generation_method": method_id,
                    "parameter": key,
                    "value": _parameter_value_text(value),
                    "value_type": type(value).__name__,
                }
            )
    return rows


def write_model_generation_parameters(
    output_dir: str | Path,
    parameters: dict[str, dict[str, object]],
) -> dict[str, str]:
    """Write explicit model-generation parameter choices for UI, reports, and tests."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "model_generation_parameters.json"
    summary_path = output / "model_generation_parameters_summary.csv"
    write_json(json_path, {"schema_version": "0.1.0", "model_generation_parameters": parameters})
    write_csv(summary_path, model_generation_parameter_summary_rows(parameters))
    return {"json": str(json_path), "summary": str(summary_path)}


def workflow_parameter_schema() -> dict[str, object]:
    """Return UI metadata for model-generation and analysis parameter panels."""

    return {
        "schema_version": "0.1.0",
        "presets": {
            "conservative": "Use stable low-cost defaults.",
            "paper_like": "Approximate original method workflows where supported.",
            "exploratory": "Enable broader scans and more candidate output.",
        },
        "model_generation": _schema_group(MODEL_GENERATION_PARAMETER_DEFAULTS, "model_generation"),
        "analysis": _schema_group(ANALYSIS_PARAMETER_DEFAULTS, "analysis"),
    }


def workflow_parameter_preview(
    *,
    model_generation_parameters: dict[str, Any] | None = None,
    analysis_parameters: dict[str, Any] | None = None,
    selected_model_generation_methods: Iterable[str] | str | None = None,
    selected_analysis_modules: Iterable[str] | str | None = None,
) -> dict[str, object]:
    """Normalize workflow parameters without running the workflow."""

    normalized_generation = normalize_model_generation_parameters(model_generation_parameters)
    normalized_analysis = normalize_analysis_parameters(analysis_parameters)
    selected_methods = normalize_model_generation_methods(selected_model_generation_methods)
    selected_modules = normalize_analysis_modules(selected_analysis_modules)
    return {
        "schema_version": "0.1.0",
        "status": "ok",
        "model_generation_parameters": normalized_generation,
        "analysis_parameters": normalized_analysis,
        "changed_model_generation_parameters": _changed_rows(
            normalized_generation,
            MODEL_GENERATION_PARAMETER_DEFAULTS,
            "model_generation_method",
        ),
        "changed_analysis_parameters": _changed_rows(normalized_analysis, ANALYSIS_PARAMETER_DEFAULTS, "analysis_module"),
        "compatibility_warnings": _parameter_warnings(normalized_generation, normalized_analysis, selected_methods, selected_modules),
    }


def normalize_selected_model_variant_ids(selected: Iterable[str] | str | None) -> list[str]:
    """Return explicit model-variant IDs from a UI selection."""

    if selected is None:
        return []
    if isinstance(selected, str):
        raw_items = [part.strip() for part in selected.replace(";", ",").split(",")]
    else:
        raw_items = [str(item).strip() for item in selected]
    seen: set[str] = set()
    normalized: list[str] = []
    for item in raw_items:
        if item and item not in seen:
            normalized.append(item)
            seen.add(item)
    return normalized


def write_analysis_selection(
    output_dir: str | Path,
    *,
    selected_model_generation_methods: Iterable[str],
    selected_analysis_modules: Iterable[str],
    selected_model_variant_id: Iterable[str] | str | None = "",
    report_preset: str = "full_audit_report",
    selected_report_variant_ids: Iterable[str] | str | None = None,
) -> Path:
    """Write the user's explicit workflow choices for UI and reports."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    selected_methods = set(selected_model_generation_methods)
    selected_modules = set(selected_analysis_modules)
    selected_variant_ids = normalize_selected_model_variant_ids(selected_model_variant_id)
    selected_variant_text = ";".join(selected_variant_ids)
    report_variant_ids = normalize_selected_model_variant_ids(selected_report_variant_ids)
    if not report_variant_ids:
        report_variant_ids = selected_variant_ids
    rows: list[dict[str, object]] = []
    for method_id, spec in MODEL_GENERATION_METHODS.items():
        rows.append(
            {
                "selection_type": "model_generation",
                "selection_id": method_id,
                "label": spec["label"],
                "selected": method_id in selected_methods,
                "selected_model_variant_id": "",
                "description": spec["description"],
            }
        )
    for module_id, spec in ANALYSIS_MODULES.items():
        rows.append(
            {
                "selection_type": "analysis",
                "selection_id": module_id,
                "label": spec["label"],
                "selected": module_id in selected_modules,
                "selected_model_variant_id": selected_variant_text,
                "description": spec["description"],
            }
        )
    rows.append(
        {
            "selection_type": "report_builder",
            "selection_id": report_preset,
            "label": "Report Builder Preset",
            "selected": True,
            "selected_model_variant_id": ";".join(report_variant_ids),
            "description": "Selected report preset for report_results output.",
        }
    )
    path = output / "workflow_selection.csv"
    write_csv(path, rows)
    return path


def read_model_variant_registry(package_dir: str | Path) -> list[dict[str, str]]:
    """Read a package's model-variant registry."""

    path = Path(package_dir) / "workflow_results" / "model_variant_registry.csv"
    if not path.exists() or path.stat().st_size == 0:
        return []
    return read_csv_records(path)


def resolve_analysis_variant(
    registry_rows: list[dict[str, str]],
    selected_model_variant_id: Iterable[str] | str | None = "",
) -> dict[str, str]:
    """Resolve the active model variant used for downstream analysis."""

    selected_ids = normalize_selected_model_variant_ids(selected_model_variant_id)
    if selected_ids:
        selected = selected_ids[0]
        for row in registry_rows:
            if row.get("variant_id") == selected:
                return dict(row)
    usable_statuses = {"generated", "staged", "evidence_prepared", "inputs_prepared"}
    usable_rows = [row for row in registry_rows if row.get("generation_status") in usable_statuses]
    for row in usable_rows:
        if row.get("generation_method") == "baseline_gem":
            return dict(row)
    if usable_rows:
        return dict(usable_rows[0])
    return dict(registry_rows[0]) if registry_rows else {}


def build_analysis_variant_context(
    registry_rows: list[dict[str, str]],
    *,
    selected_analysis_modules: Iterable[str] | str | None,
    selected_model_variant_id: Iterable[str] | str | None = "",
) -> list[dict[str, object]]:
    """Build per-analysis compatibility rows for the active model variant."""

    modules = normalize_analysis_modules(selected_analysis_modules)
    active_variant = resolve_analysis_variant(registry_rows, selected_model_variant_id)
    active_method = active_variant.get("generation_method", "")
    active_status = active_variant.get("generation_status", "")
    rows: list[dict[str, object]] = []
    for module_id in modules:
        compatible = _is_analysis_compatible(module_id, active_variant)
        rows.append(
            {
                "analysis_module": module_id,
                "analysis_label": ANALYSIS_MODULES[module_id]["label"],
                "selected": True,
                "active_variant_id": active_variant.get("variant_id", ""),
                "active_variant_status": active_status,
                "active_generation_method": active_method,
                "active_generation_method_label": active_variant.get("generation_method_label", ""),
                "compatible": compatible,
                "execution_scope": _analysis_execution_scope(module_id, active_method, compatible),
                "active_model_path": _analysis_active_model_path(active_variant),
                "active_model_source": _analysis_active_model_source(active_variant),
                "primary_artifact": active_variant.get("primary_artifact", ""),
                "context_model_sbml": active_variant.get("context_model_sbml", ""),
                "guidance": _analysis_variant_guidance(module_id, active_variant, compatible),
            }
        )
    return rows


def write_analysis_variant_context(
    output_dir: str | Path,
    rows: list[dict[str, object]],
) -> Path:
    """Write the active-variant context rows used by downstream analysis dispatch."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    path = output / "analysis_variant_context.csv"
    write_csv(path, rows)
    return path


def write_model_variant_registry(
    output_dir: str | Path,
    *,
    package_dir: str | Path,
    model_path: str | Path,
    constraints_dir: str | Path,
    cobra_results_dir: str | Path,
    transcriptomics_flux_dir: str | Path,
    troppo_dir: str | Path,
    evidence_mode_dir: str | Path,
    enzyme_results_dir: str | Path,
    gecko_package_dir: str | Path,
    model_artifacts_dir: str | Path | None = None,
    selected_methods: Iterable[str] | str | None = None,
) -> Path:
    """Write a registry of model variants generated or staged for downstream analysis."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    methods = normalize_model_generation_methods(selected_methods)
    rows = build_model_variant_registry(
        package_dir=package_dir,
        model_path=model_path,
        constraints_dir=constraints_dir,
        cobra_results_dir=cobra_results_dir,
        transcriptomics_flux_dir=transcriptomics_flux_dir,
        troppo_dir=troppo_dir,
        evidence_mode_dir=evidence_mode_dir,
        enzyme_results_dir=enzyme_results_dir,
        gecko_package_dir=gecko_package_dir,
        model_artifacts_dir=model_artifacts_dir,
        selected_methods=methods,
    )
    edit_result = write_model_edit_artifacts(package_dir=package_dir, registry_rows=rows, output_dir=output)
    rows = attach_edit_artifact_paths(rows, edit_result)
    registry_path = output / "model_variant_registry.csv"
    manifest_path = output / "model_variant_registry_manifest.json"
    write_csv(registry_path, rows)
    write_json(
        manifest_path,
        {
            "schema_version": "0.1.0",
            "package_dir": str(Path(package_dir)),
            "selected_methods": methods,
            "variant_count": len(rows),
            "generated_count": sum(1 for row in rows if row.get("generation_status") in {"generated", "staged"}),
            "registry": str(registry_path),
            "edit_reaction_index": edit_result.get("index_path", ""),
            "edit_manifest_dir": edit_result.get("manifest_dir", ""),
            "edit_record_count": edit_result.get("row_count", 0),
        },
    )
    return registry_path


def build_model_variant_registry(
    *,
    package_dir: str | Path,
    model_path: str | Path,
    constraints_dir: str | Path,
    cobra_results_dir: str | Path,
    transcriptomics_flux_dir: str | Path,
    troppo_dir: str | Path,
    evidence_mode_dir: str | Path,
    enzyme_results_dir: str | Path,
    gecko_package_dir: str | Path,
    model_artifacts_dir: str | Path | None = None,
    selected_methods: Iterable[str] | str | None = None,
) -> list[dict[str, object]]:
    """Build registry rows for selected model-generation methods."""

    package = Path(package_dir)
    model = Path(model_path)
    constraints = Path(constraints_dir)
    cobra = Path(cobra_results_dir)
    tx_flux = Path(transcriptomics_flux_dir)
    troppo = Path(troppo_dir)
    evidence = Path(evidence_mode_dir)
    enzyme = Path(enzyme_results_dir)
    gecko = Path(gecko_package_dir)
    artifacts = Path(model_artifacts_dir) if model_artifacts_dir else package / "workflow_results" / "model_artifacts"
    methods = normalize_model_generation_methods(selected_methods)
    rows: list[dict[str, object]] = []

    if "baseline_gem" in methods:
        for condition in _conditions_from_csv(cobra / "fba_summary.csv", fallback=_conditions_from_csv(constraints / "exchange_bounds.csv")):
            rows.append(
                _variant_row(
                    variant_id=f"baseline_gem__{_slug(condition)}",
                    method_id="baseline_gem",
                    condition=condition,
                    evidence_mode="none",
                    source_model_path=model,
                    primary_artifact=model,
                    supporting_files=[cobra / "fba_summary.csv", constraints / "exchange_bounds.csv"],
                    status="generated" if model.exists() else "missing_model",
                    confidence_label="baseline",
                    guidance="Use this as the reference GEM before applying omics-derived constraints.",
                )
            )

    if "eflux" in methods:
        conditions = _conditions_from_csv(tx_flux / "eflux_summary.csv", fallback=_conditions_from_csv(constraints / "reaction_expression_evidence.csv"))
        tx_input = _first_existing([constraints / "reaction_expression_evidence.csv", constraints / "gene_expression_evidence.csv"])
        for condition in conditions:
            rows.append(
                _variant_row(
                    variant_id=f"eflux__{_slug(condition)}",
                    method_id="eflux",
                    condition=condition,
                    evidence_mode="transcriptomics",
                    source_model_path=model,
                    primary_artifact=tx_flux / "eflux_summary.csv",
                    supporting_files=[
                        constraints / "gene_expression_evidence.csv",
                        constraints / "reaction_expression_evidence.csv",
                        tx_flux / "delta_fba_summary.csv",
                    ],
                    status="generated" if (tx_flux / "eflux_summary.csv").exists() else "evidence_prepared" if tx_input else "missing_transcriptomics_evidence",
                    confidence_label="usable_with_caution" if tx_input else "not_ready",
                    guidance="Use for expression-constrained interpretation; inspect gene/reaction mapping before treating it as quantitative.",
                )
            )

    if "fastcore" in methods:
        conditions = _conditions_from_csv(troppo / "troppo_fastcore_summary.csv", fallback=_conditions_from_csv(constraints / "fastcore_core_reactions.csv"))
        for condition in conditions:
            variant_id = f"fastcore__{_slug(condition)}"
            artifact_manifest = _artifact_manifest_path(artifacts, variant_id)
            rows.append(
                _variant_row(
                    variant_id=variant_id,
                    method_id="fastcore",
                    condition=condition,
                    evidence_mode="transcriptomics_core",
                    source_model_path=model,
                    primary_artifact=artifact_manifest if artifact_manifest.exists() else troppo / "troppo_fastcore_selected_reactions.csv",
                    supporting_files=[
                        artifact_manifest,
                        artifacts / variant_id / "context_model.xml",
                        constraints / "fastcore_core_reactions.csv",
                        constraints / "context_reaction_policy.csv",
                        troppo / "troppo_fastcore_summary.csv",
                        artifacts / variant_id / "context_keep_reactions.csv",
                        artifacts / variant_id / "context_delete_reactions.csv",
                    ],
                    status="generated" if artifact_manifest.exists() or (troppo / "troppo_fastcore_selected_reactions.csv").exists() else "inputs_prepared" if (constraints / "fastcore_core_reactions.csv").exists() else "missing_fastcore_inputs",
                    confidence_label="context_model_candidate",
                    guidance="Use as a context-specific model candidate; review removed reactions and feasibility before downstream design.",
                )
            )

    if "consensus_evidence" in methods:
        conditions = _conditions_from_csv(
            evidence / "evidence_mode_summary.csv",
            fallback=_conditions_from_csv(constraints / "multi_omics_consensus_reaction_evidence.csv"),
        )
        for condition in conditions:
            variant_id = f"consensus_context__{_slug(condition)}"
            artifact_manifest = _artifact_manifest_path(artifacts, variant_id)
            rows.append(
                _variant_row(
                    variant_id=variant_id,
                    method_id="consensus_evidence",
                    condition=condition,
                    evidence_mode="multi_omics_consensus",
                    source_model_path=model,
                    primary_artifact=artifact_manifest if artifact_manifest.exists() else constraints / "consensus_context_reaction_policy.csv",
                    supporting_files=[
                        artifact_manifest,
                        artifacts / variant_id / "context_model.xml",
                        constraints / "multi_omics_consensus_reaction_evidence.csv",
                        constraints / "multi_omics_conflict_summary.csv",
                        evidence / "evidence_mode_summary.csv",
                        artifacts / variant_id / "context_keep_reactions.csv",
                        artifacts / variant_id / "context_delete_reactions.csv",
                        artifacts / variant_id / "context_penalize_reactions.csv",
                    ],
                    status="generated" if artifact_manifest.exists() or (constraints / "consensus_context_reaction_policy.csv").exists() else "missing_consensus_evidence",
                    confidence_label="usable_with_caution",
                    guidance="Use when transcriptomics/proteomics evidence has been reconciled; inspect conflict-softened reactions.",
                )
            )

    if "enzyme_gecko" in methods:
        conditions = _conditions_from_csv(enzyme / "enzyme_qc_summary.csv", fallback=["ALL"])
        for condition in conditions:
            rows.append(
                _variant_row(
                    variant_id=f"enzyme_gecko__{_slug(condition)}",
                    method_id="enzyme_gecko",
                    condition=condition,
                    evidence_mode="absolute_proteomics_kcat",
                    source_model_path=model,
                    primary_artifact=gecko / "gecko_export_summary.csv",
                    supporting_files=[
                        constraints / "protein_abundance.csv",
                        constraints / "kcat_priors.csv",
                        enzyme / "reaction_enzyme_capacity.csv",
                        gecko / "kcat_table.tsv",
                    ],
                    status="staged" if (gecko / "gecko_export_summary.csv").exists() else "missing_absolute_proteomics_or_kcat",
                    confidence_label="enzyme_constrained_candidate",
                    guidance="Use for GECKO/ecFactory handoff or capacity checks; review kcat evidence tier and conflict flags.",
                )
            )

    if not rows:
        rows.append(
            {
                "variant_id": "no_model_generation_selected",
                "variant_label": "No model generation selected",
                "method": "",
                "generation_method": "",
                "generation_method_label": "",
                "condition": "",
                "evidence_mode": "",
                "generation_status": "not_selected",
                "confidence": "",
                "confidence_label": "",
                "source_model_path": str(model),
                "primary_model_path": str(model),
                "primary_artifact": "",
                "context_model_sbml": "",
                "supporting_files": "",
                "generated_files": "",
                "compatible_analyses": "",
                "recommended_next_analyses": "",
                "guidance": "Select at least one model-generation method before running downstream analysis.",
            }
        )
    return rows


def write_context_model_artifacts(
    output_dir: str | Path,
    *,
    package_dir: str | Path,
    model_path: str | Path,
    constraints_dir: str | Path,
    troppo_dir: str | Path,
    selected_methods: Iterable[str] | str | None = None,
) -> Path:
    """Write standardized context-model artifact packages for selected context methods."""

    output = Path(output_dir)
    artifact_root = output / "model_artifacts"
    artifact_root.mkdir(parents=True, exist_ok=True)
    methods = set(normalize_model_generation_methods(selected_methods))
    constraints = Path(constraints_dir)
    troppo = Path(troppo_dir)
    summary_rows: list[dict[str, object]] = []
    if "fastcore" in methods:
        summary_rows.extend(
            _write_fastcore_artifacts(
                artifact_root=artifact_root,
                package_dir=package_dir,
                model_path=model_path,
                selected_path=troppo / "troppo_fastcore_selected_reactions.csv",
                removed_path=troppo / "troppo_fastcore_removed_reactions.csv",
                core_path=constraints / "fastcore_core_reactions.csv",
                policy_path=constraints / "context_reaction_policy.csv",
            )
        )
    if "consensus_evidence" in methods:
        summary_rows.extend(
            _write_consensus_artifacts(
                artifact_root=artifact_root,
                package_dir=package_dir,
                model_path=model_path,
                keep_path=constraints / "consensus_context_keep_reactions.csv",
                delete_path=constraints / "consensus_context_delete_candidates.csv",
                penalize_path=constraints / "consensus_context_penalize_candidates.csv",
                core_path=constraints / "consensus_fastcore_core_reactions.csv",
                policy_path=constraints / "consensus_context_reaction_policy.csv",
            )
        )
    if not summary_rows:
        summary_rows.append(
            {
                "variant_id": "",
                "generation_method": "",
                "condition": "",
                "artifact_status": "skipped",
                "artifact_format": "reaction_set_package",
                "manifest": "",
                "keep_count": 0,
                "delete_count": 0,
                "penalize_count": 0,
                "core_count": 0,
                "guidance": "No context model-generation method was selected.",
            }
        )
    summary_path = output / "context_model_artifact_summary.csv"
    write_csv(summary_path, summary_rows)
    write_json(
        output / "context_model_artifact_manifest.json",
        {
            "schema_version": "0.1.0",
            "package_dir": str(Path(package_dir)),
            "model_path": str(Path(model_path)),
            "artifact_root": str(artifact_root),
            "selected_methods": sorted(methods),
            "artifact_count": sum(1 for row in summary_rows if row.get("artifact_status") == "generated"),
            "summary": str(summary_path),
        },
    )
    return summary_path


def _write_fastcore_artifacts(
    *,
    artifact_root: Path,
    package_dir: str | Path,
    model_path: str | Path,
    selected_path: Path,
    removed_path: Path,
    core_path: Path,
    policy_path: Path,
) -> list[dict[str, object]]:
    selected_rows = _read_rows(selected_path)
    removed_rows = _read_rows(removed_path)
    core_rows = _read_rows(core_path)
    conditions = _conditions_from_rows(selected_rows) or _conditions_from_rows(core_rows) or ["ALL"]
    summary_rows: list[dict[str, object]] = []
    for condition in conditions:
        variant_id = f"fastcore__{_slug(condition)}"
        selected_for_condition = _rows_for_condition(selected_rows, condition)
        removed_for_condition = _rows_for_condition(removed_rows, condition)
        core_for_condition = [
            row
            for row in selected_for_condition
            if str(row.get("role", "")).lower() == "core" or str(row.get("core_source", "")).lower() not in {"", "supporting"}
        ]
        if not core_for_condition:
            core_for_condition = _rows_for_condition(core_rows, condition)
        keep_rows = _standardize_reaction_rows(selected_for_condition, condition, "keep", "fastcore", selected_path)
        delete_rows = _standardize_reaction_rows(removed_for_condition, condition, "delete", "fastcore", removed_path)
        core_artifact_rows = _standardize_reaction_rows(core_for_condition, condition, "core", "fastcore", core_path)
        summary_rows.append(
            _write_context_artifact_package(
                artifact_root=artifact_root,
                package_dir=package_dir,
                model_path=model_path,
                variant_id=variant_id,
                generation_method="fastcore",
                condition=condition,
                evidence_mode="transcriptomics_core",
                keep_rows=keep_rows,
                delete_rows=delete_rows,
                penalize_rows=[],
                core_rows=core_artifact_rows,
                selected_rows=keep_rows,
                source_files=[selected_path, removed_path, core_path, policy_path],
                guidance="FASTcore artifact package records selected, removed, and core reactions; no pruned SBML is emitted in v1.",
            )
        )
    return summary_rows


def _write_consensus_artifacts(
    *,
    artifact_root: Path,
    package_dir: str | Path,
    model_path: str | Path,
    keep_path: Path,
    delete_path: Path,
    penalize_path: Path,
    core_path: Path,
    policy_path: Path,
) -> list[dict[str, object]]:
    keep_source_rows = _read_rows(keep_path)
    delete_source_rows = _read_rows(delete_path)
    penalize_source_rows = _read_rows(penalize_path)
    core_source_rows = _read_rows(core_path)
    conditions = (
        _conditions_from_rows(keep_source_rows)
        or _conditions_from_rows(delete_source_rows)
        or _conditions_from_rows(core_source_rows)
        or ["ALL"]
    )
    summary_rows: list[dict[str, object]] = []
    for condition in conditions:
        variant_id = f"consensus_context__{_slug(condition)}"
        keep_rows = _standardize_reaction_rows(
            _rows_for_condition(keep_source_rows, condition),
            condition,
            "keep",
            "consensus_evidence",
            keep_path,
        )
        delete_rows = _standardize_reaction_rows(
            _rows_for_condition(delete_source_rows, condition),
            condition,
            "delete",
            "consensus_evidence",
            delete_path,
        )
        penalize_rows = _standardize_reaction_rows(
            _rows_for_condition(penalize_source_rows, condition),
            condition,
            "penalize",
            "consensus_evidence",
            penalize_path,
        )
        core_rows = _standardize_reaction_rows(
            _rows_for_condition(core_source_rows, condition),
            condition,
            "core",
            "consensus_evidence",
            core_path,
        )
        selected_rows = _dedupe_reaction_rows([*keep_rows, *core_rows], condition)
        summary_rows.append(
            _write_context_artifact_package(
                artifact_root=artifact_root,
                package_dir=package_dir,
                model_path=model_path,
                variant_id=variant_id,
                generation_method="consensus_evidence",
                condition=condition,
                evidence_mode="multi_omics_consensus",
                keep_rows=keep_rows,
                delete_rows=delete_rows,
                penalize_rows=penalize_rows,
                core_rows=core_rows,
                selected_rows=selected_rows,
                source_files=[keep_path, delete_path, penalize_path, core_path, policy_path],
                guidance="Consensus artifact package records keep/delete/penalize/core reactions; inspect conflicts before treating it as a final context model.",
            )
        )
    return summary_rows


def _write_context_artifact_package(
    *,
    artifact_root: Path,
    package_dir: str | Path,
    model_path: str | Path,
    variant_id: str,
    generation_method: str,
    condition: str,
    evidence_mode: str,
    keep_rows: list[dict[str, object]],
    delete_rows: list[dict[str, object]],
    penalize_rows: list[dict[str, object]],
    core_rows: list[dict[str, object]],
    selected_rows: list[dict[str, object]],
    source_files: list[Path],
    guidance: str,
) -> dict[str, object]:
    artifact_dir = artifact_root / variant_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "selected_reactions": artifact_dir / "context_selected_reactions.csv",
        "keep_reactions": artifact_dir / "context_keep_reactions.csv",
        "delete_reactions": artifact_dir / "context_delete_reactions.csv",
        "penalize_reactions": artifact_dir / "context_penalize_reactions.csv",
        "core_reactions": artifact_dir / "context_core_reactions.csv",
        "context_model_sbml": artifact_dir / "context_model.xml",
        "manifest": artifact_dir / "context_model_artifact_manifest.json",
    }
    write_csv(paths["selected_reactions"], selected_rows)
    write_csv(paths["keep_reactions"], keep_rows)
    write_csv(paths["delete_reactions"], delete_rows)
    write_csv(paths["penalize_reactions"], penalize_rows)
    write_csv(paths["core_reactions"], core_rows)
    existing_sources = [str(path) for path in source_files if path.exists()]
    artifact_status = "generated" if selected_rows or keep_rows or delete_rows or core_rows or penalize_rows else "empty"
    sbml_export = _export_pruned_context_sbml(
        source_model_path=Path(model_path),
        output_path=paths["context_model_sbml"],
        delete_rows=delete_rows,
    )
    write_json(
        paths["manifest"],
        {
            "schema_version": "0.1.0",
            "variant_id": variant_id,
            "generation_method": generation_method,
            "condition": condition,
            "evidence_mode": evidence_mode,
            "artifact_status": artifact_status,
            "artifact_format": "reaction_set_package",
            "package_dir": str(Path(package_dir)),
            "source_model_path": str(Path(model_path)),
            "context_model_sbml": sbml_export["context_model_sbml"],
            "context_model_export_status": sbml_export["status"],
            "context_model_export_message": sbml_export["message"],
            "files": {key: str(path) for key, path in paths.items() if key != "manifest"},
            "source_files": existing_sources,
            "counts": {
                "selected_count": len(selected_rows),
                "keep_count": len(keep_rows),
                "delete_count": len(delete_rows),
                "penalize_count": len(penalize_rows),
                "core_count": len(core_rows),
                "removed_reaction_count": sbml_export["removed_reaction_count"],
                "missing_delete_reaction_count": sbml_export["missing_delete_reaction_count"],
                "initial_reaction_count": sbml_export["initial_reaction_count"],
                "final_reaction_count": sbml_export["final_reaction_count"],
            },
            "guidance": guidance,
        },
    )
    return {
        "variant_id": variant_id,
        "generation_method": generation_method,
        "condition": condition,
        "evidence_mode": evidence_mode,
        "artifact_status": artifact_status,
        "artifact_format": "reaction_set_package",
        "artifact_dir": str(artifact_dir),
        "manifest": str(paths["manifest"]),
        "context_model_sbml": sbml_export["context_model_sbml"],
        "context_model_export_status": sbml_export["status"],
        "context_model_export_message": sbml_export["message"],
        "selected_reactions": str(paths["selected_reactions"]),
        "keep_reactions": str(paths["keep_reactions"]),
        "delete_reactions": str(paths["delete_reactions"]),
        "penalize_reactions": str(paths["penalize_reactions"]),
        "core_reactions": str(paths["core_reactions"]),
        "selected_count": len(selected_rows),
        "keep_count": len(keep_rows),
        "delete_count": len(delete_rows),
        "penalize_count": len(penalize_rows),
        "core_count": len(core_rows),
        "removed_reaction_count": sbml_export["removed_reaction_count"],
        "missing_delete_reaction_count": sbml_export["missing_delete_reaction_count"],
        "initial_reaction_count": sbml_export["initial_reaction_count"],
        "final_reaction_count": sbml_export["final_reaction_count"],
        "guidance": guidance,
    }


def _variant_row(
    *,
    variant_id: str,
    method_id: str,
    condition: str,
    evidence_mode: str,
    source_model_path: Path,
    primary_artifact: Path,
    supporting_files: list[Path],
    status: str,
    confidence_label: str,
    guidance: str,
) -> dict[str, object]:
    spec = MODEL_GENERATION_METHODS[method_id]
    existing_support = [str(path) for path in supporting_files if path.exists()]
    context_model_sbml = _context_model_sbml_from_manifest(primary_artifact)
    primary_model_path = _primary_model_path(
        method_id=method_id,
        source_model_path=source_model_path,
        primary_artifact=primary_artifact,
        context_model_sbml=context_model_sbml,
    )
    generated_files = _generated_files(
        primary_artifact=primary_artifact,
        context_model_sbml=context_model_sbml,
        supporting_files=existing_support,
    )
    row = {
        "variant_id": variant_id,
        "variant_label": f"{spec['label']} ({condition})",
        "method": method_id,
        "generation_method": method_id,
        "generation_method_label": spec["label"],
        "condition": condition,
        "evidence_mode": evidence_mode,
        "generation_status": status,
        "confidence": confidence_label,
        "confidence_label": confidence_label,
        "source_model_path": str(source_model_path),
        "primary_model_path": primary_model_path,
        "primary_artifact": str(primary_artifact) if primary_artifact.exists() else "",
        "context_model_sbml": context_model_sbml,
        "supporting_files": ";".join(existing_support),
        "generated_files": generated_files,
        "recommended_next_analyses": spec["recommended_next_analyses"],
        "guidance": guidance,
    }
    row["compatible_analyses"] = _compatible_analyses(row)
    return row


def safe_variant_dir_name(variant_id: str) -> str:
    """Return a filesystem-safe directory name for a model variant."""

    text = str(variant_id or "active_variant").strip()
    cleaned = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in text)
    cleaned = cleaned.strip("._-")
    return cleaned or "active_variant"


def _copy_parameter_defaults() -> dict[str, dict[str, object]]:
    return _copy_nested_defaults(ANALYSIS_PARAMETER_DEFAULTS)


def _copy_nested_defaults(defaults: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    copied: dict[str, dict[str, object]] = {}
    for module_id, values in defaults.items():
        copied[module_id] = {
            key: list(value) if isinstance(value, list) else value
            for key, value in values.items()
        }
    return copied


def _as_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y", "on"}:
        return True
    if text in {"false", "0", "no", "n", "off"}:
        return False
    return default


def _bounded_float(value: object, *, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _bounded_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _optional_bounded_float(value: object, *, minimum: float, maximum: float) -> float | str:
    if value in {"", None}:
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return max(minimum, min(maximum, number))


def _fraction_list(value: object, *, default: list[float]) -> list[float]:
    if isinstance(value, str):
        raw_items = value.replace(";", ",").split(",")
    elif isinstance(value, Iterable):
        raw_items = list(value)
    else:
        raw_items = default
    fractions: list[float] = []
    seen: set[float] = set()
    for item in raw_items:
        try:
            fraction = round(float(item), 6)
        except (TypeError, ValueError):
            continue
        fraction = max(0.0, min(1.0, fraction))
        if fraction not in seen:
            fractions.append(fraction)
            seen.add(fraction)
    return fractions or list(default)


def _parameter_value_text(value: object) -> str:
    if isinstance(value, list):
        return ";".join(str(item) for item in value)
    return str(value)


def _one_of(value: object, allowed: set[str], default: str) -> str:
    text = str(value or "").strip()
    return text if text in allowed else default


def _schema_group(defaults: dict[str, dict[str, object]], category: str) -> dict[str, object]:
    return {
        module_id: {
            "category": category,
            "parameters": [
                {
                    "name": key,
                    "default": value,
                    "value_type": type(value).__name__,
                    "advanced": key not in {"run_pfba", "run_fva", "fva_fraction_of_optimum", "min_expression_fraction", "flux_threshold", "biomass_fractions", "fseof_fractions"},
                    "requires_external_dependency": module_id in {"enzyme_gecko", "pytfa_export", "pytfa_external", "memote_external", "dlkcat_external"},
                    "description": _parameter_description(module_id, key),
                }
                for key, value in values.items()
            ],
        }
        for module_id, values in defaults.items()
    }


def _parameter_description(module_id: str, key: str) -> str:
    descriptions = {
        "min_expression_fraction": "Lower E-Flux capacity floor for low-expression reactions.",
        "flux_threshold": "FASTcore flux feasibility tolerance.",
        "core_evidence_threshold": "Evidence label converted into FASTcore core reactions.",
        "fva_fraction_of_optimum": "COBRApy FVA fraction_of_optimum.",
        "biomass_fractions": "Growth fractions used for production envelope.",
        "fseof_fractions": "Enforced product flux fractions used by FSEOF-lite.",
        "enable_uniprot_rest": "Allow optional UniProt REST enrichment.",
        "run_dlkcat_external": "Run external DLKcat predictor when local dependencies are configured.",
    }
    return descriptions.get(key, f"{module_id}.{key}")


def _changed_rows(
    normalized: dict[str, dict[str, object]],
    defaults: dict[str, dict[str, object]],
    id_column: str,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    default_normalized = _copy_nested_defaults(defaults)
    for module_id, values in normalized.items():
        for key, value in values.items():
            default_value = default_normalized.get(module_id, {}).get(key, "")
            if _parameter_value_text(value) != _parameter_value_text(default_value):
                rows.append(
                    {
                        id_column: module_id,
                        "parameter": key,
                        "default": _parameter_value_text(default_value),
                        "value": _parameter_value_text(value),
                    }
                )
    return rows


def _parameter_warnings(
    generation: dict[str, dict[str, object]],
    analysis: dict[str, dict[str, object]],
    selected_methods: list[str],
    selected_modules: list[str],
) -> list[dict[str, object]]:
    warnings: list[dict[str, object]] = []
    if "enzyme_gecko" in selected_methods and generation["enzyme_gecko"].get("run_gecko_external"):
        warnings.append({"scope": "enzyme_gecko", "severity": "external_dependency", "message": "GECKO external run needs MATLAB, GECKO, RAVEN, and solver configuration."})
    if "troppo_methods" in selected_methods and generation["troppo_methods"].get("execution_mode") == "optional_runner":
        warnings.append({"scope": "troppo_methods", "severity": "optional_runner", "message": "iMAT/GIMME/CORDA execution is optional and only enabled when local TROPPO backend support is detected."})
    if "fba_pfba" in selected_modules and analysis["fba_pfba"].get("run_fva") and analysis["fba_pfba"].get("fva_reaction_scope") == "all_reactions":
        warnings.append({"scope": "fba_pfba", "severity": "runtime_cost", "message": "All-reaction FVA can be slow on large GEMs."})
    if analysis.get("pytfa_external", {}).get("run_pytfa_external"):
        warnings.append({"scope": "pytfa_external", "severity": "external_dependency", "message": "pyTFA execution requires pyTFA and a configured thermodynamic database."})
    return warnings


def _normalize_selection(
    selected: Iterable[str] | str | None,
    available: dict[str, dict[str, str]],
    default: Iterable[str],
) -> list[str]:
    if selected is None:
        return list(default)
    if isinstance(selected, str):
        raw_items = [part.strip() for part in selected.replace(";", ",").split(",")]
    else:
        raw_items = [str(item).strip() for item in selected]
    seen: set[str] = set()
    normalized: list[str] = []
    for item in raw_items:
        if item in available and item not in seen:
            normalized.append(item)
            seen.add(item)
    return normalized


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return read_csv_records(path)


def _context_model_sbml_from_manifest(path: Path) -> str:
    if not path.exists() or path.suffix.lower() != ".json":
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    sbml_path = str(data.get("context_model_sbml", ""))
    return sbml_path if sbml_path and Path(sbml_path).exists() else ""


def _primary_model_path(
    *,
    method_id: str,
    source_model_path: Path,
    primary_artifact: Path,
    context_model_sbml: str,
) -> str:
    if context_model_sbml:
        return context_model_sbml
    return str(source_model_path)


def _generated_files(
    *,
    primary_artifact: Path,
    context_model_sbml: str,
    supporting_files: list[str],
) -> str:
    files: list[str] = []
    if primary_artifact.exists():
        files.append(str(primary_artifact))
    if context_model_sbml:
        files.append(context_model_sbml)
    for path in supporting_files:
        if path not in files:
            files.append(path)
    return ";".join(files)


def _compatible_analyses(variant_row: dict[str, object]) -> str:
    compatible: list[str] = []
    typed_row = {str(key): str(value) for key, value in variant_row.items()}
    for module_id in ANALYSIS_MODULES:
        if _is_analysis_compatible(module_id, typed_row):
            compatible.append(module_id)
    return ";".join(compatible)


def _analysis_active_model_path(active_variant: dict[str, str]) -> str:
    context_model = str(active_variant.get("context_model_sbml", "")).strip()
    if context_model:
        return context_model
    primary_model = str(active_variant.get("primary_model_path", "")).strip()
    if primary_model:
        return primary_model
    return str(active_variant.get("source_model_path", "")).strip()


def _analysis_active_model_source(active_variant: dict[str, str]) -> str:
    if str(active_variant.get("context_model_sbml", "")).strip():
        return "context_model_sbml"
    method = str(active_variant.get("generation_method", "")).strip()
    if method == "enzyme_gecko":
        return "gecko_ready_artifact"
    if method:
        return "uploaded_baseline_gem"
    return ""


def _is_analysis_compatible(module_id: str, active_variant: dict[str, str]) -> bool:
    active_method = active_variant.get("generation_method", "")
    if not active_method:
        return False
    allowed_methods = MODEL_BACKED_ANALYSIS_METHODS.get(module_id, set(MODEL_GENERATION_METHODS))
    if active_method not in allowed_methods:
        return False
    if active_method in {"fastcore", "consensus_evidence"} and module_id in {"fba_pfba", "production_ecfactory", "readiness_gate"}:
        return bool(active_variant.get("context_model_sbml"))
    return True


def _conditions_from_rows(rows: list[dict[str, str]]) -> list[str]:
    conditions: list[str] = []
    for row in rows:
        condition = str(row.get("condition", "")).strip()
        if condition and condition not in conditions:
            conditions.append(condition)
    return conditions


def _rows_for_condition(rows: list[dict[str, str]], condition: str) -> list[dict[str, str]]:
    if not rows:
        return []
    if condition == "ALL":
        return [dict(row) for row in rows]
    return [dict(row) for row in rows if str(row.get("condition", "")).strip() in {"", condition}]


def _standardize_reaction_rows(
    rows: list[dict[str, str]],
    condition: str,
    artifact_role: str,
    source_method: str,
    source_file: Path,
) -> list[dict[str, object]]:
    standardized: list[dict[str, object]] = []
    for row in rows:
        reaction_id = str(row.get("reaction_id") or row.get("model_reaction_id") or row.get("cobra_reaction_id") or "").strip()
        cobra_reaction_id = str(row.get("cobra_reaction_id") or row.get("reaction_id") or "").strip()
        if not reaction_id and not cobra_reaction_id:
            continue
        if not reaction_id:
            reaction_id = f"R_{cobra_reaction_id}" if not cobra_reaction_id.startswith("R_") else cobra_reaction_id
        if not cobra_reaction_id:
            cobra_reaction_id = reaction_id[2:] if reaction_id.startswith("R_") else reaction_id
        standardized.append(
            {
                "condition": str(row.get("condition") or condition),
                "reaction_id": reaction_id,
                "cobra_reaction_id": cobra_reaction_id,
                "artifact_role": artifact_role,
                "source_method": source_method,
                "source_role": row.get("role", ""),
                "source_status": row.get("status", ""),
                "decision": row.get("decision", artifact_role),
                "reason": row.get("reason", row.get("core_source", "")),
                "evidence": row.get("evidence", ""),
                "reaction_score": row.get("reaction_score", ""),
                "source_file": str(source_file),
            }
        )
    return _dedupe_reaction_rows(standardized, condition)


def _dedupe_reaction_rows(rows: list[dict[str, object]], condition: str) -> list[dict[str, object]]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[dict[str, object]] = []
    for row in rows:
        key = (
            str(row.get("condition") or condition),
            str(row.get("reaction_id", "")),
            str(row.get("artifact_role", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _export_pruned_context_sbml(
    *,
    source_model_path: Path,
    output_path: Path,
    delete_rows: list[dict[str, object]],
) -> dict[str, object]:
    """Try to export a COBRApy-pruned context SBML from delete reaction rows."""

    delete_ids = _delete_reaction_ids(delete_rows)
    if not delete_ids:
        return _sbml_export_result("skipped_no_delete_reactions", "", "No delete reactions were provided.", 0, 0)
    if not source_model_path.exists():
        return _sbml_export_result("skipped_missing_model", "", "Source SBML model does not exist.", 0, len(delete_ids))
    try:
        from .cobra_runner import cobrapy_available

        if not cobrapy_available():
            return _sbml_export_result("skipped_cobrapy_missing", "", "COBRApy is not available.", 0, len(delete_ids))
        from cobra.io import read_sbml_model, write_sbml_model

        model = read_sbml_model(str(source_model_path))
        initial_reaction_count = len(model.reactions)
        reactions_to_remove = []
        missing_ids = []
        for reaction_id in delete_ids:
            reaction = _get_cobra_model_reaction(model, reaction_id)
            if reaction is None:
                missing_ids.append(reaction_id)
            else:
                reactions_to_remove.append(reaction)
        if not reactions_to_remove:
            return _sbml_export_result(
                "skipped_no_matching_delete_reactions",
                "",
                "Delete reactions did not match COBRApy reaction IDs.",
                0,
                len(missing_ids),
                initial_reaction_count=initial_reaction_count,
                final_reaction_count=initial_reaction_count,
            )
        model.remove_reactions(reactions_to_remove, remove_orphans=True)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        write_sbml_model(model, str(output_path))
        return _sbml_export_result(
            "exported",
            str(output_path),
            f"Exported pruned context SBML after removing {len(reactions_to_remove)} reactions.",
            len(reactions_to_remove),
            len(missing_ids),
            initial_reaction_count=initial_reaction_count,
            final_reaction_count=len(model.reactions),
        )
    except Exception as exc:
        return _sbml_export_result(
            "skipped_export_error",
            "",
            f"{type(exc).__name__}: {exc}",
            0,
            len(delete_ids),
        )


def _delete_reaction_ids(delete_rows: list[dict[str, object]]) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for row in delete_rows:
        for key in ("cobra_reaction_id", "reaction_id"):
            reaction_id = str(row.get(key, "")).strip()
            if not reaction_id:
                continue
            normalized = reaction_id[2:] if reaction_id.startswith("R_") else reaction_id
            if normalized not in seen:
                ids.append(normalized)
                seen.add(normalized)
            break
    return ids


def _get_cobra_model_reaction(model, reaction_id: str):
    candidates = [reaction_id]
    if reaction_id.startswith("R_"):
        candidates.append(reaction_id[2:])
    else:
        candidates.append(f"R_{reaction_id}")
    for candidate in candidates:
        try:
            return model.reactions.get_by_id(candidate)
        except KeyError:
            continue
    return None


def _sbml_export_result(
    status: str,
    context_model_sbml: str,
    message: str,
    removed_reaction_count: int,
    missing_delete_reaction_count: int,
    *,
    initial_reaction_count: int | str = "",
    final_reaction_count: int | str = "",
) -> dict[str, object]:
    return {
        "status": status,
        "context_model_sbml": context_model_sbml,
        "message": message,
        "removed_reaction_count": removed_reaction_count,
        "missing_delete_reaction_count": missing_delete_reaction_count,
        "initial_reaction_count": initial_reaction_count,
        "final_reaction_count": final_reaction_count,
    }


def _artifact_manifest_path(artifact_root: Path, variant_id: str) -> Path:
    return artifact_root / variant_id / "context_model_artifact_manifest.json"


def _analysis_execution_scope(module_id: str, generation_method: str, compatible: bool) -> str:
    if not compatible:
        return "not_executable_for_active_variant"
    if module_id in {"ml_pca_lasso", "condition_interpretation", "minn_export", "hybrid_minn", "hybrid_graph_adapter"}:
        return "uses_package_omics_and_active_variant_context"
    if generation_method == "baseline_gem":
        return "uses_uploaded_baseline_gem"
    if generation_method == "eflux":
        return "uses_transcriptomics_constraint_outputs"
    if generation_method == "consensus_evidence":
        return "uses_context_model_sbml"
    if generation_method == "fastcore":
        return "uses_context_model_sbml"
    if generation_method == "enzyme_gecko":
        return "uses_enzyme_gecko_outputs"
    return "uses_active_variant_outputs"


def _analysis_variant_guidance(module_id: str, active_variant: dict[str, str], compatible: bool) -> str:
    if not active_variant:
        return "No active model variant is available; run model generation first."
    if compatible:
        if active_variant.get("context_model_sbml"):
            return f"{ANALYSIS_MODULES[module_id]['label']} will use context SBML {active_variant.get('context_model_sbml', '')}."
        return f"{ANALYSIS_MODULES[module_id]['label']} will be interpreted against {active_variant.get('variant_id', '')}."
    method_label = active_variant.get("generation_method_label") or active_variant.get("generation_method", "")
    if active_variant.get("generation_method") in {"fastcore", "consensus_evidence"} and module_id in {"fba_pfba", "production_ecfactory", "readiness_gate"}:
        return (
            f"{ANALYSIS_MODULES[module_id]['label']} needs a context_model_sbml for active variant "
            f"{active_variant.get('variant_id', '')}, but no exportable SBML was generated."
        )
    return (
        f"{ANALYSIS_MODULES[module_id]['label']} is not executable for active variant "
        f"{active_variant.get('variant_id', '')} ({method_label}) in this v1 dispatcher."
    )


def _conditions_from_csv(path: Path, fallback: Iterable[str] | None = None) -> list[str]:
    rows = read_csv_records(path) if path.exists() and path.stat().st_size > 0 else []
    conditions: list[str] = []
    for row in rows:
        condition = str(row.get("condition") or row.get("source_condition") or row.get("target_condition") or "").strip()
        if condition and condition not in conditions:
            conditions.append(condition)
    if conditions:
        return conditions
    if fallback is not None:
        fallback_conditions = [str(item) for item in fallback if str(item)]
        if fallback_conditions:
            return fallback_conditions
    return ["ALL"]


def _first_existing(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.exists() and path.stat().st_size > 0:
            return path
    return None


def _slug(value: str) -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(value).strip())
    slug = "_".join(part for part in slug.split("_") if part)
    return slug or "all"
