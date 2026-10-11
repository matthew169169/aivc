# Resource Atlas Lineage Tree Spec

## Purpose

The Species Resource Lineage Tree turns the old Draw_Trees model lineage view into a resource-aware Deep Dive navigator. It helps users answer whether a species has models, omics evidence, annotation resources, workflow-ready inputs, curation-only metadata, and method support.

## Data Contract

`/api/resources/atlas-summary` returns these lineage fields:

- `lineage_tree_resource_nodes`
- `lineage_tree_resource_edges`
- `lineage_tree_summary`
- `lineage_tree_image_manifest`
- `unplaced_resource_organisms`

Species and strain nodes include model, transcriptomics, proteomics, metabolomics, kcat, annotation, ready, curation, metadata-only, raw-only, method hint, case study, image, and resource id fields.

## Empty And Discovered Nodes

- Target organisms from `resources/organism_targets.csv` stay visible even when they have no indexed resources.
- Empty nodes use the same card structure as populated nodes and show `No indexed resources yet`.
- Organisms discovered from harvested metadata but not yet placed in the target registry appear under `Discovered microbes` with `Needs lineage placement`.

## Thumbnail Cache

Thumbnails are visual identifiers only; they are not scientific evidence.

- Existing Draw_Trees images are used first.
- `tools/prepare_lineage_tree_images.py` writes provenance to `resources/lineage_tree_images/image_manifest.json`.
- Online organism images must pass the allowlist license check: public domain, CC0, CC BY, or CC BY-SA.
- The script writes audit sidecars:
  - `resources/lineage_tree_images/image_source_candidates.csv`
  - `resources/lineage_tree_images/image_license_audit.csv`
  - `resources/lineage_tree_images/image_download_report.json`
  - `resources/lineage_tree_images/image_download_report.csv`
- Raw downloaded images are retained under `resources/lineage_tree_images/raw_sources/<organism_id>/`.
- Frontend-loadable images are copied to `frontend/public/model-library/lineage-tree/`.
- Downloaded sources are normalized to WebP thumbnails with stable dimensions before the frontend uses them.
- Missing images receive generated SVG placeholders with stable dimensions.
- The script supports a throttled Wikimedia Commons path with `--online-wikimedia`; source URL, source image URL, license, license URL, attribution, sha256, local path, and timestamp must be recorded.
- A dry run with `--dry-run` may query candidates but must not write files.
- If no suitable public image passes name/license checks, the entry remains a generated placeholder and is marked as a visual fallback.

## UI Contract

The tree lives inside Resource Atlas Deep Dive, after the Source x Omics coverage matrix. It uses shadcn Accordion, Card, Badge, Progress, Button, ScrollArea, and Separator primitives.

Interactions:

- Species node click applies the organism lens and opens resource results.
- Omics badge click filters current organism plus omics type.
- Readiness badge click filters current organism plus readiness state.
- Case badge click applies the case study context when available.

## Verification

Required checks:

```powershell
D:\generate\.venv\Scripts\python.exe tools\prepare_lineage_tree_images.py
D:\generate\.venv\Scripts\python.exe tools\prepare_lineage_tree_images.py --online-wikimedia --replace-placeholders --attempt-limit 3 --dry-run
D:\generate\.venv\Scripts\python.exe -m py_compile tools\prepare_lineage_tree_images.py api\services.py api\resource_atlas_helpers.py
cd D:\generate\frontend
npm.cmd run typecheck
npm.cmd run build
cd D:\generate
D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "resource_index_api_species_search_detail_and_suggestions" -q
node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log
```

Acceptance:

- Atlas summary includes lineage fields.
- Empty target nodes are present.
- Discovered unplaced organisms are present.
- `image_missing_count` is zero after placeholder generation.
- `metadata_only` and `raw_data_only` resources do not count as workflow-ready.
