# 研究兴趣与方向

## 一句话定位

我的研究聚焦于**多组学证据驱动的微生物代谢模型构建、比较与解释**：将基因组尺度代谢模型（Genome-scale Metabolic Model, GEM）、转录组、蛋白组、代谢组、酶动力学和动态培养数据连接起来，形成可审计、可复现、能够解释环境响应与代谢重编程的计算工作流。

这一方向位于计算系统生物学、代谢工程、生物信息学与科学软件工程的交叉地带。我的目标不仅是运行单个 FBA 或组学分析算法，而是研究从公共资源发现、证据整理、模型约束、变体生成、反应级比较到结果报告的完整证据链。

## 核心研究问题

### 1. 异构组学证据如何可靠地转化为代谢模型约束

公共数据库和实验数据在尺度、格式、质量与可用性上差异很大。转录组提供表达变化，蛋白组更接近酶丰度，kcat 描述催化潜力，代谢组和通量数据则反映系统状态。我的一个核心兴趣是建立透明的 evidence-to-model 映射规则，回答：

- 哪些证据可以直接改变反应上下限或模型结构？
- 哪些证据只能用于反应注释、优先级排序或方法推荐？
- 如何通过 GPR 规则将 gene/protein evidence 映射到 reaction？
- 如何区分真实数值零、尚未生成、仅有摘要、外部计算待完成等状态？

当前重点方法包括 E-Flux、FASTcore、Consensus Context、GECKO-ready 预处理，以及面向后续 ecGEM 的 proteomics/kcat capacity bridge。研究中坚持不把 metadata-only、package-ready 或 reaction-level unavailable 证据解释为已经完成的模型约束。

### 2. 如何构建可解释、可追溯的条件特异性模型

模型生成不应只是输出一个新的 SBML 文件，还应回答“模型为什么变成这样”。因此，我关注 reaction-level model edit provenance，包括：

- 新增或删除了哪些反应；
- 哪些反应的上下限发生变化；
- 哪些反应映射了 transcriptomics、proteomics 或 kcat 证据；
- 哪些结果来自直接计算，哪些来自旧案例的推断性补录；
- 哪些能力只是 package-ready，尚未形成真实 enzyme capacity 或 behavior output。

相应地，模型比较的重点不是简单比较两个模型文件，而是将结构变化、约束变化、证据覆盖和缺失状态分开解释，并在左右对齐的反应网络中展示上游建模操作留下的痕迹。

### 3. 稳态代谢模型如何连接动态调控与环境响应

传统 COBRA/GEM 方法主要描述给定约束下的稳态可行空间，但微生物在营养耗尽、氧变化和生长阶段转换过程中表现出明显的时间依赖调控。我的研究兴趣正在从静态 context-specific GEM 延伸到动态与调控层，重点包括：

- 用生长曲线和时间序列表达数据区分生长阶段效应与环境触发效应；
- 将转录触发因子、代谢物变化与反应网络联系起来；
- 使用 guarded dFBA 探索碳源、氮源、氧气和储存代谢之间的动态关系；
- 区分 paper-reported prediction、轻量复现和完整 solver recomputation 的证据等级。

*Shewanella oneidensis* MR-1 是这一方向的主要案例。一条主线关注氧条件、proteomics/kcat 与 GECKO-ready 模型；另一条主线关注 LAC/LB 生长动态、转录触发、氮耗尽与糖原储存。两条主线共同用于研究“环境变化如何通过调控和酶约束改变代谢状态”。

### 4. 如何建设面向微生物建模的资源图谱与证据基础设施

高质量模型构建往往受限于资源发现和数据准备，而不只是算法本身。因此，我也关注微生物模型与组学资源的聚合、分类和可用性判断，包括：

- 从 BiGG、GEO、Expression Atlas、PRIDE、MetaboLights、OmicsDI 等来源聚合 public metadata；
- 建立 taxonomy-aware 的微生物 target registry 和生物分类资源谱系树；
- 对跨来源记录进行 canonical linking，同时保留 source-specific provenance；
- 区分 ready-for-import、ready-for-reference、package-ready、metadata-only 和 raw-only；
- 将不可直接使用的资源送入 curation workspace，而不是伪装成可运行输入。

这部分研究实质上是在回答：怎样把分散的公共生物学资源组织成能够支持模型构建决策的 evidence atlas，而不仅是一个搜索结果列表。

### 5. 如何让计算生物学工作流具有可复现性与科学边界

我的研究也重视科学软件中的证据治理。每个结果都应能够追溯到输入文件、映射规则、参数、算法状态和生成方式。尤其需要避免以下常见问题：

- 将“未生成”显示为数值 0；
- 将论文报告的结果表述为本地重新计算；
- 将 pathway-level annotation 强行解释为 reaction-level mapping；
- 将 metadata harvesting 误写成数据下载与处理；
- 将缺少参数的外部模型包装成完整复现。

因此，项目采用 manifest、readiness、QA matrix、edit index、case context 和 report provenance 等机制，尝试让计算结论既易于展示，也经得起追问。

## 代表性研究对象与案例

### *Shewanella oneidensis* MR-1

这是当前最完整的综合案例，连接两个互补问题：

- oxygen condition 下的模型、proteomics、kcat 与 GECKO-ready evidence；
- 生长阶段转换中的 transcriptional triggers、氮限制、糖原储存与 dFBA-lite。

该案例适合研究动态环境响应、酶约束、转录调控和模型解释之间的关系。

### *Pseudomonas putida*

重点关注工业底盘、耐受性、蛋白组/kcat evidence 与外部 ecModel preparation。它用于检验在没有完整 reaction-level capacity 输出时，系统如何诚实表达 package readiness 和证据缺口。

### *Synechocystis* 与其他光合微生物

重点关注 proteomics、phosphoproteomics、metabolomics 与碳限制等条件证据，以及光合代谢模型中跨组学证据的映射与解释。

### 多物种资源层

通过 Resource Atlas 将上述案例扩展到更广泛的细菌、古菌、酵母、丝状真菌、蓝细菌和微藻，用于研究跨物种资源覆盖、taxonomy placement 与方法可迁移性。

## 方法与技术路线

我的方法体系可以概括为以下链路：

```text
公共资源与用户数据
        ↓
质量审计、taxonomy、canonical linking 与 provenance
        ↓
模型/组学输入预览与 identifier mapping
        ↓
E-Flux / FASTcore / Consensus / GECKO-ready 等模型生成路线
        ↓
reaction-level edit provenance 与左右模型比较
        ↓
FBA/pFBA、动态分析、论文复现与证据解释
        ↓
带状态边界、缺失说明和来源追踪的报告
```

具体方法包括：

- COBRA、FBA/pFBA、condition-specific modeling；
- transcriptomics-informed constraints 与 context extraction；
- GPR-based proteomics/kcat mapping 和 enzyme-capacity preflight；
- dFBA-lite 与时间序列多组学分析；
- reaction network、taxonomy tree 与 evidence overlay 可视化；
- metadata harvesting、schema normalization、deduplication 和 data quality audit；
- case-based reproducibility、artifact manifests 和科学状态语义。

## 正在形成的交叉方向

以下方向与当前项目高度相关，但仍属于进一步深化的研究兴趣：

### Trans-omic regulation network 与 GEM 的结合

Trans-omic network 擅长解释 signaling、transcription factor、gene、enzyme、reaction 和 metabolite 之间的调控路径；COBRA/GEM 擅长描述化学计量约束下的代谢可行空间。二者结合后，可以同时回答“哪些通量可行”和“哪些调控事件可能驱动了这些变化”。

### 网络控制与关键触发节点

Feedback Vertex Set、Linkage Logic 和网络结构控制理论可用于从复杂调控网络中识别关键节点。这与 transcriptional trigger、关键酶、干预靶点和模型子图选择具有潜在联系。

### AI-native DBTL 与科学代理

长期来看，Omics-GEM Studio 可以从单一软件工具演化为可审计的 Design-Build-Test-Learn 工作台：由资源代理、数据映射代理、假设生成代理和审查代理协作，但科学事实、计算状态和核心数据始终保持可追溯，AI 不替代证据判断。

## 长期研究目标

我的长期目标是构建一个面向微生物系统生物学与代谢工程的**多组学证据导航和模型推理平台**。它应同时具备四种能力：

1. **发现**：从跨来源资源中找到与物种、条件和建模方法相关的证据。
2. **构建**：将异构组学数据转化为透明、可审核的模型约束或准备包。
3. **解释**：在 reaction、pathway 和调控层面说明模型为何变化、证据覆盖到哪里。
4. **复现**：明确区分直接计算、轻量复现、论文报告结果和不可复现项。

最终希望把 GEM 从一个相对孤立的稳态优化对象，发展为连接公共资源、动态组学、酶约束、调控网络和实验设计的可解释计算载体。

## 对外简版表述

我的研究关注多组学数据与基因组尺度代谢模型的整合，重点研究如何将转录组、蛋白组、代谢组和酶动力学证据转化为可解释、可追溯的条件特异性模型。我同时开发面向微生物的资源图谱、模型修改留痕与反应网络比较方法，并探索 dFBA、trans-omic regulation network 和 AI-assisted DBTL 在动态代谢响应与代谢工程中的应用。

## 当前能力边界

本文档描述的是研究方向，而不是宣称所有方法均已完整实现。当前仍需继续推进的能力包括：full D2T2 recomputation、与原文一致的 solver-ready dFBA、完整外部 GECKO/RAVEN/MATLAB 自动化、更多物种的 curated reaction-level evidence，以及 trans-omic regulation network 与 GEM 的正式耦合。
