# Model Generator Spec

## 目标

Model Generator 用于在生成模型前确认当前模型、omics 输入和可用方法。页面分为两块：

- Model & Omics Dossier
- Method Workbench

## Dossier

必须显示：

- 模型名称、物种、格式、source file
- reaction / metabolite / gene 规模
- 上传或 staged omics 类型
- omics rows、unique genes/proteins、conditions、files 等可发现计数
- Atlas provenance 和 case story

没有统计字段时显示 `not indexed` 或 `row count only`，不能填假数字。

## Method Workbench

正式可选路线包括：

- E-Flux
- FASTcore
- Consensus Context
- GECKO-ready ecModel

Advanced packages 如 TROPPO、pyTFA 只能作为高级准备包，不默认写入运行 payload。

## 禁止行为

- 不把 `Baseline GEM` 当成用户可选普通方法。
- 不把缺 kcat/protein pool 的 GECKO-ready 标为完整 ecModel。
- 不自动运行外部 MATLAB/GECKO/RAVEN。
