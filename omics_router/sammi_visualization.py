"""Build SAMMI-compatible visualization packages from user run outputs.

The v1 implementation intentionally does not depend on SAMMIpy or MATLAB
SAMMIM. It can use configured or vendored standalone SAMMI assets when they
are present, while keeping the lightweight in-app viewer as the default path.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constraints import CORE_NS, read_csv_records, relocate_package_path, write_csv, write_json
from .model_generation import read_model_variant_registry, resolve_analysis_variant, safe_variant_dir_name


PROJECT_ROOT = Path(__file__).resolve().parents[1]

OVERLAY_SOURCES: dict[str, dict[str, str]] = {
    "none": {
        "label": "No overlay",
        "path": "",
        "value_column": "",
        "semantic_type": "none",
        "description": "Only model topology and grouping are exported.",
    },
    "transcriptomics_evidence": {
        "label": "Transcriptomics reaction evidence",
        "path": "generated_constraints/reaction_expression_evidence.csv",
        "value_column": "reaction_score",
        "semantic_type": "evidence",
        "description": "Reaction-level transcriptomics evidence generated from GPR rules.",
    },
    "relative_proteomics": {
        "label": "Relative proteomics reaction evidence",
        "path": "generated_constraints/relative_protein_reaction_evidence.csv",
        "value_column": "reaction_score",
        "semantic_type": "evidence",
        "description": "Reaction-level relative proteomics evidence when available.",
    },
    "consensus_evidence": {
        "label": "Consensus multi-omics evidence",
        "path": "generated_constraints/multi_omics_consensus_reaction_evidence.csv",
        "value_column": "consensus_score",
        "semantic_type": "evidence",
        "description": "Consensus evidence prepared from multiple omics layers.",
    },
    "fba_flux": {
        "label": "Variant FBA flux",
        "path": "variant_cobra_results/{variant_dir}/predicted_fluxes.csv",
        "value_column": "predicted_flux",
        "semantic_type": "flux",
        "description": "FBA fluxes for the selected model variant when variant FBA has been run.",
    },
    "gecko_flux_delta": {
        "label": "GECKO highO2 vs lowO2 flux delta",
        "path": "gecko_run_results/gecko_flux_delta_high_vs_low.csv",
        "value_column": "flux_delta_high_minus_low",
        "semantic_type": "flux",
        "description": "GECKO external-run flux delta comparing highO2 and lowO2 condition-specific ecModels.",
    },
    "enzyme_capacity": {
        "label": "Enzyme capacity",
        "path": "enzyme_results/reaction_enzyme_capacity.csv",
        "value_column": "enzyme_capacity_mmol_per_gDW_per_h",
        "semantic_type": "enzyme_capacity",
        "description": "Reaction-level enzyme capacity prepared from proteomics and kcat priors.",
    },
    "kcat_coverage": {
        "label": "kcat coverage",
        "path": "generated_constraints/kcat_priors.csv",
        "value_column": "kcat",
        "semantic_type": "enzyme_capacity",
        "description": "Reaction-level kcat prior coverage from uploaded or curated enzyme evidence.",
    },
    "production_ranking": {
        "label": "Production reaction ranking",
        "path": "production_results/production_design_targets.csv",
        "value_column": "score",
        "semantic_type": "production",
        "description": "Production-design reaction scores from FSEOF-lite or related outputs.",
    },
    "ml_feature_importance": {
        "label": "ML feature importance",
        "path": "ml_hybrid_profiles/{ml_profile_id}/results/ml_feature_importance_overlay.csv",
        "value_column": "importance_score",
        "semantic_type": "ml_importance",
        "description": "Reaction-level ML/HYBRID feature importance overlay from a generated profile.",
    },
    "external_ml_feature_importance": {
        "label": "External ML feature importance",
        "path": "ml_hybrid_profiles/{ml_profile_id}/external_results/__latest__/external_ml_feature_importance_overlay.csv",
        "value_column": "importance_score",
        "semantic_type": "ml_importance",
        "description": "Reaction-level feature importance overlay imported from an external ML result folder.",
    },
    "uniprot_gpr_warning": {
        "label": "UniProt / GPR warning flags",
        "path": "uniprot_model_check/reaction_annotation_flags.csv",
        "value_column": "severity",
        "semantic_type": "warning",
        "description": "Reaction-level annotation warnings from the UniProt/GPR model check.",
    },
    "custom_overlay": {
        "label": "Custom reaction overlay",
        "path": "visualization_inputs/custom_overlay.csv",
        "value_column": "overlay_value",
        "semantic_type": "custom",
        "description": "User-provided reaction overlay table for focused pathway maps.",
    },
}

GROUPING_MODES = {"subsystem", "compartment", "selected_reactions"}
COMMON_CURRENCY_METABOLITES = {
    "h",
    "h2o",
    "atp",
    "adp",
    "amp",
    "pi",
    "ppi",
    "nad",
    "nadh",
    "nadp",
    "nadph",
    "coa",
    "co2",
    "o2",
    "nh4",
    "hco3",
    "q8",
    "q8h2",
}
OVERLAY_COLUMNS = [
    "overlay_source",
    "semantic_type",
    "condition",
    "reaction_id",
    "cobra_reaction_id",
    "overlay_value",
    "overlay_value_column",
    "evidence",
    "status",
    "overlay_color",
    "overlay_size",
    "warning_flag",
    "readiness_label",
    "candidate_type",
    "candidate_action",
    "production_score",
    "product_reaction_id",
    "product_name",
    "warning_reasons",
    "source_file",
    "source_status",
]


@dataclass(slots=True)
class SammiVisualizationResult:
    """Result object returned by the SAMMI-compatible package builder."""

    status: str
    message: str
    output_dir: Path
    files: dict[str, str]
    manifest: dict[str, Any]


def build_sammi_visualization_package(
    package_dir: str | Path,
    *,
    variant_id: str = "",
    grouping_mode: str = "subsystem",
    overlay_source: str = "none",
    reaction_filter: list[str] | str | None = None,
    ml_profile_id: str = "",
    output_dir: str | Path | None = None,
) -> SammiVisualizationResult:
    """Create a subsystem-focused SAMMI-compatible visualization package.

    The function is deliberately local and reproducible. It reads the model
    variant registry, parses SBML with the standard library, merges optional
    overlay tables, and writes a package that documents optional SAMMI helper
    availability without requiring those helpers.
    """

    package = Path(package_dir)
    registry_rows = read_model_variant_registry(package)
    variant = resolve_analysis_variant(registry_rows, variant_id)
    selected_variant_id = variant.get("variant_id") or variant_id or "baseline_gem__all"
    variant_dir = safe_variant_dir_name(selected_variant_id)
    output = Path(output_dir) if output_dir else package / "visualization_results" / "sammi" / variant_dir
    output.mkdir(parents=True, exist_ok=True)

    grouping = grouping_mode if grouping_mode in GROUPING_MODES else "subsystem"
    overlay_key = overlay_source if overlay_source in OVERLAY_SOURCES else "none"
    model_path = resolve_variant_model_path(package, variant)
    files = package_file_paths(output)

    if not model_path or not model_path.exists():
        empty_manifest = build_manifest(
            package=package,
            output=output,
            variant=variant,
            grouping_mode=grouping,
            overlay_source=overlay_key,
            model_path=model_path,
            reaction_count=0,
            group_count=0,
            overlay_count=0,
            selected_reaction_count=0,
            status="model_missing",
            message="No readable model path was available for the selected model variant.",
        )
        write_empty_package(files, empty_manifest)
        return SammiVisualizationResult(
            status="model_missing",
            message=str(empty_manifest["message"]),
            output_dir=output,
            files={key: str(value) for key, value in files.items()},
            manifest=empty_manifest,
        )

    all_reactions = parse_sbml_reactions(model_path)
    filter_info = summarize_reaction_filter(all_reactions, reaction_filter)
    reactions = list(all_reactions)
    selected_reactions = selected_reaction_ids(package, variant, reaction_filter)
    if grouping == "selected_reactions" and selected_reactions:
        reactions = [row for row in reactions if row["reaction_id"] in selected_reactions or row["cobra_reaction_id"] in selected_reactions]
    elif reaction_filter:
        reactions = [row for row in reactions if row["reaction_id"] in selected_reactions or row["cobra_reaction_id"] in selected_reactions]

    package_status = "empty_filter" if filter_info["has_filter"] and not reactions else "completed"
    package_message = (
        "Reaction filter did not match any model reactions. Use Preview / Validate Filter and choose existing reaction ids."
        if package_status == "empty_filter"
        else "SAMMI-compatible visualization package generated."
    )

    assignment_rows = build_assignment_rows(reactions, grouping, selected_reactions)
    summary_rows = build_group_summary_rows(assignment_rows)
    overlay_rows, overlay_status, overlay_summary_rows = build_overlay_rows(
        package,
        reactions,
        overlay_key,
        variant_dir,
        reaction_filter=reaction_filter,
        ml_profile_id=ml_profile_id,
    )
    package_json = build_package_json(
        package=package,
        variant=variant,
        model_path=model_path,
        grouping_mode=grouping,
        assignment_rows=assignment_rows,
        summary_rows=summary_rows,
        overlay_rows=overlay_rows,
        overlay_summary_rows=overlay_summary_rows,
    )
    assets_rows = sammi_assets_status_rows()
    manifest = build_manifest(
        package=package,
        output=output,
        variant=variant,
        grouping_mode=grouping,
        overlay_source=overlay_key,
        model_path=model_path,
        reaction_count=len(assignment_rows),
        group_count=len(summary_rows),
        overlay_count=len(overlay_rows),
        selected_reaction_count=len(selected_reactions),
        status=package_status,
        message=package_message,
        overlay_status=overlay_status,
        overlay_summary_rows=overlay_summary_rows,
        filter_preview=filter_info,
    )

    write_csv(files["assignment"], assignment_rows)
    write_csv(files["summary"], summary_rows)
    write_overlay_csv(files["overlay"], overlay_rows)
    write_csv(files["overlay_summary"], overlay_summary_rows)
    if overlay_key == "production_ranking":
        write_production_visualization_outputs(
            output,
            manifest=manifest,
            overlay_rows=overlay_rows,
            overlay_summary_rows=overlay_summary_rows,
            assignment_rows=assignment_rows,
        )
    write_json(files["package"], package_json)
    write_json(files["manifest"], manifest)
    write_csv(files["assets_status"], assets_rows)
    files["readme"].write_text(build_readme_html(manifest), encoding="utf-8")
    files["launch"].write_text(build_launch_html(manifest), encoding="utf-8")

    return SammiVisualizationResult(
        status=package_status,
        message=str(manifest["message"]),
        output_dir=output,
        files={key: str(value) for key, value in files.items()},
        manifest=manifest,
    )


def overlay_availability_rows(package_dir: str | Path, variant_id: str = "") -> list[dict[str, object]]:
    """Return UI-friendly availability rows for known overlay sources."""

    package = Path(package_dir)
    variant_dir = safe_variant_dir_name(variant_id)
    rows: list[dict[str, object]] = []
    for source_id, spec in OVERLAY_SOURCES.items():
        path_template = spec["path"]
        path = (
            package / path_template.format(variant_dir=variant_dir, ml_profile_id="")
            if path_template
            else None
        )
        rows.append(
            {
                "overlay_source": source_id,
                "label": spec["label"],
                "semantic_type": spec["semantic_type"],
                "available": True if source_id == "none" else bool(path and path.exists() and path.stat().st_size > 0),
                "path": str(path) if path else "",
                "description": spec["description"],
            }
        )
    return rows


def list_sammi_model_reactions(
    package_dir: str | Path,
    *,
    variant_id: str = "",
    query: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    """Return searchable reaction metadata for a selected model variant."""

    package = Path(package_dir)
    registry_rows = read_model_variant_registry(package)
    variant = resolve_analysis_variant(registry_rows, variant_id)
    selected_variant_id = variant.get("variant_id") or variant_id or "baseline_gem__all"
    model_path = resolve_variant_model_path(package, variant)
    if not model_path or not model_path.exists():
        return {
            "status": "model_missing",
            "message": "No readable model path was available for the selected model variant.",
            "variant_id": selected_variant_id,
            "model_path": str(model_path) if model_path else "",
            "reaction_count": 0,
            "reactions": [],
        }

    reactions = parse_sbml_reactions(model_path)
    query_text = query.strip().lower()
    if query_text:
        reactions = [
            row
            for row in reactions
            if query_text
            in " ".join(
                [
                    str(row.get("reaction_id", "")),
                    str(row.get("cobra_reaction_id", "")),
                    str(row.get("reaction_name", "")),
                    str(row.get("subsystem", "")),
                ]
            ).lower()
        ]
    capped_limit = max(1, min(int(limit or 50), 500))
    return {
        "status": "ok",
        "message": "Reaction list loaded.",
        "variant_id": selected_variant_id,
        "model_path": str(model_path),
        "reaction_count": len(reactions),
        "reactions": [reaction_search_row(row) for row in reactions[:capped_limit]],
    }


def preview_sammi_filter(
    package_dir: str | Path,
    *,
    variant_id: str = "",
    grouping_mode: str = "subsystem",
    overlay_source: str = "none",
    reaction_filter: list[str] | str | None = None,
    subsystem_filter: list[str] | str | None = None,
    top_n: int = 120,
    include_currency_metabolites: bool = False,
    max_nodes: int = 900,
    max_links: int = 1800,
) -> dict[str, Any]:
    """Preview reaction filters without writing visualization outputs."""

    package = Path(package_dir)
    registry_rows = read_model_variant_registry(package)
    variant = resolve_analysis_variant(registry_rows, variant_id)
    selected_variant_id = variant.get("variant_id") or variant_id or "baseline_gem__all"
    model_path = resolve_variant_model_path(package, variant)
    if not model_path or not model_path.exists():
        return {
            "status": "model_missing",
            "message": "No readable model path was available for the selected model variant.",
            "variant_id": selected_variant_id,
            "reaction_count_available": 0,
            "reaction_count_after_filter": 0,
            "matched_reaction_ids": [],
            "missing_reaction_ids": _raw_filter_tokens(reaction_filter),
            "estimated_node_count": 0,
            "estimated_link_count": 0,
            "suggested_reactions": [],
        }

    reactions = parse_sbml_reactions(model_path)
    filter_info = summarize_reaction_filter(reactions, reaction_filter)
    filtered = list(reactions)
    if filter_info["has_filter"]:
        matched = set(filter_info["matched_reaction_ids"])
        filtered = [row for row in filtered if str(row.get("reaction_id", "")) in matched]

    subsystem_terms = {term.lower() for term in _raw_filter_tokens(subsystem_filter)}
    if subsystem_terms:
        filtered = [
            row
            for row in filtered
            if any(
                term
                in " ".join([str(row.get("subsystem", "")), str(row.get("compartment", "")), str(row.get("reaction_name", ""))]).lower()
                for term in subsystem_terms
            )
        ]

    if not filter_info["has_filter"] and not subsystem_terms and int(top_n or 0) > 0 and overlay_source != "none":
        filtered = filtered[: max(0, int(top_n or 0))]

    estimate = estimate_reaction_graph_size(filtered, include_currency_metabolites=include_currency_metabolites)
    if filter_info["has_filter"] and not filtered:
        status = "empty_filter"
        message = "Reaction filter did not match any model reactions."
    elif subsystem_terms and not filtered:
        status = "empty_filter"
        message = "Subsystem filter did not match any model reactions."
    elif (estimate["estimated_node_count"] > max_nodes or estimate["estimated_link_count"] > max_links) and not filter_info["has_filter"] and not subsystem_terms:
        status = "needs_filtering"
        message = "The graph is likely too large; choose a subsystem, reaction list, or lower top_n."
    else:
        status = "ok"
        message = "Filter preview is renderable."

    return {
        "status": status,
        "message": message,
        "variant_id": selected_variant_id,
        "grouping_mode": grouping_mode if grouping_mode in GROUPING_MODES else "subsystem",
        "overlay_source": overlay_source if overlay_source in OVERLAY_SOURCES else "none",
        "reaction_count_available": len(reactions),
        "reaction_count_after_filter": len(filtered),
        "matched_reaction_ids": filter_info["matched_reaction_ids"],
        "missing_reaction_ids": filter_info["missing_reaction_ids"],
        "estimated_node_count": estimate["estimated_node_count"],
        "estimated_link_count": estimate["estimated_link_count"],
        "suggested_reactions": filter_info["suggested_reactions"],
    }


def sammi_vendor_status(app_root: str | Path | None = None) -> dict[str, object]:
    """Return readiness for vendored standalone SAMMI assets."""

    root = Path(app_root or os.environ.get("OMICS_GEM_PROJECT_ROOT") or PROJECT_ROOT)
    candidates = [
        root / "vendor" / "sammi_standalone" / "sammi_vendor_manifest.json",
        root / ".runtime_cache" / "sammi_vendor" / "sammi_vendor_manifest.json",
        PROJECT_ROOT / ".runtime_cache" / "sammi_vendor" / "sammi_vendor_manifest.json",
    ]
    manifest_path = next((path for path in candidates if path.exists()), candidates[1])
    manifest: dict[str, Any] = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            manifest = {"status": "blocked", "message": "SAMMI vendor manifest is not valid JSON."}
    if manifest_path.name == "sammi_vendor_manifest.json" and manifest_path.parent.name == "sammi_standalone":
        assets_root = manifest_path.parent
    else:
        assets_root = Path(str(manifest.get("assets_root") or manifest_path.parent / "sammi_standalone"))
    index_path = assets_root / "index.html"
    ready = bool(manifest.get("status") == "ready" and index_path.exists())
    status = "ready" if ready else str(manifest.get("status") or "missing")
    return {
        "status": status,
        "vendored_assets_available": ready,
        "vendor_manifest_path": str(manifest_path),
        "vendor_manifest_exists": manifest_path.exists(),
        "assets_root": str(assets_root),
        "vendored_index_path": str(index_path),
        "vendored_index_exists": index_path.exists(),
        "source_url": str(manifest.get("source_url") or ""),
        "license_status": str(manifest.get("license_status") or ("unknown" if manifest_path.exists() else "missing")),
        "license_note": str(manifest.get("license_note") or "SAMMI standalone assets are optional and subject to their upstream license."),
        "distribution_mode": "vendored_local_assets" if ready else "external_open_mode",
        "message": str(
            manifest.get("message")
            or (
                "Vendored standalone SAMMI assets are available."
                if ready
                else "Vendored SAMMI assets are not available; use lightweight viewer or external SAMMI."
            )
        ),
    }


def sammi_resource_policy(standalone_home: str | Path | None = None) -> dict[str, object]:
    """Return the current standalone SAMMI resource strategy.

    v1 defaults to the lightweight viewer / external-open mode. Local assets
    are considered configured when SAMMI_STANDALONE_HOME points to a directory
    containing index.html. Vendored assets are used only when no explicit local
    path is configured and a ready vendor manifest exists.
    """

    raw_home = str(standalone_home if standalone_home is not None else os.environ.get("SAMMI_STANDALONE_HOME", "")).strip()
    home = Path(raw_home) if raw_home else None
    index_html = home / "index.html" if home else None
    local_ready = bool(index_html and index_html.exists())
    vendor = sammi_vendor_status()
    vendor_ready = bool(vendor["vendored_assets_available"])
    effective_home = home if local_ready else Path(str(vendor["assets_root"])) if vendor_ready else home
    effective_index = index_html if local_ready else Path(str(vendor["vendored_index_path"])) if vendor_ready else index_html
    resource_strategy = (
        "local_assets_configured"
        if local_ready
        else "vendored_assets_configured"
        if vendor_ready
        else "standalone_external_only"
    )
    open_mode = "local_shell_placeholder" if local_ready else "vendored_local_shell" if vendor_ready else "external_open_mode"
    return {
        "resource_strategy": resource_strategy,
        "open_mode": open_mode,
        "vendoring_status": "vendored_assets_available"
        if vendor_ready
        else "vendoring_not_enabled"
        if str(vendor["status"]) == "missing"
        else str(vendor["status"]),
        "license": "GPL >=3",
        "resource_source": "SAMMI standalone browser app / MD Anderson public software",
        "standalone_home": str(effective_home) if effective_home else "",
        "local_index_html": str(effective_index) if effective_index else "",
        "local_assets_available": local_ready or vendor_ready,
        "vendored_assets_available": vendor_ready,
        "sammi_vendor": vendor,
        "requires_user_config": not (local_ready or vendor_ready),
        "can_embed_locally": local_ready or vendor_ready,
        "guidance": (
            "Local standalone SAMMI assets were detected; the embedded SAMMI shell can be opened."
            if local_ready
            else "Vendored standalone SAMMI assets are available; the embedded SAMMI shell can be opened."
            if vendor_ready
            else "Use external SAMMI web app, configure SAMMI_STANDALONE_HOME, or run the SAMMI vendor script."
        ),
    }


def resolve_variant_model_path(package: Path, variant: dict[str, str]) -> Path | None:
    """Resolve the selected variant's model path, falling back to the staged GEM."""

    for key in ("context_model_sbml", "primary_model_path", "source_model_path"):
        value = str(variant.get(key, "")).strip()
        if not value:
            continue
        relocated = relocate_package_path(package, value)
        if relocated is not None:
            return relocated
        path = Path(value)
        if not path.is_absolute():
            path = package / value
        if path.exists():
            return path
    for row in _safe_read_csv(package / "input_file_map.csv"):
        if row.get("kind") == "model" or row.get("role") == "gem":
            for key in ("path", "relative_path"):
                value = row.get(key, "")
                if not value:
                    continue
                relocated = relocate_package_path(package, value)
                if relocated is not None:
                    return relocated
                path = Path(value)
                if not path.is_absolute():
                    path = package / value
                if path.exists():
                    return path
    return None


def parse_sbml_reactions(model_path: str | Path) -> list[dict[str, object]]:
    """Extract reaction metadata needed for a SAMMI-compatible package."""

    tree = ET.parse(model_path)
    root = tree.getroot()
    rows: list[dict[str, object]] = []
    for reaction in root.findall(f".//{CORE_NS}reaction"):
        reaction_id = reaction.attrib.get("id", "")
        if not reaction_id:
            continue
        reactants = _species_references(reaction, "listOfReactants")
        products = _species_references(reaction, "listOfProducts")
        compartment = reaction.attrib.get("compartment") or infer_reaction_compartment(reactants + products)
        rows.append(
            {
                "reaction_id": reaction_id,
                "cobra_reaction_id": reaction_id[2:] if reaction_id.startswith("R_") else reaction_id,
                "reaction_name": reaction.attrib.get("name", ""),
                "subsystem": extract_reaction_subsystem(reaction),
                "compartment": compartment or "unknown",
                "reversible": str(reaction.attrib.get("reversible", "")).lower() == "true",
                "reactants": ";".join(reactants),
                "products": ";".join(products),
            }
        )
    return rows


def reaction_search_row(row: dict[str, object]) -> dict[str, object]:
    reactants = _split_semicolon(str(row.get("reactants", "")))
    products = _split_semicolon(str(row.get("products", "")))
    return {
        "reaction_id": str(row.get("reaction_id", "")),
        "cobra_reaction_id": str(row.get("cobra_reaction_id", "")),
        "reaction_name": str(row.get("reaction_name", "")),
        "subsystem": str(row.get("subsystem", "")),
        "compartment": str(row.get("compartment", "")),
        "reactant_count": len(reactants),
        "product_count": len(products),
        "metabolite_count": len(set(reactants + products)),
    }


def summarize_reaction_filter(reactions: list[dict[str, object]], reaction_filter: list[str] | str | None) -> dict[str, Any]:
    raw_tokens = _raw_filter_tokens(reaction_filter)
    known_by_alias: dict[str, str] = {}
    for row in reactions:
        reaction_id = str(row.get("reaction_id", ""))
        cobra_id = str(row.get("cobra_reaction_id", ""))
        if reaction_id:
            known_by_alias[reaction_id] = reaction_id
            known_by_alias[reaction_id.lower()] = reaction_id
        if cobra_id:
            known_by_alias[cobra_id] = reaction_id
            known_by_alias[cobra_id.lower()] = reaction_id
        if reaction_id.startswith("R_"):
            known_by_alias[reaction_id[2:]] = reaction_id
            known_by_alias[reaction_id[2:].lower()] = reaction_id
        elif reaction_id:
            known_by_alias[f"R_{reaction_id}"] = reaction_id
            known_by_alias[f"R_{reaction_id}".lower()] = reaction_id

    matched: set[str] = set()
    missing: list[str] = []
    for token in raw_tokens:
        aliases = [token, token.lower()]
        aliases.append(token[2:] if token.startswith("R_") else f"R_{token}")
        aliases.append((token[2:] if token.startswith("R_") else f"R_{token}").lower())
        match = next((known_by_alias[alias] for alias in aliases if alias in known_by_alias), "")
        if match:
            matched.add(match)
        else:
            missing.append(token)
    return {
        "has_filter": bool(raw_tokens),
        "raw_reaction_filter": raw_tokens,
        "matched_reaction_ids": sorted(matched),
        "missing_reaction_ids": missing,
        "suggested_reactions": suggested_reaction_rows(reactions, raw_tokens),
    }


def estimate_reaction_graph_size(
    reactions: list[dict[str, object]],
    *,
    include_currency_metabolites: bool = False,
) -> dict[str, int]:
    metabolites: set[str] = set()
    link_count = 0
    for row in reactions:
        for species in _split_semicolon(str(row.get("reactants", ""))) + _split_semicolon(str(row.get("products", ""))):
            if not include_currency_metabolites and _is_currency_species(species):
                continue
            metabolites.add(species)
            link_count += 1
    return {
        "estimated_node_count": len(reactions) + len(metabolites),
        "estimated_link_count": link_count,
    }


def suggested_reaction_rows(reactions: list[dict[str, object]], raw_tokens: list[str], limit: int = 8) -> list[dict[str, object]]:
    preferred = ["R_PFK", "R_PGI", "R_GAPD", "R_ICL", "R_TPI", "R_ACONTa", "R_CS", "R_PYK"]
    by_id = {str(row.get("reaction_id", "")): row for row in reactions}
    suggestions: list[dict[str, object]] = []
    for reaction_id in preferred:
        if reaction_id in by_id:
            suggestions.append(reaction_search_row(by_id[reaction_id]))
    query_terms = [token.lower().replace("r_", "") for token in raw_tokens]
    for row in reactions:
        if len(suggestions) >= limit:
            break
        haystack = " ".join(
            [
                str(row.get("reaction_id", "")),
                str(row.get("cobra_reaction_id", "")),
                str(row.get("reaction_name", "")),
                str(row.get("subsystem", "")),
            ]
        ).lower()
        if query_terms and not any(term and term in haystack for term in query_terms):
            continue
        candidate = reaction_search_row(row)
        if candidate["reaction_id"] not in {item["reaction_id"] for item in suggestions}:
            suggestions.append(candidate)
    if len(suggestions) < limit:
        for row in reactions:
            if len(suggestions) >= limit:
                break
            reaction_id = str(row.get("reaction_id", ""))
            if not reaction_id or reaction_id.startswith(("R_EX_", "R_DM_")):
                continue
            candidate = reaction_search_row(row)
            if candidate["reaction_id"] not in {item["reaction_id"] for item in suggestions}:
                suggestions.append(candidate)
    return suggestions[:limit]


def extract_reaction_subsystem(reaction: ET.Element) -> str:
    """Extract a subsystem label from common SBML notes/annotation patterns."""

    text_chunks: list[str] = []
    for node in list(reaction):
        if _local_name(node.tag) in {"notes", "annotation"}:
            text_chunks.append(" ".join(node.itertext()))
    text = " ".join(text_chunks)
    patterns = [
        r"SUBSYSTEM\s*[:=]\s*([^;\n\r<]+)",
        r"Subsystem\s*[:=]\s*([^;\n\r<]+)",
        r"subsystem\s*[:=]\s*([^;\n\r<]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            subsystem = _clean_label(match.group(1))
            if subsystem:
                return subsystem
    return "unannotated"


def infer_reaction_compartment(species_ids: list[str]) -> str:
    compartments: list[str] = []
    for species in species_ids:
        token = species.rsplit("_", 1)[-1] if "_" in species else ""
        if token and 1 <= len(token) <= 4 and token.isalnum():
            compartments.append(token)
    if not compartments:
        return "unknown"
    counts = {value: compartments.count(value) for value in set(compartments)}
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def selected_reaction_ids(
    package: Path,
    variant: dict[str, str],
    reaction_filter: list[str] | str | None = None,
) -> set[str]:
    """Collect selected/core/keep reactions for focused context maps."""

    selected = _normalize_reaction_filter(reaction_filter)
    candidate_paths: list[Path] = []
    for key in ("primary_artifact", "supporting_files", "generated_files"):
        raw_value = str(variant.get(key, "")).strip()
        if not raw_value:
            continue
        for item in raw_value.split(";"):
            path = Path(item)
            if not path.is_absolute():
                path = package / item
            name = path.name.lower()
            if any(token in name for token in ("selected", "keep", "core", "context")):
                candidate_paths.append(path)
    for path in candidate_paths:
        for row in _safe_read_csv(path):
            for key in ("reaction_id", "cobra_reaction_id", "model_reaction_id"):
                value = row.get(key, "")
                if value:
                    selected.add(value)
                    selected.add(value[2:] if value.startswith("R_") else f"R_{value}")
    return selected


def build_assignment_rows(
    reactions: list[dict[str, object]],
    grouping_mode: str,
    selected_reactions: set[str],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for reaction in reactions:
        reaction_id = str(reaction["reaction_id"])
        cobra_id = str(reaction["cobra_reaction_id"])
        if grouping_mode == "compartment":
            group_id = str(reaction.get("compartment") or "unknown")
            group_label = f"Compartment: {group_id}"
        elif grouping_mode == "selected_reactions":
            is_selected = reaction_id in selected_reactions or cobra_id in selected_reactions
            group_id = "selected_reactions" if is_selected else "other_reactions"
            group_label = "Selected reactions" if is_selected else "Other reactions"
        else:
            group_id = _slug(str(reaction.get("subsystem") or "unannotated"))
            group_label = str(reaction.get("subsystem") or "unannotated")
        rows.append(
            {
                "reaction_id": reaction_id,
                "cobra_reaction_id": cobra_id,
                "reaction_name": reaction.get("reaction_name", ""),
                "grouping_mode": grouping_mode,
                "group_id": group_id,
                "group_label": group_label,
                "subsystem": reaction.get("subsystem", "unannotated"),
                "compartment": reaction.get("compartment", "unknown"),
                "selected_reaction": reaction_id in selected_reactions or cobra_id in selected_reactions,
                "reactants": reaction.get("reactants", ""),
                "products": reaction.get("products", ""),
            }
        )
    return rows


def build_group_summary_rows(assignment_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for row in assignment_rows:
        group_id = str(row["group_id"])
        current = grouped.setdefault(
            group_id,
            {
                "grouping_mode": row["grouping_mode"],
                "group_id": group_id,
                "group_label": row["group_label"],
                "reaction_count": 0,
                "selected_reaction_count": 0,
            },
        )
        current["reaction_count"] = int(current["reaction_count"]) + 1
        if str(row.get("selected_reaction", "")).lower() == "true" or row.get("selected_reaction") is True:
            current["selected_reaction_count"] = int(current["selected_reaction_count"]) + 1
    return sorted(grouped.values(), key=lambda row: (-int(row["reaction_count"]), str(row["group_label"])))


def build_overlay_rows(
    package: Path,
    reactions: list[dict[str, object]],
    overlay_source: str,
    variant_dir: str,
    *,
    reaction_filter: list[str] | str | None = None,
    ml_profile_id: str = "",
) -> tuple[list[dict[str, object]], str, list[dict[str, object]]]:
    semantic_type = OVERLAY_SOURCES.get(overlay_source, OVERLAY_SOURCES["none"])["semantic_type"]
    if overlay_source == "none":
        summary = build_overlay_summary_rows(
            overlay_source=overlay_source,
            semantic_type=semantic_type,
            source_file="",
            source_status="not_selected",
            matched_rows=[],
            unmatched_reactions=set(),
            missing_reason="overlay_not_selected",
        )
        return [], "not_selected", summary
    spec = OVERLAY_SOURCES[overlay_source]
    path = package / spec["path"].format(variant_dir=variant_dir, ml_profile_id=ml_profile_id)
    source_status = "available"
    missing_reason = ""
    if overlay_source == "custom_overlay" and (not path.exists() or path.stat().st_size == 0):
        source_rows = custom_overlay_rows_from_reaction_filter(reaction_filter)
        source_status = "generated_from_reaction_filter" if source_rows else "missing"
        missing_reason = "" if source_rows else "custom_overlay_missing"
    elif not path.exists() or path.stat().st_size == 0:
        source_rows = []
        source_status = "missing"
        missing_reason = f"source_file_missing:{path}"
    elif overlay_source == "production_ranking":
        source_rows, source_status, missing_reason, path = load_production_overlay_source_rows(package)
    elif overlay_source == "ml_feature_importance":
        source_rows, source_status, missing_reason, path = load_ml_feature_importance_overlay_rows(package, ml_profile_id)
    elif overlay_source == "external_ml_feature_importance":
        source_rows, source_status, missing_reason, path = load_external_ml_feature_importance_overlay_rows(package, ml_profile_id)
    else:
        source_rows = _safe_read_csv(path)
    if overlay_source == "production_ranking" and (not path.exists() or path.stat().st_size == 0):
        source_rows, source_status, missing_reason, path = load_production_overlay_source_rows(package)
    if overlay_source == "ml_feature_importance" and (not path.exists() or path.stat().st_size == 0):
        source_rows, source_status, missing_reason, path = load_ml_feature_importance_overlay_rows(package, ml_profile_id)
    if overlay_source == "external_ml_feature_importance" and (not path.exists() or path.stat().st_size == 0):
        source_rows, source_status, missing_reason, path = load_external_ml_feature_importance_overlay_rows(package, ml_profile_id)
    if not source_rows:
        summary = build_overlay_summary_rows(
            overlay_source=overlay_source,
            semantic_type=semantic_type,
            source_file=str(path),
            source_status=source_status,
            matched_rows=[],
            unmatched_reactions=set(),
            missing_reason=missing_reason or "overlay_source_empty",
        )
        return [], "overlay_missing", summary
    reaction_ids = {str(row["reaction_id"]) for row in reactions}
    cobra_ids = {str(row["cobra_reaction_id"]) for row in reactions}
    kegg_name_aliases: dict[str, tuple[str, str]] = {}
    for reaction in reactions:
        reaction_id = str(reaction.get("reaction_id", "")).strip()
        cobra_id = str(reaction.get("cobra_reaction_id", "")).strip()
        reaction_name = str(reaction.get("reaction_name", "")).strip()
        for match in re.findall(r"R\d{5}", reaction_name, flags=re.IGNORECASE):
            kegg_name_aliases.setdefault(match.upper(), (reaction_id, cobra_id))
    value_column = spec["value_column"]
    overlay_rows: list[dict[str, object]] = []
    source_reactions: set[str] = set()
    matched_source_reactions: set[str] = set()
    for row in source_rows:
        raw_reaction = (
            row.get("reaction_id")
            or row.get("model_reaction_id")
            or row.get("cobra_reaction_id")
            or row.get("model_target_id")
            or row.get("target_id")
            or ""
        )
        if not raw_reaction:
            continue
        source_reactions.add(raw_reaction)
        aliases = {raw_reaction, raw_reaction[2:] if raw_reaction.startswith("R_") else f"R_{raw_reaction}"}
        matched_reaction_id = next((alias for alias in aliases if alias in reaction_ids), "")
        matched_cobra_id = next((alias for alias in aliases if alias in cobra_ids), "")
        if not matched_reaction_id and not matched_cobra_id:
            kegg_match = re.search(r"R\d{5}", raw_reaction, flags=re.IGNORECASE)
            if kegg_match:
                matched_reaction_id, matched_cobra_id = kegg_name_aliases.get(kegg_match.group(0).upper(), ("", ""))
        if not matched_reaction_id and not matched_cobra_id:
            continue
        matched_source_reactions.add(raw_reaction)
        value = row.get(value_column, "")
        visual = overlay_visual_encoding(semantic_type, value, row)
        overlay_rows.append(
            {
                "overlay_source": overlay_source,
                "semantic_type": semantic_type,
                "condition": row.get("condition") or row.get("sample") or "",
                "reaction_id": matched_reaction_id or raw_reaction,
                "cobra_reaction_id": matched_cobra_id or (raw_reaction[2:] if raw_reaction.startswith("R_") else raw_reaction),
                "overlay_value": value,
                "overlay_value_column": value_column,
                "evidence": row.get("evidence") or row.get("status") or row.get("direction") or "",
                "status": row.get("status") or row.get("run_status") or "available",
                "overlay_color": visual["color"],
                "overlay_size": visual["size"],
                "warning_flag": visual["warning_flag"],
                "readiness_label": row.get("readiness_label") or row.get("guidance_label") or row.get("status") or "",
                "candidate_type": row.get("candidate_type") or row.get("source_role") or "",
                "candidate_action": row.get("candidate_action") or row.get("recommended_action") or row.get("target_type") or "",
                "production_score": row.get("production_score") or value,
                "product_reaction_id": row.get("product_reaction_id") or row.get("model_product_reaction_id") or "",
                "product_name": row.get("product_name") or "",
                "warning_reasons": row.get("warning_reasons") or row.get("readiness_reasons") or row.get("semantic_warning") or "",
                "source_file": row.get("source_file") or (str(path) if path.exists() else ""),
                "source_status": source_status,
            }
        )
    unmatched = source_reactions - matched_source_reactions
    overlay_status = "available" if overlay_rows else "overlay_no_matching_reactions"
    summary = build_overlay_summary_rows(
        overlay_source=overlay_source,
        semantic_type=semantic_type,
        source_file=str(path) if path.exists() else "",
        source_status=source_status if overlay_rows else "no_matching_reactions",
        matched_rows=overlay_rows,
        unmatched_reactions=unmatched,
        missing_reason="" if overlay_rows else "overlay_source_has_no_matching_model_reactions",
    )
    return overlay_rows, overlay_status, summary


def load_ml_feature_importance_overlay_rows(package: Path, ml_profile_id: str = "") -> tuple[list[dict[str, str]], str, str, Path]:
    """Load reaction-level ML feature importance overlay rows from a profile."""

    profile_root = package / "ml_hybrid_profiles"
    if ml_profile_id:
        path = profile_root / ml_profile_id / "results" / "ml_feature_importance_overlay.csv"
    else:
        path = latest_ml_profile_overlay_path(profile_root)
    if not path or not path.exists() or path.stat().st_size == 0:
        return [], "empty_guidance", "ml_profile_missing:run an ML/HYBRID profile before rendering ML Feature Importance Map", profile_root
    rows = _safe_read_csv(path)
    if not rows or not any(row.get("reaction_id") for row in rows):
        return rows, "empty_guidance", "ml_feature_importance_overlay_has_no_reaction_rows", path
    return rows, "available", "", path


def latest_ml_profile_overlay_path(profile_root: Path) -> Path:
    candidates = [
        path
        for path in profile_root.glob("*/results/ml_feature_importance_overlay.csv")
        if path.exists() and path.stat().st_size > 0
    ]
    if not candidates:
        return profile_root / "__missing__" / "results" / "ml_feature_importance_overlay.csv"
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)[0]


def load_external_ml_feature_importance_overlay_rows(package: Path, ml_profile_id: str = "") -> tuple[list[dict[str, str]], str, str, Path]:
    """Load reaction-level ML overlay rows imported from an external result folder."""

    profile_root = package / "ml_hybrid_profiles"
    if ml_profile_id:
        path = latest_external_ml_overlay_path(profile_root / ml_profile_id / "external_results")
    else:
        path = latest_external_ml_overlay_path(profile_root)
    if not path or not path.exists() or path.stat().st_size == 0:
        return (
            [],
            "empty_guidance",
            "external_ml_import_missing:import external ML feature importance before rendering External ML Feature Importance Map",
            profile_root,
        )
    rows = _safe_read_csv(path)
    if not rows or not any(row.get("reaction_id") for row in rows):
        return rows, "empty_guidance", "external_ml_feature_importance_overlay_has_no_reaction_rows", path
    return rows, "available", "", path


def latest_external_ml_overlay_path(root: Path) -> Path:
    if not root.exists():
        return root / "__missing__" / "external_ml_feature_importance_overlay.csv"
    pattern = "*/external_ml_feature_importance_overlay.csv"
    candidates = [
        path
        for path in root.glob(pattern)
        if path.exists() and path.stat().st_size > 0
    ]
    if not candidates:
        candidates = [
            path
            for path in root.glob("*/external_results/*/external_ml_feature_importance_overlay.csv")
            if path.exists() and path.stat().st_size > 0
        ]
    if not candidates:
        return root / "__missing__" / "external_ml_feature_importance_overlay.csv"
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)[0]


def load_production_overlay_source_rows(package: Path) -> tuple[list[dict[str, str]], str, str, Path]:
    """Merge production-design outputs into a single reaction overlay source."""

    production_dir = package / "production_results"
    generated_dir = package / "generated_constraints"
    uniprot_dir = package / "uniprot_model_check"
    source_paths = [
        production_dir / "production_design_targets.csv",
        production_dir / "production_design_readiness.csv",
        production_dir / "fseof_lite_reaction_targets.csv",
        production_dir / "production_target_ranking.csv",
        production_dir / "production_target_readiness.csv",
        production_dir / "fseof_reaction_targets.csv",
        uniprot_dir / "reaction_annotation_flags.csv",
        generated_dir / "kcat_conflict_flags.csv",
        package / "enzyme_results" / "enzyme_flux_capacity_check.csv",
    ]
    existing_paths = [path for path in source_paths if path.exists() and path.stat().st_size > 0]
    readiness_index = load_production_readiness_index(production_dir)
    warning_index = load_reaction_warning_index(package)
    rows: list[dict[str, str]] = []

    rows.extend(
        production_design_overlay_rows(
            production_dir / "production_design_targets.csv",
            source_role="production_design_target",
            readiness_index=readiness_index,
            warning_index=warning_index,
        )
    )
    rows.extend(
        production_design_overlay_rows(
            production_dir / "fseof_lite_reaction_targets.csv",
            source_role="fseof_lite_candidate",
            readiness_index=readiness_index,
            warning_index=warning_index,
        )
    )
    rows.extend(
        production_target_overlay_rows(
            production_dir / "production_target_ranking.csv",
            source_role="production_target",
            readiness_index=readiness_index,
            warning_index=warning_index,
        )
    )
    rows.extend(
        production_target_overlay_rows(
            production_dir / "fseof_reaction_targets.csv",
            source_role="legacy_fseof_candidate",
            readiness_index=readiness_index,
            warning_index=warning_index,
        )
    )

    if rows:
        return rows, "available", "", production_dir
    if existing_paths:
        return rows, "empty_guidance", "production_outputs_have_no_reaction_candidates", production_dir
    return rows, "empty_guidance", "production_results_missing:run Production Analysis before rendering a Production Design Map", production_dir


def production_design_overlay_rows(
    path: Path,
    *,
    source_role: str,
    readiness_index: dict[str, dict[str, str]],
    warning_index: dict[str, list[str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in _safe_read_csv(path):
        reaction_id = first_nonempty(
            row,
            ["candidate_reaction_id", "reaction_id", "model_reaction_id", "cobra_reaction_id"],
        )
        if not reaction_id:
            continue
        readiness = readiness_for_reaction(readiness_index, reaction_id)
        warning_reasons = warning_reasons_for_reaction(warning_index, reaction_id, row, readiness)
        rows.append(
            production_overlay_row(
                row,
                reaction_id=reaction_id,
                source_role=source_role,
                source_file=path,
                score=first_nonempty(row, ["intervention_score", "score", "trend_slope", "final_flux", "baseline_flux"]),
                action=first_nonempty(row, ["recommended_action", "candidate_action", "target_type"]),
                readiness=readiness,
                warning_reasons=warning_reasons,
            )
        )
    return rows


def production_target_overlay_rows(
    path: Path,
    *,
    source_role: str,
    readiness_index: dict[str, dict[str, str]],
    warning_index: dict[str, list[str]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in _safe_read_csv(path):
        reaction_id = first_nonempty(
            row,
            ["model_product_reaction_id", "product_reaction_id", "reaction_id", "model_reaction_id", "cobra_reaction_id"],
        )
        if not reaction_id:
            continue
        readiness = readiness_for_reaction(readiness_index, reaction_id)
        warning_reasons = warning_reasons_for_reaction(warning_index, reaction_id, row, readiness)
        rows.append(
            production_overlay_row(
                row,
                reaction_id=reaction_id,
                source_role=source_role,
                source_file=path,
                score=first_nonempty(
                    row,
                    [
                        "score",
                        "max_product_flux_at_half_growth",
                        "max_product_flux_at_zero_growth",
                        "max_product_flux_at_high_growth",
                    ],
                ),
                action=first_nonempty(row, ["recommended_action", "candidate_action", "target_type"]) or "production_candidate",
                readiness=readiness,
                warning_reasons=warning_reasons,
            )
        )
    return rows


def production_overlay_row(
    row: dict[str, str],
    *,
    reaction_id: str,
    source_role: str,
    source_file: Path,
    score: str,
    action: str,
    readiness: dict[str, str],
    warning_reasons: list[str],
) -> dict[str, str]:
    normalized_reaction = reaction_id if reaction_id.startswith("R_") else f"R_{reaction_id}"
    cobra_reaction = reaction_id[2:] if reaction_id.startswith("R_") else reaction_id
    readiness_label = (
        readiness.get("production_readiness_label")
        or readiness.get("readiness_label")
        or row.get("production_readiness_label")
        or row.get("readiness_label")
        or row.get("action_confidence")
        or row.get("status")
        or ""
    )
    status = row.get("filter_status") or row.get("status") or row.get("growth_coupling_label") or source_role
    return {
        **row,
        "reaction_id": normalized_reaction,
        "cobra_reaction_id": cobra_reaction,
        "score": str(score or row.get("score") or ""),
        "production_score": str(score or row.get("score") or ""),
        "candidate_type": source_role,
        "candidate_action": action or source_role,
        "recommended_action": action or row.get("recommended_action", ""),
        "readiness_label": readiness_label,
        "status": status,
        "evidence": row.get("design_guidance") or row.get("guidance") or status,
        "source_role": source_role,
        "source_file": str(source_file),
        "product_reaction_id": row.get("product_reaction_id") or row.get("model_product_reaction_id") or "",
        "product_name": row.get("product_name", ""),
        "warning_reasons": ";".join(reason for reason in warning_reasons if reason),
    }


def load_production_readiness_index(production_dir: Path) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for path in (
        production_dir / "production_design_readiness.csv",
        production_dir / "production_target_readiness.csv",
    ):
        for row in _safe_read_csv(path):
            for reaction_id in production_reaction_keys(row):
                index[reaction_id] = row
    return index


def load_reaction_warning_index(package: Path) -> dict[str, list[str]]:
    index: dict[str, list[str]] = {}
    warning_sources = [
        package / "uniprot_model_check" / "reaction_annotation_flags.csv",
        package / "generated_constraints" / "kcat_conflict_flags.csv",
        package / "enzyme_results" / "enzyme_flux_capacity_check.csv",
    ]
    for path in warning_sources:
        for row in _safe_read_csv(path):
            if not row_has_warning(row):
                continue
            message = warning_message(row, path)
            for reaction_id in production_reaction_keys(row):
                index.setdefault(reaction_id, []).append(message)
    return index


def warning_reasons_for_reaction(
    warning_index: dict[str, list[str]],
    reaction_id: str,
    row: dict[str, str],
    readiness: dict[str, str],
) -> list[str]:
    reasons: list[str] = []
    for key in reaction_aliases(reaction_id):
        reasons.extend(warning_index.get(key, []))
    for value in (
        row.get("semantic_warning", ""),
        row.get("readiness_reasons", ""),
        readiness.get("semantic_warning", ""),
        readiness.get("readiness_reasons", ""),
        readiness.get("enzyme_constraint_label", ""),
        readiness.get("kcat_conflict_label", ""),
    ):
        if value and row_has_warning({"status": value}):
            reasons.append(str(value))
    return sorted(set(reasons))


def row_has_warning(row: dict[str, str]) -> bool:
    text = " ".join(
        str(row.get(key, ""))
        for key in (
            "severity",
            "flag",
            "status",
            "semantic_warning",
            "readiness_reasons",
            "production_readiness_label",
            "enzyme_constraint_label",
            "kcat_conflict_label",
        )
    ).lower()
    return any(token in text for token in ("high", "medium", "review", "conflict", "missing", "caution", "exceeds", "block"))


def warning_message(row: dict[str, str], path: Path) -> str:
    return first_nonempty(
        row,
        ["flag", "severity", "status", "semantic_warning", "readiness_reasons", "guidance", "recommendation"],
    ) or path.stem


def readiness_for_reaction(readiness_index: dict[str, dict[str, str]], reaction_id: str) -> dict[str, str]:
    for key in reaction_aliases(reaction_id):
        if key in readiness_index:
            return readiness_index[key]
    return {}


def production_reaction_keys(row: dict[str, str]) -> set[str]:
    keys: set[str] = set()
    for value in (
        first_nonempty(
            row,
            [
                "candidate_reaction_id",
                "model_product_reaction_id",
                "product_reaction_id",
                "model_target_id",
                "target_id",
                "reaction_id",
                "model_reaction_id",
                "cobra_reaction_id",
            ],
        ),
    ):
        keys.update(reaction_aliases(value))
    return {key for key in keys if key}


def reaction_aliases(reaction_id: str) -> set[str]:
    text = str(reaction_id or "").strip()
    if not text:
        return set()
    cobra = text[2:] if text.startswith("R_") else text
    return {text, cobra, f"R_{cobra}"}


def first_nonempty(row: dict[str, str], keys: list[str]) -> str:
    for key in keys:
        value = str(row.get(key, "")).strip()
        if value:
            return value
    return ""


def overlay_visual_encoding(semantic_type: str, value: object, row: dict[str, str]) -> dict[str, object]:
    """Return stable v2-ready color/size/warning hints for overlay rows."""

    status_text = " ".join(
        str(row.get(key, ""))
        for key in (
            "evidence",
            "status",
            "severity",
            "flag",
            "readiness_label",
            "production_readiness_label",
            "candidate_action",
            "recommended_action",
            "warning_reasons",
            "semantic_warning",
            "readiness_reasons",
            "enzyme_constraint_label",
            "kcat_conflict_label",
        )
    ).lower()
    numeric = _to_float(value)
    if semantic_type == "flux":
        magnitude = abs(numeric or 0.0)
        return {
            "color": "#2563eb" if (numeric or 0.0) >= 0 else "#f97316",
            "size": round(1.0 + min(magnitude, 100.0) / 25.0, 3),
            "warning_flag": False,
        }
    if semantic_type == "warning":
        high_risk = any(token in status_text for token in ("high", "error", "conflict", "missing", "medium"))
        return {"color": "#dc2626" if high_risk else "#f59e0b", "size": 2.0 if high_risk else 1.5, "warning_flag": high_risk}
    if semantic_type == "production":
        warning = any(token in status_text for token in ("review", "conflict", "missing", "caution", "exceeds", "block"))
        action = str(row.get("candidate_action") or row.get("recommended_action") or "").upper()
        if warning:
            color = "#dc2626"
        elif action == "KO":
            color = "#ef4444"
        elif action == "KD":
            color = "#f97316"
        elif action == "OE":
            color = "#7c3aed"
        elif "target" in status_text or "production" in status_text:
            color = "#0f9f9a"
        else:
            color = "#64748b"
        magnitude = abs(numeric or 0.0)
        size = 1.4 + (min(magnitude, 1.0) * 2.4 if magnitude <= 1.0 else min(magnitude, 100.0) / 25.0)
        return {"color": color, "size": round(min(size, 5.2), 3), "warning_flag": warning}
    if semantic_type == "enzyme_capacity":
        warning = any(token in status_text for token in ("review", "conflict", "missing", "caution", "exceeds", "no_capacity"))
        magnitude = abs(numeric or 0.0)
        if warning:
            color = "#f97316"
        elif magnitude > 0:
            color = "#0f9f9a"
        else:
            color = "#94a3b8"
        if magnitude <= 0:
            size = 1.0
        elif magnitude <= 1.0:
            size = 1.4 + magnitude * 2.2
        else:
            size = 1.4 + min(4.0, (magnitude ** 0.5) / 3.0)
        return {"color": color, "size": round(min(size, 5.4), 3), "warning_flag": warning}
    if semantic_type == "ml_importance":
        warning = any(token in status_text for token in ("warning", "conflict", "missing", "caution", "failed"))
        stronger = "stronger_evidence" in status_text
        magnitude = abs(numeric or _to_float(row.get("importance_score")) or 0.0)
        color = "#dc2626" if warning else "#7c3aed" if stronger else "#0f766e"
        return {"color": row.get("overlay_color") or color, "size": round(1.0 + min(4.0, magnitude * 4.0), 3), "warning_flag": warning}
    if semantic_type == "evidence":
        if "high" in status_text or (numeric is not None and numeric > 0):
            return {"color": "#059669", "size": 1.8, "warning_flag": False}
        if "low" in status_text or (numeric is not None and numeric < 0):
            return {"color": "#d97706", "size": 1.4, "warning_flag": True}
        return {"color": "#94a3b8", "size": 1.0, "warning_flag": False}
    return {"color": row.get("overlay_color") or "#475569", "size": _to_float(row.get("overlay_size")) or 1.0, "warning_flag": _as_bool(row.get("warning_flag"))}


def custom_overlay_rows_from_reaction_filter(reaction_filter: list[str] | str | None) -> list[dict[str, str]]:
    """Build custom overlay source rows from a pasted reaction list."""

    rows = []
    for reaction_id in sorted(_normalize_reaction_filter(reaction_filter)):
        if not reaction_id.startswith("R_"):
            continue
        rows.append(
            {
                "reaction_id": reaction_id,
                "cobra_reaction_id": reaction_id[2:],
                "overlay_value": "1",
                "evidence": "custom",
                "status": "custom_selected",
                "readiness_label": "custom_selected",
            }
        )
    return rows


def build_overlay_summary_rows(
    *,
    overlay_source: str,
    semantic_type: str,
    source_file: str,
    source_status: str,
    matched_rows: list[dict[str, object]],
    unmatched_reactions: set[str],
    missing_reason: str,
) -> list[dict[str, object]]:
    """Summarize overlay matching and interpretation metadata."""

    warning_rows = [row for row in matched_rows if _as_bool(row.get("warning_flag"))]
    top_rows = sorted(
        matched_rows,
        key=lambda row: abs(_to_float(row.get("overlay_value")) or 0.0),
        reverse=True,
    )[:10]
    return [
        {
            "overlay_source": overlay_source,
            "semantic_type": semantic_type,
            "source_file": source_file,
            "source_status": source_status,
            "matched_reaction_count": len({str(row.get("reaction_id", "")) for row in matched_rows if row.get("reaction_id")}),
            "overlay_row_count": len(matched_rows),
            "unmatched_reaction_count": len(unmatched_reactions),
            "warning_count": len(warning_rows),
            "missing_reason": missing_reason,
            "top_highlighted_reactions": ";".join(str(row.get("reaction_id", "")) for row in top_rows if row.get("reaction_id")),
            "warning_reactions": ";".join(str(row.get("reaction_id", "")) for row in warning_rows if row.get("reaction_id")),
        }
    ]


def write_production_visualization_outputs(
    output: Path,
    *,
    manifest: dict[str, Any],
    overlay_rows: list[dict[str, object]],
    overlay_summary_rows: list[dict[str, object]],
    assignment_rows: list[dict[str, object]],
) -> None:
    summary_path = output / "production_visualization_summary.csv"
    manifest_path = output / "production_overlay_manifest.json"
    assignment_index = {str(row.get("reaction_id", "")): row for row in assignment_rows}
    assignment_index.update({str(row.get("cobra_reaction_id", "")): row for row in assignment_rows})
    warning_rows = [row for row in overlay_rows if _as_bool(row.get("warning_flag"))]
    top_rows = sorted(overlay_rows, key=lambda row: abs(_to_float(row.get("overlay_value")) or 0.0), reverse=True)[:10]
    action_counts = {
        action: sum(1 for row in overlay_rows if str(row.get("candidate_action", "")).upper() == action)
        for action in ("KO", "KD", "OE")
    }
    affected_subsystems = sorted(
        {
            str((assignment_index.get(str(row.get("reaction_id", ""))) or {}).get("subsystem", ""))
            for row in overlay_rows
            if (assignment_index.get(str(row.get("reaction_id", ""))) or {}).get("subsystem")
        }
    )
    overlay_summary = (overlay_summary_rows or [{}])[0]
    status = "completed" if overlay_rows else "empty_guidance"
    guidance = (
        "Production design overlay is ready for the interactive viewer."
        if overlay_rows
        else "No production ranking/design rows were available. Run Production Analysis before rendering a Production Design Map."
    )
    summary_rows = [
        {
            "variant_id": manifest.get("variant_id", ""),
            "status": status,
            "guidance": guidance,
            "overlay_status": manifest.get("overlay_status", ""),
            "candidate_count": len(overlay_rows),
            "production_candidate_count": sum(1 for row in overlay_rows if "production" in str(row.get("candidate_type", "")).lower()),
            "ko_candidate_count": action_counts["KO"],
            "kd_candidate_count": action_counts["KD"],
            "oe_candidate_count": action_counts["OE"],
            "warning_count": len(warning_rows),
            "affected_subsystems": ";".join(affected_subsystems),
            "top_candidate_reactions": ";".join(str(row.get("reaction_id", "")) for row in top_rows if row.get("reaction_id")),
            "warning_reactions": ";".join(str(row.get("reaction_id", "")) for row in warning_rows if row.get("reaction_id")),
            "missing_reason": overlay_summary.get("missing_reason", ""),
        }
    ]
    write_csv(summary_path, summary_rows)
    write_json(
        manifest_path,
        {
            "schema_version": "0.1.0",
            "status": status,
            "guidance": guidance,
            "variant_id": manifest.get("variant_id", ""),
            "overlay_source": "production_ranking",
            "overlay_status": manifest.get("overlay_status", ""),
            "summary_path": str(summary_path),
            "candidate_count": len(overlay_rows),
            "top_candidate_reactions": summary_rows[0]["top_candidate_reactions"],
            "warning_reactions": summary_rows[0]["warning_reactions"],
            "missing_reason": overlay_summary.get("missing_reason", ""),
            "source_file": overlay_summary.get("source_file", ""),
        },
    )


def build_package_json(
    *,
    package: Path,
    variant: dict[str, str],
    model_path: Path,
    grouping_mode: str,
    assignment_rows: list[dict[str, object]],
    summary_rows: list[dict[str, object]],
    overlay_rows: list[dict[str, object]],
    overlay_summary_rows: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "schema_version": "0.1.0",
        "format": "sammi_compatible_visualization_package",
        "package_dir": str(package),
        "variant_id": variant.get("variant_id", ""),
        "generation_method": variant.get("generation_method", ""),
        "model_path": str(model_path),
        "grouping_mode": grouping_mode,
        "sammi_resource_policy": sammi_resource_policy(),
        "overlay_semantic_types": sorted({str(row.get("semantic_type", "")) for row in overlay_rows if row.get("semantic_type")}),
        "reactions": assignment_rows,
        "groups": summary_rows,
        "overlays": overlay_rows,
        "overlay_summary": overlay_summary_rows,
        "notes": [
            "This is a SAMMI-compatible package generated by Omics-GEM Router.",
            "The lightweight interactive viewer remains the default; configured or vendored standalone SAMMI assets are optional.",
        ],
    }


def sammi_assets_status_rows() -> list[dict[str, object]]:
    policy = sammi_resource_policy()
    standalone_home = str(policy.get("standalone_home") or os.environ.get("SAMMI_STANDALONE_HOME", ""))
    sammim_home = os.environ.get("SAMMIM_HOME", "")
    sammipy_available = importlib.util.find_spec("sammi") is not None
    vendor = policy.get("sammi_vendor") if isinstance(policy.get("sammi_vendor"), dict) else {}
    return [
        {
            "component": "standalone_sammi",
            "available": policy["local_assets_available"],
            "status": policy["resource_strategy"],
            "detail": policy["guidance"],
            "path": standalone_home,
            "license": policy["license"],
            "resource_strategy": policy["resource_strategy"],
            "open_mode": policy["open_mode"],
        },
        {
            "component": "sammi_vendoring",
            "available": bool(vendor.get("vendored_assets_available")),
            "status": policy["vendoring_status"],
            "detail": vendor.get("message", "SAMMI standalone vendoring is optional."),
            "path": vendor.get("assets_root", ""),
            "license": policy["license"],
            "resource_strategy": policy["resource_strategy"],
            "open_mode": policy["open_mode"],
        },
        {
            "component": "sammipy_helper",
            "available": sammipy_available,
            "status": "available" if sammipy_available else "helper_missing",
            "detail": "Optional Python SAMMIpy helper; not required for v1 package generation.",
            "path": "",
            "license": "",
            "resource_strategy": "optional_helper",
            "open_mode": "not_required",
        },
        {
            "component": "sammim_runner",
            "available": bool(sammim_home and Path(sammim_home).exists()),
            "status": "configured" if sammim_home and Path(sammim_home).exists() else "optional_runner_unavailable",
            "detail": "Optional MATLAB SAMMIM runner; not required for v1 package generation.",
            "path": sammim_home,
            "license": "",
            "resource_strategy": "optional_runner",
            "open_mode": "not_required",
        },
    ]


def build_manifest(
    *,
    package: Path,
    output: Path,
    variant: dict[str, str],
    grouping_mode: str,
    overlay_source: str,
    model_path: Path | None,
    reaction_count: int,
    group_count: int,
    overlay_count: int,
    selected_reaction_count: int,
    status: str,
    message: str,
    overlay_status: str = "not_selected",
    overlay_summary_rows: list[dict[str, object]] | None = None,
    filter_preview: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = sammi_resource_policy()
    files = package_file_manifest(output)
    overlay_summary = (overlay_summary_rows or [{}])[0]
    filter_info = filter_preview or {}
    return {
        "schema_version": "0.1.0",
        "status": status,
        "message": message,
        "package_dir": str(package),
        "output_dir": str(output),
        "variant_id": variant.get("variant_id", ""),
        "generation_method": variant.get("generation_method", ""),
        "generation_status": variant.get("generation_status", ""),
        "model_path": str(model_path) if model_path else "",
        "grouping_mode": grouping_mode,
        "overlay_source": overlay_source,
        "overlay_status": overlay_status,
        "reaction_count": reaction_count,
        "group_count": group_count,
        "overlay_count": overlay_count,
        "overlay_summary_path": str(output / "overlay_summary.csv"),
        "overlay_matched_reaction_count": overlay_summary.get("matched_reaction_count", 0),
        "overlay_unmatched_reaction_count": overlay_summary.get("unmatched_reaction_count", 0),
        "overlay_warning_count": overlay_summary.get("warning_count", 0),
        "overlay_missing_reason": overlay_summary.get("missing_reason", ""),
        "overlay_source_file": overlay_summary.get("source_file", ""),
        "overlay_source_status": overlay_summary.get("source_status", ""),
        "top_highlighted_reactions": overlay_summary.get("top_highlighted_reactions", ""),
        "warning_reactions": overlay_summary.get("warning_reactions", ""),
        "selected_reaction_count": selected_reaction_count,
        "filter_status": status if status == "empty_filter" else "ok",
        "filter_has_reaction_filter": bool(filter_info.get("has_filter", False)),
        "filter_raw_reaction_ids": ";".join(str(item) for item in filter_info.get("raw_reaction_filter", []) or []),
        "filter_matched_reaction_ids": ";".join(str(item) for item in filter_info.get("matched_reaction_ids", []) or []),
        "filter_missing_reaction_ids": ";".join(str(item) for item in filter_info.get("missing_reaction_ids", []) or []),
        "filter_suggested_reactions": ";".join(
            str(item.get("reaction_id", "")) for item in filter_info.get("suggested_reactions", []) if isinstance(item, dict)
        ),
        "sammi_strategy": "standalone browser app / SAMMI-compatible package",
        "sammi_resource_policy": policy["resource_strategy"],
        "sammi_open_mode": policy["open_mode"],
        "sammi_vendoring_status": policy["vendoring_status"],
        "sammi_license": policy["license"],
        "sammi_resource_source": policy["resource_source"],
        "sammi_standalone_home": policy["standalone_home"],
        "sammi_local_index_html": policy["local_index_html"],
        "sammi_local_assets_available": policy["local_assets_available"],
        "sammi_vendor_manifest_path": policy["sammi_vendor"].get("vendor_manifest_path", "") if isinstance(policy.get("sammi_vendor"), dict) else "",
        "sammi_vendor_distribution_mode": policy["sammi_vendor"].get("distribution_mode", "") if isinstance(policy.get("sammi_vendor"), dict) else "",
        "sammi_requires_user_config": policy["requires_user_config"],
        "package_files": files,
        "requires_sammipy": False,
        "requires_sammim": False,
    }


def package_file_paths(output: Path) -> dict[str, Path]:
    return {
        "assignment": output / "subsystem_reaction_assignment.csv",
        "summary": output / "subsystem_summary.csv",
        "overlay": output / "overlay_data.csv",
        "overlay_summary": output / "overlay_summary.csv",
        "package": output / "sammi_map_package.json",
        "manifest": output / "sammi_package_manifest.json",
        "assets_status": output / "sammi_assets_status.csv",
        "readme": output / "standalone_readme.html",
        "launch": output / "sammi_launch.html",
    }


def package_file_manifest(output: Path) -> list[dict[str, str]]:
    return [
        {"role": "reaction_assignment", "file": "subsystem_reaction_assignment.csv", "path": str(output / "subsystem_reaction_assignment.csv")},
        {"role": "group_summary", "file": "subsystem_summary.csv", "path": str(output / "subsystem_summary.csv")},
        {"role": "overlay", "file": "overlay_data.csv", "path": str(output / "overlay_data.csv")},
        {"role": "overlay_summary", "file": "overlay_summary.csv", "path": str(output / "overlay_summary.csv")},
        {"role": "portable_package", "file": "sammi_map_package.json", "path": str(output / "sammi_map_package.json")},
        {"role": "manifest", "file": "sammi_package_manifest.json", "path": str(output / "sammi_package_manifest.json")},
        {"role": "assets_status", "file": "sammi_assets_status.csv", "path": str(output / "sammi_assets_status.csv")},
        {"role": "external_open_readme", "file": "standalone_readme.html", "path": str(output / "standalone_readme.html")},
        {"role": "launch_page", "file": "sammi_launch.html", "path": str(output / "sammi_launch.html")},
    ]


def write_empty_package(files: dict[str, Path], manifest: dict[str, Any]) -> None:
    write_csv(files["assignment"], [])
    write_csv(files["summary"], [])
    write_overlay_csv(files["overlay"], [])
    write_csv(files["overlay_summary"], build_overlay_summary_rows(
        overlay_source=str(manifest.get("overlay_source", "none")),
        semantic_type=OVERLAY_SOURCES.get(str(manifest.get("overlay_source", "none")), OVERLAY_SOURCES["none"])["semantic_type"],
        source_file="",
        source_status=str(manifest.get("overlay_status", "not_selected")),
        matched_rows=[],
        unmatched_reactions=set(),
        missing_reason=str(manifest.get("overlay_missing_reason", "")),
    ))
    write_json(files["package"], {"schema_version": "0.1.0", "reactions": [], "groups": [], "overlays": []})
    write_json(files["manifest"], manifest)
    write_csv(files["assets_status"], sammi_assets_status_rows())
    files["readme"].write_text(build_readme_html(manifest), encoding="utf-8")
    files["launch"].write_text(build_launch_html(manifest), encoding="utf-8")


def write_overlay_csv(path: str | Path, rows: list[dict[str, object]]) -> None:
    """Write overlay rows with a stable header even when no rows matched."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        output.write_text(",".join(OVERLAY_COLUMNS) + "\r\n", encoding="utf-8")
        return
    normalized = [{column: row.get(column, "") for column in OVERLAY_COLUMNS} for row in rows]
    write_csv(output, normalized)


def build_readme_html(manifest: dict[str, Any]) -> str:
    file_items = "\n".join(
        f'  <li><code>{item.get("file", "")}</code> - {item.get("role", "")}</li>'
        for item in manifest.get("package_files", [])
        if isinstance(item, dict)
    )
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>SAMMI package README</title></head>
<body>
<h1>SAMMI-compatible Visualization Package</h1>
<p>This package was generated by Omics-GEM Router as a local, reproducible visualization export.</p>
<ul>
  <li>Variant: <code>{manifest.get("variant_id", "")}</code></li>
  <li>Grouping mode: <code>{manifest.get("grouping_mode", "")}</code></li>
  <li>Overlay source: <code>{manifest.get("overlay_source", "")}</code> ({manifest.get("overlay_status", "")})</li>
  <li>Strategy: standalone SAMMI browser app + compatible package.</li>
  <li>Open mode: <code>{manifest.get("sammi_open_mode", "")}</code></li>
  <li>License note: standalone SAMMI is reported as <code>{manifest.get("sammi_license", "")}</code>; Omics-GEM Router does not redistribute SAMMI assets in this phase.</li>
</ul>
<h2>Package files</h2>
<ul>
{file_items}
</ul>
<h2>Open with external SAMMI</h2>
<ol>
  <li>Open the SAMMI web app or your local standalone SAMMI copy.</li>
  <li>Use <strong>Load Single SBML Model</strong> for the model listed in the manifest.</li>
  <li>Use the generated CSV/JSON package as overlay and grouping input after conversion support is added.</li>
</ol>
<p>v1 does not bundle SAMMI standalone assets. Use <code>sammi_map_package.json</code>,
<code>subsystem_reaction_assignment.csv</code>, and <code>overlay_data.csv</code> as the portable map package.</p>
</body>
</html>
"""


def build_launch_html(manifest: dict[str, Any]) -> str:
    manifest_json = json.dumps(manifest, ensure_ascii=False, indent=2)
    file_rows = "\n".join(
        f"<tr><td>{item.get('role', '')}</td><td><code>{item.get('file', '')}</code></td></tr>"
        for item in manifest.get("package_files", [])
        if isinstance(item, dict)
    )
    local_hint = (
        f"<p>Local SAMMI assets were detected at <code>{manifest.get('sammi_standalone_home', '')}</code>. "
        "This page is still a placeholder; future versions can embed the local SAMMI shell directly.</p>"
        if manifest.get("sammi_open_mode") == "local_shell_placeholder"
        else "<p>No local SAMMI assets are configured. This package uses <strong>external_open_mode</strong>.</p>"
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Open SAMMI-compatible package</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #17233b; }}
    code, pre {{ background: #f4f7fb; border-radius: 6px; padding: 2px 6px; }}
    pre {{ padding: 16px; overflow: auto; }}
  </style>
</head>
<body>
  <h1>Open with external SAMMI</h1>
  <p>Omics-GEM Router generated a SAMMI-compatible package for variant <code>{manifest.get("variant_id", "")}</code>.</p>
  <p>Grouping mode: <code>{manifest.get("grouping_mode", "")}</code>; overlay source: <code>{manifest.get("overlay_source", "")}</code> ({manifest.get("overlay_status", "")}).</p>
  {local_hint}
  <h2>Recommended steps</h2>
  <ol>
    <li>Open <a href="https://bioinformatics.mdanderson.org/Software/SAMMI/">SAMMI web app</a> or a local standalone SAMMI copy.</li>
    <li>Use <strong>Load Single SBML Model</strong> with the model path recorded in the manifest.</li>
    <li>Use <code>subsystem_reaction_assignment.csv</code> to focus the map by subsystem or selected reactions.</li>
    <li>Use <code>overlay_data.csv</code> for flux/evidence/warning/production overlays after conversion support is available.</li>
  </ol>
  <h2>Package files</h2>
  <table border="1" cellspacing="0" cellpadding="6">
    <thead><tr><th>Role</th><th>File</th></tr></thead>
    <tbody>{file_rows}</tbody>
  </table>
  <h2>Package Manifest</h2>
  <pre>{manifest_json}</pre>
</body>
</html>
"""


def _species_references(reaction: ET.Element, list_name: str) -> list[str]:
    list_node = reaction.find(f"{CORE_NS}{list_name}")
    if list_node is None:
        return []
    species: list[str] = []
    for reference in list_node.findall(f"{CORE_NS}speciesReference"):
        value = reference.attrib.get("species", "")
        if value:
            species.append(value)
    return species


def _safe_read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return read_csv_records(path)


def _normalize_reaction_filter(reaction_filter: list[str] | str | None) -> set[str]:
    if reaction_filter is None:
        return set()
    if isinstance(reaction_filter, str):
        raw_items = reaction_filter.replace(";", ",").split(",")
    else:
        raw_items = [str(item) for item in reaction_filter]
    values: set[str] = set()
    for item in raw_items:
        value = item.strip()
        if not value:
            continue
        values.add(value)
        values.add(value[2:] if value.startswith("R_") else f"R_{value}")
    return values


def _raw_filter_tokens(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        raw_items = [str(item) for item in value]
    else:
        raw_items = re.split(r"[;,\s]+", str(value))
    tokens: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        token = item.strip()
        if not token or token in seen:
            continue
        tokens.append(token)
        seen.add(token)
    return tokens


def _split_semicolon(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def _is_currency_species(species_id: str) -> bool:
    label = species_id[2:] if species_id.startswith("M_") else species_id
    base = label.rsplit("_", 1)[0] if "_" in label else label
    return base.lower() in COMMON_CURRENCY_METABOLITES


def _clean_label(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("&lt;", "<").replace("&gt;", ">")).strip(" .;:")


def _slug(value: str) -> str:
    text = value.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "unannotated"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _to_float(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"true", "1", "yes", "y", "on"}
