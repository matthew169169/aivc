# Omics-GEM Studio clone

This repository clones the original web app from
`Omics-GEM-Studio-Windows-Browser-20260908-r2` (OmicsGEM `frontend/dist` + FastAPI).

Live frontend: https://matthew169169.github.io/aivc/

GitHub Pages hosts the original SPA. API-backed workflow views need the local backend below.

## What is included

- Original React/Vite UI: `index.html`, `assets/`, `model-library/`, `ui_mockups/`
- FastAPI backend: `api/`
- Router library used by the backend: `omics_router/`
- Compact resource atlas indexes: `resources/` (full Windows runtime, MATLAB/GECKO, and large run packages are not in git)

## Run the original app locally

```bash
cd aivc
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python run_local.py
```

Open http://127.0.0.1:8765

The UI talks to `/api/*` on the same origin. Shared-password auth is off by default for the clone (`OMICS_GEM_AUTH_ENABLED=false`).

Optional:

```bash
export OMICS_GEM_PORT=8765
export OMICS_GEM_AUTH_ENABLED=true
export OMICS_GEM_PASSWORD_HASH=...
export OMICS_GEM_SESSION_SECRET=...
python run_local.py
```

## GitHub Pages note

Pages is static. DataHub / run packages / SAMMI jobs return unreachable until `run_local.py` is used. Model library trees and the original studio shell still load on Pages.
