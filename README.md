# Omics-GEM Studio — Bundle Showcase

Static GitHub Pages site documenting `Omics-GEM-Studio-Windows-Browser-20260908-r2.zip`.

- `index.html` + `assets/` — designed site (no build step)
- `data/bundle.json` — generated index: 29,235 files, 82 endpoints, 44 docs, 10 cases
- `site_docs/` — all 44 markdown docs extracted from the bundle (400 KB)

The 6.3 GB Windows zip itself is **not** committed (GitHub file/repo limits). See `.gitignore`.

## Local preview

```bash
python3 -m http.server 8000
# → http://localhost:8000
```

## Deploy

GitHub Pages serves from `main` branch root. Enabled via `gh api` after push.
