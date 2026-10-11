# Case Study Spec

## Current Note: Shewanella Integrated Overview

`shewanella_integrated_overview` is the default visible Shewanella demo case.
It is a composite display case, not a physical merge of run packages:

- `Input`, `Model Generator`, and `Model Compare` use `shewanella_gecko_case`.
- `Analysis` and `Summary` use `shewanella_transcriptional_triggers_case`.
- The legacy source cases `shewanella_gecko_oxygen` and
  `shewanella_transcriptional_triggers_lac_lb` are hidden from the default case
  dropdown but remain addressable through direct readiness/API calls.
- The combined report index only links existing report artifacts. It must not
  create new scientific results, fake condition bounds, fake enzyme capacity,
  fresh D2T2 recomputation, or fresh dFBA solver output.

## 目标

Case Study 用于可演示地串联 Input、Model Generator、Model Compare、Analysis 和 Summary。每个 case 必须有 manifest、readiness、story、默认 compare 设置和 QA matrix。

## 当前 case

- Shewanella GECKO oxygen condition：完整 ecModel demo。
- P. putida acetate tolerance / isoprenol：proteomics + kcat/package-ready evidence。
- Synechocystis SpkB carbon limitation：proteomics/phosphoproteomics/metabolomics evidence。

## 必备 artifact

- `case_display_manifest.json`
- `case_display_readiness.json`
- `case_autopilot_log.json`
- `case_qa_matrix.csv/json`

## Prepare-lite

Prepare-lite 只补最小展示 artifact：

- readiness
- ReactionDiff smoke
- 默认 submap graph
- QA matrix

不得运行：

- MATLAB / GECKO / RAVEN
- 在线 kcat 查询
- FVA/solver 扩展
- 伪造 ecModel/capacity

## Shewanella Trigger Round 2F 展示边界

`shewanella_transcriptional_triggers_lac_lb` 是论文复现展示 case，不是完整算法重跑 case。

- GDM：显示为 `computed_lite`，使用已解析的 Supplement/GEO 数据做轻量复现。
- D2T2：显示为 `paper_reported_only`，不声称重新训练 M3D/static perturbation compendium。
- dFBA/glycogen：显示为 `paper_reported_model_prediction_available`，展示论文补充数据中的模型预测曲线。
- bounds：显示为 `not_generated`，除非后续提供 solver-ready curated bounds。
- enzyme capacity：显示为 `not_applicable`，因为该论文不是 proteomics/kcat/ecModel case。

报告出口使用 `shewanella_trigger_reproduction_report` preset，输出
`report_results/shewanella_trigger_reproduction_report.html` 和
`report_results/paper_reproduction_report_manifest.json`。
