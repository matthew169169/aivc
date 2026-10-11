# Resource Atlas Lineage Tree QA

Date: 2026-06-25

## Checks Run

- `D:\generate\.venv\Scripts\python.exe tools\prepare_lineage_tree_images.py`
- `D:\generate\.venv\Scripts\python.exe -m py_compile tools\prepare_lineage_tree_images.py api\services.py api\resource_atlas_helpers.py`
- `npm.cmd run typecheck`
- `npm.cmd run build`
- `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py -k "resource_index_api_species_search_detail_and_suggestions" -q`
- `node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_lineage_tree.json --append-log`

## Current Evidence

- Atlas summary returns lineage tree fields.
- Current lineage summary reports 59 total nodes, 40 target species nodes, 9 discovered unplaced nodes, and 8 no-resource nodes.
- The image manifest contains 49 organism entries.
- Existing Draw_Trees assets cover 13 organisms.
- Generated SVG placeholders cover 36 organisms.
- `image_missing_count` is 0 after placeholder generation.
- Public-loadable placeholder files exist under `frontend/public/model-library/lineage-tree/`.

## Browser QA Notes

- HTTP/API smoke passed for Resource Atlas/Input, Model Generator, Model Compare, Analysis, and Summary.
- In-app Browser plugin bootstrap failed in this environment because its kernel assets path was unavailable.
- Strict browser/CDP mode remains unstable on this machine.
- A local Edge headless CDP probe opened `#/module-model-library`, expanded Deep Dive, and verified the Species Resource Lineage Tree DOM exists. The expanded taxonomy group exposed 22 node cards and 22 thumbnail images in the rendered DOM. Console output from PowerShell may show mojibake for Chinese text, so visual text fidelity should still be checked in the app before a formal demo.
- Visual manual QA should still be run before a formal demo if layout fidelity must be certified.

## Online Image Search Notes

- `tools/prepare_lineage_tree_images.py --online-wikimedia --replace-placeholders --limit 1 --attempt-limit 1` was run once.
- The run recorded `searched_online = true` and did not download a Commons image for that single attempted node.
- Generated placeholders remain the safe fallback.
- Larger online downloads should be run slowly and reviewed for license provenance before public redistribution.

## Public Image Replacement Notes

Date: 2026-06-26

- `tools/prepare_lineage_tree_images.py` now writes license/source audit sidecars:
  - `resources/lineage_tree_images/image_source_candidates.csv`
  - `resources/lineage_tree_images/image_license_audit.csv`
  - `resources/lineage_tree_images/image_download_report.json`
  - `resources/lineage_tree_images/image_download_report.csv`
- Wikimedia Commons candidates are accepted only when the candidate text matches the organism name and the license is public domain, CC0, CC BY, or CC BY-SA.
- The current manifest reports 16 ready images, 33 placeholders, and 3 downloaded online images.
- Enabled online images currently include `acinetobacter_baumannii_aye`, `aspergillus_niger_cbs51388`, and `shewanella_oneidensis_mr1`.
- Raw downloaded images are retained under `resources/lineage_tree_images/raw_sources/`; frontend thumbnails are normalized to WebP under `frontend/public/model-library/lineage-tree/`.
- A broader Wikimedia run hit HTTP 429 after a few requests. Continue replacements in small targeted batches with `--organism-id ... --online-wikimedia --replace-placeholders`.
- Visual check: `frontend/public/model-library/lineage-tree/bacteria/shewanella_oneidensis_mr1.webp` renders as a real micrograph-style image.

## Remaining Public Image Replacement Notes

Date: 2026-06-26

- Scope/category placeholders are now separated from organism placeholders:
  - `organism_placeholder_count = 24`
  - `abstract_placeholder_count = 9`
  - `public_image_not_checked_count = 23`
  - `public_image_query_failed_count = 1`
- `scope_*` nodes are marked `abstract_placeholder / abstract_non_species`; they are not concrete organism image targets.
- Batch 1 dry-run found accepted Wikimedia candidates, but the formal run hit `HTTP Error 429: Too Many Requests` on `aspergillus_oryzae_rib40`.
- The run stopped after 429 as intended. No additional public images were enabled in this pass.
- The next safe continuation is a later targeted batch, starting with a single organism and a longer delay, for example:
  `D:\generate\.venv\Scripts\python.exe tools\prepare_lineage_tree_images.py --organism-id aspergillus_oryzae_rib40 --online-wikimedia --replace-placeholders --attempt-limit 1 --limit 1 --sleep-seconds 10 --dry-run`

## Manual Local Image Import Notes

Date: 2026-06-26

- User-provided images were placed in `D:\generate\fig`.
- `resources/lineage_tree_images/local_image_candidates_from_fig.csv` records 11 accepted, traceable Wikimedia Commons local-image candidates.
- `resources/lineage_tree_images/local_image_candidates_from_fig_rejected.csv` records 13 files that were not imported because source/license could not be resolved, species mapping was wrong, or license text was outside the allowlist.
- Imported local images are copied to `resources/lineage_tree_images/raw_sources/<organism_id>/` and normalized to WebP thumbnails under `frontend/public/model-library/lineage-tree/`.
- Current manifest summary after import:
  - `ready_count = 27`
  - `downloaded_online_count = 14`
  - `organism_placeholder_count = 13`
  - `abstract_placeholder_count = 9`
  - `license_pending_count = 0`
- Visual check: `frontend/public/model-library/lineage-tree/bacteria/bacillus_licheniformis_dsm13.webp` renders correctly.
- Regression checks passed:
  - `D:\generate\.venv\Scripts\python.exe -m py_compile tools\prepare_lineage_tree_images.py api\services.py api\resource_atlas_helpers.py`
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_resource_harvest_tools.py tests\test_fastapi_api.py -k "resource or atlas or lineage_image" -q`
  - `npm.cmd run typecheck`
  - `npm.cmd run build`

## Internal Demo Image Import Notes

Date: 2026-06-26

- At the user's request, remaining local images from `D:\generate\fig` were imported for internal group demonstration only.
- These assets are marked `source_kind = local_internal_demo`, `public_image_status = internal_demo_only`, and `license = license_unverified_internal_demo`.
- `resources/lineage_tree_images/local_internal_demo_candidates_from_fig.csv` records the 13 internal-demo imports.
- Current manifest summary after internal-demo import:
  - `status = ready`
  - `ready_count = 40`
  - `organism_placeholder_count = 0`
  - `abstract_placeholder_count = 9`
  - `downloaded_online_count = 14`
  - `internal_demo_image_count = 13`
  - `license_pending_count = 0`
- These internal-demo images must be replaced or license-verified before public release or redistribution.
- Visual checks passed for `vibrio_cholerae_n16961.webp`, `yarrowia_lipolytica_w29.webp`, and `lactobacillus_plantarum_wcfs1.webp`.
- Regression checks passed:
  - `D:\generate\.venv\Scripts\python.exe -m pytest tests\test_resource_harvest_tools.py tests\test_fastapi_api.py -k "resource or atlas or lineage_image" -q`
  - `npm.cmd run typecheck`
  - `npm.cmd run build`
