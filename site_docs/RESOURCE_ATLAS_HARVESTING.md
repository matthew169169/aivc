# Resource Atlas Metadata Harvesting

This document records the local metadata harvesting workflow for the
Model & Omics Resource Atlas. The pipeline is metadata-only: it refreshes
searchable public-resource metadata and never downloads raw omics data,
processed matrices, model files, FASTQ, SRA, mzML, or supplementary archives.

## Commands

Refresh all cached metadata from deterministic offline seed rows:

```powershell
python tools\update_resource_cache.py --source all --offline
```

Refresh one source in live metadata mode:

```powershell
python tools\update_resource_cache.py --source geo --organism "Escherichia coli" --limit 200
```

Run a broader microbial-scope refresh in live metadata mode:

```powershell
python tools\update_resource_cache.py --source all --include-microbial-scopes --max-queries 30
```

The microbial scope registry in `resources/microbial_harvest_scopes.csv`
defines taxonomy-level discovery queries such as bacteria, archaea,
cyanobacteria, yeasts, filamentous fungi, microbial pathogens, industrial
microbes, environmental microbes, and microalgae. Scope queries are only added
when `--include-microbial-scopes` is supplied and no organism or taxon filter is
active. They widen discovery beyond the curated organism target registry while
remaining metadata-only.

Live refresh is shrink-safe by default. If a live metadata harvest returns
fewer records than the current source cache, the updater preserves the broader
existing cache, merges any newly discovered records, and records a merge note
in the source manifest. This prevents a narrow query, a capped API response,
or a temporary empty result from accidentally replacing the Atlas cache with a
smaller index while still allowing small live probes to expand the cache.

Only use the explicit override when you intentionally want the smaller live
result to replace the existing cache:

```powershell
python tools\update_resource_cache.py --source geo --organism "Escherichia coli" --limit 200 --allow-shrink
```

When `--limit`, `--page-size`, or `--max-pages` are omitted or set to `0`,
the updater uses the defaults from `resources/source_registry.json`.
Use `--max-queries` to cap how many live queries a source can run during a
single refresh. This is useful for broad microbial scope harvesting because
some public APIs can be slow or return sparse hits for many scope/theme pairs.
Offline, cached-first, and live connector query themes are defined in
`resources/resource_query_themes.json`. Add or remove source-specific themes
there when expanding microbial coverage; avoid hard-coding search strategy in
the updater.

Large public-resource searches can still be capped even when a connector is
healthy. Optional query partitions split one broad organism/theme search into
auditable microbial context slices such as carbon metabolism, stress,
oxygen/respiration, nitrogen/phosphate limitation, antibiotic response, and
fermentation. Partition definitions live in
`resources/resource_query_partitions.json`.

Run a partitioned live metadata refresh for one source:

```powershell
python tools\update_resource_cache.py --source geo --include-microbial-scopes --query-partitions microbial_context --max-partitions-per-query 3 --max-queries 30
```

`--query-partitions none` keeps the original organism/theme query shape.
`--max-partitions-per-query` bounds how many context slices are applied to each
organism/theme query. Source manifests record `query_partition_modes`,
`query_partition_suffixes`, `effective_query_partitions`, and
`effective_max_partitions_per_query` so coverage can be audited later.

Use target windows when a scheduled harvest should rotate across the microbial
target registry instead of repeatedly starting with the first curated
organisms. The window is applied after organism/taxon filtering and after
optional microbial scope targets are appended:

```powershell
python tools\update_resource_cache.py --source geo --include-microbial-scopes --query-partitions microbial_context --max-partitions-per-query 2 --target-offset 20 --target-limit 20 --max-queries 80
```

Windowed live harvests are merge-safe by default: the new target batch is
merged into the existing source cache, so one batch does not overwrite records
from earlier batches. Source manifests and query manifests record
`effective_target_offset`, `effective_target_limit`, `target_offset`, and
`target_limit` so the coverage window is auditable.

Run a metadata connector smoke probe without overwriting source caches:

```powershell
python tools\smoke_resource_live_connectors.py --source all --organism Shewanella --limit 5 --page-size 5 --max-pages 1
```

Run a staged harvest plan:

```powershell
python tools\run_resource_harvest_plan.py --stage microbial_smoke
```

Run the bounded connector-deepening stage over reviewed production targets:

```powershell
python tools\run_resource_harvest_plan.py --stage microbial_connector_deepening_v1 --continue-on-error
```

This stage does not use `--include-microbial-scopes`; it rotates only across
the reviewed production `organism_targets.csv` windows. The expanded registry
and taxonomy review queue remain advisory until reviewed and promoted.
Abstract `scope_*` rows are discovery scopes only; post-harvest promotion
dry-runs must reject them with `abstract_scope_not_promotable` and keep them
out of `organism_targets.csv`.

Audit the current cache, source registry, staged plan, dedup QA, API evidence,
and Resource Atlas UI evidence against the microbial target-mode requirements:

```powershell
python tools\audit_resource_atlas_target_mode.py
```

Use `--fail-on-blocking` in CI-like checks when missing or failed target-mode
requirements should return a non-zero exit code:

```powershell
python tools\audit_resource_atlas_target_mode.py --fail-on-blocking
```

Preview the same plan without changing source caches:

```powershell
python tools\run_resource_harvest_plan.py --stage microbial_incremental --dry-run --max-jobs 2
python tools\run_resource_harvest_plan.py --stage microbial_connector_deepening_v1 --dry-run --max-jobs 2
```

Run one source from a staged plan when you want a bounded incremental refresh:

```powershell
python tools\run_resource_harvest_plan.py --stage microbial_incremental --source geo
python tools\run_resource_harvest_plan.py --stage microbial_incremental --source pride
```

Run the next source-level continuation commands generated from capped query
backlog rows:

```powershell
python tools\run_resource_continuation_plan.py --continue-on-error
```

Preview those continuation commands without changing source caches:

```powershell
python tools\run_resource_continuation_plan.py --dry-run
```

Refresh post-harvest QA artifacts without running any live connector:

```powershell
python tools\run_resource_post_harvest_qa.py
```

Build the offline taxonomy review decisions without writing artifacts:

```powershell
python tools\review_taxonomy_targets.py --dry-run
```

Preview bounded taxonomy enrichment without network or writes:

```powershell
python tools\enrich_taxonomy_targets.py --dry-run
```

Explicitly enrich the first 50 missing-taxonomy review rows from NCBI taxonomy
metadata:

```powershell
python tools\enrich_taxonomy_targets.py --online-ncbi --limit 50
```

`run_resource_harvest_plan.py` and `run_resource_continuation_plan.py` run this
QA chain automatically after successful non-dry-run jobs unless
`--skip-post-harvest-qa` is supplied. The chain rebuilds schema quality,
canonical links, readiness audit, expanded target dry-run, promotion dry-run,
taxonomy cache artifacts, the concrete-organism taxonomy review worklist, and
offline review decisions. It never applies target promotion.

Use `taxonomy_review_decisions.*` as the manual review surface for filling
missing taxon IDs or confirming clades. Do not directly edit
`organism_targets.csv` to resolve review rows; formal promotion remains a
separate explicit apply step.

The staged plan lives in `resources/resource_harvest_plan.json`:

- `microbial_smoke`: small broad-scope connector check.
- `microbial_incremental`: bounded expansion for routine manual refresh.
- `microbial_deep`: larger scheduled expansion after smoke and incremental
  stages are stable. This stage enables `microbial_context` query partitions
  for metadata-heavy omics sources so capped broad queries can be split into
  smaller, auditable context slices.
- `microbial_target_rotation`: metadata-only target-window refreshes that move
  across the organism target registry. Use this for scheduled breadth
  expansion; use the capped-query continuation plan for source-level depth
  expansion when public APIs report capped results.
- `microbial_connector_deepening_v1`: bounded metadata-only deepening for
  reviewed production targets. Use this after smoke checks when you want
  repeatable source expansion without touching taxonomy-review candidates.

Each plan run writes `resource_harvest_plan_report.json` and `.csv` under
`resources/cached_search/`.

Install a daily cache refresh task:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\install_resource_cache_daily_task.ps1 -Time 03:00
```

Install a daily staged harvest plan refresh:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\install_resource_cache_daily_task.ps1 -Time 03:00 -PlanStage microbial_incremental -ContinueOnError
```

Install a daily staged refresh for one source:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\install_resource_cache_daily_task.ps1 -Time 03:00 -PlanStage microbial_incremental -Source geo -ContinueOnError
```

The scheduled task uses the same shrink-safe default. Pass `-AllowShrink` only
when a scheduled job is intentionally allowed to replace a source cache with a
smaller live result.

Install a daily cache refresh task that also runs the metadata connector smoke
probe after the cache refresh:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\install_resource_cache_daily_task.ps1 -Time 03:00 -RunLiveSmoke -SmokeSource all -SmokeLimit 5 -SmokeMaxPages 1
```

Install a daily task that includes broad microbial scope queries:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\install_resource_cache_daily_task.ps1 -Time 03:00 -IncludeMicrobialScopes -MaxQueries 30
```

Preview the scheduled task command without registering it:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\install_resource_cache_daily_task.ps1 -DryRun -RunLiveSmoke -SmokeOrganism Shewanella
```

Remove the scheduled task:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\install_resource_cache_daily_task.ps1 -Remove
```

## Generated Artifacts

The cache root is `resources/cached_search/`.

Key files:

- `resources/source_registry.json`: connector capability registry, including
  source database names, supported resource kinds, omics types, query modes,
  default readiness, and metadata-only safety boundaries.
- `resources/resource_query_themes.json`: source-specific query themes used by
  offline seed rows and cached-first query manifests.
- `resources/resource_query_partitions.json`: optional query partition modes
  used to split broad live metadata searches into smaller, auditable microbial
  context slices.
- `resources/microbial_harvest_scopes.csv`: optional taxonomy-level scope
  queries for broad microbial metadata discovery beyond specific strain targets.
- `resources/taxonomy/taxonomy_review_worklist.csv` / `.json`: concrete
  organism/strain review queue derived from `needs_taxonomy_review` rows.
  It excludes `scope_*`, metagenome/mixed samples, host-associated samples,
  and other special categories.
- `resources/taxonomy/taxonomy_review_decisions.csv` / `.json`: offline
  decision table that classifies worklist rows as missing taxon, missing clade,
  already reviewed, rejected, deferred, or promotion dry-run candidates.
- `resources/organism_targets_review_promotion_dry_run.json` / `.csv`:
  advisory promotion staging output. It never modifies the production target
  registry.
- `resources/taxonomy/taxonomy_enrichment_cache.json`: cache of explicit NCBI
  taxonomy metadata enrichment results.
- `resources/taxonomy/taxonomy_enrichment_candidates.csv` / `.json`: accepted
  species/strain-level taxonomy enrichments.
- `resources/taxonomy/taxonomy_enrichment_warnings.csv`: genus-only,
  ambiguous, no-hit, or failed enrichment rows requiring manual review.
- `resources/organism_targets_enrichment_promotion_dry_run.json` / `.csv`:
  advisory dry-run output for enriched targets. It never applies promotion.
- `cache_manifest.json`: source coverage, harvest status, cache QA, dedup QA,
  source registry summary, query theme summary, live smoke status, and last
  update metadata.
- `resource_harvest_qa_report.json` / `.csv`: per-source harvesting quality
  report.
- `resource_capped_query_backlog.json` / `.csv`: resumable backlog of
  bounded public-database queries. Each row records the source, query id,
  organism, omics type, query partition, harvested count, reported total when
  available, estimated remaining records, and a suggested higher page/record
  budget. This report turns `capped_queries` from a single warning number into
  an auditable continuation queue.
- `resource_capped_query_continuation_plan.json` / `.csv`: source-level
  continuation plan derived from the capped backlog. Each row groups capped
  queries by connector source and records a recommended metadata-only refresh
  command, using the `microbial_deep` harvest plan when available. This is the
  operational bridge from "coverage is capped" to "run this bounded follow-up
  command next."
- `resource_dedup_qa_report.json` / `.csv`: canonical-resource and duplicate
  group report.
- `resource_target_candidates.json` / `.csv`: advisory organisms or taxa
  discovered in harvested metadata but not yet promoted into
  `organism_targets.csv`. The updater never edits the target registry
  automatically; review this report when choosing future target windows.
- `resource_atlas_target_audit.json` / `.csv`: conservative target-mode audit
  report. It checks required sources, microbial scopes, staged plan coverage,
  normalized resource schema, readiness safety, cache manifest provenance,
  dedup QA, API evidence, UI evidence, and harvesting documentation evidence.
- `resource_live_smoke_report.json` / `.csv`: connector availability smoke
  report, including per-source query theme counts and covered omics types.

Source manifests distinguish the current merged cache from the most recent
live harvest. This matters because broad public-resource queries may return a
small capped page while an older local cache already contains more records.
Important fields:

- `record_count` / `current_cache_records`: records currently available in the
  local source cache.
- `live_reported_hits`: hits reported by the live metadata endpoint for the
  latest run, when the source reports a total.
- `live_harvested_records`: records returned by the latest live metadata run.
- `merged_existing_cache`: whether shrink-safe preservation kept the previous
  larger cache and merged the latest live result.
- `live_returned_records_before_merge` and
  `existing_cache_records_before_merge`: evidence for why a source cache did
  or did not grow.
- `capped_queries`: live queries that appear to have more matching metadata
  than the configured page/limit budget harvested.
- `capped_query_backlog_json` / `capped_query_backlog_summary`: global pointer
  to the continuation backlog. A non-empty backlog is expected whenever capped
  queries are present; it is the operational to-do list for future deep harvest
  or source-specific refresh runs.
- `capped_query_continuation_plan_json` /
  `capped_query_continuation_plan_summary`: global pointer to source-level
  continuation commands derived from the backlog. A non-empty plan is expected
  whenever capped queries are present.
- `query_partition_modes` and `query_partition_suffixes`: context partitions
  used by the latest live harvest for that source. These fields are empty for
  unpartitioned smoke and incremental jobs, and populated for partitioned deep
  harvest jobs.

For example, an incremental harvest can be operationally successful while the
target-mode audit remains `partial`: that means the cache is usable and safe,
but at least one public source reported capped query coverage that should be
expanded through deeper pagination or narrower query partitioning.

## Canonical linking

The cache updater and runtime API use the same canonical-linking rules:

- Model resources are grouped by organism and model id, so local ready models
  and BiGG metadata for the same model preserve one source-link set.
- Omics resources are grouped by normalized study accession when possible.
  Public accessions such as `GSE*`, `E-GEOD-*`, `PXD*`, `MTBLS*`, and
  BioProject identifiers are converted into stable canonical tokens.
- Synthetic cached query ids remain source-specific and are not merged unless
  they resolve to the same public accession.
- API resources expose `canonical_resource_id`, `cross_source_ids`, and
  `source_links`; source links include the original source database,
  connector, accession, URL, and canonical tokens used for QA.

## Acceptance Criteria

- Each target source has a cached metadata path and a manifest status.
- Each cached-first source reports configured query theme counts and covered
  omics types in the cache manifest.
- Dedup QA reports include canonical group counts, cross-source group counts,
  canonical tokens, cross-source ids, and preserved source links.
- Cache refresh is atomic: failed source refreshes do not delete the previous
  usable cache.
- Metadata-only and raw-only resources are never marked as `ready_for_import`.
- API responses expose `cache_status`, `coverage_by_source`, facets, paging
  counts, and guidance for partial or stale cache states.
- The Atlas UI can show the last update status and source-level smoke status
  without requiring live network access.
- The target-mode audit has no `failed` or `missing` checks. `partial` checks
  are acceptable only when they represent explicitly recorded coverage limits
  such as capped public-database queries or stale/partial cache guidance, not
  missing artifacts or unsafe readiness semantics.

## Safety Boundaries

- Do not use this pipeline to download raw data.
- Do not fabricate upload-ready matrices from metadata.
- Do not overwrite case-study ready resources with metadata-only rows.
- Do not treat a successful connector smoke probe as proof that a resource can
  be imported directly.
