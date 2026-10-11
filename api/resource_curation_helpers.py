"""Pure Resource Atlas curation helpers.

These helpers keep manual curation role/template semantics away from
endpoint-facing service orchestration. They do not read or write files and do
not import FastAPI.
"""

from __future__ import annotations

import io
from typing import Any

from omics_router.validators import EXPECTED_COLUMNS, inspect_table_file


def curation_target_role(row: dict[str, Any], resource_kind: str = "") -> str:
    if resource_kind == "model":
        return "model_reference"
    omics_type = str(row.get("omics_type") or "").lower()
    text = " ".join(
        [
            str(row.get("resource_id") or ""),
            str(row.get("title") or ""),
            str(row.get("data_level") or ""),
            str(row.get("readiness_reason") or ""),
            str(row.get("source_database") or ""),
        ]
    ).lower()
    if "condition" in omics_type or "condition" in text or "bound" in text:
        return "condition_exchange_bounds"
    if "kcat" in omics_type or "kcat" in text or "gotenzymes" in text:
        return "ml_priors"
    if "annotation" in omics_type or "annotation" in text or "kegg" in text or "uniprot" in text:
        return "uniprot_annotation"
    if "proteomics" in omics_type or "protein" in text or "pride" in text:
        return "absolute_proteomics"
    if "metabolomics" in omics_type or "metabol" in text:
        return "extracellular_metabolomics"
    if "transcriptomics" in omics_type or "expression" in text or "geo" in text:
        return "transcriptomics"
    return "custom_annotation"


def curation_template_for_role(role: str) -> dict[str, Any]:
    templates: dict[str, dict[str, Any]] = {
        "transcriptomics": {
            "suggested_filename": "curated_transcriptomics.csv",
            "columns": ["gene_id", "sample", "value"],
            "example_rows": [{"gene_id": "SO_0001", "sample": "condition_1", "value": "12.5"}],
        },
        "absolute_proteomics": {
            "suggested_filename": "curated_absolute_proteomics.csv",
            "columns": ["protein_id", "sample", "value", "unit"],
            "example_rows": [{"protein_id": "Q8EKT7", "sample": "condition_1", "value": "3.4", "unit": "fmol_per_ug"}],
        },
        "relative_proteomics": {
            "suggested_filename": "curated_relative_proteomics.csv",
            "columns": ["protein_id", "sample", "value"],
            "example_rows": [{"protein_id": "Q8EKT7", "sample": "condition_1", "value": "1.7"}],
        },
        "ml_priors": {
            "suggested_filename": "curated_kcat_priors.csv",
            "columns": ["target_id", "target_type", "value", "confidence", "unit", "source"],
            "example_rows": [
                {
                    "target_id": "R_PFK",
                    "target_type": "reaction",
                    "value": "120.0",
                    "confidence": "0.8",
                    "unit": "1/s",
                    "source": "manual_curation",
                }
            ],
        },
        "condition_exchange_bounds": {
            "suggested_filename": "curated_condition_bounds.csv",
            "columns": ["condition", "reaction_id", "lower_bound", "upper_bound"],
            "example_rows": [{"condition": "condition_1", "reaction_id": "EX_o2_e", "lower_bound": "-10", "upper_bound": "1000"}],
        },
        "uniprot_annotation": {
            "suggested_filename": "curated_reaction_annotation.csv",
            "columns": ["reaction_id", "subsystem", "kegg_pathway", "custom_group", "gene_id", "uniprot_id", "ec_number"],
            "example_rows": [
                {
                    "reaction_id": "R_PFK",
                    "subsystem": "Glycolysis",
                    "kegg_pathway": "Glycolysis / Gluconeogenesis",
                    "custom_group": "central carbon",
                    "gene_id": "geneA",
                    "uniprot_id": "P0A796",
                    "ec_number": "2.7.1.11",
                }
            ],
        },
        "extracellular_metabolomics": {
            "suggested_filename": "curated_metabolomics.csv",
            "columns": ["metabolite_id", "sample", "value", "unit"],
            "example_rows": [{"metabolite_id": "ac_e", "sample": "condition_1", "value": "2.1", "unit": "mM"}],
        },
        "model_reference": {
            "suggested_filename": "model_resource_note.csv",
            "columns": ["model_id", "source_file", "organism", "note"],
            "example_rows": [{"model_id": "iML1515", "source_file": "model.xml", "organism": "Escherichia coli", "note": "model metadata"}],
        },
        "custom_annotation": {
            "suggested_filename": "curated_custom_annotation.csv",
            "columns": ["reaction_id", "custom_group", "note"],
            "example_rows": [{"reaction_id": "R_PFK", "custom_group": "central carbon", "note": "manual group"}],
        },
    }
    return templates.get(role, templates["custom_annotation"])


def curation_required_columns(role: str) -> set[str]:
    required: dict[str, set[str]] = {
        "condition_exchange_bounds": {"condition", "reaction_id", "lower_bound", "upper_bound"},
        "uniprot_annotation": {"reaction_id"},
        "custom_annotation": {"reaction_id", "custom_group"},
        "model_reference": {"model_id"},
    }
    if role in required:
        return required[role]
    return EXPECTED_COLUMNS.get(role, set())


def curation_inspection_role(role: str) -> str:
    if role == "condition_exchange_bounds":
        return "fluxomics"
    if role == "custom_annotation":
        return "uniprot_annotation"
    if role == "model_reference":
        return "id_alias_table"
    return role


def curation_suggested_methods(role: str) -> list[str]:
    if role == "transcriptomics":
        return ["eflux", "fastcore", "consensus_evidence"]
    if role in {"absolute_proteomics", "relative_proteomics"}:
        return ["consensus_evidence", "enzyme_gecko"]
    if role == "ml_priors":
        return ["enzyme_gecko"]
    if role == "condition_exchange_bounds":
        return ["fba_pfba", "eflux_delta_fba"]
    if role in {"uniprot_annotation", "custom_annotation"}:
        return ["model_compare", "analysis_visualization"]
    if role == "extracellular_metabolomics":
        return ["analysis_visualization", "summary_evidence"]
    return ["manual_review"]


def curation_guidance_for_resource(row: dict[str, Any], role: str) -> str:
    readiness = str(row.get("readiness") or row.get("import_readiness") or "metadata_only")
    if role == "transcriptomics":
        return "Use sample as the condition/sample label required by the current upload schema."
    if role == "ml_priors":
        return "Use target_id for reaction_id_or_enzyme_id and target_type for reaction/enzyme; preview does not validate biochemical mapping."
    if role == "condition_exchange_bounds":
        return "Condition bounds templates are previewed locally and should be uploaded through the Input condition files section."
    if role in {"uniprot_annotation", "custom_annotation"}:
        return "Annotation templates can enable Compare/Analysis grouping; reaction ids must match the model for downstream mapping."
    if readiness in {"metadata_only", "raw_data_only", "needs_gene_mapping", "needs_condition_curation"}:
        return "This resource remains curation-only until a user-provided CSV passes preview and is uploaded through Input."
    return "Ready resources may still use this template as a manual review aid."


def normalize_preview_column(column: str) -> str:
    return column.strip().lower().replace("-", "_").replace(" ", "_")


def resolve_curation_role(requested_role: str, resource: dict[str, Any], resource_kind: str) -> str:
    selected_role = (requested_role or curation_target_role(resource, resource_kind)).strip()
    return selected_role or "custom_annotation"


def curation_preview_status(role: str, inspection_status: str, columns: list[str], missing_columns: list[str]) -> str:
    custom_role = role in {"condition_exchange_bounds", "uniprot_annotation", "custom_annotation", "model_reference"}
    status = "ready" if inspection_status == "ok" and not missing_columns else "partial"
    if custom_role and columns:
        status = "ready" if not missing_columns else "partial"
    return status


def build_resource_curation_template_response(
    *,
    resource_id: str,
    resource_kind: str,
    resource: dict[str, Any],
) -> dict[str, Any]:
    role = curation_target_role(resource, resource_kind)
    template = curation_template_for_role(role)
    readiness = str(resource.get("readiness") or resource.get("import_readiness") or "metadata_only")
    return {
        "status": "ready",
        "resource_id": resource_id,
        "resource_kind": resource_kind,
        "resource_title": resource.get("title") or resource.get("model_name") or resource.get("model_id") or resource_id,
        "readiness": readiness,
        "target_role": role,
        "suggested_filename": template["suggested_filename"],
        "columns": template["columns"],
        "example_rows": template["example_rows"],
        "readiness_guidance": curation_guidance_for_resource(resource, role),
        "suggested_methods": curation_suggested_methods(role),
        "resource": resource,
    }


def build_resource_curation_preview_response(
    *,
    status: str,
    resource_id: str,
    role: str,
    detected_role: str,
    filename: str,
    columns: list[str],
    missing_columns: list[str],
    warnings: list[str],
    details: list[str],
) -> dict[str, Any]:
    return {
        "status": status,
        "resource_id": resource_id,
        "role": role,
        "detected_role": detected_role,
        "filename": filename,
        "columns": columns,
        "missing_columns": missing_columns,
        "warnings": warnings,
        "details": details,
        "suggested_methods": curation_suggested_methods(role),
        "readiness_preview": "curated_file_preview_ready" if status == "ready" else "curation_needs_review",
        "guidance": (
            "Curated file preview is ready. Add this CSV through the Input upload panel to stage it."
            if status == "ready"
            else "Curated file needs column review before it can be uploaded as workflow evidence."
        ),
    }


def preview_resource_curation_file(
    *,
    resource_id: str,
    resource_kind: str,
    resource: dict[str, Any],
    requested_role: str,
    filename: str,
    data: bytes,
) -> dict[str, Any]:
    """Apply curation preview policy to a caller-owned resource snapshot."""

    selected_role = resolve_curation_role(requested_role, resource, resource_kind)
    expected_columns = curation_required_columns(selected_role)
    inspection_role = curation_inspection_role(selected_role)
    selected_omics = [inspection_role] if inspection_role in EXPECTED_COLUMNS else list(EXPECTED_COLUMNS)
    inspection = inspect_table_file(io.BytesIO(data), filename, selected_omics)
    normalized = {normalize_preview_column(column) for column in inspection.columns}
    missing_columns = sorted(column for column in expected_columns if column not in normalized)
    warnings = list(inspection.details)
    if missing_columns:
        warnings.append(f"{selected_role}: missing {', '.join(missing_columns)}")
    status = curation_preview_status(selected_role, inspection.status, inspection.columns, missing_columns)
    return build_resource_curation_preview_response(
        status=status,
        resource_id=resource_id,
        role=selected_role,
        detected_role=inspection_role,
        filename=filename,
        columns=inspection.columns,
        missing_columns=missing_columns,
        warnings=warnings,
        details=inspection.details,
    )
