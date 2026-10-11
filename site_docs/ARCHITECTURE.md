# 架构说明

本文档记录当前 Omics-GEM Studio 的工程结构和模块边界。它描述的是现状，不是理想化重写方案。

## 顶层结构

```text
D:\generate
  api/             FastAPI HTTP 层和后端服务聚合
  frontend/        React / Vite 前端
  omics_router/    workflow、模型、可视化、报告核心库
  resources/       Resource Atlas index、cache、case manifest
  case_studies/    本地 case study 原始材料和转换数据
  user_runs/       Run Package 与演示运行结果
  tools/           harvesting、case、部署、QA 与维护脚本
  deployment/      Caddy、Cloudflare 等本机部署配置
  docs/            工程文档、spec、QA 和清理记录
```

## 后端边界

- `api/main.py` 定义 FastAPI app、endpoint、认证和路由入口。
- `api/services.py` 仍是主要服务聚合层，保持 endpoint 兼容，后续只做渐进式拆分。
- `api/status_semantics.py` 承载共享的 readiness / missing evidence 状态语义。
- `api/resource_atlas_helpers.py` 承载 Resource Atlas 的纯聚合 helper，例如 species row、landscape cluster 和 count breakdown。
- `api/resource_atlas_helpers.py` also owns Resource Atlas search pagination, resource payload shaping, facet aggregation, and search response shaping; `api/services.py` still owns index loading and filter predicate orchestration.
- `api/resource_atlas_helpers.py` also owns Resource Atlas summary count aggregation and response shaping; `api/services.py` still owns index loading, resource normalization, deduplication, coverage lookup, and landscape node generation.
- `api/resource_atlas_helpers.py` owns Resource Atlas resource detail response shaping; `api/resource_curation_helpers.py` keeps the pure role, template, required-column, preview status, and guidance policy used by curation previews.
- `api/resource_curation_workspace.py` owns the persistent Resource Curation Workspace lifecycle behind a typed `create / query / execute` interface: resource snapshots, curated-file manifests, identifier mapping artifacts, stage eligibility, and Run Package staging order.
- `api/services.py` composes that module from the current workspace roots and Resource Atlas collaborators, preserves the existing endpoint-facing functions/response shapes, maps `ResourceCurationWorkspaceError` to `ApiError`, and appends the existing run overview after staging.
- `api/case_study_helpers.py` 承载 Case Study readiness ladder、QA matrix、missing-run readiness payload、prepare-preview dry-run response/log payload、prepare-lite response/log payload 的纯装配。
- `api/services.py` 仍负责 case manifest normalization、run package resolution、artifact probing、pair summary smoke、QA artifact writes, and endpoint-facing orchestration.
- `api/compare_semantics.py` 承载 Model Compare readiness summary 与 case-specific guidance 的纯语义判断。
- `api/file_artifact_helpers.py` 承载文件/Artifact 访问的纯路径安全 helper 与 package-relative path helper；`api/services.py` 继续保留 endpoint-facing wrapper，`api/main.py` 继续负责 `FileResponse`。
- `omics_router/` 保存领域逻辑，尽量避免混入 HTTP 请求细节。
- `resources/` 和 `user_runs/` 是展示与 workflow 的事实来源，不在 UI 中伪造缺失 artifact。

## 前端边界

`frontend/src/App.tsx` 仍是应用 shell、路由、状态和 API 调用的主入口。为降低复杂度，纯展示层正在逐步迁移到 `features/`：

```text
frontend/src/features/
  input/            Input 模式切换、case story、上传面板骨架、上传文件 role/preview 展示
  resource-atlas/   Atlas map、results、inspector 的展示与 adapter
  model-generator/  Model & Omics Dossier、Method Workbench
  model-compare/    Compare context、coverage、ranking、reaction detail、compareAdapters
  analysis/         Analysis Method Workbench、registry、inspector、action bar
  summary/          Case story、readiness ladder、QA matrix
```

当前约束：

- `features/*` 组件只接收 props 和 callbacks，不自行 fetch。
- `features/*/*Adapter.ts` 只做纯数据装配，不持有 React state，不调用 API。
- `frontend/src/features/input/InputPanels.tsx` 承载 Input 模式切换、Upload Run Package 表单壳，以及上传文件摘要、逐文件 omics role editor、condition 文件提示和 role preview；上传状态、文件对象、提交动作和 role 推断仍由 `App.tsx` 管理。
- `frontend/src/domain/workflowRouting.ts` 只做 hash route 到 stage/module/subview 的纯解析，不自行 fetch，也不直接写 React state。
- `App.tsx` 继续负责 API 调用、状态管理、workflow action 和数据装配。
- Model Compare 的 ReactionDiff 事实层、pair summary、network viewer 和图谱加载暂不拆出；只把 coverage、ranking filter、detail rows 等派生数据放入 adapter。
- Analysis 的方法列表数据仍由 `App.tsx` 装配，展示层由 `features/analysis` 承载。
- 拆分时保留现有 CSS className，避免视觉回归。

## 数据流

1. Input 上传或 Atlas staging 创建 `user_runs/{run_id}`。
2. Workflow / Model Generator 读取 run package，生成 variants、summary 和 comparison artifacts。
3. Model Compare 读取 pair summary、annotation groups、graph 和 ReactionDiff。
4. Analysis 汇总已有输出，不自动运行重型外部工具。
5. Summary 展示报告、case story、QA matrix、缺失项和下一步建议。

## 状态语义

前后端应统一使用这些缺失证据状态：

- `ready`
- `partial`
- `not generated`
- `package-ready only`
- `reaction-level unavailable`
- `external pending`
- `external ecModel pending`
- `evidence-only case`

真实 `0` 只用于 artifact 已生成且字段明确为零。未生成、不可用或外部 pending 的证据不得用 `0` 代替。

## 兼容边界

- 不随意改变 API 路径。
- 不改变 CSV schema、method id、job type 或输出文件名。
- 不删除 `case_studies`、`user_runs`、`resources/cached_search`、`paper`、`.venv`。
- 清理只采用 `_cleanup_quarantine/YYYYMMDD/` 隔离归档，并在 `docs/CLEANUP_MANIFEST.md` 记录。
## Workflow shell 与 deep-link 路由

- `frontend/src/domain/workflowTypes.ts` 是 workflow stage、module、subview、input mode 的前端类型事实源。
- `frontend/src/domain/workflowDefinitions.ts` 是 workflow 静态结构事实源，包含 stage 列表、首页可见 workflow stages、module registry 和 primary stage module。
- `frontend/src/domain/workflowRouting.ts` 是 hash route 到 workflow stage/module/subview 的唯一纯解析入口。
- `frontend/src/features/workflow/WorkflowShellPanels.tsx` 承载顶部 workflow nav、首页四阶段 overview、stage frame 和 stage navigator 的纯展示层。
- `frontend/src/features/workflow/workflowShellAdapter.ts` 承载 workflow shell 的派生数据装配，例如 nav stage items、overview stage/module items 和 status pills；它是纯函数层，不 fetch、不读写全局状态。
- `App.tsx` 仍负责 route 应用、状态管理、API 调用、refresh、language/auth 和 workflow actions；domain 和 `features/workflow` 不自行 fetch、不读写浏览器存储。
- 导航或深链改动后必须运行 `node tools\check_workflow_routing.mjs` 与 browser smoke，避免 `#/module-generate` 回退到 workflow overview。

## Workflow domain helper 边界

- `frontend/src/domain/workflowHelpers.ts` 承载 workflow stage 与后端 stage id 的映射、后端保存状态恢复规则，以及 workflow stage/module id guard。
- `stageFromApiId("model_comparison")` 和 `stageFromApiId("compare")` 会恢复为 `generate`，因为 Model Compare 是 Model Generator 内部子页，不再作为首页第五阶段。
- `workflowRouting.ts` 只做 hash route 解析；遇到 module-like route 时必须通过 `isWorkflowModuleId` guard 后再读取 module registry。
- 修改 `workflowTypes.ts`、`workflowDefinitions.ts`、`workflowHelpers.ts` 或 `workflowRouting.ts` 后，必须运行 `node tools\check_workflow_routing.mjs`。

## Workflow state adapter 边界

- `frontend/src/domain/workflowStateAdapter.ts` 承载后端 workflow state 到前端 stage/module/subview/hash 决策的纯装配逻辑。
- `resolveSavedWorkflowState(...)` 只返回决策对象，不自行写 React state、不写 `window.location.hash`、不调用 API。
- `buildWorkflowStatePayload(...)` 统一生成 `updateWorkflowState` payload；`moduleId === "workflow"` 时写入空 `active_module`。
- `resolveStageStatusForNav(...)` 统一从 `workflowSummary.stages` 派生顶部导航状态。
- `App.tsx` 仍负责实际 `setState`、hash 写入、API 调用和 refresh orchestration。

## API client 与 domain type barrels

- `frontend/src/api.ts` 仍是后端 wire contract 与 `ApiClient` runtime 的事实源；endpoint client 不拆分、不复制。
- `frontend/src/domain/*Types.ts` 只做 type-only re-export，作为前端业务模块的类型阅读入口，避免 `App.tsx` 和 feature 组件直接依赖庞大的 `api.ts` 类型列表。
- `resourceAtlasTypes.ts`、`caseStudyTypes.ts`、`modelCompareTypes.ts`、`workflowApiTypes.ts` 不包含 runtime 逻辑，不 fetch、不持有状态、不改 response shape。
- 后续拆分 feature 时优先从 domain type barrels import 类型；只有 `ApiClient`、`ApiRequestError`、`DEFAULT_API_BASE` 这类 runtime API 入口继续从 `api.ts` 导入。

## Workflow action result panel boundary

- `frontend/src/features/workflow/ActionResultPanel.tsx` owns the pure display layer for recent action results used by DataHub, Model Generator, Analysis, and Summary.
- The component receives `actionResults`, localized copy, fallback idle results, the default reaction filter, and `apiBaseUrl` from `App.tsx`.
- It does not fetch, mutate workflow state, submit jobs, or inspect global browser state.
- `App.tsx` remains responsible for action execution, action result state updates, language switching, run/job orchestration, and the runtime `DEFAULT_API_BASE` value.

## Resource Atlas adapter 边界

- `frontend/src/features/resource-atlas/resourceLandscapeAdapter.ts` 承载 map-ready organism node 的纯转换逻辑，输入来自 `OrganismIdentity[]`，输出给 `ResourceLandscapeMap` 使用。
- `frontend/src/features/resource-atlas/resourceAtlasAdapters.ts` 承载 Resource Atlas 页面级纯数据装配，包括 case study 下拉选项、active resource 查找、source link 去重、omics 分组、cache / source coverage view model、facet options、count cards、landscape context 和 Deep Dive source rows。
- `frontend/src/features/resource-atlas/ResourceAtlasPanels.tsx` 承载 cache status、source coverage、Results Drawer、Deep Dive 证据矩阵与 Decision Inspector 的纯展示面板；它只接收 adapter 输出、页面状态快照和回调，不自行 fetch 或持有搜索状态。
- Resource Atlas adapter 不 fetch、不读写 React state、不调用 `ApiClient`，也不触发 workflow action；`App.tsx` 仍负责资源搜索、detail 读取、case 选择、候选包、curation workspace 和所有回调。
- 资源地图、Results Drawer、Decision Inspector 的展示组件可以消费这些 adapter 输出，但不能把 metadata-only / raw-only 资源改写成 `ready_for_import`。
- 修改 Resource Atlas adapter 后至少运行 `npm.cmd run typecheck`、`npm.cmd run build` 和 browser smoke；如果触碰搜索/筛选语义，还需要手动检查 Resource Landscape Map、Current lens chips、Results Drawer 和 Decision Inspector。

## Backend file artifact helper boundary

- `api/file_artifact_helpers.py` owns pure file/artifact path helpers: safe workspace path resolution, package-relative path formatting, and package-relative file listing.
- It also owns file summary, table preview, and JSON artifact discovery shape helpers; `api/services.py` injects the existing CSV/JSON readers so the helper layer stays free of service imports.
- `api/services.py` keeps compatibility wrappers such as `_relative_files(...)` so endpoint-facing call sites remain stable during gradual extraction.
- `api/main.py` remains responsible for FastAPI response objects such as `FileResponse`; helper modules should not import FastAPI runtime response classes.

## Backend run package helper boundary

- `api/run_package_helpers.py` owns pure run package structure helpers: run package marker detection, staged model path discovery, and GECKO export model id lookup.
- It also owns run id naming rules such as run id sanitization and next-available id selection for active and archived run directories.
- It owns run package path enumeration helpers for known workspace packages and discovery-root candidates; `api/services.py` still builds import status, overview, and endpoint responses.
- It owns import/archive/restore manifest payload shaping for run package lifecycle actions; `api/services.py` still owns timestamps, `write_json`, file IO, and compatibility wrappers.
- It owns import/archive/restore action result payload shaping; `api/services.py` still owns validation, copy/move operations, manifest writing, and job orchestration.
- It owns archive/restore job log line shaping; `api/services.py` still owns job callbacks, log file IO, and sync job execution.
- It owns import/archive manifest response shaping; `api/services.py` still owns run/archive path resolution and JSON manifest reads.
- It owns run package candidate view-model shaping and safe path equality checks; `api/services.py` still reads run overview data and workspace roots.
- It owns safe run overview fallback shaping; `api/services.py` still owns the full `run_overview(...)` implementation and injects readers.
- It owns archived run overview row shaping; `api/services.py` still reads archive manifests and resolves archived workspace paths.
- `api/services.py` keeps compatibility wrappers such as `_looks_like_run_package(...)`, `_run_model_path(...)`, and `_model_id_from_existing_manifest(...)` so existing endpoint-facing orchestration stays stable.
- The helper layer receives CSV/JSON reader callbacks from `api/services.py`; it should not import service globals, FastAPI runtime classes, or workspace state.

## Backend workspace helper boundary

- `api/workspace_helpers.py` owns workspace/project response shaping for workspace status and the default project row.
- It also owns workspace path candidate normalization and workspace config payload shaping.
- `api/services.py` still owns workspace config reads, root switching, directory initialization, existence checks, access checks, persistence writes, and endpoint-facing wrappers.
- The helper layer should not mutate workspace globals, create directories, or read config files.

## Resource Lineage Atlas 当前边界

- Resource Atlas 当前主入口是 `Resource Lineage Atlas`，不是搜索列表或 landscape map。
- `api/resource_atlas_helpers.py` 负责把 `resource_index.json + cached_search/* + target organisms + image manifest` 聚合成 `lineage_tree_resource_nodes`、`lineage_tree_resource_edges` 和 `lineage_tree_summary`。
- cache 中有资源但不在原始 Draw_Trees 里的 organism 会进入 `Indexed microbes` fallback 分组；不要使用 `unclaimed` 这类含义不清的分组名。
- `frontend/src/features/resource-atlas/SpeciesResourceLineageTree.tsx` 负责主谱系树展示：taxonomy group、species/strain 卡片、资源类型子节点、图片占位、计数和点击回调。
- `frontend/src/features/resource-atlas/ResourceAtlasPanels.tsx` 负责右侧 Species Resource Inspector、Resource entries、Source coverage、Deep Dive 等纯展示面板。
- `App.tsx` 仍负责 API 调用、搜索状态、case 选择、candidate package、curation workspace 和 workflow action 回调。
- Resource Landscape Map、Advanced search、Deep Dive 保留为折叠辅助区；它们不能重新抢占 Resource Atlas 第一视觉。
## Case Context domain seam

- `frontend/src/domain/caseContext.ts` owns pure case/stage/run decision logic for visible cases, composite cases, legacy Shewanella fallback, and plain run fallback.
- Its single interface is `resolveCaseStageContext(...)`; it returns `current` plus stage contexts for `input`, `generate`, `compare`, `analysis`, and `summary`.
- The module is pure: it does not fetch, mutate React state, write hash routes, read browser storage, run workflows, or create artifacts.
- `App.tsx` remains responsible for API calls and applying the returned context to existing state/effects.
- Fallback order is fixed: exact manifest/readiness context, explicit legacy fallback table, selected-run plain fallback, then empty shell context.
- Changes to case/stage/run routing must run `node tools\check_case_context.mjs`.

## Workflow Runtime domain seam

- `frontend/src/domain/workflowRuntime.ts` owns the first pure snapshot resolver for workflow runtime decisions.
- Its single interface is `resolveWorkflowRuntime(...)`; callers pass the current React state snapshot, `caseContext`, workflow summary, and localized shell copy callbacks.
- The module returns current stage/module/subview/run decisions, shell view-model rows, semantic refresh intents, a workflow state payload, and guidance.
- It is pure: it does not fetch, mutate React state, write hash routes, read storage, submit workflow actions, or create artifacts.
- `App.tsx` remains the adapter that applies decisions: it still owns API calls, loading/error state, hash writes, React state writes, auth, language, and workflow action side effects.
- The refresh plan is intentionally semantic only, for example `workflow_summary`, `analysis_summary`, or `model_compare_pair`; it is not an API execution order.
- Changes to workflow runtime decisions must run `node tools\check_workflow_runtime.mjs` plus `node tools\check_workflow_routing.mjs`.

## Model Compare Workspace domain seam

- `frontend/src/domain/modelCompareWorkspace.ts` owns pure Model Compare workspace decisions for effective pair, effective submap/scope, graph status, graph load plan, dashboard metrics, legend semantics, and guidance.
- Its single interface is `resolveModelCompareWorkspace(...)`; callers pass the current React/API snapshot, `caseContext`, variant options, annotation groups, pair summary, graph state, and current user selections.
- The module is pure: it does not fetch pair summaries, read graph files, mutate React state, write hash routes, render network nodes, or create workflow artifacts.
- `App.tsx` remains responsible for side effects: pair summary API calls, graph JSON loading, selected reaction state, hash routing, and `InteractiveNetworkViewer` rendering.
- The resolver explicitly prevents silent reference-vs-reference fallback, keeps Shewanella integrated GECKO defaults at `baseline_gem__all -> enzyme_gecko__higho2` and `kegg_pathway / rn00020`, and keeps trigger paper defaults at `custom_annotation / nitrogen_glycogen_coupling`.
- Graph loading uses a fixed priority: inline edit graph with nodes, pair graph path, then active annotation group graph path. Path-only graph metadata is not treated as a loaded graph.
- Changes to Model Compare workspace decisions must run `node tools\check_model_compare_workspace.mjs` plus the existing case context and workflow routing checks.

## Analysis Workspace domain seam

- `frontend/src/domain/analysisWorkspace.ts` owns pure Analysis/Summary paper reproduction decisions.
- Its single interface is `resolveAnalysisWorkspace(...)`; callers pass the current snapshot: selected run, active case id, `caseContext`, loaded `analysisSummary`, optional trigger paper payload, and known run ids.
- The module returns the active Analysis run, active Summary run, workbench mode, Summary report preset, paper reproduction payload, section status decisions, and guidance.
- It is pure: it does not fetch analysis summaries, mutate React state, write hash routes, trigger report jobs, render charts, or create artifacts.
- `App.tsx` remains responsible for API timing, `triggerPaperReproduction` state, report job submission, and passing the returned view-model into `PaperReproductionWorkbench` and Summary panels.
- The contract intentionally locks only demo-critical facts: integrated Shewanella Analysis/Summary use the trigger run, GDM is `computed_lite`, D2T2 is `paper_reported_only`, dFBA/glycogen is `paper_reported_model_prediction_available`, bounds are `not_generated`, and enzyme capacity is `not_applicable`.
- It does not lock Chinese/English copy, artifact counts, chart point counts, generated report HTML, or caveat wording.
- Changes to Analysis/Summary paper reproduction decisions must run `node tools\check_analysis_workspace.mjs` plus the existing case context and workflow routing checks.

## Resource Lineage Tree domain seam

- `frontend/src/domain/resourceLineageTree.ts` owns pure Resource Atlas lineage decisions: Draw_Trees leaf matching, biological placement, empty-species visibility, broad resource category grouping, selection targets, and lineage guidance.
- Its main interface is `resolveResourceLineageTree(...)`; callers pass a Draw_Trees root and backend `lineage_tree_resource_nodes`.
- The module is pure: it does not fetch Atlas summary, download or mutate images, create candidate packages, write React state, draw SVG edges, handle pan/zoom, or open the right-side drawer.
- `frontend/src/features/resource-atlas/SpeciesResourceLineageTree.tsx` owns rendering and viewport behavior: SVG/CSS tree layout, horizontal scroll rail, blank-canvas drag pan, zoom buttons, focus controls, and click callbacks.
- `App.tsx` remains responsible for fetching Atlas summary, resource search results, candidate package actions, curation workspace actions, and right drawer state.
- Resource categories are intentionally split into four primary categories (`Model`, `Transcriptomics`, `Proteomics`, `Metabolomics`) plus two support categories (`Enzyme/kcat`, `Annotation/metadata`) so support evidence is not presented as an equal omics layer.
- Empty species nodes are hidden by default in the product UI and only returned when `includeEmptySpecies` is explicitly enabled for debug/review.
- Changes to lineage placement, category semantics, empty-species handling, or selection targets must run `node tools\check_resource_lineage_tree.mjs`.

## Run Package Resolver backend seam

- `api/run_package_resolver.py` owns read-only run package context: package identity, artifact inventory, stage readiness, variant context, optional evidence status, and paper/report context.
- Its main interface is `resolve_run_package_context(package, readers=None, options=None)`.
- The resolver is read-only: it does not import FastAPI, execute workflows, upload files, archive/restore packages, render graphs, generate reports, or write artifacts.
- `api/services.py` remains the endpoint-facing orchestration layer; it injects existing CSV/JSON/variant/edit readers and preserves existing response shapes.
- `api/run_package_helpers.py` continues to own lifecycle/path helper behavior such as discovery, import/archive/restore payload shaping, run id sanitization, and package marker detection.
- Missing optional evidence is represented as guidance/status, never as a real numeric `0`; critical missing artifacts degrade the affected stage readiness rather than raising.
- Changes to run package inventory, readiness semantics, variant context, or paper/report context must run `D:\generate\.venv\Scripts\python.exe tools\check_run_package_resolver.py`.

## Resource Curation Workspace backend seam

- `api/resource_curation_workspace.py` owns Resource Curation Workspace state transitions and artifact ordering.
- Its interface has three entry points: `create(CreateWorkspace)`, `query(GetWorkspace | ListWorkspaces)`, and `execute(workspace_id, AddCuratedFile | PreviewMapping | StageRunPackage)`.
- The module owns workspace/file manifests, safe local paths, curated-file preview records, SBML identifier mapping, mapping JSON/CSV artifacts, stage guards, Run Package inputs, and Atlas provenance manifests.
- New Workspaces are prepared in a hidden sibling directory and atomically published, so a failed create does not reserve the requested workspace id.
- Curated-file content is immutable/versioned. `curated_file_manifest.json` is the canonical pointer; the legacy `curated_files/<name>` path and Workspace manifest are compatibility projections and are rolled back if the aggregate upload commit fails. Public responses keep the legacy path/shape and hide internal content pointers.
- Mapping preview JSON/CSV files are published with a generation transaction plus SHA-256 commit marker bound to the current model and every preview-ready curated file. Query/staging rejects stale, incomplete, or mixed generations.
- Run Package staging is prepared under `user_runs/.curation_staging`, all embedded paths are rewritten to their published location, and the complete directory is atomically published. An ordinary write failure preserves the incomplete package under the same-volume `user_runs/.curation_failed/<workspace_id>` recovery area and leaves the requested run id reusable. Recovery only touches a published directory when the current attempt actually published it.
- Local files are a local-substitutable internal seam configured by `ResourceCurationWorkspaceConfig`; the interface does not expose a hypothetical storage port.
- The module does not import FastAPI, `api.services`, or `ApiError`. `api/services.py` is the compatibility adapter that maps domain errors and preserves existing endpoint response shapes.
- `Run Package Resolver` remains read-only and separate. Resource Curation Workspace creates a package; the compatibility adapter adds the existing `run_overview(...)` projection afterward.
- Changes to this lifecycle must run `D:\generate\.venv\Scripts\python.exe tools\check_resource_curation_workspace.py` plus the Resource Curation HTTP regression tests.
