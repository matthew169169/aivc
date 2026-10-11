# 技术债登记表

## P0: 演示稳定性

| 问题 | 影响 | 当前处理 |
| --- | --- | --- |
| `.git` 目录存在但不是可用仓库 | 无可靠 git diff / rollback 基线 | 不做不可逆删除；大改前建议外部备份或重新初始化仓库 |
| 缺失证据曾显示为 `0` | 用户会把“未生成”误解为真实零值 | 已统一为 `not generated`、`reaction-level unavailable`、`external pending` 等状态标签 |
| case study 依赖分散 | 下拉选择后可能无法完整展示 | 使用 case manifest、readiness、prepare-lite、QA matrix 作为事实源 |

## P1: Model Compare 收口后剩余项

| 问题 | 影响 | 当前处理 |
| --- | --- | --- |
| 旧 Difference / Constraint / Behavior / Ranking 事实字段仍保留在兼容代码中 | 文件体积和认知负担仍偏大 | 前端默认已切换为左右双网络；旧字段仅保留后端兼容，后续确认无依赖后再清理 |
| 旧 case 的 edit provenance 是 backfill 推断 | 不能代表完整上游直接留痕 | 标记为 `inferred_legacy`；新 workflow 生成的记录标记为 `direct` |
| P. putida / Synechocystis 没有真实 ecModel/capacity | Compare 只能展示 evidence/package-ready，不能展示真实 enzyme usage | UI 显示 `external pending` 或 `reaction-level unavailable`，不伪造数值 |
| Synechocystis 默认 compare graph 仍可能是 `needs_filtering` | 子图可解释性不如 Shewanella / P. putida | prepare-lite 只记录状态；后续可补默认 submap graph 渲染，不伪造图 |
| shadcn/Radix Select 有 controlled/uncontrolled warning | 真实浏览器 console 有非阻塞 warning，影响 QA 干净度 | 记录为 UI polish；后续统一 Select 初始 value/defaultValue 语义 |

## P1: Resource Curation Workspace 持久化

| 问题 | 影响 | 当前处理 |
| --- | --- | --- |
| Run Package 目录发布与 Workspace `staged` 标记跨两个目录，尚无进程崩溃 journal | 进程恰在原子发布后、Workspace 状态写入前被强制终止时，会留下完整 package 但 Workspace 未提交；相同 run id 重试会冲突 | 普通异常已自动把本次 package 隔离到同卷恢复区并释放 run id；后续补启动时 reconciliation，将完整 provenance package 与 Workspace 自动对账 |

## P2: 浏览器 QA 自动化

| 问题 | 影响 | 当前处理 |
| --- | --- | --- |
| HTTP/API smoke 不能替代真实视觉 QA | 可能出现“测试通过但界面拥挤”的问题 | 每轮 UI 改动仍需要 in-app Browser 手动 QA |
| strict browser 在部分本机环境不稳定 | 自动截图/视觉断言不够可靠 | 保留 HTTP/API smoke；真实视觉检查写入 `docs/QA_LOG.md` |

## P3: 科学能力后续扩展

| 问题 | 影响 | 当前处理 |
| --- | --- | --- |
| FVA、GECKO、RAVEN、MATLAB 外部运行未自动化 | Compare 不能自动生成真实 behavior / capacity 输出 | 当前只读取已有 output；外部运行作为后续科学扩展 |
| 在线 kcat 查询不在本轮执行 | P. putida / Synechocystis kcat 可能仍是 package-ready 或 partial | 不联网补齐；只显示已有 evidence 和缺口 |
| full-model graph 可能过大 | 无 scoped annotation group 时不适合直接渲染 | Compare 默认依赖 annotation group / submap；缺 scope 时显示 guidance |

## P4: 工程结构

| 问题 | 影响 | 当前处理 |
| --- | --- | --- |
| `frontend/src/App.tsx` 仍偏大 | 后续 UI 修改仍有牵连风险 | 已拆出 workflow、Resource Atlas、Input、Summary、Analysis、Model Compare 部分展示组件和 adapters；继续小步拆分 |
| `api/services.py` 仍偏大 | 后端边界仍不够清晰 | Resource Curation Workspace 生命周期已深化为独立 typed module，`services.py` 保留兼容 adapter；继续按完整生命周期小步迁移，避免只抽 shallow helpers |
| `case_studies/`、`user_runs/`、`resources/cached_search/` 数据量大 | 备份和协作成本高 | 不直接删除；后续制定 release artifact/cache archive 规则 |
