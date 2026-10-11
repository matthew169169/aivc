# Model Compare Spec

## 目标

Model Compare 用于解释 Model Generator 在上游如何修改模型。当前默认产品形态是左右双网络对比，而不是旧的 Difference Map / Constraint Evidence / Behavior 工作区。

核心问题是：用户选择 reference variant 和 target variant 后，能看到哪些 reaction 被新增、删除、修改 bounds，哪些 reaction 被 proteomics / kcat / annotation / package-ready 证据映射，以及缺失的 ecModel/capacity 证据为什么不可用。

## 事实层

- `workflow_results/model_edit_reaction_index.csv` 是新版 Compare 的主要事实层。
- `workflow_results/model_edit_manifests/{variant_id}.json` 记录每个 variant 的来源模型、目标模型、证据文件、生成方法和 edit summary。
- `/api/runs/{run_id}/model-comparison/pair` 继续兼容旧字段，同时返回：
  - `edit_context_summary`
  - `model_edit_diff_index`
  - `network_graphs.reference_edit`
  - `network_graphs.target_edit`
- 新 workflow 生成的 edit records 标为 `direct`；旧 run 通过 backfill 推断的记录标为 `inferred_legacy`。

## UI 行为

- 顶部提供 reference model、target model、sync submap、左右 submap selectors。
- 中间是左右两个 network pane；默认同步子图，也允许左右独立选择。
- 下方展示 Modification Dashboard 和 Legend。
- 点击 reaction 节点后打开 detail Sheet，显示 edit type、bounds before/after、evidence flags、capacity status、source files 和外链。
- 旧 `ReactionDiff` 字段保留为后端兼容层，但前端默认不再展示旧四视图和 ranking。

## 视觉语义

- `added`：绿色节点或绿色外圈。
- `removed`：淡灰 ghost 节点，低透明度或虚线。
- `bounds_changed`：误差棒 glyph。
- `proteomics_mapped` / `kcat_mapped`：蓝色 evidence highlight。
- `package_ready_only`：弱化 package-ready 标记，不显示为真实 enzyme capacity 数值。
- `unchanged`：中性样式。

## 缺失证据语义

真实 artifact 已生成且值确认为 0 时才显示 `0`。未生成或不可用时必须显示状态标签：

- `not generated`
- `reaction-level unavailable`
- `summary-level only`
- `package-ready only`
- `external pending`
- `evidence-only case`

## 禁止行为

- 不用一侧图伪装成另一侧图。
- 不把 GECKO enzyme pseudo reactions 混入 conventional GEM structural diff。
- 不把 condition-level summary 强行映射到 reaction。
- 不在没有真实 reaction-level capacity 时显示 `ENZYME CAPACITY 0`。
- 不在 Compare 中自动运行 MATLAB、GECKO、RAVEN、FVA 或在线 kcat 查询。
