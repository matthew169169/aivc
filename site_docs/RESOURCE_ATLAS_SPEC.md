# Resource Atlas Spec

## Target Registry Review v1.3 Contract

- `scope_*` rows and other abstract discovery scopes are not promotable organism targets. They belong in `microbial_harvest_scopes.csv`, not `organism_targets.csv`.
- Promotion dry-runs must mark abstract scopes as `rejected: abstract_scope_not_promotable`; they must not appear in `rows_to_add`.
- Taxonomy candidate merging prioritizes `organism_id` and current-registry identity before taxon/name fallback, so existing reviewed targets do not re-enter the review queue when cached metadata is incomplete.
- `resources/taxonomy/taxonomy_review_worklist.csv` and `.json` contain concrete organism/strain rows only. They exclude `scope_*`, metagenome/mixed samples, host-associated samples, and other special categories.
- Formal promotion remains manual and review-first: only `review_status=ready` concrete organisms with complete fields may be appended, and only through explicit `--apply`.

## Target Registry Review v1.4 Contract

- `review_taxonomy_targets.py` is offline-only by default. It must not query NCBI, infer missing taxon IDs, or mutate `organism_targets.csv`.
- `taxonomy_review_decisions.*` is the review surface for filling `taxon_id` and clade gaps. Reviewers should update review artifacts or source candidate metadata before any future promotion, not edit production registry rows directly.
- `organism_targets.reviewed_candidates.csv` may contain only complete concrete organism/strain rows approved for promotion dry-run.
- `organism_targets_review_promotion_dry_run.*` is advisory. A `rows_to_add=0` result is valid when all worklist rows still need taxon IDs.
- `organism_targets.backup_preview.csv` is a preview copy only; it is not a restore point and must not replace the production registry automatically.

## Target Registry Review v1.5 Contract

- `enrich_taxonomy_targets.py` is cache-first by default. It may query NCBI only with explicit `--online-ncbi`.
- Enrichment is taxonomy metadata only. It must not download omics data, mutate `organism_targets.csv`, or overwrite `organism_targets.expanded.csv`.
- Accepted rows require species/strain-level NCBI matches by exact scientific name, strain-aware match, or trusted synonym. Genus-only, ambiguous, no-hit, and network-failed rows remain warnings.
- `taxonomy_enrichment_candidates.*` and `organism_targets_enrichment_promotion_dry_run.*` are staging artifacts for review; formal promotion remains a later explicit apply step.

## 目标

Resource Atlas 是 Omics-GEM Studio 的模型与组学资源入口。它面向微生物资源聚合搜索，负责发现模型、omics metadata、annotation 与 case 线索，并判断哪些资源可以进入 workflow，哪些只是 metadata/curation 线索。

它不是 raw data 下载器，也不会把公共库 metadata-only 或 raw-only 记录伪装成可直接导入数据。

## 主界面

- **Resource Lineage Atlas**：默认第一视图。用生物分类资源谱系树展示重点物种、模型和组学资源分布。
- **Search Results Mode**：面向大规模聚合 metadata 的精确检索与分页浏览。
- **Decision Inspector**：显示选中 taxonomy branch、species 或 resource category 的资源摘要、readiness、method support 和条目列表。
- **Resource entries**：固定高度滚动列表，展示具体 source、accession、omics type、readiness、external URL 与 curation guidance。
- **Landscape / Deep Dive**：辅助视图，默认折叠，不抢占谱系树主入口。

## 资源语义

- `total indexed` 表示 Atlas 当前索引到的 metadata/resource 条目总数，不等于可导入资源数。
- `ready_for_import` 只允许本地可导入文件或明确 processed matrix。
- `ready_for_reference` 用于本地 reference model 或可信模型 metadata。
- `package_ready` 表示可进入外部工具或人工整理准备流程，但不是已完成 ecModel/processed matrix。
- `metadata_only`、`raw_data_only`、`license_or_access_limited` 只能作为发现和 curation 线索。
- 公共库 capped query 是覆盖未完成提示，不是系统失败；必须记录 backlog 和 continuation plan。

## 质量与 canonical linking

Resource Atlas 本地 cache 必须生成并维护以下质量报告：

- `resource_schema_quality_report.*`：字段完整性和 A/B/C/blocked 分级。
- `resource_field_completeness.csv`：字段级 completeness。
- `resource_readiness_audit.*`：检查 metadata-only/raw-only 是否被误标为 ready。
- `resource_canonical_link_report.*`：study/accession 层面的 canonical sidecar。

Canonical linking 只做 study/resource 层面的别名和重复组记录，不删除 source-specific rows，不做 sample-level merge。

## Taxonomy 与 target registry

正式 harvest target 仍以 `resources/organism_targets.csv` 为生产 registry。扩容流程使用 review-first artifacts：

- `organism_targets.expanded.csv`
- `organism_targets_expansion_report.*`
- `organism_targets_promotion_report.*`
- `organism_target_taxonomy_warnings.csv`

Taxonomy resolver 采用本地优先策略，输出：

- `resources/taxonomy/taxonomy_cache.json`
- `resources/taxonomy/taxonomy_resolution_queue.csv`
- `resources/taxonomy/taxonomy_resolution_warnings.csv`
- `resources/taxonomy/microbial_special_categories.csv`

缺 taxon、分类不确定或无法确认 microbial scope 的条目必须进入 `needs_taxonomy_review`，不能静默进入正式 harvest 队列。Metagenome、mixed sample、host-associated 或非微生物样本进入 special category。

## 禁止行为

- 不默认下载 FASTQ、SRA、mzML、raw CEL 或 supplementary raw matrix。
- 不把 metadata-only/raw-only 标成 `ready_for_import`。
- 不用一个 target batch 覆盖另一个 batch；harvesting 必须合并旧 cache 并记录 source manifest。
- 不把 taxonomy 不确定的 organism 自动 promotion 到 `organism_targets.csv`。
- 不使用版权不明图片作为物种节点照片。

## QA 要点

- Resource Atlas 默认首屏是生物分类资源谱系树。
- 搜索结果和右侧详情固定高度滚动，不拉长整页。
- 质量报告覆盖所有 cached resources。
- `ready_violation_count` 必须为 0。
- expanded registry 保持 review-first；正式 registry 只在明确 `--apply` 后修改。
- taxonomy queue/cache 必须能区分 ready、needs review 和 special category。
