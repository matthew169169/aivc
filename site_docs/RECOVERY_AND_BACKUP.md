# 恢复与备份说明

## 当前回滚基线

当前项目目录存在 `.git/`，但本轮审查中 `git status` 返回 `not a git repository`。因此现阶段不能把 git 当作可靠回滚手段使用。

本轮不重新初始化 git、不移动 `.git/`、不改写 refs。后续如果要正式多人协作，建议先在外部完成一次完整目录备份，再单独修复版本库。

## 清理恢复方式

工程治理采用隔离归档策略：不直接删除疑似废弃文件，而是移动到：

```text
D:\generate\_cleanup_quarantine\YYYYMMDD\
```

已归档文件记录在：

```text
D:\generate\docs\CLEANUP_MANIFEST.md
```

恢复步骤：

1. 在 `CLEANUP_MANIFEST.md` 中找到原路径和归档路径。
2. 确认当前原路径没有新的同名文件。
3. 将归档文件或目录复制回原路径。
4. 运行最小 smoke：后端 `test_fastapi_api.py`、前端 `typecheck/build`，以及相关页面手动检查。

## 禁止直接删除的目录

以下目录包含 case、cache、user run、论文材料或运行环境，不能直接删除：

- `case_studies/`
- `user_runs/`
- `resources/cached_search/`
- `resources/resource_index.json`
- `paper/`
- `.venv/`
- `frontend/`
- `api/`
- `omics_router/`

以下目录体积较大，但仍可能参与运行、渲染或桌面打包。只能先做依赖审计，不能直接归档：

- `.runtime_cache/`
- `.tmp/`
- `tmp/`
- `desktop_staging/`
- `desktop_dist/`
- `desktop_installer/`

## 建议备份节奏

- 每次大规模 UI 或 API 重构前，复制整个 `D:\generate` 到外部目录或压缩包。
- 每次清理前，先更新 `docs/CLEANUP_CANDIDATES.md` 和 `docs/CLEANUP_DEPENDENCY_AUDIT.md`。
- 每次归档后，立即运行测试并更新 `docs/CLEANUP_MANIFEST.md`。

## 失败时的处理

如果启动失败、页面空白、case study 缺文件或 API 404：

1. 先查看最近一次 `CLEANUP_MANIFEST.md`。
2. 恢复最近归档批次。
3. 运行：

```powershell
D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py
cd D:\generate\frontend
npm.cmd run typecheck
npm.cmd run build
```

4. 如果仍失败，把失败命令、错误输出和最近修改文件写入 `docs\TECH_DEBT_REGISTER.md`。
