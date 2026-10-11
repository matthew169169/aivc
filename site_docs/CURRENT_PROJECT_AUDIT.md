# 当前项目审查报告

审查日期：2026-06-23  
项目根目录：`D:\generate`

## 结论

当前项目已经从原型发展成包含 Web 前端、FastAPI 后端、Resource Atlas、Model Generator、Model Compare、case study、桌面打包和公网演示脚本的综合应用。主要问题不是功能缺失，而是长期迭代后边界变厚：

- `frontend/src/App.tsx` 约 1.34 万行，是前端主要复杂度来源。
- `api/services.py` 约 8900 行，聚合了 resources、case、workflow、compare、summary 等多种服务。
- 根目录同时承载源码、缓存、桌面构建、case 数据、论文材料、运行结果和部署文件。
- 当前 `.git` 目录存在但 `git status` 无法识别为有效仓库，需要视为“没有可靠版本回滚”。

## 目录现状

| 区域 | 用途 | 风险判断 |
| --- | --- | --- |
| `frontend/` | React/Vite/Electron/Tauri 前端 | 核心源码，不能清理；应渐进拆分 |
| `api/` | FastAPI 入口与服务层 | 核心源码，不能清理；应拆分服务 |
| `omics_router/` | workflow、模型生成、可视化、报告等核心库 | 核心源码，不能清理 |
| `resources/` | Resource Atlas index/cache/case manifest | 核心数据，不直接移动 |
| `case_studies/` | 本地案例和论文数据 | 体积最大，默认只读保留 |
| `user_runs/` | 用户运行包和演示 run | 演示依赖，默认保留 |
| `tools/` | harvesting、case、部署、打包脚本 | 需要分类文档，不直接删 |
| `desktop_*` | 桌面打包与 staging | 体积大，后续可单独归档策略 |
| `paper/` | 计划、QA、论文、mockup | 内容混杂，但包含重要上下文 |
| `.runtime_cache` / `.tmp` / `tmp` | 运行缓存和临时输出 | 可作为后续清理重点 |

## 大文件与大目录

当前体积大头：

- `case_studies/`：约 33 GB，主要是本地案例、论文与输入数据。
- `frontend/`：约 3 GB，包含依赖和构建相关内容。
- `desktop_staging/`：约 1.6 GB，桌面 staging 产物。
- `.runtime_cache/`：约 1.4 GB，运行缓存。
- `.tmp/`：约 1.0 GB，临时输出。
- `paper/`：约 946 MB，论文、计划和 QA 材料。
- `.venv/`：约 769 MB，Python 环境。
- `user_runs/`：约 499 MB，演示和用户运行包。

## 入口与测试

前端：

- `frontend/package.json`
- 常用命令：`npm.cmd run typecheck`、`npm.cmd run build`

后端：

- `api/main.py`
- 主要 API：health、auth、workspace、resources、case-studies、runs、workflow、model-comparison、visualizations、reports、jobs、files。

测试：

- `tests/test_fastapi_api.py`
- `tests/test_resource_harvest_tools.py`
- `tests/test_variant_comparison.py`
- `tests/test_enzyme_constraints.py`
- `tests/test_upload_workflow.py`

## 本轮清洁边界

可以安全隔离的第一批内容只限：

- 根目录临时日志：`debug.log`、`gurobi.log`
- 根目录和源码目录中的 Python cache：`__pycache__`
- 根目录 `.pytest_cache`

暂不清理：

- `case_studies/`
- `user_runs/`
- `resources/cached_search/`
- `paper/`
- `desktop_*`
- `.runtime_cache`
- `.tmp`
- `.venv`

这些目录可能很大，但和演示、数据、环境或打包有关，需要后续单独确认。
