# Omics-GEM Studio 文档导航

本目录是当前工程文档入口。文档以中文为主，保留 API、artifact、method id、CSV 字段等英文技术术语。

## 快速入口

- [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md)：项目目标、四阶段 workflow、核心能力边界。
- [RESEARCH_INTERESTS.md](RESEARCH_INTERESTS.md)：由当前项目凝练出的研究兴趣、核心科学问题、方法路线与长期目标。
- [ARCHITECTURE.md](ARCHITECTURE.md)：前端、FastAPI、tools、resources、case studies、user runs 的工程结构。
- [WORKFLOW_SPEC.md](WORKFLOW_SPEC.md)：`Input -> Model Generator -> Analysis -> Summary` 的阶段契约。
- [TESTING_QA.md](TESTING_QA.md)：推荐测试命令、浏览器 QA 主线、乱码扫描说明。
- [RECOVERY_AND_BACKUP.md](RECOVERY_AND_BACKUP.md)：清理回滚、备份边界、当前 `.git` 状态说明。
- [CLEANUP_MANIFEST.md](CLEANUP_MANIFEST.md)：已归档文件和恢复路径。
- [CLEANUP_DEPENDENCY_AUDIT.md](CLEANUP_DEPENDENCY_AUDIT.md)：第二批大目录只读依赖审计。
- [QA_LOG.md](QA_LOG.md)：工程治理期间的回归检查记录。
- [TECH_DEBT_REGISTER.md](TECH_DEBT_REGISTER.md)：已知技术债和后续修补项。
- [LEGACY_README_ARCHIVE.md](LEGACY_README_ARCHIVE.md)：旧根 README 全文归档，仅作历史参考。

## 功能规格

- [RESOURCE_ATLAS_SPEC.md](RESOURCE_ATLAS_SPEC.md)：Resource Atlas、metadata cache、readiness、case/candidate/workspace 边界。
- [MODEL_GENERATOR_SPEC.md](MODEL_GENERATOR_SPEC.md)：Dossier、Method Workbench、generation route 的 UI 和 payload 边界。
- [MODEL_COMPARE_SPEC.md](MODEL_COMPARE_SPEC.md)：ReactionDiff、Difference Map、Constraint Evidence、Behavior、缺失证据语义。
- [CASE_STUDY_SPEC.md](CASE_STUDY_SPEC.md)：case display manifest、readiness、prepare-lite、QA matrix。

## 用户和部署文档

- [快速入门.md](快速入门.md)：面向非开发用户的快速使用说明。
- [详细使用手册.md](详细使用手册.md)：桌面版和主要功能使用说明。
- [分发说明.md](分发说明.md)：安装包和 portable runtime 分发说明。
- [LOGIN_AND_NETWORK_DEPLOYMENT.md](LOGIN_AND_NETWORK_DEPLOYMENT.md)：共享密码和联网部署边界。
- [LOCAL_CLOUDFLARE_TUNNEL_DEPLOYMENT.md](LOCAL_CLOUDFLARE_TUNNEL_DEPLOYMENT.md)：本机反代和 Cloudflare quick tunnel 演示方案。

## 维护原则

- 不把 metadata-only / raw-only 公共资源标成 `ready_for_import`。
- 不用 `0` 表示未生成或不可用的 ecModel / capacity / FVA / validation evidence。
- 清理文件先进入 `_cleanup_quarantine/YYYYMMDD/`，不要直接删除。
- 如果 `.git` 仍不可用，任何大改动前都应先做外部目录级备份。
