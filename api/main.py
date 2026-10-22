"""FastAPI entrypoint for the Omics-GEM Router backend prototype."""

from __future__ import annotations

import json
import os
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from .auth import (
    authenticate_password,
    auth_status_from_request,
    clear_session_cookie,
    require_authenticated_request,
    set_session_cookie,
)
from .services import (
    ApiError,
    api_health,
    backend_environment_readiness,
    case_study_prepare_lite,
    case_study_prepare_preview,
    case_study_qa_matrix,
    case_study_readiness,
    create_archive_run_job,
    create_backend_environment_repair_job,
    create_external_dependency_deep_check_job,
    create_ml_hybrid_external_import_job,
    create_ml_hybrid_profile_job,
    create_ml_hybrid_profile_export_job,
    create_gecko_adapter_probe_job,
    create_gecko_external_run_job,
    create_report_job,
    create_restore_archived_run_job,
    create_sammi_interactive_render_job,
    create_sammi_native_export_job,
    create_sammi_visualization_job,
    create_uploaded_run_package,
    create_user_workflow_job,
    discover_run_packages,
    get_job,
    get_job_logs,
    get_archived_run_manifest,
    get_run_import_manifest,
    import_example_run_preset,
    import_run_package,
    list_archived_runs,
    list_case_studies,
    list_example_run_presets,
    list_jobs,
    list_projects,
    create_project_workspace,
    list_runs,
    create_resource_curation_workspace,
    get_resource_curation_workspace,
    list_resource_curation_workspaces,
    preview_resource_curation_workspace_mapping,
    resource_curation_preview,
    resource_curation_template,
    resource_atlas_summary,
    resource_detail,
    resource_candidate_package_preview,
    resource_model_suggestions,
    resource_search,
    resource_species,
    run_analysis_summary,
    run_annotation_groups,
    run_atlas_resource_manifest,
    stage_resource_curation_workspace_run,
    create_pipeline_job,
    reset_workspace_root,
    resolve_safe_file,
    run_gecko_adapter_preview,
    run_gecko_status,
    run_model_comparison_pair_summary,
    run_model_comparison_summary,
    run_sammi_filter_preview,
    run_sammi_native_exports,
    run_sammi_reactions,
    run_workflow_parameter_schema,
    preview_workflow_parameters,
    run_ml_hybrid_profile_comparison,
    run_ml_hybrid_profile_detail,
    run_ml_hybrid_external_result_detail,
    run_ml_hybrid_external_results,
    run_ml_hybrid_profile_exports,
    run_summary,
    run_ml_hybrid_profiles,
    run_verify_summary,
    run_variants,
    save_external_dependency_config,
    stage_resource_candidate_package,
    upload_resource_curation_workspace_file,
    set_workspace_root,
    update_workflow_ui_state,
    workflow_state_summary,
    workspace_status,
)


class SammiVisualizationRequest(BaseModel):
    variant_id: str = ""
    grouping_mode: str = "subsystem"
    overlay_source: str = "none"
    reaction_filter: str | list[str] = ""
    ml_profile_id: str = ""


class SammiInteractiveRenderRequest(BaseModel):
    variant_id: str = ""
    grouping_mode: str = "subsystem"
    overlay_source: str = "none"
    reaction_filter: str | list[str] = ""
    subsystem_filter: str | list[str] = ""
    ml_profile_id: str = ""
    top_n: int = 120
    include_currency_metabolites: bool = False


class ReportRequest(BaseModel):
    preset: str = "full_audit_report"
    active_variant_id: str | list[str] = ""
    selected_variant_ids: list[str] | str = ""


class MlHybridProfileRequest(BaseModel):
    profile_id: str = ""
    task_type: str = "auto"
    selected_variant_ids: list[str] | str = ""
    target_column: str = ""
    feature_sources: list[str] | str = ""
    benchmark_feature_sets: list[str] | str = ""
    max_features: int = 50


class MlHybridProfileExportRequest(BaseModel):
    export_format: str = "both"


class MlHybridExternalImportRequest(BaseModel):
    source_dir: str = ""
    result_format: str = "generic_tabular"
    import_id: str = ""


class BackendRepairRequest(BaseModel):
    mode: str = "minimal"
    dry_run: bool = True
    recreate_venv: bool = False
    confirm: str = ""


class AuthLoginRequest(BaseModel):
    password: str = ""


class ExternalDependencyConfigRequest(BaseModel):
    matlab_cmd: str = ""
    gecko_home: str = ""
    raven_home: str = ""
    cobra_toolbox_home: str = ""
    solver: str = ""
    pytfa_thermo_db: str = ""
    sammi_standalone_home: str = ""


class ExternalDependencyDeepCheckRequest(BaseModel):
    matlab_cmd: str = ""
    timeout_seconds: int = 120


class WorkspaceRootRequest(BaseModel):
    root: str
    create: bool = False
    persist: bool = True


class ProjectCreateRequest(BaseModel):
    name: str = "New project"
    project_id: str = ""


class RunPackageImportRequest(BaseModel):
    source_path: str
    target_run_id: str = ""
    dry_run: bool = True


class ExampleRunPresetImportRequest(BaseModel):
    preset_id: str
    target_run_id: str = ""
    dry_run: bool = True


class ResourceCandidatePackageRequest(BaseModel):
    resource_ids: list[str] | str = []
    run_id: str = ""
    package_name: str = ""
    notes: str = ""


class ResourceCurationWorkspaceRequest(BaseModel):
    resource_ids: list[str] | str = []
    workspace_id: str = ""
    title: str = ""
    notes: str = ""


class ResourceCurationWorkspaceStageRequest(BaseModel):
    run_id: str = ""


class ResourceCurationWorkspaceMappingRequest(BaseModel):
    file_name: str = ""


class RunArchiveRequest(BaseModel):
    dry_run: bool = True
    confirm_run_id: str = ""


class RunRestoreRequest(BaseModel):
    dry_run: bool = True
    confirm_run_id: str = ""


class WorkflowRunRequest(BaseModel):
    model_generation_methods: list[str] | str = ""
    analysis_modules: list[str] | str = ""
    selected_model_variant_ids: list[str] | str = ""
    report_preset: str = "full_audit_report"
    model_generation_parameters: dict[str, Any] = {}
    analysis_parameters: dict[str, Any] = {}
    gecko_adapter_parameters: dict[str, Any] = {}
    gecko_ec_model_mode: str = "full_ecModel"
    run_gecko_probe: bool = False
    run_gecko_external: bool = False


class WorkflowParameterPreviewRequest(BaseModel):
    model_generation_methods: list[str] | str = ""
    analysis_modules: list[str] | str = ""
    model_generation_parameters: dict[str, Any] = {}
    analysis_parameters: dict[str, Any] = {}


class WorkflowUiStateRequest(BaseModel):
    active_stage: str = ""
    active_module: str = ""
    active_step: str = ""
    selected_variant_id: str = ""
    selected_job_id: str = ""
    notes: str = ""


class GeckoAdapterRequest(BaseModel):
    gecko_ec_model_mode: str = "full_ecModel"
    gecko_adapter_parameters: dict[str, Any] = {}
    matlab_cmd: str = ""
    gecko_home: str = ""
    raven_home: str = ""
    solver: str = ""
    timeout_seconds: int = 300


class GeckoExternalRunRequest(BaseModel):
    matlab_cmd: str = ""
    gecko_home: str = ""
    raven_home: str = ""
    solver: str = ""
    timeout_seconds: int = 7200
    run_probe_first: bool = True
    run_full_ecmodel: bool = True
    run_condition_models: bool = True
    dry_run: bool = False


app = FastAPI(
    title="Omics-GEM Router API",
    version="0.1.0",
    description="Local API prototype for run packages, model variants, reports, and SAMMI-compatible visualizations.",
)


def _allowed_cors_origins() -> list[str]:
    defaults = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
    ]
    configured = [
        item.strip().rstrip("/")
        for item in os.environ.get("OMICS_GEM_ALLOWED_ORIGINS", "").split(",")
        if item.strip() and item.strip() != "*"
    ]
    return list(dict.fromkeys([*defaults, *configured]))


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_cors_origins(),
    allow_origin_regex=r"^http://(127\.0\.0\.1|localhost):51[0-9]{2}$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def shared_password_auth_middleware(request: Request, call_next):
    path = request.url.path
    public_api = path == "/api/health" or path.startswith("/api/auth/")
    protected_docs = path == "/openapi.json" or path.startswith("/docs") or path.startswith("/redoc")
    protected_api = path.startswith("/api/") and not public_api
    if request.method != "OPTIONS" and (protected_api or protected_docs):
        try:
            require_authenticated_request(request)
        except HTTPException as exc:
            return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    return await call_next(request)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return api_health()


@app.get("/api/auth/session")
def auth_session(request: Request) -> dict[str, Any]:
    return auth_status_from_request(request)


@app.post("/api/auth/login")
def auth_login(request_body: AuthLoginRequest, request: Request) -> Response:
    status = authenticate_password(request_body.password, request)
    token = status.pop("token", "")
    response = JSONResponse(status)
    if token:
        set_session_cookie(response, token, expires_at=int(status.get("expires_at", 0)))
    return response


@app.post("/api/auth/logout")
def auth_logout() -> Response:
    response = JSONResponse({"status": "logged_out", "authenticated": False})
    clear_session_cookie(response)
    return response


@app.get("/api/environment/backend")
def backend_environment() -> dict[str, Any]:
    return backend_environment_readiness()


@app.post("/api/environment/backend/repair")
def backend_environment_repair(request: BackendRepairRequest) -> dict[str, Any]:
    return _handle(lambda: create_backend_environment_repair_job(_model_data(request)))


@app.post("/api/environment/external-dependencies/config")
def external_dependency_config(request: ExternalDependencyConfigRequest) -> dict[str, Any]:
    return _handle(lambda: save_external_dependency_config(_model_data(request)))


@app.post("/api/environment/external-dependencies/deep-check")
def external_dependency_deep_check(request: ExternalDependencyDeepCheckRequest) -> dict[str, Any]:
    return _handle(lambda: create_external_dependency_deep_check_job(_model_data(request)))


@app.get("/api/projects")
def projects() -> dict[str, Any]:
    return {"projects": list_projects()}


@app.post("/api/projects")
def create_project(request: ProjectCreateRequest | None = None) -> dict[str, Any]:
    payload = request or ProjectCreateRequest()
    return _handle(lambda: create_project_workspace(payload.name, payload.project_id))


@app.get("/api/workspace")
def workspace() -> dict[str, Any]:
    return workspace_status()


@app.post("/api/workspace/root")
def workspace_root(request: WorkspaceRootRequest) -> dict[str, Any]:
    return _handle(lambda: set_workspace_root(request.root, create=request.create, persist=request.persist))


@app.post("/api/workspace/reset")
def workspace_reset() -> dict[str, Any]:
    return _handle(lambda: reset_workspace_root(persist=True))


@app.get("/api/workspace/run-packages")
def workspace_run_packages(root: str = Query("", description="Directory to scan for run packages."), limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    return _handle(lambda: discover_run_packages(root, limit=limit))


@app.post("/api/workspace/import-run-package")
def workspace_import_run_package(request: RunPackageImportRequest) -> dict[str, Any]:
    return _handle(
        lambda: import_run_package(
            request.source_path,
            target_run_id=request.target_run_id,
            dry_run=request.dry_run,
        )
    )


@app.post("/api/workspace/upload-run-package")
async def workspace_upload_run_package(
    run_id: str = Form(""),
    run_config_json: str = Form("{}"),
    file_roles_json: str = Form("{}"),
    model_file: UploadFile | None = File(None),
    omics_files: list[UploadFile] = File(default=[]),
    condition_files: list[UploadFile] = File(default=[]),
) -> dict[str, Any]:
    roles = _json_object_from_text(file_roles_json, "file_roles_json")
    model_entry = await _upload_entry(model_file) if model_file and model_file.filename else None
    omics_entries = [await _upload_entry(file) for file in omics_files if file and file.filename]
    condition_entries = [await _upload_entry(file) for file in condition_files if file and file.filename]
    return _handle(
        lambda: create_uploaded_run_package(
            run_id=run_id,
            run_config_json=run_config_json,
            file_roles=roles,
            model_file=model_entry,
            omics_files=omics_entries,
            condition_files=condition_entries,
        )
    )


@app.get("/api/workspace/example-presets")
def workspace_example_presets() -> dict[str, Any]:
    return _handle(list_example_run_presets)


@app.post("/api/workspace/import-example-preset")
def workspace_import_example_preset(request: ExampleRunPresetImportRequest) -> dict[str, Any]:
    return _handle(
        lambda: import_example_run_preset(
            request.preset_id,
            target_run_id=request.target_run_id,
            dry_run=request.dry_run,
        )
    )


@app.get("/api/case-studies")
def case_studies_endpoint() -> dict[str, Any]:
    return _handle(list_case_studies)


@app.get("/api/case-studies/qa-matrix")
def case_study_qa_matrix_endpoint() -> dict[str, Any]:
    return _handle(case_study_qa_matrix)


@app.get("/api/case-studies/{case_id}/readiness")
def case_study_readiness_endpoint(case_id: str) -> dict[str, Any]:
    return _handle(lambda: case_study_readiness(case_id))


@app.post("/api/case-studies/{case_id}/prepare-preview")
def case_study_prepare_preview_endpoint(case_id: str) -> dict[str, Any]:
    return _handle(lambda: case_study_prepare_preview(case_id))


@app.post("/api/case-studies/{case_id}/prepare-lite")
def case_study_prepare_lite_endpoint(case_id: str) -> dict[str, Any]:
    return _handle(lambda: case_study_prepare_lite(case_id))


@app.get("/api/resources/species")
def resources_species_endpoint() -> dict[str, Any]:
    return _handle(resource_species)


@app.get("/api/resources/search")
def resources_search_endpoint(
    organism: str = Query("", description="Organism name, strain, alias, or organism id."),
    model_id: str = Query("", description="Model id or resource id."),
    omics_type: str = Query("", description="Omics evidence type, such as proteomics or kcat."),
    source_database: str = Query("", description="Source database or local index source."),
    readiness: str = Query("", description="Readiness status filter."),
    taxonomy_group: str = Query("", description="Microbial taxonomy group filter."),
    method_support: str = Query("", description="Supported modeling method filter."),
    taxon_id: str = Query("", description="NCBI taxonomy id filter."),
    accession: str = Query("", description="External accession or model id filter."),
    q: str = Query("", description="Free-text resource search query."),
    limit: int = Query(100, ge=1, le=500, description="Maximum resources to return."),
    offset: int = Query(0, ge=0, description="Pagination offset."),
) -> dict[str, Any]:
    return _handle(
        lambda: resource_search(
            organism=organism,
            model_id=model_id,
            omics_type=omics_type,
            source_database=source_database,
            readiness=readiness,
            taxonomy_group=taxonomy_group,
            method_support=method_support,
            taxon_id=taxon_id,
            accession=accession,
            q=q,
            limit=limit,
            offset=offset,
        )
    )


@app.get("/api/resources/atlas-summary")
def resources_atlas_summary_endpoint() -> dict[str, Any]:
    return _handle(resource_atlas_summary)


@app.get("/api/resources/model/{model_id}/suggestions")
def resources_model_suggestions_endpoint(model_id: str) -> dict[str, Any]:
    return _handle(lambda: resource_model_suggestions(model_id))


@app.post("/api/resources/candidate-package/preview")
def resources_candidate_package_preview_endpoint(request: ResourceCandidatePackageRequest) -> dict[str, Any]:
    return _handle(
        lambda: resource_candidate_package_preview(
            request.resource_ids,
            run_id=request.run_id,
            package_name=request.package_name,
            notes=request.notes,
        )
    )


@app.post("/api/resources/candidate-package/stage")
def resources_candidate_package_stage_endpoint(request: ResourceCandidatePackageRequest) -> dict[str, Any]:
    return _handle(
        lambda: stage_resource_candidate_package(
            request.resource_ids,
            run_id=request.run_id,
            package_name=request.package_name,
            notes=request.notes,
        )
    )


@app.get("/api/resources/{resource_id}/curation-template")
def resources_curation_template_endpoint(resource_id: str) -> dict[str, Any]:
    return _handle(lambda: resource_curation_template(resource_id))


@app.post("/api/resources/curation-preview")
async def resources_curation_preview_endpoint(
    resource_id: str = Form(""),
    role: str = Form(""),
    file: UploadFile | None = File(None),
) -> dict[str, Any]:
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="file is required.")
    uploaded = await _upload_entry(file)
    return _handle(
        lambda: resource_curation_preview(
            resource_id,
            role,
            str(uploaded.get("filename") or "uploaded_file"),
            bytes(uploaded.get("data") or b""),
        )
    )


@app.post("/api/resources/curation-workspaces")
def resources_curation_workspace_create_endpoint(request: ResourceCurationWorkspaceRequest) -> dict[str, Any]:
    return _handle(
        lambda: create_resource_curation_workspace(
            request.resource_ids,
            workspace_id=request.workspace_id,
            title=request.title,
            notes=request.notes,
        )
    )


@app.get("/api/resources/curation-workspaces")
def resources_curation_workspaces_list_endpoint() -> dict[str, Any]:
    return _handle(list_resource_curation_workspaces)


@app.get("/api/resources/curation-workspaces/{workspace_id}")
def resources_curation_workspace_get_endpoint(workspace_id: str) -> dict[str, Any]:
    return _handle(lambda: get_resource_curation_workspace(workspace_id))


@app.post("/api/resources/curation-workspaces/{workspace_id}/curated-files")
async def resources_curation_workspace_file_endpoint(
    workspace_id: str,
    resource_id: str = Form(""),
    role: str = Form(""),
    file: UploadFile | None = File(None),
) -> dict[str, Any]:
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="file is required.")
    uploaded = await _upload_entry(file)
    return _handle(
        lambda: upload_resource_curation_workspace_file(
            workspace_id,
            resource_id=resource_id,
            role=role,
            filename=str(uploaded.get("filename") or "uploaded_file"),
            data=bytes(uploaded.get("data") or b""),
        )
    )


@app.post("/api/resources/curation-workspaces/{workspace_id}/mapping-preview")
def resources_curation_workspace_mapping_endpoint(
    workspace_id: str,
    request: ResourceCurationWorkspaceMappingRequest,
) -> dict[str, Any]:
    return _handle(lambda: preview_resource_curation_workspace_mapping(workspace_id, file_name=request.file_name))


@app.post("/api/resources/curation-workspaces/{workspace_id}/stage-run-package")
def resources_curation_workspace_stage_endpoint(workspace_id: str, request: ResourceCurationWorkspaceStageRequest) -> dict[str, Any]:
    return _handle(lambda: stage_resource_curation_workspace_run(workspace_id, run_id=request.run_id))


@app.get("/api/resources/{resource_id}")
def resources_detail_endpoint(resource_id: str) -> dict[str, Any]:
    return _handle(lambda: resource_detail(resource_id))


@app.get("/api/runs")
def runs() -> dict[str, Any]:
    return {"runs": list_runs()}


@app.get("/api/runs/archived")
def archived_runs() -> dict[str, Any]:
    return {"runs": list_archived_runs()}


@app.get("/api/runs/archived/{run_id}/archive-manifest")
def archived_run_manifest(run_id: str) -> dict[str, Any]:
    return _handle(lambda: get_archived_run_manifest(run_id))


@app.post("/api/runs/archived/{run_id}/restore")
def restore_archived_run(run_id: str, request: RunRestoreRequest) -> dict[str, Any]:
    return _handle(lambda: create_restore_archived_run_job(run_id, _model_data(request)))


@app.get("/api/runs/{run_id}/summary")
def summary(run_id: str) -> dict[str, Any]:
    return _handle(lambda: run_summary(run_id))


@app.get("/api/runs/{run_id}/atlas-resource-manifest")
def atlas_resource_manifest(run_id: str) -> dict[str, Any]:
    return _handle(lambda: run_atlas_resource_manifest(run_id))


@app.get("/api/runs/{run_id}/variants")
def variants(run_id: str) -> dict[str, Any]:
    return _handle(lambda: {"run_id": run_id, "variants": run_variants(run_id)})


@app.get("/api/runs/{run_id}/import-manifest")
def import_manifest(run_id: str) -> dict[str, Any]:
    return _handle(lambda: get_run_import_manifest(run_id))


@app.post("/api/runs/{run_id}/archive")
def archive_run(run_id: str, request: RunArchiveRequest) -> dict[str, Any]:
    return _handle(lambda: create_archive_run_job(run_id, _model_data(request)))


@app.post("/api/runs/{run_id}/pipeline")
def pipeline(run_id: str, request: WorkflowRunRequest | None = None) -> dict[str, Any]:
    return _handle(lambda: create_pipeline_job(run_id, _model_data(request) if request else {}))


@app.post("/api/runs/{run_id}/workflow/run")
def workflow_run(run_id: str, request: WorkflowRunRequest) -> dict[str, Any]:
    return _handle(lambda: create_user_workflow_job(run_id, _model_data(request)))


@app.get("/api/runs/{run_id}/workflow/state-summary")
def workflow_state_summary_endpoint(run_id: str) -> dict[str, Any]:
    return _handle(lambda: workflow_state_summary(run_id))


@app.post("/api/runs/{run_id}/workflow/state")
def workflow_state_endpoint(run_id: str, request: WorkflowUiStateRequest) -> dict[str, Any]:
    return _handle(lambda: update_workflow_ui_state(run_id, _model_data(request)))


@app.get("/api/runs/{run_id}/workflow/parameter-schema")
def workflow_parameter_schema_endpoint(run_id: str) -> dict[str, Any]:
    return _handle(lambda: run_workflow_parameter_schema(run_id))


@app.post("/api/runs/{run_id}/workflow/parameter-preview")
def workflow_parameter_preview_endpoint(run_id: str, request: WorkflowParameterPreviewRequest) -> dict[str, Any]:
    return _handle(lambda: preview_workflow_parameters(run_id, _model_data(request)))


@app.get("/api/runs/{run_id}/model-comparison/summary")
def model_comparison_summary_endpoint(run_id: str) -> dict[str, Any]:
    return _handle(lambda: run_model_comparison_summary(run_id))


@app.get("/api/runs/{run_id}/annotation-groups")
def annotation_groups_endpoint(run_id: str) -> dict[str, Any]:
    return _handle(lambda: run_annotation_groups(run_id))


@app.get("/api/runs/{run_id}/model-comparison/pair")
def model_comparison_pair_endpoint(
    run_id: str,
    reference_variant_id: str = Query("", description="Reference model variant id."),
    target_variant_id: str = Query("", description="Target model variant id."),
    grouping: str = Query("kegg_pathway", description="Network grouping mode for the comparison viewer."),
    overlay: str = Query("none", description="Overlay source for comparison viewer."),
    annotation_type: str = Query("", description="Optional annotation type used for scoped submap comparison."),
    annotation_group_id: str = Query("", description="Optional annotation group id used for scoped submap comparison."),
    reference_annotation_group_id: str = Query("", description="Optional reference-side annotation group id."),
    target_annotation_group_id: str = Query("", description="Optional target-side annotation group id."),
) -> dict[str, Any]:
    return _handle(
        lambda: run_model_comparison_pair_summary(
            run_id,
            reference_variant_id=reference_variant_id,
            target_variant_id=target_variant_id,
            grouping=grouping,
            overlay=overlay,
            annotation_type=annotation_type,
            annotation_group_id=annotation_group_id,
            reference_annotation_group_id=reference_annotation_group_id,
            target_annotation_group_id=target_annotation_group_id,
        )
    )


@app.get("/api/runs/{run_id}/analysis/summary")
def analysis_summary_endpoint(run_id: str) -> dict[str, Any]:
    return _handle(lambda: run_analysis_summary(run_id))


@app.get("/api/runs/{run_id}/verify/summary")
def verify_summary_endpoint(run_id: str) -> dict[str, Any]:
    return _handle(lambda: run_verify_summary(run_id))


@app.get("/api/runs/{run_id}/gecko/status")
def gecko_status(run_id: str) -> dict[str, Any]:
    return _handle(lambda: run_gecko_status(run_id))


@app.post("/api/runs/{run_id}/gecko/adapter-preview")
def gecko_adapter_preview(run_id: str, request: GeckoAdapterRequest) -> dict[str, Any]:
    return _handle(lambda: run_gecko_adapter_preview(run_id, _model_data(request)))


@app.post("/api/runs/{run_id}/gecko/adapter-probe")
def gecko_adapter_probe(run_id: str, request: GeckoAdapterRequest) -> dict[str, Any]:
    return _handle(lambda: create_gecko_adapter_probe_job(run_id, _model_data(request)))


@app.post("/api/runs/{run_id}/gecko/external-run")
def gecko_external_run(run_id: str, request: GeckoExternalRunRequest) -> dict[str, Any]:
    return _handle(lambda: create_gecko_external_run_job(run_id, _model_data(request)))


@app.post("/api/runs/{run_id}/visualizations/sammi")
def sammi_visualization(run_id: str, request: SammiVisualizationRequest) -> dict[str, Any]:
    return _handle(lambda: create_sammi_visualization_job(run_id, _model_data(request)))


@app.get("/api/runs/{run_id}/visualizations/reactions")
def sammi_reactions(
    run_id: str,
    variant_id: str = Query("", description="Model variant id."),
    query: str = Query("", description="Reaction id/name/subsystem search text."),
    limit: int = Query(50, ge=1, le=500),
) -> dict[str, Any]:
    return _handle(lambda: run_sammi_reactions(run_id, variant_id=variant_id, query=query, limit=limit))


@app.post("/api/runs/{run_id}/visualizations/filter-preview")
def sammi_filter_preview(run_id: str, request: SammiInteractiveRenderRequest) -> dict[str, Any]:
    return _handle(lambda: run_sammi_filter_preview(run_id, _model_data(request)))


@app.post("/api/runs/{run_id}/visualizations/interactive-render")
def sammi_interactive_render(run_id: str, request: SammiInteractiveRenderRequest) -> dict[str, Any]:
    return _handle(lambda: create_sammi_interactive_render_job(run_id, _model_data(request)))


@app.post("/api/runs/{run_id}/visualizations/sammi-native-export")
def sammi_native_export(run_id: str, request: SammiInteractiveRenderRequest) -> dict[str, Any]:
    return _handle(lambda: create_sammi_native_export_job(run_id, _model_data(request)))


@app.get("/api/runs/{run_id}/visualizations/sammi-native-exports")
def sammi_native_exports(
    run_id: str,
    variant_id: str = Query("", description="Optional model variant id filter."),
) -> dict[str, Any]:
    return _handle(lambda: run_sammi_native_exports(run_id, variant_id=variant_id))


@app.post("/api/runs/{run_id}/reports")
def reports(run_id: str, request: ReportRequest) -> dict[str, Any]:
    return _handle(lambda: create_report_job(run_id, _model_data(request)))


@app.get("/api/runs/{run_id}/ml-hybrid/profiles")
def ml_hybrid_profiles(run_id: str) -> dict[str, Any]:
    return _handle(lambda: {"run_id": run_id, "profiles": run_ml_hybrid_profiles(run_id)})


@app.get("/api/runs/{run_id}/ml-hybrid/profile-comparison")
def ml_hybrid_profile_comparison(run_id: str) -> dict[str, Any]:
    return _handle(lambda: {"run_id": run_id, **run_ml_hybrid_profile_comparison(run_id)})


@app.get("/api/runs/{run_id}/ml-hybrid/profiles/{profile_id}")
def ml_hybrid_profile_detail(run_id: str, profile_id: str) -> dict[str, Any]:
    return _handle(lambda: {"run_id": run_id, **run_ml_hybrid_profile_detail(run_id, profile_id)})


@app.get("/api/runs/{run_id}/ml-hybrid/profiles/{profile_id}/exports")
def ml_hybrid_profile_exports(run_id: str, profile_id: str) -> dict[str, Any]:
    return _handle(lambda: {"run_id": run_id, **run_ml_hybrid_profile_exports(run_id, profile_id)})


@app.post("/api/runs/{run_id}/ml-hybrid/profiles/{profile_id}/export")
def ml_hybrid_profile_export(run_id: str, profile_id: str, request: MlHybridProfileExportRequest) -> dict[str, Any]:
    return _handle(lambda: create_ml_hybrid_profile_export_job(run_id, profile_id, _model_data(request)))


@app.get("/api/runs/{run_id}/ml-hybrid/profiles/{profile_id}/external-results")
def ml_hybrid_external_results(run_id: str, profile_id: str) -> dict[str, Any]:
    return _handle(lambda: {"run_id": run_id, **run_ml_hybrid_external_results(run_id, profile_id)})


@app.get("/api/runs/{run_id}/ml-hybrid/profiles/{profile_id}/external-results/{import_id}")
def ml_hybrid_external_result_detail(run_id: str, profile_id: str, import_id: str) -> dict[str, Any]:
    return _handle(lambda: {"run_id": run_id, **run_ml_hybrid_external_result_detail(run_id, profile_id, import_id)})


@app.post("/api/runs/{run_id}/ml-hybrid/profiles/{profile_id}/external-results")
def ml_hybrid_external_import(run_id: str, profile_id: str, request: MlHybridExternalImportRequest) -> dict[str, Any]:
    return _handle(lambda: create_ml_hybrid_external_import_job(run_id, profile_id, _model_data(request)))


@app.post("/api/runs/{run_id}/ml-hybrid/profiles")
def ml_hybrid_profile(run_id: str, request: MlHybridProfileRequest) -> dict[str, Any]:
    return _handle(lambda: create_ml_hybrid_profile_job(run_id, _model_data(request)))


@app.get("/api/jobs/{job_id}")
def job(job_id: str) -> dict[str, Any]:
    return _handle(lambda: get_job(job_id))


@app.get("/api/jobs")
def jobs(job_type: str = Query("", description="Optional job_type filter."), limit: int = Query(20, ge=1, le=200)) -> dict[str, Any]:
    return {"jobs": list_jobs(job_type=job_type, limit=limit)}


@app.get("/api/jobs/{job_id}/logs")
def job_logs(job_id: str) -> dict[str, str]:
    return _handle(lambda: get_job_logs(job_id))


@app.get("/api/files", response_model=None)
def files(
    path: str = Query(..., description="Workspace-local file path to download."),
    optional: bool = Query(False, description="Return a controlled empty response when an optional evidence file is missing."),
) -> Response:
    try:
        resolved = resolve_safe_file(path)
    except ApiError as exc:
        if optional and exc.status_code == 404:
            return JSONResponse(
                {
                    "status": "optional_missing",
                    "path": path,
                    "rows": [],
                    "message": "Optional evidence file was not found.",
                }
            )
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return FileResponse(str(resolved), filename=resolved.name)


def _handle(callback):
    try:
        return callback()
    except ApiError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def _model_data(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


async def _upload_entry(file: UploadFile) -> dict[str, Any]:
    return {
        "filename": file.filename or "uploaded_file",
        "content_type": file.content_type or "",
        "data": await file.read(),
    }


def _json_object_from_text(text: str, field_name: str) -> dict[str, Any]:
    try:
        value = json.loads(text or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail=f"{field_name} must be a JSON object.")
    return value
