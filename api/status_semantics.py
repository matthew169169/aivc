"""Shared status semantics for resource and evidence readiness.

The API still exposes domain-specific wrappers from services.py, but this module
keeps the vocabulary in one place so UI docs, Resource Atlas, and Model Compare
can converge on the same missing-data language.
"""

from __future__ import annotations

from typing import Any


USABLE_READINESS = {"ready_for_import", "ready_for_reference", "package_ready"}
NEEDS_WORK_READINESS = {"needs_gene_mapping", "needs_condition_curation", "manual_curation_required"}
INFO_BLOCKED_READINESS = {"raw_data_only", "metadata_only", "license_or_access_limited"}

CASE_STATUS_LABELS = {
    "missing_artifact": "not generated",
    "needs_workflow_run": "needs workflow run",
    "needs_graph_render": "needs graph render",
    "package_ready_only": "package-ready only",
    "reaction_level_unavailable": "reaction-level unavailable",
    "reaction-level unavailable": "reaction-level unavailable",
    "not_generated": "not generated",
    "not_applicable": "not applicable",
    "not applicable": "not applicable",
    "external_ecmodel_pending": "external ecModel pending",
    "evidence_only_no_ecmodel": "evidence-only case",
    "evidence-only case": "evidence-only case",
    "ready": "ready",
    "partial": "partial",
}


def resource_readiness_class(readiness: str) -> str:
    value = str(readiness or "metadata_only")
    if value in USABLE_READINESS:
        return "usable"
    if value in NEEDS_WORK_READINESS:
        return "needs_work"
    return "info_blocked"


def resource_main_blocker(readiness_counts: dict[str, int]) -> str:
    for key in ("needs_condition_curation", "needs_gene_mapping", "manual_curation_required"):
        if readiness_counts.get(key, 0):
            return key
    for key in ("raw_data_only", "metadata_only", "license_or_access_limited"):
        if readiness_counts.get(key, 0):
            return key
    return ""


def case_status_label(status: Any) -> str:
    text = str(status or "partial").strip()
    return CASE_STATUS_LABELS.get(text, text.replace("_", " "))


def support_status(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if text in {"true", "yes", "ready", "ok", "within", "within_fva", "mapped", "valid", "pass", "passed"}:
        return "ready"
    if text in {"false", "no", "outside", "failed", "fail"}:
        return "outside_or_failed"
    if "partial" in text:
        return "partial"
    if "missing" in text or "not_available" in text or "unavailable" in text:
        return "not_available"
    return text
