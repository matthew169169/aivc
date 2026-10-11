# QA Log

## 2026-06-26 Shewanella Integrated Case Routing

- Scope: added visible composite case `shewanella_integrated_overview`.
- Case list: pass. Default `/api/case-studies` exposes one visible Shewanella entry; `shewanella_gecko_oxygen` and `shewanella_transcriptional_triggers_lac_lb` remain direct-readiness source cases.
- Backend readiness: pass. Integrated ladder maps Input/Generator/Compare to `shewanella_gecko_case` and Analysis/Summary to `shewanella_transcriptional_triggers_case`.
- Report index: pass. Integrated readiness can write `report_results/shewanella_integrated_showcase_index.html` linking existing GECKO and trigger-paper outputs without merging run packages.
- Frontend checks: pass. `npm.cmd run typecheck` and `npm.cmd run build` completed; build still reports the existing large chunk warning.
- Backend tests: pass. `pytest tests/test_fastapi_api.py -k "case_study or analysis_summary" -q` passed.

## 2026-06-23 第二轮工程治理

### 已完成修改

- 新增 `docs/README.md`，作为工程文档导航入口。
- 新增 `docs/RECOVERY_AND_BACKUP.md`，记录 `.git` 不可用、quarantine 恢复方式和禁止直接删除的目录。
- 新增 `docs/CLEANUP_DEPENDENCY_AUDIT.md`，对 `.runtime_cache`、`.tmp`、`tmp`、`desktop_staging`、`desktop_dist`、`desktop_installer` 做只读依赖审计。
- 前端新增 `frontend/src/domain/caseReadiness.ts` 和 `frontend/src/domain/compareEvidence.ts`，集中 case 状态和 Model Compare 缺失 evidence 文案。
- 后端扩展 `api/status_semantics.py`，集中 case status 与 behavior support status；`api/services.py` 保留兼容 wrapper。
- 第二轮测试后生成的 `.pytest_cache` 和源码目录 `__pycache__` 已归档到 `_cleanup_quarantine/20260623/post_check_python_cache_round2/`。

### 已通过自动检查

```powershell
D:\generate\.venv\Scripts\python.exe -m py_compile api\services.py api\status_semantics.py
cd D:\generate\frontend
npm.cmd run typecheck
npm.cmd run build
cd D:\generate
D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py
D:\generate\.venv\Scripts\python.exe -m pytest tests\test_resource_harvest_tools.py tests\test_fastapi_api.py -k "resource or harvest"
D:\generate\.venv\Scripts\python.exe -m pytest tests\test_variant_comparison.py tests\test_enzyme_constraints.py
D:\generate\.venv\Scripts\python.exe -m pytest tests\test_upload_workflow.py tests\test_fastapi_api.py
```

结果：

- `typecheck`：通过。
- `build`：通过；仍有 Vite chunk size warning，属于既有性能优化项。
- `test_fastapi_api.py`：34 passed。
- resource/harvest 子集：21 passed, 22 deselected。
- variant comparison + enzyme constraints：10 passed, 2 warnings。
- upload workflow + API：43 passed。
- UTF-8 / mojibake marker 扫描：39 个 markdown 文件无配置 marker 命中。

### 待执行浏览器 QA

- Resource Atlas：地图入口、筛选、Results Drawer、Decision Inspector。
- Model Generator：Dossier、Method Workbench、Compare 切换。
- Model Compare：Difference Map、默认 pair、缺失 evidence 状态。
- Summary：case story、QA matrix、missing items。

### 当前风险

- `.git` 目录存在但不可用；正式大改前需要外部目录级备份。
- README 仍包含历史长文和部分旧编码段落；本轮只补当前入口，不做整篇重写。
- `.runtime_cache`、`.tmp`、`desktop_*` 目录体积较大但有运行引用，本轮不移动。

## 2026-06-23 第三轮工程治理：浏览器 QA 与 README/组件拆分

### 已完成修改

- 根目录 `README.md` 已精简为当前工程入口文档。
- 旧 README 长文已归档到 `docs/LEGACY_README_ARCHIVE.md`。
- `docs/README.md` 已补充 Legacy README 链接。
- 前端新增 `frontend/src/features/resource-atlas/`：
  - `resourceLandscapeAdapter.ts`
  - `ResourceLandscapeMap.tsx`
- 前端新增 `frontend/src/features/model-generator/GeneratorPanels.tsx`。
- `frontend/src/App.tsx` 已改为复用 Resource Atlas map adapter 和 Model Generator 纯展示 panel；状态、API 调用和 workflow 行为保持在 `App.tsx`。
- Summary 页顶部已从旧的 `STAGE 05 / VERIFY & REPORT` 收口为 `STAGE 04 / SUMMARY`；英文 stage copy 已从 `Verify & Report` 收口为 `Summary`。

### 已通过自动检查

```powershell
cd D:\generate\frontend
npm.cmd run typecheck
npm.cmd run build
cd D:\generate
D:\generate\.venv\Scripts\python.exe -m py_compile api\services.py api\status_semantics.py
D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py
D:\generate\.venv\Scripts\python.exe -m pytest tests\test_resource_harvest_tools.py tests\test_fastapi_api.py -k "resource or harvest"
D:\generate\.venv\Scripts\python.exe -m pytest tests\test_variant_comparison.py tests\test_enzyme_constraints.py
D:\generate\.venv\Scripts\python.exe -m pytest tests\test_upload_workflow.py tests\test_fastapi_api.py
```

结果：

- `typecheck`：通过。
- `build`：通过；仍有既有 Vite chunk size warning。
- `test_fastapi_api.py`：34 passed。
- resource/harvest 子集：21 passed, 22 deselected。
- variant comparison + enzyme constraints：10 passed, 2 warnings。
- upload workflow + API：43 passed。
- README / docs UTF-8 与链接检查：通过；未发现配置的 mojibake marker。

### 浏览器 QA

执行方式：

- 优先尝试 in-app Browser；Browser runtime 可初始化，但文档输出在当前会话中被截断，因此本轮使用 Playwright + 系统 Microsoft Edge fallback。
- Playwright 自带浏览器未安装；未联网下载浏览器，改用本机 `C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`。
- 视口：1366 x 768。

结果：

| 路径 | 结果 | 备注 |
| --- | --- | --- |
| Resource Atlas / Input | pass | 页面非空，能进入 Input/Atlas 区域。 |
| Model Generator | pass | Dossier 与 Method Workbench 可见。 |
| Model Compare | pass with notes | Difference / Compare 工作区可见；P. putida case 仍有一处 `ENZYME CAPACITY 0` 表达，需要后续按缺失证据语义收口。 |
| Summary | pass | 已显示 `STAGE 04 / SUMMARY`，旧 `STAGE 05 / VERIFY & REPORT` 不再出现。 |

浏览器错误：

- 无 React/Vite error overlay。
- 无 pageerror。
- 控制台存在若干 `404 Not Found`，来源为可选 evidence 文件探测，例如 P. putida 的 `reaction_enzyme_capacity.csv`、`kcat_priors.csv`、`reaction_kegg_pathway_assignment.csv`。这些不阻断页面，但会污染 QA 控制台，已登记为技术债。

### 本轮归档

- 测试后重新生成的 `.pytest_cache` 与源码目录 `api/omics_router/tools/tests` 下的 `__pycache__` 已归档到 `_cleanup_quarantine/20260623/post_check_python_cache_round3/`。

## 2026-06-23 Model Compare 缺失证据与 optional probe 收口 QA

### 已完成修改
- `/api/files` 新增 `optional=1` 探测模式：普通缺失文件仍返回 `404`；可选 evidence 缺失返回 `optional_missing` JSON，不再污染浏览器 console。
- 前端 `loadCsvRowsFromFile` 增加 optional 读取路径；kcat、capacity、pathway assignment 等探索性 evidence 文件使用静默缺失语义。
- Model Compare 的 enzyme capacity 统计统一为“真实 artifact 可用才显示数字”；P. putida / Synechocystis 这类外部 ecModel 未完成状态不再显示误导性 `0`。
- 新增 `tools/run_browser_smoke_qa.mjs`，用于固定 smoke QA；当前本机 Edge CDP 会在第一条命令后 reset，脚本保留为后续自动化入口，真实浏览器 QA 本轮通过 in-app Browser 完成。

### 已通过自动检查
```powershell
cd D:\generate\frontend
npm.cmd run typecheck
npm.cmd run build
cd D:\generate
D:\generate\.venv\Scripts\python.exe -m py_compile api\main.py api\services.py api\status_semantics.py
D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py tests\test_variant_comparison.py tests\test_enzyme_constraints.py
```

结果：
- `typecheck`：通过。
- `build`：通过；仍有既有 Vite chunk size warning。
- `py_compile`：通过。
- `pytest`：44 passed, 2 warnings。
- optional `/api/files` smoke：`optional=1` 缺失返回 `optional_missing`；严格模式缺失仍返回 `404`。

### 浏览器 QA

执行方式：
- 使用 Codex in-app Browser，目标 URL 为 `http://127.0.0.1:5173`。
- 视口为默认桌面视口；检查四条主路径。

结果：

| 路径 | 结果 | 备注 |
| --- | --- | --- |
| Resource Atlas / Input | pass | 页面非空；Input 上传模式与 case readiness 可见；无 Vite/React overlay。 |
| Model Generator | pass | `Model & Omics Dossier` 与 `Method Workbench` 可见；case story 与 readiness 可见。 |
| Model Compare | pass | 默认 pair 为 `baseline_gem__all vs consensus_context__all`；未发现 `ENZYME CAPACITY 0`；console 无 error/warn。 |
| Summary | pass | 显示 `STAGE 04 / SUMMARY`；未出现旧 `STAGE 05 / VERIFY & REPORT`；case story / readiness 可见。 |

### 当前技术债
- `tools/run_browser_smoke_qa.mjs` 的 Edge CDP 自动化在当前本机返回 `CDP websocket closed (1006 read ECONNRESET)`；真实 QA 已用 in-app Browser 通过，脚本需要后续改为 Playwright/Browser runtime 或稳定 fallback。

## 2026-06-23T13:33:21.707Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: system-edge-cdp-failed-http-fallback
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- Browser CDP smoke failed: CDP websocket closed (1006 read ECONNRESET)

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP fallback checked app shell plus atlas summary API. |
| Model Generator | pass | HTTP fallback checked hash route shell availability. |
| Model Compare | pass | HTTP fallback checked optional file probe semantics. |
| Summary | pass | HTTP fallback checked summary hash route shell availability. |

# 2026-06-26 Shewanella Integrated Case Routing

- Scope: Added visible composite case `shewanella_integrated_overview`.
- Case list: pass. Default `/api/case-studies` now exposes one visible Shewanella entry; `shewanella_gecko_oxygen` and `shewanella_transcriptional_triggers_lac_lb` remain direct-readiness source cases.
- Backend readiness: pass. Integrated ladder maps Input/Generator/Compare to `shewanella_gecko_case` and Analysis/Summary to `shewanella_transcriptional_triggers_case`.
- Report index: pass. Integrated readiness can write `report_results/shewanella_integrated_showcase_index.html` linking existing GECKO and trigger-paper outputs without merging run packages.
- Frontend checks: pass. `npm.cmd run typecheck` and `npm.cmd run build` completed; build still reports the existing large chunk warning.
- Backend tests: pass. `pytest tests/test_fastapi_api.py -k "case_study or analysis_summary" -q` passed.

Console errors:
- none

## 2026-06-23 App.tsx Adapter Split Manual QA

- URL: `http://127.0.0.1:5173`
- Scope: Input, Model Generator, Model Compare, Analysis, Summary
- Result: pass

| Path | Status | Evidence |
| --- | --- | --- |
| Input | pass | Upload Run Package、资源图谱、上传数据均可见；无 framework overlay。 |
| Model Generator | pass | Model & Omics Dossier、Method Workbench、模型生成切换均可见。 |
| Model Compare | pass | Difference / Constraint / Behavior / Side-by-side 可见；点击“行为信号”后 active 状态正确切换。 |
| Analysis | pass | 方法注册表与方法详情可见；点击 Evidence comparison 后 inspector 更新为对应方法。 |
| Summary | pass | `STAGE 04`、Summary、总结均可见。 |

Console errors:
- none

Notes:
- Browser screenshot capture timed out once during QA; DOM checks, interaction checks, HTTP/API smoke, typecheck, build, and backend regression all passed.

404 responses:
- none

## 2026-06-28T15:18:00+08:00 Resource Atlas Biological Lineage Tree Fix

- Rebuilt the Resource Atlas lineage resolver around `Root -> Cellular organisms -> Domain -> Major lineage -> Species/strain -> Resource summary`.
- Cyanobacteria is now explicitly under Domain Bacteria; Fungi stays under Eukaryota; uncertain organisms are routed to taxonomy placement warnings.
- Resource summary categories are now `Models / Transcriptomics / Proteomics / Metabolomics / Other evidence`.
- Tree connectors now use SVG curved hierarchical paths instead of CSS pseudo-element lines.
- The lineage drawer now receives tree selection context and shows taxonomy-layer overview cards for Root/Cellular/Domain/Clade selections.
- Checks passed: `node tools\check_resource_lineage_tree.mjs`, `node tools\check_model_compare_workspace.mjs`, `node tools\check_case_context.mjs`, `node tools\check_workflow_routing.mjs`, `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`, `npm.cmd run typecheck`, `npm.cmd run build`.
- Mojibake marker scan over Resource Atlas lineage files returned no matches.
- In-app Browser visual QA: after starting the full local app and clicking Refresh, the page rendered 1 root node, 1 Cellular organisms node, 3 domain nodes, 8 clade nodes, 41 species nodes, and 99 SVG tree edges; clicking Cellular organisms opened the right drawer and rendered a taxonomy overview card. A later Browser reconnect attempt timed out, so full desktop/mobile screenshot QA remains a follow-up.

## 2026-06-25 Shewanella Trigger Round 2 Data Reproduction

- Download/parse: pass. `tools/prepare_shewanella_trigger_round2.py --force-download` downloaded Oxford/NAR Supplementary Data and GEO `GSE25821` processed matrix; raw CEL files were not downloaded.
- Parsed artifacts: `processed_expression_timecourse.csv` 424,704 rows; `gdm_lite_results.csv` 10,112 rows; `d2t2_trigger_genes.csv` 720 rows; `dfba_glycogen_scenario.csv` 1,020 rows.
- API status: pass. `/api/runs/shewanella_transcriptional_triggers_case/analysis/summary` reports `partial_computed_lite`; Growth State Map is `computed_lite`; Trigger Timeline is `parsed_supplementary`.
- Algorithm boundaries: GDM is `computed_lite`; D2T2 is `paper_reported_only`; dFBA/glycogen is `paper_reported_model_prediction_available`; condition bounds are `not_generated`; enzyme capacity is `not_applicable`.
- Regression: `npm.cmd run typecheck`, `npm.cmd run build`, and `pytest tests/test_fastapi_api.py tests/test_upload_workflow.py tests/test_variant_comparison.py tests/test_enzyme_constraints.py -q` passed.

## 2026-06-25 Shewanella Trigger Round 2D Visualization

- Data refresh: pass. `tools/prepare_shewanella_trigger_round2.py --offline` regenerated chart-friendly JSON from already downloaded Supplement/GEO files without downloading raw CEL data.
- Chart artifacts: `growth_state_map_data.json` now includes growth curves and a 42 x 42 correlation matrix; `trigger_timeline_data.json` includes selected metabolite/glycogen/O2 series; `gdm_lite_results.json` includes class comparison and `gene_mapping_partial`; `dfba_glycogen_scenario.json` includes four paper-reported model-prediction scenarios.
- UI implementation: pass. Analysis workbench now has SVG/CSS panels for Growth State Map, Trigger Timeline, GDM-lite, D2T2 reported triggers, and dFBA/glycogen scenarios. Summary card includes algorithm reproducibility status strip.
- Boundary checks: no fake condition bounds, trigger scores, fresh solver dFBA, or enzyme capacity were generated.
- Verification: `npm.cmd run typecheck`, `npm.cmd run build`, `py_compile`, `pytest tests/test_fastapi_api.py -k "paper_reproduction or analysis_summary" -q`, and full backend regression passed.
- Browser smoke: HTTP/API smoke passed. In-app Browser visual check reached the Analysis route, but that browser session showed API offline/unselected-run state, so it was not counted as full rendered visual QA for the paper workbench.

## 2026-06-25 Shewanella Trigger Round 1B UI

- Scope: Added the Shewanella transcriptional trigger paper reproduction workbench to Analysis, the paper reproduction status card to Summary, and the required data checklist to Input.
- Guardrail: Missing supplementary expression/metabolite inputs are shown as guarded empty states and data requirements; no fake GDM/D2T2/dFBA curves, trigger scores, bounds changes, or enzyme capacity values were added.
- Backend contract: `paper_reproduction.status` remains `partial_missing_supplementary_data`; key files include `paper_reproduction_manifest`, `data_needed_manifest`, and `pathway_evidence_groups`.
- Checks:
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "case_study or analysis_summary or paper_reproduction" -q` passed.
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py tests\test_upload_workflow.py tests\test_variant_comparison.py tests\test_enzyme_constraints.py -q` passed, 54 tests.
  - `npm.cmd run typecheck` passed.
  - `npm.cmd run build` passed.
  - `node tools\check_workflow_routing.mjs` passed.
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log` passed in HTTP/API smoke mode.

## 2026-06-25 Shewanella transcriptional trigger case scaffold

- Added case `shewanella_transcriptional_triggers_lac_lb` with run package `shewanella_transcriptional_triggers_case`.
- Input/Generator scaffold: ready; staged iLJ1162 plus paper-reported trigger/pathway annotations.
- Analysis/Summary scaffold: partial; `paper_reproduction_manifest`, `data_needed_manifest`, Growth State Map, Trigger Timeline, Pathway Evidence Map, GDM/D2T2/dFBA guarded artifacts are present.
- Compare: guarded partial; default pair is `baseline_gem__all` vs `paper_evidence_context__lac_transition`, but no real variant comparison graph or generated LAC context model exists yet.
- Boundary: no supplementary expression/metabolite tables were found locally, so no GDM, D2T2, dFBA, condition bounds, glycogen curves, or enzyme capacity were fabricated.

## 2026-06-25T17:19:04+08:00 Resource Atlas Taxonomy Tree Visual QA

- URL: http://127.0.0.1:5173/#/module-input
- Viewport: in-app Browser default
- Browser: in-app Browser manual QA
- Flow: Input -> Resource Atlas -> Biological taxonomy resource lineage tree

| Check | Status | Note |
| --- | --- | --- |
| Biological branch labels | pass | Main branches show Bacteria, Eukaryota, Archaea and clades such as Pseudomonadota, Bacillota, Actinomycetota, Cyanobacteria, Fungi/Yeast, Algae, Mammalian/Human, Protist/Parasite. |
| Legacy application branches removed | pass | No visible Industrial Chassis, Industrial Eukaryotic, or Human Pathogens / Drug Target branch labels in the tree. |
| Tree-first layout | pass | Tree panel occupied about 95% of the Resource Atlas main layout with the right inspector collapsed to a narrow rail. |
| Canvas size | pass | Tree scroll area rendered at 660 px high with a wide internal canvas; horizontal overflow stayed inside the tree region. |
| Console health | pass | No relevant browser console warnings or errors were reported during the check. |

## 2026-06-25 Resource Atlas lineage tree visual QA

- Scope: Resource Atlas biological lineage tree main canvas.
- Result: pass.
- Checks:
  - Draw_Trees root and classification branches render as the main tree skeleton.
  - Legacy accordion/flex card stacking nodes are not present in the main tree DOM.
  - 60 small species nodes and 60 resource summary child nodes are rendered from Draw_Trees plus indexed cache organisms.
  - Resource summary expansion uses broad categories only: Model, Transcriptomics, Proteomics, Metabolomics, Enzyme/kcat, Annotation/Metadata.
  - 1366 x 768 viewport has no document-level horizontal overflow; tree scrolling is contained inside the canvas.

## 2026-06-25 Resource Lineage Atlas implementation smoke

- Scope: Resource Atlas tree-first UI, Species Resource Inspector, collapsed Landscape/Search/Deep Dive support panels.
- Changed files: `frontend/src/App.tsx`, `frontend/src/features/resource-atlas/SpeciesResourceLineageTree.tsx`, `frontend/src/features/resource-atlas/ResourceAtlasPanels.tsx`, `frontend/src/styles.css`, `api/resource_atlas_helpers.py`, `docs/RESOURCE_ATLAS_SPEC.md`.
- `npm.cmd run typecheck`: pass.
- `npm.cmd run build`: pass. Vite reported the existing large chunk warning only.
- `python -m py_compile api/resource_atlas_helpers.py api/services.py`: pass.
- Manual browser QA: not run in this pass; still needed to visually verify the tree layout, right-side scrolling, and resource-type child node interactions at 1366 x 768.

## 2026-06-25 Model Compare Side-by-side Final QA

- Scope: case edit provenance refresh, pair API contract, side-by-side Model Compare visual smoke.
- Static checks: `py_compile` passed for `omics_router/model_edit.py`, `api/services.py`, `api/main.py`, and `tools/refresh_case_edit_provenance.py`.
- Frontend checks: `npm.cmd run typecheck` passed; `npm.cmd run build` passed with the existing Vite chunk-size warning only.
- Backend regression: `tests/test_model_generation.py tests/test_variant_comparison.py tests/test_enzyme_constraints.py tests/test_fastapi_api.py -q` passed: 56 passed, 2 warnings.
- Route/API smoke: `node tools/run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp/browser_smoke_latest.json --append-log` passed.
- Strict browser mode: Edge CDP disconnected with `ECONNRESET`; recorded as browser runtime limitation, not an app failure.
- In-app Browser visual QA: direct `#/module-model-comparison` loaded the new side-by-side Compare page. After data hydration it selected `putida_acetate_isoprenol_case` with `baseline_gem__all` vs `consensus_context__all`; reference and target network panes were ready; dashboard and legend were visible; old Difference/Constraint/Behavior/Ranking labels were absent; `ENZYME CAPACITY 0` was not present.
- Console: no critical browser errors observed. Radix Select emitted controlled/uncontrolled warnings; keep as UI polish debt.
- Case pair smoke: Shewanella and P. putida default pairs returned ready edit graph data; Synechocystis returned edit context with graph `needs_filtering`, which is expected guarded guidance for that case.

## 2026-06-25 Model Compare Side-by-side 收尾 QA

- Scope: model edit provenance backfill, pair API contract, side-by-side Compare readiness.
- Added `tools/refresh_case_edit_provenance.py` for safe case-study edit provenance refresh.
- Refreshed case edit provenance:
  - Shewanella: `16752` edit rows, `inferred_legacy`.
  - P. putida: `5854` edit rows, `inferred_legacy`.
  - Synechocystis: `1726` edit rows, `inferred_legacy`.
- Pair summary smoke:
  - Shewanella: ready, `2094` scoped edit rows, reference/target edit graphs completed.
  - P. putida: ready, `2927` scoped edit rows, reference/target edit graphs completed.
  - Synechocystis: partial graph status `needs_filtering`, `863` scoped edit rows, edit context ready.
- Checks passed:
  - `py_compile` for touched backend modules and refresh tool.
  - `tests/test_model_generation.py` provenance refresh test.
  - pair API contract assertions for `model_edit_diff_index`, `edit_context_summary`, `reference_edit`, and `target_edit`.
- Notes:
  - Browser visual QA still needs an in-app Browser pass for final layout polish; HTTP/API smoke remains useful but is not a visual substitute.

## 2026-06-24 Backend Run Package Lifecycle Manifest Helper Refactor

- Scope: backend run package helper boundary.
- Changed: import, archive, and restore manifest payload shaping now lives in `api/run_package_helpers.py`.
- Kept in `api/services.py`: `_write_import_manifest`, `_write_archive_manifest`, `_write_restore_manifest`, timestamp generation, `write_json`, file IO, and endpoint-facing compatibility wrappers.
- Docs: updated `docs/ARCHITECTURE.md` with the manifest payload boundary.
- Checks passed:
  - `D:\generate\.venv\Scripts\python.exe -m py_compile api\services.py api\file_artifact_helpers.py api\run_package_helpers.py api\main.py`
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "files or resource or health"` (12 passed)
  - `cd frontend && npm.cmd run typecheck`
  - `node tools\check_workflow_routing.mjs`
  - `node --check tools\run_browser_smoke_qa.mjs`
  - `cd frontend && npm.cmd run build` (passed with existing Vite chunk-size warning)
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`
  - Standard mojibake marker scan over touched backend/docs files (no matches)

## 2026-06-24 Backend Run Package Action Result Helper Refactor

- Scope: backend run package helper boundary.
- Changed: import, archive, and restore action result payload shaping now lives in `api/run_package_helpers.py`.
- Kept in `api/services.py`: source/target validation, copy/move operations, manifest writing, run overview enrichment, and job orchestration.
- Docs: updated `docs/ARCHITECTURE.md` with the action result payload boundary.
- Checks passed:
  - `D:\generate\.venv\Scripts\python.exe -m py_compile api\services.py api\file_artifact_helpers.py api\run_package_helpers.py api\main.py`
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "run_package or archived or archive or restore"` (6 passed)
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py` (34 passed)
  - `cd frontend && npm.cmd run typecheck`
  - `node tools\check_workflow_routing.mjs`
  - `node --check tools\run_browser_smoke_qa.mjs`
  - `cd frontend && npm.cmd run build` (passed with existing Vite chunk-size warning)
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`
  - Standard mojibake marker scan over touched backend/docs files (no matches)

## 2026-06-24 Backend Run Package Job Log Helper Refactor

- Scope: backend run package helper boundary.
- Changed: archive and restore job log header/result line shaping now lives in `api/run_package_helpers.py`.
- Kept in `api/services.py`: sync job callbacks, log file writes, archive/restore execution, and job result return shape.
- Docs: updated `docs/ARCHITECTURE.md` with the job log helper boundary.
- Checks passed:
  - `D:\generate\.venv\Scripts\python.exe -m py_compile api\services.py api\file_artifact_helpers.py api\run_package_helpers.py api\main.py`
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "archive or restore or run_package"` (6 passed)
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py` (34 passed)
  - `cd frontend && npm.cmd run typecheck`
  - `node tools\check_workflow_routing.mjs`
  - `node --check tools\run_browser_smoke_qa.mjs`
  - `cd frontend && npm.cmd run build` (passed with existing Vite chunk-size warning)
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`
  - Standard mojibake marker scan over touched backend/docs files (no matches)

## 2026-06-24 Backend Run Package Manifest Response Helper Refactor

- Scope: backend run package helper boundary.
- Changed: import and archived manifest response shaping now lives in `api/run_package_helpers.py`.
- Kept in `api/services.py`: active run resolution, archived run resolution, JSON manifest reads, and endpoint-facing wrapper functions.
- Docs: updated `docs/ARCHITECTURE.md` with the manifest response helper boundary.
- Checks passed:
  - `D:\generate\.venv\Scripts\python.exe -m py_compile api\services.py api\file_artifact_helpers.py api\run_package_helpers.py api\main.py`
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "manifest or archive or import or restore or run_package"` (8 passed)
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py` (34 passed)
  - `cd frontend && npm.cmd run typecheck`
  - `node tools\check_workflow_routing.mjs`
  - `node --check tools\run_browser_smoke_qa.mjs`
  - `cd frontend && npm.cmd run build` (passed with existing Vite chunk-size warning)
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`
  - Standard mojibake marker scan over touched backend/docs files (no matches)

## 2026-06-24 Backend Workspace Helper Refactor

- Scope: backend workspace helper boundary.
- Changed: workspace status and default project row response shaping now lives in `api/workspace_helpers.py`.
- Kept in `api/services.py`: workspace config reads, root switching, directory initialization, path creation, access checks, and endpoint-facing wrapper functions.
- Docs: updated `docs/ARCHITECTURE.md` with the workspace helper boundary.
- Checks passed:
  - `D:\generate\.venv\Scripts\python.exe -m py_compile api\services.py api\workspace_helpers.py api\file_artifact_helpers.py api\run_package_helpers.py api\main.py`
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "workspace or project or health"` (7 passed)
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py` (34 passed)
  - `cd frontend && npm.cmd run typecheck`
  - `node tools\check_workflow_routing.mjs`
  - `node --check tools\run_browser_smoke_qa.mjs`
  - `cd frontend && npm.cmd run build` (passed with existing Vite chunk-size warning)
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`
  - Standard mojibake marker scan over touched backend/docs files (no matches)

## 2026-06-24 Backend Workspace Path Helper Refactor

- Scope: backend workspace helper boundary.
- Changed: workspace path candidate normalization and workspace config payload shaping now live in `api/workspace_helpers.py`.
- Kept in `api/services.py`: missing path errors, existence/is-dir validation, optional directory creation, workspace root mutation, and persistence writes.
- Docs: updated `docs/ARCHITECTURE.md` with the workspace path/config helper boundary.
- Checks passed:
  - `D:\generate\.venv\Scripts\python.exe -m py_compile api\services.py api\workspace_helpers.py api\file_artifact_helpers.py api\run_package_helpers.py api\main.py`
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "workspace or project or health or run_package"` (9 passed)
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py` (34 passed)
  - `cd frontend && npm.cmd run typecheck`
  - `node tools\check_workflow_routing.mjs`
  - `node --check tools\run_browser_smoke_qa.mjs`
  - `cd frontend && npm.cmd run build` (passed with existing Vite chunk-size warning)
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`
  - Standard mojibake marker scan over touched backend/docs files (no matches)

## 2026-06-24 Backend Resource Atlas Search Helper Refactor

- Scope: backend Resource Atlas helper boundary.
- Changed: Resource Atlas search pagination, resource payload shaping, facet aggregation, and search response shaping now live in `api/resource_atlas_helpers.py`.
- Kept in `api/services.py`: resource index loading, organism/model/omics filter predicates, deduplication, coverage-by-source lookup, and endpoint-facing wrapper functions.
- Docs: updated `docs/ARCHITECTURE.md` with the Resource Atlas search helper boundary.
- Checks passed:
  - `D:\generate\.venv\Scripts\python.exe -m py_compile api\services.py api\resource_atlas_helpers.py api\workspace_helpers.py api\file_artifact_helpers.py api\run_package_helpers.py api\main.py`
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py tests\test_resource_harvest_tools.py -k "resource or harvest"` (21 passed)
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py` (34 passed)
  - `cd frontend && npm.cmd run typecheck`
  - `node tools\check_workflow_routing.mjs`
  - `node --check tools\run_browser_smoke_qa.mjs`
  - `cd frontend && npm.cmd run build` (passed with existing Vite chunk-size warning)
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`
  - Standard mojibake marker scan over touched backend/docs files (no matches)

## 2026-06-24 Backend Archived Run Overview Helper Refactor

- Scope: backend run package helper boundary.
- Changed: archived run overview row shaping now lives in `api/run_package_helpers.py`.
- Kept in `api/services.py`: `_archived_run_overview` compatibility wrapper, archive manifest reads, path resolution, and endpoint response assembly.
- Docs: updated `docs/ARCHITECTURE.md`.
- Checks passed:
  - `D:\generate\.venv\Scripts\python.exe -m py_compile api\services.py api\file_artifact_helpers.py api\run_package_helpers.py api\main.py`
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "files or resource or health"` (12 passed)
  - `cd frontend && npm.cmd run typecheck`
  - `cd frontend && npm.cmd run build` (existing chunk-size warning only)
  - `node tools\check_workflow_routing.mjs`
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`
  - mojibake marker scan over touched backend/docs files: no matches.

## 2026-06-24 Backend Safe Run Overview Helper Refactor

- Scope: backend run package helper boundary.
- Changed: safe run overview fallback shaping now lives in `api/run_package_helpers.py`.
- Kept in `api/services.py`: `_safe_run_overview` compatibility wrapper, full `run_overview(...)`, and all endpoint-facing call sites.
- Boundary note: `services.py` injects `run_overview`, `read_csv_rows`, and `read_model_variant_registry`.
- Docs: updated `docs/ARCHITECTURE.md`.
- Checks passed:
  - `D:\generate\.venv\Scripts\python.exe -m py_compile api\services.py api\file_artifact_helpers.py api\run_package_helpers.py api\main.py`
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "files or resource or health"` (12 passed)
  - `cd frontend && npm.cmd run typecheck`
  - `cd frontend && npm.cmd run build` (existing chunk-size warning only)
  - `node tools\check_workflow_routing.mjs`
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`
  - mojibake marker scan over touched backend/docs files: no matches.

## 2026-06-24 Backend Run Package Candidate Helper Refactor

- Scope: backend run package helper boundary.
- Changed: run package candidate import status, target path, and count-card row shaping now live in `api/run_package_helpers.py`.
- Changed: safe path equality check is exported from `api/run_package_helpers.py`; `api/services.py` keeps `_same_path` as a compatibility wrapper.
- Kept in `api/services.py`: `_run_package_candidate` wrapper, workspace root access, `_safe_run_overview`, and endpoint response assembly.
- Docs: updated `docs/ARCHITECTURE.md`.
- Checks passed:
  - `D:\generate\.venv\Scripts\python.exe -m py_compile api\services.py api\file_artifact_helpers.py api\run_package_helpers.py api\main.py`
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "files or resource or health"` (12 passed)
  - `cd frontend && npm.cmd run typecheck`
  - `cd frontend && npm.cmd run build` (existing chunk-size warning only)
  - `node tools\check_workflow_routing.mjs`
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`
  - mojibake marker scan over touched backend/docs files: no matches.

## 2026-06-24 Backend Run Package Discovery Path Helper Refactor

- Scope: backend run package helper boundary.
- Changed: known workspace package enumeration and discovery-root candidate path filtering now live in `api/run_package_helpers.py`.
- Kept in `api/services.py`: endpoint-facing candidate status, overview shaping, `_iter_run_packages` compatibility wrapper, and all existing response shapes.
- Docs: updated `docs/ARCHITECTURE.md`.
- Checks passed:
  - `D:\generate\.venv\Scripts\python.exe -m py_compile api\services.py api\file_artifact_helpers.py api\run_package_helpers.py api\main.py`
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "files or resource or health"` (12 passed)
  - `cd frontend && npm.cmd run typecheck`
  - `cd frontend && npm.cmd run build` (existing chunk-size warning only)
  - `node tools\check_workflow_routing.mjs`
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`
  - mojibake marker scan over touched backend/docs files: no matches.

## 2026-06-24 Backend Run ID Helper Refactor

- Scope: backend run package helper boundary.
- Changed: run id sanitization and next-available id selection now live in `api/run_package_helpers.py`.
- Kept in `api/services.py`: `_sanitize_run_id`, `_next_available_run_id`, and `_next_available_archive_id` compatibility wrappers plus existing call sites.
- Docs: updated `docs/ARCHITECTURE.md`.
- Checks passed:
  - `D:\generate\.venv\Scripts\python.exe -m py_compile api\services.py api\file_artifact_helpers.py api\run_package_helpers.py api\main.py`
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "files or resource or health"` (12 passed)
  - `cd frontend && npm.cmd run typecheck`
  - `cd frontend && npm.cmd run build` (existing chunk-size warning only)
  - `node tools\check_workflow_routing.mjs`
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`
  - mojibake marker scan over touched backend/docs files: no matches.

## 2026-06-24 Backend Run Package Helper Refactor

- Scope: backend run package helper boundary.
- Changed: run package marker detection, staged model path discovery, and GECKO export model id lookup now live in `api/run_package_helpers.py`.
- Kept in `api/services.py`: `_looks_like_run_package`, `_run_model_path`, and `_model_id_from_existing_manifest` compatibility wrappers plus existing call sites.
- Boundary note: `services.py` injects existing CSV/JSON readers to avoid helper-to-service imports.
- Docs: updated `docs/ARCHITECTURE.md`.
- Checks passed:
  - `D:\generate\.venv\Scripts\python.exe -m py_compile api\services.py api\file_artifact_helpers.py api\run_package_helpers.py api\main.py`
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "files or resource or health"` (12 passed)
  - `cd frontend && npm.cmd run typecheck`
  - `cd frontend && npm.cmd run build` (existing chunk-size warning only)
  - `node tools\check_workflow_routing.mjs`
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`
  - mojibake marker scan over touched backend/docs files: no matches.

## 2026-06-24 Backend JSON Artifact Discovery Helper Refactor

- Scope: backend file/artifact helper boundary.
- Changed: JSON artifact discovery and status/message row shaping now live in `api/file_artifact_helpers.py`.
- Kept in `api/services.py`: `_collect_json_files` compatibility wrapper plus existing call sites.
- Boundary note: `services.py` injects the existing `read_json_object` function to avoid helper-to-service imports.
- Docs: updated `docs/ARCHITECTURE.md`.
- Checks passed:
  - `D:\generate\.venv\Scripts\python.exe -m py_compile api\services.py api\file_artifact_helpers.py api\main.py`
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "files or resource or health"` (12 passed)
  - `cd frontend && npm.cmd run typecheck`
  - `cd frontend && npm.cmd run build` (existing chunk-size warning only)
  - `node tools\check_workflow_routing.mjs`
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`
  - mojibake marker scan over touched backend/docs files: no matches.

## 2026-06-24 Backend File Summary/Table Preview Helper Refactor

- Scope: backend file/artifact helper boundary.
- Changed: file summary shape and table preview slicing now live in `api/file_artifact_helpers.py`.
- Kept in `api/services.py`: `_file_summary` and `_table_preview` compatibility wrappers plus all existing call sites.
- Boundary note: `services.py` injects the existing `read_csv_rows` function to avoid helper-to-service imports.
- Docs: updated `docs/ARCHITECTURE.md`.
- Checks passed:
  - `D:\generate\.venv\Scripts\python.exe -m py_compile api\services.py api\file_artifact_helpers.py api\main.py`
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "files or resource or health"` (12 passed)
  - `cd frontend && npm.cmd run typecheck`
  - `cd frontend && npm.cmd run build` (existing chunk-size warning only)
  - `node tools\check_workflow_routing.mjs`
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`
  - mojibake marker scan over touched backend/docs files: no matches.

## 2026-06-24 Backend Relative File Listing Helper Refactor

- Scope: backend file/artifact helper boundary.
- Changed: package-relative artifact file listing now lives in `api/file_artifact_helpers.py`.
- Kept in `api/services.py`: `_relative_files` compatibility wrapper and all existing call sites.
- Docs: updated `docs/ARCHITECTURE.md`.
- Checks passed:
  - `D:\generate\.venv\Scripts\python.exe -m py_compile api\services.py api\file_artifact_helpers.py api\main.py`
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "files or resource or health"` (12 passed)
  - `cd frontend && npm.cmd run typecheck`
  - `cd frontend && npm.cmd run build` (existing chunk-size warning only)
  - `node tools\check_workflow_routing.mjs`
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`
  - mojibake marker scan over touched backend/docs files: no matches.

## 2026-06-24 Summary Compare Card Refactor

- Scope: Summary stage display boundary.
- Changed: `SummaryCompareCard` now lives in `frontend/src/features/summary/CasePanels.tsx`.
- Kept in `App.tsx`: pair-summary loading, graph readiness calculation, overlay metrics, selected reaction state, and Compare navigation callback.
- Docs: updated `docs/SUMMARY_PANEL_BOUNDARY.md`.
- Checks passed: workflow route contract, browser smoke script syntax, frontend typecheck, frontend build, HTTP/API browser smoke, and touched-file garbled-marker scan.

## 2026-06-24 Summary File Panels Refactor

- Scope: Summary report/key traceability file display.
- Changed: `SummaryFilePanels` now lives in `frontend/src/features/summary/CasePanels.tsx`.
- Kept in `App.tsx`: report/key file row collection, API base selection, and missing-message copy assembly.
- Docs: updated `docs/SUMMARY_PANEL_BOUNDARY.md`.
- Checks passed: workflow route contract, browser smoke script syntax, frontend typecheck, frontend build, HTTP/API browser smoke, and touched-file garbled-marker scan.

## 2026-06-24 Summary Evidence Details Refactor

- Scope: Summary failed jobs, SAMMI checker, and readiness flag details.
- Changed: `SummaryEvidenceDetails` now lives in `frontend/src/features/summary/CasePanels.tsx`.
- Kept in `App.tsx`: failed job rows, SAMMI rows, readiness flag rows, inferred columns, and copy assembly.
- Docs: updated `docs/SUMMARY_PANEL_BOUNDARY.md`.
- Checks passed: workflow route contract, browser smoke script syntax, frontend typecheck, frontend build, HTTP/API browser smoke, and touched-file garbled-marker scan.

## 2026-06-24 Summary Issues Panel Refactor

- Scope: Summary issues-to-fix, repair actions, and passed checks.
- Changed: `SummaryIssuesPanel` now lives in `frontend/src/features/summary/CasePanels.tsx`.
- Kept in `App.tsx`: verify rule construction, checklist construction, primary repair selection, and repair callback behavior.
- Docs: updated `docs/SUMMARY_PANEL_BOUNDARY.md`.
- Checks passed: workflow route contract, browser smoke script syntax, frontend typecheck, frontend build, HTTP/API browser smoke, and touched-file garbled-marker scan.

## 2026-06-24 Summary Panel Refactor

- Scope: Summary stage display boundary.
- Changed: extracted `SummaryCompareCard` into `frontend/src/features/summary/CasePanels.tsx`.
- Kept in `App.tsx`: pair-summary loading, graph readiness calculation, overlay metrics, selected reaction state, and Compare navigation callback.
- Docs: updated `docs/SUMMARY_PANEL_BOUNDARY.md`.
- Checks:
  - `node tools\check_workflow_routing.mjs` passed.
  - `node --check tools\run_browser_smoke_qa.mjs` passed.
  - `npm.cmd run typecheck` passed.
  - `npm.cmd run build` passed with the existing Vite large-chunk warning.
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log` passed.
  - Garbled-marker scan over touched files returned no matches.

## 2026-06-24 Input Upload File Role Panel QA

- Scope: `UploadFileRolePanel` extracted into `frontend/src/features/input/InputPanels.tsx`; `App.tsx` keeps file objects, upload form state, role inference, submit/reset actions, and API calls.
- Static checks:
  - `node tools\check_workflow_routing.mjs`: pass.
  - `node --check tools\run_browser_smoke_qa.mjs`: pass.
  - `cd frontend && npm.cmd run typecheck`: pass.
  - `cd frontend && npm.cmd run build`: pass; existing Vite chunk-size warning only.
- HTTP/API smoke:
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`: pass.
- Static text QA:
  - Garbled marker scan over touched Input source, `App.tsx`, and docs: pass; no real hits.
- Notes:
  - The extracted panel covers selected-file summary, per-file omics role editor, condition file guidance, Atlas curated source labels, and role preview.
  - Upload Run Package shell and form fields remain in `App.tsx` for this slice.

## 2026-06-24 Resource Atlas Results Drawer QA

- Scope: `ResourceResultsDrawer` extracted into `frontend/src/features/resource-atlas/ResourceAtlasPanels.tsx`; `App.tsx` keeps search state, selected resource state, pagination, API calls, and callbacks.
- Static checks:
  - `node tools\check_workflow_routing.mjs`: pass.
  - `node --check tools\run_browser_smoke_qa.mjs`: pass.
  - `cd frontend && npm.cmd run typecheck`: pass.
  - `cd frontend && npm.cmd run build`: pass; existing Vite chunk-size warning only.
- HTTP/API smoke:
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`: pass.
- Static text QA:
  - Garbled marker scan over touched Resource Atlas source, `App.tsx`, and docs: pass; no real hits.

## 2026-06-24 Resource Atlas Deep Dive QA

- Scope: `ResourceDeepDivePanel` extracted into `frontend/src/features/resource-atlas/ResourceAtlasPanels.tsx`; `App.tsx` keeps model lineage tree rendering, category filter state, selected node state, and Resource Atlas search/API callbacks.
- Static checks:
  - `node tools\check_workflow_routing.mjs`: pass.
  - `node --check tools\run_browser_smoke_qa.mjs`: pass.
  - `cd frontend && npm.cmd run typecheck`: pass.
  - `cd frontend && npm.cmd run build`: pass; existing Vite chunk-size warning only.
- HTTP/API smoke:
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`: pass.
- Static text QA:
  - Garbled marker scan over touched Resource Atlas source, `App.tsx`, and docs: pass; no real hits.
- Notes:
  - Deep Dive evidence matrix is now a pure display component with callbacks for organism, omics, and source/omics lens changes.
  - Draw_Trees model lineage remains as children in `App.tsx` to avoid touching the heavier tree rendering logic in this slice.

## 2026-06-24 Workflow Domain Types + Definitions QA

- Scope: `workflowTypes.ts`, `workflowDefinitions.ts`, `workflowRouting.ts`, and `App.tsx` workflow domain imports.
- Static checks:
  - `node tools\check_workflow_routing.mjs`: pass
  - `node --check tools\run_browser_smoke_qa.mjs`: pass
  - `cd frontend && npm.cmd run typecheck`: pass
  - `cd frontend && npm.cmd run build`: pass; existing Vite chunk-size warning only
- HTTP/API smoke:
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`: pass
- In-app Browser route shell QA:
  - `#/module-generate`: pass; Model Generator rendered `Model & Omics Dossier` and `Method Workbench`.
  - `#/module-model-comparison`: pass; Model Compare rendered Difference Map context.
  - Console warnings/errors: none
- Notes:
  - Workflow stage/module definitions now live in `frontend/src/domain/workflowDefinitions.ts`.
  - Workflow route/types remain compatible with the existing four-stage homepage and Model Compare subview behavior.

## 2026-06-24 Backend Services Helper Split QA

Scope:
- Added pure backend helpers for Resource Atlas aggregation, Case Study readiness/QA rows, and Model Compare readiness guidance.
- Kept existing endpoint wrappers and response shapes unchanged.

Checks:
- pass: `D:\generate\.venv\Scripts\python.exe -m py_compile api\main.py api\services.py api\status_semantics.py api\resource_atlas_helpers.py api\case_study_helpers.py api\compare_semantics.py`
- pass: `node --check tools\run_browser_smoke_qa.mjs`
- pass: `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py tests\test_variant_comparison.py tests\test_enzyme_constraints.py` (`44 passed`, 2 known SWIG deprecation warnings)
- pass: `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_resource_harvest_tools.py tests\test_fastapi_api.py -k "resource or harvest"` (`21 passed`, 22 deselected)
- pass: `cd frontend && npm.cmd run typecheck`
- pass: `cd frontend && npm.cmd run build` (existing Vite chunk-size warning only)
- pass: `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`
- pass: mojibake marker scan over `frontend\src tools docs api tests`

In-app Browser manual QA:
- pass: Input route visible, with Resource Atlas / Upload entry text.
- pass: Model Compare route visible, with Difference / Constraint / Behavior / Side-by-side switch text and no console errors.
- pass: Summary route visible, with `STAGE 04 / SUMMARY`, case readiness content, and no console errors.
- note: Direct `#/module-generate` in the current API-offline shell stayed on the workflow overview instead of showing Dossier / Method Workbench. This appears unrelated to the backend helper split and is tracked as a route-state QA item.

## 2026-06-23 In-app Browser Manual QA

- URL: `http://127.0.0.1:5173`
- Viewport: in-app Browser default, desktop-width visual check
- Scope: Input, Model Generator, Model Compare, Summary
- Result: pass

| Path | Status | Evidence |
| --- | --- | --- |
| Input | pass | Route rendered non-empty shell with Upload Run Package visible; no framework overlay. |
| Model Generator | pass | Dossier and Method Workbench visible; no framework overlay. |
| Model Compare | pass | Compare view switch visible; switched from Difference Map to Behavior and active state updated. |
| Summary | pass | `STAGE 04 / Summary` visible; no framework overlay. |

Console errors:
- none

## 2026-06-23T14:10:00+08:00 In-app Browser Manual QA

- URL: http://127.0.0.1:5173
- Viewport: default in-app browser viewport
- Browser path: in-app Browser
- Flow under test: app loads -> Input / Model Generator / Model Compare / Summary routes render -> Input mode switch responds.

| Path | Status | Evidence |
| --- | --- | --- |
| Resource Atlas / Input | pass | `上传数据` tab clicked; Upload Run Package panel visible; no framework overlay. |
| Model Generator | pass | Model Generator route renders Model & Omics Dossier / Method Workbench content; no framework overlay. |
| Model Compare | pass | Compare route renders Difference Map / Model Compare content; no misleading `ENZYME CAPACITY 0`; no framework overlay. |
| Summary | pass | Summary route renders `STAGE 04 / SUMMARY`; old Verify stage copy not visible; no framework overlay. |

Console note:
- The in-app Browser log buffer still contained stale Vite HMR errors from an earlier hot-reload attempt before the final fix. A fresh route pass rendered correctly, and the stable `http-api-smoke`, `npm typecheck`, and production build all passed.

## 2026-06-23T13:34:33.828Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: system-edge-cdp-failed-http-fallback
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- Browser CDP smoke failed: CDP websocket closed (1006 read ECONNRESET)

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP fallback checked app shell plus atlas summary API. |
| Model Generator | pass | HTTP fallback checked hash route shell availability. |
| Model Compare | pass | HTTP fallback checked optional file probe semantics. |
| Summary | pass | HTTP fallback checked summary hash route shell availability. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T17:51:27+08:00 Resource Atlas Wide Tree Canvas Manual QA

- URL: http://127.0.0.1:5173/#/module-input
- Viewport: 1366 x 768
- Browser: in-app Browser manual QA
- Flow: Input -> Resource Atlas -> biological taxonomy tree -> horizontal rail controls

| Check | Status | Note |
| --- | --- | --- |
| Wide atlas page | pass | Resource Atlas page width rendered at 1342 px in a 1366 px viewport. |
| Tree-first layout | pass | Tree panel occupied about 95.8% of the lineage main layout with the Inspector collapsed to a 46 px rail. |
| Internal horizontal canvas | pass | Tree scroll viewport was 1190 px wide with a 2680 px internal canvas and no body-level horizontal overflow. |
| Custom horizontal drag rail | pass | Rail was visible; dragging moved scrollLeft from 745 to 180, and clicking the right rail moved it to 1312. |
| Paging and root controls | pass | Page right moved scrollLeft to 1490; Fit root returned to 745 and kept the root node visible. |
| Biological branches | pass | Biological clades remained visible and legacy application branches were absent. |
| Console health | pass | No relevant browser console warnings or errors were reported during the check. |

## 2026-06-24 Backend Resource Atlas Summary Helper Refactor

- Scope: backend Resource Atlas helper boundary.
- Changed: Resource Atlas summary count aggregation and response shaping now live in `api/resource_atlas_helpers.py`.
- Kept in `api/services.py`: resource index loading, resource normalization, deduplication, coverage-by-source lookup, and landscape node/cluster generation.
- Docs: updated `docs/ARCHITECTURE.md` with the Resource Atlas summary helper boundary.
- Checks passed before full smoke:
  - `D:\generate\.venv\Scripts\python.exe -m py_compile api\services.py api\resource_atlas_helpers.py api\workspace_helpers.py api\file_artifact_helpers.py api\run_package_helpers.py api\main.py`
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py tests\test_resource_harvest_tools.py -k "resource or harvest"` (21 passed)
  - Standard mojibake marker scan over touched backend/docs files (no matches)
- Full regression and smoke follow-up:
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py` (34 passed)
  - `cd frontend && npm.cmd run typecheck` (passed)
  - `node tools\check_workflow_routing.mjs` (passed: 15 route cases, 6 helper cases, 5 state adapter cases)
  - `node --check tools\run_browser_smoke_qa.mjs` (passed)
  - `cd frontend && npm.cmd run build` (passed with the existing Vite chunk-size warning)
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log` (passed)

## 2026-06-24 Backend Case Study Prepare Helper Refactor

- Scope: backend Case Study readiness / prepare-preview / prepare-lite helper boundary.
- Changed: missing-run readiness payload, prepare-preview dry-run action/log/response payloads, prepare-lite missing-package response, prepare-lite log payload, prepare-lite response, and QA matrix response shaping now live in `api/case_study_helpers.py`.
- Kept in `api/services.py`: case manifest normalization, run package resolution, artifact probing, pair summary smoke, QA artifact writes, and endpoint-facing orchestration.
- Checks passed before full smoke:
  - `D:\generate\.venv\Scripts\python.exe -m py_compile api\services.py api\case_study_helpers.py api\main.py`
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "case_study or case"` (1 passed)
- Full regression and smoke follow-up:
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py` (34 passed)
  - `cd frontend && npm.cmd run typecheck` (passed)
  - `node tools\check_workflow_routing.mjs` (passed: 15 route cases, 6 helper cases, 5 state adapter cases)
  - `node --check tools\run_browser_smoke_qa.mjs` (passed)
  - `cd frontend && npm.cmd run build` (passed with the existing Vite chunk-size warning)
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log` (passed)

## 2026-06-24 Backend Resource Detail and Curation Helper Refactor

- Scope: backend Resource Atlas detail and Atlas curation helper boundary.
- Changed: Resource Atlas resource detail response shaping now uses `build_resource_detail_response(...)` in `api/resource_atlas_helpers.py`.
- Changed: Atlas curation role, template, required-column, inspection-role, suggested-method, guidance, preview-status, and response-shaping semantics now live in `api/resource_curation_helpers.py`.
- Kept in `api/services.py`: resource index loading, API error handling, table inspection, curation workspace persistence, and endpoint-facing orchestration.
- Checks passed before full smoke:
  - `D:\generate\.venv\Scripts\python.exe -m py_compile api\services.py api\resource_atlas_helpers.py api\resource_curation_helpers.py api\main.py`
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py tests\test_upload_workflow.py -k "resource or curation or atlas or upload"` (23 passed)
- Full regression and smoke follow-up:
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py` (34 passed)
  - `cd frontend && npm.cmd run typecheck` (passed)
  - `node tools\check_workflow_routing.mjs` (passed: 15 route cases, 6 helper cases, 5 state adapter cases)
  - `node --check tools\run_browser_smoke_qa.mjs` (passed)
  - `cd frontend && npm.cmd run build` (passed with the existing Vite chunk-size warning)
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log` (passed)

## 2026-06-23T13:35:00.557Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: system-edge-cdp-failed-http-fallback
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- Browser CDP smoke failed: CDP websocket closed (1006 read ECONNRESET)

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP fallback checked app shell plus atlas summary API. |
| Model Generator | pass | HTTP fallback checked hash route shell availability. |
| Model Compare | pass | HTTP fallback checked optional file probe semantics. |
| Summary | pass | HTTP fallback checked summary hash route shell availability. |

Console errors:
- none

404 responses:
- none

## 2026-06-23T14:09:47.269Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP fallback checked app shell plus atlas summary API. |
| Model Generator | pass | HTTP fallback checked generator hash route shell availability. |
| Model Compare | pass | HTTP fallback checked compare hash route and optional file probe semantics. |
| Summary | pass | HTTP fallback checked summary hash route shell availability. |

Console errors:
- none

404 responses:
- none

## 2026-06-23T15:19:25.370Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP fallback checked app shell plus atlas summary API. |
| Model Generator | pass | HTTP fallback checked generator hash route shell availability. |
| Model Compare | pass | HTTP fallback checked compare hash route and optional file probe semantics. |
| Summary | pass | HTTP fallback checked summary hash route shell availability. |

Console errors:
- none

404 responses:
- none

## 2026-06-23T15:47:52.217Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP fallback checked app shell plus atlas summary API. |
| Model Generator | pass | HTTP fallback checked generator hash route shell availability. |
| Model Compare | pass | HTTP fallback checked compare hash route and optional file probe semantics. |
| Summary | pass | HTTP fallback checked summary hash route shell availability. |

Console errors:
- none

404 responses:
- none

## 2026-06-23T16:12:07.407Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP fallback checked app shell plus atlas summary API. |
| Model Generator | pass | HTTP fallback checked generator hash route shell availability. |
| Model Compare | pass | HTTP fallback checked compare hash route and optional file probe semantics. |
| Summary | pass | HTTP fallback checked summary hash route shell availability. |

Console errors:
- none

404 responses:
- none

## 2026-06-23T16:40:06.909Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP fallback checked app shell plus atlas summary API. |
| Model Generator | pass | HTTP fallback checked generator hash route shell availability. |
| Model Compare | pass | HTTP fallback checked compare hash route and optional file probe semantics. |
| Summary | pass | HTTP fallback checked summary hash route shell availability. |

Console errors:
- none

404 responses:
- none

## 2026-06-24 Workflow Routing Deep-link QA

- Scope: frontend hash routing helper for the four-stage workflow.
- Static checks:
  - `npm.cmd run typecheck`: pass
  - `npm.cmd run build`: pass; existing Vite chunk-size warning only
  - `node --check tools\run_browser_smoke_qa.mjs`: pass
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`: pass
- In-app Browser route checks:

| Route | Status | Note |
| --- | --- | --- |
| `#/module-input` | pass | Opened Input shell with upload/resource atlas controls. |
| `#/module-generate` | pass | Opened Model Generator main page with `Model & Omics Dossier` and `Method Workbench`; did not fall back to workflow overview. |
| `#/module-model-comparison` | pass | Opened Model Compare with Difference Map context. |
| `#/module-analysis` | pass | Opened Analysis method workbench. |
| `#/module-summary` | pass | Opened `STAGE 04 / SUMMARY`. |

- Navigation checks:
  - Top navigation `模型生成`: pass; enters Model Generator main page.
  - Model Generator tab `模型对比`: pass; enters Compare subview.

Console errors:
- none

Cleanup:
- No new `.pytest_cache` or source `__pycache__` directories found after this frontend-only round.

## 2026-06-23T17:34:55.662Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none
## 2026-06-24 Workflow Shell Refactor QA

- Scope: `features/workflow` display components, workflow route contract check, and deep-link browser smoke.
- Static checks:
  - `node tools\check_workflow_routing.mjs`: pass
  - `cd frontend && npm.cmd run typecheck`: pass
  - `cd frontend && npm.cmd run build`: pass; existing Vite chunk-size warning only
  - `node --check tools\run_browser_smoke_qa.mjs`: pass
  - mojibake marker scan over `frontend\src`, `tools`, `docs`, `api`, `tests`: no hits
- HTTP/API smoke:
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`: pass
- In-app Browser manual QA:

| Route / Interaction | Status | Note |
| --- | --- | --- |
| `#/module-input` | pass | Input shell renders with upload/resource controls. |
| `#/module-generate` | pass | Model Generator main page renders `Model & Omics Dossier` and `Method Workbench`. |
| `#/module-model-comparison` | pass | Compare subview renders Model Compare / Difference Map context. |
| `#/module-analysis` | pass | Analysis method workbench renders. |
| `#/module-summary` | pass | `STAGE 04 / SUMMARY` renders. |
| Top nav `模型生成` | pass | Enters Model Generator main page, not Compare. |
| Model Generator tab `模型对比` | pass | Enters Compare subview. |

Console warnings/errors:
- none

Screenshot evidence:
- Captured in-app Browser viewport for Model Generator / Compare; not written to repo.

## 2026-06-24 Workflow Shell Adapter + Smoke Cleanup QA

- Scope: `workflowShellAdapter.ts`, `App.tsx` workflow shell data assembly, and `run_browser_smoke_qa.mjs` strict-browser cleanup.
- Static checks:
  - `node tools\check_workflow_routing.mjs`: pass
  - `node --check tools\run_browser_smoke_qa.mjs`: pass
  - `cd frontend && npm.cmd run typecheck`: pass
  - `cd frontend && npm.cmd run build`: pass; existing Vite chunk-size warning only
- HTTP/API smoke:
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`: pass
- In-app Browser route shell QA:

| Route | Status | Note |
| --- | --- | --- |
| `#/module-input` | pass | Input shell rendered with no overlay. |
| `#/module-generate` | pass | Model Generator rendered `Model & Omics Dossier` and `Method Workbench`. |
| `#/module-model-comparison` | pass | Model Compare rendered Difference Map context. |
| `#/module-analysis` | pass | Analysis method workbench rendered. |
| `#/module-summary` | pass | `STAGE 04 / SUMMARY` rendered. |

Console warnings/errors:
- none

Notes:
- Browser screenshot evidence was captured in memory and not written to repo.
- The in-app Browser status strip displayed API offline / zero runs during visual shell QA, but HTTP/API smoke for the same URL passed; this round only changed workflow shell routing and display assembly.

## 2026-06-23T18:23:13.383Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-23T18:52:56.651Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T07:55:08.402Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none
## 2026-06-24 Workflow Domain Helper QA

- Scope: `workflowHelpers.ts`, `workflowRouting.ts`, `App.tsx` workflow state restoration, and route contract loader.
- Static checks:
  - `node tools\check_workflow_routing.mjs`: pass; 15 route cases and 6 helper cases.
  - `node --check tools\run_browser_smoke_qa.mjs`: pass.
  - `cd frontend && npm.cmd run typecheck`: pass.
  - `cd frontend && npm.cmd run build`: pass; existing Vite chunk-size warning only.
- HTTP/API smoke:
  - First run failed because `127.0.0.1:5173` was not listening.
  - Started the existing local app script with `-NoBrowser`; reran smoke successfully.
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`: pass.
- In-app Browser manual QA:
  - `#/module-generate`: pass; rendered `Model & Omics Dossier` and `Method Workbench`.
  - `#/module-model-comparison`: pass; rendered Model Compare shell with Reference / Target context.
  - `#/module-summary`: pass; rendered `STAGE 04 / SUMMARY`.
  - Precise framework overlay check: pass; no Vite / React overlay detected.
  - Console errors: none.

## 2026-06-24T08:19:42.994Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none
## 2026-06-24 Workflow State Adapter QA

- Scope: `workflowStateAdapter.ts`, `App.tsx` workflow state hydration/sync payload, and route contract state-adapter checks.
- Static checks:
  - `node tools\check_workflow_routing.mjs`: pass; 15 route cases, 6 helper cases, 5 state adapter cases.
  - `node --check tools\run_browser_smoke_qa.mjs`: pass.
  - `cd frontend && npm.cmd run typecheck`: pass.
  - `cd frontend && npm.cmd run build`: pass; existing Vite chunk-size warning only.
- HTTP/API smoke:
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`: pass.
- In-app Browser manual QA:
  - `#/module-generate`: pass; rendered `Model & Omics Dossier` and `Method Workbench`.
  - `#/module-model-comparison`: pass; rendered Model Compare with Reference / Target context.
  - Precise framework overlay check: pass; no Vite / React overlay detected.
  - Console errors: none.

## 2026-06-24T08:36:10.911Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none
## 2026-06-24 API Type Barrel QA

- Scope: `resourceAtlasTypes.ts`, `caseStudyTypes.ts`, `modelCompareTypes.ts`, `workflowApiTypes.ts`, and `App.tsx` type import cleanup.
- Static checks:
  - `cd frontend && npm.cmd run typecheck`: pass.
  - `node tools\check_workflow_routing.mjs`: pass.
  - `node --check tools\run_browser_smoke_qa.mjs`: pass.
  - `cd frontend && npm.cmd run build`: pass; existing Vite chunk-size warning only.
- HTTP/API smoke:
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`: pass.
- In-app Browser manual QA:
  - `#/module-generate`: pass; rendered `Model & Omics Dossier` and `Method Workbench`.
  - `#/module-model-comparison`: pass; rendered Model Compare with Reference / Target context.
  - Precise framework overlay check: pass; no Vite / React overlay detected.
  - Console errors: none.

## 2026-06-24 Resource Atlas Adapter QA

- Scope: `resourceAtlasAdapters.ts`, `resourceLandscapeAdapter.ts`, and `App.tsx` Resource Atlas view-model cleanup.
- Refactor notes:
  - Moved case study option assembly, active resource/source-link normalization, omics grouping, cache/source coverage summary, facet/count cards, landscape context, and Deep Dive source rows into pure feature adapters.
  - Kept API calls, React state, resource search, curation workspace actions, and workflow handoff in `App.tsx`.
- Static checks:
  - `node tools\check_workflow_routing.mjs`: pass; 15 route cases, 6 helper cases, 5 state adapter cases.
  - `node --check tools\run_browser_smoke_qa.mjs`: pass.
  - `cd frontend && npm.cmd run typecheck`: pass.
  - `cd frontend && npm.cmd run build`: pass; existing Vite chunk-size warning only.
- HTTP/API smoke:
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`: pass.
- Static text QA:
  - Garbled marker scan over touched Resource Atlas source and docs: pass; no real hits.

## 2026-06-24 Resource Atlas Panels QA

- Scope: `ResourceAtlasPanels.tsx` and `App.tsx` cache/source coverage panel extraction.
- Refactor notes:
  - Moved cached metadata status and harvesting source coverage panels into pure Resource Atlas display components.
  - Kept resource search state, target-candidate lens callbacks, API calls, and workflow actions in `App.tsx`.
- Static checks:
  - `node tools\check_workflow_routing.mjs`: pass; 15 route cases, 6 helper cases, 5 state adapter cases.
  - `node --check tools\run_browser_smoke_qa.mjs`: pass.
  - `cd frontend && npm.cmd run typecheck`: pass.
  - `cd frontend && npm.cmd run build`: pass; existing Vite chunk-size warning only.
- HTTP/API smoke:
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`: pass.
- Static text QA:
  - Garbled marker scan over touched Resource Atlas source and docs: pass; no real hits.

## 2026-06-24 Resource Atlas Decision Inspector QA

- Scope: `ResourceDecisionInspector` in `ResourceAtlasPanels.tsx` and `App.tsx` Decision Inspector extraction.
- Refactor notes:
  - Moved Evidence Stack, Readiness Summary, Method Readiness, Workflow Actions, and collapsed resource metadata display into a pure Resource Atlas display component.
  - Kept resource search state, lens callbacks, candidate/curation conversion, API calls, and workflow handoff in `App.tsx`.
- Static checks:
  - `node tools\check_workflow_routing.mjs`: pass; 15 route cases, 6 helper cases, 5 state adapter cases.
  - `node --check tools\run_browser_smoke_qa.mjs`: pass.
  - `cd frontend && npm.cmd run typecheck`: pass.
  - `cd frontend && npm.cmd run build`: pass; existing Vite chunk-size warning only.
- HTTP/API smoke:
  - `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`: pass.
- Static text QA:
  - Garbled marker scan over touched Resource Atlas source and docs: pass; no real hits.

## 2026-06-24T09:04:50.555Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T09:15:14.245Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T09:27:17.143Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T10:27:46.728Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T10:40:51.007Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T10:52:20.872Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T11:06:57.869Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T11:15:25.894Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24 Summary Compare Card Refactor

- Scope: Summary stage display boundary.
- Changed: `SummaryCompareCard` now lives in `frontend/src/features/summary/CasePanels.tsx`.
- Kept in `App.tsx`: pair-summary loading, graph readiness calculation, overlay metrics, selected reaction state, and Compare navigation callback.
- Docs: updated `docs/SUMMARY_PANEL_BOUNDARY.md`.
- Checks passed: workflow route contract, browser smoke script syntax, frontend typecheck, frontend build, HTTP/API browser smoke, and touched-file garbled-marker scan.

## 2026-06-24 Summary Decision Panel Refactor

- Scope: Summary stage display boundary.
- Changed: `SummaryDecisionPanel` now lives in `frontend/src/features/summary/CasePanels.tsx`.
- Kept in `App.tsx`: final readiness decision calculation, primary repair/report action selection, report build callback, Analysis navigation callback, and decision metric values.
- Docs: updated `docs/SUMMARY_PANEL_BOUNDARY.md`.
- Checks passed: workflow route contract, browser smoke script syntax, frontend typecheck, frontend build, HTTP/API browser smoke, and touched-file garbled-marker scan.

## 2026-06-24 Summary Report Exit Refactor

- Scope: Summary stage display boundary.
- Changed: `SummaryReportExitPanel` now lives in `frontend/src/features/summary/CasePanels.tsx`.
- Kept in `App.tsx`: report build callback, Analysis navigation callback, ActionResultPanel, Atlas provenance strip, compare summary metrics, file panels, and evidence detail data assembly.
- Docs: updated `docs/SUMMARY_PANEL_BOUNDARY.md`.
- Checks passed: workflow route contract, browser smoke script syntax, frontend typecheck, frontend build, HTTP/API browser smoke, and touched-file garbled-marker scan.

## 2026-06-24 Workflow Action Result Panel Refactor

- Scope: shared workflow display boundary.
- Changed: `ActionResultPanel` now lives in `frontend/src/features/workflow/ActionResultPanel.tsx` and is reused by DataHub, Model Generator, Analysis, and Summary.
- Kept in `App.tsx`: action execution, action result state updates, language switching, fallback result creation, and API base URL ownership.
- Docs: updated `docs/ARCHITECTURE.md`.
- Checks passed: workflow route contract, browser smoke script syntax, frontend typecheck, frontend build, HTTP/API browser smoke, and touched-file garbled-marker scan.

## 2026-06-24 Backend File Artifact Helper Refactor

- Scope: backend service boundary.
- Changed: file access path safety now lives in `api/file_artifact_helpers.py`.
- Kept in `api/services.py`: `resolve_safe_file` compatibility wrapper and current workspace root/allowed roots ownership.
- Kept in `api/main.py`: `/api/files` endpoint, optional missing response semantics, and `FileResponse`.
- Docs: updated `docs/ARCHITECTURE.md`.
- Checks passed: Python compile for touched backend modules, `/api/files` regression tests, workflow route contract, frontend typecheck/build, HTTP/API browser smoke, and touched-file garbled-marker scan.

## 2026-06-24 Backend Relative Path Helper Refactor

- Scope: backend file/artifact helper boundary.
- Changed: package-relative path formatting now lives in `api/file_artifact_helpers.py`.
- Kept in `api/services.py`: `_safe_relative_path` compatibility wrapper and all existing call sites.
- Docs: updated `docs/ARCHITECTURE.md`.
- Checks passed: Python compile for touched backend modules, `/api/files` and resource API regression subset, frontend typecheck/build, workflow route contract, HTTP/API browser smoke, and touched-file garbled-marker scan.

## 2026-06-24T11:24:57.870Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T11:33:14.703Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T11:43:45.639Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T11:57:30.224Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T12:05:11.692Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T12:29:29.687Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T12:39:59.443Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T12:48:03.031Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T12:58:43.460Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T13:06:11.885Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T13:13:15.813Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T13:20:53.476Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T13:29:00.706Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T13:35:22.678Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T13:41:54.635Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T13:50:15.849Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T13:56:00.817Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T14:08:04.863Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T14:16:25.496Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T14:25:08.368Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T14:32:50.622Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T14:41:02.162Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T14:48:25.774Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T14:56:53.522Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T15:10:14.608Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T15:26:11.383Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T15:45:10.287Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T16:53:59.523Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T17:52:35.342Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T17:57:29.755Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-24T18:29:57.307Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T02:54:21.613Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T04:45:54.529Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25 Resource Lineage Atlas visual QA

- URL: `http://127.0.0.1:5173/#/module-input`
- Viewports: `1366x768`, `1920x1080`
- Browser path: in-app Browser visual QA plus HTTP/API smoke.
- Result: pass.

Checks:
- Resource Atlas mode renders a species-first lineage tree as the main atlas surface.
- Main filter bar exposes keyword, organism, microbial group, case study, omics type, readiness, search, fit tree, and reset controls.
- Selecting a resource-type child node opens the fixed-height resource entries drawer.
- Right inspector shows organism image, resource counts, Evidence Stack, Readiness Summary, Method Readiness, and Workflow Actions.
- Source coverage and previous landscape/search surfaces are folded behind secondary panels.
- No horizontal overflow at 1366px or 1920px.
- Browser console reported no relevant errors.

## 2026-06-25T05:03:21.716Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T06:44:21.242Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T07:21:08.104Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T07:52:59.973Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T08:06:48.591Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T08:12:45.093Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T08:35:42.480Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T08:56:49.403Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T09:11:01.356Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T09:51:00.290Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T10:53:42.979Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T11:29:23.157Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T11:51:39.898Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T13:40:16.705Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T13:43:10.491Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T14:08:08.438Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T15:24:11.607Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T15:36:22.782Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T16:26:45.645Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T16:51:12.927Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T17:19:15.193Z Browser Smoke QA

- URL: http://127.0.0.1:5175
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | fail | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- http://127.0.0.1:5175/api/files strict missing returned 200

## 2026-06-25T17:25:00Z Shewanella Trigger Round 2E Manual Browser QA

- Target app: `http://127.0.0.1:5175` with fresh backend API `http://127.0.0.1:8766`
- Viewport: 1366 x 768
- Scope: `shewanella_transcriptional_triggers_case`

Checks:
- Analysis: `PaperReproductionWorkbench` is present in DOM with Growth State Map, Trigger Timeline, GDM-lite, D2T2, and dFBA/glycogen sections. Payload comes from `paper_reproduction.status = partial_computed_lite`.
- Model Compare: default pair is `baseline_gem__all` vs `paper_evidence_context__lac_transition`.
- Model Compare: default scope is `custom_annotation / gluconeogenesis`; both left and right edit graphs reach `ready` after pair summary generation.
- Model Compare: blue evidence markers appear only on GPR-mapped paper evidence reactions; unmapped nitrogen/glycogen regulator genes remain pathway-level guidance.
- Model Compare dashboard: shows `paper evidence genes = 17`, `mapped reactions = 12`, `unmapped genes = 14`, `bounds changed = 0`, `added = 0`, `removed = 0`, and `enzyme capacity = not applicable`.
- Summary: `PaperReproductionStatusCard` is present in DOM and reports GDM-lite, D2T2 paper-reported, dFBA/glycogen paper prediction, condition bounds not generated, and enzyme capacity not applicable.

Known notes:
- Pair summary for the trigger case may take around 20-30 seconds because the inline edit graph is generated on demand; early page text can temporarily show `network_graph.json not loaded`.
- A Radix Select controlled/uncontrolled warning still appears in browser console. It is non-blocking for this QA pass and should be handled in a separate UI cleanup.
- `node tools/run_browser_smoke_qa.mjs --url http://127.0.0.1:5175` fails its same-origin `/api/files` probe because 5175 was a temporary Vite-only QA port without the Caddy/same-origin API proxy. The default smoke on `http://127.0.0.1:5173` passed.

## 2026-06-26 Shewanella Trigger Round 2F Implementation QA

Scope:
- Added `shewanella_trigger_reproduction_report` preset.
- Added Summary action for the Shewanella trigger reproduction report.
- Aligned trigger case default narrative group to `nitrogen_glycogen_coupling`.

Expected boundaries:
- GDM-lite: `computed_lite`
- D2T2: `paper_reported_only`
- dFBA/glycogen: `paper_reported_model_prediction_available`
- condition bounds: `not_generated`
- enzyme capacity: `not_applicable`

Validation status:
- `py_compile omics_router\report_builder.py api\services.py api\main.py`: pass.
- `pytest tests\test_report_builder.py -q`: pass, 6 tests.
- `pytest tests\test_fastapi_api.py -k "paper_reproduction or analysis_summary or report" -q`: pass, 4 selected tests.
- `pytest tests\test_variant_comparison.py tests\test_enzyme_constraints.py -q`: pass, 10 tests with existing SWIG deprecation warnings.
- `cd frontend && npm.cmd run typecheck`: pass.
- `cd frontend && npm.cmd run build`: pass, with existing Vite large chunk warning.
- `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log`: pass.

Generated artifacts:
- `D:\generate\user_runs\shewanella_transcriptional_triggers_case\report_results\shewanella_trigger_reproduction_report.html`
- `D:\generate\user_runs\shewanella_transcriptional_triggers_case\report_results\paper_reproduction_report_manifest.json`

Notes:
- Verify summary reports the Shewanella trigger report as available.
- Case readiness refreshed as `evidence_only_no_ecmodel`, matching the transcriptomics/metabolite evidence-only boundary.

## 2026-06-25T17:21:24.546Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-25T17:56:58.231Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-26T02:51:47.146Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-26T18:20:00+08:00 Shewanella GECKO Model Compare Browser QA

- URL: http://127.0.0.1:5173/#/module-model-comparison
- Browser: in-app Browser
- Case/run: `shewanella_gecko_oxygen` / `shewanella_gecko_case`
- Pair: `baseline_gem__all` vs `enzyme_gecko__higho2`
- Scope: `kegg_pathway / rn00020` Citrate cycle (TCA cycle)

| Check | Status | Evidence |
| --- | --- | --- |
| API connected | pass | Page did not show `API offline`; `/api/health` and pair summary were available. |
| Default pair | pass | Compare rendered `baseline_gem__all` against `enzyme_gecko__higho2`. |
| Real edit facts | pass | Pair summary reported target-side TCA evidence overlay; reference-side evidence remained clean. |
| Evidence overlay | pass | Target graph rendered 16 `E` evidence glyphs for mapped kcat/proteomics-style evidence. |
| Layout mode | pass | Both network panes used the `compare` layout preset. |
| Case state isolation | pass | Switching from trigger reproduction to GECKO no longer carries over trigger case scope/story. |
| Color semantics | pass | Reference unchanged reactions render neutral gray; target mapped evidence renders blue with `E` glyphs. |
| Missing capacity semantics | pass | Page did not show misleading `ENZYME CAPACITY 0`; capacity remains unavailable/package-ready unless reaction-level artifacts exist. |
| Old workspace removed | pass | Old `Difference Map / Constraint Evidence / Behavior` workspace labels were not present. |

Notes:
- The GECKO pair is same-source/no conventional structural diff, so `added`, `removed`, and `bounds_changed` remain real zero/none.
- The visible difference for this case is the evidence/constraint overlay layer, especially kcat/package-ready support on the highO2 target.
## 2026-06-28T01:20:00+08:00 Case Context Contract Refactor

- Added pure `frontend/src/domain/caseContext.ts` for case/stage/run decisions.
- Added `tools/check_case_context.mjs`.
- Checks passed: `node tools\check_case_context.mjs`, `node tools\check_workflow_routing.mjs`, `npm.cmd run typecheck`.
- Browser visual QA not run in this step; next UI smoke should verify Shewanella integrated Compare, Analysis, and Summary paths.

## 2026-06-28T02:05:00+08:00 Workflow Runtime Snapshot Resolver

- Added pure `frontend/src/domain/workflowRuntime.ts` for workflow snapshot decisions, shell view-model rows, semantic refresh intents, and workflow state payload preview.
- Added `tools/check_workflow_runtime.mjs`.
- `App.tsx` now consumes runtime shell rows for top nav, overview stages/modules, and nav status pills; API calls, hash writes, React state writes, auth, language, and workflow actions remain in `App.tsx`.
- Checks passed: `node tools\check_workflow_runtime.mjs`, `node tools\check_workflow_routing.mjs`, `node --check tools\run_browser_smoke_qa.mjs`, `npm.cmd run typecheck`, `npm.cmd run build`.
- Browser visual QA not run in this step; next UI smoke should verify deep links and Shewanella integrated Compare/Analysis/Summary paths.

## 2026-06-28T03:10:00+08:00 Model Compare Workspace Resolver

- Added pure `frontend/src/domain/modelCompareWorkspace.ts` for effective pair, scope, graph status/load plan, dashboard metrics, legend semantics, and guidance.
- Added `tools/check_model_compare_workspace.mjs`.
- `App.tsx` now uses the resolver for effective Compare pair/scope, pair summary request scope, dashboard/legend data, and side graph loading/missing status.
- Fixed path-only `reference_edit` / `target_edit` metadata shadowing loaded graph JSON; inline edit graph is now used only when it has real nodes.
- Checks passed: `node tools\check_model_compare_workspace.mjs`, `node tools\check_case_context.mjs`, `node tools\check_workflow_routing.mjs`, `node --check tools\run_browser_smoke_qa.mjs`, `npm.cmd run typecheck`, `npm.cmd run build`.
- Browser visual QA not run because `http://127.0.0.1:5173` was not running during this step.

## 2026-06-28T03:40:00+08:00 Analysis Workspace Resolver

- Rebuilt `frontend/src/domain/analysisWorkspace.ts` as a clean pure resolver instead of keeping the earlier draft shape.
- `App.tsx` now uses the resolver for Input paper checklist visibility, Analysis paper workbench visibility, Summary paper reproduction status, and trigger report preset selection.
- The resolver does not fetch, mutate React state, submit report jobs, render charts, write hash routes, or create artifacts.
- `tools/check_analysis_workspace.mjs` locks integrated Shewanella trigger facts without locking UI copy, chart counts, or report HTML content.
- Checks passed: `node tools\check_analysis_workspace.mjs`, `node tools\check_case_context.mjs`, `node tools\check_workflow_routing.mjs`, `npm.cmd run typecheck`, `npm.cmd run build`.
- Browser visual QA not run in this step; next UI smoke should verify integrated Shewanella Analysis/Summary and trigger report generation.

## 2026-06-28T04:25:00+08:00 Resource Lineage Tree Resolver

- Added pure `frontend/src/domain/resourceLineageTree.ts` for Resource Atlas lineage decisions: biological placement, resource category grouping, empty-species visibility, selection targets, and guidance.
- Reworked `frontend/src/features/resource-atlas/SpeciesResourceLineageTree.tsx` to consume the resolver while keeping rendering, SVG/CSS tree layout, horizontal scroll, blank-canvas drag pan, zoom controls, and callbacks in the view layer.
- Added `tools/check_resource_lineage_tree.mjs` to lock placement, empty-species, category, and selection-target semantics without locking pixel layout or copy.
- Fixed mojibake in the new tree component display strings while keeping existing CSS class names and Resource Atlas data flow.
- Checks passed: `node tools\check_resource_lineage_tree.mjs`, `node tools\check_case_context.mjs`, `node tools\check_model_compare_workspace.mjs`, `node tools\check_workflow_routing.mjs`, `node --check tools\run_browser_smoke_qa.mjs`, `npm.cmd run typecheck`, `npm.cmd run build`.
- Browser visual QA not run in this step; next UI smoke should verify tree pan/zoom, drawer selection behavior, and 1366 x 768 layout.

## 2026-06-28T05:05:00+08:00 Run Package Resolver

- Added `api/run_package_resolver.py` as a read-only backend resolver for package identity, artifact inventory, stage readiness, variant context, optional evidence status, and paper/report context.
- `api/services.py` now consumes the resolver in `run_overview(...)` and case readiness fact gathering while keeping endpoint response shapes compatible.
- Added `tools/check_run_package_resolver.py` to lock missing package behavior, toy run readiness, optional capacity semantics, and Shewanella GECKO/trigger package facts.
- Checks passed: `D:\generate\.venv\Scripts\python.exe -m py_compile api\run_package_resolver.py api\services.py api\main.py`, `D:\generate\.venv\Scripts\python.exe tools\check_run_package_resolver.py`, `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "run_package or case_study or analysis_summary" -q`.
- Browser visual QA not run in this step; next UI smoke should verify run list, case readiness, Shewanella integrated Compare, and trigger Analysis/Summary still load.

## 2026-06-28T07:11:23.776Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-28T07:27:22.541Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-28T07:37:15.910Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-28T08:01:13.385Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none

## 2026-06-28T08:10:29.568Z Browser Smoke QA

- URL: http://127.0.0.1:5173
- Viewport: 1366 x 768
- Browser: http-api-smoke
- Overlay count: 0
- Page errors: 0
- Critical console errors: 0
- Warnings:
- none

| Path | Status | Note |
| --- | --- | --- |
| Resource Atlas / Input | pass | HTTP/API smoke checked app shell, atlas summary API, and Input deep link. |
| Model Generator | pass | Deep-link checked Model Generator main page. |
| Model Compare | pass | Deep-link checked Model Compare subview and optional file probe semantics. |
| Analysis | pass | Deep-link checked Analysis method workbench. |
| Summary | pass | Deep-link checked Summary stage. |

Console errors:
- none

404 responses:
- none
## 2026-06-28 Resource Atlas Connector Deepening v1.2

- Scope: added bounded connector-deepening harvest stage, automatic post-harvest QA refresh chain, and documentation for capped continuation vs target-window rotation.
- New stage: `microbial_connector_deepening_v1`, using reviewed production target windows only; `include_microbial_scopes=false` so taxonomy-review candidates are not harvested by default.
- Dry-run checks:
  - `run_resource_harvest_plan.py --stage microbial_connector_deepening_v1 --dry-run --offline --max-jobs 2`: pass; GEO and PRIDE commands included bounded target windows and `microbial_context` partitions.
  - `run_resource_continuation_plan.py --dry-run --offline --max-jobs 2`: pass; selected GEO and PRIDE capped continuation commands.
- Bounded live smoke:
  - `update_resource_cache.py --source geo --limit 40 --page-size 5 --max-pages 1 --max-queries 2 --query-partitions microbial_context --max-partitions-per-query 1 --target-offset 0 --target-limit 2`: pass.
  - GEO cache remained merge-safe at 989 records; no raw or processed data was downloaded.
- Post-harvest QA:
  - `run_resource_post_harvest_qa.py`: pass.
  - Snapshot: resource quality rows = 2524; ready violations = 0; canonical groups = 2513; expanded targets = 352; taxonomy ready = 40; needs taxonomy review = 308; special categories = 9; promotion applied = false.
- Regression:
  - `py_compile` for harvest, continuation, quality, taxonomy, and post-harvest tools: pass.
  - `pytest tests/test_resource_harvest_tools.py -q`: 18 passed.
  - `pytest tests/test_resource_harvest_tools.py tests/test_fastapi_api.py -k "resource or harvest" -q`: 30 passed, 24 deselected.
  - `frontend npm.cmd run typecheck`: pass.
  - `frontend npm.cmd run build`: pass with existing Vite large chunk warning.

## 2026-06-28 Resource Atlas Metadata Expansion Foundation v1.1

- Scope: refreshed schema quality/canonical/readiness reports, expanded target registry, promotion dry-run, and new local-first taxonomy cache/queue artifacts.
- Artifacts:
  - `resources/cached_search/resource_schema_quality_report.*`
  - `resources/cached_search/resource_canonical_link_report.*`
  - `resources/cached_search/resource_readiness_audit.*`
  - `resources/taxonomy/taxonomy_cache.json`
  - `resources/taxonomy/taxonomy_resolution_queue.csv`
  - `resources/taxonomy/taxonomy_resolution_warnings.csv`
  - `resources/taxonomy/microbial_special_categories.csv`
- Acceptance snapshot: resource quality rows = 2524; ready violations = 0; expanded targets = 352; taxonomy candidates = 357; taxonomy ready = 40; needs taxonomy review = 308; special categories = 9; promotion dry-run add = 5; promotion applied = false.
- Checks:
  - `py_compile` for Resource Atlas quality, target registry, promotion, and taxonomy tools: pass.
  - `pytest tests/test_resource_harvest_tools.py -q`: 17 passed.
  - `pytest tests/test_resource_harvest_tools.py tests/test_fastapi_api.py -k "resource or harvest" -q`: 29 passed, 24 deselected.
  - `frontend npm.cmd run typecheck`: pass.
  - `frontend npm.cmd run build`: pass with existing Vite large chunk warning.

## 2026-06-28 Resource Atlas Target Registry Review v1.3

- Scope: promotion semantics, taxonomy identity merge, and concrete-organism taxonomy review worklist.
- Changes:
  - `scope_*` and abstract microbial discovery scopes are rejected by promotion dry-run with `abstract_scope_not_promotable`.
  - taxonomy candidate merging now prioritizes `organism_id` and current-registry identity before taxon/name fallback.
  - added `resources/taxonomy/taxonomy_review_worklist.csv` and `.json` for concrete organism review.
- Acceptance snapshot after `run_resource_post_harvest_qa.py`:
  - resource quality rows = 2524; ready violations = 0; expanded targets = 352.
  - promotion dry-run rows_to_add = 0; abstract rejected = 9; applied = false.
  - taxonomy ready = 40; needs taxonomy review = 303; special categories = 9; review worklist rows = 303.
  - known current targets checked absent from taxonomy queue: Shewanella, P. putida, Synechocystis, E. coli, S. cerevisiae.
- Checks:
  - `py_compile` for target registry, taxonomy, and post-harvest QA tools: pass.
  - `pytest tests/test_resource_harvest_tools.py -q`: 18 passed.
  - `run_resource_harvest_plan.py --stage microbial_connector_deepening_v1 --dry-run --offline --max-jobs 2`: pass; planned GEO offset 0/window 20 and PRIDE offset 20/window 20 against production targets only.
  - `pytest tests/test_resource_harvest_tools.py tests/test_fastapi_api.py -k "resource or harvest" -q`: 30 passed, 24 deselected.
  - `frontend npm.cmd run typecheck`: pass.
  - `frontend npm.cmd run build`: pass with existing Vite large chunk warning.

## 2026-06-28 Resource Atlas Target Review v1.4

- Scope: offline taxonomy review decisions and review promotion dry-run staging.
- Changes:
  - Added `tools/review_taxonomy_targets.py` for offline-only review decisions.
  - Added review artifacts: `taxonomy_review_decisions.*`, `taxonomy_review_summary.json`, `organism_targets.reviewed_candidates.csv`, `organism_targets_review_promotion_dry_run.*`, conflicts/rejected reports, and `organism_targets.backup_preview.csv`.
  - Post-harvest QA now refreshes review decisions and writes cache manifest pointers.
- Acceptance snapshot after `run_resource_post_harvest_qa.py`:
  - worklist rows = 303; decision counts = `needs_taxon_id: 303`.
  - reviewed candidates = 0; review promotion dry-run rows_to_add = 0.
  - production `organism_targets.csv` remained 40 rows and contains no `scope_*`.
- Checks:
  - `py_compile` for review, taxonomy, target registry, and post-harvest QA tools: pass.
  - `pytest tests/test_resource_harvest_tools.py -q`: 20 passed.
  - `review_taxonomy_targets.py --dry-run`: pass; printed summary without writing artifacts.
  - `run_resource_post_harvest_qa.py`: pass; refreshed review artifacts and cache manifest pointers.
  - `pytest tests/test_resource_harvest_tools.py tests/test_fastapi_api.py -k "resource or harvest" -q`: 32 passed, 24 deselected.
  - `frontend npm.cmd run typecheck`: pass.
  - `frontend npm.cmd run build`: pass with existing Vite large chunk warning.

## 2026-06-28 Resource Atlas Target Review v1.5

- Scope: bounded NCBI taxonomy enrichment for top 50 `needs_taxon_id` review rows.
- Changes:
  - Added `tools/enrich_taxonomy_targets.py` with cache-first default and explicit `--online-ncbi`.
  - Added enrichment artifacts: `taxonomy_enrichment_cache.json`, `taxonomy_enrichment_candidates.*`, `taxonomy_enrichment_warnings.csv`, `taxonomy_review_decisions.enriched.csv`, and `organism_targets_enrichment_promotion_dry_run.*`.
- Acceptance snapshot after explicit `--online-ncbi --limit 50`:
  - selected = 50; accepted = 45; warnings = 5.
  - status counts: accepted_exact = 42; accepted_synonym = 3; genus_only = 2; no_hit = 3.
  - enrichment promotion dry-run rows_to_add = 45; applied = false.
  - production `organism_targets.csv` remained 40 rows and contains no `scope_*`.
- Checks:
  - `py_compile` for enrichment, review, taxonomy, and target registry tools: pass.
  - `pytest tests/test_resource_harvest_tools.py -q`: 22 passed.
  - `enrich_taxonomy_targets.py --dry-run`: pass; cache-first, no online queries.
  - `enrich_taxonomy_targets.py --online-ncbi --limit 50`: pass; metadata-only NCBI taxonomy lookup.
  - `pytest tests/test_resource_harvest_tools.py tests/test_fastapi_api.py -k "resource or harvest" -q`: 34 passed, 24 deselected.
  - `frontend npm.cmd run typecheck`: pass.
  - `frontend npm.cmd run build`: pass with existing Vite large chunk warning.

## 2026-07-11 Resource Curation Workspace Deepening

- Scope: move persistent Atlas curation workspace lifecycle ownership out of `api/services.py` without changing HTTP paths, public response shapes, published Run Package schemas, mapping results, or stage eligibility.
- Architecture:
  - Added `api/resource_curation_workspace.py` with a typed `create / query / execute` interface.
  - The module now owns workspace and file manifests, curated-file preview records, identifier mapping, mapping artifacts, stage guards, Run Package inputs, and Atlas provenance manifest ordering.
  - `api/services.py` retains six compatibility functions, composes the module from current workspace roots, maps domain errors to `ApiError`, and adds the existing `run_overview(...)` projection after staging.
  - Workspace and package file writes now reject symlink/out-of-bound targets and replace individual files atomically.
  - Workspace creation is hidden-directory prepared and atomically published; failed creation leaves the requested id reusable.
  - Curated content uses immutable versions plus an atomic manifest pointer; the legacy file path and Workspace manifest are compatibility projections with rollback, while private content pointers are removed from API responses.
  - Mapping artifacts use a generation transaction plus SHA-256 commit marker bound to the model and all preview-ready file content, so query/staging refuse stale, partial, or mixed generations.
  - Run Packages are completed under a hidden staging directory, rewritten to published paths, then atomically published; ordinary failures preserve the incomplete package under same-volume `user_runs/.curation_failed/<workspace_id>` and keep the requested run id reusable. Concurrent publishers cannot recover or move one another's package.
  - Local filesystem access remains a local-substitutable internal seam; no hypothetical storage port was added.
  - `Run Package Resolver` remains read-only and unchanged.
- Contract:
  - Added `tools/check_resource_curation_workspace.py` to exercise the module interface directly on a temporary local filesystem, including version/mirror rollback, stale mapping invalidation, atomic create retry, published-path checks, compatibility-sensitive resource-id semantics, duplicate/named-file errors, mapping transaction failure, staging failure recovery, publish races, and symlink boundaries.
  - HTTP regressions now freeze all six compatibility response key sets, legacy curated-file path projection, exact named-file 404 text, list-valued resource-id behavior, and adapter-added overview.
  - Added `Resource Curation Workspace` to `CONTEXT.md` and documented the seam and required checks in architecture/testing docs.
- Checks:
  - `D:\generate\.venv\Scripts\python.exe -m py_compile api\resource_curation_workspace.py api\resource_curation_helpers.py api\resource_atlas_helpers.py api\services.py api\main.py tools\check_resource_curation_workspace.py`: pass.
  - `D:\generate\.venv\Scripts\python.exe tools\check_resource_curation_workspace.py`: pass.
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "resource_curation" -q`: 5 passed, 31 deselected.
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py tests\test_variant_comparison.py tests\test_enzyme_constraints.py -q`: 46 passed, 2 existing SWIG deprecation warnings.
  - `D:\generate\.venv\Scripts\python.exe tools\check_run_package_resolver.py`: pass.
- Browser QA not run: backend module ownership and compatibility only; no frontend files or HTTP routes changed.
