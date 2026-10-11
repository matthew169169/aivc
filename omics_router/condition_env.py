"""Condition-specific environment tables for custom Omics-GEM runs.

The helpers in this module stay lightweight on purpose: they normalize user
tables, build exchange-bound rows compatible with the existing COBRA/TROPPO
runners, and summarize whether each condition is ready for solver-backed steps.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .constraints import SbmlModelIndex, read_csv_records, write_csv, write_json


CONDITION_ENVIRONMENT_COLUMNS = [
    "condition",
    "reference_condition",
    "medium_id",
    "substrate_rxn",
    "substrate_lb",
    "oxygen_rxn",
    "oxygen_lb",
    "co2_rxn",
    "co2_lb",
    "temperature_c",
    "ph",
    "salinity",
    "aerobic",
    "note",
    "status",
]

CONDITION_EXCHANGE_BOUND_COLUMNS = [
    "condition",
    "reaction_id",
    "model_reaction_id",
    "lower_bound",
    "upper_bound",
    "source",
    "confidence",
    "status",
    "note",
]

CONDITION_SUMMARY_COLUMNS = [
    "condition",
    "environment_status",
    "reference_condition",
    "medium_id",
    "substrate_rxn",
    "oxygen_policy",
    "exchange_bound_count",
    "valid_exchange_bound_count",
    "invalid_exchange_bound_count",
    "guidance",
]


@dataclass(slots=True)
class ConditionSetupPackage:
    """Files written for a reusable condition setup package."""

    output_dir: str
    files: dict[str, str]
    status: str
    summary_rows: list[dict[str, object]]


def default_condition_environment_rows() -> list[dict[str, object]]:
    """Return editable starter rows for the Streamlit condition setup page."""

    return [
        {
            "condition": "condition_a",
            "reference_condition": "",
            "medium_id": "custom_medium",
            "substrate_rxn": "EX_glc__D_e",
            "substrate_lb": -10.0,
            "oxygen_rxn": "EX_o2_e",
            "oxygen_lb": -20.0,
            "co2_rxn": "EX_co2_e",
            "co2_lb": "",
            "temperature_c": 37.0,
            "ph": 7.0,
            "salinity": "",
            "aerobic": True,
            "note": "",
        },
        {
            "condition": "condition_b",
            "reference_condition": "condition_a",
            "medium_id": "custom_medium",
            "substrate_rxn": "EX_glc__D_e",
            "substrate_lb": -5.0,
            "oxygen_rxn": "EX_o2_e",
            "oxygen_lb": 0.0,
            "co2_rxn": "EX_co2_e",
            "co2_lb": "",
            "temperature_c": 37.0,
            "ph": 7.0,
            "salinity": "",
            "aerobic": False,
            "note": "",
        },
    ]


def default_condition_exchange_bound_rows() -> list[dict[str, object]]:
    """Return an empty-but-shaped exchange-bound table for UI editing."""

    return [
        {
            "condition": "condition_a",
            "reaction_id": "EX_glc__D_e",
            "model_reaction_id": "",
            "lower_bound": -10.0,
            "upper_bound": "",
            "source": "manual",
            "confidence": "configured",
            "note": "",
        }
    ]


def read_condition_environment(path: str | Path) -> list[dict[str, object]]:
    """Read and normalize a condition environment CSV/TSV file."""

    return normalize_condition_environment(read_csv_records(path))


def read_condition_exchange_bounds(
    path: str | Path,
    model_index: SbmlModelIndex | None = None,
) -> list[dict[str, object]]:
    """Read and normalize condition exchange bounds."""

    return normalize_condition_exchange_bounds(read_csv_records(path), model_index=model_index)


def normalize_condition_environment(rows: list[dict[str, Any]]) -> list[dict[str, object]]:
    """Normalize condition-level environment rows into a stable schema."""

    normalized: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        condition = _text(row.get("condition") or row.get("sample") or f"condition_{index}")
        record = {
            "condition": condition,
            "reference_condition": _text(_first_value(row.get("reference_condition"), row.get("base_condition"))),
            "medium_id": _text(_first_value(row.get("medium_id"), row.get("medium"))),
            "substrate_rxn": _text(_first_value(row.get("substrate_rxn"), row.get("carbon_source_rxn"))),
            "substrate_lb": _to_float(_first_value(row.get("substrate_lb"), row.get("substrate_lower_bound"))),
            "oxygen_rxn": _text(_first_value(row.get("oxygen_rxn"), row.get("o2_rxn"))),
            "oxygen_lb": _to_float(_first_value(row.get("oxygen_lb"), row.get("oxygen_lower_bound"))),
            "co2_rxn": _text(row.get("co2_rxn")),
            "co2_lb": _to_float(_first_value(row.get("co2_lb"), row.get("co2_lower_bound"))),
            "temperature_c": _to_float(_first_value(row.get("temperature_c"), row.get("temperature"))),
            "ph": _to_float(row.get("ph")),
            "salinity": _text(row.get("salinity")),
            "aerobic": _to_bool(row.get("aerobic")),
            "note": _text(row.get("note")),
        }
        record["status"] = classify_condition_environment(record)
        normalized.append(_project_columns(record, CONDITION_ENVIRONMENT_COLUMNS))
    return normalized


def normalize_condition_exchange_bounds(
    rows: list[dict[str, Any]],
    model_index: SbmlModelIndex | None = None,
) -> list[dict[str, object]]:
    """Normalize user-provided condition exchange bounds."""

    normalized: list[dict[str, object]] = []
    for index, row in enumerate(rows, start=1):
        condition = _text(row.get("condition") or row.get("sample") or f"condition_{index}")
        reaction_id = _text(row.get("reaction_id") or row.get("model_reaction_id"))
        model_reaction_id, mapping_status = resolve_reaction_id(reaction_id, model_index)
        lower = _to_float(_first_value(row.get("lower_bound"), row.get("lb")))
        upper = _to_float(_first_value(row.get("upper_bound"), row.get("ub")))
        raw_status = _text(row.get("status"))
        status = classify_exchange_bound(reaction_id, model_reaction_id, mapping_status, lower, upper)
        if model_index is None and raw_status in {"missing_reaction", "missing_bounds", "invalid_bounds", "not_found"}:
            status = raw_status
        normalized.append(
            {
                "condition": condition,
                "reaction_id": reaction_id,
                "model_reaction_id": model_reaction_id,
                "lower_bound": lower,
                "upper_bound": upper,
                "source": _text(row.get("source")) or "manual",
                "confidence": _text(row.get("confidence")) or "configured",
                "status": status,
                "note": _text(row.get("note")),
            }
        )
    return normalized


def build_exchange_bounds_from_environment(
    environment_rows: list[dict[str, Any]],
    model_index: SbmlModelIndex | None = None,
) -> list[dict[str, object]]:
    """Build exchange-bound rows from substrate, oxygen, and CO2 shortcuts."""

    rows: list[dict[str, object]] = []
    for env in normalize_condition_environment(environment_rows):
        condition = str(env.get("condition") or "default")
        rows.extend(
            _environment_bound_row(
                condition=condition,
                reaction_id=_text(env.get("substrate_rxn")),
                lower_bound=_to_float(env.get("substrate_lb")),
                source="condition_environment:substrate",
                model_index=model_index,
            )
        )
        rows.extend(
            _environment_bound_row(
                condition=condition,
                reaction_id=_text(env.get("oxygen_rxn")),
                lower_bound=_to_float(env.get("oxygen_lb")),
                source="condition_environment:oxygen",
                model_index=model_index,
            )
        )
        rows.extend(
            _environment_bound_row(
                condition=condition,
                reaction_id=_text(env.get("co2_rxn")),
                lower_bound=_to_float(env.get("co2_lb")),
                source="condition_environment:co2",
                model_index=model_index,
            )
        )
    return rows


def combine_condition_exchange_bounds(
    environment_rows: list[dict[str, Any]],
    exchange_bound_rows: list[dict[str, Any]],
    model_index: SbmlModelIndex | None = None,
) -> list[dict[str, object]]:
    """Combine environment-derived and manually supplied exchange bounds."""

    env_bounds = build_exchange_bounds_from_environment(environment_rows, model_index=model_index)
    manual_bounds = normalize_condition_exchange_bounds(exchange_bound_rows, model_index=model_index)
    return [*env_bounds, *manual_bounds]


def summarize_condition_environment(
    environment_rows: list[dict[str, Any]],
    exchange_bound_rows: list[dict[str, Any]],
) -> list[dict[str, object]]:
    """Summarize condition readiness for downstream solver-backed workflows."""

    env_rows = normalize_condition_environment(environment_rows)
    bound_rows = normalize_condition_exchange_bounds(exchange_bound_rows)
    env_by_condition = {str(row.get("condition")): row for row in env_rows}
    bounds_by_condition: dict[str, list[dict[str, object]]] = {}
    for row in bound_rows:
        bounds_by_condition.setdefault(str(row.get("condition") or "default"), []).append(row)

    conditions = sorted(set(env_by_condition) | set(bounds_by_condition))
    rows = [
        _summarize_one_condition(condition, env_by_condition.get(condition), bounds_by_condition.get(condition, []))
        for condition in conditions
    ]
    if rows:
        rows.insert(0, _summarize_all_conditions(rows))
    return rows


def build_condition_setup_package(
    output_dir: str | Path,
    environment_rows: list[dict[str, Any]],
    exchange_bound_rows: list[dict[str, Any]],
    model_index: SbmlModelIndex | None = None,
) -> ConditionSetupPackage:
    """Write normalized condition setup tables and a compact manifest."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    env_rows = normalize_condition_environment(environment_rows)
    combined_bounds = combine_condition_exchange_bounds(env_rows, exchange_bound_rows, model_index=model_index)
    summary_rows = summarize_condition_environment(env_rows, combined_bounds)
    files = {
        "condition_environment": str(output / "condition_environment.csv"),
        "condition_exchange_bounds": str(output / "condition_exchange_bounds.csv"),
        "condition_summary": str(output / "condition_environment_summary.csv"),
        "manifest": str(output / "condition_setup_manifest.json"),
    }
    write_csv(files["condition_environment"], env_rows)
    write_csv(files["condition_exchange_bounds"], combined_bounds)
    write_csv(files["condition_summary"], summary_rows)
    status = classify_condition_setup(summary_rows)
    write_json(
        files["manifest"],
        {
            "schema_version": "0.1.0",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "status": status,
            "files": files,
            "condition_count": sum(1 for row in summary_rows if row.get("condition") != "ALL"),
        },
    )
    return ConditionSetupPackage(
        output_dir=str(output),
        files=files,
        status=status,
        summary_rows=summary_rows,
    )


def classify_condition_environment(row: dict[str, object]) -> str:
    """Classify one condition-environment row."""

    if not _text(row.get("condition")):
        return "missing_condition"
    has_medium = bool(_text(row.get("medium_id")))
    has_bound_shortcut = any(
        _text(row.get(reaction_field)) and _to_float(row.get(bound_field)) is not None
        for reaction_field, bound_field in (
            ("substrate_rxn", "substrate_lb"),
            ("oxygen_rxn", "oxygen_lb"),
            ("co2_rxn", "co2_lb"),
        )
    )
    if has_medium or has_bound_shortcut:
        return "configured"
    return "minimal"


def classify_exchange_bound(
    reaction_id: str,
    model_reaction_id: str,
    mapping_status: str,
    lower_bound: float | None,
    upper_bound: float | None,
) -> str:
    """Classify one exchange-bound row."""

    if not reaction_id:
        return "missing_reaction"
    if lower_bound is None and upper_bound is None:
        return "missing_bounds"
    if lower_bound is not None and upper_bound is not None and lower_bound > upper_bound:
        return "invalid_bounds"
    if mapping_status == "not_found":
        return "not_found"
    if model_reaction_id:
        return mapping_status if mapping_status in {"mapped", "not_checked"} else "mapped"
    return "not_checked"


def classify_condition_setup(summary_rows: list[dict[str, object]]) -> str:
    """Classify the overall condition setup status."""

    condition_rows = [row for row in summary_rows if row.get("condition") != "ALL"]
    if not condition_rows:
        return "missing_conditions"
    if any(row.get("environment_status") == "needs_review" for row in condition_rows):
        return "needs_review"
    if any(row.get("environment_status") == "minimal" for row in condition_rows):
        return "configured_with_warnings"
    return "configured"


def resolve_reaction_id(
    reaction_id: str,
    model_index: SbmlModelIndex | None = None,
) -> tuple[str, str]:
    """Resolve a reaction id against an optional SBML model index."""

    reaction = _text(reaction_id)
    if not reaction:
        return "", "missing_reaction"
    if model_index is None:
        return reaction, "not_checked"
    return model_index.resolve_reaction(reaction)


def _environment_bound_row(
    condition: str,
    reaction_id: str,
    lower_bound: float | None,
    source: str,
    model_index: SbmlModelIndex | None,
) -> list[dict[str, object]]:
    if not reaction_id or lower_bound is None:
        return []
    model_reaction_id, mapping_status = resolve_reaction_id(reaction_id, model_index)
    return [
        {
            "condition": condition,
            "reaction_id": reaction_id,
            "model_reaction_id": model_reaction_id,
            "lower_bound": lower_bound,
            "upper_bound": None,
            "source": source,
            "confidence": "configured",
            "status": classify_exchange_bound(reaction_id, model_reaction_id, mapping_status, lower_bound, None),
            "note": "",
        }
    ]


def _summarize_one_condition(
    condition: str,
    env: dict[str, object] | None,
    bounds: list[dict[str, object]],
) -> dict[str, object]:
    valid_statuses = {"mapped", "not_checked", ""}
    valid_count = sum(1 for row in bounds if row.get("status") in valid_statuses)
    invalid_count = len(bounds) - valid_count
    env_status = str(env.get("status")) if env else "bounds_only"
    if invalid_count:
        env_status = "needs_review"
    elif env_status == "minimal" and valid_count:
        env_status = "configured"
    oxygen_policy = _oxygen_policy(env)
    return _project_columns(
        {
            "condition": condition,
            "environment_status": env_status,
            "reference_condition": env.get("reference_condition", "") if env else "",
            "medium_id": env.get("medium_id", "") if env else "",
            "substrate_rxn": env.get("substrate_rxn", "") if env else "",
            "oxygen_policy": oxygen_policy,
            "exchange_bound_count": len(bounds),
            "valid_exchange_bound_count": valid_count,
            "invalid_exchange_bound_count": invalid_count,
            "guidance": _condition_guidance(env_status, valid_count, invalid_count, oxygen_policy),
        },
        CONDITION_SUMMARY_COLUMNS,
    )


def _summarize_all_conditions(rows: list[dict[str, object]]) -> dict[str, object]:
    invalid_count = sum(int(row.get("invalid_exchange_bound_count") or 0) for row in rows)
    minimal_count = sum(1 for row in rows if row.get("environment_status") == "minimal")
    status = "configured"
    if invalid_count:
        status = "needs_review"
    elif minimal_count:
        status = "configured_with_warnings"
    return _project_columns(
        {
            "condition": "ALL",
            "environment_status": status,
            "reference_condition": "",
            "medium_id": "",
            "substrate_rxn": "",
            "oxygen_policy": "",
            "exchange_bound_count": sum(int(row.get("exchange_bound_count") or 0) for row in rows),
            "valid_exchange_bound_count": sum(int(row.get("valid_exchange_bound_count") or 0) for row in rows),
            "invalid_exchange_bound_count": invalid_count,
            "guidance": f"{len(rows)} condition(s), {invalid_count} bound row(s) need review.",
        },
        CONDITION_SUMMARY_COLUMNS,
    )


def _oxygen_policy(env: dict[str, object] | None) -> str:
    if not env:
        return "unspecified"
    aerobic = env.get("aerobic")
    oxygen_lb = _to_float(env.get("oxygen_lb"))
    if aerobic is True or (oxygen_lb is not None and oxygen_lb < 0):
        return "aerobic"
    if aerobic is False or oxygen_lb == 0:
        return "anaerobic_or_limited"
    return "unspecified"


def _condition_guidance(status: str, valid_count: int, invalid_count: int, oxygen_policy: str) -> str:
    if invalid_count:
        return "Review reaction ids or lower/upper bounds before solver-backed execution."
    if status == "minimal" and not valid_count:
        return "Only metadata is configured; add exchange bounds for condition-specific FBA."
    if oxygen_policy == "unspecified":
        return "Configured; consider setting oxygen uptake if aerobic state matters."
    return "Configured for condition-specific solver steps."


def _project_columns(row: dict[str, object], columns: list[str]) -> dict[str, object]:
    return {column: row.get(column, "") for column in columns}


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _first_value(*values: object) -> object:
    for value in values:
        if value is None:
            continue
        if str(value).strip() == "":
            continue
        return value
    return None


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_bool(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return None
    if text in {"1", "true", "yes", "y", "aerobic"}:
        return True
    if text in {"0", "false", "no", "n", "anaerobic"}:
        return False
    return None
