# 第二批清理候选依赖审计

本文件只记录依赖审计结论，不移动文件、不删除文件。

## 目录概览

| 目录 | 文件数 | 体积 | 初步结论 |
|---|---:|---:|---|
| `.runtime_cache/` | 6676 | 1447.6 MiB | 运行缓存和 vendor cache，当前有代码直接读取，不能移动 |
| `.tmp/` | 6208 | 1076.1 MiB | 浏览器/渲染/演示临时输出，需进一步按子目录审计 |
| `tmp/` | 1 | 4.2 MiB | 小型临时目录，后续可单独确认 |
| `desktop_staging/` | 6399 | 1630.7 MiB | 桌面 staging 产物，被 installer/检查脚本引用 |
| `desktop_dist/` | 81 | 387.5 MiB | Electron runtime build 产物，被桌面状态检查引用 |
| `desktop_installer/` | 13 | 290.3 MiB | 安装包与 smoke report 产物，被 README 和 API 状态页引用 |

## 代码引用摘要

- `.runtime_cache` 被 `api/services.py`、`omics_router/cobra_runner.py`、`omics_router/model_qc.py`、`omics_router/troppo_runner.py`、`omics_router/sammi_visualization.py` 和多个桌面 packaging 脚本引用。
- `.tmp` 被 demo recording 脚本使用，也可能包含近期浏览器 profile / render 输出。
- `desktop_staging` 被 `tools/package_desktop_installer.ps1`、`tools/check_desktop_staging.ps1`、`api/services.py` 和 README 引用。
- `desktop_dist` 被 Electron packaging、桌面状态检查和测量脚本引用。
- `desktop_installer` 被 README、桌面分发文档、installer smoke 脚本和 `api/services.py` 引用。

## 当前处理建议

- 不移动 `.runtime_cache/`，除非先确认 SAMMI vendor、desktop bootstrap、installer local smoke、COBRA workspace cache 都不需要。
- 不移动 `.tmp/`，先按子目录生成更细粒度清单。
- `tmp/` 可作为第三轮清理候选，但仍需确认唯一文件用途。
- `desktop_*` 目录按 release artifact 管理，建议后续移动到带日期的 release archive，而不是清理到 quarantine。

## 后续检查命令

```powershell
rg -n "\.runtime_cache|\.tmp|desktop_staging|desktop_dist|desktop_installer|\\tmp|/tmp|tmp\\" api omics_router tools frontend\src docs README.md -S
```

如需进一步压缩项目体积，优先做 release archive 方案，不要直接删除桌面构建产物。
