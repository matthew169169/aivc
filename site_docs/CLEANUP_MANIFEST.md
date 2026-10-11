# 清理归档记录

清理策略：不直接删除文件。可再生成的缓存、日志和临时输出统一移动到 `_cleanup_quarantine/YYYYMMDD/`，并在这里记录原路径、归档路径、原因和恢复方式。

## 2026-06-23

| 原路径 | 归档路径 | 原因 | 可恢复 |
| --- | --- | --- | --- |
| `debug.log` | `_cleanup_quarantine/20260623/root_logs/debug.log` | 根目录临时调试日志 | 是 |
| `gurobi.log` | `_cleanup_quarantine/20260623/root_logs/gurobi.log` | 求解器临时日志 | 是 |
| `.pytest_cache/` | `_cleanup_quarantine/20260623/python_cache/.pytest_cache/` | pytest 缓存 | 是，可再生成 |
| `__pycache__/` | `_cleanup_quarantine/20260623/python_cache/root___pycache__/` | Python 缓存 | 是，可再生成 |
| `api/__pycache__/` | `_cleanup_quarantine/20260623/python_cache/api___pycache__/` | Python 缓存 | 是，可再生成 |
| `omics_router/__pycache__/` | `_cleanup_quarantine/20260623/python_cache/omics_router___pycache__/` | Python 缓存 | 是，可再生成 |
| `tools/__pycache__/` | `_cleanup_quarantine/20260623/python_cache/tools___pycache__/` | Python 缓存 | 是，可再生成 |
| `tests/__pycache__/` | `_cleanup_quarantine/20260623/python_cache/tests___pycache__/` | Python 缓存 | 是，可再生成 |
| `.pytest_cache/`、`api/__pycache__/`、`omics_router/__pycache__/`、`tools/__pycache__/`、`tests/__pycache__/` | `_cleanup_quarantine/20260623/post_check_python_cache/` | 第一轮回归后重新生成的缓存 | 是，可再生成 |
| 同上 | `_cleanup_quarantine/20260623/post_check_python_cache_round2/` | 第二轮回归后重新生成的缓存 | 是，可再生成 |
| 同上 | `_cleanup_quarantine/20260623/post_check_python_cache_round3/` | 第三轮回归后重新生成的缓存 | 是，可再生成 |
| 同上 | `_cleanup_quarantine/20260623/post_check_python_cache_round4/` | Model Compare optional evidence 回归后重新生成的缓存 | 是，可再生成 |
| 同上 | `_cleanup_quarantine/20260623/post_check_python_cache_round5/` | Browser QA 与 Input/Summary 拆分回归后重新生成的缓存 | 是，可再生成 |
| 同上 | `_cleanup_quarantine/20260623/post_check_python_cache_round6/` | Model Compare 展示组件拆分回归后重新生成的缓存 | 是，可再生成 |
| 同上 | `_cleanup_quarantine/20260623/post_check_python_cache_round7/` | App.tsx 数据装配瘦身与 Analysis 展示组件拆分回归后重新生成的缓存 | 是，可再生成 |
| 同上 | `_cleanup_quarantine/20260624/post_check_python_cache_round8/` | 后端 services helper 拆分回归后重新生成的缓存 | 是，可再生成 |
| `.pytest_cache/`, `api/__pycache__/`, `tests/__pycache__/` | `_cleanup_quarantine/20260624/test-cache-231224/` | Resource Atlas summary helper refactor regression tests regenerated Python/pytest cache | Yes, regenerated cache only |
| `.pytest_cache/`, `api/__pycache__/`, `tests/__pycache__/` | `_cleanup_quarantine/20260624/test-cache-232741/` | Resource Atlas detail and curation helper refactor regression tests regenerated Python/pytest cache | Yes, regenerated cache only |
| `.pytest_cache/`, `api/__pycache__/`, `tests/__pycache__/` | `_cleanup_quarantine/20260624/test-cache-234642/` | Case Study prepare helper refactor regression tests regenerated Python/pytest cache | Yes, regenerated cache only |

## 恢复方式

如需恢复，将归档路径移动回原路径即可。不要直接删除 `_cleanup_quarantine`，除非已经完成回归测试并确认不再需要。

## 禁止直接清理的目录

以下目录默认不清理、不移动，只做审查记录：

- `.venv`
- `.deps_troppo`
- `.runtime_cache`
- `resources/cached_search`
- `case_studies`
- `user_runs`
- `paper`
- `desktop_staging`
- `desktop_dist`
- `desktop_installer`
