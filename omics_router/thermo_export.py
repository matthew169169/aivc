"""Export pyTFA-friendly concentration packages from intracellular metabolomics."""

from __future__ import annotations

import csv
import math
import shutil
from dataclasses import dataclass
from pathlib import Path

from .constraints import read_csv_records, write_csv, write_json


PACKAGE_SCHEMA_VERSION = "0.1"
SUPPORTED_CONCENTRATION_UNITS = {
    "M": 1.0,
    "mM": 1e-3,
    "uM": 1e-6,
    "nM": 1e-9,
}


@dataclass(slots=True)
class PyTFAExportResult:
    """Summary returned by the pyTFA export workflow."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]


def export_pytfa_package(
    model_path: str | Path,
    concentration_path: str | Path,
    output_dir: str | Path,
    model_id: str = "iJO1366",
    pytfa_target: str = "pyTFA thermodynamic anchors",
) -> PyTFAExportResult:
    """Create a portable input package for a future pyTFA run."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    model_target = output / "model.xml"
    shutil.copyfile(model_path, model_target)

    files = {
        "model": str(model_target),
        "concentration_bounds": str(output / "concentration_bounds.tsv"),
        "conditions": str(output / "conditions.tsv"),
        "thermo_qc_summary": str(output / "thermo_qc_summary.csv"),
        "thermo_qc_recommendations": str(output / "thermo_qc_recommendations.csv"),
        "protocol_template": str(output / "protocol_template.py"),
        "readme": str(output / "README.md"),
        "summary": str(output / "pytfa_export_summary.csv"),
        "manifest": str(output / "pytfa_export_manifest.json"),
    }

    concentration_rows = read_csv_records(concentration_path)
    bound_rows = build_concentration_bound_rows(concentration_rows)
    summary_rows = summarize_thermo_inputs(bound_rows)
    recommendation_rows = build_thermo_recommendations(summary_rows)
    condition_rows = build_condition_rows(summary_rows)

    write_tsv(files["concentration_bounds"], bound_rows)
    write_tsv(files["conditions"], condition_rows)
    write_csv(files["thermo_qc_summary"], summary_rows)
    write_csv(files["thermo_qc_recommendations"], recommendation_rows)
    Path(files["protocol_template"]).write_text(build_protocol_template(), encoding="utf-8")
    Path(files["readme"]).write_text(build_package_readme(model_id, pytfa_target), encoding="utf-8")

    manifest = {
        "status": "completed",
        "package_schema_version": PACKAGE_SCHEMA_VERSION,
        "model_id": model_id,
        "pytfa_target": pytfa_target,
        "source_files": {
            "model_path": str(model_path),
            "concentration_path": str(concentration_path),
        },
        "unit_assumptions": {
            "source_supported_units": sorted(SUPPORTED_CONCENTRATION_UNITS),
            "exported_concentration_unit": "M",
            "ln_bounds": "natural_log_of_molar_concentration_bounds",
            "log10_bounds": "base10_log_of_molar_concentration_bounds",
        },
        "conditions": [row["condition"] for row in condition_rows],
        "files": files,
    }
    write_json(files["manifest"], manifest)
    summary = build_export_summary(files)
    write_csv(files["summary"], summary)

    ready_conditions = [row for row in summary_rows if row.get("ready_concentration_count", 0) != 0]
    return PyTFAExportResult(
        status="completed",
        output_dir=str(output),
        message=f"Exported pyTFA input package with {len(ready_conditions)} concentration-ready conditions.",
        files=files,
    )


def build_concentration_bound_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    """Normalize concentration rows and add molar/log bounds."""

    output = []
    for row in rows:
        condition = row.get("condition") or row.get("sample") or "default"
        unit = row.get("unit", "")
        factor = SUPPORTED_CONCENTRATION_UNITS.get(unit)
        concentration = _to_float(row.get("concentration") or row.get("value"))
        lower = _to_float(row.get("lower_bound"))
        upper = _to_float(row.get("upper_bound"))
        model_metabolite_id = row.get("model_metabolite_id") or row.get("metabolite_id") or ""
        mapping_status = row.get("status") or "provided"
        status = classify_concentration_status(model_metabolite_id, mapping_status, lower, upper, unit)
        concentration_m = concentration * factor if concentration is not None and factor is not None else None
        lower_m = lower * factor if lower is not None and factor is not None else None
        upper_m = upper * factor if upper is not None and factor is not None else None
        output.append(
            {
                "condition": condition,
                "sample": row.get("sample") or condition,
                "metabolite_id": row.get("metabolite_id", ""),
                "model_metabolite_id": model_metabolite_id,
                "cobra_metabolite_id": cobra_metabolite_id(model_metabolite_id),
                "compartment": row.get("compartment", ""),
                "concentration_source_value": concentration,
                "lower_bound_source": lower,
                "upper_bound_source": upper,
                "source_unit": unit,
                "concentration_M": concentration_m,
                "lower_bound_M": lower_m,
                "upper_bound_M": upper_m,
                "ln_lower_bound": math.log(lower_m) if lower_m is not None and lower_m > 0 else None,
                "ln_upper_bound": math.log(upper_m) if upper_m is not None and upper_m > 0 else None,
                "log10_lower_bound": math.log10(lower_m) if lower_m is not None and lower_m > 0 else None,
                "log10_upper_bound": math.log10(upper_m) if upper_m is not None and upper_m > 0 else None,
                "mapping_status": mapping_status,
                "status": status,
                "note": row.get("note", ""),
            }
        )
    return output


def classify_concentration_status(
    model_metabolite_id: str,
    mapping_status: str,
    lower: float | None,
    upper: float | None,
    unit: str,
) -> str:
    """Classify whether a row can be used as a pyTFA concentration bound."""

    if not model_metabolite_id:
        return "missing_metabolite"
    if mapping_status not in {"mapped", "provided", "", None}:
        return "not_mapped"
    if unit not in SUPPORTED_CONCENTRATION_UNITS:
        return "unsupported_unit"
    if lower is None or upper is None:
        return "missing_bounds"
    if lower <= 0 or upper <= 0:
        return "nonpositive_bounds"
    if lower > upper:
        return "inverted_bounds"
    return "ready"


def summarize_thermo_inputs(bound_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Summarize thermodynamic input readiness by condition."""

    rows = []
    grouped: dict[str, list[dict[str, object]]] = {}
    for row in bound_rows:
        grouped.setdefault(str(row.get("condition") or "default"), []).append(row)

    for condition, items in sorted(grouped.items()):
        ready = [row for row in items if row.get("status") == "ready"]
        mapped = [row for row in items if row.get("mapping_status") in {"mapped", "provided", "", None}]
        invalid_bound_statuses = {"missing_bounds", "nonpositive_bounds", "inverted_bounds"}
        invalid_bounds = [row for row in items if row.get("status") in invalid_bound_statuses]
        unsupported = [row for row in items if row.get("status") == "unsupported_unit"]
        compartments = {str(row.get("compartment")) for row in items if row.get("compartment")}
        rows.append(
            {
                "condition": condition,
                "metabolite_count": len(items),
                "mapped_count": len(mapped),
                "mapped_fraction": _fraction(len(mapped), len(items)),
                "ready_concentration_count": len(ready),
                "ready_concentration_fraction": _fraction(len(ready), len(items)),
                "unsupported_unit_count": len(unsupported),
                "invalid_bound_count": len(invalid_bounds),
                "compartment_count": len(compartments),
                "thermo_readiness": classify_thermo_readiness(len(ready), len(items)),
            }
        )
    return rows


def classify_thermo_readiness(ready_count: int, total_count: int) -> str:
    """Classify whether concentration data are enough for TFA-style workflows."""

    if total_count == 0 or ready_count == 0:
        return "insufficient"
    ready_fraction = _fraction(ready_count, total_count) or 0.0
    if ready_count < 10 or ready_fraction < 0.5:
        return "guidance_only"
    if ready_count < 50:
        return "prototype"
    return "ready"


def build_thermo_recommendations(summary_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Create recommendations for pyTFA/TFA readiness."""

    rows = []
    for summary in summary_rows:
        condition = summary["condition"]
        readiness = summary.get("thermo_readiness")
        if readiness in {"insufficient", "guidance_only", "prototype"}:
            rows.append(
                {
                    "condition": condition,
                    "severity": "high" if readiness == "insufficient" else "medium",
                    "topic": "concentration_coverage",
                    "recommendation": "Use current intracellular metabolomics as thermodynamic anchors; add broader compartment-specific metabolite concentration bounds before treating pyTFA results as production constraints.",
                }
            )
        if int(summary.get("invalid_bound_count") or 0) > 0:
            rows.append(
                {
                    "condition": condition,
                    "severity": "high",
                    "topic": "concentration_bounds",
                    "recommendation": "Fix missing, nonpositive, or inverted concentration bounds before exporting to pyTFA.",
                }
            )
        if int(summary.get("unsupported_unit_count") or 0) > 0:
            rows.append(
                {
                    "condition": condition,
                    "severity": "medium",
                    "topic": "units",
                    "recommendation": "Convert unsupported concentration units to M, mM, uM, or nM before running thermodynamic constraints.",
                }
            )
        if int(summary.get("ready_concentration_count") or 0) >= 50 and not any(row["condition"] == condition for row in rows):
            rows.append(
                {
                    "condition": condition,
                    "severity": "info",
                    "topic": "pyTFA",
                    "recommendation": "Concentration bounds are broad enough for a first pyTFA thermodynamic model build; still inspect thermodynamic database coverage and compartment conventions.",
                }
            )
    return rows


def build_condition_rows(summary_rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """Build package condition metadata."""

    return [
        {
            "condition": row.get("condition", "default"),
            "thermo_readiness": row.get("thermo_readiness", ""),
            "metabolite_count": row.get("metabolite_count", ""),
            "ready_concentration_count": row.get("ready_concentration_count", ""),
            "ready_concentration_fraction": row.get("ready_concentration_fraction", ""),
            "compartment_count": row.get("compartment_count", ""),
        }
        for row in summary_rows
    ]


def build_protocol_template() -> str:
    """Return a Python/pyTFA protocol template for the exported package."""

    return '''"""pyTFA protocol template generated by Omics-GEM Router.

This file is a conservative starting point. It validates the exported package,
loads the source GEM when COBRApy is available, and marks the pyTFA calls that
must be adapted to your local thermodynamic database and pyTFA version.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\\t"))


manifest = json.loads((PACKAGE_DIR / "pytfa_export_manifest.json").read_text(encoding="utf-8"))
bounds = read_tsv(PACKAGE_DIR / "concentration_bounds.tsv")
ready_bounds = [row for row in bounds if row.get("status") == "ready"]

print(f"pyTFA package: {PACKAGE_DIR}")
print(f"Model: {PACKAGE_DIR / 'model.xml'}")
print(f"Ready concentration bounds: {len(ready_bounds)} / {len(bounds)}")

try:
    import cobra
except ImportError:
    cobra = None

try:
    from pytfa import ThermoModel
except ImportError:
    ThermoModel = None

if cobra is None or ThermoModel is None:
    print("Install COBRApy and pyTFA, then adapt the TODO section below.")
    raise SystemExit(0)

model = cobra.io.read_sbml_model(str(PACKAGE_DIR / "model.xml"))

# TODO: Load a pyTFA thermodynamic database matched to the model namespace.
# thermo_data = load_thermo_data(...)
# thermo_model = ThermoModel(thermo_data, model)
# thermo_model.prepare()
# thermo_model.convert()

# TODO: Apply ready concentration bounds. pyTFA setups differ in how they
# expose log-concentration variables, so keep the exported molar and log bounds
# visible while adapting to your local workflow.
# for row in ready_bounds:
#     metabolite_id = row["cobra_metabolite_id"] or row["model_metabolite_id"]
#     lower_ln = float(row["ln_lower_bound"])
#     upper_ln = float(row["ln_upper_bound"])
#     ...

# TODO: Run thermodynamic FBA or variability analysis and write results.
# solution = thermo_model.optimize()
# print(solution.objective_value)

print(f"Loaded model {model.id}; adapt this template to your pyTFA database.")
'''


def build_package_readme(model_id: str, pytfa_target: str) -> str:
    """Return package-local README text."""

    return f"""# pyTFA Export Package

Model: `{model_id}`

Target: `{pytfa_target}`

This package was generated by Omics-GEM Router as a bridge into pyTFA or other
thermodynamic flux analysis workflows. It is not a completed thermodynamic
model; it is a transparent input bundle plus a Python protocol template.

## Files

- `model.xml`: source GEM copied into the package.
- `concentration_bounds.tsv`: condition-wise intracellular concentration bounds.
- `conditions.tsv`: condition and thermodynamic-readiness metadata.
- `thermo_qc_summary.csv`: concentration coverage and bound diagnostics.
- `thermo_qc_recommendations.csv`: data-quality recommendations.
- `protocol_template.py`: Python/pyTFA starting point.
- `pytfa_export_manifest.json`: full file index and unit assumptions.

## Bound Units

The exporter keeps source values and writes converted molar bounds:

- `lower_bound_M` and `upper_bound_M`
- `ln_lower_bound` and `ln_upper_bound`
- `log10_lower_bound` and `log10_upper_bound`

## Before Running pyTFA

1. Install COBRApy and pyTFA in a Python environment.
2. Provide a thermodynamic database compatible with the GEM namespace.
3. Inspect `thermo_qc_summary.csv`; `prototype` means the data are useful as
   concentration anchors, not as comprehensive thermodynamic coverage.
4. Adapt `protocol_template.py` to the local pyTFA concentration-bound API.
"""


def build_export_summary(files: dict[str, str]) -> list[dict[str, object]]:
    """Summarize package files."""

    rows = []
    for role, path in files.items():
        file_path = Path(path)
        if role == "summary":
            exists = True
            size = None
        else:
            exists = file_path.exists()
            size = file_path.stat().st_size if exists else None
        rows.append(
            {
                "file_role": role,
                "path": str(file_path),
                "exists": exists,
                "size_bytes": size,
            }
        )
    return rows


def write_tsv(path: str | Path, rows: list[dict[str, object]]) -> None:
    """Write rows as UTF-8 TSV."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        output.write_text("", encoding="utf-8")
        return
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def cobra_metabolite_id(metabolite_id: str) -> str:
    """Return a COBRApy-style metabolite id from an SBML species id."""

    if not metabolite_id:
        return ""
    return metabolite_id[2:] if metabolite_id.startswith("M_") else metabolite_id


def _fraction(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


def _to_float(value: object) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
