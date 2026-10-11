"""Deep Resource Curation Workspace lifecycle module.

The public interface deliberately contains only create, query, and execute.
HTTP response handling and service aggregation remain outside this module.
Filesystem substitution is an internal seam configured with local roots.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeAlias, overload
from uuid import uuid4

from api.file_artifact_helpers import is_relative_to_path, safe_relative_path
from api.resource_atlas_helpers import suggested_methods_for_resource_set
from api.resource_curation_helpers import curation_target_role, preview_resource_curation_file
from api.run_package_helpers import next_available_run_id, sanitize_run_id
from omics_router.config import to_yaml
from omics_router.constraints import parse_sbml_index
from omics_router.upload_workflow import UploadFilePayload, UserRunPackage, stage_user_run_package
from omics_router.validators import EXPECTED_COLUMNS, inspect_model_filename, inspect_table_file


ResourceRow: TypeAlias = dict[str, Any]
LoadResources: TypeAlias = Callable[[list[str]], tuple[list[ResourceRow], list[str]]]


@dataclass(frozen=True, slots=True)
class ResourceCurationWorkspaceConfig:
    app_root: Path
    workspace_root: Path
    curation_root: Path
    user_runs_root: Path


@dataclass(frozen=True, slots=True)
class CreateWorkspace:
    resource_ids: tuple[str, ...]
    workspace_id: str = ""
    title: str = ""
    notes: str = ""


@dataclass(frozen=True, slots=True)
class GetWorkspace:
    workspace_id: str


@dataclass(frozen=True, slots=True)
class ListWorkspaces:
    pass


@dataclass(frozen=True, slots=True)
class AddCuratedFile:
    resource_id: str
    role: str
    filename: str
    data: bytes


@dataclass(frozen=True, slots=True)
class PreviewMapping:
    file_name: str = ""


@dataclass(frozen=True, slots=True)
class StageRunPackage:
    run_id: str = ""


WorkspaceQuery: TypeAlias = GetWorkspace | ListWorkspaces
WorkspaceCommand: TypeAlias = AddCuratedFile | PreviewMapping | StageRunPackage


class ResourceCurationWorkspaceError(Exception):
    """Structured domain error mapped to ApiError by the compatibility adapter."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class ResourceCurationWorkspaces:
    """Own Resource Curation Workspace state, mapping, and staging semantics."""

    def __init__(
        self,
        config: ResourceCurationWorkspaceConfig,
        *,
        load_resources: LoadResources,
    ) -> None:
        self._config = ResourceCurationWorkspaceConfig(
            app_root=Path(config.app_root).resolve(),
            workspace_root=Path(config.workspace_root).resolve(),
            curation_root=Path(config.curation_root).resolve(),
            user_runs_root=Path(config.user_runs_root).resolve(),
        )
        self._load_resources = load_resources

    def create(self, command: CreateWorkspace) -> dict[str, Any]:
        selected_ids = _normalize_resource_id_list(command.resource_ids)
        resources, missing_ids = self._load_resources(selected_ids)
        resources = [dict(row) for row in resources if isinstance(row, dict)]
        model_candidates = [row for row in resources if row.get("resource_kind") == "model"]
        workspace_id = self._workspace_id(command.workspace_id or command.title or "atlas_curation_workspace", reserve=True)
        workspace_candidate = self._config.curation_root / workspace_id
        if workspace_candidate.is_symlink():
            raise ResourceCurationWorkspaceError(409, f"Curation workspace path is already reserved: {workspace_id}")
        workspace_dir = workspace_candidate.resolve(strict=False)
        if not is_relative_to_path(workspace_dir, self._config.curation_root):
            raise ResourceCurationWorkspaceError(403, "Curation workspace path is outside the active workspace.")
        if workspace_dir.exists():
            raise ResourceCurationWorkspaceError(409, f"Curation workspace already exists: {workspace_id}")
        creating_dir = self._config.curation_root / f".{workspace_id}.{uuid4().hex}.creating"
        creating_dir.mkdir(exist_ok=False)
        try:
            (creating_dir / "curated_files").mkdir(exist_ok=False)
            manifest = self._workspace_manifest(
                workspace_id=workspace_id,
                resources=resources,
                missing_ids=missing_ids,
                title=command.title,
                notes=command.notes,
                curated_files=[],
                status="draft",
            )
            _write_json(
                creating_dir / "curation_workspace.json",
                manifest,
                allowed_root=creating_dir,
            )
            _write_json(
                creating_dir / "curated_file_manifest.json",
                {"workspace_id": workspace_id, "files": []},
                allowed_root=creating_dir,
            )
            try:
                creating_dir.replace(workspace_candidate)
            except OSError as exc:
                if workspace_candidate.exists() or workspace_candidate.is_symlink():
                    raise ResourceCurationWorkspaceError(
                        409,
                        f"Curation workspace path was reserved concurrently: {workspace_id}",
                    ) from exc
                raise
        finally:
            _remove_owned_tree(creating_dir, self._config.curation_root)
        return {
            "status": "ready" if resources and not missing_ids else "partial",
            "workspace_id": workspace_id,
            "workspace_dir": str(workspace_dir),
            "manifest": manifest,
            "resources": resources,
            "primary_model": model_candidates[0] if len(model_candidates) == 1 else None,
            "curated_files": [],
            "missing_resource_ids": missing_ids,
            "guidance": manifest.get("guidance", ""),
        }

    @overload
    def query(self, query: GetWorkspace) -> dict[str, Any]: ...

    @overload
    def query(self, query: ListWorkspaces) -> dict[str, Any]: ...

    def query(self, query: WorkspaceQuery) -> dict[str, Any]:
        if isinstance(query, ListWorkspaces):
            return self._list_workspaces()
        if isinstance(query, GetWorkspace):
            workspace_dir = self._resolve_workspace(query.workspace_id)
            manifest = self._read_workspace_manifest(workspace_dir)
            files = self._workspace_files(workspace_dir)
            manifest["curated_files"] = files
            response = self._workspace_response(workspace_dir, manifest, files)
            _write_json(workspace_dir / "curation_workspace.json", manifest, allowed_root=workspace_dir)
            return response
        raise TypeError(f"Unsupported workspace query: {type(query).__name__}")

    @overload
    def execute(self, workspace_id: str, command: AddCuratedFile) -> dict[str, Any]: ...

    @overload
    def execute(self, workspace_id: str, command: PreviewMapping) -> dict[str, Any]: ...

    @overload
    def execute(self, workspace_id: str, command: StageRunPackage) -> dict[str, Any]: ...

    def execute(self, workspace_id: str, command: WorkspaceCommand) -> dict[str, Any]:
        if isinstance(command, AddCuratedFile):
            return self._add_curated_file(workspace_id, command)
        if isinstance(command, PreviewMapping):
            return self._preview_mapping(workspace_id, command)
        if isinstance(command, StageRunPackage):
            return self._stage_run_package(workspace_id, command)
        raise TypeError(f"Unsupported workspace command: {type(command).__name__}")

    def _list_workspaces(self) -> dict[str, Any]:
        self._config.curation_root.mkdir(parents=True, exist_ok=True)
        curation_root = self._config.curation_root.resolve()
        workspace_paths: list[Path] = []
        for candidate in curation_root.iterdir():
            if candidate.name.startswith("."):
                continue
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if not is_relative_to_path(resolved, curation_root) or not resolved.is_dir():
                continue
            workspace_paths.append(resolved)
        rows: list[dict[str, Any]] = []
        for path in sorted(
            workspace_paths,
            key=lambda item: item.stat().st_mtime if item.exists() else 0,
            reverse=True,
        ):
            try:
                manifest = self._read_workspace_manifest(path)
                curated_file_count = len(manifest.get("curated_files") or [])
            except (OSError, json.JSONDecodeError, ResourceCurationWorkspaceError):
                continue
            if not manifest:
                continue
            rows.append(
                {
                    "workspace_id": manifest.get("workspace_id", path.name),
                    "title": manifest.get("title", ""),
                    "status": manifest.get("status", "draft"),
                    "resource_count": len(manifest.get("resources") or []),
                    "curated_file_count": curated_file_count,
                    "updated_at": manifest.get("updated_at", manifest.get("created_at", "")),
                    "workspace_dir": str(path),
                }
            )
        return {"status": "ready", "count": len(rows), "workspaces": rows}

    def _add_curated_file(self, workspace_id: str, command: AddCuratedFile) -> dict[str, Any]:
        workspace_dir = self._resolve_workspace(workspace_id)
        manifest = self._read_workspace_manifest(workspace_dir)
        resource = _workspace_resource(manifest, command.resource_id)
        if not resource:
            raise ResourceCurationWorkspaceError(
                404,
                f"Resource is not part of this curation workspace: {command.resource_id}",
            )
        if not command.filename:
            raise ResourceCurationWorkspaceError(400, "file is required.")
        role = command.role.strip() or curation_target_role(resource, str(resource.get("resource_kind") or ""))
        preview = preview_resource_curation_file(
            resource_id=command.resource_id,
            resource_kind=str(resource.get("resource_kind") or ""),
            resource=resource,
            requested_role=role,
            filename=command.filename,
            data=command.data,
        )
        safe_name = _safe_upload_filename(command.filename or f"{command.resource_id}_{role}.csv")
        content_sha256 = hashlib.sha256(command.data).hexdigest()
        safe_path = Path(safe_name)
        version_name = f"{safe_path.stem}.{content_sha256[:16]}{safe_path.suffix}"
        version_path = workspace_dir / "curated_files" / ".versions" / version_name
        compatibility_path = workspace_dir / "curated_files" / safe_name
        version_existed_before = version_path.exists()
        _write_bytes(version_path, command.data, allowed_root=workspace_dir)
        original_file_manifest = _read_json_object(
            workspace_dir / "curated_file_manifest.json",
            allowed_root=workspace_dir,
        )
        compatibility_existed = (
            compatibility_path.is_file()
            and not compatibility_path.is_symlink()
            and is_relative_to_path(compatibility_path.resolve(), workspace_dir.resolve())
        )
        compatibility_bytes = compatibility_path.read_bytes() if compatibility_existed else None
        record = {
            "file_name": safe_name,
            "original_file_name": command.filename,
            "path": str(compatibility_path),
            "relative_path": safe_relative_path(workspace_dir, compatibility_path),
            "_content_path": str(version_path),
            "_content_relative_path": safe_relative_path(workspace_dir, version_path),
            "_content_sha256": content_sha256,
            "resource_id": command.resource_id,
            "resource_title": resource.get("title") or resource.get("model_name") or command.resource_id,
            "source_database": resource.get("source_database", ""),
            "connector_source": resource.get("connector_source", ""),
            "accession": resource.get("accession", ""),
            "role": role,
            "status": "preview_ready" if preview.get("status") == "ready" else "preview_partial",
            "preview_status": preview.get("status", "partial"),
            "readiness_preview": preview.get("readiness_preview", ""),
            "missing_columns": preview.get("missing_columns", []),
            "warnings": preview.get("warnings", []),
            "suggested_methods": preview.get("suggested_methods", []),
            "updated_at": _local_timestamp(),
        }
        files = [row for row in self._workspace_files(workspace_dir) if row.get("file_name") != safe_name]
        files.append(record)
        compatibility_written = False
        file_manifest_committed = False
        try:
            _write_bytes(compatibility_path, command.data, allowed_root=workspace_dir)
            compatibility_written = True
            self._write_file_manifest(workspace_dir, workspace_id, files)
            file_manifest_committed = True
            manifest["curated_files"] = files
            manifest["status"] = (
                "ready_with_curated_files"
                if any(row.get("status") == "preview_ready" for row in files)
                else "draft"
            )
            manifest.pop("staged_run_id", None)
            manifest.pop("staged_curated_files_revision", None)
            manifest["curated_files_revision"] = self._curated_files_revision(workspace_dir, files)
            manifest.pop("mapping_preview", None)
            manifest["mapping_preview_status"] = ""
            manifest["mapping_invalidated_at"] = _local_timestamp()
            manifest["updated_at"] = _local_timestamp()
            manifest["suggested_methods"] = self._workspace_suggested_methods(manifest, files)
            _write_json(workspace_dir / "curation_workspace.json", manifest, allowed_root=workspace_dir)
        except Exception as exc:
            rollback_errors: list[str] = []
            if file_manifest_committed:
                try:
                    _write_json(
                        workspace_dir / "curated_file_manifest.json",
                        original_file_manifest,
                        allowed_root=workspace_dir,
                    )
                except Exception as rollback_exc:
                    rollback_errors.append(f"file manifest: {rollback_exc}")
            if compatibility_written:
                try:
                    _restore_compatibility_file(
                        compatibility_path,
                        compatibility_bytes,
                        allowed_root=workspace_dir,
                    )
                except Exception as rollback_exc:
                    rollback_errors.append(f"compatibility file: {rollback_exc}")
            if not rollback_errors and not version_existed_before:
                try:
                    current_file_manifest = _read_json_object(
                        workspace_dir / "curated_file_manifest.json",
                        allowed_root=workspace_dir,
                    )
                    referenced_paths = {
                        str(row.get("_content_path") or "")
                        for row in (current_file_manifest.get("files") or [])
                        if isinstance(row, dict)
                    }
                    if str(version_path) not in referenced_paths:
                        _remove_owned_file(version_path, workspace_dir)
                except Exception as rollback_exc:
                    rollback_errors.append(f"unreferenced version: {rollback_exc}")
            if rollback_errors:
                raise ResourceCurationWorkspaceError(
                    500,
                    "Curated file commit failed and rollback was incomplete: " + "; ".join(rollback_errors),
                ) from exc
            raise
        return {
            **self._workspace_response(workspace_dir, manifest, files),
            "uploaded_file": _public_curated_file_record(record),
            "preview": preview,
        }

    def _preview_mapping(self, workspace_id: str, command: PreviewMapping) -> dict[str, Any]:
        workspace_dir = self._resolve_workspace(workspace_id)
        manifest = self._read_workspace_manifest(workspace_dir)
        resources = [row for row in manifest.get("resources") or [] if isinstance(row, dict)]
        model_candidates = [row for row in resources if row.get("resource_kind") == "model"]
        files = self._workspace_files(workspace_dir)
        if len(model_candidates) != 1:
            return self._write_partial_mapping(
                workspace_dir,
                workspace_id,
                "Mapping preview requires exactly one primary model resource in the curation workspace.",
            )
        model_path = self._resource_local_file(model_candidates[0])
        if not model_path:
            return self._write_partial_mapping(
                workspace_dir,
                workspace_id,
                "Primary model does not point to a local model file.",
            )
        if model_path.suffix.lower() not in {".xml", ".sbml"}:
            return self._write_partial_mapping(
                workspace_dir,
                workspace_id,
                f"Mapping preview currently supports SBML/XML models; got {model_path.suffix or 'unknown'} model format.",
                model_summary={"path": str(model_path)},
                input_revision=self._mapping_input_revision(workspace_dir, model_path, files),
            )
        try:
            model_index = parse_sbml_index(model_path)
        except Exception as exc:  # noqa: BLE001 - preserved endpoint guidance.
            return self._write_partial_mapping(
                workspace_dir,
                workspace_id,
                f"Could not parse primary model identifiers: {type(exc).__name__}: {exc}",
                model_summary={"path": str(model_path)},
                input_revision=self._mapping_input_revision(workspace_dir, model_path, files),
            )

        target_name = command.file_name.strip()
        selected_files = [
            row
            for row in files
            if row.get("status") == "preview_ready" and (not target_name or str(row.get("file_name") or "") == target_name)
        ]
        if target_name and not selected_files:
            raise ResourceCurationWorkspaceError(
                404,
                f"Preview-ready curated file not found in workspace: {target_name}",
            )
        alias_maps = self._workspace_alias_maps(workspace_dir, selected_files)
        file_summaries: list[dict[str, Any]] = []
        unmapped_rows: list[dict[str, Any]] = []
        mapping_by_file: dict[str, dict[str, Any]] = {}
        for row in selected_files:
            summary, unmapped = self._file_mapping_summary(workspace_dir, row, model_index, alias_maps)
            file_summaries.append(summary)
            unmapped_rows.extend(unmapped)
            mapping_by_file[str(row.get("file_name") or "")] = summary

        status = _mapping_status(file_summaries)
        guidance = _mapping_guidance(status, file_summaries)
        result = _mapping_result(
            workspace_id,
            status=status,
            guidance=guidance,
            model_summary=model_index.summary(),
            file_summaries=file_summaries,
            unmapped_rows=unmapped_rows,
        )
        input_revision = self._mapping_input_revision(workspace_dir, model_path, files)
        _write_mapping_artifacts(workspace_dir, result, input_revision=input_revision)
        self._update_files_with_mapping(workspace_dir, workspace_id, files, mapping_by_file)
        manifest["curated_files"] = self._workspace_files(workspace_dir)
        manifest["mapping_preview"] = result
        manifest["mapping_preview_status"] = status
        manifest["mapping_input_revision"] = input_revision
        manifest.pop("mapping_invalidated_at", None)
        manifest["updated_at"] = _local_timestamp()
        _write_json(workspace_dir / "curation_workspace.json", manifest, allowed_root=workspace_dir)
        return {
            **self._workspace_response(workspace_dir, manifest, manifest["curated_files"]),
            "mapping_preview": result,
        }

    def _write_partial_mapping(
        self,
        workspace_dir: Path,
        workspace_id: str,
        guidance: str,
        *,
        model_summary: dict[str, Any] | None = None,
        input_revision: str = "",
    ) -> dict[str, Any]:
        result = _mapping_result(
            workspace_id,
            status="partial",
            guidance=guidance,
            model_summary=model_summary or {},
            file_summaries=[],
            unmapped_rows=[],
        )
        _write_mapping_artifacts(workspace_dir, result, input_revision=input_revision)
        manifest = self._read_workspace_manifest(workspace_dir)
        manifest["mapping_preview"] = result
        manifest["mapping_preview_status"] = "partial"
        manifest["mapping_input_revision"] = input_revision
        manifest.pop("mapping_invalidated_at", None)
        manifest["updated_at"] = _local_timestamp()
        _write_json(workspace_dir / "curation_workspace.json", manifest, allowed_root=workspace_dir)
        return result

    def _stage_run_package(self, workspace_id: str, command: StageRunPackage) -> dict[str, Any]:
        workspace_dir = self._resolve_workspace(workspace_id)
        manifest = self._read_workspace_manifest(workspace_dir)
        resources = [row for row in manifest.get("resources") or [] if isinstance(row, dict)]
        model_candidates = [row for row in resources if row.get("resource_kind") == "model"]
        stageable_models = [row for row in model_candidates if self._resource_can_stage_model(row)]
        if len(model_candidates) != 1 or len(stageable_models) != 1:
            raise ResourceCurationWorkspaceError(
                400,
                "Curation workspace stage requires exactly one local primary model resource.",
            )
        files = self._workspace_files(workspace_dir)
        ready_files = [row for row in files if row.get("status") == "preview_ready"]
        if not ready_files:
            raise ResourceCurationWorkspaceError(400, "No preview-ready curated files are available for staging.")
        target_run_id = self._run_id(
            stageable_models[0],
            run_id=command.run_id,
            package_name=f"atlas_curated_{workspace_id}",
            reserve=True,
        )
        target = self._config.user_runs_root / target_run_id
        if not is_relative_to_path(target.resolve(strict=False), self._config.user_runs_root):
            raise ResourceCurationWorkspaceError(403, "Run Package target is outside user_runs.")
        if target.exists() or target.is_symlink():
            raise ResourceCurationWorkspaceError(409, f"Target run package already exists: {target}")

        model_payload = self._model_payload(stageable_models[0])
        omics_payloads: list[UploadFilePayload] = []
        condition_payloads: list[UploadFilePayload] = []
        for row in ready_files:
            payload, is_condition = self._curated_file_payload(workspace_dir, row)
            if is_condition:
                condition_payloads.append(payload)
            else:
                omics_payloads.append(payload)

        suggested_methods = self._workspace_suggested_methods(manifest, ready_files)
        model_path = self._resource_local_file(stageable_models[0])
        if not model_path:
            raise ResourceCurationWorkspaceError(400, "Primary model is no longer locally stageable.")
        mapping_input_revision = self._mapping_input_revision(workspace_dir, model_path, files)
        mapping_artifact_sources = _committed_mapping_artifact_paths(
            workspace_dir,
            strict=True,
            expected_input_revision=mapping_input_revision,
        )
        mapping_preview_path = mapping_artifact_sources.get("curation_mapping_preview.json")
        mapping_preview = _read_json_object(mapping_preview_path) if mapping_preview_path else {}
        mapping_by_file = {
            str(row.get("file_name") or ""): row
            for row in (mapping_preview.get("files") or [])
            if isinstance(row, dict)
        }
        run_config = {
            "run_id": target_run_id,
            "description": f"Created from Atlas curation workspace {workspace_id}.",
            "model_generation_methods": _run_config_model_methods(suggested_methods),
            "analysis_modules": _run_config_analysis_modules(suggested_methods),
            "run_gecko_external": False,
            "curation_workspace_id": workspace_id,
            "atlas_curated_sources": [
                {
                    "file_name": row.get("file_name", ""),
                    "resource_id": row.get("resource_id", ""),
                    "role": row.get("role", ""),
                    "source_database": row.get("source_database", ""),
                    "accession": row.get("accession", ""),
                    "readiness_preview": row.get("readiness_preview", row.get("preview_status", "")),
                    "mapping_preview": mapping_by_file.get(str(row.get("file_name") or ""), {}),
                }
                for row in ready_files
            ],
        }
        staging_base = self._config.user_runs_root / ".curation_staging"
        if staging_base.is_symlink() or not is_relative_to_path(
            staging_base.resolve(strict=False),
            self._config.user_runs_root,
        ):
            raise ResourceCurationWorkspaceError(403, "Run Package staging root is outside user_runs.")
        staging_root = staging_base / uuid4().hex
        staged_package_path = staging_root / target_run_id
        published_by_this_attempt = False
        try:
            package = stage_user_run_package(
                output_root=staging_root,
                run_config=run_config,
                model_file=model_payload,
                omics_files=omics_payloads,
                condition_files=condition_payloads,
                run_id=target_run_id,
            )
            response = self._prepare_staged_package(
                package=package,
                published_path=target,
                workspace_id=workspace_id,
                workspace_manifest=manifest,
                ready_files=ready_files,
                mapping_preview=mapping_preview,
                mapping_artifact_sources=mapping_artifact_sources,
            )
            self._publish_staged_package(staged_package_path, target)
            published_by_this_attempt = True
            manifest["status"] = "staged"
            manifest["staged_run_id"] = target_run_id
            curated_files_revision = self._curated_files_revision(workspace_dir, files)
            manifest["curated_files_revision"] = curated_files_revision
            manifest["staged_curated_files_revision"] = curated_files_revision
            manifest.pop("last_stage_failure", None)
            manifest["updated_at"] = _local_timestamp()
            _write_json(workspace_dir / "curation_workspace.json", manifest, allowed_root=workspace_dir)
            return response
        except Exception as exc:
            recovery_error = self._recover_failed_stage(
                workspace_dir=workspace_dir,
                workspace_manifest=manifest,
                run_id=target_run_id,
                staged_package_path=staged_package_path,
                published_path=target,
                published_by_this_attempt=published_by_this_attempt,
                error=exc,
            )
            if recovery_error:
                raise ResourceCurationWorkspaceError(
                    500,
                    f"Run Package staging failed and automatic recovery was incomplete: {recovery_error}",
                ) from exc
            raise
        finally:
            _remove_empty_directory(staging_root)
            _remove_empty_directory(staging_root.parent)

    def _prepare_staged_package(
        self,
        *,
        package: UserRunPackage,
        published_path: Path,
        workspace_id: str,
        workspace_manifest: dict[str, Any],
        ready_files: list[dict[str, Any]],
        mapping_preview: dict[str, Any],
        mapping_artifact_sources: dict[str, Path],
    ) -> dict[str, Any]:
        package_path = Path(package.output_dir).resolve()
        if not is_relative_to_path(package_path, self._config.user_runs_root / ".curation_staging"):
            raise ResourceCurationWorkspaceError(500, "Staged Run Package escaped its internal staging root.")

        rewritten_run_config = _replace_path_prefixes(
            _read_json_object(package_path / "run_config.json"),
            package_path,
            published_path,
        )
        if not isinstance(rewritten_run_config, dict):
            raise ResourceCurationWorkspaceError(500, "Staged Run Package config is invalid.")
        _write_json(package_path / "run_config.json", rewritten_run_config, allowed_root=package_path)
        _write_text(
            package_path / "run_config.yaml",
            to_yaml(rewritten_run_config),
            allowed_root=package_path,
        )
        rewritten_input_rows = _replace_path_prefixes(
            _read_csv_rows(package_path / "input_file_map.csv"),
            package_path,
            published_path,
        )
        if not isinstance(rewritten_input_rows, list):
            raise ResourceCurationWorkspaceError(500, "Staged Run Package input map is invalid.")
        _write_csv(
            package_path / "input_file_map.csv",
            [row for row in rewritten_input_rows if isinstance(row, dict)],
            allowed_root=package_path,
        )

        mapping_artifacts: dict[str, str] = {}
        for source_name, source_path in mapping_artifact_sources.items():
            target_path = package_path / source_name
            _write_bytes(target_path, source_path.read_bytes(), allowed_root=package_path)
            mapping_artifacts[source_name.rsplit(".", 1)[0]] = str(published_path / source_name)
        staged_manifest = self._stage_manifest(package.run_id, workspace_id, workspace_manifest, ready_files)
        staged_manifest["files"] = {
            "atlas_resource_manifest": str(published_path / "atlas_resource_manifest.json"),
            "atlas_curation_workspace_manifest": str(published_path / "atlas_curation_workspace_manifest.json"),
            **mapping_artifacts,
        }
        if mapping_preview:
            staged_manifest["mapping_preview"] = mapping_preview
        _write_json(package_path / "atlas_resource_manifest.json", staged_manifest, allowed_root=package_path)
        _write_json(
            package_path / "atlas_curation_workspace_manifest.json",
            staged_manifest,
            allowed_root=package_path,
        )
        manifest_payload = _replace_path_prefixes(
            _read_json_object(package_path / "upload_manifest.json"),
            package_path,
            published_path,
        )
        if not isinstance(manifest_payload, dict):
            raise ResourceCurationWorkspaceError(500, "Staged Run Package manifest is invalid.")
        manifest_payload.setdefault("files", {})
        if isinstance(manifest_payload["files"], dict):
            manifest_payload["files"]["atlas_resource_manifest"] = str(
                published_path / "atlas_resource_manifest.json"
            )
            manifest_payload["files"]["atlas_curation_workspace_manifest"] = str(
                published_path / "atlas_curation_workspace_manifest.json"
            )
            manifest_payload["files"].update(mapping_artifacts)
        manifest_payload["atlas_curation_workspace"] = {
            "workspace_id": workspace_id,
            "curated_file_count": len(ready_files),
            "status": "staged",
        }
        _write_json(package_path / "upload_manifest.json", manifest_payload, allowed_root=package_path)
        response_files = _replace_path_prefixes(package.files, package_path, published_path)
        response_input_rows = _replace_path_prefixes(package.input_rows, package_path, published_path)
        return {
            "status": package.status,
            "message": package.message,
            "workspace_id": workspace_id,
            "run_id": package.run_id,
            "output_dir": str(published_path),
            "files": {
                **(response_files if isinstance(response_files, dict) else {}),
                "atlas_resource_manifest": str(published_path / "atlas_resource_manifest.json"),
                "atlas_curation_workspace_manifest": str(published_path / "atlas_curation_workspace_manifest.json"),
                **mapping_artifacts,
            },
            "input_rows": response_input_rows if isinstance(response_input_rows, list) else [],
            "manifest": manifest_payload,
            "atlas_curation_workspace_manifest": staged_manifest,
            "mapping_preview": mapping_preview or {},
        }

    def _publish_staged_package(self, staged_path: Path, published_path: Path) -> None:
        if staged_path.is_symlink():
            raise ResourceCurationWorkspaceError(500, "Internal Run Package staging directory is invalid.")
        staged = staged_path.resolve()
        staging_root = (self._config.user_runs_root / ".curation_staging").resolve()
        if not staged.is_dir() or not is_relative_to_path(staged, staging_root):
            raise ResourceCurationWorkspaceError(500, "Internal Run Package staging directory is invalid.")
        if published_path.exists() or published_path.is_symlink():
            raise ResourceCurationWorkspaceError(409, f"Target run package already exists: {published_path}")
        published_path.parent.mkdir(parents=True, exist_ok=True)
        staged.replace(published_path)

    def _recover_failed_stage(
        self,
        *,
        workspace_dir: Path,
        workspace_manifest: dict[str, Any],
        run_id: str,
        staged_package_path: Path,
        published_path: Path,
        published_by_this_attempt: bool,
        error: Exception,
    ) -> str:
        recovery_path = ""
        recovery_error = ""
        try:
            candidate = published_path if published_by_this_attempt else staged_package_path
            if candidate.exists():
                resolved = candidate.resolve()
                allowed = (
                    self._config.user_runs_root
                    if candidate == published_path
                    else self._config.user_runs_root / ".curation_staging"
                )
                if not is_relative_to_path(resolved, allowed.resolve()) or candidate.is_symlink():
                    raise ResourceCurationWorkspaceError(403, "Failed Run Package escaped its recovery boundary.")
                recovery_base = self._config.user_runs_root / ".curation_failed"
                if recovery_base.is_symlink() or not is_relative_to_path(
                    recovery_base.resolve(strict=False),
                    self._config.user_runs_root,
                ):
                    raise ResourceCurationWorkspaceError(403, "Run Package recovery root is outside user_runs.")
                recovery_root = recovery_base / workspace_dir.name
                if recovery_root.is_symlink():
                    raise ResourceCurationWorkspaceError(403, "Run Package recovery workspace is invalid.")
                recovery_root.mkdir(parents=True, exist_ok=True)
                if not is_relative_to_path(recovery_root.resolve(), self._config.user_runs_root):
                    raise ResourceCurationWorkspaceError(403, "Run Package recovery root is outside user_runs.")
                recovered = recovery_root / f"{run_id}_{uuid4().hex[:8]}"
                candidate.replace(recovered)
                recovery_path = str(recovered)
        except Exception as recovery_exc:
            recovery_error = f"{type(recovery_exc).__name__}: {recovery_exc}"

        try:
            files = self._workspace_files(workspace_dir)
            workspace_manifest["status"] = (
                "ready_with_curated_files"
                if any(row.get("status") == "preview_ready" for row in files)
                else "draft"
            )
            workspace_manifest.pop("staged_run_id", None)
            workspace_manifest.pop("staged_curated_files_revision", None)
            workspace_manifest["last_stage_failure"] = {
                "run_id": run_id,
                "failed_at": _local_timestamp(),
                "error_type": type(error).__name__,
                "detail": str(error)[:500],
                "recovery_path": recovery_path,
                "recovery_error": recovery_error,
            }
            workspace_manifest["updated_at"] = _local_timestamp()
            _write_json(
                workspace_dir / "curation_workspace.json",
                workspace_manifest,
                allowed_root=workspace_dir,
            )
        except Exception as manifest_exc:
            manifest_error = f"{type(manifest_exc).__name__}: {manifest_exc}"
            recovery_error = f"{recovery_error}; {manifest_error}" if recovery_error else manifest_error
        return recovery_error

    def _workspace_id(self, value: str, *, reserve: bool = False) -> str:
        sanitized = sanitize_run_id(value.strip() or "atlas_curation_workspace") or "atlas_curation_workspace"
        if reserve:
            self._config.curation_root.mkdir(parents=True, exist_ok=True)
            candidate = sanitized
            index = 2
            while (self._config.curation_root / candidate).exists() or (
                self._config.curation_root / candidate
            ).is_symlink():
                candidate = f"{sanitized}_{index}"
                index += 1
            return candidate
        return sanitized

    def _resolve_workspace(self, workspace_id: str) -> Path:
        normalized = self._workspace_id(workspace_id)
        if not normalized or normalized != workspace_id:
            raise ResourceCurationWorkspaceError(
                400,
                "workspace_id may contain only letters, numbers, underscore, and dash.",
            )
        workspace_dir = (self._config.curation_root / normalized).resolve()
        if not is_relative_to_path(workspace_dir, self._config.curation_root):
            raise ResourceCurationWorkspaceError(403, "Curation workspace path is outside the active workspace.")
        if not workspace_dir.exists() or not workspace_dir.is_dir():
            raise ResourceCurationWorkspaceError(404, f"Curation workspace not found: {workspace_id}")
        return workspace_dir

    def _workspace_manifest(
        self,
        *,
        workspace_id: str,
        resources: list[ResourceRow],
        missing_ids: list[str],
        title: str,
        notes: str,
        curated_files: list[dict[str, Any]],
        status: str,
    ) -> dict[str, Any]:
        model_candidates = [row for row in resources if row.get("resource_kind") == "model"]
        stageable_models = [row for row in model_candidates if self._resource_can_stage_model(row)]
        needs_curation = [
            row
            for row in resources
            if row.get("resource_kind") != "model"
            and str(row.get("readiness") or row.get("import_readiness") or "") != "ready_for_import"
        ]
        guidance: list[str] = []
        if missing_ids:
            guidance.append(f"Unknown resource ids: {', '.join(missing_ids)}.")
        if len(model_candidates) != 1:
            guidance.append("Select exactly one primary model before staging a Run Package.")
        elif not stageable_models:
            guidance.append("The selected model is metadata-only and cannot be staged as a local model file.")
        if needs_curation:
            guidance.append("Non-ready resources can be curated here; their original Atlas readiness remains unchanged.")
        if not curated_files:
            guidance.append("Upload curated CSV files and run preview before staging.")
        now = _local_timestamp()
        return {
            "schema_version": "0.1.0",
            "workspace_id": workspace_id,
            "title": title or workspace_id,
            "notes": notes,
            "status": status,
            "created_at": now,
            "updated_at": now,
            "resource_ids": [str(row.get("resource_id") or "") for row in resources],
            "missing_resource_ids": missing_ids,
            "primary_model_resource_id": stageable_models[0].get("resource_id", "") if len(stageable_models) == 1 else "",
            "resources": [_workspace_resource_record(row) for row in resources],
            "curated_files": curated_files,
            "suggested_methods": self._workspace_suggested_methods({"resources": resources}, curated_files),
            "guidance": " ".join(guidance),
        }

    def _read_workspace_manifest(self, workspace_dir: Path) -> dict[str, Any]:
        manifest = _read_json_object(
            workspace_dir / "curation_workspace.json",
            allowed_root=workspace_dir,
        )
        if not manifest:
            raise ResourceCurationWorkspaceError(
                404,
                f"Curation workspace manifest is missing: {workspace_dir.name}",
            )
        files = self._workspace_files(workspace_dir)
        curated_files_revision = self._curated_files_revision(workspace_dir, files)
        staged_revision = str(manifest.get("staged_curated_files_revision") or "")
        if manifest.get("status") == "staged" and (not staged_revision or staged_revision == curated_files_revision):
            pass
        else:
            manifest["status"] = (
                "ready_with_curated_files"
                if any(row.get("status") == "preview_ready" for row in files)
                else "draft"
            )
            manifest.pop("staged_run_id", None)
            manifest.pop("staged_curated_files_revision", None)
        manifest["curated_files"] = files
        manifest["curated_files_revision"] = curated_files_revision
        return manifest

    def _workspace_files(self, workspace_dir: Path) -> list[dict[str, Any]]:
        payload = _read_json_object(
            workspace_dir / "curated_file_manifest.json",
            allowed_root=workspace_dir,
        )
        rows = payload.get("files", []) if isinstance(payload, dict) else []
        return [row for row in rows if isinstance(row, dict)]

    def _write_file_manifest(self, workspace_dir: Path, workspace_id: str, files: list[dict[str, Any]]) -> None:
        _write_json(
            workspace_dir / "curated_file_manifest.json",
            {
                "schema_version": "0.1.0",
                "workspace_id": workspace_id,
                "updated_at": _local_timestamp(),
                "content_revision": self._curated_files_revision(workspace_dir, files),
                "files": files,
            },
            allowed_root=workspace_dir,
        )

    def _workspace_response(
        self,
        workspace_dir: Path,
        manifest: dict[str, Any],
        files: list[dict[str, Any]],
    ) -> dict[str, Any]:
        resources = [row for row in manifest.get("resources") or [] if isinstance(row, dict)]
        primary_model_id = str(manifest.get("primary_model_resource_id") or "")
        primary_model = next(
            (row for row in resources if str(row.get("resource_id") or "") == primary_model_id),
            None,
        )
        mapping_preview: dict[str, Any] = {}
        mapping_is_current = not manifest.get("mapping_invalidated_at")
        recorded_revision = str(manifest.get("mapping_input_revision") or "")
        model_resource = next((row for row in resources if row.get("resource_kind") == "model"), None)
        if mapping_is_current and recorded_revision and model_resource:
            model_path = self._resource_local_file(model_resource)
            try:
                mapping_is_current = bool(
                    model_path
                    and self._mapping_input_revision(workspace_dir, model_path, files) == recorded_revision
                )
            except (OSError, ResourceCurationWorkspaceError):
                mapping_is_current = False
        mapping_markers_present = any(
            (workspace_dir / name).exists() or (workspace_dir / name).is_symlink()
            for name in ("curation_mapping_commit.json", "curation_mapping_transaction.json")
        )
        if mapping_is_current and mapping_markers_present:
            mapping_is_current = bool(
                _committed_mapping_artifact_paths(
                    workspace_dir,
                    strict=False,
                    expected_input_revision=recorded_revision or None,
                )
            )
        if mapping_is_current:
            mapping_preview = (
                manifest.get("mapping_preview")
                if isinstance(manifest.get("mapping_preview"), dict)
                else _read_committed_mapping_preview(
                    workspace_dir,
                    expected_input_revision=recorded_revision or None,
                )
            )
        else:
            manifest.pop("mapping_preview", None)
            manifest["mapping_preview_status"] = ""
        public_files = [_public_curated_file_record(row) for row in files]
        public_manifest = _public_workspace_manifest(manifest)
        return {
            "status": manifest.get("status", "draft"),
            "workspace_id": manifest.get("workspace_id", workspace_dir.name),
            "workspace_dir": str(workspace_dir),
            "manifest": public_manifest,
            "resources": resources,
            "primary_model": primary_model,
            "needs_curation": [
                row
                for row in resources
                if row.get("resource_kind") != "model" and str(row.get("readiness") or "") != "ready_for_import"
            ],
            "curated_files": public_files,
            "preview_ready_files": [row for row in public_files if row.get("status") == "preview_ready"],
            "suggested_methods": manifest.get("suggested_methods", []),
            "mapping_preview": mapping_preview or None,
            "mapping_preview_status": (
                manifest.get("mapping_preview_status") or (mapping_preview or {}).get("status", "")
            ),
            "guidance": manifest.get("guidance", ""),
        }

    def _mapping_input_revision(
        self,
        workspace_dir: Path,
        model_path: Path,
        files: list[dict[str, Any]],
    ) -> str:
        inputs: list[dict[str, str]] = []
        for row in sorted(
            (item for item in files if item.get("status") == "preview_ready"),
            key=lambda item: str(item.get("file_name") or ""),
        ):
            path = _workspace_file_path(workspace_dir, row)
            if (
                path.is_symlink()
                or not path.is_file()
                or not is_relative_to_path(path.resolve(), workspace_dir.resolve())
            ):
                raise ResourceCurationWorkspaceError(
                    400,
                    f"Curated file is missing or outside workspace: {row.get('file_name')}",
                )
            inputs.append(
                {
                    "file_name": str(row.get("file_name") or ""),
                    "resource_id": str(row.get("resource_id") or ""),
                    "role": str(row.get("role") or ""),
                    "sha256": _file_sha256(path),
                }
            )
        payload = {
            "model_path": str(model_path),
            "model_sha256": _file_sha256(model_path),
            "curated_files": inputs,
        }
        return hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _curated_files_revision(
        self,
        workspace_dir: Path,
        files: list[dict[str, Any]],
    ) -> str:
        entries: list[dict[str, str]] = []
        for row in sorted(files, key=lambda item: str(item.get("file_name") or "")):
            path = _workspace_file_path(workspace_dir, row)
            is_safe = (
                not path.is_symlink()
                and path.is_file()
                and is_relative_to_path(path.resolve(), workspace_dir.resolve())
            )
            entries.append(
                {
                    "file_name": str(row.get("file_name") or ""),
                    "resource_id": str(row.get("resource_id") or ""),
                    "role": str(row.get("role") or ""),
                    "status": str(row.get("status") or ""),
                    "sha256": _file_sha256(path) if is_safe else "missing_or_unsafe",
                }
            )
        return hashlib.sha256(
            json.dumps(entries, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    def _workspace_suggested_methods(
        self,
        manifest: dict[str, Any],
        files: list[dict[str, Any]],
    ) -> list[str]:
        resources = [row for row in manifest.get("resources") or [] if isinstance(row, dict)]
        methods = suggested_methods_for_resource_set(resources)
        for row in files:
            for method in row.get("suggested_methods") or []:
                if method not in methods:
                    methods.append(method)
        return methods

    def _resource_local_file(self, row: ResourceRow) -> Path | None:
        local_path = str(row.get("local_path") or "").strip()
        if not local_path:
            return None
        path = Path(local_path)
        resolved = path.resolve() if path.is_absolute() else (self._config.app_root / path).resolve()
        allowed_roots = (self._config.app_root, self._config.workspace_root)
        if not any(is_relative_to_path(resolved, root) for root in allowed_roots):
            return None
        if not resolved.exists() or not resolved.is_file():
            return None
        return resolved

    def _resource_can_stage_model(self, row: ResourceRow) -> bool:
        readiness = str(row.get("readiness") or row.get("import_readiness") or "")
        return readiness in {"ready_for_import", "ready_for_reference"} and bool(self._resource_local_file(row))

    def _model_payload(self, row: ResourceRow) -> UploadFilePayload:
        path = self._resource_local_file(row)
        if not path:
            raise ResourceCurationWorkspaceError(
                400,
                f"Model resource is not locally stageable: {row.get('resource_id')}",
            )
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

    def _curated_file_payload(
        self,
        workspace_dir: Path,
        row: dict[str, Any],
    ) -> tuple[UploadFilePayload, bool]:
        relative = str(row.get("relative_path") or "")
        path = (workspace_dir / relative).resolve() if relative else Path(str(row.get("path") or "")).resolve()
        if not is_relative_to_path(path, workspace_dir.resolve()) or not path.exists() or not path.is_file():
            raise ResourceCurationWorkspaceError(
                400,
                f"Curated file is missing or outside workspace: {row.get('file_name')}",
            )
        data = path.read_bytes()
        role = str(row.get("role") or "custom_annotation")
        is_condition = role == "condition_exchange_bounds" or "condition" in role or "bound" in role
        file_name = str(row.get("file_name") or path.name)
        inspection = inspect_table_file(io.BytesIO(data), file_name, list(EXPECTED_COLUMNS))
        return (
            UploadFilePayload(
                filename=file_name,
                data=data,
                kind="condition_table" if is_condition else "omics_table",
                role=role,
                columns=inspection.columns,
                status=inspection.status,
                details=inspection.details,
            ),
            is_condition,
        )

    def _run_id(
        self,
        primary_model: ResourceRow | None,
        *,
        run_id: str = "",
        package_name: str = "",
        reserve: bool = False,
    ) -> str:
        if run_id:
            sanitized = sanitize_run_id(run_id)
            if sanitized != run_id:
                raise ResourceCurationWorkspaceError(
                    400,
                    "run_id may contain only letters, numbers, underscore, and dash.",
                )
            return sanitized
        base = package_name or f"atlas_{str((primary_model or {}).get('model_id') or 'candidate_package').lower()}"
        sanitized_base = sanitize_run_id(base) or "atlas_candidate_package"
        return (
            next_available_run_id(sanitized_base, self._config.user_runs_root, default="atlas_candidate_package")
            if reserve
            else sanitized_base
        )

    def _stage_manifest(
        self,
        run_id: str,
        workspace_id: str,
        manifest: dict[str, Any],
        ready_files: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "schema_version": "0.1.0",
            "created_at": _local_timestamp(),
            "run_id": run_id,
            "workspace_id": workspace_id,
            "status": "staged",
            "resources": manifest.get("resources", []),
            "primary_model_resource_id": manifest.get("primary_model_resource_id", ""),
            "curated_files": [_public_curated_file_record(row) for row in ready_files],
            "suggested_methods": self._workspace_suggested_methods(manifest, ready_files),
            "guidance": (
                "Curated files were staged from an Atlas curation workspace. "
                "Original Atlas resource readiness was not modified."
            ),
        }

    def _workspace_alias_maps(
        self,
        workspace_dir: Path,
        files: list[dict[str, Any]],
    ) -> dict[str, dict[str, str]]:
        aliases: dict[str, dict[str, str]] = {"gene": {}, "reaction": {}, "metabolite": {}}
        for file_row in files:
            if str(file_row.get("role") or "") != "id_alias_table":
                continue
            path = _workspace_file_path(workspace_dir, file_row)
            if not path.exists() or not is_relative_to_path(path, workspace_dir.resolve()):
                continue
            for row in _read_csv_rows(path):
                source = _first_row_value(
                    row,
                    ["source_id", "external_id", "protein_id", "gene_id", "reaction_id", "metabolite_id"],
                )
                model_id = _first_row_value(
                    row,
                    ["model_id", "target_id", "model_gene_id", "model_reaction_id", "model_metabolite_id"],
                )
                target_type = _first_row_value(row, ["target_type", "kind", "id_type", "role"]).lower()
                if not source or not model_id:
                    continue
                if "reaction" in target_type or "rxn" in target_type:
                    aliases["reaction"][_identifier_key(source)] = model_id
                elif "metabolite" in target_type or "compound" in target_type:
                    aliases["metabolite"][_identifier_key(source)] = model_id
                else:
                    aliases["gene"][_identifier_key(source)] = model_id
        return aliases

    def _file_mapping_summary(
        self,
        workspace_dir: Path,
        file_row: dict[str, Any],
        model_index: Any,
        alias_maps: dict[str, dict[str, str]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        file_name = str(file_row.get("file_name") or "")
        path = _workspace_file_path(workspace_dir, file_row)
        role = str(file_row.get("role") or "")
        if not path.exists() or not is_relative_to_path(path, workspace_dir.resolve()):
            return _empty_mapping_summary(file_row, "mapping_failed", "Curated file is missing from the workspace."), []
        rows = _read_csv_rows(path)
        id_type, candidate_columns = _mapping_target_for_role(role)
        if not id_type or not candidate_columns:
            return _empty_mapping_summary(
                file_row,
                "mapping_not_run",
                f"Mapping preview is not defined for role: {role}.",
            ), []
        mapped_ids: set[str] = set()
        unmapped_ids: set[str] = set()
        all_ids: set[str] = set()
        conditions: set[str] = set()
        for row in rows:
            condition = _first_row_value(row, ["condition", "sample", "sample_id", "condition_id"])
            if condition:
                conditions.add(condition)
            value = _first_row_value(row, candidate_columns)
            if not value:
                continue
            for identifier in _split_identifier_values(value):
                all_ids.add(identifier)
                resolved, status = _resolve_curated_identifier(model_index, identifier, id_type, alias_maps)
                if resolved and status != "unmapped":
                    mapped_ids.add(resolved)
                else:
                    unmapped_ids.add(identifier)
        total = len(all_ids)
        mapped = len(mapped_ids)
        unmapped = len(unmapped_ids)
        if total == 0:
            mapping_status = "mapping_failed"
            guidance = f"No {id_type} identifiers were found in {file_name}."
        elif mapped == total and unmapped == 0:
            mapping_status = "mapping_ready"
            guidance = "All unique identifiers mapped to the primary model."
        elif mapped > 0:
            mapping_status = "mapping_partial"
            guidance = "Some identifiers mapped to the primary model; review unmapped IDs before relying on this evidence."
        else:
            mapping_status = "mapping_failed"
            guidance = "No identifiers mapped to the primary model; check ID namespace or provide an alias table."
        summary = {
            "file_name": file_name,
            "resource_id": file_row.get("resource_id", ""),
            "role": role,
            "mapping_status": mapping_status,
            "id_type": id_type,
            "mapped_count": mapped,
            "total_count": total,
            "unmapped_count": unmapped,
            "coverage": round(mapped / total, 4) if total else 0,
            "condition_count": len(conditions),
            "suggested_methods": file_row.get("suggested_methods", []),
            "guidance": guidance,
            "mapped_sample": sorted(mapped_ids)[:10],
            "unmapped_sample": sorted(unmapped_ids)[:20],
        }
        return summary, [
            {
                "file_name": file_name,
                "role": role,
                "id_type": id_type,
                "identifier": identifier,
                "reason": "not_found_in_primary_model",
            }
            for identifier in sorted(unmapped_ids)
        ]

    def _update_files_with_mapping(
        self,
        workspace_dir: Path,
        workspace_id: str,
        files: list[dict[str, Any]],
        mapping_by_file: dict[str, dict[str, Any]],
    ) -> None:
        updated: list[dict[str, Any]] = []
        for row in files:
            next_row = dict(row)
            mapping = mapping_by_file.get(str(row.get("file_name") or ""))
            if mapping:
                next_row["mapping_status"] = mapping.get("mapping_status", "")
                next_row["mapping_preview"] = {
                    "mapping_status": mapping.get("mapping_status", ""),
                    "mapped_count": mapping.get("mapped_count", 0),
                    "total_count": mapping.get("total_count", 0),
                    "unmapped_count": mapping.get("unmapped_count", 0),
                    "coverage": mapping.get("coverage", 0),
                    "condition_count": mapping.get("condition_count", 0),
                    "id_type": mapping.get("id_type", ""),
                    "guidance": mapping.get("guidance", ""),
                    "suggested_methods": mapping.get("suggested_methods", []),
                }
            updated.append(next_row)
        self._write_file_manifest(workspace_dir, workspace_id, updated)


def _normalize_resource_id_list(resource_ids: tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in resource_ids:
        resource_id = str(item).strip()
        if resource_id and resource_id not in seen:
            seen.add(resource_id)
            result.append(resource_id)
    return result


def _workspace_resource_record(row: ResourceRow) -> dict[str, Any]:
    return {
        "resource_id": row.get("resource_id", ""),
        "resource_kind": row.get("resource_kind", ""),
        "title": row.get("title") or row.get("model_name") or row.get("model_id") or row.get("resource_id", ""),
        "model_id": row.get("model_id", ""),
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
        "target_role": curation_target_role(row, str(row.get("resource_kind") or "")),
    }


def _workspace_resource(manifest: dict[str, Any], resource_id: str) -> ResourceRow | None:
    return next(
        (
            row
            for row in (manifest.get("resources") or [])
            if isinstance(row, dict) and str(row.get("resource_id") or "") == resource_id
        ),
        None,
    )


def _safe_upload_filename(filename: str) -> str:
    name = Path(filename).name.strip() or "curated_file.csv"
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name) or "curated_file.csv"


def _workspace_file_path(workspace_dir: Path, row: dict[str, Any]) -> Path:
    relative = str(row.get("_content_relative_path") or row.get("relative_path") or "")
    path_value = str(row.get("_content_path") or row.get("path") or "")
    return (workspace_dir / relative).resolve() if relative else Path(path_value).resolve()


def _public_curated_file_record(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if not str(key).startswith("_content_")}


def _public_workspace_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    result = dict(manifest)
    result["curated_files"] = [
        _public_curated_file_record(row)
        for row in (manifest.get("curated_files") or [])
        if isinstance(row, dict)
    ]
    return result


def _mapping_result(
    workspace_id: str,
    *,
    status: str,
    guidance: str,
    model_summary: dict[str, Any],
    file_summaries: list[dict[str, Any]],
    unmapped_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    mapped = sum(int(row.get("mapped_count") or 0) for row in file_summaries)
    total = sum(int(row.get("total_count") or 0) for row in file_summaries)
    return {
        "schema_version": "0.1.0",
        "workspace_id": workspace_id,
        "status": status,
        "generated_at": _local_timestamp(),
        "model_summary": model_summary,
        "files": file_summaries,
        "unmapped_identifiers": unmapped_rows[:1000],
        "summary": {
            "file_count": len(file_summaries),
            "mapped_count": mapped,
            "total_count": total,
            "unmapped_count": max(total - mapped, 0),
            "coverage": round(mapped / total, 4) if total else 0,
        },
        "guidance": guidance,
    }


_MAPPING_ARTIFACT_NAMES = (
    "curation_mapping_preview.json",
    "curation_mapping_summary.csv",
    "curation_mapping_unmapped_ids.csv",
)


def _write_mapping_artifacts(
    workspace_dir: Path,
    result: dict[str, Any],
    *,
    input_revision: str = "",
) -> None:
    summary_rows = [
        {
            "file_name": row.get("file_name", ""),
            "role": row.get("role", ""),
            "mapping_status": row.get("mapping_status", ""),
            "id_type": row.get("id_type", ""),
            "mapped_count": row.get("mapped_count", 0),
            "total_count": row.get("total_count", 0),
            "unmapped_count": row.get("unmapped_count", 0),
            "coverage": row.get("coverage", 0),
            "condition_count": row.get("condition_count", 0),
            "suggested_methods": ";".join(str(item) for item in (row.get("suggested_methods") or [])),
            "guidance": row.get("guidance", ""),
        }
        for row in (result.get("files") or [])
        if isinstance(row, dict)
    ]
    unmapped_rows = [
        row for row in (result.get("unmapped_identifiers") or []) if isinstance(row, dict)
    ]
    generation_id = uuid4().hex
    artifacts = {
        "curation_mapping_preview.json": _json_bytes(result),
        "curation_mapping_summary.csv": _csv_bytes(summary_rows),
        "curation_mapping_unmapped_ids.csv": _csv_bytes(unmapped_rows),
    }
    _write_json(
        workspace_dir / "curation_mapping_transaction.json",
        {
            "schema_version": "0.1.0",
            "generation_id": generation_id,
            "input_revision": input_revision,
            "state": "writing",
            "started_at": _local_timestamp(),
        },
        allowed_root=workspace_dir,
    )
    for name, data in artifacts.items():
        _write_bytes(workspace_dir / name, data, allowed_root=workspace_dir)
    _write_json(
        workspace_dir / "curation_mapping_commit.json",
        {
            "schema_version": "0.1.0",
            "generation_id": generation_id,
            "input_revision": input_revision,
            "committed_at": _local_timestamp(),
            "artifacts": {
                name: {
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "bytes": len(data),
                }
                for name, data in artifacts.items()
            },
        },
        allowed_root=workspace_dir,
    )


def _committed_mapping_artifact_paths(
    workspace_dir: Path,
    *,
    strict: bool,
    expected_input_revision: str | None = None,
) -> dict[str, Path]:
    commit_path = workspace_dir / "curation_mapping_commit.json"
    transaction_path = workspace_dir / "curation_mapping_transaction.json"
    commit_present = commit_path.exists() or commit_path.is_symlink()
    transaction_present = transaction_path.exists() or transaction_path.is_symlink()
    transaction: dict[str, Any] = {}
    if transaction_present:
        if transaction_path.is_symlink() or not is_relative_to_path(
            transaction_path.resolve(),
            workspace_dir.resolve(),
        ):
            return _mapping_artifact_failure(strict, "Mapping transaction marker escaped its workspace.")
        try:
            transaction = _read_json_object(transaction_path)
        except (OSError, json.JSONDecodeError) as exc:
            return _mapping_artifact_failure(strict, f"Mapping transaction marker is unreadable: {exc}")
        if not transaction:
            return _mapping_artifact_failure(strict, "Mapping transaction marker is invalid.")
    if commit_present:
        if commit_path.is_symlink() or not is_relative_to_path(commit_path.resolve(), workspace_dir.resolve()):
            return _mapping_artifact_failure(strict, "Mapping commit marker escaped its workspace.")
        try:
            commit = _read_json_object(commit_path)
        except (OSError, json.JSONDecodeError) as exc:
            return _mapping_artifact_failure(strict, f"Mapping commit marker is unreadable: {exc}")
        if transaction and str(transaction.get("generation_id") or "") != str(commit.get("generation_id") or ""):
            return _mapping_artifact_failure(strict, "A newer mapping transaction is incomplete; rerun preview.")
        if expected_input_revision is not None and str(commit.get("input_revision") or "") != expected_input_revision:
            return _mapping_artifact_failure(strict, "Mapping inputs changed after preview; rerun preview.")
        metadata = commit.get("artifacts") if isinstance(commit, dict) else None
        if isinstance(metadata, dict):
            paths: dict[str, Path] = {}
            for name in _MAPPING_ARTIFACT_NAMES:
                path = workspace_dir / name
                expected = metadata.get(name)
                if (
                    path.is_symlink()
                    or not path.is_file()
                    or not is_relative_to_path(path.resolve(), workspace_dir.resolve())
                    or not isinstance(expected, dict)
                ):
                    return _mapping_artifact_failure(strict, "Committed mapping artifacts are incomplete.")
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if digest != str(expected.get("sha256") or ""):
                    return _mapping_artifact_failure(strict, "Committed mapping artifacts do not match their marker.")
                paths[name] = path
            return paths
        return _mapping_artifact_failure(strict, "Mapping commit marker is invalid.")

    if transaction_present:
        return _mapping_artifact_failure(strict, "Mapping artifact transaction is incomplete; rerun preview.")

    legacy_paths: dict[str, Path] = {}
    for name in _MAPPING_ARTIFACT_NAMES:
        path = workspace_dir / name
        if path.is_symlink():
            return _mapping_artifact_failure(strict, "Legacy mapping artifact escaped its workspace.")
        if path.is_file():
            if not is_relative_to_path(path.resolve(), workspace_dir.resolve()):
                return _mapping_artifact_failure(strict, "Legacy mapping artifact escaped its workspace.")
            legacy_paths[name] = path
    return legacy_paths


def _mapping_artifact_failure(strict: bool, detail: str) -> dict[str, Path]:
    if strict:
        raise ResourceCurationWorkspaceError(409, detail)
    return {}


def _read_committed_mapping_preview(
    workspace_dir: Path,
    *,
    expected_input_revision: str | None = None,
) -> dict[str, Any]:
    paths = _committed_mapping_artifact_paths(
        workspace_dir,
        strict=False,
        expected_input_revision=expected_input_revision,
    )
    preview = paths.get("curation_mapping_preview.json")
    return _read_json_object(preview) if preview else {}


def _empty_mapping_summary(file_row: dict[str, Any], status: str, guidance: str) -> dict[str, Any]:
    return {
        "file_name": file_row.get("file_name", ""),
        "resource_id": file_row.get("resource_id", ""),
        "role": file_row.get("role", ""),
        "mapping_status": status,
        "id_type": "",
        "mapped_count": 0,
        "total_count": 0,
        "unmapped_count": 0,
        "coverage": 0,
        "condition_count": 0,
        "suggested_methods": file_row.get("suggested_methods", []),
        "guidance": guidance,
        "mapped_sample": [],
        "unmapped_sample": [],
    }


def _mapping_target_for_role(role: str) -> tuple[str, list[str]]:
    normalized = role.lower()
    if normalized == "transcriptomics":
        return "gene", ["gene_id", "model_gene_id", "target_id"]
    if normalized in {"absolute_proteomics", "relative_proteomics", "proteomics"}:
        return "gene", ["gene_id", "model_gene_id", "protein_id", "protein_id_or_gene_id", "target_id"]
    if normalized in {"ml_priors", "kcat", "kcat_priors", "dlkcat_annotation"} or "kcat" in normalized:
        return "reaction", ["reaction_id", "model_reaction_id", "target_id", "reaction_id_or_enzyme_id"]
    if normalized in {
        "condition_exchange_bounds",
        "fluxomics",
        "production_targets",
        "uniprot_annotation",
        "custom_annotation",
    } or "annotation" in normalized:
        return "reaction", ["reaction_id", "model_reaction_id", "cobra_reaction_id", "target_id"]
    if normalized in {"extracellular_metabolomics", "intracellular_metabolomics", "metabolomics"}:
        return "metabolite", ["metabolite_id", "model_metabolite_id", "compound_id", "target_id"]
    return "", []


def _resolve_curated_identifier(
    model_index: Any,
    identifier: str,
    id_type: str,
    alias_maps: dict[str, dict[str, str]],
) -> tuple[str, str]:
    alias = alias_maps.get(id_type, {}).get(_identifier_key(identifier), "")
    candidates = [identifier]
    if alias:
        candidates.insert(0, alias)
    for candidate in candidates:
        if id_type == "reaction":
            resolved, status = model_index.resolve_reaction(candidate)
            exists = resolved in getattr(model_index, "reactions", set())
        elif id_type == "metabolite":
            resolved, status = model_index.resolve_metabolite(candidate)
            exists = resolved in getattr(model_index, "metabolites", set())
        else:
            resolved, status = model_index.resolve_gene(candidate)
            exists = resolved in getattr(model_index, "genes", set())
        if resolved and (status == "mapped" or exists):
            return resolved, status
    return "", "unmapped"


def _mapping_status(file_summaries: list[dict[str, Any]]) -> str:
    if not file_summaries:
        return "mapping_not_run"
    statuses = {str(row.get("mapping_status") or "") for row in file_summaries}
    if statuses <= {"mapping_ready"}:
        return "mapping_ready"
    if "mapping_ready" in statuses or "mapping_partial" in statuses:
        return "mapping_partial"
    if "mapping_failed" in statuses:
        return "mapping_failed"
    return "mapping_not_run"


def _mapping_guidance(status: str, file_summaries: list[dict[str, Any]]) -> str:
    if not file_summaries:
        return "No preview-ready curated files are available for mapping preview."
    if status == "mapping_ready":
        return "Curated evidence identifiers map to the primary model."
    if status == "mapping_partial":
        return "Curated evidence is partially mapped; review unmapped IDs before model generation."
    if status == "mapping_failed":
        return "Curated evidence identifiers did not map to the primary model; provide an alias table or revise IDs."
    return "Mapping preview has not been run for model-dependent curated evidence."


def _run_config_model_methods(suggested_methods: list[str]) -> list[str]:
    allowed = {"baseline_gem", "eflux", "fastcore", "consensus_evidence", "enzyme_gecko"}
    methods = [method for method in suggested_methods if method in allowed]
    if "baseline_gem" not in methods:
        methods.insert(0, "baseline_gem")
    return methods


def _run_config_analysis_modules(suggested_methods: list[str]) -> list[str]:
    modules = ["fba_pfba", "evidence_comparison", "readiness_gate"]
    if any(method in suggested_methods for method in ("model_compare", "analysis_visualization", "summary_evidence")):
        modules.append("visualization")
    return modules


def _split_identifier_values(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[;|,]", str(value or "")) if part.strip()]


def _identifier_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").strip().lower())


def _first_row_value(row: dict[str, Any], candidates: list[str]) -> str:
    by_key = {_normalize_table_column(key): value for key, value in row.items()}
    for candidate in candidates:
        value = by_key.get(_normalize_table_column(candidate))
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _normalize_table_column(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    delimiter = "\t" if path.suffix.lower() in {".tsv", ".txt"} else ","
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter=delimiter)]


def _read_json_object(path: Path, *, allowed_root: Path | None = None) -> dict[str, Any]:
    if allowed_root is not None:
        root = Path(allowed_root).resolve()
        if path.is_symlink():
            raise ResourceCurationWorkspaceError(403, "JSON artifact symlink is outside the trusted boundary.")
        if path.exists() and (
            not path.is_file() or not is_relative_to_path(path.resolve(), root)
        ):
            raise ResourceCurationWorkspaceError(403, "JSON artifact is outside the trusted boundary.")
    if not path.exists() or path.stat().st_size == 0:
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, data: dict[str, Any], *, allowed_root: Path) -> None:
    _write_bytes(path, _json_bytes(data), allowed_root=allowed_root)


def _write_text(path: Path, data: str, *, allowed_root: Path) -> None:
    _write_bytes(path, data.encode("utf-8"), allowed_root=allowed_root)


def _write_bytes(path: Path, data: bytes, *, allowed_root: Path) -> None:
    target = _validated_write_target(path, allowed_root)
    temporary = target.with_name(f".{target.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def _restore_compatibility_file(
    path: Path,
    previous_data: bytes | None,
    *,
    allowed_root: Path,
) -> None:
    if previous_data is not None:
        _write_bytes(path, previous_data, allowed_root=allowed_root)
        return
    target = _validated_write_target(path, allowed_root)
    target.unlink(missing_ok=True)


def _write_csv(path: Path, rows: list[dict[str, Any]], *, allowed_root: Path) -> None:
    _write_bytes(path, _csv_bytes(rows), allowed_root=allowed_root)


def _json_bytes(data: dict[str, Any]) -> bytes:
    return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")


def _csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    if not rows:
        return b""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validated_write_target(path: Path, allowed_root: Path) -> Path:
    target = Path(path)
    root = Path(allowed_root).resolve()
    parent = target.parent.resolve(strict=False)
    if not is_relative_to_path(parent, root):
        raise ResourceCurationWorkspaceError(403, "Write target is outside the active workspace boundary.")
    target.parent.mkdir(parents=True, exist_ok=True)
    parent = target.parent.resolve()
    if not is_relative_to_path(parent, root) or target.is_symlink():
        raise ResourceCurationWorkspaceError(403, "Write target is outside the active workspace boundary.")
    if target.exists() and not target.is_file():
        raise ResourceCurationWorkspaceError(409, f"Write target is not a regular file: {target}")
    if target.exists() and not is_relative_to_path(target.resolve(), root):
        raise ResourceCurationWorkspaceError(403, "Write target is outside the active workspace boundary.")
    return target


def _replace_path_prefixes(value: Any, source: Path, target: Path) -> Any:
    source_text = str(source)
    target_text = str(target)
    if isinstance(value, str):
        return value.replace(source_text, target_text)
    if isinstance(value, list):
        return [_replace_path_prefixes(item, source, target) for item in value]
    if isinstance(value, dict):
        return {key: _replace_path_prefixes(item, source, target) for key, item in value.items()}
    return value


def _remove_empty_directory(path: Path) -> None:
    try:
        path.rmdir()
    except (FileNotFoundError, OSError):
        pass


def _remove_owned_file(path: Path, allowed_root: Path) -> None:
    target = _validated_write_target(path, allowed_root)
    target.unlink(missing_ok=True)


def _remove_owned_tree(path: Path, allowed_root: Path) -> None:
    try:
        if path.is_symlink() or not path.exists():
            return
        resolved = path.resolve()
        root = allowed_root.resolve()
        if resolved == root or not is_relative_to_path(resolved, root):
            return
        shutil.rmtree(path)
    except OSError:
        pass


def _local_timestamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


__all__ = [
    "AddCuratedFile",
    "CreateWorkspace",
    "GetWorkspace",
    "ListWorkspaces",
    "PreviewMapping",
    "ResourceCurationWorkspaceConfig",
    "ResourceCurationWorkspaceError",
    "ResourceCurationWorkspaces",
    "StageRunPackage",
]
