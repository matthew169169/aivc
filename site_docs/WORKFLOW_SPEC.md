# Workflow Spec

## 阶段

当前稳定产品流程为四阶段：

1. `Input`
2. `Model Generator`
3. `Analysis`
4. `Summary`

`Model Compare` 是 `Model Generator` 内部页面，不是顶层阶段。

## Input

输入来源包括用户上传和 Resource Atlas。上传文件必须有明确 role/type。Atlas metadata-only/raw-only 资源只能进入 provenance 或 curation workspace，不能直接进入可导入 input map。

## Model Generator

展示当前模型和 omics dossier，并让用户选择建模方法。`Baseline GEM` 是 reference，不作为普通用户方法卡展示。GECKO-ready 是 guarded route，缺少 kcat/protein pool 时不能标为完整 ecModel。

## Analysis

Analysis 是方法工作台，不再作为网络地图主入口。网络子图、overlay 和 reaction 外链归属 Model Compare。

## Summary

Summary 汇总输入、生成、对比、分析、报告、缺失项和下一步动作。

## 状态语义

- `ready`：artifact 或 evidence 可用于当前步骤。
- `partial`：部分可用，但有缺口。
- `not generated`：尚未生成。
- `package-ready only`：输入包准备好，但外部计算未完成。
- `reaction-level unavailable`：有全局或摘要信息，但没有 reaction-level 明细。
- `external pending`：需要外部 MATLAB/GECKO/RAVEN 或手动步骤。
