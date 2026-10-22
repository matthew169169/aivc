"""Local backend configuration for optional external tools."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = Path(os.environ.get("OMICS_GEM_DATA_DIR") or ROOT) / "local_backend_config.json"
BACKEND_ENV_KEYS = {
    "matlab_cmd": "MATLAB_CMD",
    "gecko_home": "GECKO_HOME",
    "raven_home": "RAVEN_HOME",
    "cobra_toolbox_home": "COBRA_TOOLBOX_HOME",
    "solver": "OMICS_GEM_SOLVER",
    "pytfa_thermo_db": "PYTFA_THERMO_DB",
    "sammi_standalone_home": "SAMMI_STANDALONE_HOME",
}


def load_local_backend_config(path: str | Path | None = None) -> dict[str, str]:
    """Load local backend paths from a JSON config file."""

    config_path = Path(path or DEFAULT_CONFIG_PATH)
    if not config_path.exists() or config_path.stat().st_size == 0:
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {
        key: str(data.get(key, "")).strip()
        for key in BACKEND_ENV_KEYS
        if str(data.get(key, "")).strip()
    }


def save_local_backend_config(
    config: dict[str, Any],
    path: str | Path | None = None,
) -> dict[str, str]:
    """Save local backend paths and return the normalized config."""

    normalized = {
        key: str(config.get(key, "")).strip()
        for key in BACKEND_ENV_KEYS
        if str(config.get(key, "")).strip()
    }
    output = Path(path or DEFAULT_CONFIG_PATH)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    return normalized


def apply_local_backend_env(config: dict[str, Any] | None = None) -> dict[str, str]:
    """Apply local backend config to this process environment."""

    normalized = {
        key: str(value).strip()
        for key, value in (config or load_local_backend_config()).items()
        if str(value).strip()
    }
    applied: dict[str, str] = {}
    for key, env_key in BACKEND_ENV_KEYS.items():
        value = normalized.get(key, "")
        if value:
            os.environ[env_key] = value
            applied[env_key] = value
    return applied


def backend_config_rows(config: dict[str, Any] | None = None) -> list[dict[str, object]]:
    """Return config rows suitable for display in Streamlit."""

    normalized = config or load_local_backend_config()
    rows: list[dict[str, object]] = []
    for key, env_key in BACKEND_ENV_KEYS.items():
        value = str(normalized.get(key, "")).strip()
        exists = Path(value).exists() if value else False
        rows.append(
            {
                "setting": key,
                "env_var": env_key,
                "path": value,
                "exists": exists,
                "status": "configured" if exists else "missing_or_unset",
            }
        )
    return rows
