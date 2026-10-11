"""Service helpers for the Omics-GEM FastAPI prototype.

This module deliberately avoids importing FastAPI so it can be unit-tested and
reused by Streamlit, React, or Electron wrappers.
"""

from __future__ import annotations

import csv
import html
import io
import importlib.metadata
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from omics_router.local_config import apply_local_backend_env, load_local_backend_config, save_local_backend_config
from omics_router.gecko_adapter import build_gecko_adapter_files, run_gecko_adapter_probe
from omics_router.gecko_runner import run_shewanella_gecko_external_workflow, validate_gecko_package
from omics_router.ml_hybrid_profile import (
    compare_ml_hybrid_profiles,
    export_ml_hybrid_profile,
    get_ml_hybrid_external_result_detail,
    get_ml_hybrid_profile_detail,
    import_ml_hybrid_external_results,
    list_ml_hybrid_external_results,
    list_ml_hybrid_profile_exports,
    list_ml_hybrid_profiles,
    run_ml_hybrid_profile,
)
from omics_router.model_generation import (
    read_model_variant_registry,
    safe_variant_dir_name,
    workflow_parameter_preview,
    workflow_parameter_schema,
)
from omics_router.model_edit import (
    build_model_edit_diff_index,
    edit_context_summary,
    overlay_edit_graph,
    read_model_edit_reaction_index,
    refresh_model_edit_artifacts_for_package,
)
from omics_router.report_builder import build_report_bundle
from omics_router.sammi_interactive_render import build_sammi_interactive_render
from omics_router.sammi_native_export import build_sammi_native_export, list_sammi_native_exports
from omics_router.sammi_visualization import (
    build_sammi_visualization_package,
    list_sammi_model_reactions,
    preview_sammi_filter,
    sammi_vendor_status,
)
from omics_router.upload_workflow import (
    IGNORE_ROLE,
    UploadFilePayload,
    choose_default_role,
    stage_user_run_package,
)
from omics_router.user_pipeline import run_user_package_minimal
from omics_router.validators import EXPECTED_COLUMNS, inspect_model_filename, inspect_table_file
from omics_router.variant_comparison import _compare_model_structures, _parse_model_structure, _reaction_diff_rows, _reaction_functional_group
from api.case_study_helpers import (
    CASE_QA_STAGE_CHECKS,
    build_case_prepare_lite_log_payload,
    build_case_prepare_lite_missing_package_response,
    build_case_prepare_lite_response,
    build_case_prepare_preview_actions,
    build_case_prepare_preview_log_payload,
    build_case_prepare_preview_response,
    build_case_qa_matrix_response,
    build_missing_case_readiness_payload,
    build_case_readiness_stage_rows,
    case_check,
    case_check_map,
)
from api.compare_semantics import case_compare_guidance, compare_readiness_summary
from api.file_artifact_helpers import (
    build_file_summary,
    collect_json_artifacts,
    is_relative_to_path,
    list_relative_files,
    preview_table_rows,
    resolve_safe_file_path,
    safe_relative_path,
)
from api.resource_atlas_helpers import (
    build_resource_detail_response,
    build_landscape_clusters,
    build_resource_atlas_summary_response,
    build_resource_search_payload,
    build_resource_search_response,
    build_species_resource_lineage_tree,
    canonical_resource_method_support,
    build_resource_species_row,
    count_by_values,
    normalize_resource_search_pagination,
    resource_main_blocker,
    resource_readiness_class,
    suggested_methods_for_resource,
    suggested_methods_for_resource_set,
)
from api.resource_curation_helpers import (
    build_resource_curation_template_response,
    preview_resource_curation_file,
)
from api.resource_curation_workspace import (
    AddCuratedFile as CurationAddCuratedFile,
    CreateWorkspace as CreateCurationWorkspace,
    GetWorkspace as GetCurationWorkspace,
    ListWorkspaces as ListCurationWorkspaces,
    PreviewMapping as PreviewCurationMapping,
    ResourceCurationWorkspaceConfig,
    ResourceCurationWorkspaceError,
    ResourceCurationWorkspaces,
    StageRunPackage as StageCurationRunPackage,
)
from api.run_package_helpers import (
    build_already_available_import_result,
    build_archive_manifest_payload,
    build_archive_run_result,
    build_archived_manifest_response,
    build_archived_run_overview,
    build_import_manifest_payload,
    build_import_manifest_response,
    build_import_run_result,
    build_restore_manifest_payload,
    build_restore_run_result,
    build_run_package_candidate,
    build_run_package_job_header_lines,
    build_run_package_job_result_lines,
    discover_run_package_paths,
    find_run_model_path,
    list_known_run_packages,
    looks_like_run_package,
    next_available_run_id,
    read_model_id_from_gecko_manifest,
    sanitize_run_id,
    same_path,
    safe_run_overview,
)
from api.run_package_resolver import resolve_run_package_context
from api.status_semantics import support_status
from api.workspace_helpers import (
    build_project_row,
    build_workspace_config_payload,
    build_workspace_status_payload,
    resolve_directory_candidate_path,
)


ROOT = Path(__file__).resolve().parents[1]
APP_ROOT = ROOT
WORKSPACE_CONFIG_PATH = APP_ROOT / "api_workspace_config.json"
WORKSPACE_ROOT = APP_ROOT
USER_RUNS_DIR = WORKSPACE_ROOT / "user_runs"
EXAMPLES_DIR = WORKSPACE_ROOT / "examples"
TASK_LOGS_DIR = WORKSPACE_ROOT / "task_logs"
ATLAS_CURATION_WORKSPACES_DIR = WORKSPACE_ROOT / "atlas_curation_workspaces"
ALLOWED_FILE_ROOTS = (WORKSPACE_ROOT, APP_ROOT)
RESOURCE_INDEX_PATH = APP_ROOT / "resources" / "resource_index.json"
RESOURCE_ORGANISM_TARGETS_PATH = APP_ROOT / "resources" / "organism_targets.csv"
RESOURCE_LINEAGE_IMAGE_MANIFEST_PATH = APP_ROOT / "resources" / "lineage_tree_images" / "image_manifest.json"
RESOURCE_CACHE_ROOT = APP_ROOT / "resources" / "cached_search"
RESOURCE_CACHE_MANIFEST_PATH = RESOURCE_CACHE_ROOT / "cache_manifest.json"
RESOURCE_TARGET_CANDIDATE_REPORT_PATH = RESOURCE_CACHE_ROOT / "resource_target_candidates.json"
CASE_DISPLAY_MANIFEST_PATH = APP_ROOT / "resources" / "case_display_manifest.json"
RESOURCE_CONNECTOR_CACHE_FILES: tuple[tuple[str, Path], ...] = (
    ("bigg_cache", RESOURCE_CACHE_ROOT / "bigg" / "models.json"),
    ("geo_cache", RESOURCE_CACHE_ROOT / "geo" / "series.json"),
    ("expression_atlas_cache", RESOURCE_CACHE_ROOT / "expression_atlas" / "studies.json"),
    ("pride_cache", RESOURCE_CACHE_ROOT / "pride" / "datasets.json"),
    ("metabolights_cache", RESOURCE_CACHE_ROOT / "metabolights" / "studies.json"),
    ("omicsdi_cache", RESOURCE_CACHE_ROOT / "omicsdi" / "datasets.json"),
)

apply_local_backend_env()


@dataclass(slots=True)
class ApiError(Exception):
    """Structured service error that routes can convert to HTTP responses."""

    status_code: int
    detail: str


def api_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "omics-gem-router-api",
        "app_root": str(APP_ROOT),
        "root": str(WORKSPACE_ROOT),
        "workspace_root": str(WORKSPACE_ROOT),
        "user_runs_dir": str(USER_RUNS_DIR),
    }


def resource_species() -> dict[str, Any]:
    return _resource_species_from_index(load_resource_index())


def _read_resource_organism_targets() -> list[dict[str, Any]]:
    if not RESOURCE_ORGANISM_TARGETS_PATH.exists():
        return []
    targets: list[dict[str, Any]] = []
    try:
        with RESOURCE_ORGANISM_TARGETS_PATH.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if str(row.get("enabled") or "").strip().lower() in {"false", "0", "no"}:
                    continue
                aliases = [value.strip() for value in str(row.get("aliases") or "").split(";") if value.strip()]
                linked_model_ids = [value.strip() for value in str(row.get("model_ids") or "").split(";") if value.strip()]
                targets.append(
                    {
                        "organism_id": str(row.get("organism_id") or "").strip(),
                        "scientific_name": str(row.get("scientific_name") or "").strip(),
                        "strain": str(row.get("strain") or "").strip(),
                        "taxon_id": str(row.get("taxon_id") or "").strip(),
                        "ncbi_taxon_id": str(row.get("taxon_id") or "").strip(),
                        "aliases": aliases,
                        "taxonomy_group": _resource_canonical_taxonomy_group(row.get("taxonomy_group")) or "unclassified_metadata",
                        "linked_model_ids": linked_model_ids,
                        "priority_tier": str(row.get("priority_tier") or "").strip(),
                        "source": str(row.get("source") or "").strip(),
                    }
                )
    except (OSError, csv.Error):
        return []
    return [row for row in targets if row.get("organism_id")]


def _read_resource_lineage_image_manifest() -> dict[str, Any]:
    if not RESOURCE_LINEAGE_IMAGE_MANIFEST_PATH.exists():
        return {}
    try:
        payload = json.loads(RESOURCE_LINEAGE_IMAGE_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "partial", "entries": {}, "guidance": "Image manifest could not be read."}
    if isinstance(payload, dict):
        payload.setdefault("manifest_path", str(RESOURCE_LINEAGE_IMAGE_MANIFEST_PATH))
        return payload
    return {}


def _resource_species_from_index(index: dict[str, Any]) -> dict[str, Any]:
    organisms = list(index.get("organisms") or [])
    model_resources = _resource_records(index, "model_resources")
    omics_resources = _resource_records(index, "omics_resources")
    species_rows: list[dict[str, Any]] = []
    for organism in organisms:
        organism_id = str(organism.get("organism_id") or "")
        organism_models = [row for row in model_resources if str(row.get("organism_id") or "") == organism_id]
        organism_omics = [row for row in omics_resources if str(row.get("organism_id") or "") == organism_id]
        taxonomy_group = _resource_organism_taxonomy_group(organism, index)
        species_rows.append(
            build_resource_species_row(
                organism,
                organism_models,
                organism_omics,
                taxonomy_group=taxonomy_group,
                supported_methods_for_row=_resource_supported_methods,
            )
        )
    return {
        "status": index.get("status", "ready"),
        "species": species_rows,
        "guidance": index.get("guidance", ""),
        "index_path": str(RESOURCE_INDEX_PATH),
    }


def resource_search(
    organism: str = "",
    model_id: str = "",
    omics_type: str = "",
    source_database: str = "",
    readiness: str = "",
    taxonomy_group: str = "",
    method_support: str = "",
    taxon_id: str = "",
    accession: str = "",
    q: str = "",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    index = load_resource_index()
    organisms = list(index.get("organisms") or [])
    model_resources = _resource_records(index, "model_resources")
    omics_resources = _resource_records(index, "omics_resources")
    organism_query = organism.strip()
    matching_organism_ids = _matching_organism_ids(organisms, organism_query)
    model_query = model_id.strip().lower()
    omics_query = omics_type.strip().lower()
    source_query = source_database.strip().lower()
    readiness_query = readiness.strip().lower()
    taxonomy_query = taxonomy_group.strip().lower()
    method_query = canonical_resource_method_support(method_support) if method_support.strip() else ""
    taxon_query = taxon_id.strip().lower()
    accession_query = accession.strip().lower()
    text_query = q.strip().lower()

    def organism_ok(row: dict[str, Any]) -> bool:
        return not organism_query or str(row.get("organism_id") or "") in matching_organism_ids

    def taxon_ok(row: dict[str, Any]) -> bool:
        if not taxon_query:
            return True
        row_taxon = str(row.get("taxon_id") or "").lower()
        organism_row = _organism_by_id(index, str(row.get("organism_id") or ""))
        organism_taxon = str(organism_row.get("ncbi_taxon_id") or "").lower()
        return taxon_query in row_taxon or taxon_query in organism_taxon

    def model_ok(row: dict[str, Any]) -> bool:
        if not model_query:
            return True
        return model_query in " ".join(
            [
                str(row.get("model_id") or ""),
                str(row.get("model_name") or ""),
                str(row.get("resource_id") or ""),
            ]
        ).lower()

    def source_ok(row: dict[str, Any]) -> bool:
        return not source_query or source_query in " ".join(
            [
                str(row.get("source_database") or ""),
                str(row.get("connector_source") or ""),
            ]
        ).lower()

    def readiness_ok(row: dict[str, Any]) -> bool:
        if not readiness_query:
            return True
        readiness_value = str(row.get("readiness") or row.get("import_readiness") or "").lower()
        if readiness_query in {"usable", "needs_work", "info_blocked"}:
            return _resource_readiness_class(readiness_value) == readiness_query
        return readiness_query == readiness_value

    def taxonomy_ok(row: dict[str, Any]) -> bool:
        if not taxonomy_query:
            return True
        return taxonomy_query == _resource_taxonomy_group(row, index).lower()

    def method_ok(row: dict[str, Any]) -> bool:
        if not method_query:
            return True
        return method_query in {item.lower() for item in _resource_supported_methods(row)}

    def accession_ok(row: dict[str, Any]) -> bool:
        if not accession_query:
            return True
        return accession_query in " ".join(
            [
                str(row.get("accession") or ""),
                str(row.get("model_id") or ""),
                str(row.get("resource_id") or ""),
            ]
        ).lower()

    def text_ok(row: dict[str, Any]) -> bool:
        return not text_query or text_query in _resource_search_text(row, index)

    limit, offset = normalize_resource_search_pagination(limit, offset)
    model_filter_requested = omics_query in {"model", "models"}
    omics_filter = "" if model_filter_requested else omics_query

    models = [
        row
        for row in model_resources
        if organism_ok(row)
        and taxon_ok(row)
        and model_ok(row)
        and source_ok(row)
        and readiness_ok(row)
        and taxonomy_ok(row)
        and method_ok(row)
        and accession_ok(row)
        and text_ok(row)
        and (not omics_query or model_filter_requested)
    ]
    omics_rows = [
        row
        for row in omics_resources
        if organism_ok(row)
        and taxon_ok(row)
        and (not model_query or model_query in str(row.get("model_id") or row.get("linked_model_id") or row.get("resource_id") or "").lower())
        and not model_filter_requested
        and (not omics_filter or omics_filter == str(row.get("omics_type") or "").lower())
        and source_ok(row)
        and readiness_ok(row)
        and taxonomy_ok(row)
        and method_ok(row)
        and accession_ok(row)
        and text_ok(row)
    ]
    raw_resources = [
        build_resource_search_payload(
            row,
            "model",
            taxonomy_group=_resource_taxonomy_group(row, index),
            supported_methods=_resource_supported_methods(row),
        )
        for row in models
    ] + [
        build_resource_search_payload(
            row,
            "omics",
            taxonomy_group=_resource_taxonomy_group(row, index),
            supported_methods=_resource_supported_methods(row),
        )
        for row in omics_rows
    ]
    all_resources = _deduplicate_resource_payloads(raw_resources)
    deduplication_summary = _resource_deduplication_summary(raw_resources, all_resources)
    return build_resource_search_response(
        index=index,
        query={
            "organism": organism,
            "model_id": model_id,
            "omics_type": omics_type,
            "source_database": source_database,
            "readiness": readiness,
            "taxonomy_group": taxonomy_group,
            "method_support": method_support,
            "taxon_id": taxon_id,
            "accession": accession,
            "q": q,
        },
        species=[row for row in organisms if not organism_query or str(row.get("organism_id") or "") in matching_organism_ids],
        raw_resources=raw_resources,
        resources=all_resources,
        deduplication_summary=deduplication_summary,
        limit=limit,
        offset=offset,
        coverage_by_source=_resource_coverage_by_source(index),
    )


def _deduplicate_resource_payloads(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    by_canonical: dict[str, dict[str, Any]] = {}
    for row in rows:
        canonical_id = str(row.get("canonical_resource_id") or row.get("resource_id") or "")
        if not canonical_id or canonical_id not in by_canonical:
            by_canonical[canonical_id] = row
            deduped.append(row)
            continue
        existing = by_canonical[canonical_id]
        replace_base = _resource_merge_rank(row) > _resource_merge_rank(existing)
        existing_links = existing.get("source_links") if isinstance(existing.get("source_links"), list) else []
        row_links = row.get("source_links") if isinstance(row.get("source_links"), list) else []
        merged_links = list(existing_links)
        seen_links = {
            (
                str(link.get("source_database") or ""),
                str(link.get("accession") or ""),
                str(link.get("external_url") or ""),
            )
            for link in merged_links
            if isinstance(link, dict)
        }
        for link in row_links:
            if not isinstance(link, dict):
                continue
            key_tuple = (
                str(link.get("source_database") or ""),
                str(link.get("accession") or ""),
                str(link.get("external_url") or ""),
            )
            if key_tuple in seen_links:
                continue
            seen_links.add(key_tuple)
            merged_links.append(link)
        cross_ids = _resource_cross_source_ids_from_rows([existing, row], merged_links)
        merged_methods = _merge_resource_string_lists(existing, row, "supported_methods")
        merged_condition_keywords = _merge_resource_string_lists(existing, row, "condition_keywords")
        if replace_base:
            existing.clear()
            existing.update(row)
        existing["source_links"] = merged_links
        existing["cross_source_ids"] = cross_ids
        if merged_methods:
            existing["supported_methods"] = merged_methods
        if merged_condition_keywords:
            existing["condition_keywords"] = merged_condition_keywords
        existing["duplicate_group_size"] = max(
            int(existing.get("duplicate_group_size") or 1),
            int(row.get("duplicate_group_size") or 1),
            len(merged_links) or len(cross_ids) or 1,
        )
    return deduped


def _resource_merge_rank(row: dict[str, Any]) -> tuple[int, int, int]:
    readiness = str(row.get("readiness") or row.get("import_readiness") or "").lower()
    readiness_rank = {
        "ready_for_import": 60,
        "ready_for_reference": 55,
        "needs_condition_curation": 40,
        "needs_gene_mapping": 40,
        "manual_curation_required": 30,
        "metadata_only": 20,
        "raw_data_only": 10,
        "license_or_access_limited": 5,
    }.get(readiness, 0)
    local_rank = 10 if str(row.get("local_path") or "") else 0
    link_rank = len(row.get("source_links") or []) if isinstance(row.get("source_links"), list) else 0
    return readiness_rank, local_rank, link_rank


def _merge_resource_string_lists(left: dict[str, Any], right: dict[str, Any], field: str) -> list[str]:
    values: list[str] = []
    for row in (left, right):
        raw_values = row.get(field)
        if not isinstance(raw_values, list):
            continue
        for item in raw_values:
            text = str(item)
            if text and text not in values:
                values.append(text)
    return values


def _resource_cross_source_ids_from_rows(rows: list[dict[str, Any]], links: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []

    def add(value: Any) -> None:
        text = str(value or "")
        if text and text not in values:
            values.append(text)

    for row in rows:
        add(row.get("resource_id"))
        add(row.get("accession"))
        add(row.get("model_id"))
        for token in _resource_accession_tokens(row):
            add(token)
        if isinstance(row.get("cross_source_ids"), list):
            for item in row.get("cross_source_ids") or []:
                add(item)
    for link in links:
        if not isinstance(link, dict):
            continue
        add(link.get("resource_id"))
        add(link.get("accession"))
        for token in str(link.get("canonical_tokens") or "").split(";"):
            add(token)
    return values


def _resource_deduplication_summary(raw_rows: list[dict[str, Any]], deduped_rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in raw_rows:
        canonical_id = str(row.get("canonical_resource_id") or row.get("resource_id") or "")
        if not canonical_id:
            continue
        groups.setdefault(canonical_id, []).append(row)
    duplicate_groups = [
        {
            "canonical_resource_id": canonical_id,
            "duplicate_group_size": len(group_rows),
            "resource_ids": [str(row.get("resource_id") or "") for row in group_rows if str(row.get("resource_id") or "")],
            "source_databases": sorted({str(row.get("source_database") or "") for row in group_rows if str(row.get("source_database") or "")}),
            "connector_sources": sorted({str(row.get("connector_source") or "") for row in group_rows if str(row.get("connector_source") or "")}),
            "accessions": sorted({str(row.get("accession") or row.get("model_id") or "") for row in group_rows if str(row.get("accession") or row.get("model_id") or "")}),
            "canonical_tokens": sorted({token for row in group_rows for token in _resource_accession_tokens(row)}),
        }
        for canonical_id, group_rows in groups.items()
        if len(group_rows) > 1
    ]
    duplicate_groups.sort(key=lambda row: (-int(row.get("duplicate_group_size") or 0), str(row.get("canonical_resource_id") or "")))
    cross_source_group_count = sum(
        1 for row in duplicate_groups
        if len(row.get("source_databases") or []) > 1 or len(row.get("connector_sources") or []) > 1
    )
    return {
        "raw_records": len(raw_rows),
        "deduplicated_records": len(deduped_rows),
        "canonical_group_count": len(groups),
        "duplicate_group_count": len(duplicate_groups),
        "cross_source_group_count": cross_source_group_count,
        "duplicate_resource_count": max(0, len(raw_rows) - len(deduped_rows)),
        "top_duplicate_groups": duplicate_groups[:12],
        "guidance": "Resources sharing a canonical model/accession key are merged at query time while preserving source_links and cross_source_ids.",
    }


def _resource_coverage_by_source(index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    manifest = index.get("cache_manifest") if isinstance(index.get("cache_manifest"), dict) else {}
    sources = manifest.get("sources") if isinstance(manifest.get("sources"), dict) else {}
    live_smoke_rows = manifest.get("live_smoke_report_rows") if isinstance(manifest.get("live_smoke_report_rows"), list) else []
    live_smoke_by_source = {
        str(row.get("connector_source") or row.get("source") or ""): row
        for row in live_smoke_rows
        if isinstance(row, dict)
    }
    coverage_by_source: dict[str, dict[str, Any]] = {}
    for source_name, source_payload in sources.items():
        if not isinstance(source_payload, dict):
            continue
        live_smoke = live_smoke_by_source.get(str(source_name), {})
        reported_hits = source_payload.get("reported_hits", source_payload.get("source_reported_total", 0))
        harvested_count = source_payload.get(
            "harvested_records",
            source_payload.get("harvested_count", source_payload.get("record_count", 0)),
        )
        coverage_by_source[str(source_name)] = {
            "status": source_payload.get("status", source_payload.get("cache_status", "")),
            "cache_status": source_payload.get("cache_status", source_payload.get("status", "")),
            "source_database": source_payload.get("source_database", ""),
            "resource_kinds": source_payload.get("resource_kinds", []),
            "omics_types": source_payload.get("omics_types", []),
            "query_modes": source_payload.get("query_modes", []),
            "live_connector": source_payload.get("live_connector", False),
            "cached_connector": source_payload.get("cached_connector", True),
            "supports_pagination": source_payload.get("supports_pagination", False),
            "default_limit": source_payload.get("default_limit", 0),
            "default_page_size": source_payload.get("default_page_size", 0),
            "default_max_pages": source_payload.get("default_max_pages", 0),
            "effective_limit": source_payload.get("effective_limit", 0),
            "effective_page_size": source_payload.get("effective_page_size", 0),
            "effective_max_pages": source_payload.get("effective_max_pages", 0),
            "readiness_default": source_payload.get("readiness_default", ""),
            "data_level": source_payload.get("data_level", ""),
            "safety_boundaries": source_payload.get("safety_boundaries", []),
            "query_theme_count": source_payload.get("query_theme_count", 0),
            "query_theme_omics_types": source_payload.get("query_theme_omics_types", []),
            "query_theme_suffixes": source_payload.get("query_theme_suffixes", []),
            "reported_hits": reported_hits,
            "source_reported_total": source_payload.get("source_reported_total", reported_hits),
            "harvested_records": harvested_count,
            "harvested_count": harvested_count,
            "record_count": source_payload.get("record_count", harvested_count),
            "current_cache_records": source_payload.get("current_cache_records", source_payload.get("record_count", harvested_count)),
            "live_reported_hits": source_payload.get("live_reported_hits", 0),
            "live_harvested_records": source_payload.get("live_harvested_records", 0),
            "live_coverage_ratio": source_payload.get("live_coverage_ratio", "unknown"),
            "merged_existing_cache": source_payload.get("merged_existing_cache", False),
            "existing_cache_records_before_merge": source_payload.get("existing_cache_records_before_merge", 0),
            "live_returned_records_before_merge": source_payload.get("live_returned_records_before_merge", 0),
            "merged_cache_records": source_payload.get("merged_cache_records", 0),
            "coverage_ratio": source_payload.get("coverage_ratio", 0),
            "query_count": source_payload.get("query_count", 0),
            "failed_queries": source_payload.get("failed_queries", source_payload.get("error_count", 0)),
            "capped_queries": source_payload.get("capped_queries", 0),
            "last_updated": source_payload.get(
                "last_updated",
                source_payload.get("last_successful_update", source_payload.get("updated_at", "")),
            ),
            "last_successful_update": source_payload.get("last_successful_update", ""),
            "raw_query_manifest": source_payload.get("raw_query_manifest", ""),
            "normalized_cache": source_payload.get("normalized_cache", ""),
            "source_manifest": source_payload.get("source_manifest", ""),
            "guidance": source_payload.get("guidance", ""),
            "live_smoke_status": live_smoke.get("status", ""),
            "live_smoke_mode": live_smoke.get("mode", ""),
            "live_smoke_reported_hits": live_smoke.get("reported_hits", 0),
            "live_smoke_harvested_records": live_smoke.get("harvested_records", 0),
            "live_smoke_query_count": live_smoke.get("query_count", 0),
            "live_smoke_failed_queries": live_smoke.get("failed_queries", 0),
            "live_smoke_capped_queries": live_smoke.get("capped_queries", 0),
            "live_smoke_guidance": live_smoke.get("guidance", ""),
            "live_smoke_error": live_smoke.get("error", ""),
        }
    return coverage_by_source


def resource_atlas_summary() -> dict[str, Any]:
    index = load_resource_index()
    model_resources = [{**row, "resource_kind": "model"} for row in _resource_records(index, "model_resources")]
    omics_resources = [{**row, "resource_kind": "omics"} for row in _resource_records(index, "omics_resources")]
    raw_resources = [*model_resources, *omics_resources]
    resources = _deduplicate_resource_payloads(raw_resources)
    deduplication_summary = _resource_deduplication_summary(raw_resources, resources)
    organisms = [row for row in index.get("organisms") or [] if isinstance(row, dict)]
    manifest = index.get("cache_manifest") if isinstance(index.get("cache_manifest"), dict) else {}

    coverage_by_source = _resource_coverage_by_source(index)
    landscape_nodes = _resource_species_from_index(index).get("species", [])
    landscape_clusters = build_landscape_clusters(
        landscape_nodes,
        canonical_taxonomy_group=_resource_canonical_taxonomy_group,
        taxonomy_label=_resource_taxonomy_label,
    )
    lineage_tree = build_species_resource_lineage_tree(
        landscape_nodes=landscape_nodes,
        target_organisms=_read_resource_organism_targets(),
        resources=resources,
        image_manifest=_read_resource_lineage_image_manifest(),
        canonical_taxonomy_group=_resource_canonical_taxonomy_group,
        taxonomy_label=_resource_taxonomy_label,
    )

    return build_resource_atlas_summary_response(
        index=index,
        model_resources=model_resources,
        omics_resources=omics_resources,
        raw_resources=raw_resources,
        resources=resources,
        deduplication_summary=deduplication_summary,
        organisms=organisms,
        manifest=manifest,
        coverage_by_source=coverage_by_source,
        landscape_nodes=landscape_nodes,
        landscape_clusters=landscape_clusters,
        lineage_tree_resource_nodes=lineage_tree["nodes"],
        lineage_tree_resource_edges=lineage_tree["edges"],
        unplaced_resource_organisms=lineage_tree["unplaced_resource_organisms"],
        lineage_tree_summary=lineage_tree["summary"],
        lineage_tree_image_manifest=lineage_tree["image_manifest"],
        taxonomy_group_for_row=lambda row: _resource_taxonomy_group(row, index),
        supported_methods_for_row=_resource_supported_methods,
        readiness_class_for_value=_resource_readiness_class,
    )


def resource_detail(resource_id: str) -> dict[str, Any]:
    index = load_resource_index()
    resource_id = resource_id.strip()
    for kind, key in (("model", "model_resources"), ("omics", "omics_resources")):
        for row in _resource_records(index, key):
            if str(row.get("resource_id") or "") == resource_id:
                organism = _organism_by_id(index, str(row.get("organism_id") or ""))
                row = dict(row)
                row["taxonomy_group"] = _resource_taxonomy_group(row, index)
                row["supported_methods"] = _resource_supported_methods(row)
                return build_resource_detail_response(
                    index=index,
                    resource_kind=kind,
                    resource=row,
                    organism=organism,
                    suggested_methods=suggested_methods_for_resource(row),
                )
    raise ApiError(404, f"Resource not found: {resource_id}")


def resource_curation_template(resource_id: str) -> dict[str, Any]:
    """Return a lightweight CSV template for manually curating one resource."""

    detail = resource_detail(resource_id)
    resource = dict(detail.get("resource") or {})
    resource_kind = str(detail.get("resource_kind") or "")
    return build_resource_curation_template_response(
        resource_id=resource_id,
        resource_kind=resource_kind,
        resource=resource,
    )


def resource_curation_preview(resource_id: str, role: str, filename: str, data: bytes) -> dict[str, Any]:
    """Preview a user-curated CSV without saving it or changing Atlas readiness."""

    if not resource_id.strip():
        raise ApiError(400, "resource_id is required.")
    if not filename:
        raise ApiError(400, "file is required.")
    detail = resource_detail(resource_id)
    resource = dict(detail.get("resource") or {})
    return preview_resource_curation_file(
        resource_id=resource_id,
        resource_kind=str(detail.get("resource_kind") or ""),
        resource=resource,
        requested_role=role,
        filename=filename,
        data=data,
    )


def resource_model_suggestions(model_id: str) -> dict[str, Any]:
    index = load_resource_index()
    normalized_model = model_id.strip().lower()
    model_rows = [
        row
        for row in _resource_records(index, "model_resources")
        if normalized_model
        and normalized_model
        in " ".join([str(row.get("model_id") or ""), str(row.get("model_name") or ""), str(row.get("resource_id") or "")]).lower()
    ]
    organism_ids = {str(row.get("organism_id") or "") for row in model_rows}
    omics_rows = [
        row for row in _resource_records(index, "omics_resources") if str(row.get("organism_id") or "") in organism_ids
    ]
    method_ids: list[str] = []
    for row in omics_rows:
        for method in suggested_methods_for_resource(row):
            if method not in method_ids:
                method_ids.append(method)
    return {
        "status": index.get("status", "ready"),
        "model_id": model_id,
        "models": model_rows,
        "omics_resources": omics_rows,
        "suggested_methods": method_ids,
        "readiness_reason": _resource_suggestion_reason(omics_rows),
        "guidance": index.get("guidance", ""),
    }


def resource_candidate_package_preview(
    resource_ids: list[str] | str,
    *,
    run_id: str = "",
    package_name: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """Preview an Atlas candidate package without writing a run package."""

    index = load_resource_index()
    selected_ids = _normalize_resource_id_list(resource_ids)
    resources, missing_ids = _lookup_resource_candidates(index, selected_ids)
    model_candidates = [row for row in resources if row.get("resource_kind") == "model"]
    omics_candidates = [row for row in resources if row.get("resource_kind") == "omics"]
    stageable_models = [row for row in model_candidates if _resource_can_stage_model(row)]
    ready_evidence = [row for row in omics_candidates if _resource_can_stage_evidence(row)]
    non_ready = [row for row in resources if row not in stageable_models and row not in ready_evidence]
    suggested_methods = suggested_methods_for_resource_set(resources)
    primary_model = stageable_models[0] if len(stageable_models) == 1 else None
    proposed_run_id = _candidate_package_run_id(primary_model, run_id=run_id, package_name=package_name, reserve=False)
    guidance = _candidate_package_guidance(
        selected_ids=selected_ids,
        missing_ids=missing_ids,
        model_candidates=model_candidates,
        stageable_models=stageable_models,
        ready_evidence=ready_evidence,
        non_ready=non_ready,
    )
    can_stage = bool(primary_model and ready_evidence and not missing_ids and len(stageable_models) == 1 and len(model_candidates) == 1)
    return {
        "status": "ready" if can_stage else "partial",
        "resource_ids": selected_ids,
        "missing_resource_ids": missing_ids,
        "can_stage": can_stage,
        "proposed_run_id": proposed_run_id,
        "package_name": package_name,
        "notes": notes,
        "primary_model": primary_model,
        "model_candidates": model_candidates,
        "ready_evidence": ready_evidence,
        "needs_curation": non_ready,
        "metadata_only": [
            row
            for row in non_ready
            if str(row.get("readiness") or row.get("import_readiness") or "") in {"metadata_only", "raw_data_only"}
        ],
        "suggested_methods": suggested_methods,
        "readiness_groups": _candidate_readiness_groups(resources),
        "guidance": " ".join(guidance),
    }


def stage_resource_candidate_package(
    resource_ids: list[str] | str,
    *,
    run_id: str = "",
    package_name: str = "",
    notes: str = "",
) -> dict[str, Any]:
    """Stage an Atlas candidate package into user_runs without downloading external data."""

    preview = resource_candidate_package_preview(resource_ids, run_id=run_id, package_name=package_name, notes=notes)
    if not preview.get("can_stage"):
        raise ApiError(400, str(preview.get("guidance") or "Candidate package is not ready to stage."))
    primary_model = preview.get("primary_model")
    if not isinstance(primary_model, dict):
        raise ApiError(400, "Candidate package requires one primary model.")
    target_run_id = _candidate_package_run_id(primary_model, run_id=run_id, package_name=package_name, reserve=True)
    target = (USER_RUNS_DIR / target_run_id).resolve()
    if target.exists():
        raise ApiError(409, f"Target run package already exists: {target}")

    model_payload = _candidate_model_payload(primary_model)
    omics_payloads: list[UploadFilePayload] = []
    condition_payloads: list[UploadFilePayload] = []
    for row in preview.get("ready_evidence") or []:
        if not isinstance(row, dict):
            continue
        payload, is_condition = _candidate_table_payload(row)
        if is_condition:
            condition_payloads.append(payload)
        else:
            omics_payloads.append(payload)

    run_config = _candidate_run_config(target_run_id, preview)
    package = stage_user_run_package(
        output_root=USER_RUNS_DIR,
        run_config=run_config,
        model_file=model_payload,
        omics_files=omics_payloads,
        condition_files=condition_payloads,
        run_id=target_run_id,
    )
    package_path = Path(package.output_dir)
    atlas_manifest = _candidate_atlas_manifest(target_run_id, preview)
    write_json(package_path / "atlas_resource_manifest.json", atlas_manifest)
    manifest = read_json_object(package_path / "upload_manifest.json")
    manifest.setdefault("files", {})
    if isinstance(manifest["files"], dict):
        manifest["files"]["atlas_resource_manifest"] = str(package_path / "atlas_resource_manifest.json")
    manifest["atlas_candidate_package"] = {
        "resource_ids": preview.get("resource_ids", []),
        "suggested_methods": preview.get("suggested_methods", []),
        "status": "staged",
    }
    write_json(package_path / "upload_manifest.json", manifest)
    return {
        "status": package.status,
        "message": package.message,
        "run_id": package.run_id,
        "output_dir": package.output_dir,
        "files": {
            **package.files,
            "atlas_resource_manifest": str(package_path / "atlas_resource_manifest.json"),
        },
        "input_rows": package.input_rows,
        "manifest": manifest,
        "atlas_resource_manifest": atlas_manifest,
        "preview": preview,
        "overview": run_overview(package_path),
    }


def run_atlas_resource_manifest(run_id: str) -> dict[str, Any]:
    """Read the Atlas provenance manifest for a staged run package."""

    package = resolve_run_package(run_id)
    manifest_path = package / "atlas_resource_manifest.json"
    if not manifest_path.exists():
        return {
            "run_id": run_id,
            "status": "partial",
            "manifest_path": str(manifest_path),
            "manifest_exists": False,
            "resources": [],
            "primary_model": None,
            "ready_evidence": [],
            "needs_curation": [],
            "metadata_only": [],
            "staged_files": [],
            "suggested_methods": [],
            "source_databases": [],
            "guidance": "Atlas resource manifest is not available for this run.",
        }
    try:
        manifest = read_json_object(manifest_path)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "run_id": run_id,
            "status": "partial",
            "manifest_path": str(manifest_path),
            "manifest_exists": True,
            "resources": [],
            "primary_model": None,
            "ready_evidence": [],
            "needs_curation": [],
            "metadata_only": [],
            "staged_files": [],
            "suggested_methods": [],
            "source_databases": [],
            "guidance": f"Atlas resource manifest could not be read: {exc}",
        }

    resources = [row for row in (manifest.get("resources") or []) if isinstance(row, dict)]
    primary_model_id = str(manifest.get("primary_model_resource_id") or "")
    primary_model = next((row for row in resources if str(row.get("resource_id") or "") == primary_model_id), None)
    ready_evidence = [
        row
        for row in resources
        if row.get("staged_as_input") and str(row.get("resource_kind") or "") != "model"
    ]
    needs_curation = [
        row
        for row in resources
        if not row.get("staged_as_input")
        and str(row.get("readiness") or "") not in {"ready_for_import", "ready_for_reference"}
    ]
    metadata_only = [
        row
        for row in resources
        if str(row.get("readiness") or "") in {"metadata_only", "raw_data_only", "license_or_access_limited"}
    ]
    staged_files: list[dict[str, Any]] = []
    input_rows = read_csv_rows(package / "input_file_map.csv")
    for row in input_rows:
        path_text = str(row.get("path") or "")
        if not path_text:
            continue
        staged_files.append(
            {
                "kind": row.get("kind", ""),
                "role": row.get("role", ""),
                "path": path_text,
                "relative_path": row.get("relative_path", _safe_relative_path(package, Path(path_text))),
                "status": "ready" if Path(path_text).exists() else "missing",
            }
        )
    source_databases = sorted(
        {
            str(row.get("source_database") or row.get("connector_source") or "")
            for row in resources
            if str(row.get("source_database") or row.get("connector_source") or "")
        }
    )
    return {
        "run_id": run_id,
        "status": "ready" if resources else "partial",
        "manifest_path": str(manifest_path),
        "manifest_exists": True,
        "manifest": manifest,
        "resources": resources,
        "primary_model": primary_model,
        "ready_evidence": ready_evidence,
        "needs_curation": needs_curation,
        "metadata_only": metadata_only,
        "staged_files": staged_files,
        "suggested_methods": manifest.get("suggested_methods", []),
        "source_databases": source_databases,
        "mapping_preview": manifest.get("mapping_preview", {}),
        "mapping_preview_status": (manifest.get("mapping_preview") or {}).get("status", ""),
        "guidance": manifest.get("guidance", ""),
    }


def _resource_curation_workspaces() -> ResourceCurationWorkspaces:
    """Compose the deep Resource Curation Workspace module from current roots."""

    return ResourceCurationWorkspaces(
        ResourceCurationWorkspaceConfig(
            app_root=APP_ROOT,
            workspace_root=WORKSPACE_ROOT,
            curation_root=ATLAS_CURATION_WORKSPACES_DIR,
            user_runs_root=USER_RUNS_DIR,
        ),
        load_resources=lambda resource_ids: _lookup_resource_candidates(load_resource_index(), resource_ids),
    )


def _run_resource_curation_workspace(operation: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return operation()
    except ResourceCurationWorkspaceError as exc:
        raise ApiError(exc.status_code, exc.detail) from exc


def create_resource_curation_workspace(
    resource_ids: list[str] | str,
    *,
    workspace_id: str = "",
    title: str = "",
    notes: str = "",
) -> dict[str, Any]:
    workspace = _resource_curation_workspaces()
    command = CreateCurationWorkspace(
        resource_ids=tuple(_normalize_resource_id_list(resource_ids)),
        workspace_id=workspace_id,
        title=title,
        notes=notes,
    )
    return _run_resource_curation_workspace(lambda: workspace.create(command))


def list_resource_curation_workspaces() -> dict[str, Any]:
    workspace = _resource_curation_workspaces()
    return _run_resource_curation_workspace(lambda: workspace.query(ListCurationWorkspaces()))


def get_resource_curation_workspace(workspace_id: str) -> dict[str, Any]:
    workspace = _resource_curation_workspaces()
    return _run_resource_curation_workspace(
        lambda: workspace.query(GetCurationWorkspace(workspace_id=workspace_id))
    )


def upload_resource_curation_workspace_file(
    workspace_id: str,
    *,
    resource_id: str,
    role: str,
    filename: str,
    data: bytes,
) -> dict[str, Any]:
    workspace = _resource_curation_workspaces()
    command = CurationAddCuratedFile(
        resource_id=resource_id,
        role=role,
        filename=filename,
        data=data,
    )
    return _run_resource_curation_workspace(lambda: workspace.execute(workspace_id, command))


def preview_resource_curation_workspace_mapping(
    workspace_id: str,
    *,
    file_name: str = "",
) -> dict[str, Any]:
    workspace = _resource_curation_workspaces()
    return _run_resource_curation_workspace(
        lambda: workspace.execute(workspace_id, PreviewCurationMapping(file_name=file_name))
    )


def stage_resource_curation_workspace_run(
    workspace_id: str,
    *,
    run_id: str = "",
) -> dict[str, Any]:
    workspace = _resource_curation_workspaces()
    payload = _run_resource_curation_workspace(
        lambda: workspace.execute(workspace_id, StageCurationRunPackage(run_id=run_id))
    )
    payload["overview"] = run_overview(Path(str(payload.get("output_dir") or "")))
    return payload


def _normalize_resource_id_list(resource_ids: list[str] | str) -> list[str]:
    if isinstance(resource_ids, str):
        raw = re.split(r"[;,\s]+", resource_ids)
    else:
        raw = [str(item) for item in resource_ids]
    seen: set[str] = set()
    result: list[str] = []
    for item in raw:
        resource_id = str(item or "").strip()
        if resource_id and resource_id not in seen:
            seen.add(resource_id)
            result.append(resource_id)
    return result


def _lookup_resource_candidates(index: dict[str, Any], resource_ids: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    by_id: dict[str, dict[str, Any]] = {}
    for kind, key in (("model", "model_resources"), ("omics", "omics_resources")):
        for row in _resource_records(index, key):
            record = dict(row)
            record["resource_kind"] = kind
            by_id[str(record.get("resource_id") or "")] = record
    resources: list[dict[str, Any]] = []
    missing: list[str] = []
    for resource_id in resource_ids:
        row = by_id.get(resource_id)
        if row:
            resources.append(row)
        else:
            missing.append(resource_id)
    return resources, missing




def _resource_can_stage_model(row: dict[str, Any]) -> bool:
    readiness = str(row.get("readiness") or row.get("import_readiness") or "")
    return readiness in {"ready_for_import", "ready_for_reference"} and bool(_resource_local_file(row))


def _resource_can_stage_evidence(row: dict[str, Any]) -> bool:
    readiness = str(row.get("readiness") or row.get("import_readiness") or "")
    return readiness == "ready_for_import" and bool(_resource_local_file(row))


def _resource_local_file(row: dict[str, Any]) -> Path | None:
    local_path = str(row.get("local_path") or "").strip()
    if not local_path:
        return None
    path = Path(local_path)
    resolved = path.resolve() if path.is_absolute() else (APP_ROOT / path).resolve()
    allowed_roots = (APP_ROOT.resolve(), WORKSPACE_ROOT.resolve())
    if not any(_is_relative_to(resolved, root) for root in allowed_roots):
        return None
    if not resolved.exists() or not resolved.is_file():
        return None
    return resolved




def _candidate_package_guidance(
    *,
    selected_ids: list[str],
    missing_ids: list[str],
    model_candidates: list[dict[str, Any]],
    stageable_models: list[dict[str, Any]],
    ready_evidence: list[dict[str, Any]],
    non_ready: list[dict[str, Any]],
) -> list[str]:
    guidance: list[str] = []
    if not selected_ids:
        guidance.append("Add resources from the Atlas before preparing a Run Package.")
    if missing_ids:
        guidance.append(f"Unknown resource ids: {', '.join(missing_ids)}.")
    if not model_candidates:
        guidance.append("Select exactly one model resource as the primary reference model.")
    elif len(model_candidates) > 1:
        guidance.append("Multiple model resources were selected; keep one primary model for v1 staging.")
    elif not stageable_models:
        guidance.append("The selected model has no local import-ready file; review the source and curate it first.")
    if not ready_evidence:
        guidance.append("No local ready evidence tables are selected; metadata-only resources are recorded as curation notes only.")
    if non_ready:
        guidance.append("Non-ready resources will be recorded in atlas_resource_manifest.json and will not create fake input files.")
    if not guidance:
        guidance.append("Candidate package is ready to stage into user_runs.")
    return guidance


def _candidate_readiness_groups(resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in resources:
        key = str(row.get("readiness") or row.get("import_readiness") or "metadata_only")
        groups.setdefault(key, []).append(row)
    return [{"readiness": key, "count": len(rows), "resources": rows} for key, rows in sorted(groups.items())]


def _candidate_package_run_id(
    primary_model: dict[str, Any] | None,
    *,
    run_id: str = "",
    package_name: str = "",
    reserve: bool = False,
) -> str:
    if run_id:
        sanitized = _sanitize_run_id(run_id)
        if sanitized != run_id:
            raise ApiError(400, "run_id may contain only letters, numbers, underscore, and dash.")
        return sanitized
    base = package_name or f"atlas_{str((primary_model or {}).get('model_id') or 'candidate_package').lower()}"
    sanitized_base = _sanitize_run_id(base) or "atlas_candidate_package"
    return _next_available_run_id(sanitized_base) if reserve else sanitized_base


def _candidate_model_payload(row: dict[str, Any]) -> UploadFilePayload:
    path = _resource_local_file(row)
    if not path:
        raise ApiError(400, f"Model resource is not locally stageable: {row.get('resource_id')}")
    inspection = inspect_model_filename(path.name)
    return UploadFilePayload(
        filename=path.name,
        data=path.read_bytes(),
        kind="model",
        role="gem",
        columns=[],
        status=inspection.status,
        details=inspection.details,
    )


def _candidate_table_payload(row: dict[str, Any]) -> tuple[UploadFilePayload, bool]:
    path = _resource_local_file(row)
    if not path:
        raise ApiError(400, f"Resource is not locally stageable: {row.get('resource_id')}")
    data = path.read_bytes()
    role, is_condition = _candidate_table_role(row)
    inspection = inspect_table_file(io.BytesIO(data), path.name, list(EXPECTED_COLUMNS))
    return (
        UploadFilePayload(
            filename=path.name,
            data=data,
            kind="condition_table" if is_condition else "omics_table",
            role=role,
            columns=inspection.columns,
            status=inspection.status,
            details=inspection.details,
        ),
        is_condition,
    )


def _candidate_table_role(row: dict[str, Any]) -> tuple[str, bool]:
    omics_type = str(row.get("omics_type") or "").lower()
    text = " ".join(
        [
            str(row.get("resource_id") or ""),
            str(row.get("title") or ""),
            str(row.get("local_path") or ""),
            str(row.get("platform") or ""),
        ]
    ).lower()
    if "condition" in text or "exchange_bound" in text or "bound" in text:
        return "condition_exchange_bounds", True
    if "absolute_proteomics" in text or ("proteomics" in omics_type and "absolute" in text):
        return "absolute_proteomics", False
    if "relative_proteomics" in text or ("proteomics" in omics_type and "relative" in text):
        return "relative_proteomics", False
    if omics_type == "proteomics":
        return "absolute_proteomics", False
    if omics_type == "transcriptomics":
        return "transcriptomics", False
    if omics_type == "kcat" or "kcat" in text or "gotenzymes" in text:
        return "ml_priors", False
    if "uniprot" in text:
        return "uniprot_annotation", False
    if "dlkcat" in text:
        return "dlkcat_annotation", False
    if "production" in text:
        return "production_targets", False
    if "alias" in text or "kegg" in text or omics_type == "annotation":
        return "id_alias_table", False
    return choose_default_role(str(row.get("local_path") or row.get("title") or "resource.csv"), [], list(EXPECTED_COLUMNS)), False


def _candidate_run_config(run_id: str, preview: dict[str, Any]) -> dict[str, Any]:
    methods = [
        method
        for method in preview.get("suggested_methods") or []
        if method in {"baseline_gem", "eflux", "fastcore", "consensus_evidence", "enzyme_gecko"}
    ]
    if "baseline_gem" not in methods:
        methods.insert(0, "baseline_gem")
    analyses = ["fba_pfba", "evidence_comparison", "readiness_gate"]
    if "analysis_visualization" in (preview.get("suggested_methods") or []):
        analyses.append("visualization")
    return {
        "run_id": run_id,
        "description": "Created from Model & Omics Resource Atlas candidate package.",
        "model_generation_methods": methods,
        "analysis_modules": analyses,
        "run_gecko_external": False,
        "atlas_candidate_package": {
            "resource_ids": preview.get("resource_ids", []),
            "suggested_methods": preview.get("suggested_methods", []),
            "notes": preview.get("notes", ""),
        },
    }


def _candidate_atlas_manifest(run_id: str, preview: dict[str, Any]) -> dict[str, Any]:
    resources = []
    for row in (
        (preview.get("model_candidates") or [])
        + (preview.get("ready_evidence") or [])
        + (preview.get("needs_curation") or [])
    ):
        if not isinstance(row, dict):
            continue
        resources.append(
            {
                "resource_id": row.get("resource_id", ""),
                "resource_kind": row.get("resource_kind", ""),
                "title": row.get("title") or row.get("model_name") or row.get("model_id") or row.get("resource_id", ""),
                "source_database": row.get("source_database", ""),
                "connector_source": row.get("connector_source", ""),
                "accession": row.get("accession", ""),
                "organism_id": row.get("organism_id", ""),
                "organism_name": row.get("organism_name", ""),
                "omics_type": row.get("omics_type", ""),
                "readiness": row.get("readiness", row.get("import_readiness", "")),
                "readiness_reason": row.get("readiness_reason", ""),
                "external_url": row.get("external_url", ""),
                "local_path": row.get("local_path", ""),
                "staged_as_input": row in (preview.get("ready_evidence") or []) or row == preview.get("primary_model"),
            }
        )
    return {
        "schema_version": "0.1.0",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "run_id": run_id,
        "status": "staged",
        "resource_ids": preview.get("resource_ids", []),
        "primary_model_resource_id": (preview.get("primary_model") or {}).get("resource_id", ""),
        "suggested_methods": preview.get("suggested_methods", []),
        "guidance": preview.get("guidance", ""),
        "resources": resources,
    }


def backend_environment_readiness() -> dict[str, Any]:
    venv_python = _venv_python_path()
    frontend_root = APP_ROOT / "frontend"
    bootstrap_status_path = APP_ROOT / ".runtime_cache" / "bootstrap_status.json"
    default_staging_root = APP_ROOT / "desktop_staging" / "Omics-GEM-Studio"
    staging_manifest_candidates = [
        APP_ROOT / "desktop_staging_manifest.json",
        default_staging_root / "desktop_staging_manifest.json",
    ]
    staging_manifest_path = next((path for path in staging_manifest_candidates if path.exists()), staging_manifest_candidates[-1])
    smoke_report_candidates = [
        APP_ROOT / "desktop_staging_smoke_report.json",
        default_staging_root / "desktop_staging_smoke_report.json",
        APP_ROOT / ".runtime_cache" / "desktop_staging_smoke_report.json",
    ]
    smoke_report_path = next((path for path in smoke_report_candidates if path.exists()), smoke_report_candidates[1])
    smoke_checklist_path = APP_ROOT / "paper" / "Desktop_clean_windows_smoke_checklist.md"
    installer_root = APP_ROOT / "desktop_installer"
    installer_manifest_path = installer_root / "desktop_installer_manifest.json"
    installer_manifest = read_json_object(installer_manifest_path)
    installer_artifact_path = Path(str(installer_manifest.get("installer_artifact_path") or installer_root / "Omics-GEM-Studio-Setup.exe"))
    makensis_path = str(installer_manifest.get("makensis_path") or _resolve_makensis_path())
    makensis_version = str(installer_manifest.get("makensis_version") or _makensis_version(makensis_path))
    setup_exe_path = Path(str(installer_manifest.get("setup_exe_path") or installer_root / "Omics-GEM-Studio-Setup.exe"))
    fallback_zip_path = Path(str(installer_manifest.get("fallback_zip_path") or installer_root / "Omics-GEM-Studio-runtime-staging.zip"))
    installer_smoke_report_path = Path(
        str(installer_manifest.get("installer_smoke_report_path") or installer_root / "desktop_installer_smoke_report.json")
    )
    installer_smoke_markdown_path = Path(
        str(installer_manifest.get("installer_smoke_markdown_path") or installer_root / "desktop_installer_smoke_report.md")
    )
    installer_smoke_report = read_json_object(installer_smoke_report_path)
    installer_qa_status = str(
        installer_manifest.get("non_destructive_qa_status") or installer_smoke_report.get("status") or "missing"
    )
    setup_exe_sha256 = str(installer_manifest.get("setup_exe_sha256") or installer_smoke_report.get("setup_exe_sha256") or "")
    setup_exe_size_bytes = _safe_int(
        installer_manifest.get("setup_exe_size_bytes") or installer_smoke_report.get("setup_exe_size_bytes") or 0
    )
    local_install_smoke_report_path = installer_root / "local_install_smoke_report.json"
    local_install_smoke_markdown_path = installer_root / "local_install_smoke_report.md"
    local_install_smoke_report = read_json_object(local_install_smoke_report_path)
    local_install_bootstrap_status = local_install_smoke_report.get("bootstrap_status") or {}
    runtime_candidates = [
        APP_ROOT / "desktop_runtime" / "win-unpacked" / "Omics-GEM Studio.exe",
        APP_ROOT / "desktop_dist" / "win-unpacked" / "Omics-GEM Studio.exe",
    ]
    packaged_runtime_path = next((path for path in runtime_candidates if path.exists()), None)
    node_path = shutil.which("node") or ""
    npm_path = shutil.which("npm.cmd") or shutil.which("npm") or ""
    frontend_node_modules_ready = (frontend_root / "node_modules").exists()
    frontend_dist_ready = (frontend_root / "dist" / "index.html").exists()
    packaged_runtime_ready = packaged_runtime_path is not None
    runtime_launcher_path = APP_ROOT / "start_omics_gem_studio.bat"
    if not runtime_launcher_path.exists():
        runtime_launcher_path = APP_ROOT / "start_omics_gem_desktop.bat"
    frontend_runtime_source = (
        "packaged_electron_runtime"
        if packaged_runtime_ready
        else "frontend_dist"
        if frontend_dist_ready
        else "missing"
    )
    last_bootstrap_status = read_json_object(bootstrap_status_path)
    required_modules = _module_rows(_requirements_modules(APP_ROOT / "requirements.txt"))
    optional_modules = _module_rows(_optional_backend_modules())
    external_dependencies = external_dependency_readiness()
    external_config = load_local_backend_config()
    sammi_vendor = sammi_vendor_status(APP_ROOT)
    missing_required = [item["module"] for item in required_modules if item["status"] != "available"]
    fastapi = next((item for item in required_modules if item["module"] == "fastapi"), _module_row("fastapi"))
    cobra = next((item for item in optional_modules if item["module"] == "cobra"), _module_row("cobra"))
    python_found = Path(sys.executable).exists()
    venv_exists = venv_python.exists()
    requirements_installed = not missing_required
    if not python_found or not venv_exists:
        status = "missing_environment"
        recommendation = "Create or repair the project-local .venv before starting the desktop backend."
    elif not requirements_installed:
        status = "missing_required_modules"
        recommendation = "Install requirements.txt in the project-local .venv."
    elif cobra["status"] != "available":
        status = "ready_minimal"
        recommendation = "Core API/UI dependencies are ready; optional COBRA-backed analyses may need requirements-optional.txt."
    else:
        status = "ready"
        recommendation = "Core API/UI and common optional analysis modules are importable."
    return {
        "status": status,
        "project_root": str(APP_ROOT),
        "workspace_root": str(WORKSPACE_ROOT),
        "current_python": sys.executable,
        "python_version": sys.version.split()[0],
        "python_found": python_found,
        "venv_python": str(venv_python),
        "venv_exists": venv_exists,
        "venv_active": _same_path(Path(sys.executable), venv_python),
        "requirements_file": str(APP_ROOT / "requirements.txt"),
        "requirements_file_exists": (APP_ROOT / "requirements.txt").exists(),
        "optional_requirements_file": str(APP_ROOT / "requirements-optional.txt"),
        "optional_requirements_file_exists": (APP_ROOT / "requirements-optional.txt").exists(),
        "requirements_installed": requirements_installed,
        "missing_required_modules": missing_required,
        "fastapi_importable": fastapi["status"] == "available",
        "cobra_importable": cobra["status"] == "available",
        "required_modules": required_modules,
        "optional_modules": optional_modules,
        "external_dependencies": external_dependencies,
        "external_dependency_config": external_config,
        "sammi_vendor": sammi_vendor,
        "repair_command": r".\start_omics_gem_router.ps1 -RecreateVenv",
        "minimal_repair_command": r".\start_omics_gem_router.ps1 -Minimal",
        "bootstrap_command": r".\tools\bootstrap_desktop_env.ps1 -Mode Minimal",
        "desktop_bootstrap_command": r".\start_omics_gem_desktop.ps1",
        "runtime_bootstrap_command": r".\tools\bootstrap_desktop_env.ps1 -RuntimeOnly -Mode Minimal",
        "desktop_runtime_command": r".\start_omics_gem_desktop.ps1 -Runtime",
        "runtime_launcher_command": r".\start_omics_gem_studio.bat"
        if (APP_ROOT / "start_omics_gem_studio.bat").exists()
        else r".\start_omics_gem_desktop.ps1 -Runtime",
        "runtime_launcher_path": str(runtime_launcher_path),
        "packaged_electron_runtime_ready": packaged_runtime_ready,
        "packaged_electron_runtime_path": str(packaged_runtime_path or runtime_candidates[0]),
        "staging_manifest_path": str(staging_manifest_path),
        "staging_manifest_exists": staging_manifest_path.exists(),
        "staging_smoke_report_path": str(smoke_report_path),
        "staging_smoke_report_exists": smoke_report_path.exists(),
        "clean_windows_smoke_checklist_path": str(smoke_checklist_path),
        "clean_windows_smoke_checklist_exists": smoke_checklist_path.exists(),
        "desktop_installer_dir": str(installer_root),
        "desktop_installer_manifest_path": str(installer_manifest_path),
        "desktop_installer_manifest_exists": installer_manifest_path.exists(),
        "desktop_installer_artifact_path": str(installer_artifact_path),
        "desktop_installer_artifact_exists": installer_artifact_path.exists(),
        "desktop_installer_engine": str(installer_manifest.get("installer_engine") or ""),
        "desktop_installer_status": str(installer_manifest.get("status") or "missing"),
        "nsis_available": bool(makensis_path) and Path(makensis_path).exists(),
        "makensis_path": makensis_path,
        "makensis_version": makensis_version,
        "installer_setup_exe_path": str(setup_exe_path),
        "installer_setup_exe_exists": setup_exe_path.exists(),
        "installer_fallback_zip_path": str(fallback_zip_path),
        "installer_fallback_zip_exists": fallback_zip_path.exists(),
        "installer_smoke_report_path": str(installer_smoke_report_path),
        "installer_smoke_report_exists": installer_smoke_report_path.exists(),
        "installer_smoke_markdown_path": str(installer_smoke_markdown_path),
        "installer_smoke_markdown_exists": installer_smoke_markdown_path.exists(),
        "installer_non_destructive_qa_status": installer_qa_status,
        "installer_setup_exe_sha256": setup_exe_sha256,
        "installer_setup_exe_size_bytes": setup_exe_size_bytes,
        "local_install_smoke_report_path": str(local_install_smoke_report_path),
        "local_install_smoke_report_exists": local_install_smoke_report_path.exists(),
        "local_install_smoke_markdown_path": str(local_install_smoke_markdown_path),
        "local_install_smoke_markdown_exists": local_install_smoke_markdown_path.exists(),
        "local_install_smoke_status": str(local_install_smoke_report.get("status") or "missing"),
        "local_install_smoke_install_dir": str(local_install_smoke_report.get("install_dir") or ""),
        "local_install_smoke_bootstrap_status": str(
            local_install_bootstrap_status.get("status") if isinstance(local_install_bootstrap_status, dict) else ""
        ),
        "local_install_smoke_uninstall_exit_code": _safe_int(local_install_smoke_report.get("uninstall_exit_code")),
        "local_install_smoke_logs_dir": str(local_install_smoke_report.get("archived_logs_dir") or ""),
        "frontend_runtime_source": frontend_runtime_source,
        "node_required_for_runtime": not packaged_runtime_ready,
        "developer_node_required": True,
        "node_found": bool(node_path),
        "node_path": node_path,
        "npm_found": bool(npm_path),
        "npm_path": npm_path,
        "frontend_node_modules_ready": frontend_node_modules_ready,
        "frontend_dist_ready": frontend_dist_ready,
        "last_bootstrap_status": last_bootstrap_status,
        "last_bootstrap_status_path": str(bootstrap_status_path),
        "repair_action_status": "available_guarded",
        "recommendation": recommendation,
    }


EXTERNAL_CONFIG_KEYS = {
    "matlab_cmd",
    "gecko_home",
    "raven_home",
    "cobra_toolbox_home",
    "solver",
    "pytfa_thermo_db",
    "sammi_standalone_home",
}


def external_dependency_readiness(config: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Return read-only readiness for licensed/manual external tools."""

    normalized = config or load_local_backend_config()
    matlab_configured = _config_or_env(normalized, "matlab_cmd", "MATLAB_CMD")
    matlab_detected = _resolve_command_or_path(matlab_configured or "matlab")
    gecko_home = _config_or_env(normalized, "gecko_home", "GECKO_HOME")
    raven_home = _config_or_env(normalized, "raven_home", "RAVEN_HOME")
    cobra_toolbox_home = _config_or_env(normalized, "cobra_toolbox_home", "COBRA_TOOLBOX_HOME")
    solver = _config_or_env(normalized, "solver", "OMICS_GEM_SOLVER")
    pytfa_thermo_db = _config_or_env(normalized, "pytfa_thermo_db", "PYTFA_THERMO_DB")
    sammi_home = _config_or_env(normalized, "sammi_standalone_home", "SAMMI_STANDALONE_HOME")

    return [
        {
            "id": "matlab",
            "label": "MATLAB",
            "status": "available" if matlab_detected else "needs_manual_install",
            "detected_path": matlab_detected,
            "configured_path": matlab_configured,
            "required_for": "GECKO ecModel execution, GECKO/DLKcat, MATLAB-based helper workflows.",
            "install_guidance": "Install MATLAB locally and make matlab.exe available on PATH, or set MATLAB command/path here.",
            "next_action": "Configure matlab path or install MATLAB." if not matlab_detected else "Ready for optional MATLAB probes.",
        },
        _path_dependency_row(
            "gecko_home",
            "GECKO_HOME",
            gecko_home,
            "GECKO ecModel export execution and GECKO/DLKcat prediction.",
            "Install or clone GECKO separately, then set GECKO_HOME to the GECKO checkout directory.",
            "Set GECKO_HOME after installing GECKO.",
        ),
        _multi_path_dependency_row(
            "raven_cobra_toolbox",
            "RAVEN / COBRA Toolbox",
            {"RAVEN_HOME": raven_home, "COBRA_TOOLBOX_HOME": cobra_toolbox_home},
            "MATLAB-side model loading and GECKO adapter workflows.",
            "Install RAVEN or COBRA Toolbox separately and configure the local path when your GECKO protocol needs it.",
            "Configure RAVEN_HOME or COBRA_TOOLBOX_HOME if your MATLAB protocol requires it.",
        ),
        _solver_dependency_row(solver),
        _path_dependency_row(
            "pytfa_thermo_db",
            "PYTFA_THERMO_DB",
            pytfa_thermo_db,
            "Optional thermodynamic FBA workflows.",
            "Provide an existing pyTFA thermodynamic database file; the app does not generate or install databases automatically.",
            "Set PYTFA_THERMO_DB only when using pyTFA workflows.",
            expect_file=True,
            optional=True,
        ),
        _sammi_dependency_row(sammi_home),
    ]


def save_external_dependency_config(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist external dependency paths without installing external software."""

    current = load_local_backend_config()
    merged = dict(current)
    for key in EXTERNAL_CONFIG_KEYS:
        if key in payload:
            value = str(payload.get(key, "") or "").strip()
            if value:
                merged[key] = value
            else:
                merged.pop(key, None)
    normalized = save_local_backend_config(merged)
    apply_local_backend_env(normalized)
    return {
        "status": "saved",
        "config": normalized,
        "external_dependencies": external_dependency_readiness(normalized),
        "message": "External dependency paths saved. No external software was installed.",
    }


def create_external_dependency_deep_check_job(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run an opt-in MATLAB probe for GECKO/RAVEN availability."""

    request = payload or {}
    config = load_local_backend_config()
    matlab_cmd = str(request.get("matlab_cmd") or config.get("matlab_cmd") or os.environ.get("MATLAB_CMD") or "matlab").strip()
    matlab_path = _resolve_command_or_path(matlab_cmd)
    final_status = "completed" if matlab_path else "skipped"

    def callback(log_path: Path) -> dict[str, Any]:
        deps = external_dependency_readiness(config)
        header = [
            "External dependency deep check job.",
            "This probe does not install MATLAB, GECKO, RAVEN, solvers, or databases.",
            f"matlab_cmd={matlab_cmd}",
            f"matlab_path={matlab_path}",
            "",
        ]
        log_path.write_text("\n".join(header), encoding="utf-8")
        if not matlab_path:
            return {
                "result_status": "skipped",
                "message": "MATLAB command was not found; deep GECKO/RAVEN probe was skipped.",
                "external_dependencies": deps,
            }

        command = [
            matlab_path,
            "-batch",
            _matlab_probe_expression(config),
        ]
        with log_path.open("a", encoding="utf-8", errors="replace") as handle:
            handle.write("command=" + " ".join(command) + "\n\n")
            completed = subprocess.run(
                command,
                cwd=str(APP_ROOT),
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=_safe_int(request.get("timeout_seconds")) or 120,
                check=False,
            )
        result_status = "probe_passed" if completed.returncode == 0 else "probe_failed"
        return {
            "result_status": result_status,
            "message": "MATLAB external dependency probe completed." if completed.returncode == 0 else "MATLAB probe ran but reported missing paths or functions.",
            "return_code": completed.returncode,
            "command": command,
            "external_dependencies": external_dependency_readiness(config),
        }

    return run_sync_job("external_dependency_deep_check", "environment", callback, final_status=final_status)


def list_projects() -> list[dict[str, Any]]:
    return [
        build_project_row(
            workspace_root=WORKSPACE_ROOT,
            user_runs_dir=USER_RUNS_DIR,
            examples_dir=EXAMPLES_DIR,
            task_logs_dir=TASK_LOGS_DIR,
            app_root=APP_ROOT,
        )
    ]


def workspace_status() -> dict[str, Any]:
    config = read_json_object(WORKSPACE_CONFIG_PATH)
    configured_root = str(config.get("workspace_root", "") or "")
    exists = WORKSPACE_ROOT.exists()
    return build_workspace_status_payload(
        app_root=APP_ROOT,
        workspace_root=WORKSPACE_ROOT,
        user_runs_dir=USER_RUNS_DIR,
        examples_dir=EXAMPLES_DIR,
        task_logs_dir=TASK_LOGS_DIR,
        config_path=WORKSPACE_CONFIG_PATH,
        configured_root=configured_root,
        source="config" if configured_root else "default",
        is_default=_same_path(WORKSPACE_ROOT, APP_ROOT),
        exists=exists,
        is_dir=WORKSPACE_ROOT.is_dir(),
        writable=os.access(WORKSPACE_ROOT, os.W_OK) if exists else False,
        allowed_file_roots=ALLOWED_FILE_ROOTS,
    )


def set_workspace_root(path_text: str, *, create: bool = False, persist: bool = True) -> dict[str, Any]:
    if not path_text or not str(path_text).strip():
        raise ApiError(400, "Missing workspace root path.")
    resolved = resolve_directory_candidate_path(path_text, base_root=APP_ROOT)
    if not resolved.exists():
        if create:
            resolved.mkdir(parents=True, exist_ok=True)
        else:
            raise ApiError(404, f"Workspace root does not exist: {path_text}")
    if not resolved.is_dir():
        raise ApiError(400, f"Workspace root must be a directory: {path_text}")
    _apply_workspace_root(resolved, persist=persist)
    _initialize_workspace_dirs()
    return workspace_status()


def reset_workspace_root(*, persist: bool = True) -> dict[str, Any]:
    _apply_workspace_root(APP_ROOT, persist=persist)
    _initialize_workspace_dirs()
    return workspace_status()


def discover_run_packages(root_text: str = "", *, limit: int = 50) -> dict[str, Any]:
    root = _resolve_existing_directory(root_text or str(WORKSPACE_ROOT), "Discovery root")
    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200

    rows = [_run_package_candidate(path, location) for path, location in discover_run_package_paths(root, limit=limit)]

    return {
        "root": str(root),
        "workspace_root": str(WORKSPACE_ROOT),
        "user_runs_dir": str(USER_RUNS_DIR),
        "limit": limit,
        "count": len(rows),
        "candidates": rows,
    }


def import_run_package(source_path: str, *, target_run_id: str = "", dry_run: bool = True) -> dict[str, Any]:
    source = _resolve_existing_directory(source_path, "Source run package")
    if not _looks_like_run_package(source):
        raise ApiError(400, f"Source is not a recognized run package: {source_path}")
    run_id = target_run_id.strip() if target_run_id else _sanitize_run_id(source.name)
    if not run_id:
        raise ApiError(400, "Could not infer a valid target run id.")
    if not re_match_job_id(run_id):
        raise ApiError(400, "target_run_id may contain only letters, numbers, underscore, and dash.")
    target = (USER_RUNS_DIR / run_id).resolve()
    source_resolved = source.resolve()
    if _same_path(source_resolved, target):
        manifest = read_json_object(source_resolved / "import_manifest.json")
        return build_already_available_import_result(
            source_resolved,
            target,
            run_id,
            dry_run=dry_run,
            manifest=manifest,
            overview=run_overview(source_resolved),
        )
    if target.exists():
        raise ApiError(409, f"Target run package already exists: {target}")
    result = build_import_run_result(
        source_resolved,
        target,
        run_id,
        dry_run=dry_run,
        source_overview=_safe_run_overview(source_resolved),
    )
    if dry_run:
        return result
    USER_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_resolved, target)
    manifest = _write_import_manifest(target, source_resolved, run_id)
    result["manifest_path"] = str(target / "import_manifest.json")
    result["import_manifest"] = manifest
    result["overview"] = run_overview(target)
    return result


def list_example_run_presets() -> dict[str, Any]:
    examples_root = APP_ROOT / "examples"
    rows: list[dict[str, Any]] = []
    if examples_root.exists():
        for path in sorted(examples_root.iterdir()):
            if not path.is_dir() or not _looks_like_run_package(path):
                continue
            preset_id = _sanitize_run_id(path.name)
            overview = _safe_run_overview(path)
            rows.append(
                {
                    "preset_id": preset_id,
                    "name": path.name,
                    "source_path": str(path.resolve()),
                    "suggested_target_run_id": _next_available_run_id(preset_id),
                    "input_count": overview.get("input_count", 0),
                    "model_variant_count": overview.get("model_variant_count", 0),
                    "report_count": overview.get("report_count", 0),
                    "visualization_count": overview.get("visualization_count", 0),
                    "last_modified": overview.get("last_modified", 0),
                    "import_status": "target_exists" if (USER_RUNS_DIR / preset_id).exists() else "importable",
                }
            )
    return {
        "examples_root": str(examples_root),
        "workspace_root": str(WORKSPACE_ROOT),
        "user_runs_dir": str(USER_RUNS_DIR),
        "count": len(rows),
        "presets": rows,
    }


def import_example_run_preset(preset_id: str, *, target_run_id: str = "", dry_run: bool = True) -> dict[str, Any]:
    normalized = _sanitize_run_id(preset_id)
    if not normalized or normalized != preset_id:
        raise ApiError(400, "Invalid preset_id.")
    source = (APP_ROOT / "examples" / normalized).resolve()
    if not source.exists() or not source.is_dir() or not _looks_like_run_package(source):
        raise ApiError(404, f"Example run preset not found: {preset_id}")
    target = target_run_id.strip() if target_run_id else _next_available_run_id(normalized)
    result = import_run_package(str(source), target_run_id=target, dry_run=dry_run)
    result["preset_id"] = normalized
    result["preset_source"] = "builtin_example"
    if result.get("import_manifest"):
        manifest = dict(result["import_manifest"])
        manifest["preset_id"] = normalized
        manifest["preset_source"] = "builtin_example"
        if not dry_run and result.get("manifest_path"):
            write_json(Path(str(result["manifest_path"])), manifest)
        result["import_manifest"] = manifest
    return result


def create_uploaded_run_package(
    *,
    run_id: str = "",
    run_config_json: str = "",
    file_roles: dict[str, Any] | None = None,
    model_file: dict[str, Any] | None = None,
    omics_files: list[dict[str, Any]] | None = None,
    condition_files: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Stage browser-uploaded files into the active workspace as a run package."""

    requested_run_id = _sanitize_run_id(run_id) if run_id else ""
    if run_id and requested_run_id != run_id:
        raise ApiError(400, "run_id may contain only letters, numbers, underscore, and dash.")
    target_run_id = requested_run_id or _next_available_run_id("uploaded_run")
    target = (USER_RUNS_DIR / target_run_id).resolve()
    if target.exists():
        raise ApiError(409, f"Target run package already exists: {target}")

    try:
        run_config = json.loads(run_config_json) if run_config_json.strip() else {}
    except json.JSONDecodeError as exc:
        raise ApiError(400, f"run_config_json is not valid JSON: {exc}") from exc
    if not isinstance(run_config, dict):
        raise ApiError(400, "run_config_json must decode to a JSON object.")

    roles = file_roles or {}
    selected_omics = list(EXPECTED_COLUMNS)
    staged_model: UploadFilePayload | None = None
    if model_file and model_file.get("data"):
        model_name = str(model_file.get("filename") or "model.xml")
        inspection = inspect_model_filename(model_name)
        staged_model = UploadFilePayload(
            filename=model_name,
            data=bytes(model_file.get("data") or b""),
            kind="model",
            role=_role_for_upload(roles, "model", model_name, "gem"),
            columns=[],
            status=inspection.status,
            details=inspection.details,
        )

    staged_omics = [
        _table_upload_payload(file_info, "omics_table", roles, selected_omics)
        for file_info in (omics_files or [])
        if file_info.get("data")
    ]
    staged_conditions = [
        _table_upload_payload(file_info, "condition_table", roles, selected_omics)
        for file_info in (condition_files or [])
        if file_info.get("data")
    ]
    package = stage_user_run_package(
        output_root=USER_RUNS_DIR,
        run_config=run_config,
        model_file=staged_model,
        omics_files=staged_omics,
        condition_files=staged_conditions,
        run_id=target_run_id,
    )
    package_path = Path(package.output_dir)
    manifest = read_json_object(package_path / "upload_manifest.json")
    return {
        "status": package.status,
        "message": package.message,
        "run_id": package.run_id,
        "output_dir": package.output_dir,
        "files": package.files,
        "input_rows": package.input_rows,
        "manifest": manifest,
        "overview": run_overview(package_path),
    }


def _table_upload_payload(
    file_info: dict[str, Any],
    kind: str,
    roles: dict[str, Any],
    selected_omics: list[str],
) -> UploadFilePayload:
    filename = str(file_info.get("filename") or "table.csv")
    data = bytes(file_info.get("data") or b"")
    inspection = inspect_table_file(io.BytesIO(data), filename, selected_omics)
    fallback_role = choose_default_role(filename, inspection.columns, selected_omics)
    if kind == "condition_table":
        fallback_role = _infer_condition_role(filename)
    role = _role_for_upload(roles, "condition" if kind == "condition_table" else "omics", filename, fallback_role)
    return UploadFilePayload(
        filename=filename,
        data=data,
        kind=kind,
        role=role,
        columns=inspection.columns,
        status=inspection.status,
        details=inspection.details,
    )


def _role_for_upload(roles: dict[str, Any], section: str, filename: str, fallback: str) -> str:
    direct = roles.get(filename)
    section_map = roles.get(section)
    if direct:
        return str(direct)
    if isinstance(section_map, dict) and section_map.get(filename):
        return str(section_map[filename])
    files_map = roles.get("files")
    if isinstance(files_map, dict) and files_map.get(filename):
        return str(files_map[filename])
    return fallback or IGNORE_ROLE


def _infer_condition_role(filename: str) -> str:
    name = filename.lower()
    if "exchange" in name or "bound" in name:
        return "condition_exchange_bounds"
    if "medium" in name or "environment" in name:
        return "condition_environment"
    if "growth" in name or "phenotype" in name:
        return "phenotype_growth"
    return "condition_table"


def get_run_import_manifest(run_id: str) -> dict[str, Any]:
    package = resolve_run_package(run_id)
    manifest_path = package / "import_manifest.json"
    manifest = read_json_object(manifest_path)
    return build_import_manifest_response(package, manifest_path, manifest)


def archive_run_package(run_id: str, *, dry_run: bool = True, confirm_run_id: str = "") -> dict[str, Any]:
    if not run_id or not re_match_job_id(run_id):
        raise ApiError(400, "Invalid run_id.")
    source = (USER_RUNS_DIR / run_id).resolve()
    if not source.exists() or not source.is_dir():
        try:
            resolve_run_package(run_id)
        except ApiError as exc:
            raise exc
        raise ApiError(403, "Only run packages under the active workspace user_runs directory can be archived.")
    if not _is_relative_to(source, USER_RUNS_DIR.resolve()):
        raise ApiError(403, "Archive is restricted to active workspace user_runs.")
    if not _looks_like_run_package(source):
        raise ApiError(400, f"Source is not a recognized run package: {run_id}")
    archive_root = WORKSPACE_ROOT / "archived_runs"
    target = (archive_root / run_id).resolve()
    if target.exists():
        suggested = _next_available_archive_id(run_id)
        raise ApiError(409, f"Archived target already exists: {target}. Suggested target id: {suggested}")
    result = build_archive_run_result(
        source,
        target,
        run_id,
        dry_run=dry_run,
        workspace_root=WORKSPACE_ROOT,
        archive_root=archive_root,
    )
    if dry_run:
        return result
    if confirm_run_id != run_id:
        raise ApiError(400, "Set confirm_run_id to the exact run_id before archiving.")
    archive_root.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    manifest = _write_archive_manifest(target, source, run_id)
    result["manifest_path"] = str(target / "archive_manifest.json")
    result["archive_manifest"] = manifest
    return result


def create_archive_run_job(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    dry_run = bool(payload.get("dry_run", True))
    confirm_run_id = str(payload.get("confirm_run_id", ""))
    if not dry_run and confirm_run_id != run_id:
        raise ApiError(400, "Set confirm_run_id to the exact run_id before archiving.")
    # Validate source/target safety before creating a job record.
    archive_run_package(run_id, dry_run=True)
    final_status = "skipped" if dry_run else "completed"

    def callback(log_path: Path) -> dict[str, Any]:
        lines = build_run_package_job_header_lines("Run archive job.", run_id, dry_run=dry_run)
        log_path.write_text("\n".join(lines), encoding="utf-8")
        result = archive_run_package(run_id, dry_run=dry_run, confirm_run_id=confirm_run_id)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(build_run_package_job_result_lines(result)))
            handle.write("\n")
        return {**result, "result_status": result.get("status", "")}

    return run_sync_job("run_archive", run_id, callback, final_status=final_status)


def list_archived_runs() -> list[dict[str, Any]]:
    archive_root = WORKSPACE_ROOT / "archived_runs"
    if not archive_root.exists() or not archive_root.is_dir():
        return []
    rows = [_archived_run_overview(path) for path in archive_root.iterdir() if path.is_dir()]
    return sorted(rows, key=lambda row: str(row.get("archived_at") or row.get("last_modified") or ""), reverse=True)


def get_archived_run_manifest(run_id: str) -> dict[str, Any]:
    source = _resolve_archived_run(run_id)
    manifest_path = source / "archive_manifest.json"
    manifest = read_json_object(manifest_path)
    return build_archived_manifest_response(source, manifest_path, manifest)


def restore_archived_run_package(run_id: str, *, dry_run: bool = True, confirm_run_id: str = "") -> dict[str, Any]:
    source = _resolve_archived_run(run_id)
    if not _looks_like_run_package(source):
        raise ApiError(400, f"Archived source is not a recognized run package: {run_id}")
    target = (USER_RUNS_DIR / run_id).resolve()
    if target.exists():
        raise ApiError(409, f"Active run package already exists: {target}")
    result = build_restore_run_result(
        source,
        target,
        run_id,
        dry_run=dry_run,
        workspace_root=WORKSPACE_ROOT,
        archive_root=WORKSPACE_ROOT / "archived_runs",
        user_runs_dir=USER_RUNS_DIR,
    )
    if dry_run:
        return result
    if confirm_run_id != run_id:
        raise ApiError(400, "Set confirm_run_id to the exact run_id before restoring.")
    USER_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    manifest = _write_restore_manifest(target, source, run_id)
    result["manifest_path"] = str(target / "restore_manifest.json")
    result["restore_manifest"] = manifest
    result["overview"] = run_overview(target)
    return result


def create_restore_archived_run_job(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    dry_run = bool(payload.get("dry_run", True))
    confirm_run_id = str(payload.get("confirm_run_id", ""))
    if not dry_run and confirm_run_id != run_id:
        raise ApiError(400, "Set confirm_run_id to the exact run_id before restoring.")
    # Validate source/target safety before creating a job record.
    restore_archived_run_package(run_id, dry_run=True)
    final_status = "skipped" if dry_run else "completed"

    def callback(log_path: Path) -> dict[str, Any]:
        lines = build_run_package_job_header_lines("Archived run restore job.", run_id, dry_run=dry_run)
        log_path.write_text("\n".join(lines), encoding="utf-8")
        result = restore_archived_run_package(run_id, dry_run=dry_run, confirm_run_id=confirm_run_id)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(build_run_package_job_result_lines(result)))
            handle.write("\n")
        return {**result, "result_status": result.get("status", "")}

    return run_sync_job("run_restore", run_id, callback, final_status=final_status)


def list_runs() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for package in _iter_run_packages():
        rows.append(run_overview(package))
    return sorted(rows, key=lambda row: str(row.get("last_modified", "")), reverse=True)


def run_summary(run_id: str) -> dict[str, Any]:
    package = resolve_run_package(run_id)
    input_rows = read_csv_rows(package / "input_file_map.csv")
    registry_rows = read_model_variant_registry(package)
    report_files = _relative_files(package, package / "report_results", "*.html")
    visualization_manifests = _relative_files(package, package / "visualization_results" / "sammi", "*/sammi_package_manifest.json")
    pipeline_manifest = read_json_object(package / "pipeline_results" / "pipeline_run_manifest.json")
    workflow_selection = read_csv_rows(package / "workflow_results" / "workflow_selection.csv")
    model_generation_parameters = read_csv_rows(package / "workflow_results" / "model_generation_parameters_summary.csv")
    analysis_parameters = read_csv_rows(package / "workflow_results" / "analysis_parameters_summary.csv")
    pipeline_steps = read_csv_rows(package / "pipeline_results" / "pipeline_steps.csv")
    full_audit_report = package / "cobra_results" / "report.html"
    if full_audit_report.exists():
        report_files = [{"name": "full_audit_legacy_report.html", "path": str(full_audit_report), "relative_path": str(full_audit_report.relative_to(package))}] + report_files
    return {
        **run_overview(package),
        "inputs": input_rows,
        "input_statistics": _input_statistics(package, input_rows),
        "model_variants": registry_rows,
        "reports": report_files,
        "visualizations": visualization_manifests,
        "pipeline_manifest": pipeline_manifest,
        "workflow_selection": workflow_selection,
        "model_generation_parameters_summary": model_generation_parameters,
        "analysis_parameters_summary": analysis_parameters,
        "pipeline_steps": pipeline_steps,
    }


def run_variants(run_id: str) -> list[dict[str, str]]:
    return read_model_variant_registry(resolve_run_package(run_id))


def _input_statistics(package: Path, input_rows: list[dict[str, str]]) -> dict[str, Any]:
    role_stats: dict[str, dict[str, Any]] = {}
    row_summaries: list[dict[str, Any]] = []

    def normalize_role(role: str) -> str:
        role = role.lower().strip()
        if role in {"gem", "model", "model_reference"}:
            return "model"
        if role in {"absolute_proteomics", "relative_proteomics", "proteomics"}:
            return role
        if role in {"ml_priors", "kcat", "kcat_priors", "dlkcat_annotation"}:
            return "kcat"
        if role in {"condition", "condition_bounds", "condition_exchange_bounds"}:
            return "condition_bounds"
        if role in {"uniprot_annotation", "custom_annotation", "id_alias_table", "annotation", "alias"}:
            return "annotation"
        return role or "unknown"

    def first_existing_path(row: dict[str, str]) -> Path | None:
        for key in ("path", "relative_path", "file", "saved_name"):
            value = str(row.get(key) or "").strip()
            if not value:
                continue
            candidate = Path(value)
            if not candidate.is_absolute():
                candidate = package / value
            if candidate.exists() and candidate.is_file():
                return candidate
        return None

    def ensure_role(role: str) -> dict[str, Any]:
        stats = role_stats.setdefault(
            role,
            {
                "role": role,
                "file_count": 0,
                "row_count": 0,
                "unique_genes": 0,
                "unique_proteins": 0,
                "unique_reactions": 0,
                "unique_metabolites": 0,
                "unique_conditions": 0,
                "unique_kegg_groups": 0,
                "status": "indexed",
            },
        )
        for key in ("genes", "proteins", "reactions", "metabolites", "conditions", "kegg_groups"):
            stats.setdefault(f"_{key}", set())
        return stats

    def add_values(target: set[str], rows: list[dict[str, str]], keys: set[str]) -> None:
        for data_row in rows:
            lowered = {key.lower().strip(): value for key, value in data_row.items()}
            for key in keys:
                value = str(lowered.get(key) or "").strip()
                if value:
                    target.add(value)

    for input_row in input_rows:
        role = normalize_role(str(input_row.get("role") or input_row.get("kind") or "unknown"))
        stats = ensure_role(role)
        stats["file_count"] = int(stats.get("file_count") or 0) + 1
        path = first_existing_path(input_row)
        details = str(input_row.get("details") or "")
        detail_match = re.search(r"rows\s*=\s*(\d+)", details, flags=re.IGNORECASE)
        detail_rows = int(detail_match.group(1)) if detail_match else 0
        table_rows: list[dict[str, str]] = []
        if path and path.suffix.lower() in {".csv", ".tsv", ".txt"}:
            try:
                table_rows = read_csv_rows(path)
            except (OSError, csv.Error, UnicodeDecodeError):
                table_rows = []
        row_count = len(table_rows) or detail_rows
        stats["row_count"] = int(stats.get("row_count") or 0) + row_count
        if table_rows:
            add_values(stats["_genes"], table_rows, {"gene_id", "model_gene_id", "locus_tag", "source_id"})
            add_values(stats["_proteins"], table_rows, {"protein_id", "uniprot_id", "protein_id_or_gene_id"})
            add_values(stats["_reactions"], table_rows, {"reaction_id", "target_id", "reaction_id_or_enzyme_id"})
            add_values(stats["_metabolites"], table_rows, {"metabolite_id", "compound", "substrate_name"})
            add_values(stats["_conditions"], table_rows, {"condition", "sample", "reference_condition"})
            add_values(stats["_kegg_groups"], table_rows, {"kegg_pathway", "fig_subsystem", "custom_group"})
        row_summaries.append(
            {
                "role": role,
                "path": str(path.relative_to(package)) if path and _is_relative_to(path, package) else str(path or ""),
                "file_name": str(input_row.get("saved_name") or input_row.get("original_name") or (path.name if path else "")),
                "row_count": row_count,
                "columns": str(input_row.get("columns") or ""),
            }
        )

    for stats in role_stats.values():
        for key in ("genes", "proteins", "reactions", "metabolites", "conditions", "kegg_groups"):
            values = stats.pop(f"_{key}", set())
            stats[f"unique_{key}"] = len(values)
    return {
        "roles": role_stats,
        "rows": row_summaries,
        "status": "ready" if input_rows else "missing",
    }


WORKFLOW_UI_STAGE_IDS = (
    "input",
    "model_generator",
    "model_comparison",
    "analysis_visualization",
    "verify_report",
)
WORKFLOW_UI_STAGE_ALIASES = {
    "generate": "model_generator",
    "generator": "model_generator",
    "compare": "model_comparison",
    "analysis": "analysis_visualization",
    "analyze": "analysis_visualization",
    "visualization": "analysis_visualization",
    "verify": "verify_report",
    "report": "verify_report",
}
WORKFLOW_UI_STAGE_LABELS = {
    "input": "Input",
    "model_generator": "Model Generator",
    "model_comparison": "Model Comparison",
    "analysis_visualization": "Analysis & Visualization",
    "verify_report": "Verify & Report",
}


def workflow_state_summary(run_id: str) -> dict[str, Any]:
    package = resolve_run_package(run_id)
    state = _read_workflow_ui_state(package)
    stage_rows = [_workflow_stage_summary(package, stage_id) for stage_id in WORKFLOW_UI_STAGE_IDS]
    latest_jobs = _latest_jobs_for_run(run_id, limit=8)
    ready_count = sum(1 for row in stage_rows if row["status"] == "ready")
    status = "ready" if ready_count == len(stage_rows) else "partial"
    return {
        "run_id": run_id,
        "status": status,
        "state_path": str(_workflow_ui_state_path(package)),
        "state": state,
        "stages": stage_rows,
        "latest_jobs": latest_jobs,
        "guidance": (
            "Five-stage UI state is saved separately from scientific outputs. "
            "Partial stages usually mean the corresponding workflow step has not been run yet."
        ),
    }


def update_workflow_ui_state(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    package = resolve_run_package(run_id)
    existing = _read_workflow_ui_state(package)
    state = _normalize_workflow_ui_state(payload, existing)
    state["updated_at"] = time.time()
    path = _workflow_ui_state_path(package)
    write_json(path, state)
    return {
        "run_id": run_id,
        "status": "saved",
        "state_path": str(path),
        "state": state,
        "summary": workflow_state_summary(run_id),
    }


def run_model_comparison_summary(run_id: str) -> dict[str, Any]:
    package = resolve_run_package(run_id)
    variant_registry = read_model_variant_registry(package)
    comparison_summary = read_csv_rows(package / "variant_comparison" / "variant_comparison_summary.csv")
    flux_comparison = _table_preview(package / "variant_comparison" / "variant_flux_comparison.csv", limit=40)
    evidence_quality = _table_preview(package / "variant_comparison" / "variant_evidence_quality.csv", limit=40)
    structural_diff_summary = _table_preview(package / "variant_comparison" / "model_structural_diff_summary.csv", limit=40)
    reaction_diff = _table_preview(package / "variant_comparison" / "model_reaction_diff.csv", limit=80)
    metabolite_diff = _table_preview(package / "variant_comparison" / "model_metabolite_diff.csv", limit=80)
    gene_gpr_diff = _table_preview(package / "variant_comparison" / "model_gene_gpr_diff.csv", limit=80)
    bound_objective_diff = _table_preview(package / "variant_comparison" / "model_bound_objective_diff.csv", limit=80)
    comparison_interpretation_summary = _table_preview(package / "variant_comparison" / "model_comparison_interpretation_summary.csv", limit=20)
    comparison_layer_status = _table_preview(package / "variant_comparison" / "model_comparison_layer_status.csv", limit=20)
    reaction_drilldown_preview = _table_preview(package / "variant_comparison" / "model_reaction_drilldown.csv", limit=80)
    comparison_axis_summary = _table_preview(package / "variant_comparison" / "model_comparison_axis_summary.csv", limit=20)
    condition_behavior_comparison = _table_preview(package / "variant_comparison" / "condition_behavior_comparison.csv", limit=60)
    gecko_condition_comparison = _table_preview(package / "variant_comparison" / "gecko_condition_comparison.csv", limit=40)
    comparison_story_cards = _table_preview(package / "variant_comparison" / "model_comparison_story_cards.csv", limit=20)
    model_comparison_qc_matrix = _table_preview(package / "variant_comparison" / "model_comparison_qc_matrix.csv", limit=40)
    condition_phenotype_exchange_comparison = _table_preview(package / "variant_comparison" / "condition_phenotype_exchange_comparison.csv", limit=60)
    pathway_flux_comparison = _table_preview(package / "variant_comparison" / "pathway_flux_comparison.csv", limit=80)
    fva_flexibility_comparison = _table_preview(package / "variant_comparison" / "fva_flexibility_comparison.csv", limit=40)
    oxygen_sweep_comparison = _table_preview(package / "variant_comparison" / "oxygen_sweep_comparison.csv", limit=40)
    targeted_essentiality_comparison = _table_preview(package / "variant_comparison" / "targeted_essentiality_comparison.csv", limit=40)
    enzyme_allocation_comparison = _table_preview(package / "variant_comparison" / "enzyme_allocation_comparison.csv", limit=40)
    model_comparison_recommendation_cards = _table_preview(package / "variant_comparison" / "model_comparison_recommendation_cards.csv", limit=20)
    condition_exchange_chart = _table_preview(package / "variant_comparison" / "condition_exchange_chart.csv", limit=80)
    pathway_flux_delta_chart = _table_preview(package / "variant_comparison" / "pathway_flux_delta_chart.csv", limit=80)
    enzyme_pathway_allocation_chart = _table_preview(package / "variant_comparison" / "enzyme_pathway_allocation_chart.csv", limit=80)
    comparison_chart_manifest = _table_preview(package / "variant_comparison" / "comparison_chart_manifest.csv", limit=20)
    production_readiness = _table_preview(package / "production_results" / "production_target_readiness.csv", limit=40)
    manifest_path = package / "variant_comparison" / "variant_comparison_manifest.json"
    gecko_dir = package / "gecko_run_results"
    gecko_manifest = read_json_object(gecko_dir / "gecko_external_run_manifest.json")
    gecko_summary = _table_preview(gecko_dir / "gecko_external_run_summary.csv", limit=20)
    gecko_flux_delta = _table_preview(gecko_dir / "gecko_flux_delta_high_vs_low.csv", limit=40)
    gecko_enzyme_high = _table_preview(gecko_dir / "gecko_enzyme_usage_highO2.csv", limit=20)
    gecko_enzyme_low = _table_preview(gecko_dir / "gecko_enzyme_usage_lowO2.csv", limit=20)
    gecko_interpretation = _gecko_interpretation_summary(
        gecko_manifest=gecko_manifest,
        gecko_summary=gecko_summary,
        flux_delta=gecko_flux_delta,
        enzyme_usage_high=gecko_enzyme_high,
        enzyme_usage_low=gecko_enzyme_low,
    )
    comparison_interpretation_summary = _merge_gecko_interpretation_row(
        comparison_interpretation_summary,
        gecko_interpretation,
    )
    comparison_layer_status = _merge_gecko_layer_status_row(
        comparison_layer_status,
        gecko_interpretation,
    )
    key_files = [
        _file_summary(package, package / "workflow_results" / "model_variant_registry.csv", "model_variant_registry"),
        _file_summary(package, package / "variant_comparison" / "variant_comparison_summary.csv", "variant_comparison_summary"),
        _file_summary(package, package / "variant_comparison" / "variant_flux_comparison.csv", "variant_flux_comparison"),
        _file_summary(package, package / "variant_comparison" / "variant_evidence_quality.csv", "variant_evidence_quality"),
        _file_summary(package, package / "variant_comparison" / "model_structural_diff_summary.csv", "model_structural_diff_summary"),
        _file_summary(package, package / "variant_comparison" / "model_reaction_diff.csv", "model_reaction_diff"),
        _file_summary(package, package / "variant_comparison" / "model_metabolite_diff.csv", "model_metabolite_diff"),
        _file_summary(package, package / "variant_comparison" / "model_gene_gpr_diff.csv", "model_gene_gpr_diff"),
        _file_summary(package, package / "variant_comparison" / "model_bound_objective_diff.csv", "model_bound_objective_diff"),
        _file_summary(package, package / "variant_comparison" / "model_comparison_interpretation_summary.csv", "model_comparison_interpretation_summary"),
        _file_summary(package, package / "variant_comparison" / "model_comparison_layer_status.csv", "model_comparison_layer_status"),
        _file_summary(package, package / "variant_comparison" / "model_reaction_drilldown.csv", "model_reaction_drilldown"),
        _file_summary(package, package / "variant_comparison" / "model_comparison_axis_summary.csv", "model_comparison_axis_summary"),
        _file_summary(package, package / "variant_comparison" / "condition_behavior_comparison.csv", "condition_behavior_comparison"),
        _file_summary(package, package / "variant_comparison" / "gecko_condition_comparison.csv", "gecko_condition_comparison"),
        _file_summary(package, package / "variant_comparison" / "model_comparison_story_cards.csv", "model_comparison_story_cards"),
        _file_summary(package, package / "variant_comparison" / "model_comparison_qc_matrix.csv", "model_comparison_qc_matrix"),
        _file_summary(package, package / "variant_comparison" / "condition_phenotype_exchange_comparison.csv", "condition_phenotype_exchange_comparison"),
        _file_summary(package, package / "variant_comparison" / "pathway_flux_comparison.csv", "pathway_flux_comparison"),
        _file_summary(package, package / "variant_comparison" / "fva_flexibility_comparison.csv", "fva_flexibility_comparison"),
        _file_summary(package, package / "variant_comparison" / "oxygen_sweep_comparison.csv", "oxygen_sweep_comparison"),
        _file_summary(package, package / "variant_comparison" / "targeted_essentiality_comparison.csv", "targeted_essentiality_comparison"),
        _file_summary(package, package / "variant_comparison" / "enzyme_allocation_comparison.csv", "enzyme_allocation_comparison"),
        _file_summary(package, package / "variant_comparison" / "model_comparison_recommendation_cards.csv", "model_comparison_recommendation_cards"),
        _file_summary(package, package / "variant_comparison" / "condition_exchange_chart.csv", "condition_exchange_chart"),
        _file_summary(package, package / "variant_comparison" / "pathway_flux_delta_chart.csv", "pathway_flux_delta_chart"),
        _file_summary(package, package / "variant_comparison" / "enzyme_pathway_allocation_chart.csv", "enzyme_pathway_allocation_chart"),
        _file_summary(package, package / "variant_comparison" / "comparison_chart_manifest.csv", "comparison_chart_manifest"),
        _file_summary(package, package / "production_results" / "production_target_readiness.csv", "production_target_readiness"),
        _file_summary(package, gecko_dir / "gecko_flux_delta_high_vs_low.csv", "gecko_flux_delta"),
        _file_summary(package, gecko_dir / "gecko_external_run_manifest.json", "gecko_external_run_manifest"),
    ]
    ready = bool(variant_registry) and any(item["exists"] for item in key_files[1:])
    return {
        "run_id": run_id,
        "status": "ready" if ready else "partial",
        "variant_count": len(variant_registry),
        "variant_registry": variant_registry,
        "comparison_summary": comparison_summary,
        "structural_diff_summary": structural_diff_summary,
        "reaction_diff": reaction_diff,
        "metabolite_diff": metabolite_diff,
        "gene_gpr_diff": gene_gpr_diff,
        "bound_objective_diff": bound_objective_diff,
        "comparison_interpretation_summary": comparison_interpretation_summary,
        "comparison_layer_status": comparison_layer_status,
        "reaction_drilldown_preview": reaction_drilldown_preview,
        "comparison_axis_summary": comparison_axis_summary,
        "condition_behavior_comparison": condition_behavior_comparison,
        "gecko_condition_comparison": gecko_condition_comparison,
        "comparison_story_cards": comparison_story_cards,
        "model_comparison_qc_matrix": model_comparison_qc_matrix,
        "condition_phenotype_exchange_comparison": condition_phenotype_exchange_comparison,
        "pathway_flux_comparison": pathway_flux_comparison,
        "fva_flexibility_comparison": fva_flexibility_comparison,
        "oxygen_sweep_comparison": oxygen_sweep_comparison,
        "targeted_essentiality_comparison": targeted_essentiality_comparison,
        "enzyme_allocation_comparison": enzyme_allocation_comparison,
        "model_comparison_recommendation_cards": model_comparison_recommendation_cards,
        "condition_exchange_chart": condition_exchange_chart,
        "pathway_flux_delta_chart": pathway_flux_delta_chart,
        "enzyme_pathway_allocation_chart": enzyme_pathway_allocation_chart,
        "comparison_chart_manifest": comparison_chart_manifest,
        "flux_comparison": flux_comparison,
        "evidence_quality": evidence_quality,
        "production_target_readiness": production_readiness,
        "comparison_manifest": read_json_object(manifest_path),
        "gecko_interpretation_summary": gecko_interpretation,
        "gecko": {
            "manifest": gecko_manifest,
            "summary": gecko_summary,
            "flux_delta": gecko_flux_delta,
            "enzyme_usage_highO2": gecko_enzyme_high,
            "enzyme_usage_lowO2": gecko_enzyme_low,
        },
        "key_files": key_files,
        "guidance": (
            "Use this summary to compare the original GEM, context variants, and enzyme-constrained outputs. "
            "Missing comparison files indicate that the comparison workflow has not been generated yet."
        ),
    }


def run_annotation_groups(run_id: str) -> dict[str, Any]:
    """Build a read-only annotation group index for submap rendering.

    The index is intentionally lightweight: it aggregates existing model notes,
    uploaded annotation tables, rendered graph metadata, and prepared case
    pathway indexes without launching solvers or online annotation.
    """

    package = resolve_run_package(run_id)
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    warnings: list[str] = []

    def add_group(
        annotation_type: str,
        group_id: str,
        name: str,
        reaction_ids: list[str] | set[str],
        *,
        source: str,
        confidence: str = "medium",
        renderable: bool = True,
        graph_path: str = "",
        warning: str = "",
    ) -> None:
        clean_type = _normalize_annotation_type(annotation_type)
        clean_group = str(group_id or name or "").strip()
        if not clean_type or not clean_group:
            return
        clean_name = str(name or clean_group).strip()
        key = (clean_type, clean_group)
        entry = groups.get(key)
        if entry is None:
            entry = {
                "type": clean_type,
                "id": clean_group,
                "name": clean_name,
                "label": clean_name,
                "reaction_ids": [],
                "sample_reaction_ids": [],
                "reaction_count": 0,
                "source": source,
                "confidence": confidence,
                "renderable": renderable,
                "graph_path": graph_path,
                "warnings": [],
            }
            groups[key] = entry
        elif _source_priority(source) > _source_priority(str(entry.get("source") or "")):
            entry["source"] = source
            entry["confidence"] = confidence
            entry["renderable"] = renderable
            if graph_path:
                entry["graph_path"] = graph_path
        existing = {str(item) for item in entry.get("reaction_ids", [])}
        for reaction_id in reaction_ids:
            clean_reaction = str(reaction_id or "").strip()
            if not clean_reaction or clean_reaction in existing:
                continue
            entry["reaction_ids"].append(clean_reaction)
            existing.add(clean_reaction)
        if graph_path and not entry.get("graph_path"):
            entry["graph_path"] = graph_path
        if warning and warning not in entry["warnings"]:
            entry["warnings"].append(warning)

    _collect_prepared_shewanella_annotation_groups(run_id, add_group)
    _collect_graph_annotation_groups(package, add_group)
    _collect_model_functional_annotation_groups(package, add_group, warnings)
    _collect_uploaded_annotation_groups(package, add_group, warnings)
    _collect_gene_annotation_groups(package, add_group, warnings)
    _collect_case_paper_evidence_annotation_groups(package, add_group)
    _collect_sbml_note_annotation_groups(package, add_group, warnings)

    flat_groups = []
    for entry in groups.values():
        reaction_ids = sorted({str(item) for item in entry.get("reaction_ids", []) if str(item).strip()})
        entry["reaction_ids"] = reaction_ids
        entry["sample_reaction_ids"] = reaction_ids[:8]
        entry["reaction_count"] = len(reaction_ids)
        flat_groups.append(entry)

    flat_groups = [group for group in flat_groups if int(group.get("reaction_count") or 0) > 0]
    flat_groups.sort(
        key=lambda group: (
            _annotation_type_priority(str(group.get("type") or "")),
            -int(group.get("reaction_count") or 0),
            str(group.get("name") or "").lower(),
        )
    )
    by_type: dict[str, dict[str, Any]] = {}
    for group in flat_groups:
        annotation_type = str(group.get("type") or "")
        bucket = by_type.get(annotation_type)
        if bucket is None:
            bucket = {
                "type": annotation_type,
                "label": _annotation_type_label(annotation_type),
                "source": group.get("source") or "mixed",
                "confidence": group.get("confidence") or "medium",
                "group_count": 0,
                "reaction_count": 0,
                "groups": [],
            }
            by_type[annotation_type] = bucket
        bucket["groups"].append(group)
        bucket["group_count"] = len(bucket["groups"])
        bucket["reaction_count"] = int(bucket["reaction_count"]) + int(group.get("reaction_count") or 0)
        if _source_priority(str(group.get("source") or "")) > _source_priority(str(bucket.get("source") or "")):
            bucket["source"] = group.get("source") or bucket["source"]
            bucket["confidence"] = group.get("confidence") or bucket["confidence"]

    annotation_types = sorted(
        by_type.values(),
        key=lambda item: (_annotation_type_priority(str(item.get("type") or "")), str(item.get("label") or "")),
    )
    status = "ready" if flat_groups else "partial"
    guidance = (
        "Annotation groups are available for submap rendering."
        if flat_groups
        else "No annotation groups were detected. Upload an annotation table with reaction_id and subsystem, KEGG pathway, EC, or custom group columns."
    )
    return {
        "run_id": run_id,
        "status": status,
        "annotation_types": annotation_types,
        "groups": flat_groups,
        "warnings": warnings,
        "guidance": guidance,
    }


def _collect_prepared_shewanella_annotation_groups(run_id: str, add_group: Callable[..., None]) -> None:
    if "shewanella" not in str(run_id or "").lower():
        return
    maps_root = APP_ROOT / "case_studies" / "shewanella_gecko_case_study" / "visualization" / "kegg_pathway_maps"
    summary_rows = read_csv_rows(maps_root / "kegg_pathway_summary.csv")
    assignment_rows = read_csv_rows(maps_root / "reaction_kegg_pathway_assignment.csv")
    if not summary_rows or not assignment_rows:
        return
    reactions_by_pathway: dict[str, set[str]] = {}
    for row in assignment_rows:
        pathway_id = str(row.get("pathway_id") or row.get("pathway") or "").strip()
        if not pathway_id:
            continue
        bucket = reactions_by_pathway.setdefault(pathway_id, set())
        for key in ("reaction_id", "cobra_reaction_id", "kegg_reaction_id"):
            value = str(row.get(key) or "").strip()
            if value:
                bucket.add(value)
    for row in summary_rows:
        if str(row.get("status") or "").lower() not in {"completed", "ready", "ok"}:
            continue
        pathway_id = str(row.get("pathway_id") or "").strip()
        pathway_name = str(row.get("pathway_name") or pathway_id or "").strip()
        if not pathway_id:
            continue
        interactive_rel = str(row.get("interactive_map") or "").strip()
        folder = re.sub(r"[\\/]*interactive_map\.html$", "", interactive_rel, flags=re.IGNORECASE)
        graph_path = maps_root / folder / "network_graph.json" if folder else maps_root / pathway_id / "network_graph.json"
        add_group(
            "kegg_pathway",
            pathway_id,
            pathway_name or pathway_id,
            reactions_by_pathway.get(pathway_id, set()),
            source="prepared_case_index",
            confidence="high",
            renderable=graph_path.exists(),
            graph_path=str(graph_path) if graph_path.exists() else "",
        )


def _collect_graph_annotation_groups(package: Path, add_group: Callable[..., None]) -> None:
    sammi_root = package / "visualization_results" / "sammi"
    if not sammi_root.exists():
        return
    for graph_path in sammi_root.glob("*/network_graph.json"):
        graph = read_json_object(graph_path)
        for node in graph.get("nodes") or []:
            if not isinstance(node, dict) or str(node.get("node_type") or "") != "reaction":
                continue
            raw_id = str(node.get("group_id") or node.get("subsystem") or node.get("group_label") or "").strip()
            raw_label = str(node.get("group_label") or node.get("subsystem") or node.get("group_id") or raw_id).strip()
            if not raw_id or _is_unannotated_group(raw_id, raw_label):
                continue
            annotation_type = "kegg_pathway" if _looks_like_kegg_group(raw_id, raw_label) else "subsystem"
            reaction_id = str(node.get("id") or node.get("label") or "").strip()
            add_group(
                annotation_type,
                raw_id,
                raw_label or raw_id,
                [reaction_id] if reaction_id else [],
                source="rendered_graph",
                confidence="medium",
                renderable=True,
            )


def _collect_model_functional_annotation_groups(package: Path, add_group: Callable[..., None], warnings: list[str]) -> None:
    model_path = _first_package_model_path(package)
    if model_path is None:
        return
    parsed = _parse_model_structure(model_path)
    if getattr(parsed, "status", "") != "parsed":
        warnings.append(f"Could not build functional reaction groups from {model_path}: {getattr(parsed, 'guidance', '')}")
        return
    for reaction_id, reaction in parsed.reactions.items():
        group = _reaction_functional_group(reaction_id, str(reaction.get("name") or ""))
        if not group or group == "other_internal_flux":
            continue
        add_group(
            "kegg_pathway",
            group,
            group,
            [reaction_id],
            source="functional_hint",
            confidence="low",
            renderable=True,
            warning="Functional group was inferred from reaction identifiers/names because no curated pathway assignment was available.",
        )


def _collect_uploaded_annotation_groups(package: Path, add_group: Callable[..., None], warnings: list[str]) -> None:
    for row in read_csv_rows(package / "input_file_map.csv"):
        candidate = _input_row_path(package, row)
        if not candidate.exists() or candidate.suffix.lower() not in {".csv", ".tsv"}:
            continue
        text = " ".join(str(row.get(key) or "") for key in ("role", "kind", "original_name", "saved_name", "columns", "details")).lower()
        rows = read_csv_rows(candidate)
        if not rows:
            continue
        headers = {key.lower(): key for key in rows[0].keys()}
        reaction_col = _first_existing_column(headers, ["reaction_id", "cobra_reaction_id", "model_reaction_id", "reaction", "rxn_id", "bigg_reaction_id"])
        if not reaction_col:
            continue
        annotation_columns = _annotation_columns_from_headers(headers)
        if not annotation_columns and not any(token in text for token in ("annotation", "kegg", "subsystem", "uniprot", "metanetx")):
            continue
        for annotation_type, column_name in annotation_columns:
            for item in rows:
                reaction_id = str(item.get(reaction_col) or "").strip()
                if not reaction_id:
                    continue
                for group_value in _split_annotation_values(item.get(column_name)):
                    add_group(
                        annotation_type,
                        group_value,
                        group_value,
                        [reaction_id],
                        source="uploaded_annotation",
                        confidence="medium",
                        renderable=True,
                    )


def _collect_gene_annotation_groups(package: Path, add_group: Callable[..., None], warnings: list[str]) -> None:
    """Map uploaded gene/protein annotation evidence through model GPRs.

    Several paper-driven cases provide pathway labels for genes or proteins
    rather than direct reaction ids.  For compare submaps those labels are still
    useful if the primary GEM maps the gene to one or more reactions through
    GPR rules.
    """

    gene_to_reactions = _gene_to_reaction_index_for_package(package, warnings)
    if not gene_to_reactions:
        return
    for row in read_csv_rows(package / "input_file_map.csv"):
        candidate = _input_row_path(package, row)
        if not candidate.exists() or candidate.suffix.lower() not in {".csv", ".tsv"}:
            continue
        text = " ".join(str(row.get(key) or "") for key in ("role", "kind", "original_name", "saved_name", "columns", "details")).lower()
        rows = read_csv_rows(candidate)
        if not rows:
            continue
        headers = {key.lower(): key for key in rows[0].keys()}
        gene_columns = [
            column
            for column in (
                _first_existing_column(headers, ["model_gene_id", "gene_id", "gene", "locus_tag"]),
                _first_existing_column(headers, ["protein_id", "protein", "protein_id_or_gene_id", "protein_group", "protein.group"]),
            )
            if column
        ]
        if not gene_columns:
            continue
        annotation_columns = _annotation_columns_from_headers(headers)
        if not annotation_columns and not any(token in text for token in ("annotation", "pathway", "subsystem", "phospho", "marker")):
            continue
        for item in rows:
            mapped_reactions: set[str] = set()
            for column in gene_columns:
                for gene_id in _split_identifier_values(item.get(column)):
                    mapped_reactions.update(gene_to_reactions.get(_normalize_gene_lookup_id(gene_id), set()))
            if not mapped_reactions:
                continue
            for annotation_type, column_name in annotation_columns:
                for group_value in _split_annotation_values(item.get(column_name)):
                    add_group(
                        annotation_type,
                        group_value,
                        group_value,
                        mapped_reactions,
                        source="gene_annotation_gpr",
                        confidence="medium",
                        renderable=True,
                    )


def _collect_case_paper_evidence_annotation_groups(package: Path, add_group: Callable[..., None]) -> None:
    overlay_path = package / "case_study" / "paper_evidence_reaction_overlay.csv"
    if not overlay_path.exists() or overlay_path.stat().st_size == 0:
        return
    rows = read_csv_rows(overlay_path)
    if not rows:
        return
    reactions_by_group: dict[str, set[str]] = {}
    for row in rows:
        if str(row.get("mapping_status") or "").strip().lower() not in {"mapped", "paper_evidence_mapped"}:
            continue
        group_id = str(row.get("custom_group") or "").strip()
        reaction_id = str(row.get("reaction_id") or "").strip()
        if not group_id or not reaction_id:
            continue
        reactions_by_group.setdefault(group_id, set()).add(reaction_id)
    for group_id, reaction_ids in reactions_by_group.items():
        add_group(
            "custom_annotation",
            group_id,
            group_id.replace("_", " ").title(),
            reaction_ids,
            source="paper_evidence_gpr_overlay",
            confidence="medium",
            renderable=True,
            warning="Paper-reported gene evidence mapped through model GPR; unmapped genes remain reaction-level unavailable.",
        )


def _gene_to_reaction_index_for_package(package: Path, warnings: list[str]) -> dict[str, set[str]]:
    model_path = _first_package_model_path(package)
    if model_path is None:
        return {}
    parsed = _parse_model_structure(model_path)
    if getattr(parsed, "status", "") != "parsed":
        warnings.append(f"Could not build gene-to-reaction annotation index from {model_path}: {getattr(parsed, 'guidance', '')}")
        return {}
    index: dict[str, set[str]] = {}
    for reaction_id, reaction in parsed.reactions.items():
        for gene_id in _split_identifier_values(reaction.get("gpr", "")):
            key = _normalize_gene_lookup_id(gene_id)
            if key:
                index.setdefault(key, set()).add(reaction_id)
    return index


def _first_package_model_path(package: Path) -> Path | None:
    candidates: list[Path] = []
    for row in read_csv_rows(package / "input_file_map.csv"):
        if str(row.get("kind") or "").lower() == "model" or str(row.get("role") or "").lower() in {"gem", "model", "gsmm"}:
            candidate = _input_row_path(package, row)
            if candidate.exists() and candidate.suffix.lower() in {".xml", ".sbml"}:
                candidates.append(candidate)
    for row in read_model_variant_registry(package):
        for key in ("primary_model_path", "source_model_path", "context_model_sbml"):
            value = str(row.get(key) or "").strip()
            if not value:
                continue
            candidate = Path(value)
            if not candidate.is_absolute():
                candidate = package / value
            if candidate.exists() and candidate.suffix.lower() in {".xml", ".sbml"}:
                candidates.append(candidate)
    return candidates[0] if candidates else None


def _split_identifier_values(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "null", "na", "n/a"}:
        return []
    return [item.strip() for item in re.split(r"[;|,()\s]+", text) if item.strip() and item.strip().lower() not in {"and", "or"}]


def _normalize_gene_lookup_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"^gene[_:-]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^G[_:-]", "", text, flags=re.IGNORECASE)
    text = re.sub(r"[^A-Za-z0-9]+", "", text)
    return text.lower()
def _collect_sbml_note_annotation_groups(package: Path, add_group: Callable[..., None], warnings: list[str]) -> None:
    model_paths: list[Path] = []
    for row in read_csv_rows(package / "input_file_map.csv"):
        if str(row.get("kind") or "").lower() == "model" or str(row.get("role") or "").lower() in {"gem", "model", "gsmm"}:
            candidate = _input_row_path(package, row)
            if candidate.exists() and candidate.suffix.lower() in {".xml", ".sbml"}:
                model_paths.append(candidate)
    for row in read_model_variant_registry(package):
        for key in ("primary_model_path", "source_model_path", "context_model_sbml"):
            value = str(row.get(key) or "").strip()
            if not value:
                continue
            candidate = Path(value)
            if not candidate.is_absolute():
                candidate = package / value
            if candidate.exists() and candidate.suffix.lower() in {".xml", ".sbml"}:
                model_paths.append(candidate)
    seen = set()
    for model_path in model_paths:
        resolved = str(model_path.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            text = model_path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            warnings.append(f"Could not read model annotations from {model_path}: {exc}")
            continue
        for match in re.finditer(r"<reaction\b[^>]*\bid=[\"']([^\"']+)[\"'][^>]*>(.*?)</reaction>", text, flags=re.IGNORECASE | re.DOTALL):
            reaction_id = match.group(1)
            body = re.sub(r"<[^>]+>", " ", match.group(2))
            subsystem_match = re.search(r"\bSUBSYSTEM\s*:\s*([^;\n\r]+)", body, flags=re.IGNORECASE)
            if subsystem_match:
                subsystem = subsystem_match.group(1).strip()
                if subsystem and not _is_unannotated_group(subsystem, subsystem):
                    add_group(
                        "subsystem",
                        subsystem,
                        subsystem,
                        [reaction_id],
                        source="sbml_notes",
                        confidence="medium",
                        renderable=True,
                    )


def _input_row_path(package: Path, row: dict[str, str]) -> Path:
    value = str(row.get("path") or row.get("relative_path") or "").strip()
    if not value:
        return package / "__missing__"
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return package / value


def _annotation_columns_from_headers(headers: dict[str, str]) -> list[tuple[str, str]]:
    specs = {
        "subsystem": ["subsystem", "fig_subsystem", "bigg_subsystem"],
        "kegg_pathway": ["kegg_pathway", "kegg_pathway_id", "pathway_id", "pathway_name", "pathway"],
        "ec_number": ["ec_number", "ec", "enzyme_ec"],
        "metanetx": ["metanetx", "mnx", "mnx_reaction"],
        "uniprot": ["uniprot", "uniprot_id", "protein_id"],
        "custom_annotation": ["custom_group", "annotation_group", "function", "category"],
    }
    found: list[tuple[str, str]] = []
    for annotation_type, names in specs.items():
        for name in names:
            column = _first_existing_column(headers, [name])
            if column:
                found.append((annotation_type, column))
                break
    return found


def _first_existing_column(headers: dict[str, str], names: list[str]) -> str:
    for name in names:
        if name.lower() in headers:
            return headers[name.lower()]
    return ""


def _split_annotation_values(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "null", "na", "n/a", "unannotated"}:
        return []
    return [item.strip() for item in re.split(r"[;|,]", text) if item.strip()]


def _normalize_annotation_type(value: str) -> str:
    lower = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "kegg": "kegg_pathway",
        "pathway": "kegg_pathway",
        "kegg_pathway_derived_group": "kegg_pathway",
        "ec": "ec_number",
        "ec_numbers": "ec_number",
        "custom": "custom_annotation",
        "annotation": "custom_annotation",
    }
    return aliases.get(lower, lower)


def _annotation_type_label(annotation_type: str) -> str:
    labels = {
        "subsystem": "Subsystem",
        "kegg_pathway": "KEGG pathway",
        "ec_number": "EC number",
        "metanetx": "MetaNetX",
        "uniprot": "UniProt",
        "custom_annotation": "Custom annotation",
    }
    return labels.get(annotation_type, annotation_type.replace("_", " ").title())


def _annotation_type_priority(annotation_type: str) -> int:
    order = {
        "subsystem": 0,
        "kegg_pathway": 1,
        "custom_annotation": 2,
        "ec_number": 3,
        "metanetx": 4,
        "uniprot": 5,
    }
    return order.get(annotation_type, 99)


def _source_priority(source: str) -> int:
    order = {
        "prepared_case_index": 4,
        "uploaded_annotation": 3,
        "gene_annotation_gpr": 3,
        "sbml_notes": 2,
        "functional_hint": 1,
        "rendered_graph": 1,
    }
    return order.get(source, 0)


def _is_unannotated_group(group_id: str, label: str) -> bool:
    text = f"{group_id} {label}".lower()
    return any(token in text for token in ("unannotated", "unknown", "not assigned", "none"))


def _looks_like_kegg_group(group_id: str, label: str) -> bool:
    text = f"{group_id} {label}".lower()
    return bool(re.search(r"\b(rn|map)\d{5}\b", group_id, flags=re.IGNORECASE)) or "kegg" in text or "pathway" in text


def run_model_comparison_pair_summary(
    run_id: str,
    *,
    reference_variant_id: str = "",
    target_variant_id: str = "",
    grouping: str = "kegg_pathway",
    overlay: str = "none",
    annotation_type: str = "",
    annotation_group_id: str = "",
    reference_annotation_group_id: str = "",
    target_annotation_group_id: str = "",
) -> dict[str, Any]:
    """Return a lightweight pair-specific model comparison without launching analyses."""

    package = resolve_run_package(run_id)
    registry_rows = read_model_variant_registry(package)
    if not registry_rows:
        return {
            "run_id": run_id,
            "status": "partial",
            "reference_variant_id": "",
            "target_variant_id": "",
            "grouping": grouping or "kegg_pathway",
            "overlay": overlay or "none",
            "annotation_type": annotation_type,
            "annotation_group_id": annotation_group_id,
            "variant_registry": [],
            "pair_summary": [],
            "reaction_diff": [],
            "constraint_summary": [],
            "network_graphs": {},
            "reaction_external_links": [],
            "guidance": "No model variant registry is available. Run Model Generator first.",
        }

    reference_row, target_row = _select_comparison_pair(registry_rows, reference_variant_id, target_variant_id)
    reference_id = str(reference_row.get("variant_id") or "")
    target_id = str(target_row.get("variant_id") or "")
    reference_model = _variant_model_path(package, reference_row)
    target_model = _variant_model_path(package, target_row)
    parsed_reference = _parse_model_structure(reference_model)
    parsed_target = _parse_model_structure(target_model)
    comparison = _compare_model_structures(target_id or "target", parsed_reference, parsed_target)
    reaction_diff = _reaction_diff_rows(target_id or "target", parsed_reference, parsed_target, comparison)[:120]
    gpr_diff = _pair_gpr_diff_rows(target_id, parsed_reference, parsed_target, comparison)[:80]
    objective_diff = _pair_objective_diff_rows(target_id, parsed_reference, parsed_target, comparison)
    all_reaction_rows = [*reaction_diff, *gpr_diff, *objective_diff]
    enzyme_rows = read_csv_rows(package / "variant_comparison" / "enzyme_allocation_comparison.csv")
    evidence_rows = read_csv_rows(package / "variant_comparison" / "variant_evidence_quality.csv")
    production_rows = read_csv_rows(package / "production_results" / "production_target_readiness.csv")
    pair_summary = [
        {
            "metric": "reference_reactions",
            "reference": len(parsed_reference.reactions),
            "target": len(parsed_target.reactions),
            "status": _pair_metric_status(parsed_reference.status, parsed_target.status),
        },
        {
            "metric": "reaction_changes",
            "reference": "",
            "target": len(comparison.get("added_reactions", set()))
            + len(comparison.get("removed_reactions", set()))
            + len(comparison.get("changed_bounds", set())),
            "status": "changed" if all_reaction_rows else "same_source_or_no_structural_change",
        },
        {
            "metric": "gpr_changes",
            "reference": "",
            "target": len(comparison.get("changed_gpr", set())),
            "status": "changed" if comparison.get("changed_gpr") else "unchanged",
        },
        {
            "metric": "objective_changed",
            "reference": "",
            "target": bool(comparison.get("objective_changed")),
            "status": "changed" if comparison.get("objective_changed") else "unchanged",
        },
    ]
    reference_group_id = reference_annotation_group_id or annotation_group_id
    target_group_id = target_annotation_group_id or annotation_group_id
    scoped_reaction_ids = _selected_annotation_group_reactions(run_id, annotation_type, target_group_id or annotation_group_id)
    reference_scoped_reaction_ids = _selected_annotation_group_reactions(run_id, annotation_type, reference_group_id)
    target_scoped_reaction_ids = _selected_annotation_group_reactions(run_id, annotation_type, target_group_id)
    reference_graph = _variant_network_graph_summary(
        package,
        reference_id,
        grouping=grouping,
        overlay=overlay,
        annotation_type=annotation_type,
        annotation_group_id=reference_group_id,
        reaction_filter=reference_scoped_reaction_ids,
    )
    target_graph = _variant_network_graph_summary(
        package,
        target_id,
        grouping=grouping,
        overlay=overlay,
        annotation_type=annotation_type,
        annotation_group_id=target_group_id,
        reaction_filter=target_scoped_reaction_ids,
    )
    constraint_summary = _pair_constraint_summary(package, enzyme_rows, evidence_rows, production_rows)
    gecko_flux_rows = read_csv_rows(package / "gecko_run_results" / "gecko_flux_delta_high_vs_low.csv")
    kcat_provenance_index = _kcat_provenance_index(package)
    behavior_signal_index, behavior_context_summary = _behavior_signal_index(package)
    behavior_support_index, behavior_support_context = _behavior_support_index(package)
    reaction_detail_index = _pair_reaction_detail_index(
        package=package,
        reference=parsed_reference,
        target=parsed_target,
        comparison=comparison,
        reference_graph=reference_graph,
        target_graph=target_graph,
        diff_rows=all_reaction_rows,
        kcat_provenance_index=kcat_provenance_index,
    )
    reaction_diff_index = _reaction_diff_index_from_pair_details(
        reaction_detail_index,
        comparison=comparison,
        behavior_signal_index=behavior_signal_index,
        behavior_context_summary=behavior_context_summary,
        behavior_support_index=behavior_support_index,
        behavior_support_context=behavior_support_context,
    )
    submap_evidence_summary = _submap_evidence_summary(
        reaction_diff_index,
        scoped_reaction_ids=scoped_reaction_ids,
        comparison_label=str(comparison.get("label") or ""),
    )
    pair_difference_summary = _pair_difference_summary(
        reaction_diff_index,
        comparison=comparison,
        reference_id=reference_id,
        target_id=target_id,
        annotation_type=annotation_type,
        annotation_group_id=annotation_group_id,
        behavior_context_summary=behavior_context_summary,
        behavior_support_context=behavior_support_context,
    )
    difference_ranking = _difference_ranking(reaction_diff_index)
    merged_difference_graph = _merged_difference_graph(reference_graph, target_graph, reaction_diff_index)
    edit_rows = read_model_edit_reaction_index(package)
    model_edit_diff_index = build_model_edit_diff_index(
        reference_variant_id=reference_id,
        target_variant_id=target_id,
        edit_rows=edit_rows,
        fallback_reaction_diff_index=reaction_diff_index,
    )
    edit_summary = edit_context_summary(model_edit_diff_index)
    reference_edit_graph = overlay_edit_graph(
        read_json_object(Path(str(reference_graph.get("path") or ""))) if reference_graph.get("path") else {},
        side="reference",
        diff_index=model_edit_diff_index,
    )
    target_edit_graph = overlay_edit_graph(
        read_json_object(Path(str(target_graph.get("path") or ""))) if target_graph.get("path") else {},
        side="target",
        diff_index=model_edit_diff_index,
    )
    reaction_match_index = _pair_reaction_match_index(reaction_detail_index)
    overlay_availability = _pair_overlay_availability(
        overlay=overlay or "none",
        constraint_summary=constraint_summary,
        gecko_flux_rows=gecko_flux_rows,
        reference_graph=reference_graph,
        target_graph=target_graph,
    )
    annotation_scope = {
        "reaction_count": len(scoped_reaction_ids),
        "reaction_ids": scoped_reaction_ids[:200],
        "status": "ready" if scoped_reaction_ids else ("not_selected" if not annotation_group_id else "not_mapped"),
    }
    graph_ready = reference_graph.get("status") == "ready" and target_graph.get("status") == "ready"
    parse_ready = parsed_reference.status == "parsed" and parsed_target.status == "parsed"
    status = "ready" if parse_ready else "partial"
    if not graph_ready:
        status = "partial"
    compare_readiness_summary = _compare_readiness_summary(
        parse_ready=parse_ready,
        graph_ready=graph_ready,
        annotation_scope=annotation_scope,
        submap_evidence_summary=submap_evidence_summary,
        pair_difference_summary=pair_difference_summary,
        behavior_context_summary=behavior_context_summary,
        behavior_support_context=behavior_support_context,
    )
    return {
        "run_id": run_id,
        "status": status,
        "reference_variant_id": reference_id,
        "target_variant_id": target_id,
        "grouping": grouping or "kegg_pathway",
        "overlay": overlay or "none",
        "annotation_type": annotation_type,
        "annotation_group_id": annotation_group_id,
        "reference_annotation_group_id": reference_group_id,
        "target_annotation_group_id": target_group_id,
        "annotation_group_scope": annotation_scope,
        "reference_variant": reference_row,
        "target_variant": target_row,
        "pair_summary": pair_summary,
        "structural_status": {
            "reference_parse_status": parsed_reference.status,
            "target_parse_status": parsed_target.status,
            "comparison_label": comparison.get("label", "partial"),
            "reaction_added_count": len(comparison.get("added_reactions", set())),
            "reaction_removed_count": len(comparison.get("removed_reactions", set())),
            "reaction_changed_bounds_count": len(comparison.get("changed_bounds", set())),
            "gpr_changed_count": len(comparison.get("changed_gpr", set())),
            "objective_changed": bool(comparison.get("objective_changed")),
            "guidance": comparison.get("guidance", ""),
        },
        "reaction_diff": all_reaction_rows,
        "constraint_summary": constraint_summary,
        "reaction_detail_index": reaction_detail_index,
        "reaction_diff_index": reaction_diff_index,
        "pair_difference_summary": pair_difference_summary,
        "submap_evidence_summary": submap_evidence_summary,
        "edit_context_summary": edit_summary,
        "model_edit_diff_index": model_edit_diff_index,
        "compare_readiness_summary": compare_readiness_summary,
        "case_compare_guidance": _case_compare_guidance(
            run_id,
            submap_evidence_summary=submap_evidence_summary,
            behavior_context_summary=behavior_context_summary,
            behavior_support_context=behavior_support_context,
        ),
        "difference_ranking": difference_ranking,
        "merged_difference_graph": merged_difference_graph,
        "reaction_match_index": reaction_match_index,
        "overlay_availability": overlay_availability,
        "network_graphs": {
            "reference": reference_graph,
            "target": target_graph,
            "reference_edit": reference_edit_graph,
            "target_edit": target_edit_graph,
        },
        "reaction_external_links": _reaction_external_link_rows([*all_reaction_rows, *reaction_detail_index, *reaction_diff_index]),
        "key_files": [
            _file_summary(package, package / "workflow_results" / "model_variant_registry.csv", "model_variant_registry"),
            _file_summary(package, package / "variant_comparison" / "model_reaction_diff.csv", "model_reaction_diff"),
            _file_summary(package, package / "variant_comparison" / "enzyme_allocation_comparison.csv", "enzyme_allocation_comparison"),
            _file_summary(package, Path(str(reference_graph.get("path") or package / "__missing_reference_graph__.json")), "reference_network_graph"),
            _file_summary(package, Path(str(target_graph.get("path") or package / "__missing_target_graph__.json")), "target_network_graph"),
        ],
        "guidance": _pair_comparison_guidance(
            parse_ready=parse_ready,
            graph_ready=graph_ready,
            comparison_label=str(comparison.get("label", "")),
            grouping=grouping,
        ),
    }


def _select_comparison_pair(
    registry_rows: list[dict[str, str]],
    reference_variant_id: str,
    target_variant_id: str,
) -> tuple[dict[str, str], dict[str, str]]:
    by_id = {str(row.get("variant_id") or ""): row for row in registry_rows}
    reference = by_id.get(reference_variant_id)
    if reference is None:
        reference = next((row for row in registry_rows if "baseline" in str(row.get("variant_id") or "").lower()), registry_rows[0])
    target = by_id.get(target_variant_id)
    if target is None or target is reference:
        target = next((row for row in registry_rows if str(row.get("variant_id") or "") != str(reference.get("variant_id") or "")), reference)
    return reference, target


def _selected_annotation_group_reactions(run_id: str, annotation_type: str, annotation_group_id: str) -> list[str]:
    if not annotation_type or not annotation_group_id:
        return []
    try:
        groups_payload = run_annotation_groups(run_id)
    except Exception:
        return []
    wanted_type = _normalize_annotation_type(annotation_type)
    wanted_group = str(annotation_group_id or "").strip()
    for group in groups_payload.get("groups") or []:
        if str(group.get("type") or "") == wanted_type and str(group.get("id") or "") == wanted_group:
            return sorted({str(item).strip() for item in group.get("reaction_ids") or [] if str(item).strip()})
    return []


def _variant_model_path(package: Path, row: dict[str, str]) -> Path | None:
    for key in ("primary_model_path", "context_model_sbml", "primary_artifact", "source_model_path"):
        value = str(row.get(key) or "").strip()
        if not value:
            continue
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = package / value
        return candidate.resolve()
    return None


def _variant_network_graph_summary(
    package: Path,
    variant_id: str,
    *,
    grouping: str = "subsystem",
    overlay: str = "none",
    annotation_type: str = "",
    annotation_group_id: str = "",
    reaction_filter: list[str] | None = None,
) -> dict[str, Any]:
    safe_variant = str(variant_id or "").replace("/", "_").replace("\\", "_")
    scoped_filter = [str(item).strip() for item in (reaction_filter or []) if str(item).strip()]
    scoped_graph_path: Path | None = None
    if scoped_filter and annotation_type and annotation_group_id:
        scoped_dir = (
            package
            / "visualization_results"
            / "compare_submaps"
            / safe_variant_dir_name(variant_id or "variant")
            / _safe_file_segment(annotation_type)
            / _safe_file_segment(annotation_group_id)
            / _safe_file_segment(_sammi_overlay_from_compare_overlay(overlay))
        )
        scoped_graph_path = scoped_dir / "network_graph.json"
        if not scoped_graph_path.exists():
            try:
                build_sammi_interactive_render(
                    package,
                    variant_id=variant_id,
                    grouping_mode=grouping or "subsystem",
                    overlay_source=_sammi_overlay_from_compare_overlay(overlay),
                    reaction_filter=scoped_filter,
                    output_dir=scoped_dir,
                    top_n=max(120, min(400, len(scoped_filter) + 40)),
                )
            except Exception as exc:
                return {
                    "status": "render_failed",
                    "variant_id": variant_id,
                    "path": "",
                    "source": "annotation_group_render_failed",
                    "guidance": f"Could not render annotation group graph: {type(exc).__name__}: {exc}",
                    "filter": {
                        "reaction_filter": ";".join(scoped_filter[:80]),
                        "annotation_type": annotation_type,
                        "annotation_group_id": annotation_group_id,
                    },
                }
    candidates = [
        scoped_graph_path if scoped_graph_path is not None else None,
        package / "visualization_results" / "sammi" / safe_variant / "network_graph.json",
        package / "visualization_results" / "sammi" / safe_variant / "interactive_network" / "network_graph.json",
    ]
    graph_path = next((path for path in candidates if path is not None and path.exists()), None)
    default_manifest_path = package / "visualization_results" / "sammi" / safe_variant / "interactive_map_manifest.json"
    manifest = read_json_object(scoped_graph_path.parent / "interactive_map_manifest.json") if scoped_graph_path is not None else read_json_object(default_manifest_path)
    if graph_path is None:
        for manifest_path in (package / "visualization_results" / "sammi").glob("*/interactive_map_manifest.json"):
            item = read_json_object(manifest_path)
            if str(item.get("variant_id") or "") == variant_id:
                files = item.get("files") if isinstance(item.get("files"), dict) else {}
                graph_text = str(files.get("graph") or "").strip()
                if graph_text:
                    candidate = Path(graph_text)
                    if not candidate.is_absolute():
                        candidate = manifest_path.parent / graph_text
                    if candidate.exists():
                        graph_path = candidate
                        manifest = item
                        break
    if graph_path is None:
        return {
            "status": "missing",
            "variant_id": variant_id,
            "path": "",
            "source": "missing_pair_graph",
            "guidance": "No rendered network_graph.json was found for this variant. Render a map in Analysis first.",
        }
    summary_rows = read_csv_rows(graph_path.parent / "interactive_map_summary.csv")
    summary = summary_rows[0] if summary_rows else {}
    graph = read_json_object(graph_path)
    graph_summary = graph.get("summary") if isinstance(graph.get("summary"), dict) else {}
    graph_status = str(
        summary.get("status")
        or graph_summary.get("status")
        or graph.get("status")
        or manifest.get("status")
        or "ready"
    )
    node_count = summary.get("node_count") or graph_summary.get("node_count") or len(graph.get("nodes") or []) or manifest.get("node_count") or ""
    link_count = summary.get("link_count") or graph_summary.get("link_count") or len(graph.get("links") or []) or manifest.get("link_count") or ""
    display_status = "ready"
    guidance = ""
    if graph_status and graph_status not in {"ready", "ok", "completed"}:
        display_status = graph_status
        guidance = str(summary.get("message") or graph_summary.get("message") or graph.get("message") or manifest.get("message") or "")
    elif str(node_count) in {"", "0"}:
        display_status = "empty_filter"
        guidance = str(summary.get("message") or graph_summary.get("message") or graph.get("message") or "Rendered graph has no visible nodes.")
    overlay_source = str(manifest.get("overlay_source") or "")
    if not overlay_source:
        for node in graph.get("nodes") or []:
            if isinstance(node, dict) and node.get("overlay_source"):
                overlay_source = str(node.get("overlay_source") or "")
                break
    return {
        "status": display_status,
        "variant_id": variant_id,
        "path": str(graph_path),
        "relative_path": _safe_relative_path(package, graph_path),
        "source": "variant_rendered_graph",
        "node_count": node_count,
        "link_count": link_count,
        "graph_status": graph_status,
        "guidance": guidance,
        "overlay_source": overlay_source,
        "filter": {
            "reaction_filter": manifest.get("reaction_filter", ""),
            "subsystem_filter": manifest.get("subsystem_filter", ""),
            "annotation_type": annotation_type,
            "annotation_group_id": annotation_group_id,
        },
    }


def _sammi_overlay_from_compare_overlay(overlay: str) -> str:
    normalized = str(overlay or "none").strip()
    aliases = {
        "flux_delta": "gecko_flux_delta",
    }
    return aliases.get(normalized, normalized)


def _safe_file_segment(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return text.strip("._")[:80] or "default"


def _safe_relative_path(package: Path, path: Path) -> str:
    return safe_relative_path(package, path)


def _pair_metric_status(reference_status: str, target_status: str) -> str:
    if reference_status == "parsed" and target_status == "parsed":
        return "ready"
    return "partial"


def _pair_gpr_diff_rows(
    target_variant_id: str,
    reference: Any,
    target: Any,
    comparison: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for reaction_id in sorted(comparison.get("changed_gpr", set())):
        rows.append(
            {
                "variant_id": target_variant_id,
                "reaction_id": reaction_id,
                "change_type": "changed_gpr",
                "reaction_name": target.reactions.get(reaction_id, {}).get("name") or reference.reactions.get(reaction_id, {}).get("name", ""),
                "reference_gpr": reference.reactions.get(reaction_id, {}).get("gpr", ""),
                "model_gpr": target.reactions.get(reaction_id, {}).get("gpr", ""),
                "reference_lower_bound": reference.reactions.get(reaction_id, {}).get("lower_bound", ""),
                "reference_upper_bound": reference.reactions.get(reaction_id, {}).get("upper_bound", ""),
                "model_lower_bound": target.reactions.get(reaction_id, {}).get("lower_bound", ""),
                "model_upper_bound": target.reactions.get(reaction_id, {}).get("upper_bound", ""),
            }
        )
    return rows


def _pair_objective_diff_rows(target_variant_id: str, reference: Any, target: Any, comparison: dict[str, Any]) -> list[dict[str, Any]]:
    if not comparison.get("objective_changed"):
        return []
    return [
        {
            "variant_id": target_variant_id,
            "reaction_id": ";".join(sorted(target.objective_reactions)) or "objective",
            "change_type": "objective_changed",
            "reaction_name": "Objective reaction changed",
            "reference_objective": ";".join(sorted(reference.objective_reactions)),
            "model_objective": ";".join(sorted(target.objective_reactions)),
        }
    ]


def _pair_constraint_summary(
    package: Path,
    enzyme_rows: list[dict[str, str]],
    evidence_rows: list[dict[str, str]],
    production_rows: list[dict[str, str]],
) -> list[dict[str, Any]]:
    protein_count = sum(_safe_int(row.get("protein_count")) for row in enzyme_rows)
    kcat_count = sum(_safe_int(row.get("kcat_prior_count")) for row in enzyme_rows)
    capacity_count = sum(_safe_int(row.get("capacity_reaction_count")) for row in enzyme_rows)
    mapped_fraction = max((_safe_float(row.get("mapped_protein_fraction")) for row in enzyme_rows), default=0.0)
    if not kcat_count:
        kcat_rows = read_csv_rows(package / "generated_constraints" / "kcat_priors.csv")
        if not kcat_rows:
            kcat_rows = read_csv_rows(package / "dlkcat_results" / "dlkcat_reaction_kcat_priors.csv")
        kcat_count = len(kcat_rows)
    if not capacity_count:
        capacity_rows = read_csv_rows(package / "enzyme_results" / "reaction_enzyme_capacity.csv")
        if not capacity_rows:
            capacity_rows = read_csv_rows(package / "gecko_package" / "reaction_enzyme_capacity.csv")
        capacity_count = len(capacity_rows)
    return [
        {
            "metric": "enzyme_capacity_constrained_reactions",
            "value": capacity_count,
            "status": "ready" if capacity_count else "optional_missing",
            "guidance": "Capacity constrained reaction count is read from GECKO/proteome allocation outputs when available.",
        },
        {
            "metric": "kcat_prior_count",
            "value": kcat_count,
            "status": "ready" if kcat_count else "missing",
            "guidance": "kcat priors indicate enzyme-turnover evidence availability, not direct causal validation.",
        },
        {
            "metric": "proteomics_mapped_fraction",
            "value": mapped_fraction,
            "status": "ready" if mapped_fraction else "partial",
            "guidance": "Mapped proteomics fraction summarizes evidence mapping into model constraints.",
        },
        {
            "metric": "proteomics_protein_count",
            "value": protein_count,
            "status": "ready" if protein_count else "missing",
            "guidance": "Protein count is aggregated across available highO2/lowO2 proteomics rows.",
        },
        {
            "metric": "evidence_rows",
            "value": len(evidence_rows),
            "status": "ready" if evidence_rows else "missing",
            "guidance": "Evidence rows describe confidence/context coverage for model variants.",
        },
        {
            "metric": "production_target_rows",
            "value": len(production_rows),
            "status": "ready" if production_rows else "optional_missing",
            "guidance": "Production readiness is optional for model pair comparison.",
        },
    ]


def _behavior_signal_index(package: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Build reaction-level behavior signals from existing outputs only."""

    signals: dict[str, dict[str, Any]] = {}
    context_rows: list[dict[str, Any]] = []
    production_rows_seen = 0

    reaction_sources = [
        (
            package / "gecko_run_results" / "gecko_flux_delta_high_vs_low.csv",
            "gecko_flux_delta",
            ("flux_delta_high_minus_low", "flux_delta", "delta_flux", "predicted_flux_delta", "abs_flux_delta"),
            "highO2 vs lowO2",
        ),
        (
            package / "transcriptomics_flux_results" / "delta_fba_flux_deltas.csv",
            "delta_fba_flux_delta",
            ("predicted_flux_delta", "flux_delta", "delta_flux"),
            "",
        ),
        (
            package / "variant_comparison" / "pathway_flux_delta_chart.csv",
            "pathway_flux_delta",
            ("flux_delta", "delta_flux", "sum_abs_flux_delta", "abs_flux_delta"),
            "",
        ),
    ]
    for path, source, delta_columns, default_context in reaction_sources:
        for row in read_csv_rows(path):
            reaction_id = _first_existing(row, ("reaction_id", "cobra_reaction_id", "model_reaction_id", "target_id", "top_reaction_id", "reaction", "rxn", "bigg_reaction"))
            key = _normalize_reaction_key(reaction_id)
            if not key:
                continue
            delta_value = _first_numeric(row, delta_columns)
            if delta_value is None:
                continue
            context = _first_existing(row, ("condition_pair", "comparison", "contrast", "condition", "reference_condition", "target_condition")) or default_context
            _store_behavior_signal(
                signals,
                key,
                {
                    "reaction_id": reaction_id,
                    "flux_delta_value": delta_value,
                    "flux_delta_status": "ready" if abs(delta_value) > 1e-12 else "near_zero",
                    "condition_context": context,
                    "production_relevance": "",
                    "behavior_source": source,
                },
            )

    for path in (
        package / "production_results" / "production_target_readiness.csv",
        package / "case_study" / "production_target_readiness.csv",
    ):
        for row in read_csv_rows(path):
            reaction_id = _first_existing(row, ("model_product_reaction_id", "product_reaction_id", "reaction_id", "target_reaction_id"))
            key = _normalize_reaction_key(reaction_id)
            if not key:
                continue
            production_rows_seen += 1
            product_name = _first_existing(row, ("product_name", "target_name", "metabolite_name")) or "production target"
            relevance = _first_existing(row, ("production_readiness_label", "growth_coupling_label", "readiness_label", "semantic_label")) or product_name
            existing = signals.get(key, {})
            _store_behavior_signal(
                signals,
                key,
                {
                    "reaction_id": reaction_id,
                    "flux_delta_value": existing.get("flux_delta_value", ""),
                    "flux_delta_status": existing.get("flux_delta_status", "not_available"),
                    "condition_context": existing.get("condition_context") or _first_existing(row, ("condition", "condition_group")),
                    "production_relevance": f"{product_name}: {relevance}",
                    "behavior_source": existing.get("behavior_source") or "production_target_readiness",
                },
            )

    for path in (
        package / "variant_comparison" / "condition_behavior_comparison.csv",
        package / "variant_comparison" / "variant_flux_comparison.csv",
        package / "variant_comparison" / "pathway_flux_comparison.csv",
    ):
        rows = read_csv_rows(path)
        if rows:
            context_rows.append(
                {
                    "source": path.stem,
                    "row_count": len(rows),
                    "conditions": sorted({_first_existing(row, ("condition", "condition_group", "condition_pair")) for row in rows if _first_existing(row, ("condition", "condition_group", "condition_pair"))})[:12],
                }
            )

    source_counts = _count_values(signal.get("behavior_source") or "unknown" for signal in signals.values())
    condition_context = "; ".join(
        f"{row.get('source')}:{','.join(str(item) for item in row.get('conditions') or []) or row.get('row_count')}"
        for row in context_rows[:4]
    )
    return signals, {
        "reaction_level_signal_count": sum(1 for signal in signals.values() if abs(_optional_float(signal.get("flux_delta_value")) or 0.0) > 1e-12),
        "reaction_level_row_count": len(signals),
        "condition_context_rows": context_rows,
        "condition_context": condition_context,
        "production_relevance_count": production_rows_seen,
        "behavior_source_counts": source_counts,
        "status": "ready" if signals else "condition_level_only" if context_rows else "not_available",
        "guidance": (
            "Reaction-level behavior signals were read from existing flux or production outputs."
            if signals
            else "Only condition-level behavior summaries are available; they are not projected onto individual reactions."
            if context_rows
            else "No existing behavior output was found for this run."
        ),
    }


def _store_behavior_signal(signals: dict[str, dict[str, Any]], key: str, candidate: dict[str, Any]) -> None:
    existing = signals.get(key)
    if not existing:
        signals[key] = dict(candidate)
        return
    existing_delta = abs(_optional_float(existing.get("flux_delta_value")) or 0.0)
    candidate_delta = abs(_optional_float(candidate.get("flux_delta_value")) or 0.0)
    if candidate_delta > existing_delta:
        merged = {**existing, **candidate}
    else:
        merged = {**candidate, **existing}
        if candidate.get("production_relevance"):
            merged["production_relevance"] = candidate.get("production_relevance")
        if candidate.get("behavior_source") and candidate.get("behavior_source") not in str(existing.get("behavior_source") or ""):
            merged["behavior_source"] = ";".join(filter(None, [str(existing.get("behavior_source") or ""), str(candidate.get("behavior_source") or "")]))
    signals[key] = merged


def _behavior_support_index(package: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Build reaction-level support evidence from existing outputs only."""

    support: dict[str, dict[str, Any]] = {}
    context_rows: list[dict[str, Any]] = []

    fva_paths = [
        package / "variant_comparison" / "fva_flexibility_comparison.csv",
        *sorted((package / "variant_cobra_results").glob("*/*fva*.csv")),
        *sorted((package / "analysis_results").glob("*fva*.csv")),
    ]
    for path in fva_paths:
        rows = read_csv_rows(path)
        if not rows:
            continue
        mapped = 0
        for row in rows:
            key, reaction_id = _support_reaction_key(row)
            if not key:
                continue
            mapped += 1
            fva_min = _first_numeric(row, ("fva_minimum", "fva_min", "minimum", "min", "minimum_flux", "min_flux"))
            fva_max = _first_numeric(row, ("fva_maximum", "fva_max", "maximum", "max", "maximum_flux", "max_flux"))
            width = _first_numeric(row, ("fva_width", "width", "range", "flexibility_width"))
            if width is None and fva_min is not None and fva_max is not None:
                width = abs(fva_max - fva_min)
            within_value = _first_existing(row, ("within_fva", "within_range", "within_bounds", "fva_support", "status"))
            status = _support_status(within_value) or ("ready" if width is not None else "not_available")
            _store_behavior_support(
                support,
                key,
                {
                    "reaction_id": reaction_id,
                    "fva_status": status,
                    "fva_minimum": fva_min if fva_min is not None else "",
                    "fva_maximum": fva_max if fva_max is not None else "",
                    "fva_width": width if width is not None else "",
                    "within_fva": within_value,
                    "support_source": "target_fva" if "target_fva" in path.name else path.stem,
                },
            )
        if mapped == 0:
            context_rows.append({"source": path.stem, "row_count": len(rows), "support_type": "fva", "status": "summary_level_only"})

    validation_paths = [
        *sorted((package / "variant_cobra_results").glob("*/*validation_comparison.csv")),
        package / "transcriptomics_flux_results" / "eflux_flux_validation_comparison.csv",
        package / "case_study" / "old_vs_new_validation_summary.csv",
    ]
    for path in validation_paths:
        rows = read_csv_rows(path)
        if not rows:
            continue
        mapped = 0
        for row in rows:
            key, reaction_id = _support_reaction_key(row)
            if not key:
                continue
            mapped += 1
            observed = _first_numeric(row, ("observed_value", "observed_flux", "measured_flux", "experimental_flux", "flux_observed"))
            predicted = _first_numeric(row, ("predicted_value", "predicted_flux", "model_flux", "pfba_flux", "simulated_flux"))
            residual = _first_numeric(row, ("residual", "absolute_error", "prediction_error", "error", "delta"))
            if residual is None and observed is not None and predicted is not None:
                residual = predicted - observed
            status = _support_status(_first_existing(row, ("validation_status", "status", "comparison_status", "readiness"))) or (
                "ready" if observed is not None or predicted is not None or residual is not None else "not_available"
            )
            _store_behavior_support(
                support,
                key,
                {
                    "reaction_id": reaction_id,
                    "validation_status": status,
                    "observed_value": observed if observed is not None else "",
                    "predicted_value": predicted if predicted is not None else "",
                    "residual": residual if residual is not None else "",
                    "support_source": path.stem,
                },
            )
        if mapped == 0:
            context_rows.append({"source": path.stem, "row_count": len(rows), "support_type": "validation", "status": "summary_level_only"})

    capacity_paths = [
        package / "enzyme_results" / "reaction_enzyme_capacity.csv",
        package / "gecko_package" / "reaction_enzyme_capacity.csv",
        package / "enzyme_results" / "enzyme_flux_capacity_check.csv",
    ]
    for path in capacity_paths:
        rows = read_csv_rows(path)
        if not rows:
            continue
        mapped = 0
        for row in rows:
            key, reaction_id = _support_reaction_key(row)
            if not key:
                continue
            mapped += 1
            capacity = _first_numeric(row, ("capacity_value", "enzyme_capacity", "capacity", "max_flux_capacity", "reaction_capacity"))
            usage = _first_numeric(row, ("usage_value", "enzyme_usage", "usage", "usage_fraction", "capacity_usage", "saturation", "usage_ratio"))
            saturation = _first_existing(row, ("saturation_status", "capacity_status", "usage_status", "status"))
            status = _support_status(saturation) or ("ready" if capacity is not None or usage is not None else "package_ready_only")
            _store_behavior_support(
                support,
                key,
                {
                    "reaction_id": reaction_id,
                    "capacity_status": status,
                    "capacity_value": capacity if capacity is not None else "",
                    "usage_value": usage if usage is not None else "",
                    "saturation_status": saturation,
                    "support_source": path.stem,
                },
            )
        if mapped == 0:
            context_rows.append({"source": path.stem, "row_count": len(rows), "support_type": "capacity", "status": "summary_level_only"})

    enzyme_usage_rows = read_csv_rows(package / "gecko_run_results" / "gecko_enzyme_usage_highO2.csv") + read_csv_rows(
        package / "gecko_run_results" / "gecko_enzyme_usage_lowO2.csv"
    )
    if enzyme_usage_rows:
        mapped = 0
        for row in enzyme_usage_rows:
            key, reaction_id = _support_reaction_key(row)
            if not key:
                continue
            mapped += 1
            usage = _first_numeric(row, ("usage_value", "enzyme_usage", "usage", "usage_fraction"))
            _store_behavior_support(
                support,
                key,
                {
                    "reaction_id": reaction_id,
                    "usage_value": usage if usage is not None else "",
                    "capacity_status": "ready" if usage is not None else "package_ready_only",
                    "support_source": "gecko_enzyme_usage",
                },
            )
        if mapped == 0:
            context_rows.append({"source": "gecko_enzyme_usage", "row_count": len(enzyme_usage_rows), "support_type": "capacity", "status": "enzyme_level_only"})

    production_paths = [
        package / "production_results" / "production_target_readiness.csv",
        package / "case_study" / "production_target_readiness.csv",
        package / "production_results" / "production_gecko_target_comparison.csv",
        package / "production_results" / "production_gecko_design_comparison.csv",
    ]
    for path in production_paths:
        rows = read_csv_rows(path)
        if not rows:
            continue
        mapped = 0
        for row in rows:
            reaction_candidates = [
                _first_existing(row, ("model_product_reaction_id", "product_reaction_id", "target_reaction_id", "reaction_id")),
                _first_existing(row, ("candidate_id", "design_reaction_id")),
            ]
            for reaction_id in reaction_candidates:
                key = _normalize_reaction_key(reaction_id)
                if not key:
                    continue
                mapped += 1
                product = _first_existing(row, ("product_name", "target_name", "metabolite_name")) or "production target"
                label = _first_existing(row, ("production_readiness_label", "comparison_label", "growth_coupling_label", "semantic_label", "cobra_action"))
                _store_behavior_support(
                    support,
                    key,
                    {
                        "reaction_id": reaction_id,
                        "production_support": f"{product}: {label}" if label else product,
                        "support_source": path.stem,
                    },
                )
        if mapped == 0:
            context_rows.append({"source": path.stem, "row_count": len(rows), "support_type": "production", "status": "summary_level_only"})

    fva_count = sum(1 for item in support.values() if str(item.get("fva_status") or "") not in {"", "not_available"})
    validation_count = sum(1 for item in support.values() if str(item.get("validation_status") or "") not in {"", "not_available"})
    capacity_count = sum(1 for item in support.values() if str(item.get("capacity_status") or "") not in {"", "not_available"})
    production_count = sum(1 for item in support.values() if str(item.get("production_support") or "").strip())
    return support, {
        "reaction_level_support_count": len(support),
        "fva_support_count": fva_count,
        "validation_support_count": validation_count,
        "capacity_support_count": capacity_count,
        "production_support_count": production_count,
        "context_rows": context_rows,
        "support_source_counts": _count_values(source for item in support.values() for source in str(item.get("support_source") or "unknown").split(";") if source),
        "status": "ready" if support else "condition_level_only" if context_rows else "not_available",
        "guidance": (
            "Reaction-level support evidence was read from existing FVA, validation, capacity, or production outputs."
            if support
            else "Only summary-level support evidence is available; it is not projected onto individual reactions."
            if context_rows
            else "No existing FVA, validation, capacity, or production support output was found for this run."
        ),
    }


def _support_reaction_key(row: dict[str, Any]) -> tuple[str, str]:
    reaction_id = _first_existing(
        row,
        (
            "reaction_id",
            "model_reaction_id",
            "cobra_reaction_id",
            "target_reaction_id",
            "model_product_reaction_id",
            "product_reaction_id",
            "candidate_id",
            "design_reaction_id",
            "target_id",
            "bigg_reaction",
            "reaction",
            "rxn",
        ),
    )
    return _normalize_reaction_key(reaction_id), reaction_id


def _support_status(value: Any) -> str:
    return support_status(value)


def _store_behavior_support(support: dict[str, dict[str, Any]], key: str, candidate: dict[str, Any]) -> None:
    existing = support.get(key)
    if not existing:
        support[key] = dict(candidate)
        return
    merged = dict(existing)
    for field, value in candidate.items():
        if field == "support_source":
            sources = [item for item in str(existing.get(field) or "").split(";") if item]
            for item in str(value or "").split(";"):
                if item and item not in sources:
                    sources.append(item)
            merged[field] = ";".join(sources)
        elif value not in (None, "") and merged.get(field) in (None, ""):
            merged[field] = value
        elif field in {"fva_width", "residual", "usage_value"} and _optional_float(value) is not None:
            merged[field] = value
        elif field.endswith("_status") and value not in (None, ""):
            merged[field] = merged.get(field) or value
    support[key] = merged


def _first_existing(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _first_numeric(row: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        numeric = _optional_float(row.get(key))
        if numeric is not None:
            return numeric
    return None


def _normalize_reaction_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = re.sub(r"^r_", "", text)
    text = re.sub(r"_[a-z]\d*$", "", text)
    text = text.replace("-", "_")
    return text


def _graph_reaction_nodes(graph_summary: dict[str, Any]) -> list[dict[str, Any]]:
    path_text = str(graph_summary.get("path") or "").strip()
    if not path_text:
        return []
    graph = read_json_object(Path(path_text))
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    output: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        node_type = str(node.get("node_type") or node.get("type") or "").lower()
        if node_type and node_type != "reaction":
            continue
        output.append(node)
    return output


def _kcat_provenance_index(package: Path) -> dict[str, dict[str, Any]]:
    rows: list[dict[str, str]] = []
    for path in (
        package / "generated_constraints" / "kcat_priors.csv",
        package / "dlkcat_results" / "dlkcat_reaction_kcat_priors.csv",
        package / "normalized_inputs" / "omics" / "ml_priors__gotenzymes2_kcat_priors.csv",
    ):
        rows.extend(read_csv_rows(path))

    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        ids = [
            row.get("model_target_id"),
            row.get("target_id"),
            row.get("reaction_id"),
            row.get("reaction"),
            row.get("id"),
        ]
        keys = {_normalize_reaction_key(value) for value in ids}
        keys.discard("")
        if not keys:
            continue
        source_database = (
            row.get("original_source")
            or row.get("source_database")
            or row.get("source_tier")
            or row.get("kcat_evidence_tier")
            or "unknown"
        )
        confidence = row.get("confidence") or row.get("kcat_confidence") or ""
        provenance = {
            "kcat_value": row.get("kcat") or row.get("kcat_value") or "",
            "kcat_unit": row.get("unit") or row.get("kcat_unit") or "",
            "source_database": source_database,
            "source_tier": row.get("source_tier") or "",
            "evidence_tier": row.get("kcat_evidence_tier") or row.get("evidence_tier") or "",
            "match_level": row.get("source_tier") or row.get("status") or row.get("match_level") or "",
            "confidence": confidence,
            "confidence_label": _kcat_confidence_label(confidence),
            "source_category": _kcat_source_category(row),
            "source_file": row.get("source_file") or "",
            "selection_status": row.get("selection_status") or "",
            "mapping_status": row.get("status") or "",
            "gene_id": row.get("gene_id") or "",
            "substrate_name": row.get("substrate_name") or row.get("substrate_id") or "",
            "source_query_id": row.get("source_query_id") or "",
            "note": row.get("note") or "",
            "conflict_flag": row.get("kcat_conflict_flag") or "",
            "conflict_severity": row.get("kcat_conflict_severity") or "",
        }
        selected = str(row.get("selection_status") or "").lower() == "selected"
        mapped = str(row.get("status") or "").lower() == "mapped"
        for key in keys:
            previous = index.get(key)
            if previous is None or selected or (mapped and str(previous.get("mapping_status") or "").lower() != "mapped"):
                index[key] = provenance
    return index


def _kcat_confidence_label(value: Any) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        text = str(value or "").strip().lower()
        return text if text in {"high", "medium", "low"} else "unknown"
    if numeric >= 0.8:
        return "high"
    if numeric >= 0.55:
        return "medium"
    return "low"


def _kcat_source_category(row: dict[str, Any]) -> str:
    text = " ".join(str(row.get(key) or "").lower() for key in ("original_source", "source_tier", "kcat_evidence_tier", "source_file", "note"))
    if "dlkcat" in text or "predicted" in text:
        return "predicted"
    if "fallback" in text:
        return "fallback"
    if "gotenzymes" in text:
        return "gotenzymes2"
    if "brenda" in text:
        return "brenda"
    if "sabio" in text:
        return "sabio-rk"
    if "database" in text or "curated" in text or "gecko" in text:
        return "database"
    return "unknown"


def _pair_reaction_detail_index(
    *,
    package: Path,
    reference: Any,
    target: Any,
    comparison: dict[str, Any],
    reference_graph: dict[str, Any],
    target_graph: dict[str, Any],
    diff_rows: list[dict[str, Any]],
    kcat_provenance_index: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    reference_nodes = _graph_reaction_nodes(reference_graph)
    target_nodes = _graph_reaction_nodes(target_graph)
    reference_node_by_key = {_normalize_reaction_key(node.get("id") or node.get("label")): node for node in reference_nodes}
    target_node_by_key = {_normalize_reaction_key(node.get("id") or node.get("label")): node for node in target_nodes}
    reference_reaction_by_key = {_normalize_reaction_key(rid): rid for rid in reference.reactions.keys()}
    target_reaction_by_key = {_normalize_reaction_key(rid): rid for rid in target.reactions.keys()}
    ordered_keys: list[str] = []

    def add_key(value: Any) -> None:
        key = _normalize_reaction_key(value)
        if key and key not in ordered_keys:
            ordered_keys.append(key)

    for row in diff_rows:
        add_key(row.get("reaction_id") or row.get("reference_reaction_id") or row.get("target_reaction_id"))
    for node in [*reference_nodes, *target_nodes]:
        add_key(node.get("id") or node.get("label"))
    for reaction_id in sorted(comparison.get("added_reactions", set())):
        add_key(reaction_id)
    for reaction_id in sorted(comparison.get("removed_reactions", set())):
        add_key(reaction_id)
    for reaction_id in sorted(comparison.get("changed_bounds", set())):
        add_key(reaction_id)
    for reaction_id in sorted(comparison.get("changed_gpr", set())):
        add_key(reaction_id)

    detail_rows: list[dict[str, Any]] = []
    for key in ordered_keys[:900]:
        reference_id = reference_reaction_by_key.get(key, "")
        target_id = target_reaction_by_key.get(key, "")
        reference_node = reference_node_by_key.get(key, {})
        target_node = target_node_by_key.get(key, {})
        canonical_id = target_id or reference_id or str(target_node.get("id") or reference_node.get("id") or key)
        change_type = _pair_reaction_change_type(reference_id, target_id, comparison)
        reference_detail = _pair_reaction_side_detail(reference, reference_id, reference_node, kcat_provenance_index or {})
        target_detail = _pair_reaction_side_detail(target, target_id, target_node, kcat_provenance_index or {})
        external_links = _reaction_external_links_from_text(
            canonical_id,
            reference_id,
            target_id,
            reference_detail.get("name", ""),
            target_detail.get("name", ""),
            reference_node.get("annotation", ""),
            target_node.get("annotation", ""),
            reference_node.get("kegg_reaction", ""),
            target_node.get("kegg_reaction", ""),
        )
        detail_rows.append(
            {
                "reaction_id": canonical_id,
                "normalized_reaction_id": key,
                "reference_reaction_id": reference_id,
                "target_reaction_id": target_id,
                "reference_present": bool(reference_id or reference_node),
                "target_present": bool(target_id or target_node),
                "change_type": change_type,
                "pathway_group": target_detail.get("pathway_group") or reference_detail.get("pathway_group") or "",
                "reference": reference_detail,
                "target": target_detail,
                "external_links": external_links,
            }
        )
    return detail_rows


def _reaction_diff_index_from_pair_details(
    detail_rows: list[dict[str, Any]],
    *,
    comparison: dict[str, Any],
    behavior_signal_index: dict[str, dict[str, Any]] | None = None,
    behavior_context_summary: dict[str, Any] | None = None,
    behavior_support_index: dict[str, dict[str, Any]] | None = None,
    behavior_support_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    behavior_signal_index = behavior_signal_index or {}
    behavior_context_summary = behavior_context_summary or {}
    behavior_support_index = behavior_support_index or {}
    behavior_support_context = behavior_support_context or {}
    has_condition_level_behavior = bool(behavior_context_summary.get("condition_context_rows"))
    for row in detail_rows:
        reference = row.get("reference") if isinstance(row.get("reference"), dict) else {}
        target = row.get("target") if isinstance(row.get("target"), dict) else {}
        reference_present = bool(row.get("reference_present"))
        target_present = bool(row.get("target_present"))
        change_type = str(row.get("change_type") or "unchanged")
        bounds_changed = change_type == "bounds-changed" or _side_value(reference, "bounds") != _side_value(target, "bounds")
        gpr_changed = change_type == "GPR-changed" or _side_value(reference, "gpr") != _side_value(target, "gpr")
        structural_change = change_type not in {"", "unchanged"} or not (reference_present and target_present)
        reference_kcat = _side_kcat_provenance(reference)
        target_kcat = _side_kcat_provenance(target)
        kcat_available = bool(reference_kcat or target_kcat) or _side_has_signal(reference, ("kcat_status", "kcat_coverage", "kcat")) or _side_has_signal(
            target,
            ("kcat_status", "kcat_coverage", "kcat"),
        )
        capacity_available = _side_has_signal(
            reference,
            ("enzyme_capacity_status", "enzyme_capacity", "capacity_status"),
        ) or _side_has_signal(target, ("enzyme_capacity_status", "enzyme_capacity", "capacity_status"))
        proteomics_available = _side_has_signal(
            reference,
            ("proteomics_evidence", "proteomics_status", "readiness_label"),
        ) or _side_has_signal(target, ("proteomics_evidence", "proteomics_status", "readiness_label"))
        normalized_key = str(row.get("normalized_reaction_id") or _normalize_reaction_key(row.get("reaction_id")))
        behavior_signal = behavior_signal_index.get(normalized_key, {})
        behavior_delta = _optional_float(behavior_signal.get("flux_delta_value"))
        behavior_has_reaction_delta = behavior_delta is not None and abs(behavior_delta) > 1e-12
        graph_flux_available = _side_has_signal(reference, ("overlay_value", "flux_delta", "delta_flux")) or _side_has_signal(
            target,
            ("overlay_value", "flux_delta", "delta_flux"),
        )
        flux_available = behavior_has_reaction_delta or graph_flux_available
        production_relevance = str(behavior_signal.get("production_relevance") or "").strip()
        behavior_signal_available = flux_available or bool(production_relevance)
        flux_delta_status = "ready" if behavior_has_reaction_delta else "condition_level_only" if has_condition_level_behavior else "not_available"
        behavior_support = dict(behavior_support_index.get(normalized_key, {}))
        behavior_support_available = _behavior_support_available(behavior_support)
        behavior_support.setdefault("support_available", behavior_support_available)
        behavior_support.setdefault("fva_status", "not_available")
        behavior_support.setdefault("validation_status", "not_available")
        behavior_support.setdefault("capacity_status", "not_available")
        behavior_support.setdefault("production_support", "")
        behavior_support.setdefault("support_source", "")
        external_links = row.get("external_links") if isinstance(row.get("external_links"), list) else []
        score, reasons = _reaction_difference_score(
            change_type=change_type,
            structural_change=structural_change,
            bounds_changed=bounds_changed,
            gpr_changed=gpr_changed,
            kcat_available=kcat_available,
            capacity_available=capacity_available,
            proteomics_available=proteomics_available,
            behavior_signal_available=behavior_signal_available,
            behavior_support_available=behavior_support_available,
            external_links=external_links,
        )
        presence = (
            "shared"
            if reference_present and target_present
            else "reference_only"
            if reference_present
            else "target_only"
            if target_present
            else "not_present"
        )
        constraint_role = _constraint_role(
            reference=reference,
            target=target,
            reference_kcat=reference_kcat,
            target_kcat=target_kcat,
            capacity_available=capacity_available,
            kcat_available=kcat_available,
            proteomics_available=proteomics_available,
        )
        kcat_provenance = target_kcat or reference_kcat
        rows.append(
            {
                "reaction_id": row.get("reaction_id") or row.get("target_reaction_id") or row.get("reference_reaction_id") or "",
                "normalized_reaction_id": normalized_key,
                "reference_reaction_id": row.get("reference_reaction_id", ""),
                "target_reaction_id": row.get("target_reaction_id", ""),
                "presence": presence,
                "change_type": change_type,
                "pathway_group": row.get("pathway_group", ""),
                "definition_diff": {
                    "reference_present": reference_present,
                    "target_present": target_present,
                    "bounds_changed": bounds_changed,
                    "gpr_changed": gpr_changed,
                    "objective_changed": bool(comparison.get("objective_changed")) and change_type == "objective-changed",
                    "structural_change": structural_change,
                },
                "constraint_evidence": {
                    "kcat_available": kcat_available,
                    "enzyme_capacity_available": capacity_available,
                    "proteomics_evidence_available": proteomics_available,
                    "constraint_role": constraint_role,
                    "kcat_provenance": kcat_provenance,
                    "kcat_source_database": kcat_provenance.get("source_database", ""),
                    "kcat_match_level": kcat_provenance.get("match_level", ""),
                    "kcat_confidence": kcat_provenance.get("confidence_label") or kcat_provenance.get("confidence", ""),
                    "kcat_source_category": kcat_provenance.get("source_category", ""),
                    "kcat_status": _first_side_signal(reference, target, ("kcat_status", "kcat_coverage", "kcat")),
                    "enzyme_capacity_status": _first_side_signal(
                        reference,
                        target,
                        ("enzyme_capacity_status", "enzyme_capacity", "capacity_status"),
                    ),
                    "proteomics_status": _first_side_signal(
                        reference,
                        target,
                        ("proteomics_evidence", "proteomics_status", "readiness_label"),
                    ),
                },
                "behavior_diff": {
                    "behavior_signal_available": behavior_signal_available,
                    "flux_delta_available": flux_available,
                    "flux_delta_value": behavior_signal.get("flux_delta_value", ""),
                    "flux_delta_status": flux_delta_status,
                    "condition_context": behavior_signal.get("condition_context") or behavior_context_summary.get("condition_context") or "",
                    "production_relevance": production_relevance,
                    "behavior_source": behavior_signal.get("behavior_source", ""),
                    "reference_overlay_value": _side_value(reference, "overlay_value"),
                    "target_overlay_value": _side_value(target, "overlay_value"),
                },
                "behavior_support": {
                    "support_available": behavior_support_available,
                    "fva_status": behavior_support.get("fva_status", "not_available"),
                    "fva_minimum": behavior_support.get("fva_minimum", ""),
                    "fva_maximum": behavior_support.get("fva_maximum", ""),
                    "fva_width": behavior_support.get("fva_width", ""),
                    "within_fva": behavior_support.get("within_fva", ""),
                    "validation_status": behavior_support.get("validation_status", "not_available"),
                    "observed_value": behavior_support.get("observed_value", ""),
                    "predicted_value": behavior_support.get("predicted_value", ""),
                    "residual": behavior_support.get("residual", ""),
                    "capacity_status": behavior_support.get("capacity_status", "not_available"),
                    "capacity_value": behavior_support.get("capacity_value", ""),
                    "usage_value": behavior_support.get("usage_value", ""),
                    "saturation_status": behavior_support.get("saturation_status", ""),
                    "production_support": behavior_support.get("production_support", ""),
                    "support_source": behavior_support.get("support_source", ""),
                    "support_context": behavior_support_context.get("guidance") or "",
                    "support_context_status": behavior_support_context.get("status") or "not_available",
                },
                "reference": reference,
                "target": target,
                "external_links": external_links,
                "difference_score": score,
                "ranking_reasons": reasons,
                "kcat_provenance": kcat_provenance,
                "kcat_confidence": kcat_provenance.get("confidence_label") or kcat_provenance.get("confidence", ""),
                "kcat_source_database": kcat_provenance.get("source_database", ""),
                "kcat_match_level": kcat_provenance.get("match_level", ""),
                "constraint_role": constraint_role,
                "behavior_source": behavior_signal.get("behavior_source", ""),
                "flux_delta_value": behavior_signal.get("flux_delta_value", ""),
                "behavior_support_source": behavior_support.get("support_source", ""),
                "evidence_badges": [
                    badge
                    for badge, available in (
                        ("kcat", kcat_available),
                        ("capacity", capacity_available),
                        ("proteomics", proteomics_available),
                        ("flux", flux_available),
                        ("behavior", behavior_signal_available),
                        ("fva", _support_field_available(behavior_support, "fva_status")),
                        ("validation", _support_field_available(behavior_support, "validation_status")),
                        ("capacity_support", _support_field_available(behavior_support, "capacity_status")),
                        ("production_support", bool(str(behavior_support.get("production_support") or "").strip())),
                    )
                    if available
                ],
            }
        )
    return rows


def _behavior_support_available(support: dict[str, Any]) -> bool:
    return any(
        (
            _support_field_available(support, "fva_status"),
            _support_field_available(support, "validation_status"),
            _support_field_available(support, "capacity_status"),
            bool(str(support.get("production_support") or "").strip()),
        )
    )


def _support_field_available(support: dict[str, Any], field: str) -> bool:
    text = str(support.get(field) or "").strip().lower()
    return bool(text and text not in {"not_available", "missing", "optional_missing", "unavailable", "condition_level_only", "summary_level_only"})


def _side_value(side: dict[str, Any], key: str) -> str:
    value = side.get(key) if isinstance(side, dict) else ""
    return str(value or "").strip()


def _side_has_signal(side: dict[str, Any], keys: tuple[str, ...]) -> bool:
    if not isinstance(side, dict):
        return False
    for key in keys:
        value = side.get(key)
        if value in (None, ""):
            continue
        text = str(value).strip().lower()
        if text and text not in {"0", "0.0", "false", "none", "missing", "optional_missing", "not_available", "unavailable", "mapping pending"}:
            return True
    return False


def _first_side_signal(reference: dict[str, Any], target: dict[str, Any], keys: tuple[str, ...]) -> str:
    for side in (target, reference):
        if not isinstance(side, dict):
            continue
        for key in keys:
            value = side.get(key)
            if _side_has_signal(side, (key,)):
                return str(value)
    return ""


def _side_kcat_provenance(side: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(side, dict):
        return {}
    provenance = side.get("kcat_provenance")
    if isinstance(provenance, dict) and provenance:
        return dict(provenance)
    if _side_has_signal(side, ("kcat_source_database", "kcat_confidence", "kcat_match_level", "kcat_status", "kcat_coverage", "kcat")):
        return {
            "source_database": side.get("kcat_source_database") or "unknown",
            "confidence": side.get("kcat_confidence") or "",
            "confidence_label": _kcat_confidence_label(side.get("kcat_confidence") or ""),
            "match_level": side.get("kcat_match_level") or "",
            "source_category": side.get("kcat_source_category") or "unknown",
            "kcat_value": side.get("kcat_value") or side.get("kcat") or "",
            "kcat_unit": side.get("kcat_unit") or "",
        }
    return {}


def _constraint_role(
    *,
    reference: dict[str, Any],
    target: dict[str, Any],
    reference_kcat: dict[str, Any],
    target_kcat: dict[str, Any],
    capacity_available: bool,
    kcat_available: bool,
    proteomics_available: bool,
) -> str:
    reference_capacity = _side_has_signal(reference, ("enzyme_capacity_status", "enzyme_capacity", "capacity_status"))
    target_capacity = _side_has_signal(target, ("enzyme_capacity_status", "enzyme_capacity", "capacity_status"))
    if target_capacity and not reference_capacity:
        return "target-only constraint"
    if reference_capacity and not target_capacity:
        return "reference-only constraint"
    if reference_capacity and target_capacity:
        return "shared enzyme constraint"
    if target_kcat and not reference_kcat:
        return "target-only kcat evidence"
    if reference_kcat and not target_kcat:
        return "reference-only kcat evidence"
    if reference_kcat and target_kcat:
        return "shared kcat evidence"
    if kcat_available or proteomics_available:
        return "shared evidence"
    if capacity_available:
        return "constraint evidence"
    return "mapping pending"


def _reaction_difference_score(
    *,
    change_type: str,
    structural_change: bool,
    bounds_changed: bool,
    gpr_changed: bool,
    kcat_available: bool,
    capacity_available: bool,
    proteomics_available: bool,
    behavior_signal_available: bool,
    behavior_support_available: bool,
    external_links: list[Any],
) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    if change_type in {"added", "removed"}:
        score += 100
        reasons.append(change_type)
    elif bounds_changed:
        score += 85
        reasons.append("bounds changed")
    elif gpr_changed:
        score += 80
        reasons.append("GPR changed")
    elif structural_change:
        score += 70
        reasons.append(change_type or "structural change")
    if capacity_available:
        score += 36
        reasons.append("enzyme capacity signal")
    if kcat_available:
        score += 30
        reasons.append("kcat evidence")
    if behavior_signal_available:
        score += 24
        reasons.append("behavior signal")
    if behavior_support_available:
        score += 18
        reasons.append("behavior support evidence")
    if proteomics_available:
        score += 16
        reasons.append("proteomics evidence")
    if not external_links:
        score += 4
        reasons.append("external link missing")
    return score, reasons or ["unchanged context reaction"]


def _submap_evidence_summary(
    reaction_diff_index: list[dict[str, Any]],
    *,
    scoped_reaction_ids: list[str],
    comparison_label: str,
) -> dict[str, Any]:
    changed_rows = [row for row in reaction_diff_index if str(row.get("change_type") or "") not in {"", "unchanged"}]
    kcat_rows = [row for row in reaction_diff_index if bool((row.get("constraint_evidence") or {}).get("kcat_available"))]
    capacity_rows = [row for row in reaction_diff_index if bool((row.get("constraint_evidence") or {}).get("enzyme_capacity_available"))]
    proteomics_rows = [row for row in reaction_diff_index if bool((row.get("constraint_evidence") or {}).get("proteomics_evidence_available"))]
    behavior_rows = [row for row in reaction_diff_index if bool((row.get("behavior_diff") or {}).get("behavior_signal_available"))]
    flux_rows = [row for row in reaction_diff_index if bool((row.get("behavior_diff") or {}).get("flux_delta_available"))]
    production_relevant_rows = [row for row in reaction_diff_index if str((row.get("behavior_diff") or {}).get("production_relevance") or "").strip()]
    behavior_support_rows = [row for row in reaction_diff_index if bool((row.get("behavior_support") or {}).get("support_available"))]
    fva_support_rows = [row for row in reaction_diff_index if _support_field_available(row.get("behavior_support") or {}, "fva_status")]
    validation_support_rows = [row for row in reaction_diff_index if _support_field_available(row.get("behavior_support") or {}, "validation_status")]
    capacity_support_rows = [row for row in reaction_diff_index if _support_field_available(row.get("behavior_support") or {}, "capacity_status")]
    production_support_rows = [row for row in reaction_diff_index if str((row.get("behavior_support") or {}).get("production_support") or "").strip()]
    kcat_source_counts = _count_values(
        (row.get("constraint_evidence") or {}).get("kcat_source_database") or (row.get("constraint_evidence") or {}).get("kcat_source_category") or "unknown"
        for row in kcat_rows
    )
    kcat_confidence_counts = _count_values(
        (row.get("constraint_evidence") or {}).get("kcat_confidence") or "unknown"
        for row in kcat_rows
    )
    constraint_role_counts = _count_values(
        (row.get("constraint_evidence") or {}).get("constraint_role") or row.get("constraint_role") or "mapping pending"
        for row in reaction_diff_index
    )
    behavior_source_counts = _count_values(
        (row.get("behavior_diff") or {}).get("behavior_source") or "unknown"
        for row in behavior_rows
    )
    flux_status_counts = _count_values(
        (row.get("behavior_diff") or {}).get("flux_delta_status") or "not_available"
        for row in reaction_diff_index
    )
    behavior_support_source_counts = _count_values(
        source
        for row in behavior_support_rows
        for source in str((row.get("behavior_support") or {}).get("support_source") or "unknown").split(";")
        if source
    )
    behavior_support_status_counts = _count_values(
        value
        for row in reaction_diff_index
        for value in (
            (row.get("behavior_support") or {}).get("fva_status") or "not_available",
            (row.get("behavior_support") or {}).get("validation_status") or "not_available",
            (row.get("behavior_support") or {}).get("capacity_status") or "not_available",
        )
    )
    positive_flux_count = sum(
        1 for row in flux_rows if (_optional_float((row.get("behavior_diff") or {}).get("flux_delta_value")) or 0.0) > 1e-12
    )
    negative_flux_count = sum(
        1 for row in flux_rows if (_optional_float((row.get("behavior_diff") or {}).get("flux_delta_value")) or 0.0) < -1e-12
    )
    same_source = comparison_label in {"same_source_model", "reference_model", "no_structural_change"}
    enzyme_capacity_count = len(capacity_rows)
    enzyme_capacity_support_count = len(capacity_support_rows)
    enzyme_capacity_status = (
        "ready"
        if enzyme_capacity_count
        else "support_ready"
        if enzyme_capacity_support_count
        else "not_available"
    )
    return {
        "status": "ready" if reaction_diff_index else "missing_scope",
        "scope_status": "annotation_group" if scoped_reaction_ids else "unscoped",
        "reaction_count": len(reaction_diff_index),
        "scoped_reaction_count": len(scoped_reaction_ids),
        "changed_count": len(changed_rows),
        "kcat_covered_count": len(kcat_rows),
        "enzyme_capacity_count": enzyme_capacity_count or enzyme_capacity_support_count,
        "enzyme_capacity_constraint_count": enzyme_capacity_count,
        "enzyme_capacity_support_count": enzyme_capacity_support_count,
        "enzyme_capacity_status": enzyme_capacity_status,
        "proteomics_mapped_count": len(proteomics_rows),
        "proteomics_status": "ready" if proteomics_rows else "mapping_pending",
        "flux_delta_count": len(flux_rows),
        "behavior_signal_count": len(behavior_rows),
        "production_relevant_count": len(production_relevant_rows),
        "behavior_support_count": len(behavior_support_rows),
        "fva_support_count": len(fva_support_rows),
        "validation_support_count": len(validation_support_rows),
        "capacity_support_count": len(capacity_support_rows),
        "production_support_count": len(production_support_rows),
        "behavior_signal_counts": {
            "ready": len(behavior_rows),
            "flux_delta": len(flux_rows),
            "production_relevant": len(production_relevant_rows),
            "positive_flux_delta": positive_flux_count,
            "negative_flux_delta": negative_flux_count,
        },
        "behavior_support_counts": {
            "ready": len(behavior_support_rows),
            "fva": len(fva_support_rows),
            "validation": len(validation_support_rows),
            "capacity": len(capacity_support_rows),
            "production": len(production_support_rows),
        },
        "behavior_source_counts": behavior_source_counts,
        "flux_delta_status_counts": flux_status_counts,
        "behavior_support_source_counts": behavior_support_source_counts,
        "behavior_support_status_counts": behavior_support_status_counts,
        "kcat_source_counts": kcat_source_counts,
        "kcat_confidence_counts": kcat_confidence_counts,
        "constraint_role_counts": constraint_role_counts,
        "structural_status": "same_source" if same_source and not changed_rows else "changed" if changed_rows else "unchanged",
        "guidance": (
            "No annotation group scope was selected; choose a subsystem, KEGG pathway, or custom annotation group before interpreting a difference map."
            if not scoped_reaction_ids
            else "Counts are scoped to the selected annotation group and derived from ReactionDiff rows."
        ),
    }


def _count_values(values: Iterable[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "unknown").strip() or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _pair_difference_summary(
    reaction_diff_index: list[dict[str, Any]],
    *,
    comparison: dict[str, Any],
    reference_id: str,
    target_id: str,
    annotation_type: str,
    annotation_group_id: str,
    behavior_context_summary: dict[str, Any] | None = None,
    behavior_support_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    behavior_context_summary = behavior_context_summary or {}
    behavior_support_context = behavior_support_context or {}
    submap = _submap_evidence_summary(
        reaction_diff_index,
        scoped_reaction_ids=[],
        comparison_label=str(comparison.get("label") or ""),
    )
    changed = int(submap.get("changed_count") or 0)
    kcat = int(submap.get("kcat_covered_count") or 0)
    capacity = int(submap.get("enzyme_capacity_count") or 0)
    proteomics = int(submap.get("proteomics_mapped_count") or 0)
    flux = int(submap.get("flux_delta_count") or 0)
    support = int(submap.get("behavior_support_count") or 0)
    label = str(comparison.get("label") or "partial")
    if changed:
        dominant = "structural_difference"
        headline = f"{changed} reaction-level structural or definition differences are present in the current scope."
    elif capacity or kcat:
        dominant = "constraint_evidence"
        headline = "No conventional structural diff dominates; enzyme/kcat constraint evidence is the main comparison signal."
    elif flux:
        dominant = "behavior_signal"
        headline = "No structural diff dominates; flux/behavior signals are the main comparison signal."
    elif support:
        dominant = "behavior_support"
        headline = "No structural diff dominates; existing FVA, validation, capacity, or production outputs support behavior interpretation."
    elif proteomics:
        dominant = "evidence_context"
        headline = "No structural diff dominates; proteomics evidence marks reactions for review."
    elif label in {"same_source_model", "reference_model", "no_structural_change"}:
        dominant = "same_source"
        headline = "Same-source conventional GEM comparison: review constraints, evidence, and behavior rather than structural changes."
    else:
        dominant = "partial"
        headline = "Pair comparison is partial; select an annotation group or render scoped graphs to inspect differences."
    return {
        "reference_variant_id": reference_id,
        "target_variant_id": target_id,
        "annotation_type": annotation_type,
        "annotation_group_id": annotation_group_id,
        "comparison_label": label,
        "dominant_signal": dominant,
        "headline": headline,
        "structural_change_count": changed,
        "kcat_signal_count": kcat,
        "enzyme_capacity_signal_count": capacity,
        "proteomics_signal_count": proteomics,
        "flux_signal_count": flux,
        "behavior_signal_count": int(submap.get("behavior_signal_count") or 0),
        "production_relevant_count": int(submap.get("production_relevant_count") or 0),
        "behavior_support_count": support,
        "fva_support_count": int(submap.get("fva_support_count") or 0),
        "validation_support_count": int(submap.get("validation_support_count") or 0),
        "capacity_support_count": int(submap.get("capacity_support_count") or 0),
        "production_support_count": int(submap.get("production_support_count") or 0),
        "behavior_context": behavior_context_summary.get("guidance") or "",
        "behavior_context_status": behavior_context_summary.get("status") or "not_available",
        "behavior_source_counts": behavior_context_summary.get("behavior_source_counts") or {},
        "behavior_support_context": behavior_support_context.get("guidance") or "",
        "behavior_support_context_status": behavior_support_context.get("status") or "not_available",
        "behavior_support_source_counts": behavior_support_context.get("support_source_counts") or {},
        "guidance": comparison.get("guidance", ""),
    }


def _compare_readiness_summary(
    *,
    parse_ready: bool,
    graph_ready: bool,
    annotation_scope: dict[str, Any],
    submap_evidence_summary: dict[str, Any],
    pair_difference_summary: dict[str, Any],
    behavior_context_summary: dict[str, Any],
    behavior_support_context: dict[str, Any],
) -> dict[str, Any]:
    return compare_readiness_summary(
        parse_ready=parse_ready,
        graph_ready=graph_ready,
        annotation_scope=annotation_scope,
        submap_evidence_summary=submap_evidence_summary,
        pair_difference_summary=pair_difference_summary,
        behavior_context_summary=behavior_context_summary,
        behavior_support_context=behavior_support_context,
    )


def _case_compare_guidance(
    run_id: str,
    *,
    submap_evidence_summary: dict[str, Any],
    behavior_context_summary: dict[str, Any],
    behavior_support_context: dict[str, Any],
) -> str:
    return case_compare_guidance(
        run_id,
        submap_evidence_summary=submap_evidence_summary,
        behavior_context_summary=behavior_context_summary,
        behavior_support_context=behavior_support_context,
    )


def _difference_ranking(reaction_diff_index: list[dict[str, Any]], limit: int = 80) -> list[dict[str, Any]]:
    ranked = sorted(
        reaction_diff_index,
        key=lambda row: (-int(row.get("difference_score") or 0), str(row.get("reaction_id") or "")),
    )
    output: list[dict[str, Any]] = []
    for index, row in enumerate(ranked[:limit], start=1):
        output.append(
            {
                "rank": index,
                "reaction_id": row.get("reaction_id", ""),
                "normalized_reaction_id": row.get("normalized_reaction_id", ""),
                "change_type": row.get("change_type", ""),
                "pathway_group": row.get("pathway_group", ""),
                "difference_score": row.get("difference_score", 0),
                "reasons": row.get("ranking_reasons", []),
                "evidence_badges": row.get("evidence_badges", []),
                "filter_tags": _ranking_filter_tags(row),
                "constraint_role": row.get("constraint_role", ""),
                "kcat_source_database": row.get("kcat_source_database", ""),
                "kcat_confidence": row.get("kcat_confidence", ""),
                "behavior_source": (row.get("behavior_diff") or {}).get("behavior_source", ""),
                "flux_delta_value": (row.get("behavior_diff") or {}).get("flux_delta_value", ""),
                "production_relevance": (row.get("behavior_diff") or {}).get("production_relevance", ""),
                "behavior_support_source": (row.get("behavior_support") or {}).get("support_source", ""),
                "fva_status": (row.get("behavior_support") or {}).get("fva_status", ""),
                "validation_status": (row.get("behavior_support") or {}).get("validation_status", ""),
                "capacity_status": (row.get("behavior_support") or {}).get("capacity_status", ""),
                "production_support": (row.get("behavior_support") or {}).get("production_support", ""),
            }
        )
    return output


def _ranking_filter_tags(row: dict[str, Any]) -> list[str]:
    tags = ["all"]
    change_type = str(row.get("change_type") or "")
    badges = {str(value) for value in row.get("evidence_badges", []) if value}
    constraint = row.get("constraint_evidence") if isinstance(row.get("constraint_evidence"), dict) else {}
    behavior = row.get("behavior_diff") if isinstance(row.get("behavior_diff"), dict) else {}
    support = row.get("behavior_support") if isinstance(row.get("behavior_support"), dict) else {}
    if change_type and change_type != "unchanged":
        tags.append("structural")
    if "kcat" in badges or constraint.get("kcat_available"):
        tags.append("kcat")
    if "capacity" in badges or constraint.get("enzyme_capacity_available"):
        tags.append("capacity")
    if "proteomics" in badges or constraint.get("proteomics_evidence_available"):
        tags.append("proteomics")
    if "flux" in badges or "behavior" in badges or behavior.get("flux_delta_available") or behavior.get("behavior_signal_available"):
        tags.append("behavior")
    if (
        "fva" in badges
        or "validation" in badges
        or "capacity_support" in badges
        or "production_support" in badges
        or support.get("support_available")
    ):
        tags.append("support")
    return tags


def _merged_difference_graph(
    reference_graph: dict[str, Any],
    target_graph: dict[str, Any],
    reaction_diff_index: list[dict[str, Any]],
) -> dict[str, Any]:
    diff_by_key = {str(row.get("normalized_reaction_id") or ""): row for row in reaction_diff_index if row.get("normalized_reaction_id")}
    nodes_by_id: dict[str, dict[str, Any]] = {}
    link_keys: set[tuple[str, str, str]] = set()
    links: list[dict[str, Any]] = []

    def load_graph(summary: dict[str, Any]) -> dict[str, Any]:
        path_text = str(summary.get("path") or "").strip()
        return read_json_object(Path(path_text)) if path_text else {}

    def merged_node_id(node: dict[str, Any]) -> str:
        node_type = str(node.get("node_type") or node.get("type") or "").lower()
        raw_id = str(node.get("id") or node.get("label") or "")
        if node_type == "reaction":
            key = _normalize_reaction_key(raw_id)
            return f"reaction:{key or raw_id}"
        return f"metabolite:{raw_id}"

    def add_graph(graph: dict[str, Any], side: str) -> dict[str, str]:
        raw_to_merged: dict[str, str] = {}
        for node in graph.get("nodes") if isinstance(graph.get("nodes"), list) else []:
            if not isinstance(node, dict):
                continue
            raw_id = str(node.get("id") or node.get("label") or "")
            if not raw_id:
                continue
            merged_id = merged_node_id(node)
            raw_to_merged[raw_id] = merged_id
            current = nodes_by_id.setdefault(
                merged_id,
                {
                    **node,
                    "id": merged_id,
                    "source_ids": [],
                    "graph_sides": [],
                },
            )
            current.setdefault("source_ids", []).append(raw_id)
            current.setdefault("graph_sides", []).append(side)
            node_type = str(node.get("node_type") or node.get("type") or "").lower()
            if node_type == "reaction":
                key = _normalize_reaction_key(raw_id)
                diff = diff_by_key.get(key, {})
                current.update(
                    {
                        "reaction_id": diff.get("reaction_id") or raw_id,
                        "normalized_reaction_id": key,
                        "change_type": diff.get("change_type", "unchanged"),
                        "difference_score": diff.get("difference_score", 0),
                        "difference_status": _merged_node_difference_status(diff),
                        "evidence_badges": diff.get("evidence_badges", []),
                        "ranking_reasons": diff.get("ranking_reasons", []),
                    }
                )
        for link in graph.get("links") if isinstance(graph.get("links"), list) else []:
            if not isinstance(link, dict):
                continue
            raw_source = link.get("source")
            raw_target = link.get("target")
            source_id = raw_source.get("id") if isinstance(raw_source, dict) else str(raw_source or "")
            target_id = raw_target.get("id") if isinstance(raw_target, dict) else str(raw_target or "")
            merged_source = raw_to_merged.get(source_id, source_id)
            merged_target = raw_to_merged.get(target_id, target_id)
            if not merged_source or not merged_target:
                continue
            key = (merged_source, merged_target, str(link.get("link_type") or ""))
            if key in link_keys:
                continue
            link_keys.add(key)
            links.append({**link, "source": merged_source, "target": merged_target, "graph_side": side})
        return raw_to_merged

    add_graph(load_graph(reference_graph), "reference")
    add_graph(load_graph(target_graph), "target")
    reaction_count = sum(1 for node in nodes_by_id.values() if str(node.get("id", "")).startswith("reaction:"))
    changed_count = sum(
        1
        for node in nodes_by_id.values()
        if str(node.get("id", "")).startswith("reaction:") and str(node.get("change_type") or "unchanged") != "unchanged"
    )
    return {
        "status": "ready" if reaction_count else "missing",
        "nodes": list(nodes_by_id.values())[:1000],
        "links": links[:1600],
        "summary": {
            "reaction_count": reaction_count,
            "changed_count": changed_count,
            "node_count": len(nodes_by_id),
            "link_count": len(links),
        },
        "legend": [
            {"status": "shared_unchanged", "label": "shared unchanged", "color": "#94a3b8"},
            {"status": "reference_only", "label": "reference-only", "color": "#5b8def"},
            {"status": "target_only", "label": "target-only", "color": "#e8c45d"},
            {"status": "definition_changed", "label": "bounds/GPR changed", "color": "#e65f5c"},
            {"status": "constraint_evidence", "label": "constraint/evidence", "color": "#42b883"},
            {"status": "behavior_signal", "label": "flux behavior", "color": "#f59e0b"},
        ],
    }


def _merged_node_difference_status(diff: dict[str, Any]) -> str:
    if not diff:
        return "shared_unchanged"
    presence = str(diff.get("presence") or "")
    change_type = str(diff.get("change_type") or "")
    if presence == "reference_only":
        return "reference_only"
    if presence == "target_only":
        return "target_only"
    if change_type in {"bounds-changed", "GPR-changed", "objective-changed", "added", "removed"}:
        return "definition_changed"
    constraint = diff.get("constraint_evidence") if isinstance(diff.get("constraint_evidence"), dict) else {}
    behavior = diff.get("behavior_diff") if isinstance(diff.get("behavior_diff"), dict) else {}
    if constraint.get("enzyme_capacity_available") or constraint.get("kcat_available"):
        return "constraint_evidence"
    if behavior.get("flux_delta_available") or behavior.get("behavior_signal_available"):
        return "behavior_signal"
    return "shared_unchanged"


def _pair_reaction_side_detail(
    model: Any,
    reaction_id: str,
    graph_node: dict[str, Any],
    kcat_provenance_index: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    reaction = model.reactions.get(reaction_id, {}) if reaction_id else {}
    lower_bound = reaction.get("lower_bound", "")
    upper_bound = reaction.get("upper_bound", "")
    kcat_provenance = _reaction_kcat_provenance(reaction_id, graph_node, kcat_provenance_index or {})
    return {
        "present": bool(reaction_id or graph_node),
        "reaction_id": reaction_id or str(graph_node.get("id") or ""),
        "name": reaction.get("name") or graph_node.get("reaction_name") or graph_node.get("name") or graph_node.get("label") or "",
        "bounds": f"{lower_bound} / {upper_bound}" if lower_bound != "" or upper_bound != "" else "",
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
        "gpr": reaction.get("gpr", "") or graph_node.get("gpr", ""),
        "kcat_status": graph_node.get("kcat_status") or graph_node.get("kcat_coverage") or graph_node.get("kcat") or "",
        "kcat_provenance": kcat_provenance,
        "kcat_source_database": kcat_provenance.get("source_database", ""),
        "kcat_confidence": kcat_provenance.get("confidence_label") or kcat_provenance.get("confidence", ""),
        "kcat_match_level": kcat_provenance.get("match_level", ""),
        "kcat_source_category": kcat_provenance.get("source_category", ""),
        "kcat_value": kcat_provenance.get("kcat_value", ""),
        "kcat_unit": kcat_provenance.get("kcat_unit", ""),
        "enzyme_capacity_status": graph_node.get("enzyme_capacity_status") or graph_node.get("enzyme_capacity") or graph_node.get("capacity_status") or "",
        "proteomics_evidence": graph_node.get("proteomics_evidence") or graph_node.get("proteomics_status") or graph_node.get("readiness_label") or "",
        "pathway_group": graph_node.get("group_label") or graph_node.get("subsystem") or graph_node.get("group_id") or "",
        "overlay_value": graph_node.get("overlay_value", ""),
        "overlay_color": graph_node.get("overlay_color", ""),
    }


def _reaction_kcat_provenance(
    reaction_id: str,
    graph_node: dict[str, Any],
    kcat_provenance_index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    for candidate in (
        reaction_id,
        graph_node.get("id") if isinstance(graph_node, dict) else "",
        graph_node.get("label") if isinstance(graph_node, dict) else "",
        graph_node.get("reaction_id") if isinstance(graph_node, dict) else "",
    ):
        key = _normalize_reaction_key(candidate)
        if key and key in kcat_provenance_index:
            return dict(kcat_provenance_index[key])
    if not isinstance(graph_node, dict):
        return {}
    source_database = graph_node.get("kcat_source_database") or graph_node.get("kcat_source") or graph_node.get("source_database") or ""
    confidence = graph_node.get("kcat_confidence") or graph_node.get("confidence") or ""
    if not any((source_database, confidence, graph_node.get("kcat"), graph_node.get("kcat_status"), graph_node.get("kcat_coverage"))):
        return {}
    return {
        "kcat_value": graph_node.get("kcat") or graph_node.get("kcat_value") or "",
        "kcat_unit": graph_node.get("kcat_unit") or "",
        "source_database": source_database or "unknown",
        "match_level": graph_node.get("kcat_match_level") or graph_node.get("match_level") or "",
        "confidence": confidence,
        "confidence_label": _kcat_confidence_label(confidence),
        "source_category": _kcat_source_category({key: graph_node.get(key) for key in graph_node.keys()}),
        "note": graph_node.get("kcat_note") or "",
    }


def _pair_reaction_change_type(reference_id: str, target_id: str, comparison: dict[str, Any]) -> str:
    if reference_id and not target_id:
        return "removed"
    if target_id and not reference_id:
        return "added"
    reaction_id = target_id or reference_id
    if reaction_id in comparison.get("changed_bounds", set()):
        return "bounds-changed"
    if reaction_id in comparison.get("changed_gpr", set()):
        return "GPR-changed"
    reference_objective = comparison.get("reference_objective_reactions", set())
    target_objective = comparison.get("target_objective_reactions", set())
    objective_reactions = (reference_objective if isinstance(reference_objective, set) else set()) | (
        target_objective if isinstance(target_objective, set) else set()
    )
    if comparison.get("objective_changed") and reaction_id in objective_reactions:
        return "objective-changed"
    return "unchanged"


def _pair_reaction_match_index(detail_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "reaction_id": row.get("reaction_id", ""),
            "normalized_reaction_id": row.get("normalized_reaction_id", ""),
            "reference_reaction_id": row.get("reference_reaction_id", ""),
            "target_reaction_id": row.get("target_reaction_id", ""),
            "match_status": (
                "matched"
                if row.get("reference_present") and row.get("target_present")
                else "target_only"
                if row.get("target_present")
                else "reference_only"
                if row.get("reference_present")
                else "not_present"
            ),
            "change_type": row.get("change_type", ""),
        }
        for row in detail_rows
    ]


def _pair_overlay_availability(
    *,
    overlay: str,
    constraint_summary: list[dict[str, Any]],
    gecko_flux_rows: list[dict[str, str]],
    reference_graph: dict[str, Any],
    target_graph: dict[str, Any],
) -> list[dict[str, Any]]:
    metrics = {str(row.get("metric") or ""): row for row in constraint_summary}
    graph_overlay_counts = _graph_overlay_counts(reference_graph) + _graph_overlay_counts(target_graph)

    def metric_count(metric: str) -> int:
        return _safe_int(metrics.get(metric, {}).get("value"))

    rows = [
        {
            "overlay": "none",
            "status": "ready",
            "coverage_count": 0,
            "active": overlay == "none",
            "guidance": "No overlay is applied; graph colors use network defaults.",
        },
        {
            "overlay": "enzyme_capacity",
            "status": "ready" if metric_count("enzyme_capacity_constrained_reactions") or graph_overlay_counts else "optional_missing",
            "coverage_count": metric_count("enzyme_capacity_constrained_reactions") or graph_overlay_counts,
            "active": overlay == "enzyme_capacity",
            "guidance": "Enzyme capacity overlay is available when GECKO/enzyme-constrained outputs contain capacity signals.",
        },
        {
            "overlay": "kcat_coverage",
            "status": "ready" if metric_count("kcat_prior_count") or graph_overlay_counts else "missing",
            "coverage_count": metric_count("kcat_prior_count") or graph_overlay_counts,
            "active": overlay == "kcat_coverage",
            "guidance": "kcat coverage shows mapped turnover priors or kcat evidence, not causal validation.",
        },
        {
            "overlay": "flux_delta",
            "status": "ready" if gecko_flux_rows or graph_overlay_counts else "optional_missing",
            "coverage_count": len(gecko_flux_rows) or graph_overlay_counts,
            "active": overlay == "flux_delta",
            "guidance": "Flux delta overlay is available when highO2/lowO2 flux-delta outputs have been generated.",
        },
    ]
    return rows


def _graph_overlay_counts(graph_summary: dict[str, Any]) -> int:
    return sum(1 for node in _graph_reaction_nodes(graph_summary) if str(node.get("overlay_value") or node.get("overlay_color") or "").strip())


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _reaction_external_link_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    output: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        reaction_id = str(row.get("reaction_id") or "").strip()
        row_text = " ".join(str(value) for value in row.values() if isinstance(value, (str, int, float)))
        for link in _reaction_external_links_from_text(reaction_id, row_text):
            key = (reaction_id, link["label"])
            if key in seen:
                continue
            seen.add(key)
            output.append({"reaction_id": reaction_id, **link})
        if len(output) >= 120:
            break
    return output


def _reaction_external_links_from_text(reaction_id: str, *texts: Any) -> list[dict[str, str]]:
    links = _reaction_external_links(reaction_id)
    seen = {link["label"] for link in links}
    search_text = " ".join([str(reaction_id or ""), *(str(text or "") for text in texts)])
    ec_matches = re.findall(r"\b\d+\.\d+\.\d+\.\d+\b", search_text)
    for ec_id in ec_matches[:3]:
        label = f"EC {ec_id}"
        if label not in seen:
            seen.add(label)
            links.append({"label": label, "href": f"https://enzyme.expasy.org/EC/{ec_id}"})
    uniprot_matches = re.findall(r"\b(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9])\b", search_text)
    for uniprot_id in uniprot_matches[:3]:
        label = f"UniProt {uniprot_id}"
        if label not in seen:
            seen.add(label)
            links.append({"label": label, "href": f"https://www.uniprot.org/uniprotkb/{uniprot_id}/entry"})
    return links


def _reaction_external_links(reaction_id: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    raw = str(reaction_id or "").strip()
    if not raw:
        return links
    kegg_match = re.search(r"R\d{5}", raw, re.IGNORECASE)
    if kegg_match:
        rid = kegg_match.group(0).upper()
        links.append({"label": "KEGG", "href": f"https://www.kegg.jp/entry/{rid}"})
    clean = re.sub(r"^R_", "", raw)
    clean = re.sub(r"_[a-z]\d*$", "", clean, flags=re.IGNORECASE)
    clean = clean.replace("-", "_")
    if re.match(r"^[A-Za-z][A-Za-z0-9_]+$", clean):
        links.append({"label": "BiGG", "href": f"http://bigg.ucsd.edu/universal/reactions/{clean}"})
    mnx_match = re.search(r"MNXR\d+", raw, re.IGNORECASE)
    if mnx_match:
        mnx_id = mnx_match.group(0).upper()
        links.append({"label": "MetaNetX", "href": f"https://www.metanetx.org/equa_info/{mnx_id}"})
    return links


def _pair_comparison_guidance(*, parse_ready: bool, graph_ready: bool, comparison_label: str, grouping: str) -> str:
    messages: list[str] = []
    if not parse_ready:
        messages.append("Structural pair diff is partial because one or both model files could not be parsed as SBML/XML.")
    elif comparison_label in {"same_source_model", "reference_model", "no_structural_change"}:
        messages.append("No conventional GEM structural difference was detected; compare constraints, omics evidence, and behavior outputs.")
    else:
        messages.append("Pair-specific structural differences are available for reaction-level review.")
    if not graph_ready:
        messages.append("One or both model-specific rendered graphs are missing; render maps in Analysis before using the dual-network view.")
    if grouping == "kegg_pathway":
        messages.append("KEGG pathway-derived grouping is recommended when native subsystem annotation is sparse.")
    return " ".join(messages)


def _gecko_interpretation_summary(
    *,
    gecko_manifest: dict[str, Any],
    gecko_summary: list[dict[str, Any]],
    flux_delta: list[dict[str, Any]],
    enzyme_usage_high: list[dict[str, Any]],
    enzyme_usage_low: list[dict[str, Any]],
) -> dict[str, Any]:
    status = str(gecko_manifest.get("status") or gecko_manifest.get("run_status") or "").strip()
    has_outputs = bool(gecko_manifest or gecko_summary or flux_delta or enzyme_usage_high or enzyme_usage_low)
    flux_count = len(flux_delta)
    enzyme_usage_count = len(enzyme_usage_high) + len(enzyme_usage_low)
    if has_outputs:
        normalized_status = status or "available"
        headline = "GECKO enzyme-constrained outputs are available."
        guidance = (
            "Interpret GECKO flux and enzyme-usage results as enzyme-constrained behavior. "
            "They are intentionally kept separate from conventional GEM structural diff."
        )
    else:
        normalized_status = "optional_missing"
        headline = "GECKO outputs are not available for this run."
        guidance = (
            "GECKO remains an optional external dependency path. Missing GECKO output does not block "
            "conventional GEM structural comparison."
        )
    return {
        "status": normalized_status,
        "headline": headline,
        "flux_delta_row_count": flux_count,
        "enzyme_usage_row_count": enzyme_usage_count,
        "summary_row_count": len(gecko_summary),
        "external_run_recorded": bool(gecko_manifest),
        "guidance": guidance,
    }


def _merge_gecko_interpretation_row(
    rows: list[dict[str, Any]],
    gecko_interpretation: dict[str, Any],
) -> list[dict[str, Any]]:
    output = [dict(row) for row in rows if str(row.get("layer")) != "gecko_behavior"]
    output.append(
        {
            "layer": "gecko_behavior",
            "status": gecko_interpretation.get("status", "optional_missing"),
            "headline": gecko_interpretation.get("headline", ""),
            "detail": gecko_interpretation.get("guidance", ""),
            "recommended_next_step": (
                "Use GECKO flux and enzyme-usage outputs when enzyme-constrained behavior is central."
                if gecko_interpretation.get("external_run_recorded")
                else "Run or import GECKO outputs only when the external dependency path is required."
            ),
        }
    )
    return output


def _merge_gecko_layer_status_row(
    rows: list[dict[str, Any]],
    gecko_interpretation: dict[str, Any],
) -> list[dict[str, Any]]:
    output = [dict(row) for row in rows if str(row.get("layer")) != "gecko_behavior"]
    signal_count = int(gecko_interpretation.get("flux_delta_row_count") or 0) + int(gecko_interpretation.get("enzyme_usage_row_count") or 0)
    output.append(
        {
            "layer": "gecko_behavior",
            "status": "ready" if signal_count else gecko_interpretation.get("status", "optional_missing"),
            "signal_count": signal_count,
            "warning_count": 0 if signal_count else 1,
            "summary": gecko_interpretation.get("headline", ""),
        }
    )
    return output


def run_analysis_summary(run_id: str) -> dict[str, Any]:
    package = resolve_run_package(run_id)
    summary = run_summary(run_id)
    native_exports = list_sammi_native_exports(package)
    production_dir = package / "production_results"
    gecko_dir = package / "gecko_run_results"
    case_study_dir = package / "case_study"
    ml_profiles = list_ml_hybrid_profiles(package)
    key_files = [
        _file_summary(package, package / "workflow_results" / "analysis_parameters_summary.csv", "analysis_parameters_summary"),
        _file_summary(package, production_dir / "production_target_readiness.csv", "production_target_readiness"),
        _file_summary(package, production_dir / "production_visualization_summary.csv", "production_visualization_summary"),
        _file_summary(package, gecko_dir / "gecko_flux_delta_high_vs_low.csv", "gecko_flux_delta"),
        _file_summary(package, gecko_dir / "gecko_enzyme_usage_highO2.csv", "gecko_enzyme_usage_highO2"),
        _file_summary(package, case_study_dir / "paper_reproduction_manifest.json", "paper_reproduction_manifest"),
        _file_summary(package, case_study_dir / "supplement_download_manifest.json", "supplement_download_manifest"),
        _file_summary(package, case_study_dir / "supplement_file_inventory.csv", "supplement_file_inventory"),
        _file_summary(package, case_study_dir / "data_needed_manifest.json", "data_needed_manifest"),
        _file_summary(package, case_study_dir / "processed_expression_timecourse.csv", "processed_expression_timecourse"),
        _file_summary(package, case_study_dir / "growth_curve_timecourse.csv", "growth_curve_timecourse"),
        _file_summary(package, case_study_dir / "metabolite_glycogen_timecourse.csv", "metabolite_glycogen_timecourse"),
        _file_summary(package, case_study_dir / "growth_state_map_data.json", "growth_state_map_data"),
        _file_summary(package, case_study_dir / "trigger_timeline_data.json", "trigger_timeline_data"),
        _file_summary(package, case_study_dir / "pathway_evidence_groups.csv", "pathway_evidence_groups"),
        _file_summary(package, case_study_dir / "gdm_lite_results.json", "gdm_lite_results"),
        _file_summary(package, case_study_dir / "d2t2_trigger_genes.csv", "d2t2_trigger_genes"),
        _file_summary(package, case_study_dir / "dfba_parameter_set.json", "dfba_parameter_set"),
        _file_summary(package, case_study_dir / "dfba_glycogen_scenario.csv", "dfba_glycogen_scenario"),
        _file_summary(package, case_study_dir / "dfba_glycogen_scenario.json", "dfba_glycogen_scenario_json"),
        _file_summary(package, case_study_dir / "paper_evidence_reaction_overlay.csv", "paper_evidence_reaction_overlay"),
        _file_summary(package, case_study_dir / "paper_evidence_mapping_summary.json", "paper_evidence_mapping_summary"),
    ]
    visualization_count = len(summary.get("visualizations", [])) + len(native_exports.get("exports", []))
    paper_reproduction_manifest = read_json_object(case_study_dir / "paper_reproduction_manifest.json")
    ready = bool(summary.get("analysis_parameters_summary")) or visualization_count > 0 or any(item["exists"] for item in key_files[1:])
    return {
        "run_id": run_id,
        "status": "ready" if ready else "partial",
        "workflow_selection": summary.get("workflow_selection", []),
        "analysis_parameters": summary.get("analysis_parameters_summary", []),
        "visualizations": summary.get("visualizations", []),
        "sammi_native_exports": native_exports,
        "production": {
            "target_readiness": _table_preview(production_dir / "production_target_readiness.csv", limit=50),
            "visualization_summary": _table_preview(production_dir / "production_visualization_summary.csv", limit=50),
            "overlay_manifest": read_json_object(production_dir / "production_overlay_manifest.json"),
        },
        "gecko": {
            "summary": _table_preview(gecko_dir / "gecko_external_run_summary.csv", limit=20),
            "flux_delta": _table_preview(gecko_dir / "gecko_flux_delta_high_vs_low.csv", limit=50),
            "enzyme_usage_highO2": _table_preview(gecko_dir / "gecko_enzyme_usage_highO2.csv", limit=20),
            "enzyme_usage_lowO2": _table_preview(gecko_dir / "gecko_enzyme_usage_lowO2.csv", limit=20),
        },
        "ml_hybrid_profiles": ml_profiles,
        "paper_reproduction": {
            "manifest": paper_reproduction_manifest,
            "supplement_download": read_json_object(case_study_dir / "supplement_download_manifest.json"),
            "supplement_file_inventory": _table_preview(case_study_dir / "supplement_file_inventory.csv", limit=50),
            "data_needed": read_json_object(case_study_dir / "data_needed_manifest.json"),
            "growth_state_map": read_json_object(case_study_dir / "growth_state_map_data.json"),
            "trigger_timeline": read_json_object(case_study_dir / "trigger_timeline_data.json"),
            "pathway_evidence_groups": _table_preview(case_study_dir / "pathway_evidence_groups.csv", limit=50),
            "gdm_gene_classes": _table_preview(case_study_dir / "gdm_gene_classes.csv", limit=20),
            "gdm_lite_results": read_json_object(case_study_dir / "gdm_lite_results.json"),
            "d2t2_trigger_genes": _table_preview(case_study_dir / "d2t2_trigger_genes.csv", limit=50),
            "dfba_parameter_set": read_json_object(case_study_dir / "dfba_parameter_set.json"),
            "dfba_scenario_manifest": read_json_object(case_study_dir / "dfba_scenario_manifest.json"),
            "dfba_glycogen_scenario_chart": read_json_object(case_study_dir / "dfba_glycogen_scenario.json"),
            "dfba_glycogen_scenario": _table_preview(case_study_dir / "dfba_glycogen_scenario.csv", limit=80),
            "paper_evidence_reaction_overlay": _table_preview(case_study_dir / "paper_evidence_reaction_overlay.csv", limit=80),
            "paper_evidence_mapping_summary": read_json_object(case_study_dir / "paper_evidence_mapping_summary.json"),
            "status": str(paper_reproduction_manifest.get("status") or "not_available") if paper_reproduction_manifest else "not_available",
            "guidance": (
                str(paper_reproduction_manifest.get("guidance") or "")
                if paper_reproduction_manifest
                else "No paper reproduction manifest is attached to this run."
            ),
        },
        "key_files": key_files,
        "guidance": (
            "This endpoint aggregates analysis outputs and visualization readiness. "
            "It does not run analyses; submit workflow or visualization jobs from their existing endpoints."
        ),
    }


def run_verify_summary(run_id: str) -> dict[str, Any]:
    package = resolve_run_package(run_id)
    summary = run_summary(run_id)
    jobs = _latest_jobs_for_run(run_id, limit=30)
    failed_jobs = [job for job in jobs if job.get("status") == "failed"]
    report_manifest_path = package / "report_results" / "report_manifest.json"
    report_manifest = read_json_object(report_manifest_path)
    sammi_checks = _collect_json_files(package, "sammi_native_export_check.json", limit=20)
    risky_checks = [
        item for item in sammi_checks
        if str(item.get("status", "")).lower() not in {"passed", "ready", "ok", "completed"}
    ]
    comparison_dir = package / "variant_comparison"
    comparison_interpretation = _table_preview(comparison_dir / "model_comparison_interpretation_summary.csv", limit=10)
    comparison_layers = _table_preview(comparison_dir / "model_comparison_layer_status.csv", limit=10)
    comparison_drilldown = _table_preview(comparison_dir / "model_reaction_drilldown.csv", limit=20)
    key_files = [
        _file_summary(package, report_manifest_path, "report_manifest"),
        _file_summary(package, package / "report_results" / "production_design_report.html", "production_design_report"),
        _file_summary(package, package / "report_results" / "full_audit_report.html", "full_audit_report"),
        _file_summary(package, package / "report_results" / "shewanella_trigger_reproduction_report.html", "shewanella_trigger_reproduction_report"),
        _file_summary(package, package / "report_results" / "paper_reproduction_report_manifest.json", "paper_reproduction_report_manifest"),
        _file_summary(package, package / "workflow_results" / "workflow_selection.csv", "workflow_selection"),
        _file_summary(package, package / "workflow_results" / "model_variant_registry.csv", "model_variant_registry"),
        _file_summary(package, comparison_dir / "model_comparison_interpretation_summary.csv", "model_comparison_interpretation_summary"),
        _file_summary(package, comparison_dir / "model_reaction_drilldown.csv", "model_reaction_drilldown"),
    ]
    readiness_flags = []
    if not summary.get("model_variants"):
        readiness_flags.append({"severity": "warning", "message": "No model variants were found for this run."})
    if summary.get("model_variants") and not comparison_interpretation:
        readiness_flags.append({"severity": "warning", "message": "Model comparison interpretation has not been generated yet."})
    same_source_only = bool(comparison_layers) and any(
        str(row.get("layer")) == "structural_changes" and str(row.get("status")) == "same_source"
        for row in comparison_layers
    )
    behavior_ready = any(
        str(row.get("layer")) == "behavior_outputs" and str(row.get("status")) == "ready"
        for row in comparison_layers
    )
    if same_source_only and not behavior_ready:
        readiness_flags.append(
            {
                "severity": "info",
                "message": "Same-source variants are explained structurally, but behavior outputs are still recommended for interpretation.",
            }
        )
    if not summary.get("reports") and not report_manifest:
        readiness_flags.append({"severity": "info", "message": "No generated reports were found yet."})
    if failed_jobs:
        readiness_flags.append({"severity": "warning", "message": f"{len(failed_jobs)} failed job(s) are present in recent history."})
    if risky_checks:
        readiness_flags.append({"severity": "info", "message": f"{len(risky_checks)} SAMMI checker file(s) need review."})
    return {
        "run_id": run_id,
        "status": "ready" if summary.get("reports") or report_manifest else "partial",
        "reports": summary.get("reports", []),
        "report_manifest": report_manifest,
        "report_manifest_path": str(report_manifest_path),
        "jobs": jobs,
        "failed_jobs": failed_jobs,
        "sammi_native_checks": sammi_checks,
        "model_comparison": {
            "interpretation_summary": comparison_interpretation,
            "layer_status": comparison_layers,
            "reaction_drilldown_preview": comparison_drilldown,
            "same_source_only": same_source_only,
            "behavior_outputs_ready": behavior_ready,
        },
        "readiness_flags": readiness_flags,
        "key_files": key_files,
        "guidance": (
            "Verify & Report is the final quality gate. Review failed jobs, missing reports, "
            "external dependency readiness, and visualization checker outputs before presenting results."
        ),
    }


def run_ml_hybrid_profiles(run_id: str) -> list[dict[str, Any]]:
    return list_ml_hybrid_profiles(resolve_run_package(run_id))


def run_ml_hybrid_profile_detail(run_id: str, profile_id: str) -> dict[str, Any]:
    return get_ml_hybrid_profile_detail(resolve_run_package(run_id), profile_id)


def run_ml_hybrid_profile_comparison(run_id: str) -> dict[str, Any]:
    return compare_ml_hybrid_profiles(resolve_run_package(run_id))


def run_ml_hybrid_profile_exports(run_id: str, profile_id: str) -> dict[str, Any]:
    return list_ml_hybrid_profile_exports(resolve_run_package(run_id), profile_id)


def run_ml_hybrid_external_results(run_id: str, profile_id: str) -> dict[str, Any]:
    return list_ml_hybrid_external_results(resolve_run_package(run_id), profile_id)


def run_ml_hybrid_external_result_detail(run_id: str, profile_id: str, import_id: str) -> dict[str, Any]:
    return get_ml_hybrid_external_result_detail(resolve_run_package(run_id), profile_id, import_id)


def run_sammi_reactions(run_id: str, *, variant_id: str = "", query: str = "", limit: int = 50) -> dict[str, Any]:
    return list_sammi_model_reactions(
        resolve_run_package(run_id),
        variant_id=variant_id,
        query=query,
        limit=limit,
    )


def run_sammi_filter_preview(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return preview_sammi_filter(
        resolve_run_package(run_id),
        variant_id=str(payload.get("variant_id", "")),
        grouping_mode=str(payload.get("grouping_mode", "subsystem")),
        overlay_source=str(payload.get("overlay_source", "none")),
        reaction_filter=payload.get("reaction_filter", ""),
        subsystem_filter=payload.get("subsystem_filter", ""),
        top_n=int(payload.get("top_n", 120) or 0),
        include_currency_metabolites=bool(payload.get("include_currency_metabolites", False)),
    )


def run_sammi_native_exports(run_id: str, *, variant_id: str = "") -> dict[str, Any]:
    return list_sammi_native_exports(resolve_run_package(run_id), variant_id=variant_id)


def create_ml_hybrid_profile_job(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    package = resolve_run_package(run_id)

    def callback(log_path: Path) -> dict[str, Any]:
        log_path.write_text("Building ML/HYBRID analysis profile.\n", encoding="utf-8")
        result = run_ml_hybrid_profile(
            package,
            profile_id=str(payload.get("profile_id", "")),
            task_type=str(payload.get("task_type", "auto")),
            selected_variant_ids=payload.get("selected_variant_ids") or [],
            target_column=str(payload.get("target_column", "")),
            feature_sources=payload.get("feature_sources") or [],
            benchmark_feature_sets=payload.get("benchmark_feature_sets") or [],
            max_features=int(payload.get("max_features", 50) or 50),
        )
        log_path.write_text(
            log_path.read_text(encoding="utf-8") + f"{result.message}\n",
            encoding="utf-8",
        )
        return {
            "result_status": result.status,
            "message": result.message,
            "output_dir": result.output_dir,
            "manifest": result.manifest,
            "files": result.files,
        }

    return run_sync_job("ml_hybrid_profile", run_id, callback)


def create_ml_hybrid_profile_export_job(run_id: str, profile_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    package = resolve_run_package(run_id)
    export_format = str(payload.get("export_format", "both") or "both")

    def callback(log_path: Path) -> dict[str, Any]:
        log_path.write_text(
            f"Exporting ML/HYBRID profile bundle.\nprofile_id={profile_id}\nexport_format={export_format}\n",
            encoding="utf-8",
        )
        result = export_ml_hybrid_profile(package, profile_id, export_format=export_format)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{result.message}\n")
            handle.write(f"status={result.status}\n")
            handle.write(f"output_dir={result.output_dir}\n")
        return {
            "result_status": result.status,
            "message": result.message,
            "output_dir": result.output_dir,
            "manifest": result.manifest,
            "files": result.files,
        }

    return run_sync_job("ml_hybrid_profile_export", run_id, callback)


def create_ml_hybrid_external_import_job(run_id: str, profile_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    package = resolve_run_package(run_id)
    source_dir = str(payload.get("source_dir", "") or "")
    result_format = str(payload.get("result_format", "generic_tabular") or "generic_tabular")
    import_id = str(payload.get("import_id", "") or "")

    def callback(log_path: Path) -> dict[str, Any]:
        log_path.write_text(
            (
                "Importing external ML/HYBRID results.\n"
                f"profile_id={profile_id}\n"
                f"result_format={result_format}\n"
                f"source_dir={source_dir}\n"
            ),
            encoding="utf-8",
        )
        result = import_ml_hybrid_external_results(
            package,
            profile_id,
            source_dir=source_dir,
            result_format=result_format,
            import_id=import_id,
        )
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"{result.message}\n")
            handle.write(f"status={result.status}\n")
            handle.write(f"output_dir={result.output_dir}\n")
        return {
            "result_status": result.status,
            "message": result.message,
            "output_dir": result.output_dir,
            "manifest": result.manifest,
            "files": result.files,
        }

    return run_sync_job("ml_hybrid_external_import", run_id, callback)


def create_sammi_visualization_job(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    package = resolve_run_package(run_id)

    def callback(log_path: Path) -> dict[str, Any]:
        log_path.write_text(
            "Generating SAMMI-compatible visualization package.\n",
            encoding="utf-8",
        )
        result = build_sammi_visualization_package(
            package,
            variant_id=str(payload.get("variant_id", "")),
            grouping_mode=str(payload.get("grouping_mode", "subsystem")),
            overlay_source=str(payload.get("overlay_source", "none")),
            reaction_filter=payload.get("reaction_filter", ""),
            ml_profile_id=str(payload.get("ml_profile_id", "")),
        )
        log_path.write_text(
            log_path.read_text(encoding="utf-8") + f"{result.message}\n",
            encoding="utf-8",
        )
        return {
            "result_status": result.status,
            "message": result.message,
            "output_dir": str(result.output_dir),
            "manifest": result.manifest,
            "files": result.files,
        }

    return run_sync_job("sammi_visualization", run_id, callback)


def create_sammi_interactive_render_job(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    package = resolve_run_package(run_id)

    def callback(log_path: Path) -> dict[str, Any]:
        log_path.write_text("Generating interactive SAMMI-style network map.\n", encoding="utf-8")
        result = build_sammi_interactive_render(
            package,
            variant_id=str(payload.get("variant_id", "")),
            grouping_mode=str(payload.get("grouping_mode", "subsystem")),
            overlay_source=str(payload.get("overlay_source", "none")),
            reaction_filter=payload.get("reaction_filter", ""),
            subsystem_filter=payload.get("subsystem_filter", ""),
            ml_profile_id=str(payload.get("ml_profile_id", "")),
            top_n=int(payload.get("top_n", 120) or 0),
            include_currency_metabolites=bool(payload.get("include_currency_metabolites", False)),
        )
        log_path.write_text(
            log_path.read_text(encoding="utf-8") + f"{result.message}\n",
            encoding="utf-8",
        )
        return {
            "result_status": result.status,
            "message": result.message,
            "output_dir": str(result.output_dir),
            "manifest": result.manifest,
            "files": result.files,
        }

    return run_sync_job("sammi_interactive_render", run_id, callback)


def create_sammi_native_export_job(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    package = resolve_run_package(run_id)

    def callback(log_path: Path) -> dict[str, Any]:
        log_path.write_text("Generating SAMMI-native session export.\n", encoding="utf-8")
        result = build_sammi_native_export(
            package,
            variant_id=str(payload.get("variant_id", "")),
            grouping_mode=str(payload.get("grouping_mode", "subsystem")),
            overlay_source=str(payload.get("overlay_source", "none")),
            reaction_filter=payload.get("reaction_filter", ""),
            subsystem_filter=payload.get("subsystem_filter", ""),
            ml_profile_id=str(payload.get("ml_profile_id", "")),
            top_n=int(payload.get("top_n", 120) or 0),
            include_currency_metabolites=bool(payload.get("include_currency_metabolites", False)),
        )
        log_path.write_text(
            log_path.read_text(encoding="utf-8") + f"{result.message}\n",
            encoding="utf-8",
        )
        return {
            "result_status": result.status,
            "message": result.message,
            "output_dir": str(result.output_dir),
            "manifest": result.manifest,
            "files": result.files,
        }

    return run_sync_job("sammi_native_export", run_id, callback)


def create_report_job(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    package = resolve_run_package(run_id)

    def callback(log_path: Path) -> dict[str, Any]:
        log_path.write_text("Building report bundle.\n", encoding="utf-8")
        result = build_report_bundle(
            package,
            preset=str(payload.get("preset", "full_audit_report")),
            active_variant_id=payload.get("active_variant_id") or payload.get("selected_variant_ids") or "",
        )
        log_path.write_text(
            log_path.read_text(encoding="utf-8") + f"{result.message}\n",
            encoding="utf-8",
        )
        return {
            "result_status": result.status,
            "message": result.message,
            "report_path": result.report_path,
            "manifest_path": result.manifest_path,
            "selection_path": result.selection_path,
        }

    return run_sync_job("report_bundle", run_id, callback)


def create_user_workflow_job(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    package = resolve_run_package(run_id)
    payload = _merge_run_default_workflow(package, payload)

    def callback(log_path: Path) -> dict[str, Any]:
        log_path.write_text(
            (
                "Running selected Model & Analysis workflow.\n"
                f"model_generation_methods={payload.get('model_generation_methods')}\n"
                f"analysis_modules={payload.get('analysis_modules')}\n"
                f"selected_model_variant_ids={payload.get('selected_model_variant_ids')}\n"
            ),
            encoding="utf-8",
        )
        result = run_user_package_minimal(
            package,
            model_generation_methods=payload.get("model_generation_methods"),
            analysis_modules=payload.get("analysis_modules"),
            selected_model_variant_id=payload.get("selected_model_variant_ids") or payload.get("selected_model_variant_id") or "",
            report_preset=str(payload.get("report_preset", "full_audit_report") or "full_audit_report"),
            model_generation_parameters=payload.get("model_generation_parameters") if isinstance(payload.get("model_generation_parameters"), dict) else None,
            analysis_parameters=payload.get("analysis_parameters") if isinstance(payload.get("analysis_parameters"), dict) else None,
            gecko_adapter_parameters=payload.get("gecko_adapter_parameters") if isinstance(payload.get("gecko_adapter_parameters"), dict) else None,
            gecko_ec_model_mode=str(payload.get("gecko_ec_model_mode") or "full_ecModel"),
        )
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"status={result.status}\n")
            handle.write(f"message={result.message}\n")
            handle.write(f"files={json.dumps(result.files, ensure_ascii=False)}\n")
        return {
            "result_status": result.status,
            "message": result.message,
            "output_dir": str(package),
            "files": result.files,
            "step_count": len(result.step_rows),
            "steps": result.step_rows,
        }

    return run_sync_job("user_workflow", run_id, callback)


def run_workflow_parameter_schema(run_id: str) -> dict[str, Any]:
    """Return parameter schema metadata after validating that the run exists."""

    resolve_run_package(run_id)
    return workflow_parameter_schema()


def preview_workflow_parameters(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize selected workflow parameters without running the workflow."""

    resolve_run_package(run_id)
    return workflow_parameter_preview(
        model_generation_parameters=payload.get("model_generation_parameters") if isinstance(payload.get("model_generation_parameters"), dict) else None,
        analysis_parameters=payload.get("analysis_parameters") if isinstance(payload.get("analysis_parameters"), dict) else None,
        selected_model_generation_methods=payload.get("model_generation_methods"),
        selected_analysis_modules=payload.get("analysis_modules"),
    )


def run_gecko_status(run_id: str) -> dict[str, Any]:
    """Return GECKO package, adapter, and probe status for a run package."""

    package = resolve_run_package(run_id)
    gecko_package = package / "gecko_package"
    gecko_run = package / "gecko_run_results"
    export_manifest = read_json_object(gecko_package / "gecko_export_manifest.json")
    adapter_config = read_json_object(gecko_package / "gecko_adapter_config.json")
    protocol_config = read_json_object(gecko_package / "gecko_protocol_config.json")
    probe_manifest = read_json_object(gecko_run / "gecko_adapter_probe_manifest.json")
    external_manifest = read_json_object(gecko_run / "gecko_external_run_manifest.json")
    external_summary = read_csv_rows(gecko_run / "gecko_external_run_summary.csv")
    package_status = validate_gecko_package(gecko_package)
    return {
        "run_id": run_id,
        "status": "ok",
        "gecko_package_dir": str(gecko_package),
        "gecko_run_dir": str(gecko_run),
        "package_status": package_status,
        "export_manifest_path": str(gecko_package / "gecko_export_manifest.json"),
        "export_manifest_exists": bool(export_manifest),
        "adapter_config_path": str(gecko_package / "gecko_adapter_config.json"),
        "adapter_config_exists": bool(adapter_config),
        "adapter_config": adapter_config,
        "protocol_config_path": str(gecko_package / "gecko_protocol_config.json"),
        "protocol_config": protocol_config,
        "adapter_file_path": str(gecko_package / "generated_adapter.m"),
        "adapter_file_exists": (gecko_package / "generated_adapter.m").exists(),
        "class_adapter_file_path": str(gecko_package / f"{adapter_config.get('adapter_class_name', '')}.m") if adapter_config else "",
        "class_adapter_file_exists": bool(adapter_config and (gecko_package / f"{adapter_config.get('adapter_class_name', '')}.m").exists()),
        "adapter_readiness_path": str(gecko_package / "gecko_adapter_readiness.csv"),
        "adapter_readiness": read_csv_rows(gecko_package / "gecko_adapter_readiness.csv"),
        "probe_manifest_path": str(gecko_run / "gecko_adapter_probe_manifest.json"),
        "probe_manifest_exists": bool(probe_manifest),
        "probe_manifest": probe_manifest,
        "external_run_manifest_path": str(gecko_run / "gecko_external_run_manifest.json"),
        "external_run_manifest_exists": bool(external_manifest),
        "external_run_manifest": external_manifest,
        "external_run_summary_path": str(gecko_run / "gecko_external_run_summary.csv"),
        "external_run_summary": external_summary,
        "external_run_status": external_manifest.get("status", "") if isinstance(external_manifest, dict) else "",
        "external_output_status": external_manifest.get("output_status", []) if isinstance(external_manifest, dict) else [],
    }


def run_gecko_adapter_preview(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Generate GECKO adapter config/files for the selected run without launching MATLAB."""

    package = resolve_run_package(run_id)
    payload = _merge_run_default_workflow(package, payload)
    gecko_package = package / "gecko_package"
    gecko_package.mkdir(parents=True, exist_ok=True)
    model_path = _run_model_path(package)
    if model_path is None:
        raise ApiError(404, "No staged GEM/GSMM model was found for this run.")
    target_model = gecko_package / "model.xml"
    if not target_model.exists() or not _same_path(model_path, target_model):
        shutil.copyfile(model_path, target_model)
    adapter_parameters = payload.get("gecko_adapter_parameters") if isinstance(payload.get("gecko_adapter_parameters"), dict) else payload
    model_id = str(adapter_parameters.get("model_id") or _model_id_from_existing_manifest(gecko_package) or package.name)
    mode = str(payload.get("gecko_ec_model_mode") or adapter_parameters.get("ec_model_mode") or "full_ecModel")
    result = build_gecko_adapter_files(
        gecko_package,
        adapter_parameters,
        model_id=model_id,
        model_path=target_model,
        ec_model_mode=mode,
    )
    return {
        "run_id": run_id,
        "result_status": result.status,
        "message": result.message,
        "gecko_package_dir": str(gecko_package),
        "files": result.files,
        "adapter_config": result.config,
        "readiness": result.readiness,
    }


def _merge_run_default_workflow(package: Path, payload: dict[str, Any]) -> dict[str, Any]:
    """Fill missing workflow request fields from run_config.default_workflow."""

    merged = dict(payload or {})
    config = read_json_object(package / "run_config.json")
    defaults = config.get("default_workflow") if isinstance(config, dict) else None
    if not isinstance(defaults, dict):
        return merged
    for key in (
        "model_generation_methods",
        "analysis_modules",
        "selected_model_variant_ids",
        "report_preset",
        "analysis_parameters",
        "model_generation_parameters",
        "gecko_adapter_parameters",
        "gecko_ec_model_mode",
    ):
        value = merged.get(key)
        if value in (None, "", [], {}) and key in defaults:
            merged[key] = defaults[key]
    return merged


def create_gecko_adapter_probe_job(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Run an opt-in MATLAB probe for the generated GECKO adapter."""

    package = resolve_run_package(run_id)
    gecko_package = package / "gecko_package"
    gecko_run = package / "gecko_run_results"
    config = load_local_backend_config()
    matlab_cmd = str(payload.get("matlab_cmd") or config.get("matlab_cmd") or os.environ.get("MATLAB_CMD") or "matlab")
    gecko_home = str(payload.get("gecko_home") or config.get("gecko_home") or os.environ.get("GECKO_HOME") or "")
    raven_home = str(payload.get("raven_home") or config.get("raven_home") or os.environ.get("RAVEN_HOME") or "")
    solver = str(payload.get("solver") or config.get("solver") or os.environ.get("OMICS_GEM_SOLVER") or "")
    timeout_seconds = int(payload.get("timeout_seconds") or 300)
    final_status = "skipped"
    if (gecko_package / "generated_adapter.m").exists() and _resolve_command_or_path(matlab_cmd) and gecko_home and Path(gecko_home).exists():
        final_status = "completed"

    def callback(log_path: Path) -> dict[str, Any]:
        log_path.write_text("Running GECKO adapter MATLAB probe.\n", encoding="utf-8")
        result = run_gecko_adapter_probe(
            gecko_package,
            gecko_run,
            matlab_cmd=matlab_cmd,
            gecko_home=gecko_home,
            raven_home=raven_home,
            solver=solver,
            timeout_seconds=timeout_seconds,
        )
        with log_path.open("a", encoding="utf-8", errors="replace") as handle:
            handle.write(f"status={result.status}\n")
            handle.write(f"message={result.message}\n")
            handle.write(f"files={json.dumps(result.files, ensure_ascii=False)}\n")
        return {
            "result_status": result.status,
            "message": result.message,
            "files": result.files,
            "gecko_status": run_gecko_status(run_id),
        }

    return run_sync_job("gecko_adapter_probe", run_id, callback, final_status=final_status)


def create_gecko_external_run_job(run_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Run the opt-in Shewanella MATLAB/GECKO external workflow."""

    package = resolve_run_package(run_id)
    gecko_package = package / "gecko_package"
    gecko_run = package / "gecko_run_results"
    config = load_local_backend_config()
    matlab_cmd = _default_matlab_cmd(payload, config)
    gecko_home = str(payload.get("gecko_home") or config.get("gecko_home") or os.environ.get("GECKO_HOME") or r"D:\MatExt\GECKO")
    raven_home = str(payload.get("raven_home") or config.get("raven_home") or os.environ.get("RAVEN_HOME") or r"D:\MatExt\RAVEN")
    solver = str(payload.get("solver") or config.get("solver") or os.environ.get("OMICS_GEM_SOLVER") or "")
    timeout_seconds = int(payload.get("timeout_seconds") or 7200)
    run_probe_first = bool(payload.get("run_probe_first", True))
    run_full_ecmodel = bool(payload.get("run_full_ecmodel", True))
    run_condition_models = bool(payload.get("run_condition_models", True))
    final_status = "completed" if _resolve_command_or_path(matlab_cmd) and Path(gecko_home).exists() else "skipped"

    def callback(log_path: Path) -> dict[str, Any]:
        log_path.write_text("Running Shewanella GECKO external workflow.\n", encoding="utf-8")
        probe_payload: dict[str, Any] | None = None
        if run_probe_first:
            probe = run_gecko_adapter_probe(
                gecko_package,
                gecko_run,
                matlab_cmd=matlab_cmd,
                gecko_home=gecko_home,
                raven_home=raven_home,
                solver=solver,
                timeout_seconds=min(timeout_seconds, 600),
            )
            probe_payload = {
                "result_status": probe.status,
                "message": probe.message,
                "files": probe.files,
            }
            with log_path.open("a", encoding="utf-8", errors="replace") as handle:
                handle.write(f"probe_status={probe.status}\n")
                handle.write(f"probe_message={probe.message}\n")
            if probe.status != "probe_passed":
                return {
                    "result_status": "skipped",
                    "message": "GECKO external run skipped because adapter probe did not pass.",
                    "probe": probe_payload,
                    "gecko_status": run_gecko_status(run_id),
                }
        result = run_shewanella_gecko_external_workflow(
            gecko_package,
            gecko_run,
            matlab_cmd=matlab_cmd,
            gecko_home=gecko_home,
            raven_home=raven_home,
            solver=solver,
            dry_run=bool(payload.get("dry_run", False)),
            timeout_seconds=timeout_seconds,
            run_full_ecmodel=run_full_ecmodel,
            run_condition_models=run_condition_models,
        )
        with log_path.open("a", encoding="utf-8", errors="replace") as handle:
            handle.write(f"external_status={result.status}\n")
            handle.write(f"external_message={result.message}\n")
            handle.write(f"files={json.dumps(result.files, ensure_ascii=False)}\n")
        return {
            "result_status": result.status,
            "message": result.message,
            "probe": probe_payload,
            "files": result.files,
            "gecko_status": run_gecko_status(run_id),
        }

    return run_sync_job("gecko_external_run", run_id, callback, final_status=final_status)


def legacy_pipeline_stub_job(run_id: str) -> dict[str, Any]:
    resolve_run_package(run_id)

    def callback(log_path: Path) -> dict[str, Any]:
        message = (
            "Legacy pipeline stub: full asynchronous pipeline execution is not implemented in this endpoint. "
            "Use POST /api/runs/{run_id}/workflow/run for the guided Model & Analysis workflow."
        )
        log_path.write_text(message + "\n", encoding="utf-8")
        return {
            "result_status": "legacy_stub",
            "message": message,
            "recommended_endpoint": f"/api/runs/{run_id}/workflow/run",
        }

    return run_sync_job("pipeline", run_id, callback, final_status="skipped")


def create_backend_environment_repair_job(payload: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("mode", "minimal")).strip().lower()
    if mode not in {"minimal", "full"}:
        raise ApiError(400, "Repair mode must be 'minimal' or 'full'.")
    dry_run = bool(payload.get("dry_run", True))
    recreate_venv = bool(payload.get("recreate_venv", False))
    confirm = str(payload.get("confirm", ""))
    if not dry_run and confirm != "REPAIR_PYTHON_ENV":
        raise ApiError(400, "Set confirm to REPAIR_PYTHON_ENV before running a real repair.")
    if recreate_venv and not dry_run:
        raise ApiError(
            409,
            "Live API repair cannot recreate .venv because the current backend may be running inside it. "
            "Close the desktop/API backend and run .\\start_omics_gem_router.ps1 -RecreateVenv from a terminal.",
        )
    script = APP_ROOT / "tools" / "repair_backend_env.ps1"
    if not script.exists():
        raise ApiError(404, f"Repair script not found: {script}")

    ps_mode = "Minimal" if mode == "minimal" else "Full"
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-Mode",
        ps_mode,
    ]
    if recreate_venv:
        command.append("-RecreateVenv")
    final_status = "skipped" if dry_run else "completed"

    def callback(log_path: Path) -> dict[str, Any]:
        header = [
            "Backend Python environment repair job.",
            f"mode={mode}",
            f"dry_run={dry_run}",
            f"recreate_venv={recreate_venv}",
            "command=" + " ".join(command),
            "",
        ]
        log_path.write_text("\n".join(header), encoding="utf-8")
        if dry_run:
            return {
                "result_status": "dry_run",
                "message": "Dry run only; no environment changes were made.",
                "mode": mode,
                "dry_run": dry_run,
                "recreate_venv": recreate_venv,
                "command": command,
                "readiness": backend_environment_readiness(),
            }
        with log_path.open("a", encoding="utf-8", errors="replace") as handle:
            result = subprocess.run(
                command,
                cwd=str(APP_ROOT),
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        if result.returncode != 0:
            raise RuntimeError(f"Repair command failed with exit code {result.returncode}.")
        return {
            "result_status": "completed",
            "message": "Backend Python environment repair completed.",
            "mode": mode,
            "dry_run": dry_run,
            "recreate_venv": recreate_venv,
            "command": command,
            "readiness": backend_environment_readiness(),
        }

    return run_sync_job("backend_environment_repair", "environment", callback, final_status=final_status)


def run_sync_job(
    job_type: str,
    run_id: str,
    callback: Callable[[Path], dict[str, Any]],
    *,
    final_status: str = "completed",
) -> dict[str, Any]:
    TASK_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    job_id = f"{job_type}_{uuid.uuid4().hex[:12]}"
    status_path = TASK_LOGS_DIR / f"{job_id}.json"
    log_path = TASK_LOGS_DIR / f"{job_id}.log"
    started = time.time()
    status: dict[str, Any] = {
        "job_id": job_id,
        "job_type": job_type,
        "run_id": run_id,
        "status": "running",
        "created_at": started,
        "updated_at": started,
        "log_path": str(log_path),
    }
    write_json(status_path, status)
    try:
        result = callback(log_path)
        status.update(
            {
                "status": final_status,
                "updated_at": time.time(),
                "elapsed_seconds": round(time.time() - started, 6),
                "result": result,
            }
        )
    except Exception as exc:
        log_path.write_text((log_path.read_text(encoding="utf-8") if log_path.exists() else "") + f"ERROR: {type(exc).__name__}: {exc}\n", encoding="utf-8")
        status.update(
            {
                "status": "failed",
                "updated_at": time.time(),
                "elapsed_seconds": round(time.time() - started, 6),
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    write_json(status_path, status)
    return status


def get_job(job_id: str) -> dict[str, Any]:
    path = safe_job_path(job_id, ".json")
    if not path.exists():
        raise ApiError(404, f"Job not found: {job_id}")
    return read_json_object(path)


def list_jobs(job_type: str = "", limit: int = 20) -> list[dict[str, Any]]:
    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200
    normalized_type = job_type.strip()
    if normalized_type and not re_match_job_id(normalized_type):
        return []
    if not TASK_LOGS_DIR.exists():
        return []
    rows: list[dict[str, Any]] = []
    for path in TASK_LOGS_DIR.glob("*.json"):
        try:
            item = read_json_object(path)
        except json.JSONDecodeError:
            continue
        if normalized_type and item.get("job_type") != normalized_type:
            continue
        rows.append(item)
    rows.sort(key=lambda item: float(item.get("updated_at") or item.get("created_at") or 0), reverse=True)
    return rows[:limit]


def get_job_logs(job_id: str) -> dict[str, str]:
    path = safe_job_path(job_id, ".log")
    if not path.exists():
        raise ApiError(404, f"Job log not found: {job_id}")
    return {"job_id": job_id, "log": path.read_text(encoding="utf-8", errors="replace")}


def resolve_safe_file(path_text: str) -> Path:
    # Bundled reference data follows the app; user_runs follows the selected workspace.
    candidate = Path(path_text)
    if not candidate.is_absolute() and candidate.parts and candidate.parts[0] in {"case_studies", "resources"}:
        path_text = str(APP_ROOT / candidate)
    return resolve_safe_file_path(
        path_text,
        workspace_root=WORKSPACE_ROOT,
        allowed_roots=ALLOWED_FILE_ROOTS,
        error_factory=ApiError,
    )


def resolve_run_package(run_id: str) -> Path:
    if not run_id or any(part in run_id for part in ("..", "/", "\\")):
        raise ApiError(400, "Invalid run_id.")
    candidates = [
        USER_RUNS_DIR / run_id,
        EXAMPLES_DIR / run_id,
        EXAMPLES_DIR / "ecoli" if run_id == "ecoli" else Path("__missing__"),
        EXAMPLES_DIR / "ecoli_real" if run_id == "ecoli_real" else Path("__missing__"),
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate.resolve()
    raise ApiError(404, f"Run package not found: {run_id}")


def _resolve_run_package_context(package: Path) -> dict[str, Any]:
    return resolve_run_package_context(
        package,
        readers={
            "csv": read_csv_rows,
            "json": read_json_object,
            "variant_registry": read_model_variant_registry,
            "edit_reaction_index": read_model_edit_reaction_index,
        },
    )


def run_overview(package: Path) -> dict[str, Any]:
    context = _resolve_run_package_context(package)
    identity = context.get("package_identity", {}) if isinstance(context.get("package_identity"), dict) else {}
    inventory = context.get("artifact_inventory", {}) if isinstance(context.get("artifact_inventory"), dict) else {}
    input_map = inventory.get("input_map", {}) if isinstance(inventory.get("input_map"), dict) else {}
    variant_registry = inventory.get("variant_registry", {}) if isinstance(inventory.get("variant_registry"), dict) else {}
    reports = inventory.get("reports", {}) if isinstance(inventory.get("reports"), dict) else {}
    visualization_count = len(list((package / "visualization_results" / "sammi").glob("*/sammi_package_manifest.json"))) if (package / "visualization_results" / "sammi").exists() else 0
    source_manifest = identity.get("source_manifest", {}) if isinstance(identity.get("source_manifest"), dict) else {}
    return {
        "run_id": identity.get("run_id") or package.name,
        "path": identity.get("run_dir") or str(package),
        "input_count": input_map.get("count", 0),
        "model_variant_count": variant_registry.get("count", 0),
        "report_count": reports.get("count", 0),
        "visualization_count": visualization_count,
        "last_modified": identity.get("last_modified", package.stat().st_mtime if package.exists() else 0),
        "import_status": source_manifest.get("import_status", "native"),
        "import_source_path": source_manifest.get("source_path", ""),
        "imported_at": identity.get("imported_at", ""),
        "import_manifest_path": source_manifest.get("import_manifest_path", ""),
    }


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    delimiter = "\t" if path.suffix.lower() in {".tsv", ".txt"} else ","
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter=delimiter))


def read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_resource_index() -> dict[str, Any]:
    if not RESOURCE_INDEX_PATH.exists():
        return {
            "version": 1,
            "status": "partial",
            "organisms": [],
            "model_resources": [],
            "omics_resources": [],
            "guidance": f"Resource index is missing: {RESOURCE_INDEX_PATH}",
        }
    try:
        index = read_json_object(RESOURCE_INDEX_PATH)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "version": 1,
            "status": "partial",
            "organisms": [],
            "model_resources": [],
            "omics_resources": [],
            "guidance": f"Resource index could not be read: {exc}",
        }
    if not isinstance(index, dict):
        return {
            "version": 1,
            "status": "partial",
            "organisms": [],
            "model_resources": [],
            "omics_resources": [],
            "guidance": "Resource index is not a JSON object.",
        }
    index.setdefault("organisms", [])
    index.setdefault("model_resources", [])
    index.setdefault("omics_resources", [])
    index.setdefault("status", "ready")
    index.setdefault("guidance", "")
    _merge_resource_connector_caches(index)
    _apply_resource_cross_source_links(index)
    return index


def _resource_records(index: dict[str, Any], key: str) -> list[dict[str, Any]]:
    rows = index.get(key)
    if not isinstance(rows, list):
        return []
    resource_kind = "model" if key == "model_resources" else "omics"
    return [_normalize_resource_record(dict(row), resource_kind) for row in rows if isinstance(row, dict)]


def _apply_resource_cross_source_links(index: dict[str, Any]) -> None:
    """Attach canonical ids and source-link groups without mutating cache files."""

    for key, resource_kind in (("model_resources", "model"), ("omics_resources", "omics")):
        rows = index.get(key)
        if not isinstance(rows, list):
            continue
        groups: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            canonical_id = _canonical_resource_id(row, resource_kind)
            row["canonical_resource_id"] = canonical_id
            groups.setdefault(canonical_id, []).append(row)
        for canonical_id, group_rows in groups.items():
            source_links = [_resource_source_link(row) for row in group_rows if isinstance(row, dict)]
            deduped_links: list[dict[str, str]] = []
            seen_links: set[tuple[str, str, str]] = set()
            for link in source_links:
                key_tuple = (
                    str(link.get("source_database") or ""),
                    str(link.get("accession") or ""),
                    str(link.get("external_url") or ""),
                )
                if key_tuple in seen_links:
                    continue
                seen_links.add(key_tuple)
                deduped_links.append(link)
            cross_source_ids = [
                str(row.get("resource_id") or "")
                for row in group_rows
                if isinstance(row, dict) and str(row.get("resource_id") or "")
            ]
            for row in group_rows:
                if not isinstance(row, dict):
                    continue
                for value in (row.get("accession"), row.get("model_id")):
                    text = str(value or "")
                    if text and text not in cross_source_ids:
                        cross_source_ids.append(text)
                for token in _resource_accession_tokens(row):
                    if token and token not in cross_source_ids:
                        cross_source_ids.append(token)
            for row in group_rows:
                row["canonical_resource_id"] = canonical_id
                row["cross_source_ids"] = cross_source_ids
                row["source_links"] = deduped_links
                row["duplicate_group_size"] = len(group_rows)


def _canonical_resource_id(row: dict[str, Any], resource_kind: str) -> str:
    organism = _slug_token(str(row.get("organism_id") or row.get("organism_name") or "unknown"))
    if resource_kind == "model":
        model_token = _slug_token(str(row.get("model_id") or row.get("accession") or row.get("resource_id") or "model"))
        return f"model::{organism}::{model_token}"
    accession_tokens = _resource_accession_tokens(row)
    if accession_tokens:
        return f"omics::{accession_tokens[0]}"
    omics_type = _slug_token(str(row.get("omics_type") or "omics"))
    resource_id = _slug_token(str(row.get("resource_id") or "resource"))
    return f"omics::{organism}::{omics_type}::{resource_id}"


def _resource_text_fields_for_accessions(row: dict[str, Any]) -> list[str]:
    fields = (
        "accession",
        "source_accession",
        "study_accession",
        "secondary_accession",
        "dataset_id",
        "model_id",
        "external_url",
    )
    return [str(row.get(field) or "") for field in fields if str(row.get(field) or "")]


def _resource_accession_tokens(row: dict[str, Any]) -> list[str]:
    tokens: list[str] = []
    seen: set[str] = set()

    def add(token: str) -> None:
        clean = token.strip().lower()
        if clean and clean not in seen:
            seen.add(clean)
            tokens.append(clean)

    for raw_text in _resource_text_fields_for_accessions(row):
        upper = str(raw_text or "").strip().upper()
        for match in re.finditer(r"\bE[-_]?GEOD[-_]?(\d+)\b", upper):
            add(f"geo::gse{match.group(1)}")
        for match in re.finditer(r"\bGSE[-_]?(\d+)\b", upper):
            add(f"geo::gse{match.group(1)}")
        for match in re.finditer(r"\bGDS[-_]?(\d+)\b", upper):
            add(f"geo::gds{match.group(1)}")
        for match in re.finditer(r"\bGSM[-_]?(\d+)\b", upper):
            add(f"geo::gsm{match.group(1)}")
        for match in re.finditer(r"\bPXD[-_]?(\d+)\b", upper):
            add(f"pride::pxd{match.group(1)}")
        for match in re.finditer(r"\bMTBLS[-_]?(\d+)\b", upper):
            add(f"metabolights::mtbls{match.group(1)}")
        for match in re.finditer(r"\b(E[-_](?:MTAB|MEXP|TABM|GEOD)[-_]\d+)\b", upper):
            accession = match.group(1).replace("_", "-").lower()
            if accession.startswith("e-geod-"):
                add(f"geo::gse{accession.rsplit('-', 1)[-1]}")
            else:
                add(f"expression_atlas::{accession}")
        for match in re.finditer(r"\bPRJ[EDN][A-Z]?[-_]?(\d+)\b", upper):
            add(f"bioproject::{match.group(0).replace('_', '').replace('-', '').lower()}")
    if tokens:
        return tokens
    accession = str(row.get("accession") or row.get("model_id") or "").strip()
    if not accession:
        return []
    source = _slug_token(str(row.get("source_database") or row.get("connector_source") or "resource"))
    return [f"{source}::{_slug_token(accession)}"]


def _slug_token(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")
    return normalized or "unknown"


def _resource_source_link(row: dict[str, Any]) -> dict[str, str]:
    return {
        "resource_id": str(row.get("resource_id") or ""),
        "source_database": str(row.get("source_database") or ""),
        "connector_source": str(row.get("connector_source") or ""),
        "accession": str(row.get("accession") or row.get("model_id") or ""),
        "canonical_tokens": ";".join(_resource_accession_tokens(row)),
        "external_url": str(row.get("external_url") or ""),
    }


def _merge_resource_connector_caches(index: dict[str, Any]) -> None:
    statuses: list[dict[str, str]] = []
    guidance_parts = [str(index.get("guidance") or "").strip()]
    for connector_source, cache_path in RESOURCE_CONNECTOR_CACHE_FILES:
        if not cache_path.exists():
            statuses.append({"source": connector_source, "status": "missing", "path": str(cache_path)})
            guidance_parts.append(f"{connector_source} metadata cache is missing: {cache_path}")
            continue
        try:
            payload = read_json_object(cache_path)
        except (OSError, json.JSONDecodeError) as exc:
            statuses.append({"source": connector_source, "status": "partial", "path": str(cache_path), "error": str(exc)})
            guidance_parts.append(f"{connector_source} metadata cache could not be read: {exc}")
            continue
        if not isinstance(payload, dict):
            statuses.append({"source": connector_source, "status": "partial", "path": str(cache_path)})
            guidance_parts.append(f"{connector_source} metadata cache is not a JSON object.")
            continue
        added = 0
        for key in ("organisms", "model_resources", "omics_resources"):
            rows = payload.get(key)
            if not isinstance(rows, list):
                continue
            target = index.setdefault(key, [])
            if not isinstance(target, list):
                continue
            existing_ids = {_resource_cache_identity(row, key) for row in target if isinstance(row, dict)}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                record = dict(row)
                if key != "organisms":
                    record.setdefault("connector_source", connector_source)
                    record.setdefault("cache_status", "cached")
                identifier = _resource_cache_identity(record, key)
                if identifier and identifier in existing_ids:
                    if key != "organisms":
                        for existing in target:
                            if isinstance(existing, dict) and _resource_cache_identity(existing, key) == identifier:
                                existing.setdefault("connector_source", connector_source)
                                existing.setdefault("cache_status", "cached")
                                for optional_key in ("accession", "taxon_id", "external_url"):
                                    existing.setdefault(optional_key, record.get(optional_key, ""))
                                break
                    continue
                target.append(record)
                if identifier:
                    existing_ids.add(identifier)
                added += 1
        statuses.append({"source": connector_source, "status": "cached", "path": str(cache_path), "records": str(added)})
    if statuses:
        index["connector_status"] = statuses
    manifest = _read_resource_cache_manifest()
    if manifest:
        index["cache_manifest"] = manifest
        index["cache_status"] = _resource_cache_status_summary(manifest, statuses)
    elif statuses:
        index["cache_status"] = _resource_cache_status_summary({}, statuses)
    if any(row.get("status") != "cached" for row in statuses):
        index["status"] = "partial"
    guidance = " ".join(part for part in guidance_parts if part)
    if guidance:
        index["guidance"] = guidance


def _read_resource_cache_manifest() -> dict[str, Any]:
    if not RESOURCE_CACHE_MANIFEST_PATH.exists():
        return {}
    try:
        payload = read_json_object(RESOURCE_CACHE_MANIFEST_PATH)
    except (OSError, json.JSONDecodeError):
        return {
            "status": "partial",
            "path": str(RESOURCE_CACHE_MANIFEST_PATH),
            "guidance": "Resource cache manifest could not be read.",
        }
    if not isinstance(payload, dict):
        return {}
    if RESOURCE_TARGET_CANDIDATE_REPORT_PATH.exists() and RESOURCE_TARGET_CANDIDATE_REPORT_PATH.is_file():
        try:
            target_report = read_json_object(RESOURCE_TARGET_CANDIDATE_REPORT_PATH)
        except (OSError, json.JSONDecodeError):
            target_report = {}
        if isinstance(target_report, dict):
            payload.setdefault("target_candidate_report_json", str(RESOURCE_TARGET_CANDIDATE_REPORT_PATH))
            payload.setdefault("target_candidate_report_status", target_report.get("status", ""))
            payload.setdefault("target_candidate_report_summary", target_report.get("summary", {}))
            candidates = target_report.get("candidates")
            if isinstance(candidates, list):
                payload["target_candidate_top"] = [row for row in candidates if isinstance(row, dict)][:20]
    smoke_report_path = Path(str(payload.get("live_smoke_report_json") or ""))
    if smoke_report_path.exists() and smoke_report_path.is_file():
        try:
            smoke_report = read_json_object(smoke_report_path)
        except (OSError, json.JSONDecodeError):
            smoke_report = {}
        if isinstance(smoke_report, dict):
            payload["live_smoke_report_generated_at"] = smoke_report.get("generated_at", "")
            payload["live_smoke_report_guidance"] = smoke_report.get("guidance", "")
            source_rows = smoke_report.get("source_rows")
            if isinstance(source_rows, list):
                payload["live_smoke_report_rows"] = [row for row in source_rows if isinstance(row, dict)]
    return payload


def _resource_cache_status_summary(manifest: dict[str, Any], statuses: list[dict[str, str]]) -> dict[str, Any]:
    sources = manifest.get("sources") if isinstance(manifest.get("sources"), dict) else {}
    total_records = 0
    if isinstance(sources, dict):
        for source_payload in sources.values():
            if isinstance(source_payload, dict):
                total_records += int(source_payload.get("record_count") or 0)
    if not total_records:
        for status in statuses:
            try:
                total_records += int(status.get("records") or 0)
            except ValueError:
                continue
    return {
        "status": manifest.get("status") or ("partial" if any(row.get("status") != "cached" for row in statuses) else "cached"),
        "generated_at": manifest.get("generated_at") or manifest.get("updated_at") or "",
        "total_records": total_records,
        "source_count": len(sources) if isinstance(sources, dict) and sources else len(statuses),
        "sources": sources,
        "connector_status": statuses,
        "guidance": manifest.get("guidance") or "",
        "query": manifest.get("query", {}),
        "query_count": manifest.get("query_count", 0),
        "failed_queries": manifest.get("failed_queries", 0),
        "capped_queries": manifest.get("capped_queries", 0),
        "target_registry_summary": manifest.get("target_registry_summary", {}),
        "target_candidate_report_summary": manifest.get("target_candidate_report_summary", {}),
        "target_candidate_top": manifest.get("target_candidate_top", []),
        "capped_query_backlog_status": manifest.get("capped_query_backlog_status", ""),
        "capped_query_backlog_summary": manifest.get("capped_query_backlog_summary", {}),
        "capped_query_continuation_plan_status": manifest.get("capped_query_continuation_plan_status", ""),
        "capped_query_continuation_plan_summary": manifest.get("capped_query_continuation_plan_summary", {}),
        "dedup_qa_report_status": manifest.get("dedup_qa_report_status", ""),
        "dedup_qa_report_summary": manifest.get("dedup_qa_report_summary", {}),
        "resource_schema_quality_report_status": manifest.get("resource_schema_quality_report_status", ""),
        "resource_schema_quality_report_summary": manifest.get("resource_schema_quality_report_summary", {}),
        "resource_readiness_audit_status": manifest.get("resource_readiness_audit_status", ""),
        "resource_readiness_audit_summary": manifest.get("resource_readiness_audit_summary", {}),
        "resource_canonical_link_report_status": manifest.get("resource_canonical_link_report_status", ""),
        "resource_canonical_link_report_summary": manifest.get("resource_canonical_link_report_summary", {}),
        "harvest_qa_report_status": manifest.get("harvest_qa_report_status", ""),
        "harvest_qa_report_summary": manifest.get("harvest_qa_report_summary", {}),
    }


def _resource_cache_identity(row: dict[str, Any], key: str) -> str:
    if key == "organisms":
        return str(row.get("organism_id") or "")
    if key == "model_resources":
        return "|".join(
            [
                str(row.get("organism_id") or "").lower(),
                str(row.get("source_database") or "").lower(),
                str(row.get("model_id") or row.get("resource_id") or "").lower(),
            ]
        )
    return "|".join(
        [
            str(row.get("organism_id") or "").lower(),
            str(row.get("source_database") or "").lower(),
            str(row.get("omics_type") or "").lower(),
            str(row.get("accession") or row.get("resource_id") or "").lower(),
        ]
    )


def _normalize_resource_record(row: dict[str, Any], resource_kind: str) -> dict[str, Any]:
    readiness = str(row.get("readiness") or row.get("import_readiness") or "metadata_only")
    connector_source = str(row.get("connector_source") or "manual_seed")
    row["readiness"] = readiness
    row.setdefault("import_readiness", readiness)
    row.setdefault("connector_source", connector_source)
    row.setdefault("cache_status", "cached" if connector_source != "manual_seed" else "manual_seed")
    row.setdefault("resource_kind", resource_kind)
    if "taxon_id" not in row and row.get("ncbi_taxon_id"):
        row["taxon_id"] = row.get("ncbi_taxon_id")
    if resource_kind == "omics":
        row.setdefault("data_level", "metadata_only")
    return row


_RESOURCE_MISSING_TAXONOMY_VALUES = {
    "",
    "na",
    "n/a",
    "none",
    "null",
    "unknown",
    "unclassified",
    "unclaimed",
    "not_available",
    "not available",
}

_RESOURCE_TAXONOMY_ALIASES = {
    "bacterium": "bacteria",
    "bacterial": "bacteria",
    "bacteria": "bacteria",
    "cyanobacterium": "cyanobacteria",
    "cyanobacteria": "cyanobacteria",
    "pathogen": "pathogen_bacteria",
    "pathogen_bacteria": "pathogen_bacteria",
    "human_pathogen": "pathogen_bacteria",
    "human_pathogens": "pathogen_bacteria",
    "anaerobe": "anaerobic_bacteria",
    "anaerobic_bacteria": "anaerobic_bacteria",
    "actinobacterium": "actinobacteria",
    "actinobacteria": "actinobacteria",
    "yeast": "yeast_fungi",
    "fungi": "yeast_fungi",
    "fungus": "yeast_fungi",
    "yeast_fungi": "yeast_fungi",
    "filamentous_fungi": "filamentous_fungi",
    "archaea": "archaea",
    "archaeon": "archaea",
    "microalgae": "microalgae",
    "algae": "microalgae",
    "industrial_microbes": "bacteria",
    "environmental_microbes": "bacteria",
    "other_industrial_environmental_microbes": "bacteria",
    "unclassified_metadata": "unclassified_metadata",
}

_RESOURCE_TARGET_TAXONOMY_CACHE: dict[str, str] | None = None


def _resource_canonical_taxonomy_group(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    normalized = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
    if normalized in _RESOURCE_MISSING_TAXONOMY_VALUES:
        return ""
    return _RESOURCE_TAXONOMY_ALIASES.get(normalized, normalized)


def _resource_target_taxonomy_lookup() -> dict[str, str]:
    global _RESOURCE_TARGET_TAXONOMY_CACHE
    if _RESOURCE_TARGET_TAXONOMY_CACHE is not None:
        return _RESOURCE_TARGET_TAXONOMY_CACHE
    lookup: dict[str, str] = {}
    if RESOURCE_ORGANISM_TARGETS_PATH.exists():
        try:
            with RESOURCE_ORGANISM_TARGETS_PATH.open("r", encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    taxonomy_group = _resource_canonical_taxonomy_group(row.get("taxonomy_group"))
                    if not taxonomy_group:
                        continue
                    keys = [
                        row.get("organism_id"),
                        row.get("scientific_name"),
                        row.get("taxon_id"),
                    ]
                    aliases = str(row.get("aliases") or "").split(";")
                    keys.extend(aliases)
                    for key in keys:
                        normalized_key = str(key or "").strip().lower()
                        if normalized_key:
                            lookup[normalized_key] = taxonomy_group
        except (OSError, csv.Error):
            lookup = {}
    _RESOURCE_TARGET_TAXONOMY_CACHE = lookup
    return lookup


def _resource_taxonomy_from_identity(values: Iterable[Any]) -> str:
    haystack = " ".join(str(value or "") for value in values).lower()
    if not haystack:
        return ""
    if any(token in haystack for token in ("synechocystis", "synechococcus", "cyanobacter", "nostoc", "anabaena")):
        return "cyanobacteria"
    if any(token in haystack for token in ("saccharomyces", "komagataella", "pichia", "candida", "yeast")):
        return "yeast_fungi"
    if any(token in haystack for token in ("aspergillus", "trichoderma", "neurospora", "penicillium")):
        return "filamentous_fungi"
    if any(token in haystack for token in ("methano", "halobacter", "thermococcus", "thermoplasma", "archaea", "archaeon")):
        return "archaea"
    if any(token in haystack for token in ("chlamydomonas", "chlorella", "microalgae", "microalga")):
        return "microalgae"
    if any(token in haystack for token in ("streptomyces", "corynebacterium", "mycobacterium", "mycolicibacterium")):
        return "actinobacteria"
    if any(token in haystack for token in ("clostridium", "clostridioides")):
        return "anaerobic_bacteria"
    if any(token in haystack for token in ("salmonella", "shigella", "klebsiella", "acinetobacter", "helicobacter", "aeruginosa", "cholerae")):
        return "pathogen_bacteria"
    if any(
        token in haystack
        for token in (
            "bacterium",
            "bacteria",
            "escherichia",
            "pseudomonas",
            "shewanella",
            "bacillus",
            "lactococcus",
            "lactobacillus",
            "lactiplantibacillus",
            "cupriavidus",
            "zymomonas",
            "vibrio",
        )
    ):
        return "bacteria"
    return ""


def _resource_organism_taxonomy_group(organism: dict[str, Any], index: dict[str, Any]) -> str:
    direct = _resource_canonical_taxonomy_group(organism.get("taxonomy_group") or organism.get("domain"))
    if direct:
        return direct
    lookup = _resource_target_taxonomy_lookup()
    keys = [
        organism.get("organism_id"),
        organism.get("scientific_name"),
        organism.get("taxon_id"),
        organism.get("ncbi_taxon_id"),
    ]
    aliases = organism.get("aliases") if isinstance(organism.get("aliases"), list) else []
    keys.extend(aliases)
    for key in keys:
        taxonomy_group = lookup.get(str(key or "").strip().lower())
        if taxonomy_group:
            return taxonomy_group
    inferred = _resource_taxonomy_from_identity(keys)
    if inferred:
        return inferred

    organism_id = str(organism.get("organism_id") or "").strip()
    organism_resources = [
        row
        for key in ("model_resources", "omics_resources")
        for row in _resource_records(index, key)
        if str(row.get("organism_id") or "").strip() == organism_id
    ]
    resource_groups = [
        _resource_canonical_taxonomy_group(row.get("taxonomy_group") or row.get("domain"))
        for row in organism_resources
    ]
    resource_groups = [group for group in resource_groups if group]
    if resource_groups:
        return sorted(resource_groups, key=lambda group: (-resource_groups.count(group), group))[0]
    return "unclassified_metadata"


def _resource_taxonomy_group(row: dict[str, Any], index: dict[str, Any]) -> str:
    direct = _resource_canonical_taxonomy_group(row.get("taxonomy_group") or row.get("domain"))
    if direct:
        return direct
    organism = _organism_by_id(index, str(row.get("organism_id") or ""))
    if organism:
        return _resource_organism_taxonomy_group(organism, index)
    inferred = _resource_taxonomy_from_identity(
        [
            row.get("organism_id"),
            row.get("organism"),
            row.get("scientific_name"),
            row.get("taxon_id"),
            row.get("ncbi_taxon_id"),
        ]
    )
    return inferred or "unclassified_metadata"


def _resource_taxonomy_label(taxonomy_group: str) -> str:
    labels = {
        "bacteria": "Bacteria",
        "cyanobacteria": "Cyanobacteria",
        "pathogen_bacteria": "Pathogen bacteria",
        "anaerobic_bacteria": "Anaerobic bacteria",
        "actinobacteria": "Actinobacteria",
        "yeast_fungi": "Yeast / fungi",
        "filamentous_fungi": "Filamentous fungi",
        "archaea": "Archaea",
        "microalgae": "Microalgae",
        "unclassified_metadata": "Unclassified metadata",
    }
    return labels.get(taxonomy_group, taxonomy_group.replace("_", " ").title())


def _resource_supported_methods(row: dict[str, Any]) -> list[str]:
    return suggested_methods_for_resource(row)


def _resource_readiness_class(readiness: str) -> str:
    return resource_readiness_class(readiness)


def _resource_main_blocker(readiness_counts: dict[str, int]) -> str:
    return resource_main_blocker(readiness_counts)


def _organism_by_id(index: dict[str, Any], organism_id: str) -> dict[str, Any]:
    for row in index.get("organisms") or []:
        if isinstance(row, dict) and str(row.get("organism_id") or "") == organism_id:
            return dict(row)
    return {}


def _matching_organism_ids(organisms: list[dict[str, Any]], query: str) -> set[str]:
    if not query:
        return {str(row.get("organism_id") or "") for row in organisms}
    normalized = query.lower()
    matches: set[str] = set()
    for organism in organisms:
        aliases = organism.get("aliases") if isinstance(organism.get("aliases"), list) else []
        haystack = " ".join(
            [
                str(organism.get("organism_id") or ""),
                str(organism.get("scientific_name") or ""),
                str(organism.get("strain") or ""),
                str(organism.get("ncbi_taxon_id") or ""),
                *[str(alias) for alias in aliases],
            ]
        ).lower()
        if normalized in haystack:
            matches.add(str(organism.get("organism_id") or ""))
    return matches


def _resource_search_text(row: dict[str, Any], index: dict[str, Any]) -> str:
    organism = _organism_by_id(index, str(row.get("organism_id") or ""))
    aliases = organism.get("aliases") if isinstance(organism.get("aliases"), list) else []
    keywords = row.get("condition_keywords") if isinstance(row.get("condition_keywords"), list) else []
    values = [
        str(row.get("resource_id") or ""),
        str(row.get("model_id") or ""),
        str(row.get("model_name") or ""),
        str(row.get("title") or ""),
        str(row.get("organism_name") or ""),
        str(row.get("strain") or ""),
        str(row.get("source_database") or ""),
        str(row.get("connector_source") or ""),
        str(row.get("accession") or ""),
        str(row.get("omics_type") or ""),
        str(row.get("data_level") or ""),
        str(row.get("readiness") or ""),
        str(row.get("readiness_reason") or ""),
        str(organism.get("scientific_name") or ""),
        str(organism.get("strain") or ""),
        str(organism.get("ncbi_taxon_id") or ""),
        *[str(alias) for alias in aliases],
        *[str(keyword) for keyword in keywords],
    ]
    return " ".join(values).lower()




def _resource_suggestion_reason(rows: list[dict[str, Any]]) -> str:
    ready_types = sorted(
        {
            str(row.get("omics_type") or "")
            for row in rows
            if str(row.get("readiness") or "") == "ready_for_import" and str(row.get("omics_type") or "")
        }
    )
    if ready_types:
        return f"Ready local evidence detected for: {', '.join(ready_types)}."
    if rows:
        return "Only metadata or manually curated resources are available in the local index."
    return "No omics evidence is indexed for this model yet."


def _default_case_display_manifest() -> dict[str, Any]:
    return {
        "schema_version": "case_display_manifest_v1",
        "generated_by": "case_study_readiness_checker",
        "case_studies": [
            {
                "case_id": "shewanella_integrated_overview",
                "run_id": "shewanella_gecko_case",
                "title": "Shewanella integrated GECKO and trigger overview",
                "title_zh": "Shewanella GECKO 与转录触发器综合展示",
                "story_title": "Integrated Shewanella ecModel and paper-reproduction showcase",
                "story_title_zh": "Shewanella ecModel 与论文复现综合案例",
                "story_summary": (
                    "A single demonstration entry that links the GECKO oxygen-condition model comparison "
                    "with the transcriptional-trigger paper reproduction workbench. Model Compare uses the "
                    "GECKO run; Analysis and Summary use the trigger-paper run."
                ),
                "story_summary_zh": (
                    "一个统一展示入口：Model Compare 使用 GECKO 氧条件对比 run，"
                    "Analysis 与 Summary 使用转录触发器论文复现 run。"
                ),
                "organism_id": "shewanella_oneidensis_mr1",
                "organism_name": "Shewanella oneidensis MR-1",
                "default_query": "Shewanella GECKO oxygen transcriptional triggers GDM D2T2 glycogen",
                "default_reference_variant_id": "baseline_gem__all",
                "default_target_variant_id": "enzyme_gecko__higho2",
                "default_annotation_type": "kegg_pathway",
                "default_annotation_group_id": "rn00020",
                "default_annotation_groups": ["rn00020", "rn00010", "rn00030"],
                "default_compare_view_mode": "side_by_side",
                "composite_case": True,
                "linked_runs": {
                    "gecko_oxygen": "shewanella_gecko_case",
                    "transcriptional_triggers": "shewanella_transcriptional_triggers_case",
                },
                "stage_run_map": {
                    "input": "shewanella_gecko_case",
                    "model_generator": "shewanella_gecko_case",
                    "model_compare": "shewanella_gecko_case",
                    "analysis": "shewanella_transcriptional_triggers_case",
                    "summary": "shewanella_transcriptional_triggers_case",
                },
                "default_compare_context": {
                    "run_id": "shewanella_gecko_case",
                    "reference_variant_id": "baseline_gem__all",
                    "target_variant_id": "enzyme_gecko__higho2",
                    "annotation_type": "kegg_pathway",
                    "annotation_group_id": "rn00020",
                },
                "default_analysis_context": {
                    "run_id": "shewanella_transcriptional_triggers_case",
                    "workbench": "paper_reproduction",
                    "report_preset": "shewanella_trigger_reproduction_report",
                },
                "evidence_status_labels": {
                    "GECKO_compare": "ready",
                    "kcat": "ready",
                    "proteomics": "ready",
                    "flux_behavior": "ready",
                    "trigger_analysis": "computed_lite",
                    "D2T2": "paper_reported_only",
                    "dFBA_glycogen": "paper_reported_model_prediction_available",
                    "enzyme_capacity": "reaction-level unavailable",
                },
                "recommended_model_generation_methods": ["baseline_gem", "eflux", "consensus_evidence", "enzyme_gecko"],
                "recommended_analysis_methods": [
                    "growth_state_map",
                    "trigger_timeline",
                    "gdm_lite",
                    "d2t2_lite",
                    "dfba_glycogen_guarded",
                    "readiness_gate",
                ],
                "key_evidence_types": [
                    "absolute_proteomics",
                    "kcat",
                    "gecko_package",
                    "processed_expression_timecourse",
                    "metabolite_glycogen_timecourse",
                    "paper_reproduction_report",
                ],
                "expected_ecmodel": True,
                "display_caveats": [
                    "This is a composite display case; it links two existing run packages instead of merging their files.",
                    "GECKO Compare evidence and trigger-paper Analysis evidence must remain stage-specific.",
                    "Fresh D2T2 recomputation, fresh dFBA solver runs, and fabricated enzyme capacity are out of scope.",
                ],
                "display_next_actions": [
                    "Use Model Compare for GECKO oxygen-condition evidence and kcat/proteomics overlays.",
                    "Use Analysis and Summary for Growth State Map, Trigger Timeline, GDM-lite, D2T2 reported triggers, and dFBA/glycogen paper-reported curves.",
                ],
            },
            {
                "case_id": "shewanella_gecko_oxygen",
                "run_id": "shewanella_gecko_case",
                "hidden_from_case_dropdown": True,
                "title": "Shewanella GECKO oxygen comparison",
                "title_zh": "Shewanella GECKO \u6c27\u6761\u4ef6\u5bf9\u6bd4",
                "story_title": "Complete oxygen-condition ecModel demonstration",
                "story_title_zh": "\u5b8c\u6574\u6c27\u6761\u4ef6 ecModel \u5c55\u793a\u6848\u4f8b",
                "story_summary": (
                    "Compare the iLJ1162 reference GEM with the highO2 GECKO-ready ecModel. "
                    "Use KEGG-derived submaps to explain kcat evidence, flux signals, and GECKO behavior."
                ),
                "story_summary_zh": (
                    "\u5bf9\u6bd4 iLJ1162 \u53c2\u8003 GEM \u4e0e highO2 GECKO-ready ecModel\uff0c"
                    "\u7528 KEGG \u6d3e\u751f\u5b50\u56fe\u89e3\u91ca kcat \u8bc1\u636e\u3001\u901a\u91cf\u4fe1\u53f7\u548c GECKO \u884c\u4e3a\u3002"
                ),
                "organism_id": "shewanella_oneidensis_mr1",
                "organism_name": "Shewanella oneidensis MR-1",
                "default_query": "Shewanella iLJ1162 highO2 lowO2 GECKO",
                "default_reference_variant_id": "baseline_gem__all",
                "default_target_variant_id": "enzyme_gecko__higho2",
                "default_annotation_type": "kegg_pathway",
                "default_annotation_group_id": "rn00020",
                "default_annotation_groups": ["rn00020", "rn00010", "rn00030"],
                "default_compare_view_mode": "difference",
                "evidence_status_labels": {
                    "kcat": "ready",
                    "proteomics": "ready",
                    "flux_behavior": "ready",
                    "enzyme_capacity": "reaction-level unavailable",
                    "ecmodel": "partial",
                },
                "recommended_model_generation_methods": ["baseline_gem", "eflux", "consensus_evidence", "enzyme_gecko"],
                "recommended_analysis_methods": [
                    "fba_pfba",
                    "eflux_delta_fba",
                    "evidence_comparison",
                    "production_ecfactory",
                    "readiness_gate",
                ],
                "key_evidence_types": [
                    "absolute_proteomics",
                    "relative_proteomics",
                    "kcat",
                    "condition_bounds",
                    "annotation",
                    "gecko_package",
                ],
                "expected_ecmodel": True,
                "display_caveats": [
                    "GECKO enzyme pseudo reactions are interpreted as constraint evidence, not conventional GEM structural diff.",
                    "Reaction-level capacity is displayed only when an existing capacity table is available.",
                ],
                "display_next_actions": [
                    "Open Model Compare and inspect TCA, glycolysis, and PPP KEGG-derived submaps.",
                    "Keep enzyme capacity marked unavailable unless reaction-level capacity output is present.",
                ],
            },
            {
                "case_id": "shewanella_transcriptional_triggers_lac_lb",
                "run_id": "shewanella_transcriptional_triggers_case",
                "hidden_from_case_dropdown": True,
                "title": "Shewanella transcriptional triggers in LAC/LB growth",
                "title_zh": "Shewanella LAC/LB \u751f\u957f\u52a8\u6001\u8f6c\u5f55\u89e6\u53d1\u56e0\u5b50\u8bba\u6587\u590d\u73b0",
                "story_title": "Guarded evidence-chain reproduction of transcriptional triggers",
                "story_title_zh": "\u8f6c\u5f55\u89e6\u53d1\u56e0\u5b50\u8bc1\u636e\u94fe\u590d\u73b0\u6848\u4f8b",
                "story_summary": (
                    "Uses Supplement and GEO processed data to show Growth State Map, Trigger Timeline, GDM-lite, "
                    "paper-reported D2T2 triggers, and paper-reported dFBA/glycogen scenarios. Model Compare only "
                    "overlays paper evidence that maps through GEM GPRs; nitrogen/glycogen regulators that do not map "
                    "to reaction-level GPRs remain pathway-level caveats."
                ),
                "story_summary_zh": (
                    "\u57fa\u4e8e\u8bba\u6587 Supplement \u548c GEO processed matrix \u5c55\u793a Growth State Map\u3001"
                    "Trigger Timeline\u3001GDM-lite\u3001\u8bba\u6587\u62a5\u9053\u7684 D2T2 trigger \u4e0e dFBA/glycogen scenario\u3002"
                    "Model Compare \u53ea\u53e0\u52a0\u53ef\u901a\u8fc7 GPR \u771f\u5b9e\u6620\u5c04\u5230\u53cd\u5e94\u7684 paper evidence\uff1b"
                    "\u6c2e/\u7cd6\u539f\u4e3b\u7ebf\u4e2d\u672a\u6620\u5c04\u7684\u8c03\u63a7\u57fa\u56e0\u4fdd\u7559\u4e3a pathway-level caveat\u3002"
                ),
                "organism_id": "shewanella_oneidensis_mr1",
                "organism_name": "Shewanella oneidensis MR-1",
                "default_query": "Shewanella transcriptional triggers LAC LB nitrogen glycogen GDM D2T2",
                "default_reference_variant_id": "baseline_gem__all",
                "default_target_variant_id": "paper_evidence_context__lac_transition",
                "default_annotation_type": "custom_annotation",
                "default_annotation_group_id": "nitrogen_glycogen_coupling",
                "default_annotation_groups": [
                    "nitrogen_glycogen_coupling",
                    "lactate_utilization",
                    "oxygen_response",
                    "gluconeogenesis",
                    "growth_state_transition",
                ],
                "default_compare_view_mode": "side_by_side",
                "evidence_status_labels": {
                    "expression_timecourse": "parsed / chart-ready",
                    "metabolite_glycogen": "parsed / chart-ready",
                    "GDM": "computed_lite",
                    "D2T2": "paper_reported_only",
                    "dFBA_glycogen": "paper_reported_model_prediction_available",
                    "paper_evidence_overlay": "partial_mapping_ready",
                    "bounds": "not_generated",
                    "enzyme_capacity": "not_applicable",
                },
                "recommended_model_generation_methods": ["baseline_gem", "eflux", "consensus_evidence"],
                "recommended_analysis_methods": [
                    "growth_state_map",
                    "trigger_timeline",
                    "pathway_evidence_map",
                    "gdm_lite",
                    "d2t2_lite",
                    "dfba_glycogen_guarded",
                    "readiness_gate",
                ],
                "key_evidence_types": [
                    "processed_expression_timecourse",
                    "metabolite_glycogen_timecourse",
                    "gdm_lite_results",
                    "d2t2_trigger_genes",
                    "paper_evidence_reaction_overlay",
                    "paper_reported_trigger_annotation",
                    "pathway_annotation",
                ],
                "expected_ecmodel": False,
                "display_caveats": [
                    "GDM is a lightweight reproduction from processed expression and growth data, not the full original implementation.",
                    "D2T2 triggers and dFBA/glycogen curves are paper-reported tables; no full influence-network or solver recomputation is claimed.",
                    "Condition bounds, structural model edits, and enzyme capacity are not generated for this transcriptomics/metabolite paper.",
                    "Nitrogen/glycogen trigger genes are retained as paper evidence, but current iLJ1162 GPR mapping does not provide reaction-level overlay for that group.",
                ],
                "display_next_actions": [
                    "Use Analysis to inspect Growth State Map, Trigger Timeline, GDM-lite, D2T2, and dFBA/glycogen panels.",
                    "Use the default nitrogen/glycogen group for the paper story; switch to gluconeogenesis to inspect evidence reactions that map through iLJ1162 GPRs.",
                    "Keep bounds, fresh dFBA, and enzyme capacity marked unavailable unless curated parameters or external outputs are added.",
                ],
            },
            {
                "case_id": "putida_acetate_isoprenol",
                "run_id": "putida_acetate_isoprenol_case",
                "title": "P. putida acetate tolerance and isoprenol",
                "title_zh": "P. putida \u4e59\u9178\u8010\u53d7\u4e0e isoprenol \u8bba\u6587\u6848\u4f8b",
                "story_title": "Proteomics-driven acetate tolerance evidence case",
                "story_title_zh": "\u86cb\u767d\u7ec4\u9a71\u52a8\u7684\u4e59\u9178\u8010\u53d7\u8bc1\u636e\u6848\u4f8b",
                "story_summary": (
                    "Use the P. putida acetate/isoprenol proteomics study to compare the reference model "
                    "with a consensus context variant and explain acetate assimilation and MEP/isoprenol marker evidence."
                ),
                "story_summary_zh": (
                    "\u57fa\u4e8e P. putida \u4e59\u9178/isoprenol \u86cb\u767d\u7ec4\u8bba\u6587\uff0c"
                    "\u5bf9\u6bd4\u53c2\u8003\u6a21\u578b\u4e0e consensus context \u53d8\u4f53\uff0c\u89e3\u91ca\u4e59\u9178\u540c\u5316\u3001MEP/isoprenol marker \u8bc1\u636e\u3002"
                ),
                "organism_id": "pseudomonas_putida_kt2440",
                "organism_name": "Pseudomonas putida KT2440",
                "default_query": "Pseudomonas putida iJN1463 acetate isoprenol proteomics",
                "default_reference_variant_id": "baseline_gem__all",
                "default_target_variant_id": "consensus_context__all",
                "default_annotation_type": "custom_annotation",
                "default_annotation_group_id": "acetate_assimilation",
                "default_annotation_groups": ["acetate_assimilation", "glyoxylate_tca", "isoprenol_mep"],
                "default_compare_view_mode": "difference",
                "evidence_status_labels": {
                    "proteomics": "ready",
                    "marker_annotation": "ready",
                    "kcat": "package-ready only",
                    "enzyme_capacity": "external ecModel pending",
                    "ecmodel": "external ecModel pending",
                },
                "recommended_model_generation_methods": ["baseline_gem", "consensus_evidence"],
                "recommended_analysis_methods": [
                    "fba_pfba",
                    "evidence_comparison",
                    "ml_pca_lasso",
                    "condition_interpretation",
                    "readiness_gate",
                ],
                "key_evidence_types": ["absolute_proteomics", "relative_proteomics", "kcat", "annotation", "condition_summary"],
                "expected_ecmodel": False,
                "display_caveats": [
                    "Use as proteomics plus kcat/package-ready evidence unless an external ecModel has been generated.",
                    "Capacity or enzyme usage should be shown as package-ready/not available when reaction-level output is absent.",
                ],
                "display_next_actions": [
                    "Show proteomics and marker annotation evidence in Model Compare.",
                    "Keep capacity and ecModel outputs marked external pending until a real ecModel run exists.",
                ],
            },
            {
                "case_id": "synechocystis_spkb_carbon",
                "run_id": "synechocystis_spkb_case",
                "title": "Synechocystis SpkB carbon limitation",
                "title_zh": "Synechocystis SpkB \u78b3\u9650\u5236\u8bba\u6587\u6848\u4f8b",
                "story_title": "Evidence-only carbon limitation integration case",
                "story_title_zh": "\u8bc1\u636e\u6574\u5408\u578b\u78b3\u9650\u5236\u6848\u4f8b",
                "story_summary": (
                    "Use proteomics, phosphoproteomics, metabolomics, and phenotype evidence to explain the SpkB carbon-limitation response. "
                    "Treat the case as evidence integration unless a protein pool and external ecModel run are provided."
                ),
                "story_summary_zh": (
                    "\u6574\u5408\u86cb\u767d\u7ec4\u3001\u78f7\u9178\u5316\u86cb\u767d\u7ec4\u3001\u4ee3\u8c22\u7ec4\u4e0e\u8868\u578b\u8bc1\u636e\u89e3\u91ca SpkB \u78b3\u9650\u5236\u54cd\u5e94\uff1b"
                    "\u5728\u6ca1\u6709 protein pool \u548c\u5916\u90e8 ecModel \u8fd0\u884c\u524d\uff0c\u6309\u8bc1\u636e\u6574\u5408\u6848\u4f8b\u5c55\u793a\u3002"
                ),
                "organism_id": "synechocystis_pcc6803",
                "organism_name": "Synechocystis sp. PCC 6803",
                "default_query": "Synechocystis iJN678 SpkB carbon limitation proteomics phosphoproteomics",
                "default_reference_variant_id": "baseline_gem__all",
                "default_target_variant_id": "consensus_context__all",
                "default_annotation_type": "kegg_pathway",
                "default_annotation_group_id": "redox_quinone_flavin_eet",
                "default_annotation_groups": ["redox_quinone_flavin_eet", "TCA cycle", "Glycolysis / Gluconeogenesis"],
                "default_compare_view_mode": "difference",
                "evidence_status_labels": {
                    "proteomics": "ready",
                    "phosphoproteomics": "ready",
                    "metabolomics": "ready",
                    "kcat": "package-ready only",
                    "enzyme_capacity": "not generated",
                    "ecmodel": "evidence-only case",
                },
                "recommended_model_generation_methods": ["baseline_gem", "consensus_evidence"],
                "recommended_analysis_methods": [
                    "fba_pfba",
                    "evidence_comparison",
                    "condition_interpretation",
                    "readiness_gate",
                ],
                "key_evidence_types": ["relative_proteomics", "phosphoproteomics", "metabolomics", "kcat", "annotation"],
                "expected_ecmodel": False,
                "display_caveats": [
                    "This case is evidence-integration and kcat-ready unless a protein pool and external ecModel run are provided.",
                    "Do not report enzyme capacity as zero when reaction-level capacity is not generated.",
                ],
                "display_next_actions": [
                    "Use Model Compare for pathway/proteomics/phosphoproteomics evidence.",
                    "Do not show enzyme capacity as available without protein pool and external ecModel output.",
                ],
            },
        ],
    }


_CASE_MANIFEST_AUTHORITATIVE_FIELDS = {
    "title_zh",
    "story_title",
    "story_title_zh",
    "story_summary",
    "story_summary_zh",
    "default_annotation_group_id",
    "default_compare_view_mode",
    "evidence_status_labels",
    "display_next_actions",
    "hidden_from_case_dropdown",
    "composite_case",
    "linked_runs",
    "stage_run_map",
    "default_compare_context",
    "default_analysis_context",
}


def _case_manifest_defaults_by_id() -> dict[str, dict[str, Any]]:
    return {
        str(case.get("case_id") or ""): case
        for case in _default_case_display_manifest().get("case_studies", [])
        if isinstance(case, dict) and case.get("case_id")
    }


def _normalize_case_manifest_entry(item: dict[str, Any]) -> dict[str, Any]:
    case_id = str(item.get("case_id") or "")
    defaults = _case_manifest_defaults_by_id().get(case_id, {})
    merged = {**defaults, **item} if defaults else dict(item)
    for field in _CASE_MANIFEST_AUTHORITATIVE_FIELDS:
        if field in defaults:
            merged[field] = defaults[field]
    if not merged.get("default_annotation_group_id"):
        groups = merged.get("default_annotation_groups") if isinstance(merged.get("default_annotation_groups"), list) else []
        if groups:
            merged["default_annotation_group_id"] = str(groups[0])
    if not merged.get("default_compare_view_mode"):
        merged["default_compare_view_mode"] = "difference"
    return merged


def _normalize_case_display_manifest(payload: dict[str, Any]) -> dict[str, Any]:
    defaults = _default_case_display_manifest()
    rows = payload.get("case_studies") if isinstance(payload.get("case_studies"), list) else []
    if not rows:
        rows = defaults.get("case_studies", [])
    seen: set[str] = set()
    normalized_rows: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        normalized = _normalize_case_manifest_entry(item)
        case_id = str(normalized.get("case_id") or "")
        if not case_id:
            continue
        seen.add(case_id)
        normalized_rows.append(normalized)
    for default_item in defaults.get("case_studies", []):
        if not isinstance(default_item, dict):
            continue
        case_id = str(default_item.get("case_id") or "")
        if case_id and case_id not in seen:
            normalized_rows.append(_normalize_case_manifest_entry(default_item))
    return {
        "schema_version": str(payload.get("schema_version") or defaults["schema_version"]),
        "generated_by": str(payload.get("generated_by") or defaults["generated_by"]),
        "case_studies": normalized_rows,
    }


def _case_display_manifest() -> dict[str, Any]:
    if CASE_DISPLAY_MANIFEST_PATH.exists():
        try:
            payload = read_json_object(CASE_DISPLAY_MANIFEST_PATH)
            if isinstance(payload.get("case_studies"), list):
                normalized = _normalize_case_display_manifest(payload)
                if normalized != payload:
                    write_json(CASE_DISPLAY_MANIFEST_PATH, normalized)
                return normalized
        except (OSError, json.JSONDecodeError):
            pass
    payload = _normalize_case_display_manifest(_default_case_display_manifest())
    write_json(CASE_DISPLAY_MANIFEST_PATH, payload)
    return payload


def list_case_studies() -> dict[str, Any]:
    manifest = _case_display_manifest()
    studies: list[dict[str, Any]] = []
    case_rows = manifest.get("case_studies") if isinstance(manifest.get("case_studies"), list) else []
    for item in case_rows:
        if not isinstance(item, dict):
            continue
        case = dict(item)
        if bool(case.get("hidden_from_case_dropdown")):
            continue
        try:
            readiness = case_study_readiness(str(case.get("case_id") or ""), write_artifact=False)
        except ApiError:
            readiness = {"overall_status": "missing_artifact", "guidance": "Case readiness could not be checked."}
        case["readiness_status"] = readiness.get("overall_status", "partial")
        case["readiness_guidance"] = readiness.get("guidance", "")
        studies.append(case)
    studies.sort(key=lambda row: 0 if str(row.get("case_id") or "") == "shewanella_integrated_overview" else 1)
    return {
        "status": "ready",
        "manifest_path": str(CASE_DISPLAY_MANIFEST_PATH),
        "case_studies": studies,
    }


def _case_study_entry(case_id: str) -> dict[str, Any]:
    manifest = _case_display_manifest()
    case_rows = manifest.get("case_studies") if isinstance(manifest.get("case_studies"), list) else []
    for item in case_rows:
        if isinstance(item, dict) and str(item.get("case_id") or "") == case_id:
            return _normalize_case_manifest_entry(item)
    raise ApiError(404, f"Case study not found: {case_id}")


def _case_table_count(path: Path) -> int:
    return len(read_csv_rows(path))


def _case_file_status(path: Path, *, empty_status: str = "missing_artifact") -> tuple[str, int]:
    if not path.exists():
        return "missing_artifact", 0
    if path.is_file() and path.stat().st_size == 0:
        return empty_status, 0
    if path.suffix.lower() in {".csv", ".tsv", ".txt"}:
        rows = read_csv_rows(path)
        if rows:
            return "ready", len(rows)
        return empty_status, 0
    return "ready", 1


def _case_find_variant(registry: list[dict[str, Any]], requested: str, preferred_tokens: Iterable[str] = ()) -> str:
    ids = [str(row.get("variant_id") or row.get("model_variant_id") or "") for row in registry if isinstance(row, dict)]
    if requested in ids:
        return requested
    lowered = [(variant_id, variant_id.lower()) for variant_id in ids if variant_id]
    for token in preferred_tokens:
        token_lower = token.lower()
        for variant_id, value in lowered:
            if token_lower and token_lower in value:
                return variant_id
    return ids[0] if ids else ""


def _case_default_pair(case: dict[str, Any], registry: list[dict[str, Any]]) -> tuple[str, str, str]:
    reference = _case_find_variant(
        registry,
        str(case.get("default_reference_variant_id") or ""),
        ("baseline", "reference", "original", "all"),
    )
    target = _case_find_variant(
        registry,
        str(case.get("default_target_variant_id") or ""),
        ("enzyme_gecko", "gecko", "consensus", "eflux", "higho2", "target"),
    )
    if target == reference:
        for row in registry:
            variant_id = str(row.get("variant_id") or row.get("model_variant_id") or "")
            if variant_id and variant_id != reference:
                target = variant_id
                break
    status = "ready" if reference and target and reference != target else "missing_artifact"
    return reference, target, status


def _case_annotation_scope(case: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    run_id = str(case.get("run_id") or "")
    annotation_type = str(case.get("default_annotation_type") or "")
    requested_groups = [
        str(item)
        for item in [case.get("default_annotation_group_id"), *(case.get("default_annotation_groups") or [])]
        if str(item)
    ]
    try:
        payload = run_annotation_groups(run_id)
    except ApiError as exc:
        return annotation_type, requested_groups[0] if requested_groups else "", {"status": "missing_artifact", "guidance": exc.detail}
    types = payload.get("annotation_types") if isinstance(payload.get("annotation_types"), list) else []
    selected_type = annotation_type
    selected_group = requested_groups[0] if requested_groups else ""
    group_count = 0
    reaction_count = 0
    for type_row in types:
        if not isinstance(type_row, dict):
            continue
        type_id = str(type_row.get("annotation_type") or type_row.get("type") or "")
        groups = type_row.get("groups") if isinstance(type_row.get("groups"), list) else []
        if selected_type and type_id != selected_type:
            continue
        selected_type = type_id or selected_type
        group_count = len(groups)
        for group in groups:
            group_id = str(group.get("group_id") or group.get("id") or group.get("label") or "")
            if not selected_group or group_id == selected_group or str(group.get("label") or "") == selected_group:
                selected_group = group_id or selected_group
                reaction_ids = group.get("reaction_ids") if isinstance(group.get("reaction_ids"), list) else []
                reaction_count = len(reaction_ids) or _safe_int(group.get("reaction_count"))
                break
        if selected_group:
            break
    if not selected_type and types:
        first_type = types[0] if isinstance(types[0], dict) else {}
        selected_type = str(first_type.get("annotation_type") or first_type.get("type") or "")
        groups = first_type.get("groups") if isinstance(first_type.get("groups"), list) else []
        group_count = len(groups)
        if groups and isinstance(groups[0], dict):
            selected_group = str(groups[0].get("group_id") or groups[0].get("id") or groups[0].get("label") or "")
            reaction_ids = groups[0].get("reaction_ids") if isinstance(groups[0].get("reaction_ids"), list) else []
            reaction_count = len(reaction_ids) or _safe_int(groups[0].get("reaction_count"))
    status = "ready" if selected_type and selected_group else "missing_artifact"
    return selected_type, selected_group, {
        "status": status,
        "annotation_type": selected_type,
        "annotation_group_id": selected_group,
        "annotation_type_count": len(types),
        "group_count": group_count,
        "reaction_count": reaction_count,
        "guidance": "Annotation group scope is available." if status == "ready" else "No annotation group scope is available for compare submaps.",
    }


def _case_compare_graph_count(package: Path) -> int:
    roots = [
        package / "visualization_results" / "compare_submaps",
        package / "visualization_results" / "sammi",
    ]
    count = 0
    for root in roots:
        if root.exists():
            count += len(list(root.glob("**/network_graph.json")))
    return count


def _case_capacity_status(package: Path, *, expected_ecmodel: bool) -> dict[str, Any]:
    paths = [
        package / "enzyme_results" / "reaction_enzyme_capacity.csv",
        package / "gecko_package" / "reaction_enzyme_capacity.csv",
        package / "enzyme_results" / "enzyme_flux_capacity_check.csv",
    ]
    for path in paths:
        status, count = _case_file_status(path, empty_status="reaction_level_unavailable")
        if status == "ready":
            return {
                "status": "ready",
                "count": count,
                "path": str(path),
                "guidance": "Reaction-level enzyme capacity evidence is available.",
            }
        if path.exists():
            return {
                "status": "reaction_level_unavailable" if expected_ecmodel else "package_ready_only",
                "count": 0,
                "path": str(path),
                "guidance": "Capacity file exists but has no reaction-level rows; show unavailable/package-ready guidance instead of 0.",
            }
    return {
        "status": "not_generated" if expected_ecmodel else "package_ready_only",
        "count": 0,
        "path": "",
        "guidance": (
            "No reaction-level enzyme capacity output was found."
            if expected_ecmodel
            else "This case is not marked as a complete ecModel; capacity should be shown as not available."
        ),
    }


def _case_capacity_status_from_context(optional_evidence: dict[str, Any], *, expected_ecmodel: bool) -> dict[str, Any]:
    for key in ("reaction_enzyme_capacity", "enzyme_flux_capacity_check"):
        item = optional_evidence.get(key) if isinstance(optional_evidence.get(key), dict) else {}
        status = str(item.get("status") or "")
        path = str(item.get("path") or "")
        if status == "ready":
            return {
                "status": "ready",
                "count": _safe_int(item.get("count")),
                "path": path,
                "guidance": "Reaction-level enzyme capacity evidence is available.",
            }
        if path:
            return {
                "status": "reaction_level_unavailable" if expected_ecmodel else "package_ready_only",
                "count": 0,
                "path": path,
                "guidance": "Capacity artifact exists but has no reaction-level rows; show unavailable/package-ready guidance instead of 0.",
            }
    return {
        "status": "not_generated" if expected_ecmodel else "package_ready_only",
        "count": 0,
        "path": "",
        "guidance": (
            "No reaction-level enzyme capacity output was found."
            if expected_ecmodel
            else "This case is not marked as a complete ecModel; capacity should be shown as not available."
        ),
    }


def _case_analysis_status(package: Path) -> dict[str, Any]:
    candidates = [
        package / "analysis_results",
        package / "report_results",
        package / "reports",
        package / "summary_results",
    ]
    file_count = 0
    for root in candidates:
        if root.exists():
            file_count += len([path for path in root.glob("**/*") if path.is_file()])
    scaffold_files = [
        package / "workflow_results" / "analysis_parameters_summary.csv",
        package / "case_study" / "paper_reproduction_manifest.json",
        package / "case_study" / "data_needed_manifest.json",
    ]
    scaffold_count = sum(1 for path in scaffold_files if path.exists() and path.is_file())
    paper_manifest = read_json_object(package / "case_study" / "paper_reproduction_manifest.json")
    if str(paper_manifest.get("status") or "") == "partial_computed_lite":
        chart_files = [
            package / "case_study" / "growth_state_map_data.json",
            package / "case_study" / "trigger_timeline_data.json",
            package / "case_study" / "gdm_lite_results.json",
            package / "case_study" / "dfba_glycogen_scenario.json",
        ]
        chart_count = sum(1 for path in chart_files if path.exists() and path.is_file())
        if chart_count >= 3:
            return {
                "status": "ready",
                "count": scaffold_count + chart_count,
                "guidance": "Paper reproduction workbench artifacts are chart-ready; full D2T2/dFBA remain guarded.",
            }
    if file_count:
        return {
            "status": "ready",
            "count": file_count,
            "guidance": "Analysis or report outputs are available.",
        }
    if scaffold_count:
        return {
            "status": "partial",
            "count": scaffold_count,
            "guidance": "Analysis scaffold artifacts are available; algorithmic reproduction or final report outputs are still pending.",
        }
    return {
        "status": "missing_artifact",
        "count": 0,
        "guidance": "No analysis/report output files were found.",
    }


def _case_linked_run_id(case: dict[str, Any], key: str, fallback: str = "") -> str:
    linked = case.get("linked_runs") if isinstance(case.get("linked_runs"), dict) else {}
    stage_map = case.get("stage_run_map") if isinstance(case.get("stage_run_map"), dict) else {}
    return str(stage_map.get(key) or linked.get(key) or fallback or case.get("run_id") or "")


def _integrated_case_report_index(case: dict[str, Any], main_package: Path) -> dict[str, Any]:
    linked = case.get("linked_runs") if isinstance(case.get("linked_runs"), dict) else {}
    trigger_run_id = str(linked.get("transcriptional_triggers") or "shewanella_transcriptional_triggers_case")
    gecko_run_id = str(linked.get("gecko_oxygen") or case.get("run_id") or "shewanella_gecko_case")
    try:
        trigger_package = resolve_run_package(trigger_run_id)
    except ApiError:
        trigger_package = USER_RUNS_DIR / trigger_run_id
    try:
        gecko_package = resolve_run_package(gecko_run_id)
    except ApiError:
        gecko_package = main_package
    report_dir = main_package / "report_results"
    report_dir.mkdir(parents=True, exist_ok=True)
    index_path = report_dir / "shewanella_integrated_showcase_index.html"
    manifest_path = report_dir / "shewanella_integrated_showcase_manifest.json"
    links = [
        {
            "label": "GECKO full audit report",
            "path": str(gecko_package / "report_results" / "full_audit_report.html"),
            "exists": (gecko_package / "report_results" / "full_audit_report.html").exists(),
        },
        {
            "label": "GECKO production design report",
            "path": str(gecko_package / "report_results" / "production_design_report.html"),
            "exists": (gecko_package / "report_results" / "production_design_report.html").exists(),
        },
        {
            "label": "Trigger reproduction report",
            "path": str(trigger_package / "report_results" / "shewanella_trigger_reproduction_report.html"),
            "exists": (trigger_package / "report_results" / "shewanella_trigger_reproduction_report.html").exists(),
        },
        {
            "label": "Trigger reproduction manifest",
            "path": str(trigger_package / "report_results" / "paper_reproduction_report_manifest.json"),
            "exists": (trigger_package / "report_results" / "paper_reproduction_report_manifest.json").exists(),
        },
    ]
    link_item_parts: list[str] = []
    for row in links:
        label = html.escape(str(row["label"]))
        path_text = str(row["path"])
        path_url = path_text.replace("\\", "/")
        status_html = f'<a href="file:///{html.escape(path_url)}">open</a>' if row["exists"] else "<span>missing</span>"
        link_item_parts.append(f"<li><strong>{label}</strong>: {status_html}<br><code>{html.escape(path_text)}</code></li>")
    link_items = "\n".join(link_item_parts)
    index_path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Shewanella integrated showcase</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; line-height: 1.55; color: #142033; }}
    main {{ max-width: 920px; margin: 0 auto; }}
    h1 {{ margin-bottom: 0.2rem; }}
    .card {{ border: 1px solid #d8e3ea; border-radius: 12px; padding: 18px; margin: 18px 0; background: #fbfdff; }}
    code {{ color: #345; font-size: 0.9em; }}
    li {{ margin: 12px 0; }}
  </style>
</head>
<body>
<main>
  <h1>Shewanella integrated showcase</h1>
  <p>Composite demo index linking the GECKO oxygen-condition comparison and transcriptional-trigger paper reproduction outputs.</p>
  <section class="card">
    <h2>Linked reports</h2>
    <ul>{link_items}</ul>
  </section>
  <section class="card">
    <h2>Boundary</h2>
    <p>This index does not merge run packages or generate new scientific results. Model Compare evidence comes from the GECKO run; Analysis and paper-reproduction evidence come from the trigger-paper run.</p>
  </section>
</main>
</body>
</html>
""",
        encoding="utf-8",
    )
    payload = {
        "schema_version": "0.1.0",
        "status": "ready",
        "case_id": case.get("case_id", ""),
        "gecko_run_id": gecko_run_id,
        "trigger_run_id": trigger_run_id,
        "report_html": str(index_path),
        "links": links,
    }
    write_json(manifest_path, payload)
    return {"html": str(index_path), "manifest": str(manifest_path), "links": links}


def _composite_case_readiness(case_id: str, case: dict[str, Any], *, write_artifact: bool) -> dict[str, Any]:
    main_run_id = str(case.get("run_id") or "")
    gecko_case_id = "shewanella_gecko_oxygen"
    trigger_case_id = "shewanella_transcriptional_triggers_lac_lb"
    gecko = case_study_readiness(gecko_case_id, write_artifact=False)
    trigger = case_study_readiness(trigger_case_id, write_artifact=False)
    try:
        main_package = resolve_run_package(main_run_id)
    except ApiError as exc:
        return build_missing_case_readiness_payload(case_id=case_id, run_id=main_run_id, case=case, guidance=exc.detail)

    gecko_checks = case_check_map(gecko)
    trigger_checks = case_check_map(trigger)
    default_pair = gecko.get("default_pair") if isinstance(gecko.get("default_pair"), dict) else {}
    default_scope = gecko.get("default_scope") if isinstance(gecko.get("default_scope"), dict) else {}
    analysis_check = trigger_checks.get("analysis_summary", {})
    report_index = _integrated_case_report_index(case, main_package) if write_artifact else {}
    checks = [
        case_check(
            "run_package",
            "Composite run packages",
            "ready",
            count=2,
            guidance="GECKO and trigger-paper run packages are linked for one display entry.",
        ),
        case_check(
            "inputs",
            "Input package",
            gecko_checks.get("inputs", {}).get("status", "partial"),
            guidance="Input and Model Generator context use the GECKO oxygen run.",
            source_run_id=gecko.get("run_id", ""),
        ),
        case_check(
            "variants",
            "Variant registry",
            gecko_checks.get("variants", {}).get("status", "partial"),
            count=gecko_checks.get("variants", {}).get("count", 0),
            guidance=gecko_checks.get("variants", {}).get("guidance", ""),
            source_run_id=gecko.get("run_id", ""),
        ),
        case_check(
            "default_pair",
            "Default compare pair",
            default_pair.get("status", "partial"),
            reference_variant_id=default_pair.get("reference_variant_id", ""),
            target_variant_id=default_pair.get("target_variant_id", ""),
            guidance="Model Compare uses the GECKO oxygen pair.",
            source_run_id=gecko.get("run_id", ""),
        ),
        case_check(
            "model_compare",
            "Model Compare",
            "ready"
            if gecko_checks.get("reaction_diff", {}).get("status") == "ready"
            and gecko_checks.get("compare_graphs", {}).get("status") == "ready"
            else "partial",
            guidance="GECKO compare graphs and edit provenance come from the oxygen-condition run.",
            source_run_id=gecko.get("run_id", ""),
        ),
        case_check(
            "analysis_summary",
            "Trigger paper Analysis and Summary",
            analysis_check.get("status", "partial"),
            count=analysis_check.get("count", 0),
            guidance=analysis_check.get("guidance", "Analysis and report outputs are read from the trigger-paper run."),
            source_run_id=trigger.get("run_id", ""),
        ),
        case_check(
            "combined_report_index",
            "Combined report index",
            "ready" if report_index.get("html") else "not_generated",
            path=report_index.get("html", ""),
            guidance="Lightweight index links GECKO and trigger-paper reports without merging run packages.",
        ),
    ]
    readiness_ladder = [
        {"stage_id": "input", "label": "Input", "status": checks[1]["status"], "guidance": "Uses GECKO oxygen run inputs."},
        {"stage_id": "model_generator", "label": "Model Generator", "status": checks[2]["status"], "guidance": "Uses GECKO oxygen variants."},
        {"stage_id": "model_compare", "label": "Model Compare", "status": checks[4]["status"], "guidance": "Uses GECKO oxygen pair and KEGG submaps."},
        {"stage_id": "analysis", "label": "Analysis", "status": checks[5]["status"], "guidance": "Uses trigger-paper reproduction workbench."},
        {"stage_id": "summary", "label": "Summary", "status": checks[5]["status"], "guidance": "Uses trigger-paper Summary plus integrated report links."},
    ]
    missing_items = [str(check.get("id")) for check in checks if str(check.get("status")) in {"missing_artifact", "needs_workflow_run", "needs_graph_render", "not_generated"}]
    overall_status = "ready" if not missing_items or missing_items == ["combined_report_index"] else "partial"
    payload = {
        "case_id": case_id,
        "run_id": main_run_id,
        "case": case,
        "story_title": case.get("story_title", ""),
        "story_title_zh": case.get("story_title_zh", ""),
        "story_summary": case.get("story_summary", ""),
        "story_summary_zh": case.get("story_summary_zh", ""),
        "default_compare_view_mode": case.get("default_compare_view_mode", "side_by_side"),
        "evidence_status_labels": case.get("evidence_status_labels", {}),
        "display_next_actions": case.get("display_next_actions", []),
        "overall_status": overall_status,
        "guidance": "Integrated Shewanella case links GECKO Compare with trigger-paper Analysis.",
        "default_pair": default_pair,
        "default_scope": default_scope,
        "linked_runs": case.get("linked_runs", {}),
        "stage_run_map": case.get("stage_run_map", {}),
        "default_compare_context": case.get("default_compare_context", {}),
        "default_analysis_context": case.get("default_analysis_context", {}),
        "checks": checks,
        "readiness_ladder": readiness_ladder,
        "missing_items": missing_items,
        "next_actions": [
            "Use Model Compare for GECKO oxygen-condition kcat/proteomics overlays.",
            "Use Analysis/Summary for trigger-paper GDM-lite, D2T2 reported triggers, and dFBA/glycogen report.",
        ],
        "source_readiness": {
            "gecko_oxygen": gecko,
            "transcriptional_triggers": trigger,
        },
        "combined_report_index": report_index,
        "artifact_path": str(main_package / "case_study" / "case_display_readiness.json"),
    }
    if write_artifact:
        write_json(main_package / "case_study" / "case_display_readiness.json", payload)
    return payload


def case_study_readiness(case_id: str, *, write_artifact: bool = True) -> dict[str, Any]:
    case = _case_study_entry(case_id)
    if bool(case.get("composite_case")):
        return _composite_case_readiness(case_id, case, write_artifact=write_artifact)
    run_id = str(case.get("run_id") or "")
    try:
        package = resolve_run_package(run_id)
    except ApiError as exc:
        return build_missing_case_readiness_payload(
            case_id=case_id,
            run_id=run_id,
            case=case,
            guidance=exc.detail,
        )

    package_context = _resolve_run_package_context(package)
    inventory = package_context.get("artifact_inventory", {}) if isinstance(package_context.get("artifact_inventory"), dict) else {}
    variant_context = package_context.get("variant_context", {}) if isinstance(package_context.get("variant_context"), dict) else {}
    optional_evidence = inventory.get("optional_evidence", {}) if isinstance(inventory.get("optional_evidence"), dict) else {}
    input_rows = read_csv_rows(package / "input_file_map.csv")
    model_rows = [
        row
        for row in input_rows
        if str(row.get("kind") or "").lower() == "model"
        or str(row.get("role") or row.get("file_role") or "").lower() in {"model", "gem", "gsmm", "sbml"}
    ]
    omics_rows = [
        row
        for row in input_rows
        if row not in model_rows and str(row.get("role") or row.get("file_role") or "").lower() not in {"", "ignore"}
    ]
    registry = [dict(row) for row in variant_context.get("variants", [])] if isinstance(variant_context.get("variants"), list) else []
    reference, target, pair_status = _case_default_pair(case, registry)
    annotation_type, annotation_group, annotation_check = _case_annotation_scope(case)
    expected_ecmodel = bool(case.get("expected_ecmodel"))
    kcat_context = optional_evidence.get("kcat_priors") if isinstance(optional_evidence.get("kcat_priors"), dict) else {}
    kcat_status = "ready" if str(kcat_context.get("status") or "") == "ready" else "missing_artifact"
    kcat_count = _safe_int(kcat_context.get("count"))
    capacity = _case_capacity_status_from_context(optional_evidence, expected_ecmodel=expected_ecmodel)
    is_trigger_paper_case = str(case.get("case_id") or "") == "shewanella_transcriptional_triggers_lac_lb"
    if is_trigger_paper_case:
        kcat_status, kcat_count = "not_applicable", 0
        capacity = {
            "status": "not_applicable",
            "count": 0,
            "path": "",
            "guidance": "This transcriptomics/metabolite paper does not provide protein abundance, kcat, or reaction-level enzyme capacity evidence.",
        }
    variant_comparison = inventory.get("variant_comparison", {}) if isinstance(inventory.get("variant_comparison"), dict) else {}
    edit_provenance = inventory.get("edit_provenance", {}) if isinstance(inventory.get("edit_provenance"), dict) else {}
    compare_graphs = inventory.get("compare_graphs", {}) if isinstance(inventory.get("compare_graphs"), dict) else {}
    analysis = inventory.get("analysis_summary", {}) if isinstance(inventory.get("analysis_summary"), dict) else _case_analysis_status(package)
    compare_rows = _safe_int(variant_comparison.get("summary_count"))
    reaction_diff_rows = _safe_int(variant_comparison.get("reaction_diff_count"))
    edit_count = _safe_int(edit_provenance.get("count"))
    graph_count = _safe_int(compare_graphs.get("count"))
    has_guarded_paper_data_gap = (package / "case_study" / "data_needed_manifest.json").exists() and (
        is_trigger_paper_case
        or str(case.get("evidence_status_labels", {}).get("d2t2") or "").lower().startswith("paper-reported")
    )

    checks = [
        case_check(
            "run_package",
            "Run package",
            "ready",
            count=1,
            path=str(package),
            guidance="Run package exists.",
        ),
        case_check(
            "inputs",
            "Input package",
            "ready" if model_rows and omics_rows else "partial" if model_rows else "missing_artifact",
            count=len(input_rows),
            model_count=len(model_rows),
            evidence_count=len(omics_rows),
            guidance=(
                "Model and evidence inputs are indexed."
                if model_rows and omics_rows
                else "Input package is missing model or evidence rows."
            ),
        ),
        case_check(
            "variants",
            "Variant registry",
            "ready" if registry else "needs_workflow_run",
            count=len(registry),
            guidance="Model variants are indexed." if registry else "Run the model generation workflow to create variants.",
        ),
        case_check(
            "default_pair",
            "Default compare pair",
            pair_status,
            reference_variant_id=reference,
            target_variant_id=target,
            guidance=(
                f"Default pair is {reference} vs {target}."
                if pair_status == "ready"
                else "No usable reference/target pair was found."
            ),
        ),
        case_check(
            "variant_comparison",
            "Variant comparison",
            "ready" if compare_rows else "needs_workflow_run",
            count=compare_rows,
            reaction_diff_rows=reaction_diff_rows,
            guidance="Variant comparison outputs are available." if compare_rows else "Run or refresh variant comparison.",
        ),
        case_check(
            "model_edit_provenance",
            "Model edit provenance",
            "ready" if edit_count else "not_generated",
            count=edit_count,
            path=str(package / "workflow_results" / "model_edit_reaction_index.csv"),
            guidance=(
                "Reaction-level model edit provenance is available."
                if edit_count
                else "Run prepare-lite or rerun Model Generator to create model edit provenance."
            ),
        ),
        case_check(
            "kcat_priors",
            "kcat priors",
            kcat_status,
            count=kcat_count,
            guidance="kcat priors are available." if kcat_status == "ready" else "No kcat prior table was found.",
        ),
        case_check(
            "enzyme_capacity",
            "Enzyme capacity",
            capacity.get("status", "not_generated"),
            count=capacity.get("count", 0),
            path=capacity.get("path", ""),
            guidance=capacity.get("guidance", ""),
        ),
        case_check(
            "annotation_groups",
            "Annotation groups",
            annotation_check.get("status", "missing_artifact"),
            annotation_type=annotation_type,
            annotation_group_id=annotation_group,
            group_count=annotation_check.get("group_count", 0),
            reaction_count=annotation_check.get("reaction_count", 0),
            guidance=annotation_check.get("guidance", ""),
        ),
        case_check(
            "compare_graphs",
            "Compare submap graphs",
            "ready" if graph_count else "needs_graph_render",
            count=graph_count,
            guidance="Compare submap graphs are available." if graph_count else "Render compare submap graphs for the default annotation group.",
        ),
        case_check(
            "analysis_summary",
            "Analysis and summary outputs",
            analysis.get("status", "missing_artifact"),
            count=analysis.get("count", 0),
            guidance=analysis.get("guidance", ""),
        ),
    ]

    pair_smoke: dict[str, Any] = {}
    if pair_status == "ready":
        try:
            pair_smoke = run_model_comparison_pair_summary(
                run_id,
                reference_variant_id=reference,
                target_variant_id=target,
                grouping=annotation_type or "subsystem",
                overlay="none",
                annotation_type=annotation_type,
                annotation_group_id=annotation_group,
            )
            reaction_diff_count = len(pair_smoke.get("reaction_diff_index") or [])
            ranking_count = len(pair_smoke.get("difference_ranking") or [])
            checks.append(
                case_check(
                    "reaction_diff",
                    "ReactionDiff smoke",
                    "ready" if reaction_diff_count else "partial",
                    count=reaction_diff_count,
                    ranking_count=ranking_count,
                    guidance=(
                        "ReactionDiff and ranking are available for the default scope."
                        if reaction_diff_count
                        else "Pair summary returned without scoped ReactionDiff rows."
                    ),
                )
            )
        except ApiError as exc:
            checks.append(
                case_check(
                    "reaction_diff",
                    "ReactionDiff smoke",
                    "partial",
                    guidance=f"Pair summary could not be generated: {exc.detail}",
                )
            )

    missing_items = [str(check.get("id")) for check in checks if str(check.get("status")) in {"missing_artifact", "needs_workflow_run", "needs_graph_render"}]
    if "run_package" in missing_items or "inputs" in missing_items:
        overall_status = "missing_artifact"
    elif has_guarded_paper_data_gap and not expected_ecmodel:
        overall_status = "evidence_only_no_ecmodel"
    elif "variants" in missing_items or "variant_comparison" in missing_items:
        overall_status = "needs_workflow_run"
    elif "compare_graphs" in missing_items:
        overall_status = "needs_graph_render"
    elif expected_ecmodel and str(capacity.get("status")) != "ready":
        overall_status = "partial"
    elif not expected_ecmodel and str(capacity.get("status")) != "ready":
        overall_status = "evidence_only_no_ecmodel"
    elif missing_items:
        overall_status = "partial"
    else:
        overall_status = "ready"

    def check_status(check_id: str) -> str:
        for check in checks:
            if check.get("id") == check_id:
                return str(check.get("status") or "partial")
        return "partial"

    readiness_ladder = [
        {
            "stage_id": "input",
            "label": "Input",
            "status": check_status("inputs"),
            "guidance": "Case inputs are indexed and ready for review." if check_status("inputs") == "ready" else "Review missing model/evidence inputs.",
        },
        {
            "stage_id": "model_generator",
            "label": "Model Generator",
            "status": check_status("variants"),
            "guidance": "Variants are available." if check_status("variants") == "ready" else "Run the selected model generation methods.",
        },
        {
            "stage_id": "model_compare",
            "label": "Model Compare",
            "status": "ready" if check_status("reaction_diff") == "ready" and check_status("compare_graphs") == "ready" else check_status("compare_graphs"),
            "guidance": "Compare graphs and ReactionDiff are ready." if check_status("reaction_diff") == "ready" and check_status("compare_graphs") == "ready" else "Render graphs or refresh pair summary.",
        },
        {
            "stage_id": "analysis",
            "label": "Analysis",
            "status": check_status("analysis_summary"),
            "guidance": "Analysis outputs are available." if check_status("analysis_summary") == "ready" else "Run analysis modules or review evidence-only guidance.",
        },
        {
            "stage_id": "summary",
            "label": "Summary",
            "status": check_status("analysis_summary"),
            "guidance": "Summary can cite the current case artifacts." if check_status("analysis_summary") == "ready" else "Summary should explain missing analysis/report artifacts.",
        },
    ]

    next_actions: list[str] = []
    if check_status("variants") != "ready":
        next_actions.append("Run or refresh the workflow for this case.")
    if check_status("compare_graphs") != "ready":
        next_actions.append("Render compare submap graphs for the default annotation group.")
    if str(capacity.get("status")) not in {"ready", "not_applicable"}:
        next_actions.append("Show enzyme capacity as not available/package-ready unless an external ecModel run creates reaction-level capacity.")
    if check_status("analysis_summary") != "ready":
        next_actions.append("Run analysis/report modules or keep Summary in evidence-only mode.")
    if not next_actions:
        next_actions.append("Case is ready for UI demonstration.")

    payload = {
        "case_id": case_id,
        "run_id": run_id,
        "case": case,
        "story_title": case.get("story_title", ""),
        "story_title_zh": case.get("story_title_zh", ""),
        "story_summary": case.get("story_summary", ""),
        "story_summary_zh": case.get("story_summary_zh", ""),
        "default_compare_view_mode": case.get("default_compare_view_mode", "difference"),
        "evidence_status_labels": case.get("evidence_status_labels", {}),
        "display_next_actions": case.get("display_next_actions", []),
        "overall_status": overall_status,
        "guidance": (
            "Case is display-ready."
            if overall_status == "ready"
            else "Case has clear guidance for missing or evidence-only artifacts."
        ),
        "default_pair": {
            "reference_variant_id": reference,
            "target_variant_id": target,
            "status": pair_status,
        },
        "default_scope": {
            "annotation_type": annotation_type,
            "annotation_group_id": annotation_group,
            "status": annotation_check.get("status", "missing_artifact"),
            "preferred_annotation_group_id": case.get("default_annotation_group_id", ""),
        },
        "checks": checks,
        "readiness_ladder": readiness_ladder,
        "missing_items": missing_items,
        "next_actions": next_actions,
        "pair_smoke": {
            "status": pair_smoke.get("status", "not_run") if pair_smoke else "not_run",
            "reaction_diff_count": len(pair_smoke.get("reaction_diff_index") or []) if pair_smoke else 0,
            "ranking_count": len(pair_smoke.get("difference_ranking") or []) if pair_smoke else 0,
            "compare_readiness_summary": pair_smoke.get("compare_readiness_summary", {}) if pair_smoke else {},
        },
        "artifact_path": str(package / "case_study" / "case_display_readiness.json"),
    }
    if write_artifact:
        write_json(package / "case_study" / "case_display_readiness.json", payload)
    return payload


def case_study_prepare_preview(case_id: str) -> dict[str, Any]:
    readiness = case_study_readiness(case_id, write_artifact=True)
    case = readiness.get("case") if isinstance(readiness.get("case"), dict) else {}
    run_id = str(readiness.get("run_id") or case.get("run_id") or "")
    would_run = build_case_prepare_preview_actions(readiness)
    log_payload = build_case_prepare_preview_log_payload(
        case_id=case_id,
        run_id=run_id,
        readiness=readiness,
        would_run=would_run,
    )
    if run_id:
        try:
            package = resolve_run_package(run_id)
            write_json(package / "case_study" / "case_autopilot_log.json", log_payload)
            log_payload["artifact_path"] = str(package / "case_study" / "case_autopilot_log.json")
        except ApiError:
            pass
    return build_case_prepare_preview_response(
        case_id=case_id,
        readiness=readiness,
        would_run=would_run,
        artifact_path=str(log_payload.get("artifact_path") or ""),
    )


def _write_case_qa_matrix_artifacts(package: Path, rows: list[dict[str, Any]]) -> dict[str, str]:
    out_dir = package / "case_study"
    json_path = out_dir / "case_qa_matrix.json"
    csv_path = out_dir / "case_qa_matrix.csv"
    write_json(
        json_path,
        {
            "status": "ready",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "rows": rows,
        },
    )
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["case_id", "case_title", "run_id", "stage", "stage_label", "status", "evidence_ready", "missing_items", "next_action", "artifact_paths"]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    **row,
                    "missing_items": " | ".join(str(item) for item in row.get("missing_items") or []),
                    "artifact_paths": " | ".join(str(item) for item in row.get("artifact_paths") or []),
                }
            )
    return {"json": str(json_path), "csv": str(csv_path)}


def case_study_qa_matrix() -> dict[str, Any]:
    studies = list_case_studies().get("case_studies") or []
    rows: list[dict[str, Any]] = []
    for study in studies:
        if not isinstance(study, dict):
            continue
        case_id = str(study.get("case_id") or "")
        if not case_id:
            continue
        try:
            readiness = case_study_readiness(case_id, write_artifact=False)
        except ApiError as exc:
            readiness = {
                "case_id": case_id,
                "run_id": study.get("run_id", ""),
                "case": study,
                "overall_status": "missing_artifact",
                "guidance": exc.detail,
                "checks": [case_check("run_package", "Run package", "missing_artifact", guidance=exc.detail)],
                "readiness_ladder": [
                    {"stage_id": stage_id, "label": stage_id.replace("_", " ").title(), "status": "missing_artifact", "guidance": exc.detail}
                    for stage_id in CASE_QA_STAGE_CHECKS
                ],
            }
        rows.extend(build_case_readiness_stage_rows(readiness))
    return build_case_qa_matrix_response(studies, rows)


def case_study_prepare_lite(case_id: str) -> dict[str, Any]:
    readiness = case_study_readiness(case_id, write_artifact=True)
    run_id = str(readiness.get("run_id") or "")
    actions: list[dict[str, Any]] = [
        {
            "action": "refresh_readiness",
            "status": "done",
            "heavy_compute": False,
            "message": "Refreshed case display readiness.",
        }
    ]
    try:
        package = resolve_run_package(run_id)
    except ApiError as exc:
        return build_case_prepare_lite_missing_package_response(
            case_id=case_id,
            readiness=readiness,
            actions=actions,
            guidance=exc.detail,
        )

    edit_refresh = refresh_model_edit_artifacts_for_package(
        package,
        edit_record_mode="inferred_legacy",
        update_registry=True,
    )
    actions.append(
        {
            "action": "refresh_edit_provenance",
            "status": edit_refresh.get("status", "partial"),
            "heavy_compute": False,
            "row_count": edit_refresh.get("row_count", 0),
            "edit_record_mode": edit_refresh.get("edit_record_mode", "inferred_legacy"),
            "artifact_path": edit_refresh.get("edit_reaction_index_path", ""),
            "message": edit_refresh.get("guidance", ""),
        }
    )

    default_pair = readiness.get("default_pair") if isinstance(readiness.get("default_pair"), dict) else {}
    default_scope = readiness.get("default_scope") if isinstance(readiness.get("default_scope"), dict) else {}
    reference = str(default_pair.get("reference_variant_id") or "")
    target = str(default_pair.get("target_variant_id") or "")
    annotation_type = str(default_scope.get("annotation_type") or "")
    annotation_group = str(default_scope.get("annotation_group_id") or "")
    if reference and target and reference != target:
        try:
            pair = run_model_comparison_pair_summary(
                run_id,
                reference_variant_id=reference,
                target_variant_id=target,
                grouping=annotation_type or "subsystem",
                overlay="none",
                annotation_type=annotation_type,
                annotation_group_id=annotation_group,
            )
            graph_status = pair.get("network_graphs") if isinstance(pair.get("network_graphs"), dict) else {}
            actions.append(
                {
                    "action": "pair_summary_smoke",
                    "status": "done",
                    "heavy_compute": False,
                    "reaction_diff_count": len(pair.get("reaction_diff_index") or []),
                    "ranking_count": len(pair.get("difference_ranking") or []),
                    "reference_graph_status": (graph_status.get("reference") or {}).get("status") if isinstance(graph_status.get("reference"), dict) else "",
                    "target_graph_status": (graph_status.get("target") or {}).get("status") if isinstance(graph_status.get("target"), dict) else "",
                }
            )
        except ApiError as exc:
            actions.append(
                {
                    "action": "pair_summary_smoke",
                    "status": "partial",
                    "heavy_compute": False,
                    "message": exc.detail,
                }
            )
    else:
        actions.append(
            {
                "action": "pair_summary_smoke",
                "status": "skipped",
                "heavy_compute": False,
                "message": "No valid default reference/target pair is available.",
            }
        )

    readiness = case_study_readiness(case_id, write_artifact=True)
    rows = build_case_readiness_stage_rows(readiness)
    artifacts = _write_case_qa_matrix_artifacts(package, rows)
    log_payload = build_case_prepare_lite_log_payload(
        case_id=case_id,
        run_id=run_id,
        readiness=readiness,
        actions=actions,
        qa_matrix_artifacts=artifacts,
    )
    log_path = package / "case_study" / "case_autopilot_log.json"
    write_json(log_path, log_payload)
    return build_case_prepare_lite_response(
        case_id=case_id,
        readiness=readiness,
        rows=rows,
        qa_matrix_artifacts=artifacts,
        actions=actions,
        artifact_path=str(log_path),
    )


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _workflow_ui_state_path(package: Path) -> Path:
    return package / "workflow_results" / "workflow_ui_state.json"


def _default_workflow_ui_state() -> dict[str, Any]:
    return {
        "active_stage": "input",
        "active_module": "datahub",
        "active_step": "0",
        "selected_variant_id": "",
        "selected_job_id": "",
        "notes": "",
        "updated_at": 0,
        "status": "default",
    }


def _read_workflow_ui_state(package: Path) -> dict[str, Any]:
    existing = read_json_object(_workflow_ui_state_path(package))
    if not existing:
        return _default_workflow_ui_state()
    return _normalize_workflow_ui_state(existing, _default_workflow_ui_state())


def _normalize_workflow_ui_state(payload: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    state = dict(existing or _default_workflow_ui_state())
    for key, max_length in (
        ("active_module", 120),
        ("active_step", 120),
        ("selected_variant_id", 180),
        ("selected_job_id", 180),
        ("notes", 1000),
    ):
        if key in payload:
            state[key] = str(payload.get(key) or "").strip()[:max_length]
    if "active_stage" in payload:
        stage = _normalize_workflow_stage_id(payload.get("active_stage"))
        state["active_stage"] = stage
    else:
        state["active_stage"] = _normalize_workflow_stage_id(state.get("active_stage"))
    state["status"] = "saved" if float(state.get("updated_at") or 0) else "default"
    return state


def _normalize_workflow_stage_id(value: Any) -> str:
    stage = str(value or "input").strip().replace("-", "_")
    stage = WORKFLOW_UI_STAGE_ALIASES.get(stage, stage)
    if stage not in WORKFLOW_UI_STAGE_IDS:
        raise ApiError(400, f"Invalid workflow stage: {value}")
    return stage


def _workflow_stage_summary(package: Path, stage_id: str) -> dict[str, Any]:
    stage_files: dict[str, list[tuple[Path, str]]] = {
        "input": [
            (package / "input_file_map.csv", "input_file_map"),
            (package / "upload_manifest.json", "upload_manifest"),
            (package / "source_manifest.json", "source_manifest"),
        ],
        "model_generator": [
            (package / "workflow_results" / "model_variant_registry.csv", "model_variant_registry"),
            (package / "workflow_results" / "model_generation_parameters_summary.csv", "model_generation_parameters"),
            (package / "workflow_results" / "workflow_selection.csv", "workflow_selection"),
            (package / "gecko_package" / "gecko_adapter_config.json", "gecko_adapter_config"),
        ],
        "model_comparison": [
            (package / "variant_comparison" / "variant_comparison_summary.csv", "variant_comparison_summary"),
            (package / "variant_comparison" / "variant_flux_comparison.csv", "variant_flux_comparison"),
            (package / "variant_comparison" / "variant_evidence_quality.csv", "variant_evidence_quality"),
            (package / "gecko_run_results" / "gecko_flux_delta_high_vs_low.csv", "gecko_flux_delta"),
        ],
        "analysis_visualization": [
            (package / "workflow_results" / "analysis_parameters_summary.csv", "analysis_parameters"),
            (package / "production_results" / "production_target_readiness.csv", "production_target_readiness"),
            (package / "gecko_run_results" / "gecko_enzyme_usage_highO2.csv", "gecko_enzyme_usage_highO2"),
            (package / "visualization_results" / "sammi", "sammi_visualization_dir"),
        ],
        "verify_report": [
            (package / "report_results" / "report_manifest.json", "report_manifest"),
            (package / "report_results", "report_results_dir"),
            (package / "cobra_results" / "report.html", "legacy_audit_report"),
        ],
    }
    files = [_file_summary(package, path, label) for path, label in stage_files.get(stage_id, [])]
    ready_files = [item for item in files if item["exists"]]
    if stage_id == "verify_report" and (package / "report_results").exists():
        reports = _relative_files(package, package / "report_results", "*.html")
        if reports:
            ready_files.append({"label": "report_html", "path": str(package / "report_results"), "relative_path": "report_results", "exists": True, "row_count": 0})
    status = "ready" if ready_files else "missing"
    if ready_files and len(ready_files) < len(files):
        status = "partial"
    return {
        "stage_id": stage_id,
        "label": WORKFLOW_UI_STAGE_LABELS.get(stage_id, stage_id),
        "status": status,
        "ready_file_count": len(ready_files),
        "key_files": files,
        "guidance": _stage_guidance(stage_id, status),
    }


def _stage_guidance(stage_id: str, status: str) -> str:
    if status == "ready":
        return "Core files for this stage are present."
    messages = {
        "input": "Import or upload a run package before continuing.",
        "model_generator": "Run model generation or refresh the model variant registry.",
        "model_comparison": "Generate model comparison outputs after model generation.",
        "analysis_visualization": "Run analysis and visualization jobs to populate this stage.",
        "verify_report": "Build reports and review checker outputs before presenting results.",
    }
    return messages.get(stage_id, "Stage outputs are not available yet.")


def _file_summary(package: Path, path: Path, label: str) -> dict[str, Any]:
    return build_file_summary(package, path, label, read_rows=read_csv_rows)


def _table_preview(path: Path, *, limit: int = 25) -> list[dict[str, str]]:
    return preview_table_rows(path, read_rows=read_csv_rows, limit=limit)


def _latest_jobs_for_run(run_id: str, *, limit: int = 10) -> list[dict[str, Any]]:
    rows = []
    for job in list_jobs(limit=200):
        if str(job.get("run_id", "")) == run_id:
            rows.append(job)
        if len(rows) >= limit:
            break
    return rows


def _collect_json_files(package: Path, filename: str, *, limit: int = 20) -> list[dict[str, Any]]:
    return collect_json_artifacts(package, filename, read_json=read_json_object, limit=limit)


def _run_model_path(package: Path) -> Path | None:
    return find_run_model_path(package, read_rows=read_csv_rows)


def _model_id_from_existing_manifest(gecko_package: Path) -> str:
    return read_model_id_from_gecko_manifest(gecko_package, read_json=read_json_object)


def _apply_workspace_root(root: Path, *, persist: bool) -> None:
    global WORKSPACE_ROOT, USER_RUNS_DIR, EXAMPLES_DIR, TASK_LOGS_DIR, ATLAS_CURATION_WORKSPACES_DIR, ALLOWED_FILE_ROOTS
    resolved = root.resolve()
    WORKSPACE_ROOT = resolved
    USER_RUNS_DIR = resolved / "user_runs"
    EXAMPLES_DIR = resolved / "examples"
    TASK_LOGS_DIR = resolved / "task_logs"
    ATLAS_CURATION_WORKSPACES_DIR = resolved / "atlas_curation_workspaces"
    ALLOWED_FILE_ROOTS = (resolved, APP_ROOT)
    if persist:
        write_json(
            WORKSPACE_CONFIG_PATH,
            build_workspace_config_payload(resolved, updated_at=time.time()),
        )


def _initialize_workspace_dirs() -> None:
    USER_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    EXAMPLES_DIR.mkdir(parents=True, exist_ok=True)
    TASK_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    ATLAS_CURATION_WORKSPACES_DIR.mkdir(parents=True, exist_ok=True)


def safe_job_path(job_id: str, suffix: str) -> Path:
    if not job_id or not re_match_job_id(job_id):
        raise ApiError(400, "Invalid job_id.")
    return TASK_LOGS_DIR / f"{job_id}{suffix}"


def re_match_job_id(job_id: str) -> bool:
    return all(ch.isalnum() or ch in {"_", "-"} for ch in job_id)


def _iter_run_packages() -> list[Path]:
    return list_known_run_packages(USER_RUNS_DIR, EXAMPLES_DIR)


def _relative_files(package: Path, root: Path, pattern: str) -> list[dict[str, str]]:
    return list_relative_files(package, root, pattern)


def _resolve_existing_directory(path_text: str, label: str) -> Path:
    if not path_text or not str(path_text).strip():
        raise ApiError(400, f"Missing {label.lower()} path.")
    resolved = resolve_directory_candidate_path(path_text, base_root=WORKSPACE_ROOT)
    if not resolved.exists():
        raise ApiError(404, f"{label} does not exist: {path_text}")
    if not resolved.is_dir():
        raise ApiError(400, f"{label} must be a directory: {path_text}")
    return resolved


def _looks_like_run_package(path: Path) -> bool:
    return looks_like_run_package(path)


def _run_package_candidate(path: Path, location: str) -> dict[str, Any]:
    overview = _safe_run_overview(path)
    return build_run_package_candidate(
        path,
        location,
        user_runs_dir=USER_RUNS_DIR,
        known_packages=_iter_run_packages(),
        overview=overview,
    )


def _safe_run_overview(path: Path) -> dict[str, Any]:
    return safe_run_overview(
        path,
        read_overview=run_overview,
        read_rows=read_csv_rows,
        read_variants=read_model_variant_registry,
    )


def _sanitize_run_id(value: str) -> str:
    return sanitize_run_id(value)


def _next_available_run_id(base: str) -> str:
    return next_available_run_id(base, USER_RUNS_DIR, default="run")


def _next_available_archive_id(base: str) -> str:
    return next_available_run_id(base, WORKSPACE_ROOT / "archived_runs", default="run")


def _resolve_archived_run(run_id: str) -> Path:
    if not run_id or not re_match_job_id(run_id):
        raise ApiError(400, "Invalid run_id.")
    archive_root = (WORKSPACE_ROOT / "archived_runs").resolve()
    source = (archive_root / run_id).resolve()
    if not _is_relative_to(source, archive_root):
        raise ApiError(403, "Archived run access is restricted to active workspace archived_runs.")
    if not source.exists() or not source.is_dir():
        raise ApiError(404, f"Archived run package not found: {run_id}")
    return source


def _archived_run_overview(path: Path) -> dict[str, Any]:
    manifest = read_json_object(path / "archive_manifest.json")
    overview = _safe_run_overview(path)
    return build_archived_run_overview(path, overview=overview, manifest=manifest)


def _write_import_manifest(target: Path, source: Path, target_run_id: str) -> dict[str, Any]:
    manifest = build_import_manifest_payload(
        target,
        source,
        target_run_id,
        workspace_root=WORKSPACE_ROOT,
        user_runs_dir=USER_RUNS_DIR,
        imported_at=time.time(),
    )
    write_json(target / "import_manifest.json", manifest)
    return manifest


def _write_archive_manifest(target: Path, source: Path, run_id: str) -> dict[str, Any]:
    manifest = build_archive_manifest_payload(
        target,
        source,
        run_id,
        workspace_root=WORKSPACE_ROOT,
        user_runs_dir=USER_RUNS_DIR,
        archive_root=WORKSPACE_ROOT / "archived_runs",
        archived_at=time.time(),
    )
    write_json(target / "archive_manifest.json", manifest)
    return manifest


def _write_restore_manifest(target: Path, source: Path, run_id: str) -> dict[str, Any]:
    manifest = build_restore_manifest_payload(
        target,
        source,
        run_id,
        workspace_root=WORKSPACE_ROOT,
        user_runs_dir=USER_RUNS_DIR,
        archive_root=WORKSPACE_ROOT / "archived_runs",
        restored_at=time.time(),
    )
    write_json(target / "restore_manifest.json", manifest)
    return manifest


def _venv_python_path() -> Path:
    if sys.platform == "win32":
        return APP_ROOT / ".venv" / "Scripts" / "python.exe"
    return APP_ROOT / ".venv" / "bin" / "python"


def _config_or_env(config: dict[str, Any], key: str, env_key: str) -> str:
    return str(config.get(key) or os.environ.get(env_key) or "").strip()


def _resolve_configured_path(path_text: str) -> Path:
    candidate = Path(path_text).expanduser()
    if not candidate.is_absolute():
        candidate = APP_ROOT / candidate
    return candidate


def _resolve_command_or_path(value: str) -> str:
    if not value:
        return ""
    candidate = Path(value).expanduser()
    if candidate.exists():
        return str(candidate.resolve())
    resolved = shutil.which(value)
    return resolved or ""


def _default_matlab_cmd(payload: dict[str, Any], config: dict[str, Any]) -> str:
    value = str(payload.get("matlab_cmd") or config.get("matlab_cmd") or os.environ.get("MATLAB_CMD") or "").strip()
    if value:
        return value
    windows_default = Path(r"D:\Matlab\bin\matlab.EXE")
    if windows_default.exists():
        return str(windows_default)
    return "matlab"


def _path_status(path_text: str, *, expect_file: bool = False) -> tuple[str, str, bool]:
    if not path_text:
        return "missing", "", False
    candidate = _resolve_configured_path(path_text)
    exists = candidate.is_file() if expect_file else candidate.exists()
    if exists:
        return "configured", str(candidate.resolve()), True
    return "invalid_path", str(candidate), False


def _path_dependency_row(
    dependency_id: str,
    label: str,
    path_text: str,
    required_for: str,
    install_guidance: str,
    missing_action: str,
    *,
    expect_file: bool = False,
    optional: bool = False,
) -> dict[str, Any]:
    status, detected_path, exists = _path_status(path_text, expect_file=expect_file)
    if optional and status == "missing":
        status = "optional_missing"
    return {
        "id": dependency_id,
        "label": label,
        "status": status,
        "detected_path": detected_path if exists else "",
        "configured_path": path_text,
        "required_for": required_for,
        "install_guidance": install_guidance,
        "next_action": "No action needed for the current optional workflow." if status == "optional_missing" else missing_action if status != "configured" else "Configured.",
    }


def _multi_path_dependency_row(
    dependency_id: str,
    label: str,
    paths: dict[str, str],
    required_for: str,
    install_guidance: str,
    missing_action: str,
) -> dict[str, Any]:
    configured = {key: value for key, value in paths.items() if value}
    existing: dict[str, str] = {}
    invalid: dict[str, str] = {}
    for key, value in configured.items():
        status, detected_path, exists = _path_status(value)
        if exists:
            existing[key] = detected_path
        elif status == "invalid_path":
            invalid[key] = value
    if existing:
        status = "configured"
        next_action = "Configured."
    elif invalid:
        status = "invalid_path"
        next_action = "Fix the configured path or leave it blank until this MATLAB helper is needed."
    else:
        status = "optional_missing"
        next_action = missing_action
    return {
        "id": dependency_id,
        "label": label,
        "status": status,
        "detected_path": "; ".join(f"{key}={value}" for key, value in existing.items()),
        "configured_path": "; ".join(f"{key}={value}" for key, value in configured.items()),
        "required_for": required_for,
        "install_guidance": install_guidance,
        "next_action": next_action,
    }


def _solver_dependency_row(solver: str) -> dict[str, Any]:
    normalized = solver.strip().lower()
    detected = ""
    status = "optional_missing"
    next_action = "Configure a commercial solver only if your workflow requires it; COBRApy can often use open-source defaults."
    if normalized:
        if normalized in {"gurobi", "gurobipy"}:
            spec = importlib.util.find_spec("gurobipy")
            detected = str(spec.origin) if spec and spec.origin else shutil.which("gurobi_cl") or ""
        elif normalized in {"cplex"}:
            spec = importlib.util.find_spec("cplex")
            detected = str(spec.origin) if spec and spec.origin else shutil.which("cplex") or ""
        else:
            detected = shutil.which(normalized) or ""
        status = "available" if detected else "needs_manual_install"
        next_action = "Solver detected." if detected else f"Install or license solver '{solver}', then ensure it is available to Python or PATH."
    return {
        "id": "solver",
        "label": "Solver",
        "status": status,
        "detected_path": detected,
        "configured_path": solver,
        "required_for": "Optional high-performance FBA/FVA/MEMOTE workflows.",
        "install_guidance": "Commercial solvers and licenses are managed outside this app. Configure a solver name only after installing it.",
        "next_action": next_action,
    }


def _sammi_dependency_row(path_text: str) -> dict[str, Any]:
    status, detected_path, exists = _path_status(path_text)
    index_exists = bool(exists and (Path(detected_path) / "index.html").exists())
    vendor = sammi_vendor_status(APP_ROOT)
    detected_output = detected_path if exists else ""
    if not path_text:
        if vendor["vendored_assets_available"]:
            status = "configured"
            detected_path = str(vendor["assets_root"])
            detected_output = detected_path
            next_action = "Vendored SAMMI standalone assets are available; local SAMMI mode can be used."
        else:
            status = "optional_missing"
            next_action = "Use external SAMMI web app mode, configure SAMMI_STANDALONE_HOME, or run tools\\vendor_sammi_standalone.ps1."
    elif exists and index_exists:
        status = "configured"
        next_action = "Local standalone SAMMI assets are configured."
    elif exists:
        status = "needs_manual_install"
        next_action = "Directory exists but index.html was not found; point SAMMI_STANDALONE_HOME at standalone SAMMI assets."
    else:
        status = "invalid_path"
        next_action = "Fix SAMMI_STANDALONE_HOME or keep using external-open mode."
    return {
        "id": "sammi_standalone_home",
        "label": "SAMMI_STANDALONE_HOME",
        "status": status,
        "detected_path": detected_output,
        "configured_path": path_text,
        "required_for": "Optional local SAMMI standalone visualization shell.",
        "install_guidance": "SAMMI external-open mode works without local assets. Local embedding can use SAMMI_STANDALONE_HOME or vendored standalone assets generated by tools\\vendor_sammi_standalone.ps1.",
        "next_action": next_action,
    }


def _matlab_literal(value: str) -> str:
    return str(value or "").replace("\\", "/").replace("'", "''")


def _matlab_probe_expression(config: dict[str, Any]) -> str:
    gecko_home = _matlab_literal(str(config.get("gecko_home", "")))
    raven_home = _matlab_literal(str(config.get("raven_home", "")))
    cobra_home = _matlab_literal(str(config.get("cobra_toolbox_home", "")))
    return (
        "geckoHome='"
        + gecko_home
        + "'; ravenHome='"
        + raven_home
        + "'; cobraHome='"
        + cobra_home
        + "'; "
        "if ~isempty(geckoHome), if isfolder(geckoHome), addpath(genpath(geckoHome)); fprintf('GECKO_HOME_OK=%s\\n',geckoHome); else, error('GECKO_HOME missing: %s',geckoHome); end, end; "
        "if ~isempty(ravenHome), if isfolder(ravenHome), addpath(genpath(ravenHome)); fprintf('RAVEN_HOME_OK=%s\\n',ravenHome); else, error('RAVEN_HOME missing: %s',ravenHome); end, end; "
        "if ~isempty(cobraHome), if isfolder(cobraHome), addpath(genpath(cobraHome)); fprintf('COBRA_TOOLBOX_HOME_OK=%s\\n',cobraHome); else, error('COBRA_TOOLBOX_HOME missing: %s',cobraHome); end, end; "
        "checks={'runDLKcat','ModelAdapterManager','makeEcModel','readCbModel','importModel'}; "
        "for i=1:numel(checks), name=checks{i}; fprintf('MATLAB_CHECK %s file=%d class=%d\\n',name,exist(name,'file'),exist(name,'class')); end"
    )


def _resolve_makensis_path() -> str:
    found = shutil.which("makensis")
    if found:
        return found
    candidates = [
        Path(os.environ.get("ProgramFiles", "")) / "NSIS" / "makensis.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "NSIS" / "makensis.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "electron-builder" / "Cache",
    ]
    for candidate in candidates:
        if not str(candidate) or not candidate.exists():
            continue
        if candidate.is_file():
            return str(candidate)
        try:
            nested = next(candidate.rglob("makensis.exe"), None)
        except OSError:
            nested = None
        if nested:
            return str(nested)
    return ""


def _makensis_version(path_text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text)
    if not path.exists():
        return ""
    try:
        completed = subprocess.run(
            [str(path), "/VERSION"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if completed.returncode != 0:
        return ""
    return (completed.stdout or completed.stderr).strip()


def _same_path(left: Path, right: Path) -> bool:
    return same_path(left, right)


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _requirements_modules(path: Path) -> list[str]:
    if not path.exists():
        return []
    modules: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        package = re.split(r"[<>=!~;\[]", line, maxsplit=1)[0].strip()
        if package:
            modules.append(_import_name(package))
    return modules


def _optional_backend_modules() -> list[str]:
    modules = _requirements_modules(APP_ROOT / "requirements-optional.txt")
    for extra in ["troppo", "pytfa"]:
        if extra not in modules:
            modules.append(extra)
    return modules


def _import_name(package: str) -> str:
    package_map = {
        "uvicorn": "uvicorn",
        "appdirs": "appdirs",
        "openpyxl": "openpyxl",
        "xlrd": "xlrd",
    }
    normalized = package.strip().lower().replace("-", "_")
    return package_map.get(normalized, normalized)


def _module_rows(modules: list[str]) -> list[dict[str, str]]:
    seen: set[str] = set()
    rows: list[dict[str, str]] = []
    for module in modules:
        if module in seen:
            continue
        seen.add(module)
        rows.append(_module_row(module))
    return rows


def _module_row(module: str) -> dict[str, str]:
    spec = importlib.util.find_spec(module)
    available = spec is not None
    version = ""
    if available:
        try:
            version = importlib.metadata.version(module)
        except importlib.metadata.PackageNotFoundError:
            version = "importable"
    return {
        "module": module,
        "import_name": module,
        "status": "available" if available else "missing",
        "version": version,
        "source": str(spec.origin) if spec and spec.origin else "",
    }


def _is_relative_to(path: Path, root: Path) -> bool:
    return is_relative_to_path(path, root)


def _initialize_workspace_from_config() -> None:
    try:
        config = read_json_object(WORKSPACE_CONFIG_PATH)
    except (OSError, json.JSONDecodeError):
        return
    configured = str(config.get("workspace_root", "") or "").strip()
    if not configured:
        return
    candidate = Path(configured).expanduser()
    if not candidate.is_absolute():
        candidate = APP_ROOT / candidate
    try:
        resolved = candidate.resolve()
    except OSError:
        return
    if resolved.exists() and resolved.is_dir():
        _apply_workspace_root(resolved, persist=False)


_initialize_workspace_from_config()
