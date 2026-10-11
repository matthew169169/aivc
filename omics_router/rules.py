"""Rule-based method selection for multi-omics integration into GEMs.

The router intentionally stays transparent: every recommendation has a
rationale, required inputs, cautions, and validation suggestions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


OMICS_LABELS: dict[str, str] = {
    "transcriptomics": "转录组 RNA-seq / microarray",
    "absolute_proteomics": "绝对定量蛋白组",
    "relative_proteomics": "相对定量蛋白组",
    "extracellular_metabolomics": "胞外代谢组 / exchange flux",
    "intracellular_metabolomics": "胞内定量代谢组",
    "fluxomics": "Fluxomics / 13C-MFA",
    "lipidomics_glycomics": "脂质组 / 糖组",
    "single_cell_spatial": "单细胞 / 空间组学",
    "ml_priors": "机器学习先验 kcat / dG / 缺失模态",
}

GOAL_LABELS: dict[str, str] = {
    "context": "构建组织/细胞/患者特异模型",
    "flux_change": "比较条件间通量重分配",
    "enzyme_bottleneck": "寻找酶容量、蛋白负担或资源瓶颈",
    "thermo": "检查方向性、热力学可行性和无效循环",
    "calibration": "用实验通量校准或验证模型",
    "community": "构建宿主-微生物或群落模型",
    "screening": "预测基因/反应/药物脆弱点",
    "exploratory": "探索性整合，不确定主要问题",
}

ORGANISM_LABELS: dict[str, str] = {
    "microbe": "微生物 / 工业菌株",
    "human": "人类组织 / 肿瘤 / 细胞系",
    "plant": "植物",
    "community": "微生物群落 / 宿主-微生物",
    "other": "其他或暂不确定",
}


@dataclass(slots=True)
class MethodRecommendation:
    """A single recommended modeling route."""

    key: str
    title: str
    priority: str
    constraint_logic: str
    rationale: str
    methods: list[str]
    tools: list[str]
    required_inputs: list[str]
    outputs: list[str]
    cautions: list[str]
    validation: list[str]
    run_after: list[str] = field(default_factory=list)
    implementation_note: str = ""


@dataclass(slots=True)
class RecommendationPlan:
    """Complete routing result shown in the app and exported as config."""

    summary: str
    recommendations: list[MethodRecommendation]
    warnings: list[str]
    missing_inputs: list[str]
    run_order: list[str]
    next_best_data: list[str]


def route_methods(selection: dict[str, Any]) -> RecommendationPlan:
    """Return a transparent modeling plan from user selections.

    Expected keys in ``selection``:
    ``has_gem``, ``omics`` list, ``goal``, ``organism``, ``has_kcat``,
    ``has_growth_rate``, ``has_exchange_flux``, ``objective_known``.
    Extra keys are ignored so the UI can evolve without breaking this API.
    """

    omics = set(selection.get("omics") or [])
    has_gem = bool(selection.get("has_gem"))
    has_kcat = bool(selection.get("has_kcat"))
    has_growth_rate = bool(selection.get("has_growth_rate"))
    has_exchange_flux = bool(selection.get("has_exchange_flux"))
    objective_known = bool(selection.get("objective_known", True))
    organism = selection.get("organism", "other")
    goal = selection.get("goal", "exploratory")

    recommendations: list[MethodRecommendation] = []
    warnings: list[str] = []
    missing_inputs: list[str] = []
    next_best_data: list[str] = []

    if not has_gem:
        missing_inputs.append("基础 GEM / GSMM 模型文件，优先 SBML FBC 格式")
        warnings.append("没有基础 GEM 时只能生成方法建议，不能进入约束建模工作流。")
    else:
        recommendations.append(_baseline_qc())

    if not omics:
        warnings.append("尚未选择组学数据；当前路线只包含基础模型 QC 与 FBA/FVA 基线分析。")
        next_best_data.extend(["培养基 / exchange bounds", "growth rate", "转录组或蛋白组"])

    if "single_cell_spatial" in omics:
        recommendations.append(_single_cell_route())
        warnings.append("单细胞/空间 feature 不建议直接写入 GEM；应先按细胞类型、状态或空间邻域汇总。")
        if "transcriptomics" not in omics:
            next_best_data.append("聚类后的 pseudo-bulk expression matrix")

    if "transcriptomics" in omics:
        if goal in {"flux_change"}:
            recommendations.append(_expression_bounds_route())
        else:
            recommendations.append(_context_route(objective_known=objective_known, organism=organism))

    if "absolute_proteomics" in omics:
        if has_kcat or "ml_priors" in omics:
            recommendations.append(_enzyme_route(uses_ml_kcat=not has_kcat and "ml_priors" in omics))
        else:
            recommendations.append(_protein_budget_route())
            missing_inputs.append("kcat 表或 kcat 数据库映射，用于升级到 ecGEM")
            next_best_data.append("kcat hierarchy: organism-specific -> homolog -> generic -> ML prior")

    if "relative_proteomics" in omics:
        recommendations.append(_relative_proteomics_route())
        if "absolute_proteomics" not in omics:
            warnings.append("相对蛋白组通常不适合直接生成绝对 flux upper bounds。")

    if "extracellular_metabolomics" in omics:
        recommendations.append(_exchange_route())

    if "intracellular_metabolomics" in omics:
        recommendations.append(_thermo_route())
        next_best_data.extend(["代谢物区室映射", "pH / ionic strength / concentration range"])

    if "fluxomics" in omics:
        recommendations.append(_calibration_route())
    elif has_growth_rate or has_exchange_flux:
        recommendations.append(_phenotype_validation_route(has_growth_rate, has_exchange_flux))

    if "lipidomics_glycomics" in omics:
        recommendations.append(_biomass_route())

    if organism == "community" or goal == "community":
        recommendations.append(_community_route())
        next_best_data.extend(["物种丰度", "diet constraints", "共享环境 exchange reactions"])

    if "ml_priors" in omics:
        recommendations.append(_ml_bridge_route())
        warnings.append("ML 输出应作为带置信度的先验进入约束，不建议硬编码成唯一真值。")

    recommendations = _deduplicate(recommendations)
    run_order = _build_run_order(recommendations)
    summary = _make_summary(has_gem, omics, goal, organism, recommendations)

    if not (has_growth_rate or has_exchange_flux or "fluxomics" in omics):
        next_best_data.append("至少一种表型验证数据：growth、exchange flux、essentiality 或 secretion profile")

    return RecommendationPlan(
        summary=summary,
        recommendations=recommendations,
        warnings=_unique(warnings),
        missing_inputs=_unique(missing_inputs),
        run_order=run_order,
        next_best_data=_unique(next_best_data),
    )


def _baseline_qc() -> MethodRecommendation:
    return MethodRecommendation(
        key="baseline_qc",
        title="基础 GEM 质量检查与基线分析",
        priority="必须",
        constraint_logic="模型底座",
        rationale="所有组学约束都依赖基础模型质量；先确认质量守恒、边界、GPR 和 blocked reactions。",
        methods=["MEMOTE", "FBA", "pFBA", "FVA"],
        tools=["MEMOTE", "COBRApy"],
        required_inputs=["SBML / JSON / MAT GEM", "目标函数", "培养基或 exchange bounds"],
        outputs=["QC 报告", "baseline growth / objective", "blocked reactions", "FVA baseline"],
        cautions=["基础模型质量差时，后续组学整合会放大假阳性。"],
        validation=["growth rate", "substrate utilization", "known secretion / uptake"],
        implementation_note="MVP 先生成 QC 任务配置；实际执行可接 memote 与 cobra.flux_analysis。",
    )


def _context_route(objective_known: bool, organism: str) -> MethodRecommendation:
    methods = ["iMAT", "FASTCORE", "CORDA"]
    if organism in {"human", "plant"}:
        methods.insert(0, "tINIT / INIT")
    if objective_known:
        methods.append("GIMME")
    return MethodRecommendation(
        key="context_specific",
        title="转录组驱动的 context-specific 模型",
        priority="高",
        constraint_logic="switch / context filter",
        rationale="转录组最适合作为反应可用性的上下文过滤器，用于决定哪些反应应保留、惩罚或删除。",
        methods=methods,
        tools=["TROPPO", "COBRA Toolbox", "RAVEN/Human-GEM ecosystem"],
        required_inputs=["表达矩阵", "gene ID mapping", "GPR 规则", "表达阈值或 reaction confidence"],
        outputs=["context-specific GEM", "保留/删除反应表", "阈值敏感性结果"],
        cautions=[
            "mRNA 不等于酶活，结果不宜直接解释为通量。",
            "阈值、标准化和 GPR 聚合规则会明显影响网络结构。",
        ],
        validation=["metabolic task consistency", "gene essentiality", "known tissue functions", "secretion profile"],
        run_after=["baseline_qc"],
        implementation_note="MVP 生成 TROPPO/iMAT/FASTCORE/CORDA 路由与参数模板。",
    )


def _expression_bounds_route() -> MethodRecommendation:
    return MethodRecommendation(
        key="expression_bounds",
        title="表达量到通量边界的连续映射",
        priority="中",
        constraint_logic="expression-informed flux bounds / penalty",
        rationale="当问题是条件间通量重分配时，可保留连续表达信息并缩放 reaction bounds。",
        methods=["E-Flux", "DeltaFBA", "PROM", "GX-FBA", "RELATCH", "TRFBA / EXTREAM"],
        tools=["COBRApy custom workflow", "COBRA Toolbox"],
        required_inputs=["条件化表达矩阵", "表达标准化规则", "GPR 聚合规则", "边界缩放函数"],
        outputs=["condition-specific flux solution", "reaction bound table"],
        cautions=[
            "表达量与通量上限的比例关系需要校准。",
            "更适合相对比较，不适合作为绝对通量真值。",
        ],
        validation=["condition-wise growth", "exchange flux", "perturbation response"],
        run_after=["baseline_qc"],
    )


def _enzyme_route(uses_ml_kcat: bool) -> MethodRecommendation:
    kcat_note = "ML kcat prior + confidence tier" if uses_ml_kcat else "kcat hierarchy"
    return MethodRecommendation(
        key="enzyme_constrained",
        title="酶容量约束模型 ecGEM",
        priority="高",
        constraint_logic="valve / enzyme budget",
        rationale="绝对蛋白组和 kcat 可以把 reaction upper bound 转成酶容量约束，适合分析瓶颈、溢流和资源竞争。",
        methods=["GECKO", "sMOMENT", "AutoPACMEN", "ECMpy"],
        tools=["GECKO", "AutoPACMEN", "ECMpy", "COBRApy"],
        required_inputs=["absolute proteomics", kcat_note, "enzyme molecular weight", "GPR / EC / UniProt mapping"],
        outputs=["enzyme-constrained GEM", "limiting enzymes", "protein pool usage", "FVA shrinkage report"],
        cautions=[
            "kcat 条件依赖强，缺失值和同工酶匹配会改变结论。",
            "需要记录 kcat 来源层级与置信度。",
        ],
        validation=["growth rate", "overflow phenotype", "product yield", "proteome fraction", "exchange flux"],
        run_after=["baseline_qc", "context_specific"],
        implementation_note="GECKO 偏 MATLAB 生态；MVP 使用 runner 配置保留外部调用入口。",
    )


def _protein_budget_route() -> MethodRecommendation:
    return MethodRecommendation(
        key="protein_budget",
        title="蛋白预算或反应权重模型",
        priority="中",
        constraint_logic="protein budget",
        rationale="已有绝对蛋白组但缺少 kcat 时，可先做总蛋白池、反应权重或瓶颈候选排序。",
        methods=["pcGEM-lite", "weighted pFBA", "protein-pool constraint"],
        tools=["COBRApy custom workflow"],
        required_inputs=["absolute proteomics", "protein-to-gene mapping", "total protein pool estimate"],
        outputs=["protein budget table", "candidate bottleneck reactions"],
        cautions=["没有 kcat 时不能可靠地把蛋白丰度转成每个反应的绝对通量上限。"],
        validation=["proteome fraction", "growth", "exchange flux"],
        run_after=["baseline_qc"],
    )


def _relative_proteomics_route() -> MethodRecommendation:
    return MethodRecommendation(
        key="relative_proteomics",
        title="相对蛋白组驱动的条件比较",
        priority="中",
        constraint_logic="relative enzyme evidence / penalty",
        rationale="相对蛋白组可支持条件间缩放、反应权重和蛋白预算变化，但通常不直接给绝对边界。",
        methods=["weighted context extraction", "relative bound scaling", "condition-wise protein pool scaling"],
        tools=["TROPPO", "COBRApy custom workflow"],
        required_inputs=["relative proteomics matrix", "reference condition", "protein ID mapping"],
        outputs=["condition-comparison report", "changed reaction capacities"],
        cautions=["相对定量需要参考条件；跨平台数据不宜直接合并。"],
        validation=["condition-wise growth", "exchange flux", "known phenotype shift"],
        run_after=["baseline_qc"],
    )


def _exchange_route() -> MethodRecommendation:
    return MethodRecommendation(
        key="exchange_bounds",
        title="胞外代谢组转 exchange bounds",
        priority="高",
        constraint_logic="medium / uptake-secretion boundary",
        rationale="胞外代谢物和交换通量可直接修正培养基、摄取和分泌边界，是最稳妥的一类约束。",
        methods=["exchange-bound mapping", "medium reconstruction", "FBA/FVA with measured exchanges"],
        tools=["COBRApy"],
        required_inputs=["metabolite ID mapping", "exchange reaction mapping", "uptake/secretion rate or concentration change"],
        outputs=["condition-specific medium", "exchange bound table", "secretion/uptake consistency report"],
        cautions=["浓度差需要换算为速率时必须有时间、细胞量或生物量归一化信息。"],
        validation=["extracellular metabolomics holdout", "growth", "known uptake/secretion"],
        run_after=["baseline_qc"],
    )


def _thermo_route() -> MethodRecommendation:
    return MethodRecommendation(
        key="thermodynamic",
        title="代谢组驱动的热力学约束",
        priority="中",
        constraint_logic="thermodynamic anchors",
        rationale="胞内定量代谢组可通过浓度范围和 Gibbs 自由能限制反应方向，减少热力学不可行循环。",
        methods=["TMFA / TFA", "pyTFA", "matTFA", "multiTFA"],
        tools=["pyTFA", "matTFA"],
        required_inputs=["intracellular concentration range", "metabolite compartment mapping", "dG estimates", "pH / ionic strength"],
        outputs=["thermodynamics-constrained GEM", "reaction direction changes", "TIC removal report"],
        cautions=[
            "代谢物区室不清时容易误约束。",
            "pH、离子强度和 dG convention 需要显式记录。",
        ],
        validation=["directionality consistency", "absence of thermodynamic loops", "exchange flux signs"],
        run_after=["baseline_qc", "exchange_bounds"],
    )


def _calibration_route() -> MethodRecommendation:
    return MethodRecommendation(
        key="flux_calibration",
        title="Fluxomics / 13C-MFA 校准与验证",
        priority="高",
        constraint_logic="calibration anchors",
        rationale="13C-MFA 最接近实验通量真值，适合作为校准和外部验证，而不是第一层网络剪枝。",
        methods=["13C-MFA", "INCA", "mfapy", "FreeFlux", "flux fitting / holdout validation"],
        tools=["INCA", "mfapy", "FreeFlux", "COBRApy custom calibration"],
        required_inputs=["measured fluxes", "confidence intervals", "reaction mapping"],
        outputs=["flux fit report", "parameter calibration", "prediction-vs-measurement plot data"],
        cautions=["中心碳代谢覆盖较好，但全网络通量真值通常不可得。"],
        validation=["flux correlation", "interval coverage", "leave-one-condition-out"],
        run_after=["baseline_qc", "enzyme_constrained", "thermodynamic"],
    )


def _phenotype_validation_route(has_growth_rate: bool, has_exchange_flux: bool) -> MethodRecommendation:
    validation = []
    required_inputs = []
    if has_growth_rate:
        validation.append("growth rate")
        required_inputs.append("measured growth rate")
    if has_exchange_flux:
        validation.append("exchange flux")
        required_inputs.append("measured exchange flux")
    return MethodRecommendation(
        key="phenotype_validation",
        title="表型数据验证",
        priority="必须",
        constraint_logic="phenotype validation",
        rationale="growth 和 exchange flux 是成本较低但信息量高的验证层，适合作为每个建模阶段的 sanity check。",
        methods=["growth fit", "exchange flux consistency", "FVA coverage"],
        tools=["COBRApy"],
        required_inputs=required_inputs,
        outputs=["validation score table", "failed phenotype list"],
        cautions=["验证数据不要和建模约束完全重叠，否则会高估泛化能力。"],
        validation=validation,
        run_after=["baseline_qc"],
    )


def _biomass_route() -> MethodRecommendation:
    return MethodRecommendation(
        key="biomass_composition",
        title="脂质组/糖组修正 biomass composition",
        priority="中",
        constraint_logic="biomass composition / maintenance",
        rationale="脂质组和糖组更适合修正 biomass、膜成分或特定产物需求，而不是直接决定内部通量。",
        methods=["BOFdat-style biomass update", "condition-specific biomass reconstruction"],
        tools=["COBRApy custom workflow", "BOFdat-inspired templates"],
        required_inputs=["lipid/glycan abundance", "biomass component mapping", "condition metadata"],
        outputs=["condition-specific biomass reaction", "yield comparison"],
        cautions=["不同平台定量不可直接比较；biomass 修改会强烈影响 growth/yield。"],
        validation=["growth yield", "lipid accumulation", "maintenance fit"],
        run_after=["baseline_qc"],
    )


def _single_cell_route() -> MethodRecommendation:
    return MethodRecommendation(
        key="single_cell_preprocess",
        title="单细胞/空间组学预处理后再入 GEM",
        priority="高",
        constraint_logic="cell-state context filter",
        rationale="单细胞和空间数据应先聚合到细胞类型、状态或邻域，再映射到 GPR 与反应权重。",
        methods=["pseudo-bulk aggregation", "cluster-specific iMAT / FASTCORE / tINIT", "spatial neighborhood exchange constraints"],
        tools=["Scanpy/Seurat upstream", "TROPPO", "RAVEN/Human-GEM ecosystem"],
        required_inputs=["cell clusters or spatial neighborhoods", "pseudo-bulk expression", "marker/task list"],
        outputs=["cluster-specific GEMs", "spatial metabolic interaction hypotheses"],
        cautions=["dropout 和缺失模态会放大阈值敏感性；单细胞通量真值通常缺失。"],
        validation=["cell-type marker tasks", "spatial metabolite imaging", "CRISPR/drug response"],
        run_after=["baseline_qc"],
    )


def _community_route() -> MethodRecommendation:
    return MethodRecommendation(
        key="community_modeling",
        title="群落或宿主-微生物模型",
        priority="中",
        constraint_logic="species composition / shared environment",
        rationale="群落场景中，context-specific 首先体现为物种组成、共享环境和 diet/exchange 约束。",
        methods=["patient-specific community GEM", "diet-constrained community FBA", "cross-feeding analysis"],
        tools=["MICOM", "COBRApy", "AGORA2 / VMH resources"],
        required_inputs=["species abundance", "species GEM collection", "shared medium", "diet or fecal metabolomics"],
        outputs=["community model", "cross-feeding table", "intervention hypotheses"],
        cautions=["丰度不等于活性；社区目标函数不唯一。"],
        validation=["fecal metabolomics", "known nutrient usage", "drug metabolism capability"],
        run_after=["baseline_qc", "exchange_bounds"],
    )


def _ml_bridge_route() -> MethodRecommendation:
    return MethodRecommendation(
        key="ml_bridge",
        title="ML 先验回写到机理约束",
        priority="辅助",
        constraint_logic="ML bridge",
        rationale="ML 最适合作为 kcat、dG、缺失模态或缺失反应的先验，再带置信度写回约束模型。",
        methods=["DLKcat / RealKcat prior", "dG prediction prior", "missing modality imputation", "uncertainty-aware bound setting"],
        tools=["external ML predictors", "COBRApy custom prior ingestion"],
        required_inputs=["prediction table", "confidence score", "mapping to reaction/gene/metabolite"],
        outputs=["prior table", "uncertainty tiers", "sensitivity analysis template"],
        cautions=["OOD 条件下 ML 先验可能系统性偏移，必须做灵敏度和外部验证。"],
        validation=["OOD split", "holdout condition", "growth/exchange/flux consistency"],
        run_after=["baseline_qc"],
    )


def _build_run_order(recommendations: list[MethodRecommendation]) -> list[str]:
    preferred = [
        "baseline_qc",
        "single_cell_preprocess",
        "exchange_bounds",
        "context_specific",
        "expression_bounds",
        "biomass_composition",
        "protein_budget",
        "relative_proteomics",
        "enzyme_constrained",
        "thermodynamic",
        "community_modeling",
        "ml_bridge",
        "phenotype_validation",
        "flux_calibration",
    ]
    keys = {rec.key for rec in recommendations}
    return [key for key in preferred if key in keys]


def _make_summary(
    has_gem: bool,
    omics: set[str],
    goal: str,
    organism: str,
    recommendations: list[MethodRecommendation],
) -> str:
    if not has_gem:
        return "当前只能生成方法路线；请先提供基础 GEM 才能进入可执行建模。"
    if not omics:
        return "当前建议先完成基础 GEM QC、FBA/FVA 基线和验证数据准备。"

    goal_label = GOAL_LABELS.get(goal, goal)
    organism_label = ORGANISM_LABELS.get(organism, organism)
    high_priority = [rec.title for rec in recommendations if rec.priority in {"必须", "高"}]
    return (
        f"面向“{organism_label}”的“{goal_label}”，推荐从 "
        f"{' -> '.join(high_priority[:4])} 开始；后续按数据质量逐层加入更强约束。"
    )


def _deduplicate(recommendations: list[MethodRecommendation]) -> list[MethodRecommendation]:
    seen: set[str] = set()
    result: list[MethodRecommendation] = []
    for rec in recommendations:
        if rec.key in seen:
            continue
        seen.add(rec.key)
        result.append(rec)
    return result


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item and item not in seen:
            seen.add(item)
            result.append(item)
    return result
