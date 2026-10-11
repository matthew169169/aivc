"""Prepare the Shewanella GECKO case study as an Omics-GEM run package."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .constraints import write_csv, write_json
from .upload_workflow import UploadFilePayload, stage_user_run_package


DEFAULT_SOURCE_DIR = Path(r"D:\MatExt\GECKO\ecShewanella")
DEFAULT_RUN_ID = "shewanella_gecko_case"
CASE_SCHEMA_VERSION = "0.1.0"
PTOT_G_PER_GDCW = 0.48


@dataclass(slots=True)
class ShewanellaCaseStudyResult:
    """Summary returned after preparing the Shewanella case package."""

    status: str
    run_id: str
    output_dir: str
    message: str
    files: dict[str, str]
    row_counts: dict[str, int]


def prepare_shewanella_case_study(
    source_dir: str | Path = DEFAULT_SOURCE_DIR,
    output_root: str | Path = r"D:\generate\user_runs",
    run_id: str = DEFAULT_RUN_ID,
    overwrite: bool = False,
) -> ShewanellaCaseStudyResult:
    """Convert the local ecShewanella project into a staged Omics-GEM run package."""

    source = Path(source_dir).resolve()
    output_base = Path(output_root).resolve()
    run_id = _safe_run_id(run_id)
    target = (output_base / run_id).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Shewanella source directory was not found: {source}")
    _validate_source_files(source)
    if target.exists():
        if not overwrite:
            raise FileExistsError(f"Target run package already exists: {target}")
        _assert_safe_target(target, output_base)
        shutil.rmtree(target)

    paths = _source_paths(source)
    adapter_parameters = parse_shewanella_adapter(paths["adapter"])
    model_bytes = paths["model"].read_bytes()
    model_reactions = read_sbml_reactions(paths["model"])

    proteomics_tables = build_taylor_omics_tables(paths["taylor"], adapter_parameters)
    kcat_rows = build_gotenzymes_kcat_priors(paths["gotenzymes"])
    alias_rows, annotation_rows = build_annotation_tables(paths["taylor"])
    dlkcat_rows = build_dlkcat_annotation(paths["uniprot"])
    condition_rows, condition_summary = build_condition_exchange_bounds(paths["conditions"], model_reactions)
    target_rows, target_discovery, target_readiness = build_shewanella_targets(model_reactions)
    source_manifest = build_source_manifest(source, paths, adapter_parameters)
    validation_rows = build_validation_baseline_rows(source)
    ml_summary_rows = build_initial_ml_summary(proteomics_tables)

    omics_payloads = [
        _csv_payload("transcriptomics_shewanella.csv", "omics_table", "transcriptomics", proteomics_tables["transcriptomics"]),
        _csv_payload(
            "absolute_proteomics_shewanella.csv",
            "omics_table",
            "absolute_proteomics",
            proteomics_tables["absolute_proteomics"],
        ),
        _csv_payload(
            "relative_proteomics_shewanella.csv",
            "omics_table",
            "relative_proteomics",
            proteomics_tables["relative_proteomics"],
        ),
        _csv_payload("gotenzymes2_kcat_priors.csv", "omics_table", "ml_priors", kcat_rows),
        _csv_payload("shewanella_gene_aliases.csv", "omics_table", "id_alias_table", alias_rows),
        _csv_payload("shewanella_functional_annotation.csv", "omics_table", "uniprot_annotation", annotation_rows),
        _csv_payload("shewanella_dlkcat_annotation.csv", "omics_table", "dlkcat_annotation", dlkcat_rows),
        _csv_payload("production_targets_shewanella.csv", "omics_table", "production_targets", target_rows),
    ]
    condition_payloads = [
        _csv_payload(
            "condition_exchange_bounds_shewanella.csv",
            "condition_table",
            "condition_exchange_bounds",
            condition_rows,
        ),
        _csv_payload("shewanella_condition_summary.csv", "condition_table", "condition_summary", condition_summary),
    ]
    run_config = {
        "project_name": "Shewanella GECKO Case Study",
        "organism": "Shewanella oneidensis MR-1",
        "schema_version": CASE_SCHEMA_VERSION,
        "source_dir": str(source),
        "case_study": {
            "case_id": run_id,
            "source_manifest": "source_manifest.json",
            "plan_file": str(Path(r"D:\generate\paper\Shewanella_GECKO_case_study_plan.md")),
        },
        "default_workflow": {
            "model_generation_methods": ["baseline_gem", "eflux", "enzyme_gecko", "consensus_evidence"],
            "analysis_modules": [
                "fba_pfba",
                "eflux_delta_fba",
                "evidence_comparison",
                "ml_pca_lasso",
                "condition_interpretation",
                "production_ecfactory",
                "readiness_gate",
            ],
            "selected_model_variant_ids": ["baseline_gem__all"],
            "report_preset": "full_audit_report",
            "gecko_ec_model_mode": "full_ecModel",
            "gecko_adapter_parameters": adapter_parameters,
            "analysis_parameters": {
                "fba_pfba": {"run_pfba": True, "run_fva": False},
                "ml_pca_lasso": {"min_overlap": 1, "max_clusters": 4, "max_lasso_features": 50},
                "production_ecfactory": {
                    "biomass_fractions": [0.0, 0.25, 0.5, 0.75, 0.9],
                    "fseof_fractions": [0.0, 0.25, 0.5, 0.75, 0.9],
                },
            },
        },
        "notes": [
            "Original ecShewanella folder is treated as read-only.",
            "GECKO external MATLAB execution is disabled until adapter probe and user confirmation.",
            "PCA/LASSO/clustering are exploratory and not causal evidence.",
        ],
    }
    package = stage_user_run_package(
        output_root=output_base,
        run_config=run_config,
        model_file=UploadFilePayload(
            filename="iLJ1162.xml",
            data=model_bytes,
            kind="model",
            role="gem",
            columns=[],
            status="ok",
            details=["Shewanella iLJ1162 conventional GEM copied from read-only source."],
        ),
        omics_files=omics_payloads,
        condition_files=condition_payloads,
        run_id=run_id,
    )
    package_dir = Path(package.output_dir)
    case_dir = package_dir / "case_study"
    case_dir.mkdir(parents=True, exist_ok=True)
    files = {
        "source_manifest": str(package_dir / "source_manifest.json"),
        "gecko_adapter_config": str(case_dir / "gecko_adapter_config.json"),
        "shewanella_source_summary": str(case_dir / "shewanella_source_summary.csv"),
        "shewanella_condition_summary": str(case_dir / "shewanella_condition_summary.csv"),
        "shewanella_kcat_mapping_summary": str(case_dir / "shewanella_kcat_mapping_summary.csv"),
        "shewanella_target_discovery": str(case_dir / "shewanella_target_discovery.csv"),
        "production_target_readiness": str(case_dir / "production_target_readiness.csv"),
        "shewanella_ml_summary": str(case_dir / "shewanella_ml_summary.csv"),
        "old_vs_new_validation_summary": str(case_dir / "old_vs_new_validation_summary.csv"),
        "case_readme": str(case_dir / "README.md"),
        "case_manifest": str(case_dir / "shewanella_case_manifest.json"),
        **package.files,
    }
    source_summary = build_source_summary_rows(paths, source_manifest)
    kcat_summary = build_kcat_summary_rows(kcat_rows, model_reactions)
    write_json(files["source_manifest"], source_manifest)
    write_json(files["gecko_adapter_config"], adapter_parameters)
    write_csv(files["shewanella_source_summary"], source_summary)
    write_csv(files["shewanella_condition_summary"], condition_summary)
    write_csv(files["shewanella_kcat_mapping_summary"], kcat_summary)
    write_csv(files["shewanella_target_discovery"], target_discovery)
    write_csv(files["production_target_readiness"], target_readiness)
    write_csv(files["shewanella_ml_summary"], ml_summary_rows)
    write_csv(files["old_vs_new_validation_summary"], validation_rows)
    Path(files["case_readme"]).write_text(
        render_case_readme(run_id=run_id, source=source),
        encoding="utf-8",
    )
    row_counts = {
        "transcriptomics": len(proteomics_tables["transcriptomics"]),
        "absolute_proteomics": len(proteomics_tables["absolute_proteomics"]),
        "relative_proteomics": len(proteomics_tables["relative_proteomics"]),
        "kcat_priors": len(kcat_rows),
        "aliases": len(alias_rows),
        "annotations": len(annotation_rows),
        "dlkcat_annotation": len(dlkcat_rows),
        "condition_exchange_bounds": len(condition_rows),
        "production_targets": len(target_rows),
        "target_discovery": len(target_discovery),
    }
    case_manifest = {
        "schema_version": CASE_SCHEMA_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "ready_for_workflow",
        "run_id": run_id,
        "source_dir": str(source),
        "output_dir": str(package_dir),
        "files": files,
        "row_counts": row_counts,
        "default_workflow": run_config["default_workflow"],
    }
    write_json(files["case_manifest"], case_manifest)
    _augment_upload_manifest(package_dir, files, row_counts)
    return ShewanellaCaseStudyResult(
        status="ready_for_workflow",
        run_id=run_id,
        output_dir=str(package_dir),
        message=f"Prepared Shewanella GECKO case package at {package_dir}",
        files=files,
        row_counts=row_counts,
    )


def parse_shewanella_adapter(adapter_path: str | Path) -> dict[str, Any]:
    """Extract GECKO ModelAdapter values from the existing MATLAB adapter."""

    text = Path(adapter_path).read_text(encoding="utf-8", errors="ignore")
    params = {
        "adapter_class_name": "ShewanellaGeckoAdapter",
        "model_id": "iLJ1162_shewanella",
        "conv_gem_path": "inputs/model/model__iLJ1162.xml",
        "organism_name": _matlab_string(text, "org_name") or "shewanella oneidensis",
        "kegg_id": _matlab_string(text, "kegg.ID") or "son",
        "kegg_gene_id": _matlab_string(text, "kegg.geneID") or "kegg",
        "uniprot_type": _matlab_string(text, "uniprot.type") or "proteome",
        "uniprot_id": _matlab_string(text, "uniprot.ID") or "UP000008186",
        "uniprot_gene_id_field": _matlab_string(text, "uniprot.geneIDfield") or "gene_oln",
        "uniprot_reviewed": _matlab_bool(text, "uniprot.reviewed", default=False),
        "complex_taxonomic_id": _matlab_number(text, "complex.taxonomicID") or 211586,
        "bio_rxn": _matlab_string(text, "bioRxn") or "bio1",
        "c_source": _matlab_string(text, "c_source") or "EX_cpd00159_e0",
        "enzyme_comp": _matlab_string(text, "enzyme_comp") or "c0",
        "sigma": _matlab_number(text, "sigma") or 0.5,
        "Ptot": _matlab_number(text, "Ptot") or PTOT_G_PER_GDCW,
        "f": _matlab_number(text, "f") or 0.5,
        "gR_exp": _matlab_number(text, "gR_exp") or 0.15,
        "spontaneous_reaction_strategy": "rxn_name_contains_spontaneous",
        "ec_model_mode": "full_ecModel",
        "proteomics_integration": True,
    }
    return params


def build_taylor_omics_tables(taylor_csv: str | Path, adapter_parameters: dict[str, Any]) -> dict[str, list[dict[str, object]]]:
    """Build transcriptomics, absolute proteomics, and relative proteomics tables."""

    rows = _read_csv_rows(taylor_csv)
    ptot = _to_float(adapter_parameters.get("Ptot")) or PTOT_G_PER_GDCW
    absolute: list[dict[str, object]] = []
    relative: list[dict[str, object]] = []
    transcriptomics: list[dict[str, object]] = []

    protein_specs = [
        ("highO2_sample1", "Fraction total protein", "highO2"),
        ("lowO2_sample4", "Fraction total protein__2", "lowO2"),
        ("highO2_average", "High O2 Prot Average", "highO2"),
        ("lowO2_average", "Low O2 Prot Average", "lowO2"),
    ]
    mrna_specs = [
        ("highO2_sample1", "Sample 1 mRNA (RPKM)", "highO2"),
        ("highO2_sample2", "Sample 2 mRNA (RPKM)", "highO2"),
        ("highO2_sample3", "Sample 3 mRNA (RPKM)", "highO2"),
        ("lowO2_sample4", "Sample 4 mRNA (RPKM)", "lowO2"),
        ("lowO2_sample5", "Sample 5 mRNA (RPKM)", "lowO2"),
        ("lowO2_sample6", "Sample 6 mRNA (RPKM)", "lowO2"),
    ]
    for row in rows:
        gene = _first_nonempty(row.get("Locus Tag 1"), row.get("Locus Tag 2"))
        if not gene:
            continue
        protein_id = gene
        mw = _to_float(row.get("Protein MW"))
        product = row.get("Product Descriptor", "")
        for sample, column, condition in protein_specs:
            raw_fraction = _to_float(row.get(column))
            if raw_fraction is None or raw_fraction <= 0:
                continue
            abundance_mmol = _fraction_to_mmol_per_gdw(raw_fraction, mw, ptot)
            if abundance_mmol is None:
                continue
            absolute.append(
                {
                    "protein_id": protein_id,
                    "sample": sample,
                    "value": abundance_mmol,
                    "unit": "mmol_per_gDW",
                    "condition": condition,
                    "gene_id": gene,
                    "mass_abundance_mg_gDCW": raw_fraction * ptot * 1000.0,
                    "raw_fraction_total_protein": raw_fraction,
                    "protein_mw_da": mw,
                    "note": f"Taylor proteomics {column}; {product}".strip("; "),
                }
            )
        high_avg = _to_float(row.get("High O2 Prot Average"))
        low_avg = _to_float(row.get("Low O2 Prot Average"))
        if high_avg is not None and high_avg > 0 and low_avg is not None and low_avg > 0:
            relative.append(
                {
                    "protein_id": protein_id,
                    "sample": "lowO2_vs_highO2",
                    "value": math.log2(low_avg / high_avg),
                    "unit": "log2_fold_change",
                    "condition": "lowO2",
                    "reference_condition": "highO2",
                    "gene_id": gene,
                    "lowO2_value": low_avg,
                    "highO2_value": high_avg,
                    "note": f"Taylor Low O2 Prot Average / High O2 Prot Average; {product}".strip("; "),
                }
            )
        for sample, column, condition in mrna_specs:
            value = _to_float(row.get(column))
            if value is None:
                continue
            transcriptomics.append(
                {
                    "gene_id": gene,
                    "sample": sample,
                    "value": value,
                    "unit": "RPKM",
                    "condition": condition,
                    "note": f"Taylor mRNA column {column}; {product}".strip("; "),
                }
            )
    return {
        "absolute_proteomics": absolute,
        "relative_proteomics": relative,
        "transcriptomics": transcriptomics,
    }


def build_gotenzymes_kcat_priors(gotenzymes_csv: str | Path) -> list[dict[str, object]]:
    """Convert GotEnzymes2 rows into Omics-GEM kcat prior rows."""

    priors: list[dict[str, object]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in _read_csv_rows(gotenzymes_csv):
        reaction_id = str(row.get("reaction_id") or "").strip()
        kcat = _to_float(row.get("kcat_values"))
        if not reaction_id or kcat is None or kcat <= 0:
            continue
        gene = str(row.get("gene") or "").strip()
        compound = str(row.get("compound") or "").strip()
        key = (reaction_id, gene, compound)
        if key in seen:
            continue
        seen.add(key)
        priors.append(
            {
                "target_id": reaction_id,
                "target_type": "reaction",
                "value": kcat,
                "confidence": 0.55,
                "unit": "per_s",
                "source_tier": "gotenzymes2_predicted",
                "gene_id": gene,
                "organism": row.get("organism", ""),
                "ec_number": row.get("ec_number", ""),
                "compound": compound,
                "temperature_optimum": row.get("topt", ""),
                "melting_temperature": row.get("tm", ""),
                "note": "GotEnzymes2 predicted kcat; KEGG reaction id may need GEM mapping review.",
            }
        )
    return priors


def build_annotation_tables(taylor_csv: str | Path) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Build alias and functional annotation rows from the Taylor table."""

    aliases: list[dict[str, object]] = []
    annotations: list[dict[str, object]] = []
    seen_aliases: set[tuple[str, str]] = set()
    for row in _read_csv_rows(taylor_csv):
        gene = _first_nonempty(row.get("Locus Tag 1"), row.get("Locus Tag 2"))
        if not gene:
            continue
        for source in [row.get("Locus Tag 1"), row.get("Locus Tag 2")]:
            source_id = str(source or "").strip()
            if source_id and (source_id, gene) not in seen_aliases:
                seen_aliases.add((source_id, gene))
                aliases.append(
                    {
                        "source_id": source_id,
                        "model_id": gene,
                        "source_namespace": "Taylor2013_locus_tag",
                        "target_namespace": "model_gene",
                        "note": "Alias from Taylor proteomics table.",
                    }
                )
        annotations.append(
            {
                "gene_id": gene,
                "model_gene_id": gene,
                "locus_tag_1": row.get("Locus Tag 1", ""),
                "locus_tag_2": row.get("Locus Tag 2", ""),
                "product_descriptor": row.get("Product Descriptor", ""),
                "fig_function": row.get("FIG Function", ""),
                "fig_subsystem": row.get("FIG Subsystem", ""),
                "general_function": row.get("General Function", ""),
                "regulon": row.get("regulon", ""),
                "cofactor": row.get("cofactor", ""),
                "localization": row.get("Localization", ""),
                "source": "Taylor_2013_Proteomics.csv",
            }
        )
    return aliases, annotations


def build_dlkcat_annotation(uniprot_tsv: str | Path) -> list[dict[str, object]]:
    """Build a DLKcat-compatible protein annotation table from UniProt TSV."""

    rows: list[dict[str, object]] = []
    if not Path(uniprot_tsv).exists():
        return rows
    with Path(uniprot_tsv).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            gene = str(row.get("Gene Names (ordered locus)") or "").strip()
            sequence = str(row.get("Sequence") or "").strip()
            if not gene or not sequence:
                continue
            rows.append(
                {
                    "gene_id": gene,
                    "model_gene_id": gene,
                    "protein_id": row.get("Entry", ""),
                    "uniprot_id": row.get("Entry", ""),
                    "ec_number": row.get("EC number", ""),
                    "protein_sequence": sequence,
                    "sequence": sequence,
                    "substrate_name": "",
                    "substrate_smiles": "",
                    "source": "uniprot.tsv",
                }
            )
    return rows


def build_condition_exchange_bounds(
    conditions_csv: str | Path,
    model_reactions: dict[str, str],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Build condition-specific exchange/growth bounds from Taylor condition rows."""

    rows: list[dict[str, object]] = []
    summary: list[dict[str, object]] = []
    for condition in _read_csv_rows(conditions_csv):
        condition_id = condition.get("condition", "")
        added = 0
        for spec in [
            ("lactate", "lactate_rxn", "lactate_lb", "lactate_ub", "lactate_uptake_mmol_gDW_h", "lactate_tolerance_fraction", "uptake"),
            ("oxygen", "o2_rxn", "o2_lb", "o2_ub", "o2_uptake_mmol_gDW_h", "o2_tolerance_fraction", "uptake"),
            (
                "acetate",
                "acetate_rxn",
                "",
                "",
                "acetate_secretion_mmol_gDW_h",
                "acetate_tolerance_fraction",
                "secretion",
            ),
            (
                "pyruvate",
                "pyruvate_rxn",
                "",
                "",
                "pyruvate_secretion_mmol_gDW_h",
                "pyruvate_tolerance_fraction",
                "secretion",
            ),
            (
                "formate",
                "formate_rxn",
                "",
                "",
                "formate_secretion_mmol_gDW_h",
                "formate_tolerance_fraction",
                "secretion",
            ),
        ]:
            label, rxn_key, lb_key, ub_key, value_key, tolerance_key, direction = spec
            reaction_id = str(condition.get(rxn_key) or "").strip()
            if not reaction_id:
                continue
            lower = _to_float(condition.get(lb_key)) if lb_key else None
            upper = _to_float(condition.get(ub_key)) if ub_key else None
            value = _to_float(condition.get(value_key))
            tolerance = _to_float(condition.get(tolerance_key)) or 0.2
            if value is not None and lower is None and upper is None:
                lower, upper = _measurement_bounds(value, tolerance, direction)
            model_reaction, status = resolve_reaction_from_index(reaction_id, model_reactions)
            rows.append(
                {
                    "condition": condition_id,
                    "reaction_id": reaction_id,
                    "model_reaction_id": model_reaction,
                    "lower_bound": lower if lower is not None else "",
                    "upper_bound": upper if upper is not None else "",
                    "source": condition.get("source_label", ""),
                    "confidence": "medium" if value is None else "high",
                    "status": status,
                    "note": f"{label} {direction}; {condition.get('notes', '')}".strip("; "),
                }
            )
            added += 1
        growth = _to_float(condition.get("growth_rate_h"))
        tolerance = _to_float(condition.get("growth_tolerance_fraction")) or 0.05
        if growth is not None:
            lower = growth * (1 - tolerance)
            upper = growth * (1 + tolerance)
            rows.append(
                {
                    "condition": condition_id,
                    "reaction_id": "bio1",
                    "model_reaction_id": resolve_reaction_from_index("bio1", model_reactions)[0],
                    "lower_bound": lower,
                    "upper_bound": upper,
                    "source": condition.get("source_label", ""),
                    "confidence": "medium",
                    "status": resolve_reaction_from_index("bio1", model_reactions)[1],
                    "note": "Taylor dilution/growth target from condition table.",
                }
            )
            added += 1
        prot_pool_lb = _to_float(condition.get("prot_pool_lb"))
        if prot_pool_lb is not None:
            model_reaction, status = resolve_reaction_from_index("prot_pool_exchange", model_reactions)
            rows.append(
                {
                    "condition": condition_id,
                    "reaction_id": "prot_pool_exchange",
                    "model_reaction_id": model_reaction,
                    "lower_bound": prot_pool_lb,
                    "upper_bound": "",
                    "source": condition.get("source_label", ""),
                    "confidence": "low",
                    "status": status,
                    "note": "Protein pool bound from legacy GECKO condition table.",
                }
            )
            added += 1
        summary.append(
            {
                "condition": condition_id,
                "source_label": condition.get("source_label", ""),
                "oxygen_percent": condition.get("oxygen_percent", ""),
                "growth_rate_h": condition.get("growth_rate_h", ""),
                "exchange_bound_count": added,
                "model_file": condition.get("model_file", ""),
                "model_variable": condition.get("model_variable", ""),
                "note": condition.get("notes", ""),
            }
        )
    return rows, summary


def build_shewanella_targets(model_reactions: dict[str, str]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    """Discover validation and high-value production targets in the GEM."""

    targets = [
        {
            "target_name": "acetate",
            "tier": "A",
            "category": "validation_target",
            "priority": "high",
            "synonyms": ["acetate", "cpd00029", "EX_cpd00029"],
        },
        {
            "target_name": "pyruvate",
            "tier": "A",
            "category": "validation_target",
            "priority": "high",
            "synonyms": ["pyruvate", "cpd00020", "EX_cpd00020"],
        },
        {
            "target_name": "formate",
            "tier": "A",
            "category": "validation_target",
            "priority": "high",
            "synonyms": ["formate", "cpd00047", "EX_cpd00047"],
        },
        {
            "target_name": "riboflavin",
            "tier": "B",
            "category": "high_value_biotech_target",
            "priority": "medium",
            "synonyms": ["riboflavin", "cpd00220"],
        },
        {
            "target_name": "FMN",
            "tier": "B",
            "category": "high_value_biotech_target",
            "priority": "medium",
            "synonyms": ["FMN", "flavin mononucleotide", "cpd00050"],
        },
        {
            "target_name": "FAD",
            "tier": "B",
            "category": "high_value_biotech_target",
            "priority": "medium",
            "synonyms": ["FAD", "flavin adenine dinucleotide", "cpd00015"],
        },
        {
            "target_name": "hydrogen",
            "tier": "B",
            "category": "high_value_biotech_target",
            "priority": "medium",
            "synonyms": ["hydrogen", "cpd11640"],
        },
        {
            "target_name": "succinate",
            "tier": "C",
            "category": "optional_candidate",
            "priority": "low",
            "synonyms": ["succinate", "cpd00036", "EX_cpd00036"],
        },
    ]
    production_targets: list[dict[str, object]] = []
    discovery: list[dict[str, object]] = []
    readiness: list[dict[str, object]] = []
    for target in targets:
        match = find_target_reaction(model_reactions, list(target["synonyms"]))
        status = "available" if match else "target_candidate_missing_exchange"
        reaction_id = match[0] if match else ""
        reaction_name = match[1] if match else ""
        note = (
            "Matched exchange/demand/sink-like reaction."
            if match
            else "No exchange/demand/sink-like reaction matched; do not run production simulation unless a demand/sink test is explicitly created."
        )
        discovery.append(
            {
                "target_name": target["target_name"],
                "tier": target["tier"],
                "category": target["category"],
                "priority": target["priority"],
                "matched_reaction_id": reaction_id,
                "matched_reaction_name": reaction_name,
                "availability_status": status,
                "synonyms": ";".join(target["synonyms"]),
                "note": note,
            }
        )
        readiness.append(
            {
                "target_name": target["target_name"],
                "tier": target["tier"],
                "readiness_label": "ready_for_analysis" if match else "guidance_only",
                "status": status,
                "reaction_id": reaction_id,
                "interpretation_note": target_interpretation_note(str(target["target_name"]), status),
            }
        )
        if match and target["target_name"] not in {"lactate", "oxygen"}:
            production_targets.append(
                {
                    "condition": "ALL",
                    "reaction_id": reaction_id,
                    "product_name": target["target_name"],
                    "target_type": "product_exchange",
                    "priority": target["priority"],
                    "source": "shewanella_case_target_discovery",
                    "note": f"{target['category']}; tier={target['tier']}; {note}",
                }
            )
    return production_targets, discovery, readiness


def read_sbml_reactions(model_path: str | Path) -> dict[str, str]:
    """Read reaction ids and names from an SBML model with minimal XML parsing."""

    reactions: dict[str, str] = {}
    try:
        for _event, elem in ET.iterparse(model_path, events=("start",)):
            if elem.tag.endswith("reaction"):
                reaction_id = elem.attrib.get("id", "")
                if reaction_id:
                    reactions[reaction_id] = elem.attrib.get("name", "")
                elem.clear()
    except Exception:
        return {}
    return reactions


def build_source_manifest(source: Path, paths: dict[str, Path], adapter_parameters: dict[str, Any]) -> dict[str, Any]:
    """Build source provenance manifest for the case package."""

    files = {}
    for key, path in paths.items():
        files[key] = {
            "path": str(path),
            "exists": path.exists(),
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "sha256": sha256_file(path) if path.exists() and path.is_file() and path.stat().st_size < 50_000_000 else "",
        }
    return {
        "schema_version": CASE_SCHEMA_VERSION,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_dir": str(source),
        "read_only_source": True,
        "adapter_parameters": adapter_parameters,
        "files": files,
        "conversion_notes": [
            "Taylor proteomics fractions were converted to mmol_per_gDW using protein MW and Ptot.",
            "GotEnzymes2 kcat rows retain KEGG reaction ids; GEM mapping is reviewed downstream.",
            "Existing ecShewanella outputs are validation baselines, not model-generation inputs.",
        ],
    }


def build_source_summary_rows(paths: dict[str, Path], manifest: dict[str, Any]) -> list[dict[str, object]]:
    rows = []
    files = manifest.get("files", {})
    for key, item in files.items():
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "source_key": key,
                "path": item.get("path", ""),
                "exists": item.get("exists", False),
                "size_bytes": item.get("size_bytes", 0),
                "sha256": item.get("sha256", ""),
                "usage": source_usage_label(key),
            }
        )
    return rows


def build_kcat_summary_rows(kcat_rows: list[dict[str, object]], model_reactions: dict[str, str]) -> list[dict[str, object]]:
    total = len(kcat_rows)
    reactions = {str(row.get("target_id") or "") for row in kcat_rows if row.get("target_id")}
    mapped = 0
    for reaction in reactions:
        if resolve_reaction_from_index(reaction, model_reactions)[1] == "mapped":
            mapped += 1
    return [
        {
            "metric": "gotenzymes2_kcat_rows",
            "value": total,
            "note": "Rows with positive kcat values retained from GotEnzymes2.",
        },
        {
            "metric": "unique_kegg_reactions",
            "value": len(reactions),
            "note": "Unique KEGG reaction ids in retained GotEnzymes2 rows.",
        },
        {
            "metric": "direct_model_reaction_matches",
            "value": mapped,
            "note": "Direct reaction id matches in the SBML; most KEGG ids may need mapping review.",
        },
    ]


def build_validation_baseline_rows(source: Path) -> list[dict[str, object]]:
    candidates = [
        ("old_fba_comparison", source / "output" / "FBA_High_vs_LowO2_Comparison.csv"),
        ("old_taylor_condition_summary", source / "output" / "taylor_conditions" / "taylor_condition_summary.csv"),
        ("old_enzyme_usage_comparison", source / "output" / "protein_allocation" / "enzyme_usage_comparison.csv"),
    ]
    rows = []
    for key, path in candidates:
        rows.append(
            {
                "baseline_key": key,
                "path": str(path),
                "exists": path.exists(),
                "row_count": max(0, sum(1 for _ in path.open("r", encoding="utf-8-sig", errors="ignore")) - 1)
                if path.exists()
                else 0,
                "status": "available_for_validation" if path.exists() else "missing",
            }
        )
    return rows


def build_initial_ml_summary(tables: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
    return [
        {
            "analysis": "PCA",
            "status": "input_ready" if tables["absolute_proteomics"] else "not_ready",
            "input_rows": len(tables["absolute_proteomics"]),
            "interpretation": "Descriptive separation of highO2 and lowO2 samples.",
        },
        {
            "analysis": "clustering",
            "status": "input_ready" if tables["absolute_proteomics"] else "not_ready",
            "input_rows": len(tables["absolute_proteomics"]),
            "interpretation": "Exploratory grouping of protein or subsystem features.",
        },
        {
            "analysis": "LASSO-lite",
            "status": "exploratory_only" if tables["relative_proteomics"] else "not_ready",
            "input_rows": len(tables["relative_proteomics"]),
            "interpretation": "Marker ranking for oxygen condition; not causal inference.",
        },
    ]


def render_case_readme(*, run_id: str, source: Path) -> str:
    """Render a short operator guide for the generated case package."""

    return f"""# Shewanella GECKO Case Study

This run package was generated from the read-only source project:

`{source}`

## Default Workflow

- Model generation: baseline GEM, E-Flux, GECKO-ready full ecModel, consensus context.
- Analysis: FBA/pFBA, Delta-FBA, evidence comparison, PCA/clustering/LASSO-lite, production/ecFactory-lite readiness.
- GECKO external MATLAB execution is staged but disabled by default. Run the adapter probe before any external GECKO run.

## Key Outputs After Running The Workflow

- `workflow_results/model_variant_registry.csv`
- `gecko_package/generated_adapter.m`
- `gecko_package/protocol_template.m`
- `variant_cobra_results/variant_fba_summary.csv`
- `ml_results/ml_pca_scores.csv`
- `production_results/production_target_ranking.csv`
- `report_results/full_audit_report.html`

## Suggested Visualization Filter

Use this reaction filter for the default production target readiness map:

`R_EX_cpd00029_e0;R_EX_cpd00020_e0;R_EX_cpd00047_e0;R_EX_cpd00050_p0;R_EX_cpd00015_c0;R_EX_cpd00036_e0`

It covers acetate, pyruvate, formate, FMN, FAD, and succinate. Riboflavin and H2 are retained in target discovery as high-value candidates, but are marked as missing exchange/sink support unless you explicitly add demand/sink tests.

## Rebuild Command

```powershell
python tools\\prepare_shewanella_case_study.py --source-dir D:\\MatExt\\GECKO\\ecShewanella --output-root D:\\generate\\user_runs --run-id {run_id} --overwrite
```
"""


def find_target_reaction(model_reactions: dict[str, str], synonyms: list[str]) -> tuple[str, str] | None:
    """Find exchange/demand/sink-like reactions matching a target synonym."""

    exchange_like: list[tuple[int, str, str]] = []
    normalized_synonyms = [_normalize_token(item) for item in synonyms if item]
    for reaction_id, name in model_reactions.items():
        rid = reaction_id.lower()
        if not rid.startswith(("r_ex_", "ex_", "r_dm_", "dm_", "r_sink_", "sink_")):
            continue
        normalized_reaction = _normalize_token(reaction_id)
        haystack = _normalize_token(f"{reaction_id} {name}")
        score = 0
        for synonym in normalized_synonyms:
            if synonym and synonym in normalized_reaction:
                score = max(score, 100 + len(synonym))
            elif synonym and synonym in haystack:
                score = max(score, 10 + len(synonym))
        if score:
            exchange_like.append((score, reaction_id, name))
    if not exchange_like:
        return None
    exchange_like.sort(key=lambda item: (-item[0], item[1]))
    return exchange_like[0][1], exchange_like[0][2]


def resolve_reaction_from_index(raw_reaction: str, model_reactions: dict[str, str]) -> tuple[str, str]:
    candidates = [raw_reaction]
    if raw_reaction.startswith("R_"):
        candidates.append(raw_reaction[2:])
    else:
        candidates.append(f"R_{raw_reaction}")
    normalized = {_normalize_reaction_id(key): key for key in model_reactions}
    for candidate in candidates:
        found = normalized.get(_normalize_reaction_id(candidate))
        if found:
            return found, "mapped"
    return candidates[-1], "not_found"


def _csv_payload(filename: str, kind: str, role: str, rows: list[dict[str, object]]) -> UploadFilePayload:
    data = _csv_bytes(rows)
    columns = list(rows[0].keys()) if rows else []
    return UploadFilePayload(
        filename=filename,
        data=data,
        kind=kind,
        role=role,
        columns=columns,
        status="ok" if rows else "warning",
        details=[f"Generated Shewanella case table; rows={len(rows)}."],
    )


def _csv_bytes(rows: list[dict[str, object]]) -> bytes:
    if not rows:
        return b""
    from io import StringIO

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _read_csv_rows(path: str | Path) -> list[dict[str, str]]:
    source = Path(path)
    delimiter = "\t" if source.suffix.lower() in {".tsv", ".txt"} else ","
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=delimiter)
        try:
            header = next(reader)
        except StopIteration:
            return []
        unique_header = _unique_header(header)
        return [dict(zip(unique_header, row)) for row in reader]


def _unique_header(header: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    result = []
    for raw in header:
        name = raw.strip()
        count = seen.get(name, 0)
        seen[name] = count + 1
        result.append(name if count == 0 else f"{name}__{count + 1}")
    return result


def _source_paths(source: Path) -> dict[str, Path]:
    return {
        "adapter": source / "ecShewanellaAdapter.m",
        "model": source / "models" / "iLJ1162.xml",
        "alternate_model": source / "models" / "iLJ1162_Final_Clean.xml",
        "existing_ecmodel": source / "shewanella_ecModel.xml",
        "taylor": source / "data" / "Taylor_2013_Proteomics.csv",
        "legacy_proteomics": source / "data" / "proteomics.tsv",
        "gotenzymes": source / "data" / "Shewanella_oneidensis_GotEnzymes_Full_Fixed.csv",
        "uniprot": source / "data" / "uniprot.tsv",
        "kegg": source / "data" / "kegg.tsv",
        "conditions": source / "analysis" / "taylor_conditions" / "Taylor_conditions.csv",
        "old_fba_comparison": source / "output" / "FBA_High_vs_LowO2_Comparison.csv",
        "old_protein_allocation": source / "output" / "protein_allocation" / "enzyme_usage_comparison.csv",
        "old_taylor_condition_summary": source / "output" / "taylor_conditions" / "taylor_condition_summary.csv",
    }


def _validate_source_files(source: Path) -> None:
    paths = _source_paths(source)
    required = ["adapter", "model", "taylor", "gotenzymes", "conditions"]
    missing = [key for key in required if not paths[key].exists()]
    if missing:
        details = ", ".join(f"{key}={paths[key]}" for key in missing)
        raise FileNotFoundError(f"Missing required Shewanella source files: {details}")


def _augment_upload_manifest(package_dir: Path, files: dict[str, str], row_counts: dict[str, int]) -> None:
    manifest_path = package_dir / "upload_manifest.json"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["case_study"] = {
        "case_id": "shewanella_gecko_case",
        "status": "ready_for_workflow",
        "files": files,
        "row_counts": row_counts,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _assert_safe_target(target: Path, output_base: Path) -> None:
    try:
        target.relative_to(output_base)
    except ValueError as exc:
        raise ValueError(f"Refusing to overwrite target outside output root: {target}") from exc


def _safe_run_id(run_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", run_id.strip()).strip("_")
    if not safe:
        raise ValueError("run_id cannot be empty.")
    return safe


def _fraction_to_mmol_per_gdw(fraction: float | None, mw_da: float | None, ptot: float) -> float | None:
    if fraction is None or mw_da is None or fraction <= 0 or mw_da <= 0:
        return None
    return (fraction * ptot / mw_da) * 1000.0


def _measurement_bounds(value: float, tolerance: float, direction: str) -> tuple[float, float]:
    if abs(value) <= 1e-12:
        return (-1e-9, 1e-9)
    delta = abs(value) * tolerance
    if direction == "uptake":
        return (-(value + delta), -(value - delta))
    return (value - delta, value + delta)


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _first_nonempty(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _matlab_string(text: str, field: str) -> str:
    pattern = rf"params\.{re.escape(field)}\s*=\s*'([^']*)'"
    match = re.search(pattern, text)
    return match.group(1).strip() if match else ""


def _matlab_number(text: str, field: str) -> float | None:
    pattern = rf"params\.{re.escape(field)}\s*=\s*([0-9.eE+-]+)"
    match = re.search(pattern, text)
    return _to_float(match.group(1)) if match else None


def _matlab_bool(text: str, field: str, default: bool = False) -> bool:
    pattern = rf"params\.{re.escape(field)}\s*=\s*(true|false)"
    match = re.search(pattern, text, flags=re.IGNORECASE)
    if not match:
        return default
    return match.group(1).lower() == "true"


def _normalize_reaction_id(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower().removeprefix("r_"))


def _normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_usage_label(key: str) -> str:
    return {
        "adapter": "GECKO ModelAdapter source",
        "model": "baseline GEM",
        "alternate_model": "optional GEM comparator",
        "existing_ecmodel": "old ecModel validation reference",
        "taylor": "proteomics/transcriptomics/annotation source",
        "legacy_proteomics": "legacy GECKO proteomics reference",
        "gotenzymes": "GotEnzymes2 kcat prior source",
        "uniprot": "protein sequence and EC source",
        "kegg": "mapping support",
        "conditions": "condition bounds source",
    }.get(key, "validation/reference")


def target_interpretation_note(target_name: str, status: str) -> str:
    if status != "available":
        return "Candidate remains guidance-only until a model exchange/demand/sink reaction is available."
    if target_name.lower() in {"riboflavin", "fmn", "fad", "hydrogen"}:
        return "High-value Shewanella/EET-related target; interpret production simulations with pathway and export caution."
    return "Validation target available for production/ecFactory-lite analysis."
