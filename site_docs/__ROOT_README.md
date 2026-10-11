# Omics-GEM Studio

Omics-GEM Studio is a local-first research workbench for combining genome-scale metabolic models with omics evidence. The current workflow is:

```text
Input -> Model Generator -> Analysis -> Summary
```

Model Compare is part of Model Generator. Resource Atlas is part of Input and is used to discover model and omics evidence before creating or selecting a run package.

## Current Startup

Recommended local browser app:

```powershell
cd D:\generate
.\start_omics_gem_browser_app.ps1
```

Desktop/runtime distribution notes are maintained separately:

- `docs/分发说明.md`
- `docs/LOGIN_AND_NETWORK_DEPLOYMENT.md`
- `docs/LOCAL_CLOUDFLARE_TUNNEL_DEPLOYMENT.md`

## Documentation

Start here:

- `docs/README.md`
- `docs/PROJECT_OVERVIEW.md`
- `docs/ARCHITECTURE.md`
- `docs/WORKFLOW_SPEC.md`
- `docs/RESOURCE_ATLAS_SPEC.md`
- `docs/MODEL_GENERATOR_SPEC.md`
- `docs/MODEL_COMPARE_SPEC.md`
- `docs/CASE_STUDY_SPEC.md`
- `docs/TESTING_QA.md`
- `docs/RECOVERY_AND_BACKUP.md`

User-facing Chinese docs:

- `docs/快速入门.md`
- `docs/详细使用手册.md`
- `docs/分发说明.md`

Historical README content has been archived in:

```text
docs/LEGACY_README_ARCHIVE.md
```

## Development Checks

Backend smoke:

```powershell
D:\generate\.venv\Scripts\python.exe -m py_compile api\services.py api\status_semantics.py
D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py
```

Frontend checks:

```powershell
cd D:\generate\frontend
npm.cmd run typecheck
npm.cmd run build
```

Focused regression sets:

```powershell
cd D:\generate
D:\generate\.venv\Scripts\python.exe -m pytest tests\test_resource_harvest_tools.py tests\test_fastapi_api.py -k "resource or harvest"
D:\generate\.venv\Scripts\python.exe -m pytest tests\test_variant_comparison.py tests\test_enzyme_constraints.py
D:\generate\.venv\Scripts\python.exe -m pytest tests\test_upload_workflow.py tests\test_fastapi_api.py
```

## Cleanup And Recovery

Do not directly delete large data or runtime directories. Use the quarantine workflow documented in:

- `docs/RECOVERY_AND_BACKUP.md`
- `docs/CLEANUP_MANIFEST.md`
- `docs/CLEANUP_DEPENDENCY_AUDIT.md`

The current `.git` directory exists but is not a usable repository. Treat external directory backup as the reliable rollback method until git is repaired.

## Important Boundaries

- Do not mark metadata-only or raw-only public resources as `ready_for_import`.
- Do not use `0` to represent missing ecModel, capacity, FVA, validation, or behavior evidence.
- Do not move or delete `case_studies/`, `user_runs/`, `resources/cached_search/`, `paper/`, `.venv/`, `.runtime_cache/`, or `desktop_*` without a separate archive plan.
- Do not add new science algorithms during engineering cleanup unless explicitly requested.
