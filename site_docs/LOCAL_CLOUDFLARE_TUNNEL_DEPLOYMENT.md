# Local Cloudflare Tunnel Deployment

This guide exposes your local Omics-GEM Studio to classmates through a temporary
Cloudflare HTTPS URL. It keeps FastAPI local and exposes only the Caddy reverse
proxy.

## 1. Install/check dependencies

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\check_public_demo_dependencies.ps1
```

If dependencies are missing and `winget` is available, you can try:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\check_public_demo_dependencies.ps1 -InstallMissing
```

If `winget` is not available, install manually:

- Caddy: https://caddyserver.com/docs/install#windows
- cloudflared: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/

Open a new PowerShell window after installing command-line tools.

This project also supports portable binaries in `tools/bin/`. If
`tools/bin/caddy.exe` and `tools/bin/cloudflared.exe` exist, the deployment
scripts will use them before looking at the system `PATH`.

## 2. Enable shared-password login

Generate a password hash:

```powershell
.venv\Scripts\python.exe tools\hash_auth_password.py
```

Set environment variables before starting FastAPI:

```powershell
$env:OMICS_GEM_AUTH_ENABLED = "1"
$env:OMICS_GEM_PASSWORD_HASH = "<paste generated hash>"
$env:OMICS_GEM_SESSION_SECRET = "<long random secret>"
```

For local HTTP testing, leave this unset:

```powershell
$env:OMICS_GEM_COOKIE_SECURE = ""
```

For the Cloudflare HTTPS link, use:

```powershell
$env:OMICS_GEM_COOKIE_SECURE = "1"
```

The scripts never store the plaintext password.

## 3. Start the local same-origin proxy

Run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\start_local_reverse_proxy.ps1
```

This script:

- builds `frontend/dist` with `VITE_API_BASE_URL=same-origin`
- starts FastAPI on `127.0.0.1:8765` if needed
- starts Caddy on `http://localhost:8080`
- proxies `/api/*` to FastAPI
- serves the React static build for all other routes

Local test URL:

```text
http://localhost:8080
```

Health check:

```text
http://localhost:8080/api/health
```

## One-command quick demo

After dependencies are available, you can start the local reverse proxy and the
Cloudflare quick tunnel with one command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\start_public_demo_quick.ps1
```

The script starts the local proxy first, then keeps the Cloudflare tunnel in the
current PowerShell window so you can see the temporary public URL.

## 4. Start Cloudflare quick tunnel

In a second PowerShell window, run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\start_cloudflare_quick_tunnel.ps1
```

Cloudflare will print a temporary public URL such as:

```text
https://example-random-name.trycloudflare.com
```

Send classmates:

- the temporary HTTPS URL
- the shared Omics-GEM access password

Keep this PowerShell window open while classmates use the app.

## 5. Stop the demo

To stop public access, close the Cloudflare tunnel PowerShell window or press
`Ctrl+C` in it.

To stop the local proxy and backend, stop the `caddy` and Python/Uvicorn
processes, or restart the machine if this is only a short demo session.

## Safety notes

- Do not expose Vite or FastAPI directly to the internet.
- Do not share the Cloudflare URL without the Omics-GEM access password.
- Do not put private uploaded files or secrets into GitHub.
- This quick tunnel is for temporary demos. A fixed domain/named tunnel can be
  added later.
