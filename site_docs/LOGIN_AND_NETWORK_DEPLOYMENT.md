# Login And Network Deployment

Omics-GEM Studio supports a first-pass shared-password access gate for lab or
small public demos. This is not a multi-user permission system; it protects the
whole app with one shared password.

## Local Mode

Authentication is disabled by default. In local desktop mode, start the app as
usual and it opens without a login page.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start_omics_gem_browser_app.ps1
```

## Enable Shared Password Login

Generate a password hash:

```powershell
.venv\Scripts\python.exe tools\hash_auth_password.py
```

Set these environment variables before starting the backend:

```powershell
$env:OMICS_GEM_AUTH_ENABLED = "1"
$env:OMICS_GEM_PASSWORD_HASH = "<paste generated hash>"
$env:OMICS_GEM_SESSION_SECRET = "<long random secret>"
```

Optional settings:

```powershell
$env:OMICS_GEM_SESSION_TTL_SECONDS = "43200"
$env:OMICS_GEM_COOKIE_SECURE = "1"
$env:OMICS_GEM_ALLOWED_ORIGINS = "https://your-domain.example,http://lab-host:5173"
```

`OMICS_GEM_COOKIE_SECURE=1` should be used behind HTTPS. For local HTTP testing,
leave it unset.

## LAN / Server Mode

Use `-PublicHost` to bind the FastAPI and Vite dev servers to `0.0.0.0`.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start_omics_gem_browser_app.ps1 -PublicHost
```

If the browser must call a public API URL, pass it explicitly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start_omics_gem_browser_app.ps1 `
  -PublicHost `
  -PublicApiUrl "https://your-domain.example"
```

The startup script still checks backend health through `127.0.0.1`, so it can
start reliably even before an external reverse proxy is ready.

## Production Recommendation

For internet access, do not expose Vite or raw Uvicorn directly. Use:

- frontend static build served by Nginx or Caddy
- FastAPI behind the same HTTPS domain
- `OMICS_GEM_COOKIE_SECURE=1`
- `OMICS_GEM_ALLOWED_ORIGINS` restricted to the public frontend origin

When auth is enabled, `/api/health` and `/api/auth/*` remain public. Other API
routes, file downloads, workflow actions, `/docs`, `/redoc`, and
`/openapi.json` require a valid session cookie.
