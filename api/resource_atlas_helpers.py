"""Pure Resource Atlas aggregation helpers.

These helpers avoid filesystem and FastAPI dependencies so services.py can keep
endpoint-facing orchestration while Resource Atlas counts stay testable.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Iterable

from api.status_semantics import resource_main_blocker, resource_readiness_class


USABLE_RESOURCE_READINESS = ("ready_for_import", "ready_for_reference", "package_ready")

DRAW_TREES_IMAGE_HINTS = {
    "ecoli_k12_mg1655": "/model-library/draw-trees/mg1665.png",
    "ecoli_w3110": "/model-library/draw-trees/w3110.png",
    "ecoli_bl21_de3": "/model-library/draw-trees/bl21de3.png",
    "ecoli_b_rel606": "/model-library/draw-trees/rel606.png",
    "shewanella_oneidensis_mr1": "",
    "saccharomyces_cerevisiae_s288c": "/model-library/draw-trees/s288c.jpg",
    "pseudomonas_putida_kt2440": "/model-library/draw-trees/kt2440.png",
    "synechocystis_pcc6803": "/model-library/draw-trees/pcc6803.png",
    "bacillus_subtilis_168": "/model-library/draw-trees/bacillus-168.png",
    "lactococcus_lactis_il1403": "/model-library/draw-trees/lactococcus-lactis.png",
    "mycobacterium_tuberculosis_h37rv": "/model-library/draw-trees/h37rv.png",
    "pseudomonas_aeruginosa_pao1": "/model-library/draw-trees/pseudomonas-aeruginosa.png",
    "salmonella_typhimurium_lt2": "/model-library/draw-trees/salmonella-enterica.png",
    "klebsiella_pneumoniae_mgh78578": "/model-library/draw-trees/klebsiella-pneumoniae.png",
    "acinetobacter_baumannii_ab5075": "/model-library/draw-trees/acinetobacter-baumannii.png",
    "helicobacter_pylori_26695": "/model-library/draw-trees/helicobacter-pylori.png",
}

CASE_STUDY_HINTS_BY_ORGANISM = {
    "shewanella_oneidensis_mr1": ["shewanella_integrated_overview"],
    "pseudomonas_putida_kt2440": ["putida_acetate_isoprenol_mixed_carbon"],
    "synechocystis_pcc6803": ["synechocystis_spkb_carbon_limitation"],
}


def canonical_resource_method_support(method: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(method).strip().lower()).strip("_")
    aliases = {
        "e_flux": "eflux",
        "gecko": "gecko_ready",
        "gecko_ready": "gecko_ready",
        "gecko_ecmodel": "gecko_ready",
        "gecko_ready_ecmodel": "gecko_ready",
        "consensus": "consensus_context",
        "consensus_context": "consensus_context",
        "model_compare": "compare_submap",
        "compare_models": "compare_submap",
        "analysis_overlay": "analysis_submap",
        "summary_evidence": "summary_evidence",
    }
    return aliases.get(normalized, normalized)


def suggested_methods_for_resource(row: dict[str, Any]) -> list[str]:
    explicit = row.get("supported_methods")
    methods: list[str] = []
    if isinstance(explicit, list):
        methods.extend([str(item) for item in explicit if str(item)])
    elif isinstance(explicit, str) and explicit.strip():
        methods.extend([item.strip() for item in re.split(r"[,;]", explicit) if item.strip()])
    omics_type = str(row.get("omics_type") or "").lower()
    readiness = str(row.get("readiness") or "").lower()
    if omics_type == "transcriptomics":
        methods.extend(["eflux", "fastcore", "consensus_context"])
    elif omics_type == "proteomics":
        methods.extend(["consensus_context", "gecko_ready"])
    elif omics_type == "kcat":
        methods.append("gecko_ready")
    elif omics_type == "annotation":
        methods.extend(["compare_submap", "analysis_submap"])
    elif omics_type == "condition":
        methods.extend(["fba_pfba", "condition_comparison"])
    if readiness in {"metadata_only", "raw_data_only", "license_or_access_limited"} and not methods:
        methods.append("manual_curation_required")
    return list(dict.fromkeys(canonical_resource_method_support(method) for method in methods if method))


def suggested_methods_for_resource_set(resources: list[dict[str, Any]]) -> list[str]:
    method_map = {
        "E-Flux": "eflux",
        "FASTcore": "fastcore",
        "Consensus Context": "consensus_evidence",
        "GECKO-ready": "enzyme_gecko",
        "gecko_ready": "enzyme_gecko",
        "Model Compare": "model_compare",
        "Analysis overlay": "analysis_visualization",
        "Summary evidence": "summary_evidence",
        "compare_submap": "model_compare",
        "analysis_submap": "analysis_visualization",
        "summary_evidence": "summary_evidence",
    }
    methods = ["baseline_gem"]
    for row in resources:
        for method in suggested_methods_for_resource(row):
            normalized = method_map.get(method, method_map.get(method.strip(), method))
            if normalized and normalized not in methods:
                methods.append(normalized)
    omics_types = {str(row.get("omics_type") or "").lower() for row in resources}
    if "transcriptomics" in omics_types:
        for method in ("eflux", "fastcore"):
            if method not in methods:
                methods.append(method)
    if {"proteomics", "kcat"} & omics_types and "consensus_evidence" not in methods:
        methods.append("consensus_evidence")
    if "proteomics" in omics_types and "kcat" in omics_types and "enzyme_gecko" not in methods:
        methods.append("enzyme_gecko")
    return methods


def count_by_values(values: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0].lower())))


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


def _count(row: dict[str, Any], key: str) -> int:
    try:
        return int(float(row.get(key) or 0))
    except (TypeError, ValueError):
        return 0


def _resource_lineage_readiness(row: dict[str, Any]) -> str:
    metadata_count = _count(row, "metadata_record_count")
    eligible_count = _count(row, "eligible_resource_count")
    readiness_classes = row.get("readiness_class_counts") if isinstance(row.get("readiness_class_counts"), dict) else {}
    needs_work = int(readiness_classes.get("needs_work") or 0)
    info_blocked = int(readiness_classes.get("info_blocked") or 0)
    if eligible_count > 0:
        return "usable"
    if needs_work > 0:
        return "needs_work"
    if metadata_count > 0 or info_blocked > 0:
        return "metadata_only"
    return "no_indexed_resources"


def _resource_lineage_image(
    organism_id: str,
    image_manifest: dict[str, Any] | None = None,
) -> tuple[str, str, str]:
    if image_manifest:
        entries = image_manifest.get("entries")
        if isinstance(entries, dict):
            entry = entries.get(organism_id)
            if isinstance(entry, dict) and entry.get("image_path"):
                status = str(entry.get("image_status") or "ready")
                return str(entry.get("image_path") or ""), status, str(entry.get("usage_note") or entry.get("source_kind") or "")
    image_path = DRAW_TREES_IMAGE_HINTS.get(organism_id, "")
    if image_path:
        return image_path, "ready", "Existing Draw_Trees-style local asset."
    return "", "missing", "No local image is currently assigned; online image curation is pending."


def _resource_lineage_node_from_species(
    row: dict[str, Any],
    *,
    parent_id: str,
    node_type: str,
    resource_ids: list[str],
    image_manifest: dict[str, Any] | None = None,
    target_source: str = "",
) -> dict[str, Any]:
    organism_id = str(row.get("organism_id") or "")
    omics_counts = row.get("omics_type_counts") if isinstance(row.get("omics_type_counts"), dict) else {}
    readiness_counts = row.get("readiness_counts") if isinstance(row.get("readiness_counts"), dict) else {}
    readiness_class_counts = row.get("readiness_class_counts") if isinstance(row.get("readiness_class_counts"), dict) else {}
    method_support_counts = row.get("method_support_counts") if isinstance(row.get("method_support_counts"), dict) else {}
    image_path, image_status, image_note = _resource_lineage_image(organism_id, image_manifest)
    readiness_class = _resource_lineage_readiness(row)
    no_resources = readiness_class == "no_indexed_resources"
    display_name = str(row.get("scientific_name") or row.get("organism_name") or organism_id)
    strain = str(row.get("strain") or "")
    return {
        "node_id": organism_id or _slug(display_name),
        "parent_id": parent_id,
        "node_type": node_type,
        "organism_id": organism_id,
        "organism_name": display_name,
        "display_name": f"{display_name} {strain}".strip(),
        "strain": strain,
        "taxon_id": str(row.get("ncbi_taxon_id") or row.get("taxon_id") or ""),
        "taxonomy_group": str(row.get("taxonomy_group") or parent_id),
        "model_count": _count(row, "model_count"),
        "transcriptomics_count": int(omics_counts.get("transcriptomics") or 0),
        "proteomics_count": int(omics_counts.get("proteomics") or 0),
        "metabolomics_count": int(omics_counts.get("metabolomics") or 0),
        "kcat_count": int(omics_counts.get("kcat") or 0),
        "annotation_count": int(omics_counts.get("annotation") or 0),
        "condition_count": int(omics_counts.get("condition") or 0),
        "omics_count": _count(row, "omics_count"),
        "metadata_record_count": _count(row, "metadata_record_count"),
        "eligible_resource_count": _count(row, "eligible_resource_count"),
        "ready_count": _count(row, "eligible_resource_count"),
        "ready_for_import_count": _count(row, "ready_for_import_count"),
        "needs_curation_count": int(readiness_class_counts.get("needs_work") or 0),
        "metadata_only_count": int(readiness_counts.get("metadata_only") or 0),
        "raw_data_only_count": int(readiness_counts.get("raw_data_only") or 0),
        "readiness_counts": readiness_counts,
        "readiness_class_counts": readiness_class_counts,
        "readiness_class": readiness_class,
        "method_support_counts": method_support_counts,
        "method_hints": sorted(method_support_counts),
        "strongest_method_hint": str(row.get("top_method_support") or ""),
        "main_blocker": "No indexed resources yet" if no_resources else str(row.get("main_blocker") or ""),
        "resource_ids": resource_ids,
        "linked_model_ids": row.get("linked_model_ids") or [],
        "aliases": row.get("aliases") or [],
        "case_study_ids": CASE_STUDY_HINTS_BY_ORGANISM.get(organism_id, []),
        "image_path": image_path,
        "image_status": image_status,
        "image_note": image_note,
        "target_source": target_source or str(row.get("source") or ""),
        "lineage_status": "indexed" if _count(row, "metadata_record_count") else "no_indexed_resources",
    }


def build_species_resource_lineage_tree(
    *,
    landscape_nodes: list[dict[str, Any]],
    target_organisms: list[dict[str, Any]],
    resources: list[dict[str, Any]],
    image_manifest: dict[str, Any] | None,
    canonical_taxonomy_group: Callable[[Any], str],
    taxonomy_label: Callable[[str], str],
) -> dict[str, Any]:
    """Build a resource-aware species lineage tree for the Atlas Deep Dive."""

    resource_ids_by_organism: dict[str, list[str]] = {}
    for resource in resources:
        organism_id = str(resource.get("organism_id") or "")
        resource_id = str(resource.get("resource_id") or "")
        if organism_id and resource_id:
            resource_ids_by_organism.setdefault(organism_id, []).append(resource_id)

    species_by_id = {str(node.get("organism_id") or ""): dict(node) for node in landscape_nodes if node.get("organism_id")}
    target_by_id = {str(row.get("organism_id") or ""): dict(row) for row in target_organisms if row.get("organism_id")}
    all_organism_ids = sorted(set(species_by_id) | set(target_by_id))
    child_nodes: list[dict[str, Any]] = []
    discovered_nodes: list[dict[str, Any]] = []

    for organism_id in all_organism_ids:
        species_row = dict(species_by_id.get(organism_id) or {})
        target_row = dict(target_by_id.get(organism_id) or {})
        if target_row:
            species_row = {
                **target_row,
                **species_row,
                "organism_id": organism_id,
                "scientific_name": species_row.get("scientific_name") or target_row.get("scientific_name"),
                "strain": species_row.get("strain") or target_row.get("strain"),
                "ncbi_taxon_id": species_row.get("ncbi_taxon_id") or target_row.get("taxon_id"),
                "taxonomy_group": species_row.get("taxonomy_group") or target_row.get("taxonomy_group"),
                "linked_model_ids": species_row.get("linked_model_ids") or target_row.get("linked_model_ids") or [],
                "aliases": species_row.get("aliases") or target_row.get("aliases") or [],
            }
        taxonomy_group = canonical_taxonomy_group(species_row.get("taxonomy_group")) or "unclassified_metadata"
        placed = organism_id in target_by_id
        node = _resource_lineage_node_from_species(
            species_row,
            parent_id=taxonomy_group if placed else "indexed_microbes",
            node_type="species" if placed else "discovered",
            resource_ids=sorted(set(resource_ids_by_organism.get(organism_id, []))),
            image_manifest=image_manifest,
            target_source=str(target_row.get("source") or ""),
        )
        if placed:
            child_nodes.append(node)
        else:
            node["lineage_status"] = "needs_lineage_placement"
            node["main_blocker"] = "Needs taxonomy placement"
            discovered_nodes.append(node)

    taxonomy_groups = sorted({str(node.get("parent_id") or "") for node in child_nodes if node.get("parent_id")})
    taxonomy_nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    all_child_nodes = [*child_nodes, *discovered_nodes]

    for taxonomy_group in taxonomy_groups:
        children = [node for node in child_nodes if node.get("parent_id") == taxonomy_group]
        taxonomy_node = {
            "node_id": taxonomy_group,
            "parent_id": "resource_lineage_root",
            "node_type": "taxonomy_group",
            "organism_id": "",
            "organism_name": taxonomy_label(taxonomy_group),
            "display_name": taxonomy_label(taxonomy_group),
            "strain": "",
            "taxon_id": "",
            "taxonomy_group": taxonomy_group,
            "model_count": sum(_count(node, "model_count") for node in children),
            "transcriptomics_count": sum(_count(node, "transcriptomics_count") for node in children),
            "proteomics_count": sum(_count(node, "proteomics_count") for node in children),
            "metabolomics_count": sum(_count(node, "metabolomics_count") for node in children),
            "kcat_count": sum(_count(node, "kcat_count") for node in children),
            "annotation_count": sum(_count(node, "annotation_count") for node in children),
            "metadata_record_count": sum(_count(node, "metadata_record_count") for node in children),
            "eligible_resource_count": sum(_count(node, "eligible_resource_count") for node in children),
            "ready_count": sum(_count(node, "ready_count") for node in children),
            "child_count": len(children),
            "readiness_class": "usable" if any(node.get("readiness_class") == "usable" for node in children) else "metadata_only",
            "image_path": "",
            "image_status": "not_applicable",
            "main_blocker": "",
        }
        taxonomy_nodes.append(taxonomy_node)
        edges.append({"source": "resource_lineage_root", "target": taxonomy_group, "edge_type": "taxonomy"})
        for child in children:
            edges.append({"source": taxonomy_group, "target": str(child.get("node_id")), "edge_type": "organism"})

    if discovered_nodes:
        taxonomy_nodes.append(
            {
                "node_id": "indexed_microbes",
                "parent_id": "resource_lineage_root",
                "node_type": "taxonomy_group",
                "organism_id": "",
                "organism_name": "Indexed microbes",
                "display_name": "Indexed microbes",
                "taxonomy_group": "indexed_microbes",
                "metadata_record_count": sum(_count(node, "metadata_record_count") for node in discovered_nodes),
                "eligible_resource_count": sum(_count(node, "eligible_resource_count") for node in discovered_nodes),
                "ready_count": sum(_count(node, "ready_count") for node in discovered_nodes),
                "child_count": len(discovered_nodes),
                "readiness_class": "metadata_only",
                "image_path": "",
                "image_status": "not_applicable",
                "main_blocker": "Needs taxonomy placement",
            }
        )
        edges.append({"source": "resource_lineage_root", "target": "indexed_microbes", "edge_type": "taxonomy"})
        for child in discovered_nodes:
            edges.append({"source": "indexed_microbes", "target": str(child.get("node_id")), "edge_type": "organism"})

    image_nodes = [node for node in all_child_nodes if node.get("image_status") in {"ready", "license_pending"}]
    placeholder_nodes = [node for node in all_child_nodes if node.get("image_status") == "placeholder"]
    missing_nodes = [node for node in all_child_nodes if node.get("image_status") == "missing"]
    summary = {
        "status": "ready",
        "node_count": len(taxonomy_nodes) + len(all_child_nodes),
        "species_node_count": len(child_nodes),
        "discovered_node_count": len(discovered_nodes),
        "no_resource_node_count": sum(1 for node in all_child_nodes if node.get("readiness_class") == "no_indexed_resources"),
        "image_ready_count": len(image_nodes),
        "image_placeholder_count": len(placeholder_nodes),
        "image_missing_count": len(missing_nodes),
        "target_count": len(target_by_id),
    }
    return {
        "nodes": [*taxonomy_nodes, *child_nodes, *discovered_nodes],
        "edges": edges,
        "unplaced_resource_organisms": discovered_nodes,
        "summary": summary,
        "image_manifest": {
            "status": "partial" if placeholder_nodes or missing_nodes else "ready",
            "source_priority": ["local Draw_Trees assets", "local case/resource assets", "curated online downloads"],
            "searched_online": bool((image_manifest or {}).get("searched_online")),
            "downloaded_online_count": int((image_manifest or {}).get("downloaded_online_count") or 0),
            "local_image_count": len(image_nodes),
            "placeholder_count": len(placeholder_nodes),
            "missing_count": len(missing_nodes),
            "manifest_path": str((image_manifest or {}).get("manifest_path") or ""),
            "guidance": (
                "Online image curation is intentionally deferred to a separate provenance-tracked download step."
                if placeholder_nodes or missing_nodes
                else "All lineage nodes currently use local assets or non-image taxonomy placeholders."
            ),
        },
    }


def build_resource_species_row(
    organism: dict[str, Any],
    organism_models: list[dict[str, Any]],
    organism_omics: list[dict[str, Any]],
    *,
    taxonomy_group: str,
    supported_methods_for_row: Callable[[dict[str, Any]], list[str]],
) -> dict[str, Any]:
    organism_resources = [*organism_models, *organism_omics]
    omics_type_counts = count_by_values(str(row.get("omics_type") or "unknown") for row in organism_omics)
    readiness_counts: dict[str, int] = {}
    readiness_class_counts = {"usable": 0, "needs_work": 0, "info_blocked": 0}
    method_support_counts: dict[str, int] = {}
    for row in organism_resources:
        readiness = str(row.get("readiness") or row.get("import_readiness") or "metadata_only")
        readiness_counts[readiness] = readiness_counts.get(readiness, 0) + 1
        readiness_class = resource_readiness_class(readiness)
        readiness_class_counts[readiness_class] = readiness_class_counts.get(readiness_class, 0) + 1
        for method in supported_methods_for_row(row):
            method_support_counts[method] = method_support_counts.get(method, 0) + 1
    eligible_resource_count = sum(readiness_counts.get(value, 0) for value in USABLE_RESOURCE_READINESS)
    top_method = ""
    if method_support_counts:
        top_method = sorted(method_support_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
    return {
        **organism,
        "taxonomy_group": taxonomy_group,
        "model_count": len(organism_models),
        "omics_count": len(organism_omics),
        "ready_for_import_count": sum(
            1 for row in organism_omics if str(row.get("readiness") or "") == "ready_for_import"
        ),
        "metadata_record_count": len(organism_resources),
        "eligible_resource_count": eligible_resource_count,
        "readiness_counts": readiness_counts,
        "readiness_class_counts": readiness_class_counts,
        "method_support_counts": method_support_counts,
        "top_method_support": top_method,
        "main_blocker": resource_main_blocker(readiness_counts),
        "omics_type_counts": omics_type_counts,
    }


def build_landscape_clusters(
    landscape_nodes: list[dict[str, Any]],
    *,
    canonical_taxonomy_group: Callable[[Any], str],
    taxonomy_label: Callable[[str], str],
) -> list[dict[str, Any]]:
    cluster_rows: dict[str, dict[str, Any]] = {}
    for node in landscape_nodes:
        taxonomy_group = (
            canonical_taxonomy_group(node.get("taxonomy_group") or node.get("domain"))
            or "unclassified_metadata"
        )
        cluster = cluster_rows.setdefault(
            taxonomy_group,
            {
                "id": taxonomy_group,
                "label": taxonomy_label(taxonomy_group),
                "node_count": 0,
                "metadata_record_count": 0,
                "eligible_resource_count": 0,
            },
        )
        cluster["node_count"] = int(cluster.get("node_count") or 0) + 1
        cluster["metadata_record_count"] = int(cluster.get("metadata_record_count") or 0) + int(
            node.get("metadata_record_count") or 0
        )
        cluster["eligible_resource_count"] = int(cluster.get("eligible_resource_count") or 0) + int(
            node.get("eligible_resource_count") or 0
        )
    return sorted(cluster_rows.values(), key=lambda row: (-int(row.get("eligible_resource_count") or 0), str(row.get("label") or "")))


def normalize_resource_search_pagination(
    limit: int,
    offset: int,
    *,
    default_limit: int = 100,
    max_limit: int = 500,
) -> tuple[int, int]:
    if limit < 1:
        limit = default_limit
    if limit > max_limit:
        limit = max_limit
    if offset < 0:
        offset = 0
    return limit, offset


def build_resource_search_payload(
    row: dict[str, Any],
    resource_kind: str,
    *,
    taxonomy_group: str,
    supported_methods: list[str],
) -> dict[str, Any]:
    payload = {**row, "resource_kind": resource_kind}
    payload["taxonomy_group"] = taxonomy_group
    payload["supported_methods"] = supported_methods
    return payload


def build_resource_search_facets(resources: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    def facet_counts(field: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in resources:
            values: list[str]
            if field == "method_support":
                values = [str(value) for value in row.get("supported_methods") or [] if str(value)]
            else:
                raw_value = row.get(field)
                values = [str(raw_value)] if raw_value else []
            for value in values:
                if not value:
                    continue
                counts[value] = counts.get(value, 0) + 1
        return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0].lower())))

    return {
        "resource_kind": facet_counts("resource_kind"),
        "omics_type": facet_counts("omics_type"),
        "source_database": facet_counts("source_database"),
        "connector_source": facet_counts("connector_source"),
        "readiness": facet_counts("readiness"),
        "taxonomy_group": facet_counts("taxonomy_group"),
        "method_support": facet_counts("method_support"),
    }


def build_resource_search_response(
    *,
    index: dict[str, Any],
    query: dict[str, str],
    species: list[dict[str, Any]],
    raw_resources: list[dict[str, Any]],
    resources: list[dict[str, Any]],
    deduplication_summary: dict[str, Any],
    limit: int,
    offset: int,
    coverage_by_source: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    total_count = len(resources)
    paged_resources = resources[offset:offset + limit]
    paged_models = [row for row in paged_resources if row.get("resource_kind") == "model"]
    paged_omics_rows = [row for row in paged_resources if row.get("resource_kind") == "omics"]
    return {
        "status": index.get("status", "ready"),
        "query": {**query, "limit": str(limit), "offset": str(offset)},
        "species": species,
        "models": paged_models,
        "omics_resources": paged_omics_rows,
        "resources": paged_resources,
        "count": total_count,
        "total_count": total_count,
        "raw_count": len(raw_resources),
        "deduplicated_count": total_count,
        "deduplication_summary": deduplication_summary,
        "returned_count": len(paged_resources),
        "limit": limit,
        "offset": offset,
        "facets": build_resource_search_facets(resources),
        "coverage_by_source": coverage_by_source,
        "guidance": index.get("guidance", ""),
        "cache_manifest": index.get("cache_manifest", {}),
        "cache_status": index.get("cache_status", {}),
    }


def build_resource_detail_response(
    *,
    index: dict[str, Any],
    resource_kind: str,
    resource: dict[str, Any],
    organism: dict[str, Any],
    suggested_methods: list[str],
    guidance: str = "",
) -> dict[str, Any]:
    return {
        "status": index.get("status", "ready"),
        "resource_kind": resource_kind,
        "resource": resource,
        "organism": organism,
        "suggested_methods": suggested_methods,
        "guidance": guidance or index.get("guidance", ""),
    }


def build_resource_atlas_summary_response(
    *,
    index: dict[str, Any],
    model_resources: list[dict[str, Any]],
    omics_resources: list[dict[str, Any]],
    raw_resources: list[dict[str, Any]],
    resources: list[dict[str, Any]],
    deduplication_summary: dict[str, Any],
    organisms: list[dict[str, Any]],
    manifest: dict[str, Any],
    coverage_by_source: dict[str, dict[str, Any]],
    landscape_nodes: list[dict[str, Any]],
    landscape_clusters: list[dict[str, Any]],
    lineage_tree_resource_nodes: list[dict[str, Any]] | None,
    lineage_tree_resource_edges: list[dict[str, Any]] | None,
    unplaced_resource_organisms: list[dict[str, Any]] | None,
    lineage_tree_summary: dict[str, Any] | None,
    lineage_tree_image_manifest: dict[str, Any] | None,
    taxonomy_group_for_row: Callable[[dict[str, Any]], str],
    supported_methods_for_row: Callable[[dict[str, Any]], list[str]],
    readiness_class_for_value: Callable[[str], str],
) -> dict[str, Any]:
    source_breakdown = count_by_values(str(row.get("source_database") or "") for row in resources)
    connector_breakdown = count_by_values(str(row.get("connector_source") or "") for row in resources)
    return {
        "status": index.get("status", "ready"),
        "total_records": len(resources),
        "raw_records": len(raw_resources),
        "deduplicated_records": len(resources),
        "deduplication_summary": deduplication_summary,
        "model_records": len(model_resources),
        "omics_records": len(omics_resources),
        "source_count": len(source_breakdown),
        "connector_count": len(connector_breakdown),
        "unique_organisms": len({str(row.get("organism_id") or "") for row in organisms if row.get("organism_id")}),
        "unique_taxa": len(
            {
                str(row.get("ncbi_taxon_id") or row.get("taxon_id") or "")
                for row in organisms
                if row.get("ncbi_taxon_id") or row.get("taxon_id")
            }
        ),
        "taxonomy_breakdown": count_by_values(taxonomy_group_for_row(row) for row in resources),
        "source_breakdown": source_breakdown,
        "connector_breakdown": connector_breakdown,
        "omics_breakdown": count_by_values(str(row.get("omics_type") or "") for row in resources),
        "readiness_breakdown": count_by_values(str(row.get("readiness") or "") for row in resources),
        "method_support_breakdown": count_by_values(
            method for row in resources for method in supported_methods_for_row(row)
        ),
        "landscape_clusters": landscape_clusters,
        "landscape_nodes": landscape_nodes,
        "lineage_tree_resource_nodes": lineage_tree_resource_nodes or [],
        "lineage_tree_resource_edges": lineage_tree_resource_edges or [],
        "unplaced_resource_organisms": unplaced_resource_organisms or [],
        "lineage_tree_summary": lineage_tree_summary or {},
        "lineage_tree_image_manifest": lineage_tree_image_manifest or {},
        "readiness_class_counts": count_by_values(
            readiness_class_for_value(str(row.get("readiness") or "")) for row in resources
        ),
        "evidence_type_counts": count_by_values(str(row.get("omics_type") or "model") for row in resources),
        "coverage_by_source": coverage_by_source,
        "cache_status": index.get("cache_status", {}),
        "cache_manifest": manifest,
        "guidance": index.get("guidance", ""),
    }
