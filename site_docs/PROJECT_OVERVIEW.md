# Omics-GEM Studio 项目总览

Omics-GEM Studio 是一个面向多组学约束代谢模型构建、比较和解释的本地 Web 应用。当前产品主线是：

```text
Input -> Model Generator -> Analysis -> Summary
```

`Model Compare` 是 `Model Generator` 内部的核心工作区，用于解释 reference model 与 target model 的 reaction-level 差异。

## 核心能力

- **Input**：资源图谱、用户上传、Run Package 创建、Atlas curated evidence handoff。
- **Resource Atlas**：本地 metadata harvesting cache、微生物资源地图、资源检索、curation workspace、candidate package。
- **Model Generator**：展示模型与 omics dossier，选择 E-Flux、FASTcore、Consensus、GECKO-ready 等建模路线。
- **Model Compare**：基于 ReactionDiff 的 Difference Map、Constraint Evidence、Behavior 和 Side-by-side 视图。
- **Analysis**：分析方法工作台，组织 FBA/pFBA、evidence comparison、ML/PCA/LASSO 等方法。
- **Summary**：报告、风险、缺失项、case QA matrix、Atlas provenance。

## 当前工程原则

- 不把 metadata-only/raw-only 公共资源伪装成可导入数据。
- 不用 `0` 表示未生成或不可用证据。
- GECKO/MATLAB/RAVEN 属于外部 guarded workflow，不自动运行。
- Shewanella 是完整 ecModel 演示 case；P. putida 与 Synechocystis 当前按 evidence-integration / package-ready 展示。
