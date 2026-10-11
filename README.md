# Omics-GEM Studio — Original Web (20260908-r2)

This repo hosts the **original web** extracted from
`Omics-GEM-Studio-Windows-Browser-20260908-r2.zip`, not a summary site.

## Contents (from `OmicsGEM/` in the bundle)

- `index.html` + `assets/` — prebuilt React/Vite frontend (`frontend/dist`)
- `model-library/` — lineage-tree SVGs/WebPs + draw-trees images
- `ui_mockups/` — workflow stage mockup images
- `api/` — FastAPI backend source (15 files): `main.py`, `services.py`,
  `browser_app.py`, resource/curation/run-package helpers

Total: 113 frontend files (~25.9 MB) + 15 API files (~0.6 MB).
The 6.3 GB Windows bundle itself (`.python/`, `case_studies/`, `paper/`,
`user_runs/`, `tools/bin/*.exe`) is excluded — see `.gitignore`.

## Live demo (frontend only)

GitHub Pages serves this directory statically:

https://matthew169169.github.io/aivc/

Note: API calls will fail on Pages (no backend) — UI shell, assets,
model-library and mockups render; data views need the local backend below.

## Run full app locally (Windows, from the bundle)

```powershell
cd D:\generate
.\start_omics_gem_browser_app.ps1
# → http://127.0.0.1:8765
```

Backend smoke:

```powershell
D:\generate\.venv\Scripts\python.exe -m pytest tests\test_fastapi_api.py
```

## Serve this exact frontend locally

```bash
python3 -m http.server 8000
# → http://localhost:8000
```

To wire it to a backend, run the FastAPI app from `api/` (needs
`fastapi`, `uvicorn[standard]`, `python-multipart`) — entrypoint
`api/browser_app.py` serves `frontend/dist` + API on one port.
