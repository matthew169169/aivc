# Testing 与 QA

## Resource Atlas Metadata Expansion Checks

When changing Resource Atlas metadata quality, canonical linking, taxonomy queue/cache, or organism target registry expansion, run:

```powershell
D:\generate\.venv\Scripts\python.exe -m py_compile tools\update_resource_cache.py tools\run_resource_harvest_plan.py tools\run_resource_continuation_plan.py tools\resource_atlas_quality.py tools\microbe_target_registry.py tools\promote_organism_targets.py tools\resource_taxonomy.py tools\resource_post_harvest_qa.py tools\build_resource_taxonomy_cache.py tools\run_resource_post_harvest_qa.py tools\review_taxonomy_targets.py tools\enrich_taxonomy_targets.py
D:\generate\.venv\Scripts\python.exe -m pytest tests\test_resource_harvest_tools.py -q
```

Refresh local metadata-only artifacts in this order:

```powershell
D:\generate\.venv\Scripts\python.exe tools\build_resource_quality_report.py
D:\generate\.venv\Scripts\python.exe tools\build_microbe_target_registry.py
D:\generate\.venv\Scripts\python.exe tools\promote_organism_targets.py
D:\generate\.venv\Scripts\python.exe tools\build_resource_taxonomy_cache.py
D:\generate\.venv\Scripts\python.exe tools\review_taxonomy_targets.py --dry-run
D:\generate\.venv\Scripts\python.exe tools\enrich_taxonomy_targets.py --dry-run
D:\generate\.venv\Scripts\python.exe tools\run_resource_post_harvest_qa.py
```

Expected behavior:

- `organism_targets.csv` is unchanged unless `promote_organism_targets.py --apply` is explicitly used.
- `scope_*` and other abstract scope rows are rejected by promotion dry-run with `abstract_scope_not_promotable`; they must not appear in `rows_to_add`.
- `ready_for_import` is reserved for local/importable resources; public metadata-only rows must not be marked ready.
- taxonomy queue/cache must separate `ready`, `needs_taxonomy_review`, and special categories such as metagenome/mixed/host samples.
- `taxonomy_review_worklist.csv/json` must contain concrete organism rows only and exclude `scope_*` plus special categories.
- `taxonomy_review_decisions.csv/json` must cover every worklist row; missing taxon IDs must be labeled `needs_taxon_id`, not guessed.
- `organism_targets_review_promotion_dry_run.*` is advisory and must not modify `organism_targets.csv`.
- `enrich_taxonomy_targets.py` must remain cache-first unless `--online-ncbi` is explicitly supplied.
- NCBI enrichment accepts species/strain-level exact or synonym matches only; genus-only, ambiguous, no-hit, and network-failed rows stay in warnings.
- `cache_manifest.json` must point to quality, canonical, readiness, taxonomy, and review worklist report artifacts.

## Shewanella Integrated Case Checks

When changing case-study routing, readiness, Model Compare, Analysis, or Summary:

```powershell
D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "case_study or analysis_summary"
cd D:\generate\frontend
npm.cmd run typecheck
npm.cmd run build
```

Manual QA for `shewanella_integrated_overview`:

- Case dropdown shows one visible Shewanella entry.
- `Model Compare` uses `shewanella_gecko_case` and the default pair
  `baseline_gem__all` vs `enzyme_gecko__higho2`.
- `Analysis` and `Summary` use `shewanella_transcriptional_triggers_case` and
  show the paper reproduction workbench/report.
- Legacy source cases remain direct-API addressable but hidden from the default
  dropdown and QA matrix.

本文档记录当前项目推荐的静态检查、后端回归、浏览器 smoke 和手动 QA 流程。

## 前端静态检查

```powershell
cd D:\generate\frontend
npm.cmd run typecheck
npm.cmd run build
```

`typecheck` 用于检查 React / TypeScript 边界；`build` 用于确认 Vite production bundle 能生成。

## 后端回归

基础 API：

```powershell
cd D:\generate
.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py
```

常用专项：

```powershell
.venv\Scripts\python.exe -m pytest tests\test_resource_harvest_tools.py tests\test_fastapi_api.py -k "resource or harvest"
.venv\Scripts\python.exe -m pytest tests\test_model_generation.py tests\test_variant_comparison.py tests\test_enzyme_constraints.py
.venv\Scripts\python.exe -m pytest tests\test_upload_workflow.py tests\test_fastapi_api.py
```

后端 helper 或 endpoint wrapper 改动后先跑：

```powershell
.venv\Scripts\python.exe -m py_compile api\main.py api\services.py api\status_semantics.py
```

## Workflow 路由契约

导航、hash route、workflow type/definition、workflow helper、workflow shell adapter 改动后必须跑：

```powershell
node tools\check_workflow_routing.mjs
```

该检查覆盖 `#/module-input`、`#/module-generate`、`#/module-model-comparison`、`#/module-analysis`、`#/module-summary` 和 legacy aliases，并确认 `model_comparison` 后端状态恢复为 Model Generator 内部 compare subview。

## Workflow Runtime Contract

When changing workflow runtime decisions, shell view-model derivation, semantic refresh intents, or the way `App.tsx` consumes workflow decisions, run:

```powershell
node tools\check_workflow_runtime.mjs
node tools\check_workflow_routing.mjs
```

`check_workflow_runtime.mjs` locks the first pure snapshot resolver contract: integrated Shewanella Compare uses the GECKO run, Analysis/Summary use the trigger run, Compare subview yields a `model_compare_pair` refresh intent, Summary yields trigger Analysis/Verify refresh intents, and plain runs do not receive invented case defaults.

## Browser smoke

默认稳定模式是 HTTP/API smoke：

```powershell
node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log
```

它检查 app shell、核心 API、optional `/api/files` 语义和五个正式 hash route，但不等同于完整视觉 QA。

严格浏览器模式：

```powershell
node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --strict-browser --json-output .tmp\browser_smoke_strict.json --append-log
```

如果本机 Edge/CDP 不可用，应记录失败原因，不把 HTTP/API smoke 冒充完整浏览器 QA。

## in-app Browser 手动 QA

视觉和交互最终以 in-app Browser 手动 QA 为准。每轮 UI 改动至少检查：

- Resource Atlas：Landscape Map、lens chips、Results Drawer、Decision Inspector。
- Input：资源图谱 / 上传数据切换、Upload Run Package、case story、role preview。
- Model Generator：Model & Omics Dossier、Method Workbench、Compare 入口。
- Model Compare：左右双网络、sync submap、左右 submap selectors、Modification Dashboard、Legend、detail Sheet。
- Analysis：method registry、selected method inspector、Preview Analysis、Run Analysis、Open Summary。
- Summary：STAGE 04 / SUMMARY、case story、QA matrix、missing items。

验收标准：

- 页面非空。
- 无 Vite / React error overlay。
- Console 无关键 error。
- 关键控件可交互。
- 1366 x 768 下不溢出、不遮挡、不出现超大按钮。

## Model Compare 必跑项

Model Compare、Model Generator edit provenance 或 case demo 改动后必须检查：

```powershell
.venv\Scripts\python.exe tools\refresh_case_edit_provenance.py --case-id all --mode inferred_legacy
.venv\Scripts\python.exe -m pytest tests\test_model_generation.py tests\test_variant_comparison.py tests\test_enzyme_constraints.py tests\test_fastapi_api.py -q
```

还需要对三个 case 调用默认 pair summary，确认：

- `model_edit_diff_index` 存在。
- `edit_context_summary` 存在。
- `network_graphs.reference_edit` / `target_edit` 存在。
- 缺 capacity/FVA/validation 时显示状态标签，不显示误导性 `0`。

## QA 记录

- `docs/QA_LOG.md` 记录每轮 smoke / manual QA 结果。
- `docs/TECH_DEBT_REGISTER.md` 记录失败项、已知风险和后续动作。
- 失败截图默认放在 `paper/ui_qa/`，不要散落在根目录。
## Resource Lineage Atlas 必测项

Resource Atlas / lineage tree 改动后至少检查：

```powershell
cd D:\generate\frontend
npm.cmd run typecheck
npm.cmd run build
cd D:\generate
.venv\Scripts\python.exe -m py_compile api\resource_atlas_helpers.py api\services.py
```

手动 QA：

- Resource Atlas 第一视觉是物种资源谱系树，而不是搜索列表或 landscape map。
- 顶部 filter bar 可选择 organism、case study、omics type、readiness，并能触发右侧资源条目刷新。
- 点击 species / strain 节点后，该节点展开 Models、Transcriptomics、Proteomics、Metabolomics、kcat、Annotation 子节点。
- 点击资源类型子节点后，右侧 Resource entries 只显示该物种对应类型资源。
- `Indexed microbes` fallback 分组存在；不要出现 `unclaimed` 文案。
- 0 资源子节点弱化显示，不隐藏，也不显示为 ready。
- 右侧 Inspector 固定展示 Evidence Stack、Readiness Summary、Method Readiness、Workflow Actions。
- Resource Landscape Map、Advanced search、Deep Dive 默认是折叠辅助区，展开后功能不退化。
- 1366 x 768 下主树、右侧 Inspector、资源条目列表不溢出。

## Shewanella Trigger Round 2F 必跑项

修改 `shewanella_transcriptional_triggers_lac_lb`、Paper Reproduction Workbench、Model Compare evidence overlay 或报告出口后，至少运行：

```powershell
D:\generate\.venv\Scripts\python.exe -m py_compile omics_router\report_builder.py api\services.py api\main.py
D:\generate\.venv\Scripts\python.exe -m pytest tests\test_report_builder.py tests\test_fastapi_api.py -k "paper_reproduction or analysis_summary or report"
cd D:\generate\frontend
npm.cmd run typecheck
npm.cmd run build
```

手动 QA：

- Analysis 显示 Growth State Map、Trigger Timeline、GDM-lite、D2T2 reported triggers、dFBA/glycogen scenario。
- Model Compare 默认 pair 为 `baseline_gem__all` vs `paper_evidence_context__lac_transition`。
- 默认叙事 group 为 `nitrogen_glycogen_coupling`；若 GPR 映射不足，必须显示 reaction-level unavailable guidance，不强行生成反应。
- 只有真实 GPR 映射 reaction 显示蓝色 paper evidence overlay。
- Summary 可生成 `shewanella_trigger_reproduction_report`，并能打开 `shewanella_trigger_reproduction_report.html`。
- 报告必须明确：D2T2 是 `paper_reported_only`，dFBA/glycogen 是 `paper_reported_model_prediction_available`，bounds 是 `not_generated`，enzyme capacity 是 `not_applicable`。
## Case Context Contract

When changing case/stage/run routing, composite case defaults, or Shewanella integrated case behavior, run:

```powershell
node tools\check_case_context.mjs
```

This locks only demo-critical fields: stage-to-run mapping, GECKO Compare default pair, `kegg_pathway / rn00020` default scope, trigger Analysis workbench, and trigger report preset. It does not lock story copy, readiness text, dashboard numbers, or generated report HTML.

## Model Compare Workspace Contract

When changing Model Compare pair selection, annotation group selection, graph loading, dashboard metrics, legend semantics, or Shewanella demo defaults, run:

```powershell
node tools\check_model_compare_workspace.mjs
node tools\check_case_context.mjs
node tools\check_workflow_routing.mjs
cd frontend
npm.cmd run typecheck
npm.cmd run build
```

`check_model_compare_workspace.mjs` locks the pure workspace resolver contract: Shewanella integrated uses `baseline_gem__all -> enzyme_gecko__higho2`, GECKO scope defaults to `kegg_pathway / rn00020`, trigger paper scope defaults to `custom_annotation / nitrogen_glycogen_coupling`, user pair/group choices override case defaults, graph loading/missing/error states carry guidance, and unavailable capacity is not displayed as numeric `0`.

## Analysis Workspace Contract

When changing Analysis/Summary paper reproduction context, trigger report presets, or Shewanella trigger reproducibility status decisions, run:

```powershell
node tools\check_analysis_workspace.mjs
node tools\check_case_context.mjs
node tools\check_workflow_routing.mjs
cd frontend
npm.cmd run typecheck
npm.cmd run build
```

`check_analysis_workspace.mjs` locks only necessary facts: integrated Shewanella Analysis/Summary use `shewanella_transcriptional_triggers_case`, the paper workbench is active, Summary uses `shewanella_trigger_reproduction_report`, GDM is `computed_lite`, D2T2 is `paper_reported_only`, dFBA/glycogen is `paper_reported_model_prediction_available`, bounds are `not_generated`, and enzyme capacity is `not_applicable`. It does not lock UI wording, artifact counts, chart row counts, or report HTML content.

## Resource Lineage Tree Contract

When changing Resource Atlas biological placement, broad resource categories, empty species visibility, lineage node selection targets, or tree resolver inputs, run:

```powershell
node tools\check_resource_lineage_tree.mjs
cd frontend
npm.cmd run typecheck
npm.cmd run build
```

`check_resource_lineage_tree.mjs` locks only semantic decisions: key organism placement, hidden empty species by default, four primary categories, two support categories, species/category selection targets, and no-resource debug behavior. It does not lock pixel layout, SVG edge geometry, scroll rail position, zoom styling, image URLs, or displayed counts.

## Run Package Resolver Contract

When changing backend run package inventory, stage readiness, variant context, optional evidence semantics, case readiness inputs, or run overview internals, run:

```powershell
D:\generate\.venv\Scripts\python.exe -m py_compile api\run_package_resolver.py api\services.py api\main.py
D:\generate\.venv\Scripts\python.exe tools\check_run_package_resolver.py
D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "run_package or case_study or analysis_summary"
```

`check_run_package_resolver.py` locks only backend facts: missing packages return a missing context, toy packages expose variants/edit provenance/reports, missing variant registry degrades Generate/Compare readiness, optional capacity artifacts do not become misleading numeric `0`, Shewanella GECKO variants/edit provenance are detected, and the Shewanella trigger paper/report context is recognized. It does not lock copy, exact artifact counts, report HTML, file ordering, or UI labels.

## Resource Curation Workspace Contract

When changing persistent Atlas curation drafts, curated-file previews, identifier mapping, stage eligibility, mapping artifacts, or the `api/services.py` compatibility adapter, run:

```powershell
D:\generate\.venv\Scripts\python.exe -m py_compile api\resource_curation_workspace.py api\services.py api\main.py
D:\generate\.venv\Scripts\python.exe tools\check_resource_curation_workspace.py
D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "resource_curation" -q
```

`check_resource_curation_workspace.py` exercises the deep module interface directly on a temporary local filesystem. It locks create/query/execute ordering, ready versus partial curated files, version-pointer/mirror rollback, stale mapping invalidation and remapping, mapping-generation failure detection, atomic Workspace creation, stage artifacts, published-path rewriting, duplicate/named-file errors, list-valued resource-id semantics, injected staging-failure recovery, publish-race ownership, symlink boundaries, and the absence of `run_overview` from the module result. HTTP tests freeze the six compatibility response key sets, legacy curated-file path projection, status/error semantics, and the adapter-added overview.
