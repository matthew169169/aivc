# Omics-GEM Router

## Current Engineering Entry

The current engineering documentation starts at:

```text
docs/README.md
```

Use it for the maintained project overview, architecture, workflow specs,
Resource Atlas / Model Generator / Model Compare specs, testing guidance, and
cleanup/recovery notes. Some older sections below are retained as historical
desktop/runtime notes and may contain legacy encoding artifacts.

Current local browser-app launcher:

```powershell
cd D:\generate
.\start_omics_gem_browser_app.ps1
```

Desktop installer/runtime notes are still kept below for distribution work.

## Current Recommended Startup

For normal use from this project folder, start the packaged Electron runtime:

```powershell
cd D:\generate
.\start_omics_gem_studio.bat
```

This launcher calls `start_omics_gem_desktop.ps1 -Runtime`, runs the runtime-only Python bootstrap when needed, and then opens the React/Electron UI. The installer artifact is available at:

```text
D:\generate\desktop_installer\Omics-GEM-Studio-Setup.exe
```

If you run the installer, use the installed `start_omics_gem_studio.bat` entrypoint rather than launching the Electron exe directly, because the batch file sets the project root and performs first-run bootstrap.

## User-Facing Documentation

For sharing this tool with non-developer users, send the installer plus the two Chinese user documents:

```text
D:\generate\desktop_installer\Omics-GEM-Studio-Setup.exe
D:\generate\docs\快速入门.md
D:\generate\docs\详细使用手册.md
```

Distribution guidance is in:

```text
D:\generate\docs\分发说明.md
```

If the installer is blocked by local security policy, use the portable runtime zip instead:

```text
D:\generate\desktop_installer\Omics-GEM-Studio-runtime-staging.zip
```

Do not distribute only `desktop_runtime\win-unpacked\Omics-GEM Studio.exe`; it needs the runtime launcher, backend source, bootstrap script, and requirements files around it.

Legacy/developer entrypoints are still kept for debugging:

```text
start_omics_gem_router.bat   Streamlit legacy UI
start_omics_gem_web.bat      React dev web UI
start_omics_gem_api.bat      FastAPI only
start_omics_gem_tauri.bat    Tauri feasibility prototype
```

To preview or archive old generated artifacts safely:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\cleanup_legacy_artifacts.ps1 -IncludeCaches
powershell -NoProfile -ExecutionPolicy Bypass -File tools\cleanup_legacy_artifacts.ps1 -IncludeCaches -Apply
```

Use `-IncludeLegacyLaunchers` or `-IncludeLegacyStaticHtml` only when you intentionally want to archive older entrypoints or the old standalone `index.html`.

## Tauri Desktop Prototype

Phase 8 adds a minimal Tauri v2 desktop-shell prototype next to the existing
Electron shell. Tauri is not the default desktop route yet; it is a feasibility
prototype that reuses the same React frontend and local FastAPI backend.

Prerequisites for building Tauri on Windows:

```text
Rust / Cargo
Microsoft C++ Build Tools
Microsoft Edge WebView2 Runtime
Node.js and npm.cmd
Project .venv with the Python FastAPI backend dependencies
```

Useful commands:

```powershell
cd frontend
npm.cmd run tauri:check
npm.cmd run tauri:build
```

Or from the project root:

```powershell
.\start_omics_gem_tauri.bat
.\start_omics_gem_tauri.ps1 -Dev
.\start_omics_gem_tauri.ps1 -Build
```

The Tauri shell checks `http://127.0.0.1:8765/api/health`. If no healthy API is
running, it starts:

```powershell
.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8765
```

Current Phase 8 measurements can be regenerated with:

```powershell
python tools\measure_desktop_shells.py
```

Outputs:

```text
desktop_metrics/desktop_shell_comparison.json
desktop_metrics/desktop_shell_comparison.csv
paper/Electron_vs_Tauri_可行性复评.md
```

Current status: Tauri builds successfully and produces a small Windows NSIS
setup, but it still depends on the project `.venv` and backend source tree. The
recommended route is to keep Electron as the current mainline desktop shell and
continue validating Tauri as the smaller future shell.

Phase 9 adds desktop runtime hardening for both Electron and Tauri. In the React
Settings page, desktop mode can now check API health, restart only shell-owned
FastAPI processes, open runtime logs, and report port conflicts without killing
external services. Manual validation steps are tracked in:

```text
paper/Desktop_runtime_smoke_checklist.md
paper/Python_backend_packaging_strategy.md
```

Omics-GEM Router 是一个用于“把多组学数据整合进基因组规模代谢模型（GEM / GSMM）”的原型工具。它的目标不是把组学数据直接当成通量真值，而是先判断每类数据适合转成哪种建模证据或约束，再生成可复现的 workflow、结果表和判读报告。

当前版本已经从“方法推荐器”发展成了一个可执行的多阶段 workflow：用户可以上传 GEM 和多组学数据，先生成一个或多个 model variants，再选择对哪些 variant 做 FBA、production、ML / hybrid 等分析，最后导出不同类型的 HTML report。

## 当前完成度

| 模块 | 状态 |
|---|---|
| 方法路由 / 推荐 | 已实现 |
| 用户上传文件检查 | 已实现 |
| 用户 run package 打包 | 已实现 |
| E. coli demo 数据和约束表生成 | 已实现 |
| COBRApy FBA / pFBA / targeted FVA | COBRApy 可用时可执行 |
| 轻量 GEM model QC | 已实现 |
| Evidence Mode Comparison | 已实现 |
| Condition Interpretation Dashboard | 已实现 |
| Reaction Drill-Down | 已实现 |
| Transcriptomics E-Flux | 已实现 |
| Delta-FBA Lite | 已实现 |
| TROPPO FASTcore | TROPPO 可用时可执行 |
| TROPPO iMAT / GIMME / CORDA | 输入矩阵已准备，真实执行入口待接 |
| Enzyme-capacity bridge | 已实现 |
| GECKO export package + ModelAdapter profile | 已实现，支持 Full / Light ecModel adapter config |
| GECKO adapter probe / external runner | 已 staging，需要本地 MATLAB / GECKO / RAVEN / solver |
| pyTFA export package | 已实现 |
| pyTFA external runner | 已 staging，需要本地 pyTFA |
| MEMOTE external runner | 已 staging，需要本地 MEMOTE |
| Streamlit UI | 已实现 |
| Integrated HTML report | 已实现 |
| Model Variant Registry | 已实现 |
| Variant-aware FBA / pFBA | 已实现，支持 batch variants |
| Multi-Variant Comparison | 已实现 |
| Report Builder Presets | 已实现 |
| UniProt / GPR Model Check | 已实现，本地检查 + 可选 REST enrichment |
| DLKcat / kcat bridge | 已实现，外部 DLKcat runner 为 staging / optional |
| ML PCA / LASSO-lite | 已实现 |
| MINN-style export | 已实现 |
| ML + GEM hybrid runner | 已实现，轻量 baseline scorer |
| Production Analysis / ecFactory-lite | 已实现 |
| React / Electron 主界面 | 已实现，主入口为 DataHub / Model & Analysis / Visualization |
| Guided workflow API | 已实现，主流程使用 `/workflow/run` |
| Legacy pipeline endpoint | 兼容保留，仅 legacy stub |
| SAMMI lightweight interactive viewer | 已实现，支持 filter preview、overlay、SVG/PNG 导出 |
| SAMMI native session export | 已实现，需用户在 local SAMMI 中手动 Load SAMMI Model |
| PyG / DGL graph adapter | adapter manifest 已实现，真实对象导出为 optional dependency |
| Desktop installer | installer shell 已实现，clean Windows/VM 仍需最终认证 |

## 它能做什么

Omics-GEM Router 会根据用户已有的数据类型，推荐合适的 GEM 整合路线：

- 转录组：context-specific evidence、E-Flux bounds、Delta-FBA Lite 条件比较。
- 相对蛋白组：条件间变化证据，并可与转录组形成保守 consensus。
- 绝对蛋白组 + kcat：enzyme-capacity 表、GECKO / sMOMENT 风格输入。
- 胞外代谢组：exchange bounds 和 uptake/secretion 验证目标。
- 胞内定量代谢组：pyTFA / TFA 浓度锚点包。
- 13C-MFA / fluxomics：flux validation、calibration、measured-delta 检查。
- ML priors：带 confidence 的 kcat / thermodynamic prior 表。

工具会输出：

- 方法推荐；
- `run_config.json` / `run_config.yaml`；
- 标准化约束表；
- `model_variant_registry.csv`；
- variant-specific FBA / pFBA 结果；
- multi-variant comparison 表；
- 可选 solver-backed 结果；
- 结果判读 dashboard；
- reaction-level drill-down；
- 可复用的用户上传数据包；
- 可选择 preset 的 HTML report bundle。

## 当前产品 Workflow

推荐使用 Streamlit 图形界面完成完整流程。当前 workflow 分为五个阶段：

1. `Upload & Setup`
   上传 GEM / GSMM、多组学表、condition setup、ID alias 表、UniProt annotation、kcat / DLKcat 结果、production targets 等。这个阶段主要做文件检查、role 推断、ID mapping 和 package staging。

2. `Evidence Preparation`
   把原始数据转成可用于模型构建的 evidence：transcriptomics evidence、relative proteomics evidence、consensus evidence、kcat priors、UniProt / GPR check、DLKcat input 等。

3. `Model Generation`
   用户显式选择要生成或登记的模型变体，例如 baseline GEM、E-Flux-ready model、FASTcore context model、consensus context model、enzyme / GECKO-ready package。结果写入：

   ```text
   workflow_results/model_variant_registry.csv
   workflow_results/model_artifacts/<variant_id>/
   ```

4. `Analysis Selection`
   用户先选择 active model variant，再选择要执行的分析。FBA / pFBA 支持一次选择多个 variants 批量运行；Production 和 Hybrid 模块 v1 仍以第一个 active variant 为主。兼容性预览会提前提示哪些组合会被跳过。

5. `Report Builder`
   用户选择报告 preset，并导出对应 HTML report。旧的 full audit report 仍保留在 `cobra_results/report.html`，新的 preset report 写入 `report_results/`。

核心思想是：

```text
先生成模型变体 -> 再选择分析 -> 最后选择报告类型
```

这比“一键全跑所有模块”更适合真实研究场景，因为用户可以明确知道每个分析到底基于哪个模型变体。

## 快速开始

安装最小依赖：

```powershell
pip install -r requirements.txt
```

启动 Streamlit：

```powershell
python -m streamlit run app.py --server.port 8501
```

Windows 下也可以直接双击：

```text
start_omics_gem_router.bat
```

或用 PowerShell：

```powershell
.\start_omics_gem_router.ps1
```

启动脚本会自动创建并使用项目内的虚拟环境：

```text
.venv
```

默认会安装 `requirements.txt` 和 `requirements-optional.txt`。如果只想安装最小 UI 依赖，可以运行：

```powershell
.\start_omics_gem_router.ps1 -Minimal
```

如果要重建虚拟环境：

```powershell
.\start_omics_gem_router.ps1 -RecreateVenv
```

打开：

```text
http://localhost:8501
```

## React Web App Prototype

当前也提供 Phase 6 的 React + FastAPI 原型界面。它不会替代 Streamlit；它用于验证后续 Electron 桌面软件的前端形态。

先启动 FastAPI：

```powershell
.\start_omics_gem_api.bat
```

确认 API：

```text
http://127.0.0.1:8765/api/health
```

再启动 React 前端：

```powershell
.\start_omics_gem_web.bat
```

或手动运行：

```powershell
cd frontend
npm.cmd install
npm.cmd run dev -- --host 127.0.0.1 --port 5173
```

打开：

```text
http://127.0.0.1:5173
```

React 原型目前包含：

- `DataHub`：查看 runs、run summary、model variants、reports 和 visualization manifests。
- `Workflow Studio`：使用五阶段 workflow API；旧 pipeline endpoint 仅作为 legacy stub 保留，请优先使用 `/workflow/run`。
- `Visualization Studio`：选择 run、variant、grouping、overlay，生成 SAMMI-compatible visualization package。
- `Task Center`：查看本次前端会话触发的 jobs、logs 和 output files。
- `Settings`：查看 API base、backend health 和当前 external SAMMI mode。

如果 PowerShell 直接执行 `npm` 报 execution policy 错误，请使用 `npm.cmd`。这是 Windows PowerShell 脚本策略问题，不是前端代码问题。

## Electron Desktop Shell Prototype

Phase 7 新增 Electron 桌面壳。它会自动启动 FastAPI 后端，等待 `/api/health` ready，然后打开 React UI。

启动桌面版：

```powershell
.\start_omics_gem_desktop.bat
```

或开发模式启动：

```powershell
.\start_omics_gem_desktop.ps1 -Dev
```

也可以在前端目录手动运行：

```powershell
cd frontend
npm.cmd run electron:start
```

Electron v1 行为：

- 如果 `http://127.0.0.1:8765/api/health` 已可用，会复用现有 FastAPI。
- 如果 API 不可用，会用 `.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8765` 自动启动。
- 正常关闭 Electron 窗口时，会停止由 Electron 自己启动的 FastAPI 后端。
- `Settings` 页面会显示 Electron runtime、API mode、日志路径和文件/目录选择按钮。
- 日志写入：

```text
.streamlit_logs/electron_main.log
.streamlit_logs/electron_api.out.log
.streamlit_logs/electron_api.err.log
```

Windows staging package：

```powershell
cd frontend
npm.cmd run electron:package:win
```

输出目录：

```text
desktop_dist/win-unpacked
```

当前 package 是 unsigned staging build，仍依赖项目目录中的 `.venv` 和 Python 后端源码。完整安装器和 Python 科学环境打包会在后续阶段处理。

早期静态前端仍然保留：

```text
index.html
```

不过当前推荐使用 `app.py` 的 Streamlit 版本。

### 首次运行建议

1. 双击 `start_omics_gem_router.bat`，或在 PowerShell 运行 `.\start_omics_gem_router.ps1`。
2. 等待脚本创建 `.venv` 并安装依赖。
3. 浏览器打开 `http://localhost:8501`。
4. 先在 `Pipeline Console` 检查 `Backend Availability`。
5. 如果需要 GECKO，进入 `Local Backend Settings` 填写 `GECKO_HOME`。
6. 如果只是使用上传、推荐、报告、基础 COBRApy 分析，不需要配置 MATLAB / GECKO / pyTFA。

## 运行 E. coli Demo

示例数据目录：

```text
examples/ecoli
```

其中包含：

- `ecoli_transcriptomics_tpm.csv`
- `ecoli_absolute_proteomics.csv`
- `ecoli_relative_proteomics.csv`
- `ecoli_extracellular_metabolomics.csv`
- `ecoli_intracellular_metabolomics.csv`
- `ecoli_fluxomics_13c_mfa.csv`
- `ecoli_ml_kcat_priors.csv`
- `iJO1366 (1).xml`

运行完整 pipeline：

```powershell
python tools\run_ecoli_pipeline.py
```

刷新 HTML report：

```powershell
python tools\build_cobra_report.py
```

报告路径：

```text
examples/ecoli/cobra_results/report.html
```

pipeline 状态：

```text
examples/ecoli/pipeline_results/pipeline_run_manifest.json
examples/ecoli/pipeline_results/pipeline_steps.csv
```

如果本地缺少 MEMOTE、GECKO、pyTFA 等外部工具，pipeline 可能显示 `completed_with_skips`。这不是失败，而是说明核心流程已完成，外部后端被安全跳过。

## Demo Pipeline

E. coli demo 是一个自动示范流程，适合快速检查环境和输出格式。它会按固定顺序运行：

1. 生成标准化组学约束表。
2. 比较 transcriptomics、relative proteomics、consensus evidence modes。
3. 运行轻量 GEM model QC。
4. stage 或运行 MEMOTE。
5. 运行 COBRApy FBA、pFBA、targeted FVA。
6. 运行 E-Flux 和 Delta-FBA Lite。
7. 检查 consensus context delete-candidate feasibility。
8. 在可用时运行 TROPPO FASTcore。
9. 准备 iMAT、GIMME、CORDA、FASTcore 的 TROPPO 输入矩阵。
10. 生成 condition-level interpretation dashboard。
11. 构建 enzyme-capacity bridge tables。
12. 导出 GECKO package。
13. stage 或运行外部 GECKO workflow。
14. 导出 pyTFA package。
15. stage 或运行外部 pyTFA workflow。
16. 构建 model variant registry。
17. 运行 variant-aware FBA / pFBA。
18. 生成 multi-variant comparison。
19. 构建 integrated HTML report 和 report bundle。

预览 pipeline，不实际运行：

```powershell
python tools\run_ecoli_pipeline.py --dry-run
```

遇到第一个失败就停止：

```powershell
python tools\run_ecoli_pipeline.py --stop-on-failure
```

## 用户上传数据 Workflow

Streamlit 的 `Data Check` 页支持把用户上传数据整理成可复用 run package，并在同一个页面继续执行 custom workflow。

流程：

1. 上传 GEM 模型。
2. 上传一个或多个组学表。
3. 可选上传 condition tables、ID alias table、UniProt annotation、kcat / DLKcat 表、production targets。
4. 工具自动推断每个表的 role。
5. 用户手动确认或修改 role。
6. 可以忽略不进入 workflow 的文件。
7. 点击 `Prepare user run package`。
8. 在 `Custom Package Runner` 中运行 ID mapping、model generation、analysis 和 report builder。

输出目录：

```text
user_runs/<run_id>
```

每个 package 包含：

```text
inputs/model/
inputs/omics/
input_file_map.csv
upload_manifest.json
run_config.json
run_config.yaml
NEXT_STEPS.md
```

准备 package 后，建议按下面顺序操作：

1. `Run ID mapping review`
   检查 gene / protein / metabolite / reaction ID 是否和 GEM 匹配。

2. `Model Generation`
   勾选要生成的模型变体：

   - `Baseline GEM`
   - `E-Flux / Delta-FBA-ready model`
   - `TROPPO FASTcore context model`
   - `Consensus evidence context model`
   - `Enzyme-capacity / GECKO-ready model`

3. `Analysis Selection`
   选择 active variant 和 downstream analyses，例如：

   - `FBA / pFBA / optional FVA`
   - `E-Flux / Delta-FBA`
   - `Evidence Mode Comparison`
   - `ML PCA / LASSO-lite`
   - `MINN-style Export`
   - `Production Analysis / ecFactory-lite`
   - `ML + GEM Hybrid Runner`

4. `Report Builder`
   选择 report preset，然后点击 `Run selected workflow` 或单独点击 `Build selected report preset`。

如果某个分析和当前模型变体不兼容，工具会在 compatibility preview 中提示，并在运行时记录为 `variant_incompatible` 或 `skipped`。这通常不是程序错误，而是说明当前 variant 缺少该分析需要的模型 artifact。

## Model Variants 和 Analysis

每次 custom workflow 会写出一个统一的模型变体注册表：

```text
user_runs/<run_id>/workflow_results/model_variant_registry.csv
```

常见字段包括：

| 字段 | 含义 |
|---|---|
| `variant_id` | 模型变体 ID，例如 `baseline_gem__all`、`fastcore__glucose` |
| `generation_method` | 生成方法，例如 `baseline_gem`、`fastcore` |
| `condition` | 对应条件 |
| `evidence_mode` | 使用的证据类型 |
| `primary_model_path` | downstream analysis 优先使用的模型路径 |
| `context_model_sbml` | 如果 context model 成功导出，这里记录 SBML 路径 |
| `generated_files` | 相关生成文件 |
| `confidence` | 证据强度或使用建议 |
| `compatible_analyses` | 当前 variant 可直接支持的分析 |
| `guidance` | 简短解释 |

FBA / pFBA 的 variant-aware 输出在：

```text
user_runs/<run_id>/variant_cobra_results/<variant_id>/
user_runs/<run_id>/variant_cobra_results/variant_fba_summary.csv
```

多模型比较输出在：

```text
user_runs/<run_id>/variant_comparison/variant_comparison_summary.csv
user_runs/<run_id>/variant_comparison/variant_flux_comparison.csv
user_runs/<run_id>/variant_comparison/variant_evidence_quality.csv
user_runs/<run_id>/variant_comparison/variant_comparison_manifest.json
```

context model artifacts 输出在：

```text
user_runs/<run_id>/workflow_results/model_artifacts/<variant_id>/
```

里面包含 keep / delete / penalize / core reaction 表，以及可选导出的 `context_model.xml`。Streamlit 中可以直接 drill-down 查看这些表。

## Report Builder

旧报告入口仍然是：

```text
user_runs/<run_id>/cobra_results/report.html
```

这是 full audit report，适合调试和完整追踪。

新的 report presets 写入：

```text
user_runs/<run_id>/report_results/
```

支持的 preset：

| Preset | 用途 |
|---|---|
| `full_audit_report` | 完整审计报告，兼容旧报告逻辑 |
| `model_generation_report` | 只关注模型生成、variant registry、context artifacts 和 evidence quality |
| `single_variant_analysis_report` | 只突出某个 selected variant 的分析结果 |
| `multi_variant_comparison_report` | 比较多个 variants 的 FBA、feasibility、evidence quality |
| `production_design_report` | 汇总 Production Analysis、FSEOF-lite、KO/KD/OE、readiness gate |
| `ml_hybrid_report` | 汇总 PCA、LASSO-lite、MINN-style export、hybrid runner 和 graph adapter |

报告选择和 manifest：

```text
user_runs/<run_id>/report_results/report_selection.csv
user_runs/<run_id>/report_results/report_manifest.json
```

## 本地后端设置

`Pipeline Console` 页包含 `Local Backend Settings` 区域，可以保存：

- `GECKO_HOME`
- `PYTFA_THERMO_DB`

保存后会写入：

```text
local_backend_config.json
```

再次运行 pipeline 时，Streamlit 和子进程会自动把这些路径应用到环境变量中。

注意：`GECKO_HOME` 只负责告诉工具 GECKO 在哪里。GECKO 本身仍然需要你本地已经安装好 MATLAB / RAVEN / GECKO。

## 推荐输入格式

最小字段要求：

| 数据类型 | 最小字段 |
|---|---|
| Transcriptomics | `gene_id, sample, value` |
| Absolute proteomics | `protein_id, sample, value, unit` |
| Relative proteomics | `protein_id, sample, value` |
| Extracellular metabolomics | `metabolite_id, sample, value, unit` |
| Intracellular metabolomics | `metabolite_id, compartment, sample, value, unit` |
| Fluxomics / 13C-MFA | `reaction_id, sample, flux, unit` |
| Lipidomics / glycomics | `component_id, sample, value, unit` |
| ML priors | `target_id, target_type, value, confidence` |
| ID alias table | `source_id, model_id, target_type` |
| UniProt annotation | `gene_id, uniprot_id, ec_number` |
| Production targets | `reaction_id, product_name` |
| kcat / DLKcat predictions | `reaction_id, kcat, unit, source` |

常用可选字段：

- `condition`
- `reference_condition`
- `lower_bound`
- `upper_bound`
- `lower_ci`
- `upper_ci`
- `note`

## 主要输出目录

| 目录 | 内容 |
|---|---|
| `examples/ecoli/generated_constraints` | 标准化组学 evidence 和约束表 |
| `examples/ecoli/cobra_results` | FBA、pFBA、FVA、flux validation、HTML report |
| `examples/ecoli/evidence_mode_results` | transcriptomics / proteomics / consensus 比较 |
| `examples/ecoli/context_results` | context feasibility 检查 |
| `examples/ecoli/troppo_results` | TROPPO FASTcore 输出和 omics signal QC |
| `examples/ecoli/troppo_method_results` | iMAT / GIMME / CORDA / FASTcore 输入矩阵 |
| `examples/ecoli/transcriptomics_flux_results` | E-Flux 和 Delta-FBA Lite 输出 |
| `examples/ecoli/interpretation_results` | condition-level interpretation dashboard |
| `examples/ecoli/enzyme_results` | enzyme-capacity bridge tables |
| `examples/ecoli/gecko_package` | GECKO export package |
| `examples/ecoli/gecko_run_results` | GECKO external run 状态和日志 |
| `examples/ecoli/pytfa_package` | pyTFA export package |
| `examples/ecoli/pytfa_run_results` | pyTFA external run 状态和日志 |
| `examples/ecoli/memote_results` | MEMOTE external run 状态和日志 |
| `examples/ecoli/pipeline_results` | pipeline manifest 和每步日志 |
| `examples/ecoli/workflow_results` | model variant registry、analysis context、context artifacts |
| `examples/ecoli/variant_cobra_results` | variant-specific FBA / pFBA 输出 |
| `examples/ecoli/variant_comparison` | 多模型比较输出 |
| `examples/ecoli/report_results` | report preset HTML、manifest 和 selection |
| `user_runs` | 用户上传数据 staging package |

## Reaction Drill-Down

Streamlit 的 `Evidence Comparison` 页包含 reaction lookup。

可以试：

```text
R_PFK
R_PYK
R_PDH
R_ICL
R_MALS
R_EX_ac_e
```

单个反应可以同时查看：

- transcriptomics evidence；
- relative proteomics evidence；
- consensus evidence；
- context policy decision；
- FASTcore core 状态；
- TROPPO selected / removed membership；
- E-Flux 原始 bounds 和 constrained bounds；
- E-Flux predicted flux；
- Delta-FBA Lite expression direction；
- predicted flux delta；
- measured flux delta residual。

## 方法边界

当前版本区分“已执行”和“已 staging / input-ready”。

已执行或本地可执行：

- COBRApy FBA / pFBA / targeted FVA；
- variant-aware batch FBA / pFBA；
- context feasibility；
- E-Flux；
- Delta-FBA Lite；
- TROPPO FASTcore；
- lightweight model QC；
- evidence comparison；
- result interpretation；
- reaction drill-down；
- UniProt / GPR model check；
- kcat prior merge / conflict check；
- enzyme-capacity check；
- GECKO export package；
- ML PCA / LASSO-lite；
- MINN-style export；
- lightweight ML + GEM hybrid runner；
- Production Analysis / ecFactory-lite；
- multi-variant comparison；
- report builder presets。

已 staging 或 input-ready：

- iMAT / GIMME / CORDA；
- GECKO external workflow；
- DLKcat external workflow；
- pyTFA external workflow；
- MEMOTE external workflow。

注意：当前 `Delta-FBA Lite` 是基于 E-Flux 条件通量解的 reference-vs-target 差异判读，不是完整论文级 Delta-FBA 优化 formulation。它适合作为 directional guidance。

## 开发与测试

运行全部测试：

```powershell
python -m pytest
```

常用命令：

```powershell
python tools\build_ecoli_demo_constraints.py
python tools\run_cobra_baseline.py
python tools\compare_evidence_modes.py
python tools\run_transcriptomics_flux.py
python tools\run_troppo_fastcore.py --evidence-mode consensus
python tools\prepare_troppo_methods.py --evidence-mode consensus
python tools\build_condition_dashboard.py
python tools\run_enzyme_constraints.py
python tools\export_gecko_inputs.py
python tools\export_pytfa_inputs.py
python tools\build_cobra_report.py
```

常用验证命令：

```powershell
python -m py_compile app.py omics_router\report_builder.py omics_router\variant_comparison.py omics_router\model_generation.py omics_router\user_pipeline.py omics_router\report.py
python -m pytest tests/test_report_builder.py tests/test_variant_comparison.py tests/test_user_pipeline.py tests/test_report.py
python -m pytest
```

桌面壳 smoke 验证：

```powershell
.\.venv\Scripts\python.exe tools\smoke_desktop_runtime.py
.\.venv\Scripts\python.exe tools\measure_desktop_shells.py
```

`smoke_desktop_runtime.py` 会实际启动 Electron/Tauri 桌面壳和本地 FastAPI，用于检查自动启动、复用已有后端、端口冲突保护、SAMMI package job、report bundle job 和关闭清理。结果写入 `desktop_metrics/desktop_smoke_results.json/csv`，并由 `measure_desktop_shells.py` 汇总到 `paper/Electron_vs_Tauri_可行性复评.md`。

后端 Python 环境检查：

```powershell
curl http://127.0.0.1:8765/api/environment/backend
```

React / Electron / Tauri 的 `Settings` 页面也会显示同一份只读 readiness：当前 Python、`.venv`、必需依赖、可选分析依赖、COBRApy 状态和建议修复命令。v1 只显示检查结果，不会自动安装或修改环境。

后端 Python 环境修复预览：

```powershell
curl -X POST http://127.0.0.1:8765/api/environment/backend/repair ^
  -H "Content-Type: application/json" ^
  -d "{\"mode\":\"minimal\",\"dry_run\":true}"
```

在 React / Electron / Tauri 的 `Settings` 页面可以启动同一类 repair job。默认是 dry run；真实修复需要手动输入 `REPAIR_PYTHON_ENV`。实时重建 `.venv` 不从 API 内执行，需先关闭桌面/API 后端，再使用 `.\start_omics_gem_router.ps1 -RecreateVenv`。

查看最近的后端环境修复 job：

```powershell
curl "http://127.0.0.1:8765/api/jobs?job_type=backend_environment_repair&limit=1"
```

`Settings` 页面会自动显示最近一次 repair job 的状态和日志预览；完整 job 仍可在 `Task Center` 查看。

Workspace root API：

```powershell
curl http://127.0.0.1:8765/api/workspace
curl -X POST http://127.0.0.1:8765/api/workspace/root ^
  -H "Content-Type: application/json" ^
  -d "{\"root\":\"D:\\generate\",\"create\":false}"
curl -X POST http://127.0.0.1:8765/api/workspace/reset
```

在 React / Electron / Tauri 的 `Settings` 页面，`Workspace Root` 面板可以把桌面端选择的目录应用为 FastAPI 当前 workspace。切换后 API 会从该目录下的 `user_runs`、`examples`、`task_logs` 读取和写入项目数据；已有 run package 不会被自动移动。

发现并导入已有 run package：

```powershell
curl "http://127.0.0.1:8765/api/workspace/run-packages?root=D:\somewhere&limit=50"
curl -X POST http://127.0.0.1:8765/api/workspace/import-run-package ^
  -H "Content-Type: application/json" ^
  -d "{\"source_path\":\"D:\\somewhere\\user_runs\\old_run\",\"target_run_id\":\"old_run\",\"dry_run\":true}"
```

`dry_run=false` 时会把 source run package 复制到当前 workspace 的 `user_runs/<target_run_id>`。导入不会覆盖已有 run package，也不会删除或修改源目录。React / Electron / Tauri 的 `DataHub` 和 `Settings > Workspace Root` 都提供了同一套 discovery/import 入口。

实际导入后，目标 run package 会写入 `import_manifest.json`，记录 source path、import time、target run id 和 workspace root。`DataHub` 的 run table 会在 `Source` 列显示 `imported` 或 `native`，方便追踪每个 run 的来源。
DataHub 也提供 `Source filter` 和 `Source / path search`，可按 `native` / `imported` 或 source path 快速筛选 run package。

内置示例 preset：

```powershell
curl http://127.0.0.1:8765/api/workspace/example-presets
curl -X POST http://127.0.0.1:8765/api/workspace/import-example-preset ^
  -H "Content-Type: application/json" ^
  -d "{\"preset_id\":\"ecoli\",\"target_run_id\":\"ecoli\",\"dry_run\":true}"
```

`DataHub > Example Run Presets` 可以把应用目录中的 `examples/ecoli`、`examples/ecoli_real` 一键复制到当前 workspace，适合新用户快速练习，不需要手动寻找示例目录。

DataHub run management：

```powershell
curl http://127.0.0.1:8765/api/runs/<run_id>/import-manifest
curl -X POST http://127.0.0.1:8765/api/runs/<run_id>/archive ^
  -H "Content-Type: application/json" ^
  -d "{\"dry_run\":true}"
curl -X POST http://127.0.0.1:8765/api/runs/<run_id>/archive ^
  -H "Content-Type: application/json" ^
  -d "{\"dry_run\":false,\"confirm_run_id\":\"<run_id>\"}"
```

React / Electron / Tauri 的 `DataHub` 现在提供 selected run actions：查看 import manifest、打开 run 文件夹、查看 report / visualization 输出，以及安全归档。归档不会删除 run，而是只把 active workspace 下的 `user_runs/<run_id>` 移动到 `archived_runs/<run_id>`；内置 examples 和外部 source packages 不会被移动。

Archived run restore：

```powershell
curl http://127.0.0.1:8765/api/runs/archived
curl http://127.0.0.1:8765/api/runs/archived/<run_id>/archive-manifest
curl -X POST http://127.0.0.1:8765/api/runs/archived/<run_id>/restore ^
  -H "Content-Type: application/json" ^
  -d "{\"dry_run\":true}"
curl -X POST http://127.0.0.1:8765/api/runs/archived/<run_id>/restore ^
  -H "Content-Type: application/json" ^
  -d "{\"dry_run\":false,\"confirm_run_id\":\"<run_id>\"}"
```

`DataHub > Archived Runs` 可以查看当前 workspace 的归档 run、读取 `archive_manifest.json`、预览恢复路径，并在输入 run id 确认后把 run 从 `archived_runs/<run_id>` 移回 `user_runs/<run_id>`。恢复不会覆盖已有 active run；若目标已存在会返回冲突。

Desktop runtime status：

React / Electron / Tauri 的 `Settings > Desktop Bridge` 会同时显示 `shell_app_root` 和 `active_workspace_root`。前者用于定位桌面壳、`.venv` 和 runtime logs；后者用于当前 `user_runs`、`examples`、`task_logs` 的读写。切换 workspace 后，判断 run package 和输出位置时应以 `active_workspace_root` 为准。

## 文档

详细模块说明在 `docs/`：

- `MODEL_QC.md`
- `EVIDENCE_MODE_COMPARISON.md`
- `MULTI_OMICS_CONFLICT_QC.md`
- `RELATIVE_PROTEOMICS.md`
- `TRANSCRIPTOMICS_FLUX_METHODS.md`
- `TROPPO_FASTCORE.md`
- `TROPPO_METHOD_MATRIX.md`
- `ENZYME_CONSTRAINTS.md`
- `GECKO_EXPORT.md`
- `GECKO_EXTERNAL_RUNNER.md`
- `PYTFA_EXPORT.md`
- `PYTFA_EXTERNAL_RUNNER.md`
- `MEMOTE_EXTERNAL_RUNNER.md`
- `PIPELINE_ORCHESTRATOR.md`
- `USER_UPLOAD_WORKFLOW.md`

新近 workflow 重构、Report Builder 和 multi-variant comparison 的阶段性记录在：

```text
paper/更新日志.md
paper/后续更新计划方案.md
```

## 设计原则

这个工具的核心原则是：

> 组学数据应该先变成透明的建模证据，而不是隐藏的硬约束。

所以很多输出都会保留 evidence label、status、QC summary、recommendation 和 interpretation notes。这个工具不只是为了“跑算法”，也是为了帮助用户判断结果属于 strong evidence、usable with caution，还是 guidance only。

## Archive / Restore job tracking

DataHub archive and restore actions now use the same FastAPI job/log pattern as SAMMI visualization, report building, and backend repair. The request body is unchanged, but the response is a `JobStatus` object with `job_id`, `job_type`, `status`, `log_path`, and `result`.

```powershell
curl -X POST http://127.0.0.1:8765/api/runs/<run_id>/archive ^
  -H "Content-Type: application/json" ^
  -d "{\"dry_run\":true}"
curl http://127.0.0.1:8765/api/jobs/<job_id>
curl http://127.0.0.1:8765/api/jobs/<job_id>/logs
curl "http://127.0.0.1:8765/api/jobs?job_type=run_archive&limit=20"
curl "http://127.0.0.1:8765/api/jobs?job_type=run_restore&limit=20"
```

`dry_run=true` returns a skipped job whose `result.status` is `dry_run`; real archive/restore returns a completed job whose `result.status` is `archived` or `restored`. Invalid confirmations, protected examples, duplicate archive targets, and restore conflicts are still rejected before a job is created.

## Desktop bootstrap quick start

For the React/Electron desktop prototype, the recommended startup path is now:

```powershell
.\start_omics_gem_desktop.bat
```

The launcher runs `tools\bootstrap_desktop_env.ps1` before opening Electron. The bootstrap checks Python 3.10-3.12, prepares the project-local `.venv`, verifies Node/npm, installs frontend dependencies when needed, and builds `frontend/dist` when it is missing. The first run can take several minutes if dependencies need to be installed.

Useful manual checks:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\bootstrap_desktop_env.ps1 -DryRun -Mode Minimal
powershell -NoProfile -ExecutionPolicy Bypass -File tools\bootstrap_desktop_env.ps1 -DryRun -Mode Full
```

Bootstrap logs are written to `.streamlit_logs\bootstrap_desktop_env.log`; machine-readable status is written to `.runtime_cache\bootstrap_status.json`. Electron and Tauri no longer silently fall back to system Python when `.venv` is missing. For debugging only, set `OMICS_GEM_ALLOW_SYSTEM_PYTHON=1`.

To create a lightweight staging folder:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\package_desktop_staging.ps1
```

The developer/source startup path still needs Node/npm because it can rebuild the React frontend and Electron shell.

For a runtime-first staging package, build the packaged Electron runtime first:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\package_desktop_staging.ps1
```

The generated `desktop_staging\Omics-GEM-Studio` folder contains `desktop_runtime\win-unpacked`, a prebuilt React/Electron runtime, backend source, requirements, and runtime launchers:

```powershell
desktop_staging\Omics-GEM-Studio\start_omics_gem_studio.bat
```

Optional SAMMI standalone vendoring:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\vendor_sammi_standalone.ps1 -DryRun -SourceArchive paper\SAMMI-master.zip
powershell -NoProfile -ExecutionPolicy Bypass -File tools\vendor_sammi_standalone.ps1 -SourceArchive paper\SAMMI-master.zip
powershell -NoProfile -ExecutionPolicy Bypass -File tools\package_desktop_staging.ps1
```

`vendor_sammi_standalone.ps1` can use a local archive such as `paper\SAMMI-master.zip` or download from the configured GitHub URL when no local archive is available. It vendors assets into `.runtime_cache\sammi_vendor`, verifies that `index.html` and license/readme evidence exist, and writes `sammi_vendor_manifest.json`. If the manifest status is `ready`, the staging package copies the assets into `desktop_staging\Omics-GEM-Studio\vendor\sammi_standalone`. If vendoring is blocked or missing, Omics-GEM Studio still uses the built-in lightweight interactive viewer and external SAMMI open mode.

Before redistributing a staging folder or installer that bundles SAMMI assets, review the upstream SAMMI license/readme files recorded in the vendor manifest. The app does not auto-download SAMMI assets at runtime.

SAMMI native session export:

1. In Visualization Studio, choose a run, model variant, overlay, and optional reaction/subsystem filter.
2. Click `Preview / Validate Filter` before rendering. If a reaction id is missing, use `Search reactions` or the suggestion chips. The E. coli demo example is `R_PFK;R_PGI;R_GAPD;R_ICL`.
3. Click `Render Interactive Map` to confirm the focused graph.
4. Click `Export SAMMI Native Session`.
5. Use the `Latest SAMMI Native Session` panel to open `sammi_native_launch.html`, open the output folder, copy the session path, or open local SAMMI.
6. In SAMMI, choose `Load SAMMI Model` and select `sammi_native_session.json`.

The native export writes `sammi_native_session.json`, `sammi_native_export_manifest.json`, `sammi_native_export_summary.csv`, and `sammi_native_launch.html` into the same visualization output folder. It does not automate SAMMI's file picker; this keeps the local viewer compatible with browser security rules.

Each native export also writes `sammi_native_export_check.json` and `sammi_native_export_check.md`. The check verifies the saved-session structure before you try to load it in SAMMI: `currentparsed`, reaction/metabolite nodes, links, and display settings.

If the filter preview returns `empty_filter`, render/export is intentionally blocked in the React UI. This prevents generating an empty SAMMI session from a typo such as an absent reaction id.

Existing native sessions can be rediscovered without re-running export through:

```text
GET /api/runs/{run_id}/visualizations/sammi-native-exports?variant_id=baseline_gem__all
```

The response includes checker status, session path, launch page path, output directory, overlay source, reaction filter, and modified time. React uses this endpoint to show the latest native session whenever a run/variant is selected.

That runtime launcher calls:

```powershell
tools\bootstrap_desktop_env.ps1 -RuntimeOnly -Mode Minimal
```

RuntimeOnly prepares `.venv` and backend Python dependencies only. It skips Node/npm and frontend build checks, so normal staging users only need Python 3.10-3.12. Node/npm remain required for developers who rebuild the frontend or regenerate the Electron package.

To verify the staging folder without opening the GUI:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\check_desktop_staging.ps1
```

The check writes `desktop_staging_smoke_report.json` and `desktop_staging_smoke_report.md` into the staging folder. It verifies the packaged runtime, runtime launchers, backend source, requirements, bootstrap script, Quick Start, Python readiness, and whether runtime files accidentally require Node/npm. Manual clean-Windows GUI validation should follow `paper\Desktop_clean_windows_smoke_checklist.md`.

If Electron packaging reports `Access is denied` under `desktop_dist\win-unpacked`, close all running Omics-GEM Studio / Electron windows and rerun:

```powershell
cd D:\generate\frontend
npm.cmd run electron:package:win
```

The packaging wrapper now checks whether the old `win-unpacked` directory is writable before rebuilding and prints a clear blocker message instead of treating a locked runtime directory as a code failure.

To build the installer shell artifact:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\package_desktop_installer.ps1 -SkipBootstrap
```

The installer shell writes outputs to `desktop_installer/`, including `desktop_installer_manifest.json` and a build log. When `makensis.exe` is available, the script builds `Omics-GEM-Studio-Setup.exe`; otherwise it writes a portable runtime-staging zip fallback and marks the manifest as `portable_zip_fallback`. The installed entrypoint is the runtime launcher, so first startup still runs `bootstrap_desktop_env.ps1 -RuntimeOnly` before opening Electron.

If NSIS is installed but not on `PATH`, pass it explicitly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\package_desktop_installer.ps1 -SkipBootstrap -MakensisPath "C:\Program Files (x86)\NSIS\makensis.exe"
```

This workspace also supports a project-local portable NSIS toolchain. For example:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\package_desktop_installer.ps1 -SkipBootstrap -MakensisPath ".runtime_cache\nsis\nsis-3.12\nsis-3.12\makensis.exe"
```

The current Phase 14 build produced `desktop_installer\Omics-GEM-Studio-Setup.exe`. It is still an installer shell: target machines need Python 3.10-3.12, and scientific optional backends remain external.

To validate the installer artifact without installing it:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\check_desktop_installer.ps1
```

This writes `desktop_installer\desktop_installer_smoke_report.json` and `desktop_installer\desktop_installer_smoke_report.md`. The check verifies the setup exe, manifest, NSIS script, SHA256, source staging files, and runtime launcher evidence. It does not run `Setup.exe`, install files, or create shortcuts. Manual install and clean-Windows first-run validation are tracked in `paper\Desktop_installer_smoke_checklist.md`.

To run a controlled local installer smoke test:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\smoke_desktop_installer_local.ps1
```

The local smoke installs the setup artifact into `.runtime_cache\installer_local_smoke\OmicsGemStudio`, verifies installed files and shortcuts, runs `bootstrap_desktop_env.ps1 -RuntimeOnly -Mode Minimal`, archives bootstrap logs, and then silently uninstalls by default. It writes `desktop_installer\local_install_smoke_report.json` and `desktop_installer\local_install_smoke_report.md`. Use `-DryRun` to preview, `-KeepInstalled` to inspect the installed tree, and `-LaunchGui` only when you want a manual Electron GUI smoke.

## ML/HYBRID profile management and comparison

The React `Workflow Studio` can now manage existing ML/HYBRID profiles, not only create a new one.

Typical flow:

1. Select a run in `DataHub`.
2. Open `Workflow Studio`.
3. In `ML/HYBRID Profile`, run a profile or click `Refresh Profiles`.
4. Select a profile to view benchmark matrix, model metrics, top features, GEM feature importance, subsystem importance, and production candidate overlap.
5. Use `Profile Comparison` to compare existing profiles without rerunning models.
6. In `Visualization Studio`, choose `ML Feature Importance Map` and select a profile from the `ML profile id` dropdown.
7. Build an `ml_hybrid_report` in Report Builder to include profile discovery, comparison, benchmark, and explainability sections.

Related API endpoints:

```text
GET /api/runs/{run_id}/ml-hybrid/profiles
GET /api/runs/{run_id}/ml-hybrid/profiles/{profile_id}
GET /api/runs/{run_id}/ml-hybrid/profile-comparison
POST /api/runs/{run_id}/ml-hybrid/profiles
```

The profile manager reuses existing `ml_hybrid_profiles/<profile_id>/` outputs. It does not install scikit-learn, PyTorch, XGBoost, or Flexynesis, and it does not interpret feature importance as causal mechanism evidence.

ML/HYBRID profile export bundles:

1. Open `Workflow Studio`.
2. Select an existing profile from `Selected profile`.
3. Choose `Export format`:
   - `omics_gem_bundle`
   - `flexynesis_like_inputs`
   - `both`
4. Click `Export Profile Bundle`.
5. Use the file links or, in Electron/Tauri, `Open Export Folder`.

The export job writes:

```text
ml_hybrid_profiles/<profile_id>/exports/omics_gem_profile_bundle/
ml_hybrid_profiles/<profile_id>/exports/flexynesis_like_inputs/
ml_hybrid_profiles/<profile_id>/exports/ml_hybrid_profile_export_manifest.json
ml_hybrid_profiles/<profile_id>/exports/ml_hybrid_profile_export_summary.csv
```

Related API endpoints:

```text
POST /api/runs/{run_id}/ml-hybrid/profiles/{profile_id}/export
GET /api/runs/{run_id}/ml-hybrid/profiles/{profile_id}/exports
```

`flexynesis_like_inputs` is a Flexynesis-inspired multi-view tabular export. It creates view tables such as `omics_view.csv`, `flux_view.csv`, `kcat_readiness_view.csv`, `production_view.csv`, plus `clinical_or_target.csv` and `sample_metadata.csv`. It does not include or run Flexynesis itself.

External ML result import:

1. Run an external ML tool using the exported bundle or Flexynesis-like inputs.
2. Put common result files in one local folder:
   - `prediction_table.csv`
   - `model_metrics.csv`
   - `feature_importance.csv`
   - optional `sample_embeddings.csv`
   - optional `model_config.json`
3. Open `Workflow Studio`, select the source profile, and use `Import External ML Results`.
4. Choose `generic_tabular` or `flexynesis_like`, then import.
5. Review validation flags, GEM feature mapping, and the generated overlay.
6. In `Visualization Studio`, choose `External ML Feature Importance Map` to render imported external importance on a reaction network.

The import writes:

```text
ml_hybrid_profiles/<profile_id>/external_results/<import_id>/external_import_manifest.json
ml_hybrid_profiles/<profile_id>/external_results/<import_id>/external_import_summary.csv
ml_hybrid_profiles/<profile_id>/external_results/<import_id>/external_validation_flags.csv
ml_hybrid_profiles/<profile_id>/external_results/<import_id>/normalized_prediction_table.csv
ml_hybrid_profiles/<profile_id>/external_results/<import_id>/normalized_model_metrics.csv
ml_hybrid_profiles/<profile_id>/external_results/<import_id>/normalized_feature_importance.csv
ml_hybrid_profiles/<profile_id>/external_results/<import_id>/gem_external_feature_importance.csv
ml_hybrid_profiles/<profile_id>/external_results/<import_id>/external_ml_feature_importance_overlay.csv
```

Related API endpoints:

```text
POST /api/runs/{run_id}/ml-hybrid/profiles/{profile_id}/external-results
GET /api/runs/{run_id}/ml-hybrid/profiles/{profile_id}/external-results
GET /api/jobs?job_type=ml_hybrid_external_import
```

External feature importance is treated as predictive marker evidence, not causal proof. GEM re-mapping is best-effort and uses existing feature ids, reaction ids, subsystem annotations, readiness warnings, and production candidate tables.

External import QA and E. coli demo:

- `Workflow Studio` shows a selected external import detail panel with QA status, validation flags, normalized metrics, top feature importance, GEM remapping, and overlay rows.
- Use `E. coli External ML Demo` in the external import section to fill:
  - `source_dir = examples\ecoli\external_ml_demo_results`
  - `result_format = generic_tabular`
  - `import_id = ecoli_external_ml_demo`
- The demo folder contains minimal external ML outputs:
  - `prediction_table.csv`
  - `model_metrics.csv`
  - `feature_importance.csv`
- After import, open `Visualization Studio`, choose `External ML Feature Importance Map`, and render the selected model variant. The map uses the latest imported external ML overlay for the selected/latest profile.
- In reports, `ml_hybrid_report` includes `External Import Detail / QA`, validation flags, and GEM remapping tables.

Detail endpoint:

```text
GET /api/runs/{run_id}/ml-hybrid/profiles/{profile_id}/external-results/{import_id}
```

## GECKO Adapter / ModelAdapter Workflow

GECKO 3 integration now exports more than a generic input folder. When you
select `GECKO-ready` in `Model & Analysis > Model Generation`, Omics-GEM Studio
can generate and validate a GECKO ModelAdapter draft:

```text
gecko_package/gecko_adapter_config.json
gecko_package/gecko_adapter_summary.csv
gecko_package/generated_adapter.m
gecko_package/gecko_protocol_config.json
gecko_package/gecko_adapter_readiness.csv
gecko_package/protocol_template.m
```

The UI supports:

- `full_ecModel`: recommended route for later measured proteomics integration.
- `light_ecModel`: lightweight route for protein-pool style constraints.
- adapter parameters such as organism name, KEGG / UniProt ids, biomass
  reaction, carbon source exchange, enzyme compartment, `sigma`, `Ptot`, `f`,
  and `gR_exp`.
- optional files such as `spontaneousReactions.tsv`, `pseudoRxns.tsv`,
  `customKcats.tsv`, and `uniprotConversion.tsv`.

FastAPI endpoints:

```text
POST /api/runs/{run_id}/gecko/adapter-preview
POST /api/runs/{run_id}/gecko/adapter-probe
GET /api/runs/{run_id}/gecko/status
```

The preview step only writes adapter/config/readiness files. The probe step is
optional and checks MATLAB, `GECKO_HOME`, RAVEN path, generated adapter loading,
and `ModelAdapterManager.setDefault(...)`. If MATLAB or GECKO is missing, it is
reported as `skipped` with guidance; the rest of the workflow continues.

Omics-GEM Studio does not auto-install MATLAB, GECKO, RAVEN, or commercial
solvers. It generates the adapter draft and readiness evidence, but the user
still needs to confirm organism-specific biology before running GECKO
externally.

## Workflow 参数化与复现实验

React / Electron 主界面的 `模型与分析` 现在把参数分为两层：

- `模型生成参数`：写入 `workflow_results/model_generation_parameters.json` 和 `model_generation_parameters_summary.csv`。
- `分析参数`：写入 `workflow_results/analysis_parameters.json` 和 `analysis_parameters_summary.csv`。

用户可以在 `模型生成` 阶段展开每个方法卡片设置关键参数：

- E-Flux / Delta-FBA-ready：表达缩放、最小表达比例、reference condition、上/下调阈值、pFBA。
- FASTcore：evidence mode、core threshold、solver、flux threshold、objective/exchange 保护、feasibility check。
- Consensus context：转录组/蛋白组/ML prior 权重、冲突处理策略、keep/delete/penalize threshold。
- TROPPO iMAT / GIMME / CORDA：high/low threshold、epsilon、objective fraction、confidence cutoff 等输入包参数。
- GECKO-ready：Full / Light ecModel mode、probe/external run flags；完整 ModelAdapter 参数在 GECKO Adapter 面板中设置。

在 `分析选择` 阶段，每张 analysis card 也有参数区：

- FBA / pFBA / FVA：objective override、direction、FVA scope、fraction_of_optimum、loopless、pfba_factor、processes。
- E-Flux / Delta-FBA：reference condition、delta threshold、是否使用 pFBA flux。
- Production / ecFactory-lite / FSEOF-lite：biomass/product reaction、enforced product flux fractions、candidate 数量、KO/KD/OE strategy。
- ML/HYBRID：task type、target column、feature sources、benchmark feature sets、max features。
- UniProt / kcat / DLKcat / MEMOTE / pyTFA：以参数 + readiness + 外部依赖说明的形式呈现，默认不自动运行重型外部工具。

可用参数 API：

```powershell
curl http://127.0.0.1:8765/api/runs/<run_id>/workflow/parameter-schema
curl -X POST http://127.0.0.1:8765/api/runs/<run_id>/workflow/parameter-preview ^
  -H "Content-Type: application/json" ^
  -d "{\"model_generation_methods\":[\"eflux\"],\"analysis_modules\":[\"fba_pfba\"],\"model_generation_parameters\":{\"eflux\":{\"min_expression_fraction\":0.05}},\"analysis_parameters\":{\"fba_pfba\":{\"run_fva\":true}}}"
```

正式运行仍使用：

```powershell
curl -X POST http://127.0.0.1:8765/api/runs/<run_id>/workflow/run ^
  -H "Content-Type: application/json" ^
  -d "{\"model_generation_methods\":[\"baseline_gem\",\"eflux\"],\"analysis_modules\":[\"fba_pfba\"],\"model_generation_parameters\":{},\"analysis_parameters\":{}}"
```
