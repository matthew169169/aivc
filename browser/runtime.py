"""Run the existing HTTP application in a browser worker, without a socket."""
from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import subprocess
import zipfile
from pathlib import Path, PurePosixPath


def initialize():
    os.environ.update(OMICS_GEM_DATA_DIR="/data", OMICS_GEM_JOB_MODE="inline", OMICS_GEM_AUTH_ENABLED="false", OMICS_GEM_BROWSER="true")
    # A dedicated Web Worker already keeps Python off the UI thread. Browser
    # Python cannot start native threads, sockets, subprocesses, or MATLAB.
    import anyio.to_thread
    async def direct(function, *args, **kwargs):
        return function(*args)
    anyio.to_thread.run_sync = direct
    def unavailable(*args, **kwargs):
        raise RuntimeError("External programs cannot run in browser mode. Export the package for a compatible external runtime.")
    subprocess.run = unavailable
    from api.main import app
    from api.services import start_background_jobs
    start_background_jobs()
    return app


APP = None


def capabilities():
    return {
        "mode": "browser", "installation_required": False, "api_server_required": False,
        "storage": "IndexedDB on this browser and origin", "shared_between_devices": False,
        "supported": ["projects", "uploads", "atlas_curation", "steady_state_sbml", "model_generation", "fba", "pfba", "single_process_fva", "comparison", "reports", "sammi", "ml_profiles", "export_import"],
        "unavailable": ["MATLAB", "external_GECKO_RAVEN_execution", "external_DLkcat_execution", "native_subprocesses", "full_libSBML_validation", "parallel_processes"],
        "sbml": "Core Level 2/3, FBC bounds and objective, legacy COBRA bounds; dynamic SBML constructs are rejected",
    }


def backup():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("browser-backup.json", json.dumps({"format": "omics-gem-browser", "version": 1}))
        for path in sorted(Path("/data").rglob("*")):
            if path.is_file() and not path.is_symlink():
                archive.write(path, "data/" + path.relative_to("/data").as_posix())
    return output.getvalue()


def restore(data):
    """Validate the complete archive before restoring any files; never extract outside /data."""
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        marker = json.loads(archive.read("browser-backup.json"))
        if marker != {"format": "omics-gem-browser", "version": 1}:
            raise ValueError("This is not a supported Omics-GEM browser backup.")
        total = 0
        entries = []
        for entry in archive.infolist():
            if entry.filename == "browser-backup.json" or entry.is_dir():
                continue
            name = PurePosixPath(entry.filename)
            if not entry.filename.startswith("data/") or ".." in name.parts or "\\" in entry.filename or (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("The backup contains an unsafe file path.")
            target = (Path("/data") / Path(*name.parts[1:])).resolve()
            if not target.is_relative_to(Path("/data").resolve()):
                raise ValueError("The backup contains an unsafe file path.")
            total += entry.file_size
            if total > 768 * 1024 * 1024 or len(entries) >= 25000:
                raise ValueError("The backup exceeds the browser restore limit (768 MB / 25,000 files).")
            entries.append((entry, target))
        # Reading first also validates CRCs before existing data is touched.
        contents = [(target, archive.read(entry)) for entry, target in entries]
    for target, content in contents:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    from api import services
    services._initialize_workspace_from_config()
    return {"status": "restored", "file_count": len(entries)}


async def handle(payload):
    global APP
    if APP is None:
        APP = initialize()
    request = json.loads(payload)
    path, method = request["path"], request.get("method", "GET")
    body = base64.b64decode(request.get("body", ""))
    if path.split("?", 1)[0] == "/api/browser/capabilities":
        return response(200, json.dumps(capabilities()).encode())
    if path.split("?", 1)[0] == "/api/browser/backup" and method == "GET":
        return response(200, backup(), {"content-type": "application/zip", "content-disposition": 'attachment; filename="omics-gem-browser-backup.zip"'})
    if path.split("?", 1)[0] == "/api/browser/restore" and method == "POST":
        try:
            return response(200, json.dumps(restore(body)).encode())
        except (ValueError, KeyError, zipfile.BadZipFile) as exc:
            return response(400, json.dumps({"detail": str(exc)}).encode())
    if path.startswith("/api/environment/backend/repair") or path.startswith("/api/environment/external-dependencies/deep-check") or path.endswith("/gecko/external-run") or path.endswith("/gecko/adapter-probe"):
        return response(422, json.dumps({"detail": "This action needs an external program. Browser mode supports package preparation and export; external execution needs a compatible runtime."}).encode())
    import httpx
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=APP), base_url="http://browser.internal") as client:
        result = await client.request(method, path, content=body, headers=request.get("headers", {}))
    data = result.content
    if path.split("?", 1)[0] == "/api/health":
        health = result.json()
        health.update(execution_mode="browser", api_server_required=False, job_mode="browser_worker")
        data = json.dumps(health).encode()
    elif path.split("?", 1)[0] == "/api/environment/backend":
        environment = result.json()
        environment["required_modules"] = [row for row in environment.get("required_modules", []) if row["module"] != "uvicorn"]
        environment["missing_required_modules"] = [row["module"] for row in environment["required_modules"] if row["status"] != "available"]
        environment.update(execution_mode="browser", requirements_installed=not environment["missing_required_modules"],
                           status="ready" if environment.get("cobra_importable") else "ready_minimal",
                           recommendation="Browser runtime ready. The solver downloads automatically for your first calculation; no environment repair or installation is needed.")
        data = json.dumps(environment).encode()
    return response(result.status_code, data, dict(result.headers))


def response(status, body, headers=None):
    headers = headers or {"content-type": "application/json"}
    headers.pop("content-length", None)
    return json.dumps({"status": status, "headers": headers, "body": base64.b64encode(body).decode()})
