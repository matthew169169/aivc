# Omics-GEM Studio clone

This repository clones the original web app from
`Omics-GEM-Studio-Windows-Browser-20260908-r2` (OmicsGEM `frontend/dist` + FastAPI).

Live frontend: https://matthew169169.github.io/aivc/

Live API: https://aivc.onrender.com (deploy below) — the Pages site talks
to it via `window.OMICS_GEM_API_BASE` in `index.html`/`404.html`.
No static snapshots: every `/api/*` call hits the real FastAPI backend,
so all functions (search, curation, runs, GECKO, SAMMI, ML-hybrid, jobs)
work from the public site once the backend is up.

## Deploy the backend (Render, free)

One click (uses `render.yaml` in this repo):

https://render.com/deploy?repo=https://github.com/matthew169169/aivc

Keep the service name `aivc` so its URL is `https://aivc.onrender.com`
(the URL wired into the frontend). If you pick another name, update the
`OMICS_GEM_API_BASE` line in `index.html` and `404.html` and push.
`render.yaml` already sets CORS for the Pages origin and disables the
shared-password gate (`OMICS_GEM_AUTH_ENABLED=false`).

Verify after deploy:

```bash
curl https://aivc.onrender.com/api/health
curl https://aivc.onrender.com/api/case-studies
```

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

The bundled JS is subpath-aware (API base = `OMICS_GEM_API_BASE` override
or `origin + pathname`, relative `./model-library/` + `./ui_mockups/`
links), so the same build works locally, on Render, and on Pages.
Pages is static hosting only — it serves the SPA shell and forwards every
`/api/*` call to the Render backend above. The studio shell and model
library load without a login gate.
