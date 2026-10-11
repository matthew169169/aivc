"""Export GECKO-friendly input packages from prepared enzyme tables."""

from __future__ import annotations

import csv
import shutil
from dataclasses import dataclass
from pathlib import Path

from .constraints import read_csv_records, write_csv, write_json
from .gecko_adapter import build_gecko_adapter_files, normalize_ec_model_mode


PACKAGE_SCHEMA_VERSION = "0.1"


@dataclass(slots=True)
class GeckoExportResult:
    """Summary returned by the GECKO export workflow."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]


def export_gecko_package(
    model_path: str | Path,
    protein_abundance_path: str | Path,
    kcat_priors_path: str | Path,
    enzyme_results_dir: str | Path,
    output_dir: str | Path,
    model_id: str = "iJO1366",
    gecko_target: str = "GECKO 3 full/light ecModel",
    adapter_parameters: dict[str, object] | None = None,
    ec_model_mode: str = "full_ecModel",
) -> GeckoExportResult:
    """Create a portable package for a future GECKO/MATLAB run."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    enzyme_dir = Path(enzyme_results_dir)
    ec_model_mode = normalize_ec_model_mode(ec_model_mode)

    model_target = output / "model.xml"
    shutil.copyfile(model_path, model_target)

    protein_rows = read_csv_records(protein_abundance_path)
    kcat_rows = read_csv_records(kcat_priors_path)
    condition_rows = _read_optional(enzyme_dir / "enzyme_qc_summary.csv")

    files = {
        "model": str(model_target),
        "protein_abundance": str(output / "protein_abundance.tsv"),
        "kcat_table": str(output / "kcat_table.tsv"),
        "conditions": str(output / "conditions.tsv"),
        "reaction_enzyme_capacity": str(output / "reaction_enzyme_capacity.csv"),
        "enzyme_qc_summary": str(output / "enzyme_qc_summary.csv"),
        "enzyme_qc_recommendations": str(output / "enzyme_qc_recommendations.csv"),
        "protocol_template": str(output / "protocol_template.m"),
        "adapter_config": str(output / "gecko_adapter_config.json"),
        "adapter_summary": str(output / "gecko_adapter_summary.csv"),
        "adapter_file": str(output / "generated_adapter.m"),
        "class_adapter_file": "",
        "protocol_config": str(output / "gecko_protocol_config.json"),
        "adapter_readiness": str(output / "gecko_adapter_readiness.csv"),
        "readme": str(output / "README.md"),
        "summary": str(output / "gecko_export_summary.csv"),
        "manifest": str(output / "gecko_export_manifest.json"),
    }

    write_tsv(files["protein_abundance"], build_protein_tsv_rows(protein_rows))
    write_tsv(files["kcat_table"], build_kcat_tsv_rows(kcat_rows))
    write_tsv(files["conditions"], build_condition_rows(condition_rows, protein_rows))
    copy_optional(enzyme_dir / "reaction_enzyme_capacity.csv", files["reaction_enzyme_capacity"])
    copy_optional(enzyme_dir / "enzyme_qc_summary.csv", files["enzyme_qc_summary"])
    copy_optional(enzyme_dir / "enzyme_qc_recommendations.csv", files["enzyme_qc_recommendations"])
    adapter_result = build_gecko_adapter_files(
        output,
        adapter_parameters,
        model_id=model_id,
        model_path=model_target,
        ec_model_mode=ec_model_mode,
    )
    files["class_adapter_file"] = adapter_result.files.get("class_adapter_file", "")
    Path(files["protocol_template"]).write_text(build_protocol_template(), encoding="utf-8")
    Path(files["readme"]).write_text(build_package_readme(model_id, gecko_target, ec_model_mode), encoding="utf-8")

    manifest = {
        "status": "completed",
        "package_schema_version": PACKAGE_SCHEMA_VERSION,
        "model_id": model_id,
        "gecko_target": gecko_target,
        "ec_model_mode": ec_model_mode,
        "adapter_status": adapter_result.status,
        "adapter_message": adapter_result.message,
        "source_files": {
            "model_path": str(model_path),
            "protein_abundance_path": str(protein_abundance_path),
            "kcat_priors_path": str(kcat_priors_path),
            "enzyme_results_dir": str(enzyme_results_dir),
        },
        "unit_assumptions": {
            "protein_abundance": "mmol_per_gDW",
            "kcat": "per_s",
            "capacity": "mmol_per_gDW_per_h",
        },
        "conditions": [row["condition"] for row in build_condition_rows(condition_rows, protein_rows)],
        "adapter_config": adapter_result.config,
        "adapter_readiness": adapter_result.readiness,
        "files": files,
    }
    write_json(files["manifest"], manifest)
    summary_rows = build_export_summary(files)
    write_csv(files["summary"], summary_rows)

    return GeckoExportResult(
        status="completed",
        output_dir=str(output),
        message=f"Exported GECKO input package with {len(summary_rows)} files.",
        files=files,
    )


def build_protein_tsv_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    """Normalize protein abundance rows for GECKO import/adaptation."""

    output = []
    for row in rows:
        output.append(
            {
                "condition": row.get("condition") or row.get("sample") or "default",
                "protein_id": row.get("protein_id", ""),
                "gene_id": row.get("gene_id", ""),
                "model_gene_id": row.get("model_gene_id", ""),
                "abundance_mmol_per_gDW": _to_float(row.get("abundance") or row.get("value")),
                "source_unit": row.get("unit", ""),
                "mapping_status": row.get("status", ""),
                "note": row.get("note", ""),
            }
        )
    return output


def build_kcat_tsv_rows(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    """Normalize kcat priors for GECKO import/adaptation."""

    output = []
    for row in rows:
        output.append(
            {
                "target_id": row.get("target_id", ""),
                "target_type": row.get("target_type", ""),
                "model_reaction_id": row.get("model_target_id", ""),
                "cobra_reaction_id": _cobra_reaction_id(row.get("model_target_id", "")),
                "kcat_per_s": _to_float(row.get("kcat") or row.get("value")),
                "confidence": _to_float(row.get("confidence")),
                "source_tier": row.get("source_tier", ""),
                "kcat_evidence_tier": row.get("kcat_evidence_tier", ""),
                "selection_status": row.get("selection_status", ""),
                "mapping_status": row.get("status", ""),
                "note": row.get("note", ""),
            }
        )
    return output


def build_condition_rows(
    enzyme_summary_rows: list[dict[str, str]],
    protein_rows: list[dict[str, str]],
) -> list[dict[str, object]]:
    """Build package condition metadata."""

    if enzyme_summary_rows:
        return [
            {
                "condition": row.get("condition", "default"),
                "enzyme_readiness": row.get("enzyme_readiness", ""),
                "protein_count": row.get("protein_count", ""),
                "ready_capacity_fraction": row.get("ready_capacity_fraction", ""),
                "mean_kcat_confidence": row.get("mean_kcat_confidence", ""),
            }
            for row in enzyme_summary_rows
        ]

    conditions = sorted({row.get("condition") or row.get("sample") or "default" for row in protein_rows})
    return [
        {
            "condition": condition,
            "enzyme_readiness": "",
            "protein_count": "",
            "ready_capacity_fraction": "",
            "mean_kcat_confidence": "",
        }
        for condition in conditions
    ]


def build_protocol_template() -> str:
    """Return a MATLAB/GECKO protocol template for the exported package."""

    return """% GECKO 3 ecModel protocol template
% Generated by Omics-GEM Router.
%
% This template is intentionally conservative: it stages the package inputs
% and performs the key ModelAdapter setup required by GECKO 3. The actual
% ecModel reconstruction is still opt-in and should be reviewed locally.

packageDir = fileparts(mfilename('fullpath'));
config = jsondecode(fileread(fullfile(packageDir, 'gecko_export_manifest.json')));
protocolConfig = jsondecode(fileread(fullfile(packageDir, 'gecko_protocol_config.json')));

geckoHome = getenv('GECKO_HOME');
if isempty(geckoHome)
    error('Set GECKO_HOME to your local SysBioChalmers/GECKO checkout.');
end
addpath(genpath(geckoHome));

adapterFile = fullfile(packageDir, 'generated_adapter.m');
if ~isfile(adapterFile)
    error('Missing generated GECKO adapter: %s', adapterFile);
end
adapter = ModelAdapterManager.setDefault(adapterFile);
params = adapter.getParameters();

modelFile = fullfile(packageDir, 'model.xml');
proteinFile = fullfile(packageDir, 'protein_abundance.tsv');
kcatFile = fullfile(packageDir, 'kcat_table.tsv');
capacityFile = fullfile(packageDir, 'reaction_enzyme_capacity.csv');

fprintf('GECKO package: %s\\n', packageDir);
fprintf('Model: %s\\n', modelFile);
fprintf('Proteomics: %s\\n', proteinFile);
fprintf('Kcat table: %s\\n', kcatFile);
fprintf('Capacity precheck: %s\\n', capacityFile);
fprintf('Adapter: %s (%s)\\n', class(adapter), protocolConfig.ec_model_mode);
fprintf('bioRxn=%s c_source=%s enzyme_comp=%s\\n', params.bioRxn, params.c_source, params.enzyme_comp);

% Load the conventional GEM. If the adapter convGEM points to model.xml,
% loadConventionalGEM() should use the generated adapter. Otherwise use
% the loader required by your local RAVEN/COBRA setup.
% model = loadConventionalGEM();
% model = importModel(modelFile);

% TODO: Follow the GECKO tutorials/full_ecModel or light_ecModel protocol:
%   1. Convert the GEM to a full or light ecModel according to
%      protocolConfig.ec_model_mode:
%        [ecModel,noUniprot] = makeEcModel(model,false); % full
%        [ecModel,noUniprot] = makeEcModel(model,true);  % light
%   2. Import or map kcat values from kcat_table.tsv into ecModel.ec.kcat.
%   3. Apply kcat constraints with applyKcatConstraints(ecModel).
%   4. Apply measured proteomics/protein pool constraints as appropriate.
%   5. Save with saveEcModel(ecModel, 'ecModel.yml', modelAdapter).
%
% Notes:
%   - protein_abundance.tsv uses mmol_per_gDW.
%   - kcat_table.tsv uses per_s.
%   - reaction_enzyme_capacity.csv is a transparent preflight table, not a
%     GECKO-native data structure.
%   - Full ecModels are the recommended route for measured proteomics.
%   - Light ecModels are faster but do not support measured proteomics
%     integration in the GECKO tutorial workflow.
%   - GECKO 3.2+ protein usage behavior should be checked against your local
%     GECKO version and protocol.
"""


def build_package_readme(model_id: str, gecko_target: str, ec_model_mode: str = "full_ecModel") -> str:
    """Return package-local README text."""

    return f"""# GECKO Export Package

Model: `{model_id}`

Target: `{gecko_target}`

ecModel mode: `{ec_model_mode}`

This package was generated by Omics-GEM Router as a bridge into GECKO. It is
not a completed ecModel; it is a transparent input bundle plus a MATLAB
protocol template.

## Files

- `model.xml`: source GEM copied into the package.
- `protein_abundance.tsv`: condition-wise absolute protein abundance.
- `kcat_table.tsv`: reaction-level kcat priors with confidence/source metadata.
- `reaction_enzyme_capacity.csv`: precomputed capacity table from the router.
- `enzyme_qc_summary.csv`: enzyme-readiness diagnostics.
- `enzyme_qc_recommendations.csv`: data-quality recommendations.
- `conditions.tsv`: condition metadata.
- `gecko_adapter_config.json`: ModelAdapter parameters.
- `generated_adapter.m`: generated MATLAB ModelAdapter class.
- `gecko_adapter_readiness.csv`: required field checks and warnings.
- `gecko_protocol_config.json`: full/light mode and protocol metadata.
- `protocol_template.m`: MATLAB/GECKO starting point.
- `gecko_export_manifest.json`: full file index and unit assumptions.

## Before Running GECKO

1. Install GECKO and RAVEN/MATLAB dependencies.
2. Set `GECKO_HOME` to the local GECKO checkout.
3. Provide or adapt a model adapter for this GEM.
4. Inspect `gecko_adapter_readiness.csv`; `needs_adapter_input` means
   biomass reaction, carbon-source exchange, or enzyme compartment still need
   to be configured before a reliable GECKO probe/run.
5. Inspect `enzyme_qc_summary.csv`; `guidance_only` means the data are useful
   for a prototype or teaching run, not a production ecGEM.

## Full vs Light ecModel

- `full_ecModel` is the recommended route when measured absolute proteomics
  should later constrain enzyme usage.
- `light_ecModel` is a smaller protein-pool route and is useful for a first
  GECKO sanity check, but GECKO tutorials note that measured proteomics
  integration is not supported for light ecModels.
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


def copy_optional(source: str | Path, target: str | Path) -> None:
    """Copy a file if present, otherwise create an empty placeholder."""

    source_path = Path(source)
    target_path = Path(target)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if source_path.exists():
        shutil.copyfile(source_path, target_path)
    else:
        target_path.write_text("", encoding="utf-8")


def _read_optional(path: str | Path) -> list[dict[str, str]]:
    table = Path(path)
    if not table.exists() or table.stat().st_size == 0:
        return []
    return read_csv_records(table)


def _cobra_reaction_id(reaction_id: str) -> str:
    if not reaction_id:
        return ""
    return reaction_id[2:] if reaction_id.startswith("R_") else reaction_id


def _to_float(value: object) -> float | None:
    try:
        if value in {None, ""}:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
