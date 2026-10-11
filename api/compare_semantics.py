"""Pure Model Compare readiness and guidance helpers."""

from __future__ import annotations

from typing import Any


COMPARE_MISSING_STATUSES = {
    "",
    "missing",
    "missing_graph",
    "not_selected",
    "not_available",
    "condition_level_only",
    "summary_level_only",
}


def compare_readiness_summary(
    *,
    parse_ready: bool,
    graph_ready: bool,
    annotation_scope: dict[str, Any],
    submap_evidence_summary: dict[str, Any],
    pair_difference_summary: dict[str, Any],
    behavior_context_summary: dict[str, Any],
    behavior_support_context: dict[str, Any],
) -> dict[str, Any]:
    capacity_status = str(submap_evidence_summary.get("enzyme_capacity_status") or "not_available")
    support_counts = submap_evidence_summary.get("behavior_support_counts") or {}
    behavior_counts = submap_evidence_summary.get("behavior_signal_counts") or {}
    return {
        "status": "ready" if parse_ready and graph_ready and annotation_scope.get("status") == "ready" else "partial",
        "parse_status": "ready" if parse_ready else "partial",
        "graph_status": "ready" if graph_ready else "missing_graph",
        "annotation_scope_status": annotation_scope.get("status") or "not_selected",
        "structural_status": submap_evidence_summary.get("structural_status") or "unknown",
        "kcat_status": "ready" if int(submap_evidence_summary.get("kcat_covered_count") or 0) else "not_available",
        "enzyme_capacity_status": capacity_status,
        "proteomics_status": submap_evidence_summary.get("proteomics_status") or "mapping_pending",
        "behavior_status": "ready" if int(behavior_counts.get("ready") or 0) else behavior_context_summary.get("status") or "not_available",
        "behavior_support_status": (
            "ready"
            if int(support_counts.get("ready") or 0)
            else behavior_support_context.get("status") or "not_available"
        ),
        "dominant_signal": pair_difference_summary.get("dominant_signal") or "partial",
        "missing_items": [
            label
            for label, status in {
                "graph": "ready" if graph_ready else "missing_graph",
                "annotation_scope": annotation_scope.get("status") or "not_selected",
                "enzyme_capacity": capacity_status,
                "behavior": behavior_context_summary.get("status") or "not_available",
                "behavior_support": behavior_support_context.get("status") or "not_available",
            }.items()
            if status in COMPARE_MISSING_STATUSES
        ],
    }


def case_compare_guidance(
    run_id: str,
    *,
    submap_evidence_summary: dict[str, Any],
    behavior_context_summary: dict[str, Any],
    behavior_support_context: dict[str, Any],
) -> str:
    lower_run = run_id.lower()
    capacity_status = str(submap_evidence_summary.get("enzyme_capacity_status") or "not_available")
    if "shewanella_transcriptional_triggers" in lower_run:
        return (
            "Shewanella trigger paper case is an evidence-chain reproduction. Only paper evidence that maps "
            "through model GPRs is overlaid on reactions; nitrogen/glycogen regulators without GPR links remain "
            "pathway-level evidence. Bounds, fresh dFBA, and enzyme capacity are not generated."
        )
    if "shewanella" in lower_run:
        return (
            "Shewanella is the complete ecModel demonstration case. Inspect KEGG-derived submaps for kcat, "
            "flux, production, and enzyme-capacity support where reaction-level outputs are available."
        )
    if "putida" in lower_run:
        if capacity_status in {"ready", "support_ready"}:
            return (
                "P. putida has proteomics, marker annotation, and reaction-level capacity support where mapped; "
                "interpret it as GECKO-ready or capacity-supported evidence unless a full ecModel run is present."
            )
        return (
            "P. putida is an evidence-integration case here: proteomics and marker annotations are available, "
            "but full ecModel capacity outputs are not yet generated."
        )
    if "synechocystis" in lower_run:
        return (
            "Synechocystis is shown as pathway/proteomics/phosphoproteomics evidence integration. "
            "Protein-pool enzyme capacity is unavailable unless a real ecModel output is added."
        )
    if behavior_context_summary.get("status") == "condition_level_only" or behavior_support_context.get("status") == "condition_level_only":
        return "Only summary or condition-level behavior evidence is available; reaction-level panels show guarded guidance."
    return ""
