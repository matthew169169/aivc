# Resource Atlas Metadata Harvesting Target Mode

## Summary

The `Model & Omics Resource Atlas` is a microbial metadata aggregation and
workflow-entry system. It should help users find, compare, and stage public
model and omics evidence for microbial organisms without pretending that
metadata is already upload-ready data.

The Atlas harvests metadata from public sources, caches it locally, normalizes
it into one resource index, deduplicates cross-source records, visualizes the
resource distribution, and hands selected resources into the existing
`Input -> Model Generator -> Analysis -> Summary` workflow.

The default mode is metadata-only. The Atlas must not download raw data, parse
large archives, fabricate processed matrices, or mark metadata-only records as
ready for import.

## Goals

- Build a sustainable microbial metadata harvesting pipeline rather than a
  manually curated seed list.
- Cover microbial resources discoverable from configured public sources:
  BiGG, GEO, Expression Atlas, PRIDE / ProteomeXchange, MetaboLights, and
  OmicsDI.
- Support resource search by organism, taxon ID, taxonomy group, strain,
  model ID, accession, keyword, omics type, source database, readiness, and
  method support.
- Make cache coverage auditable through per-source manifests, harvest QA,
  dedup QA, live smoke status, timestamps, failed query counts, capped query
  counts, and partial guidance.
- Give users a visual overview of resource distribution across taxonomy,
  omics type, source database, readiness, and method support.
- Send ready local resources to Candidate Package / Run Package workflows.
- Send metadata-only, raw-only, or curation-required resources to curation
  templates and curation workspaces.
- Let Model Generator and Summary show Atlas provenance and method hints.

## Completion Standards

### Coverage

- `resources/organism_targets.csv` defines the microbial target registry.
- `resources/microbial_harvest_scopes.csv` defines broad microbial harvest
  scopes for high-level coverage beyond the curated target registry.
- Target registry covers bacteria, archaea, cyanobacteria, yeasts, filamentous
  fungi, industrial microbes, environmental microbes, microbial pathogens, and
  microalgae or cell-factory hosts.
- Broad scope harvesting covers microbial-scale queries such as bacteria,
  archaea, cyanobacteria, yeasts, filamentous fungi, microbial pathogens,
  industrial microbes, environmental microbes, and microalgae.
- Every target source has a cached connector or cached metadata ingestion path.
- Every source reports query count, reported hits, harvested count, failed
  queries, capped queries, last update, and partial or stale state.
- Completion is judged by configured source coverage and auditable harvesting
  behavior, not by a fixed record-count target.
- Small live refreshes must merge new metadata into the existing cache instead
  of shrinking or replacing a broader cache unless an explicit shrink flag is
  used.

### Data Integrity

Every normalized resource must include:

- `resource_id`
- `resource_kind`
- `source_database`
- `connector_source`
- `accession` or `model_id`
- `organism_name`
- `taxon_id`
- `taxonomy_group`
- `omics_type`
- `data_level`
- `readiness`
- `readiness_reason`
- `external_url`
- `supported_methods`
- `harvested_at`
- `cache_status`

Cross-source duplicates must preserve provenance through:

- `canonical_resource_id`
- `cross_source_ids`
- `source_links`
- source-specific accession and URL metadata

`metadata_only`, `raw_data_only`, `manual_curation_required`, and similar
statuses must never be displayed as `ready_for_import`.

### API

`GET /api/resources/search` must support:

- `organism`
- `taxon_id`
- `taxonomy_group`
- `model_id`
- `accession`
- `q`
- `omics_type`
- `source_database`
- `readiness`
- `method_support`
- `limit`
- `offset`

The response must include:

- `resources`
- `total_count`
- `returned_count`
- `facets`
- `cache_status`
- `coverage_by_source`
- `guidance`

`GET /api/resources/atlas-summary` must include:

- total records
- source breakdown
- taxonomy breakdown
- omics breakdown
- readiness breakdown
- method support breakdown
- stale / partial cache status
- source-level coverage

### UI

- Resource Atlas is a resource map and workflow-entry surface, not a plain
  database list.
- Search results are not expanded before a search action.
- Results are shown in a fixed-height, scrollable board with pagination or
  load-more behavior.
- Resource Inspector has fixed height and internal scrolling, with long
  titles, accessions, URLs, and readiness reasons wrapped or truncated safely.
- A distribution visualization is available. v1 uses a clustered bubble map;
  v2 may use a Voronoi or space-filling map.
- Distribution views can switch between taxonomy, omics type, source database,
  readiness, and method support.
- Clicking a distribution group filters the result board.

### Workflow Handoff

- `ready_for_import` resources can be staged into Candidate Package / Run
  Package flows.
- `metadata_only`, `raw_data_only`, and `needs_curation` resources enter
  curation template or curation workspace flows.
- Candidate Package and Curation Workspace preserve Atlas provenance.
- Model Generator Dossier shows selected resource provenance, omics type,
  curation state, and method hints.
- Summary shows Atlas provenance and unresolved curation requirements.

## Phases

### Phase 1: Microbial Target Registry

Deliver `resources/organism_targets.csv` with scientific name, strain,
taxon ID, aliases, taxonomy group, model IDs, priority tier, source, and
enabled flag.

Acceptance:

- API can return target organisms.
- Search can filter by taxonomy group.
- Disabled targets are not included in default harvesting.

### Phase 2: Unified Resource Schema

Deliver a normalized resource schema for models, omics resources, readiness,
and method support inference.

Acceptance:

- All sources merge into one `resources[]` structure.
- Readiness is normalized consistently.
- Source, accession, organism, omics type, and readiness fields are complete.

### Phase 3: Cached Connector Framework

Deliver cached-first connectors for BiGG, GEO, Expression Atlas, PRIDE /
ProteomeXchange, MetaboLights, and OmicsDI.

Acceptance:

- Each connector supports dry run.
- Paginated sources support page size and max page controls.
- Network failure preserves old cache or fallback cache.
- No connector downloads raw data.
- Each source manifest records query and harvest statistics.

### Phase 4: Harvesting Pipeline Productionization

Deliver `tools/update_resource_cache.py` as the repeatable harvesting entry.

Acceptance:

- `--offline` generates a complete local metadata cache without network.
- Online mode can refresh one source at a time.
- Online mode can include broad microbial harvest scopes when the goal is
  microbial-wide discovery rather than one named organism.
- Live refreshes preserve and merge existing cache contents when a limited
  query returns fewer records than the current cache.
- `resources/resource_harvest_plan.json` defines staged smoke, incremental,
  and deep microbial metadata refresh plans.
- `tools/run_resource_harvest_plan.py` can execute or dry-run those stages and
  write an auditable plan report.
- A partial source failure does not invalidate other sources.
- `cache_manifest.json` summarizes all source states.
- The pipeline is compatible with scheduled daily metadata refresh.

### Phase 5: Deduplication and Cross-source Linking

Deliver canonical IDs, duplicate detection, and source-link preservation.

Acceptance:

- Repeated public studies are linked rather than shown as unrelated resources.
- Inspector can show multiple source links for a canonical resource.
- Deduplication does not discard source-specific metadata.
- Raw count and deduplicated count are both auditable.

### Phase 6: Search API and Atlas Summary

Deliver paginated search, facets, coverage summaries, and atlas summary.

Acceptance:

- Search supports core filters.
- Facets match the current result set.
- Atlas summary exposes source, taxonomy, omics, readiness, and method support
  distributions.
- Partial or stale cache states can be displayed in the UI.

### Phase 7: Resource Atlas UI

Deliver search filters, distribution map, result board, inspector, cache
summary, pagination, and workflow actions.

Acceptance:

- Results appear only after search.
- Large result sets do not stretch the whole page.
- Inspector remains readable with long metadata.
- Bubble map gives an at-a-glance resource distribution.
- Clicking a taxonomy, source, omics, readiness, or method group filters
  results.

### Phase 8: Workflow Handoff

Deliver Candidate Package, curation template, curation workspace, curated
evidence preview, curated evidence mapping preview, method hints, and Summary
provenance.

Acceptance:

- Ready local resources can create a Run Package.
- Metadata-only resources can only enter curation workflows.
- Curated CSV files join the Input upload queue only after preview.
- Summary traces source and curation state.

### Phase 9: Live Update and Monitoring

Deliver daily metadata refresh, stale cache detection, source failure logs,
last successful update tracking, and UI update status.

Acceptance:

- Daily updates refresh metadata only.
- Failed sources keep old cache available.
- UI displays last updated, partial, stale, and failed-source states.
- Users can tell whether the current index is fresh, stale, or partial.

## Non-goals

- Do not download raw FASTQ, SRA, mzML, supplementary matrices, or large raw
  archives by default.
- Do not automatically generate expression matrices, proteomics abundance
  tables, or metabolomics tables from raw data.
- Do not perform online gene, protein, or metabolite ID mapping automatically.
- Do not mark metadata-only resources as ready for import.
- Do not replace the Atlas with a plain database table.
- Do not use a fixed record count as the final completion criterion.

## Final Acceptance

The target mode is achieved when a user can:

1. Search microbial model and omics metadata across the configured public
   sources.
2. Inspect source, accession, organism, omics type, readiness, method support,
   provenance, and external links for each resource.
3. Understand resource distribution by taxonomy, omics type, source database,
   readiness, and method support from the Atlas visualization.
4. Filter and page through results without layout breakage.
5. Send ready resources to Run Package preparation.
6. Send non-ready resources to curation templates and curation workspaces.
7. Use the Atlas offline from the most recent metadata cache.
8. Audit each harvest from manifests, QA reports, dedup reports, and cache
   status.
