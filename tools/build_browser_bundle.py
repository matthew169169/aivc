"""Create deterministic, content-addressed browser application/data archives."""
from __future__ import annotations

import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets/browser"


def archive(paths):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(paths):
            if not path.is_file() or "__pycache__" in path.parts or path.name.startswith("."):
                continue
            info = zipfile.ZipInfo(path.relative_to(ROOT).as_posix(), date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            bundle.writestr(info, path.read_bytes())
    return output.getvalue()


def build():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifests = {}
    tracked = set(subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).decode().split("\0"))
    groups = {
        "application": [p for root in ("api", "omics_router", "browser") for p in (ROOT / root).rglob("*.py")] + [ROOT / "requirements.txt", ROOT / "requirements-optional.txt"] + [p for root in ("resources", "case_studies", "model-library") for p in (ROOT / root).rglob("*")],
        "examples": [p for name in ("shewanella_gecko_case", "putida_acetate_isoprenol_case", "synechocystis_spkb_case") for p in (ROOT / "user_runs" / name).rglob("*") if p.relative_to(ROOT).as_posix() in tracked],
    }
    for name, paths in groups.items():
        data = archive(paths)
        digest = hashlib.sha256(data).hexdigest()
        filename = f"{name}-{digest[:12]}.zip"
        (OUTPUT / filename).write_bytes(data)
        for previous in OUTPUT.glob(f"{name}-*.zip"):
            if previous.name != filename:
                previous.unlink()
        manifests[name] = {"file": filename, "sha256": digest, "bytes": len(data)}
        print(f"{name}: {len(data) / 1024 / 1024:.1f} MB")
    (OUTPUT / "manifest.json").write_text(json.dumps({"schema": 1, "pyodide": "0.29.3", "bundles": manifests}, indent=2) + "\n")


if __name__ == "__main__":
    build()
