"""Pure Case Study readiness and QA-matrix helpers."""

from __future__ import annotations

from typing import Any

from api.status_semantics import case_status_label


CASE_QA_STAGE_CHECKS: dict[str, tuple[str, ...]] = {
    "input": ("run_package", "inputs"),
    "model_generator": ("variants", "kcat_priors", "enzyme_capacity"),
    "model_compare": (
        "default_pair",
        "variant_comparison",
        "annotation_groups",
        "compare_graphs",
        "reaction_diff",
        "kcat_priors",
        "enzyme_capacity",
    ),
    "analysis": ("analysis_summary",),
    "summary": ("analysis_summary",),
}


def case_check(check_id: str, label: str, status: str, **fields: Any) -> dict[str, Any]:
    guidance = fields.pop("guidance", "")
    return {
        "id": check_id,
        "label": label,
        "status": status,
        "guidance": guidance,
        **fields,
    }


def case_check_map(readiness: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = readiness.get("checks") if isinstance(readiness.get("checks"), list) else []
    return {str(row.get("id") or ""): row for row in rows if isinstance(row, dict) and row.get("id")}


def case_ladder_map(readiness: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = readiness.get("readiness_ladder") if isinstance(readiness.get("readiness_ladder"), list) else []
    return {str(row.get("stage_id") or ""): row for row in rows if isinstance(row, dict) and row.get("stage_id")}


def case_stage_next_action(stage_id: str, missing: list[str], readiness: dict[str, Any]) -> str:
    if not missing:
        return "Ready for demonstration."
    if stage_id == "input":
        return "Prepare or stage the case run package, then review Input."
    if stage_id == "model_generator":
        return "Run or refresh the lightweight workflow outputs needed for variants."
    if stage_id == "model_compare":
        return "Refresh pair summary or render the default annotation-group compare graph."
    if stage_id == "analysis":
        return "Run analysis modules or keep the case in evidence-only mode."
    if stage_id == "summary":
        actions = readiness.get("next_actions") if isinstance(readiness.get("next_actions"), list) else []
        return str(actions[0]) if actions else "Summarize missing artifacts and case caveats."
    return "Review missing case artifacts."


def build_case_readiness_stage_rows(readiness: dict[str, Any]) -> list[dict[str, Any]]:
    case = readiness.get("case") if isinstance(readiness.get("case"), dict) else {}
    checks = case_check_map(readiness)
    ladder = case_ladder_map(readiness)
    overall_status = case_status_label(readiness.get("overall_status"))
    rows: list[dict[str, Any]] = []
    for stage_id, check_ids in CASE_QA_STAGE_CHECKS.items():
        ladder_row = ladder.get(stage_id, {})
        raw_status = str(ladder_row.get("status") or "partial")
        status = case_status_label(raw_status)
        missing: list[str] = []
        artifact_paths: list[str] = []
        for check_id in check_ids:
            check = checks.get(check_id)
            if not check:
                continue
            check_status = case_status_label(check.get("status"))
            if stage_id == "model_compare" and check_id == "variant_comparison" and overall_status == "evidence-only case":
                continue
            if check_status not in {"ready", "not applicable"}:
                label = str(check.get("label") or check_id)
                guidance = str(check.get("guidance") or "").strip()
                missing.append(f"{label}: {check_status}" + (f" ({guidance})" if guidance else ""))
            path = str(check.get("path") or "").strip()
            if path:
                artifact_paths.append(path)
        if stage_id == "model_compare":
            capacity_status = case_status_label(checks.get("enzyme_capacity", {}).get("status"))
            if capacity_status in {"package-ready only", "reaction-level unavailable", "not generated", "external ecModel pending"}:
                status = "partial" if status == "ready" else status
            if overall_status == "evidence-only case" and status == "ready":
                status = "evidence-only case"
        if stage_id == "summary":
            artifact_path = str(readiness.get("artifact_path") or "").strip()
            if artifact_path:
                artifact_paths.append(artifact_path)
        rows.append(
            {
                "case_id": readiness.get("case_id", ""),
                "case_title": case.get("title", ""),
                "run_id": readiness.get("run_id", ""),
                "stage": stage_id,
                "stage_label": str(ladder_row.get("label") or stage_id.replace("_", " ").title()),
                "status": status,
                "evidence_ready": status == "ready",
                "missing_items": missing,
                "next_action": case_stage_next_action(stage_id, missing, readiness),
                "artifact_paths": sorted(set(artifact_paths)),
            }
        )
    return rows


def build_missing_case_readiness_payload(
    *,
    case_id: str,
    run_id: str,
    case: dict[str, Any],
    guidance: str,
) -> dict[str, Any]:
    return {
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
        "overall_status": "missing_artifact",
        "guidance": guidance,
        "default_pair": {
            "reference_variant_id": case.get("default_reference_variant_id", ""),
            "target_variant_id": case.get("default_target_variant_id", ""),
            "status": "missing_artifact",
        },
        "default_scope": {
            "annotation_type": case.get("default_annotation_type", ""),
            "annotation_group_id": case.get("default_annotation_group_id", ""),
            "status": "missing_artifact",
            "preferred_annotation_group_id": case.get("default_annotation_group_id", ""),
        },
        "checks": [case_check("run_package", "Run package", "missing_artifact", guidance=guidance)],
        "readiness_ladder": [
            {"stage_id": "input", "label": "Input", "status": "missing_artifact", "guidance": guidance},
            {"stage_id": "model_generator", "label": "Model Generator", "status": "missing_artifact", "guidance": "Run package is missing."},
            {"stage_id": "model_compare", "label": "Model Compare", "status": "missing_artifact", "guidance": "Run package is missing."},
            {"stage_id": "analysis", "label": "Analysis", "status": "missing_artifact", "guidance": "Run package is missing."},
            {"stage_id": "summary", "label": "Summary", "status": "missing_artifact", "guidance": "Run package is missing."},
        ],
        "missing_items": ["run_package"],
        "next_actions": ["Prepare or stage the case run package first."],
    }


def build_case_prepare_preview_actions(readiness: dict[str, Any]) -> list[dict[str, Any]]:
    actions = readiness.get("next_actions") if isinstance(readiness.get("next_actions"), list) else []
    would_run: list[dict[str, Any]] = []
    for action in actions:
        action_text = str(action)
        would_run.append(
            {
                "action": action_text,
                "dry_run": True,
                "heavy_compute": False,
                "status": "planned" if "Case is ready" not in action_text else "not_needed",
            }
        )
    return would_run


def build_case_prepare_preview_log_payload(
    *,
    case_id: str,
    run_id: str,
    readiness: dict[str, Any],
    would_run: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "run_id": run_id,
        "dry_run": True,
        "status": readiness.get("overall_status", "partial"),
        "would_run": would_run,
        "readiness_artifact": readiness.get("artifact_path", ""),
    }


def build_case_prepare_preview_response(
    *,
    case_id: str,
    readiness: dict[str, Any],
    would_run: list[dict[str, Any]],
    artifact_path: str = "",
) -> dict[str, Any]:
    response = {
        "status": "ready",
        "dry_run": True,
        "case_id": case_id,
        "readiness": readiness,
        "would_run": would_run,
        "guidance": "Prepare preview is dry-run only; it does not run MATLAB/GECKO/RAVEN or heavy solver jobs.",
    }
    if artifact_path:
        response["artifact_path"] = artifact_path
    return response


def build_case_prepare_lite_missing_package_response(
    *,
    case_id: str,
    readiness: dict[str, Any],
    actions: list[dict[str, Any]],
    guidance: str,
) -> dict[str, Any]:
    return {
        "status": "partial",
        "prepare_lite": True,
        "case_id": case_id,
        "readiness": readiness,
        "actions": [
            *actions,
            {
                "action": "resolve_run_package",
                "status": "blocked",
                "heavy_compute": False,
                "message": guidance,
            },
        ],
        "guidance": "Run package is missing; prepare-lite did not run workflow or create fake artifacts.",
    }


def build_case_prepare_lite_log_payload(
    *,
    case_id: str,
    run_id: str,
    readiness: dict[str, Any],
    actions: list[dict[str, Any]],
    qa_matrix_artifacts: dict[str, str],
) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "run_id": run_id,
        "prepare_lite": True,
        "heavy_compute": False,
        "status": readiness.get("overall_status", "partial"),
        "actions": actions,
        "readiness_artifact": readiness.get("artifact_path", ""),
        "qa_matrix_artifacts": qa_matrix_artifacts,
        "forbidden_actions": [
            "model_generation_workflow",
            "analysis_workflow",
            "MATLAB_GECKO_RAVEN",
            "online_kcat_query",
            "FVA_or_solver_extension",
            "fake_ecModel_or_capacity",
        ],
    }


def build_case_prepare_lite_response(
    *,
    case_id: str,
    readiness: dict[str, Any],
    rows: list[dict[str, Any]],
    qa_matrix_artifacts: dict[str, str],
    actions: list[dict[str, Any]],
    artifact_path: str,
) -> dict[str, Any]:
    return {
        "status": readiness.get("overall_status", "partial"),
        "prepare_lite": True,
        "case_id": case_id,
        "readiness": readiness,
        "qa_matrix": {
            "rows": rows,
            "row_count": len(rows),
            "artifact_paths": qa_matrix_artifacts,
        },
        "actions": actions,
        "artifact_path": artifact_path,
        "guidance": "Prepare-lite refreshed display artifacts only; no heavy workflow, external GECKO, online kcat, or fake capacity was run.",
    }


def build_case_qa_matrix_response(studies: list[Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "ready",
        "case_count": len([row for row in studies if isinstance(row, dict)]),
        "stage_count": len(CASE_QA_STAGE_CHECKS),
        "row_count": len(rows),
        "rows": rows,
    }
