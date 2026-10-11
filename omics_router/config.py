"""Run configuration export helpers."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from .rules import RecommendationPlan


def make_run_config(selection: dict[str, Any], plan: RecommendationPlan) -> dict[str, Any]:
    """Build a reproducible config object from a routing result."""

    return {
        "schema_version": "0.1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "selection": selection,
        "run_order": plan.run_order,
        "recommendations": [asdict(rec) for rec in plan.recommendations],
        "warnings": plan.warnings,
        "missing_inputs": plan.missing_inputs,
        "next_best_data": plan.next_best_data,
        "execution": {
            "solver": "auto",
            "random_seed": 42,
            "dry_run": True,
            "tool_runners": {
                "baseline_qc": "memote + cobrapy",
                "context_specific": "troppo",
                "enzyme_constrained": "external_gecko_or_autopacmen",
                "thermodynamic": "pytfa",
                "flux_calibration": "external_fluxomics",
            },
        },
    }


def to_json(data: dict[str, Any]) -> str:
    """Serialize config to pretty JSON."""

    return json.dumps(data, ensure_ascii=False, indent=2)


def to_yaml(data: Any, indent: int = 0) -> str:
    """Serialize a simple JSON-like object to readable YAML.

    This avoids a PyYAML dependency for the MVP. The generated YAML is intended
    for configuration and review, not for preserving custom Python types.
    """

    spaces = " " * indent
    if isinstance(data, dict):
        lines: list[str] = []
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                lines.append(f"{spaces}{_scalar(key)}:")
                lines.append(to_yaml(value, indent + 2))
            else:
                lines.append(f"{spaces}{_scalar(key)}: {_scalar(value)}")
        return "\n".join(lines)
    if isinstance(data, list):
        if not data:
            return f"{spaces}[]"
        lines = []
        for item in data:
            if isinstance(item, dict):
                lines.append(f"{spaces}-")
                lines.append(to_yaml(item, indent + 2))
            elif isinstance(item, list):
                lines.append(f"{spaces}-")
                lines.append(to_yaml(item, indent + 2))
            else:
                lines.append(f"{spaces}- {_scalar(item)}")
        return "\n".join(lines)
    return f"{spaces}{_scalar(data)}"


def _scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if not text:
        return '""'
    if any(ch in text for ch in [":", "#", "{", "}", "[", "]", ",", "&", "*", "\n", "\"", "'"]):
        return json.dumps(text, ensure_ascii=False)
    if text.lower() in {"true", "false", "null"} or text[0] in "-!?@`":
        return json.dumps(text, ensure_ascii=False)
    return text
