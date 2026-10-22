"""Cloud data layout, separate from application source and bundled examples."""
from __future__ import annotations

import os
import json
import shutil
from pathlib import Path

from .background_jobs import atomic_json


BUNDLED_RUNS = ("shewanella_gecko_case", "putida_acetate_isoprenol_case", "synechocystis_spkb_case")


def data_root(app_root: Path) -> Path:
    configured = os.environ.get("OMICS_GEM_DATA_DIR", "").strip()
    return Path(configured).expanduser().resolve() if configured else app_root


def seed_cloud_workspace(app_root: Path, root: Path) -> None:
    """Copy examples once; an existing cloud workspace is never overwritten."""
    root.mkdir(parents=True, exist_ok=True)
    marker = root / ".bundled_examples_seeded.json"
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
        seeded = set(payload.get("run_ids", [])) if isinstance(payload, dict) else set()
    except (OSError, ValueError):
        seeded = set()
    for run_id in BUNDLED_RUNS:
        if run_id in seeded:
            continue
        source = app_root / "user_runs" / run_id
        target = root / "user_runs" / run_id
        if source.is_dir() and not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            staging = target.with_name(f".{run_id}.seeding")
            if staging.exists():
                shutil.rmtree(staging)
            shutil.copytree(source, staging)
            staging.rename(target)
        if source.is_dir():
            seeded.add(run_id)
    atomic_json(marker, {"run_ids": sorted(seeded)})
    for directory in ("task_logs", "examples", "atlas_curation_workspaces", "workspaces"):
        (root / directory).mkdir(parents=True, exist_ok=True)
