# 清理候选清单

本文件列出候选，不等于已删除。默认策略是先隔离归档，确认无问题后再决定是否删除。

## 已确定可隔离

| 路径 | 类型 | 原因 |
| --- | --- | --- |
| `debug.log` | 临时日志 | 根目录调试输出，不是运行输入 |
| `gurobi.log` | 求解器日志 | 可再生成，不是配置 |
| `__pycache__/` | Python cache | 可再生成 |
| `.pytest_cache/` | pytest cache | 可再生成 |
| `api/__pycache__/` | Python cache | 可再生成 |
| `omics_router/__pycache__/` | Python cache | 可再生成 |
| `tools/__pycache__/` | Python cache | 可再生成 |
| `tests/__pycache__/` | Python cache | 可再生成 |

## 暂不处理但建议后续审查

| 路径 | 原因 |
| --- | --- |
| `.runtime_cache/` | 体积大，但可能包含 SAMMI/vendor/cache，需确认启动依赖 |
| `.tmp/` | 体积大，但可能包含近期渲染或中间文件 |
| `tmp/` | 临时输出，需确认是否被文档或 case 引用 |
| `desktop_staging/` | 桌面打包产物，建议按 release 归档 |
| `desktop_dist/` | 桌面发行产物，建议按 release 归档 |
| `desktop_installer/` | 安装包产物，建议按 release 归档 |
| `paper/ui_qa/` | QA 截图多，但可作为演示证据 |
| `paper/ui_mockups/` | mockup 可归档，但可能仍有设计参考价值 |

## 禁止直接清理

- `resources/cached_search/`
- `resources/case_display_manifest.json`
- `case_studies/`
- `user_runs/`
- `frontend/src/`
- `api/`
- `omics_router/`
- `tests/`
