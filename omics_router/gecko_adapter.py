"""GECKO 3 ModelAdapter profile generation and probe helpers."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .constraints import write_csv, write_json


ADAPTER_SCHEMA_VERSION = "0.1"
EC_MODEL_MODES = {"full_ecModel", "light_ecModel"}


@dataclass(slots=True)
class GeckoAdapterBuildResult:
    """Summary returned when generating GECKO adapter files."""

    status: str
    message: str
    files: dict[str, str]
    config: dict[str, Any]
    readiness: dict[str, Any]


@dataclass(slots=True)
class GeckoAdapterProbeResult:
    """Summary returned by the MATLAB/GECKO adapter probe."""

    status: str
    message: str
    files: dict[str, str]


def default_adapter_parameters(
    *,
    model_id: str = "custom_model",
    model_path: str | Path = "model.xml",
    ec_model_mode: str = "full_ecModel",
) -> dict[str, Any]:
    """Return conservative GECKO ModelAdapter defaults."""

    mode = normalize_ec_model_mode(ec_model_mode)
    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "ec_model_mode": mode,
        "adapter_class_name": _safe_matlab_class_name(f"{model_id}_GeckoAdapter"),
        "model_id": model_id or "custom_model",
        "conv_gem_path": str(model_path),
        "organism_name": "unknown organism",
        "kegg_id": "",
        "kegg_gene_id": "kegg",
        "uniprot_type": "taxonomy",
        "uniprot_id": "",
        "uniprot_gene_id_field": "gene_oln",
        "uniprot_reviewed": False,
        "complex_taxonomic_id": "",
        "bio_rxn": "",
        "c_source": "",
        "enzyme_comp": "cytoplasm",
        "sigma": 0.5 if mode == "full_ecModel" else 0.1,
        "Ptot": 0.5,
        "f": 0.5,
        "gR_exp": 0.1,
        "c_UptakeExp": "",
        "spontaneous_reaction_strategy": "rxn_name_contains_spontaneous",
        "spontaneous_reactions_file": "",
        "pseudo_rxns_file": "",
        "custom_kcats_file": "",
        "uniprot_conversion_file": "",
        "proteomics_integration": mode == "full_ecModel",
    }


def normalize_adapter_parameters(
    parameters: dict[str, Any] | None,
    *,
    model_id: str = "custom_model",
    model_path: str | Path = "model.xml",
    ec_model_mode: str = "full_ecModel",
) -> dict[str, Any]:
    """Merge user-provided adapter parameters with safe defaults."""

    raw = dict(parameters or {})
    mode = normalize_ec_model_mode(str(raw.get("ec_model_mode") or ec_model_mode))
    config = default_adapter_parameters(model_id=model_id, model_path=model_path, ec_model_mode=mode)
    for key, value in raw.items():
        if value is None:
            continue
        if key in {"bioRxn", "bio_rxn"}:
            config["bio_rxn"] = str(value).strip()
        elif key in {"cSource", "c_source"}:
            config["c_source"] = str(value).strip()
        elif key in {"enzymeComp", "enzyme_comp"}:
            config["enzyme_comp"] = str(value).strip()
        elif key in {"Ptot", "ptot"}:
            config["Ptot"] = _float_or_text(value)
        elif key in {"gR_exp", "growth_rate"}:
            config["gR_exp"] = _float_or_text(value)
        elif key in {"c_UptakeExp", "c_uptake_exp"}:
            config["c_UptakeExp"] = _float_or_text(value, allow_empty=True)
        elif key in config:
            config[key] = value

    config["ec_model_mode"] = mode
    config["adapter_class_name"] = _safe_matlab_class_name(str(config.get("adapter_class_name") or "OmicsGemGeckoAdapter"))
    config["model_id"] = str(config.get("model_id") or model_id or "custom_model")
    config["conv_gem_path"] = str(config.get("conv_gem_path") or model_path)
    config["organism_name"] = str(config.get("organism_name") or "unknown organism")
    config["kegg_id"] = str(config.get("kegg_id") or "")
    config["kegg_gene_id"] = str(config.get("kegg_gene_id") or "kegg")
    config["uniprot_type"] = "proteome" if str(config.get("uniprot_type")).lower() == "proteome" else "taxonomy"
    config["uniprot_id"] = str(config.get("uniprot_id") or "")
    config["uniprot_gene_id_field"] = str(config.get("uniprot_gene_id_field") or "gene_oln")
    config["uniprot_reviewed"] = _as_bool(config.get("uniprot_reviewed"), default=False)
    config["complex_taxonomic_id"] = _float_or_text(config.get("complex_taxonomic_id"), allow_empty=True)
    config["bio_rxn"] = str(config.get("bio_rxn") or "").strip()
    config["c_source"] = str(config.get("c_source") or "").strip()
    config["enzyme_comp"] = str(config.get("enzyme_comp") or "").strip()
    for key in ("sigma", "Ptot", "f", "gR_exp"):
        config[key] = _float_or_text(config.get(key))
    config["spontaneous_reaction_strategy"] = str(config.get("spontaneous_reaction_strategy") or "rxn_name_contains_spontaneous")
    config["proteomics_integration"] = mode == "full_ecModel"
    return config


def build_gecko_adapter_files(
    output_dir: str | Path,
    parameters: dict[str, Any] | None = None,
    *,
    model_id: str = "custom_model",
    model_path: str | Path = "model.xml",
    ec_model_mode: str = "full_ecModel",
) -> GeckoAdapterBuildResult:
    """Write GECKO adapter config, MATLAB class, protocol config, and readiness rows."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    config = normalize_adapter_parameters(parameters, model_id=model_id, model_path=model_path, ec_model_mode=ec_model_mode)
    files = {
        "adapter_config": str(output / "gecko_adapter_config.json"),
        "adapter_summary": str(output / "gecko_adapter_summary.csv"),
        "adapter_file": str(output / "generated_adapter.m"),
        "class_adapter_file": str(output / f"{config['adapter_class_name']}.m"),
        "protocol_config": str(output / "gecko_protocol_config.json"),
        "adapter_readiness": str(output / "gecko_adapter_readiness.csv"),
    }
    readiness = adapter_readiness(config, output)
    write_json(files["adapter_config"], config)
    write_json(files["protocol_config"], build_protocol_config(config, files))
    adapter_text = build_adapter_matlab(config)
    Path(files["adapter_file"]).write_text(adapter_text, encoding="utf-8")
    Path(files["class_adapter_file"]).write_text(adapter_text, encoding="utf-8")
    write_csv(files["adapter_summary"], adapter_summary_rows(config))
    write_csv(files["adapter_readiness"], readiness["rows"])
    return GeckoAdapterBuildResult(
        status=str(readiness["status"]),
        message=str(readiness["message"]),
        files=files,
        config=config,
        readiness=readiness,
    )


def adapter_readiness(config: dict[str, Any], output_dir: str | Path | None = None) -> dict[str, Any]:
    """Classify adapter readiness without launching MATLAB."""

    missing = []
    for field in ("bio_rxn", "c_source", "enzyme_comp"):
        if not str(config.get(field) or "").strip():
            missing.append(field)
    warnings = []
    if not str(config.get("uniprot_id") or "").strip():
        warnings.append("uniprot_id_missing")
    if not str(config.get("kegg_id") or "").strip():
        warnings.append("kegg_id_missing")
    if config.get("ec_model_mode") == "light_ecModel":
        warnings.append("light_ecModel_no_measured_proteomics_integration")
    optional_files = [
        "spontaneous_reactions_file",
        "pseudo_rxns_file",
        "custom_kcats_file",
        "uniprot_conversion_file",
    ]
    missing_optional = []
    base = Path(output_dir) if output_dir else None
    for key in optional_files:
        value = str(config.get(key) or "").strip()
        if value:
            candidate = Path(value)
            if not candidate.is_absolute() and base is not None:
                candidate = base / value
            if not candidate.exists():
                missing_optional.append(key)
    status = "ready" if not missing else "needs_adapter_input"
    if missing_optional and status == "ready":
        status = "ready_with_warnings"
    message = "GECKO adapter config is ready for MATLAB probe." if status.startswith("ready") else "GECKO adapter is missing required reaction/compartment parameters."
    rows = [
        {"check": "required_field", "item": field, "status": "missing" if field in missing else "ok"}
        for field in ("bio_rxn", "c_source", "enzyme_comp")
    ]
    rows.extend({"check": "warning", "item": item, "status": "warning"} for item in warnings)
    rows.extend({"check": "optional_file", "item": item, "status": "missing"} for item in missing_optional)
    return {
        "status": status,
        "message": message,
        "missing_required": missing,
        "warnings": warnings,
        "missing_optional_files": missing_optional,
        "rows": rows,
    }


def build_protocol_config(config: dict[str, Any], files: dict[str, str]) -> dict[str, Any]:
    """Build a JSON-friendly protocol summary for GECKO runner/UI."""

    return {
        "schema_version": ADAPTER_SCHEMA_VERSION,
        "ec_model_mode": config["ec_model_mode"],
        "adapter_class_name": config["adapter_class_name"],
        "adapter_file": files["adapter_file"],
        "class_adapter_file": files.get("class_adapter_file", ""),
        "recommended_protocol": "full_ecModel/protocol.m" if config["ec_model_mode"] == "full_ecModel" else "light_ecModel/protocol.m",
        "proteomics_integration_supported": bool(config["proteomics_integration"]),
        "requires_manual_confirmation": True,
    }


def build_adapter_matlab(config: dict[str, Any]) -> str:
    """Generate a MATLAB ModelAdapter class from normalized config."""

    cls = str(config["adapter_class_name"])
    tax_id = _matlab_number_or_empty(config.get("complex_taxonomic_id"))
    c_uptake = _matlab_number_or_empty(config.get("c_UptakeExp"))
    reviewed = "true" if config.get("uniprot_reviewed") else "false"
    file_strategy = str(config.get("spontaneous_reaction_strategy") or "rxn_name_contains_spontaneous")
    if file_strategy == "file":
        spontaneous_block = """
            filePath = fullfile(obj.params.path,'spontaneousReactions.tsv');
            if isfile(filePath)
                rxns_tsv = readtable(filePath,'FileType','text','Delimiter','\\t');
                if any(strcmp(rxns_tsv.Properties.VariableNames,'reaction_id'))
                    spontaneousIds = string(rxns_tsv.reaction_id);
                else
                    spontaneousIds = string(rxns_tsv{:,1});
                end
                [spont,~] = ismember(model.rxns,cellstr(spontaneousIds));
                spontRxnNames = model.rxns(spont);
            else
                spont = false(size(model.rxns));
                spontRxnNames = {};
            end
"""
    elif file_strategy == "none":
        spontaneous_block = """
            spont = false(size(model.rxns));
            spontRxnNames = {};
"""
    else:
        spontaneous_block = """
            if isfield(model,'rxnNames')
                spont = contains(lower(model.rxnNames),'spontaneous');
                spontRxnNames = model.rxnNames(spont);
            else
                spont = false(size(model.rxns));
                spontRxnNames = {};
            end
"""
    return f"""classdef {cls} < ModelAdapter
    methods
        function obj = {cls}()
            obj.params.path = fileparts(mfilename('fullpath'));
            obj.params.convGEM = fullfile(obj.params.path,'model.xml');
            obj.params.sigma = {_matlab_number(config.get('sigma'))};
            obj.params.Ptot = {_matlab_number(config.get('Ptot'))};
            obj.params.f = {_matlab_number(config.get('f'))};
            obj.params.gR_exp = {_matlab_number(config.get('gR_exp'))};
            obj.params.c_UptakeExp = {c_uptake};
            obj.params.org_name = '{_matlab_string(config.get('organism_name'))}';
            obj.params.complex.taxonomicID = {tax_id};
            obj.params.kegg.ID = '{_matlab_string(config.get('kegg_id'))}';
            obj.params.kegg.geneID = '{_matlab_string(config.get('kegg_gene_id'))}';
            obj.params.uniprot.type = '{_matlab_string(config.get('uniprot_type'))}';
            obj.params.uniprot.ID = '{_matlab_string(config.get('uniprot_id'))}';
            obj.params.uniprot.geneIDfield = '{_matlab_string(config.get('uniprot_gene_id_field'))}';
            obj.params.uniprot.reviewed = {reviewed};
            obj.params.c_source = '{_matlab_string(config.get('c_source'))}';
            obj.params.bioRxn = '{_matlab_string(config.get('bio_rxn'))}';
            obj.params.enzyme_comp = '{_matlab_string(config.get('enzyme_comp'))}';
        end

        function [spont,spontRxnNames] = getSpontaneousReactions(obj,model)
{spontaneous_block.rstrip()}
        end
    end
end
"""


def adapter_summary_rows(config: dict[str, Any]) -> list[dict[str, object]]:
    """Flatten adapter config for UI/report tables."""

    keys = [
        "ec_model_mode",
        "adapter_class_name",
        "model_id",
        "organism_name",
        "bio_rxn",
        "c_source",
        "enzyme_comp",
        "sigma",
        "Ptot",
        "f",
        "gR_exp",
        "kegg_id",
        "uniprot_type",
        "uniprot_id",
        "uniprot_reviewed",
        "proteomics_integration",
    ]
    return [{"parameter": key, "value": config.get(key, "")} for key in keys]


def run_gecko_adapter_probe(
    package_dir: str | Path,
    output_dir: str | Path,
    *,
    matlab_cmd: str = "matlab",
    gecko_home: str | Path | None = None,
    raven_home: str | Path | None = None,
    solver: str = "",
    timeout_seconds: int = 300,
) -> GeckoAdapterProbeResult:
    """Run an opt-in MATLAB probe for a generated GECKO adapter."""

    package = Path(package_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "summary": str(output / "gecko_adapter_probe_summary.csv"),
        "manifest": str(output / "gecko_adapter_probe_manifest.json"),
        "command": str(output / "gecko_adapter_probe_command.txt"),
        "stdout": str(output / "gecko_adapter_probe_stdout.log"),
        "stderr": str(output / "gecko_adapter_probe_stderr.log"),
    }
    adapter_file = matlab_adapter_file(package)
    config_path = package / "gecko_adapter_config.json"
    gecko_home_text = str(gecko_home or "").strip()
    raven_home_text = str(raven_home or "").strip()
    matlab_path = resolve_matlab_command(matlab_cmd)
    readiness_status = "ready"
    message = "GECKO adapter probe completed."
    if not adapter_file.exists() or not config_path.exists():
        readiness_status = "skipped"
        message = "GECKO adapter files are missing; run adapter preview/export first."
    elif not matlab_path:
        readiness_status = "skipped"
        message = "MATLAB command was not found; adapter probe skipped."
    elif not gecko_home_text or not Path(gecko_home_text).exists():
        readiness_status = "skipped"
        message = "GECKO_HOME is missing or invalid; adapter probe skipped."

    command = build_probe_matlab_command(
        matlab_path or matlab_cmd,
        package_dir=package,
        adapter_file=adapter_file,
        gecko_home=gecko_home_text,
        raven_home=raven_home_text,
        solver=solver,
    )
    Path(files["command"]).write_text(format_command(command), encoding="utf-8")
    if readiness_status != "ready":
        Path(files["stdout"]).write_text("", encoding="utf-8")
        Path(files["stderr"]).write_text("", encoding="utf-8")
        _write_probe_outputs(files, package, adapter_file, readiness_status, message, command, None)
        return GeckoAdapterProbeResult(readiness_status, message, files)

    completed = subprocess.run(
        command,
        cwd=str(package),
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
        check=False,
    )
    Path(files["stdout"]).write_text(completed.stdout or "", encoding="utf-8")
    Path(files["stderr"]).write_text(completed.stderr or "", encoding="utf-8")
    status = "probe_passed" if completed.returncode == 0 else "probe_failed"
    message = "GECKO adapter probe passed." if status == "probe_passed" else "GECKO adapter probe failed."
    _write_probe_outputs(files, package, adapter_file, status, message, command, completed.returncode)
    return GeckoAdapterProbeResult(status, message, files)


def build_probe_matlab_command(
    matlab_cmd: str,
    *,
    package_dir: Path,
    adapter_file: Path,
    gecko_home: str,
    raven_home: str = "",
    solver: str = "",
) -> list[str]:
    """Build a MATLAB command that only probes adapter availability."""

    script = (
        f"geckoHome='{_matlab_string(gecko_home)}'; "
        f"ravenHome='{_matlab_string(raven_home)}'; "
        f"packageDir='{_matlab_string(str(package_dir.resolve()))}'; "
        f"adapterFile='{_matlab_string(str(adapter_file.resolve()))}'; "
        "if isempty(geckoHome) || ~isfolder(geckoHome), error('GECKO_HOME missing'); end; "
        "addpath(genpath(geckoHome)); "
        "if ~isempty(ravenHome), if isfolder(ravenHome), addpath(genpath(ravenHome)); else, error('RAVEN_HOME missing'); end, end; "
        "if exist('GECKOInstaller','class') || exist('GECKOInstaller','file'), try, GECKOInstaller.install; catch ME, fprintf('GECKOInstaller warning: %s\\n',ME.message); end, end; "
        + (f"try, setRavenSolver('{_matlab_string(solver)}'); catch ME, fprintf('solver warning: %s\\n',ME.message); end; " if solver else "")
        + "adapter = ModelAdapterManager.setDefault(adapterFile); "
        "params = adapter.getParameters(); "
        "fprintf('ADAPTER_CLASS=%s\\n',class(adapter)); "
        "fprintf('BIO_RXN=%s\\n',params.bioRxn); "
        "fprintf('C_SOURCE=%s\\n',params.c_source); "
        "fprintf('ENZYME_COMP=%s\\n',params.enzyme_comp); "
        "checks={'makeEcModel','ModelAdapterManager','loadConventionalGEM','saveEcModel','applyKcatConstraints'}; "
        "for i=1:numel(checks), name=checks{i}; fprintf('GECKO_CHECK %s file=%d class=%d\\n',name,exist(name,'file'),exist(name,'class')); end"
    )
    return [matlab_cmd, "-batch", script]


def matlab_adapter_file(package_dir: str | Path) -> Path:
    """Return the MATLAB-loadable adapter class file, with legacy fallback."""

    package = Path(package_dir)
    config_path = package / "gecko_adapter_config.json"
    try:
        import json

        config = json.loads(config_path.read_text(encoding="utf-8"))
        class_name = str(config.get("adapter_class_name") or "").strip()
    except Exception:
        class_name = ""
    if class_name:
        class_path = package / f"{class_name}.m"
        if class_path.exists():
            return class_path
    return package / "generated_adapter.m"


def resolve_matlab_command(matlab_cmd: str) -> str:
    """Resolve a MATLAB command/path when possible."""

    if not matlab_cmd:
        return ""
    candidate = Path(matlab_cmd)
    if candidate.exists():
        return str(candidate)
    return shutil.which(matlab_cmd) or ""


def format_command(command: list[str]) -> str:
    return " ".join(_quote_part(part) for part in command)


def normalize_ec_model_mode(mode: str) -> str:
    text = (mode or "full_ecModel").strip()
    if text in EC_MODEL_MODES:
        return text
    return "light_ecModel" if text.lower().startswith("light") else "full_ecModel"


def _write_probe_outputs(
    files: dict[str, str],
    package: Path,
    adapter_file: Path,
    status: str,
    message: str,
    command: list[str],
    return_code: int | None,
) -> None:
    row = {
        "status": status,
        "message": message,
        "package_dir": str(package),
        "adapter_file": str(adapter_file),
        "return_code": "" if return_code is None else return_code,
    }
    write_csv(files["summary"], [row])
    write_json(files["manifest"], {**row, "command": command, "files": files})
    Path(files["stdout"]).touch(exist_ok=True)
    Path(files["stderr"]).touch(exist_ok=True)


def _safe_matlab_class_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", value or "OmicsGemGeckoAdapter")
    if not cleaned or not re.match(r"[A-Za-z]", cleaned[0]):
        cleaned = f"OmicsGem_{cleaned}"
    return cleaned


def _matlab_string(value: Any) -> str:
    return str(value or "").replace("'", "''").replace("\\", "/")


def _matlab_number(value: Any) -> str:
    try:
        return str(float(value))
    except (TypeError, ValueError):
        return "0"


def _matlab_number_or_empty(value: Any) -> str:
    if value in {"", None}:
        return "[]"
    return _matlab_number(value)


def _float_or_text(value: Any, *, allow_empty: bool = False) -> float | str:
    if allow_empty and (value is None or str(value).strip() == ""):
        return ""
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value or "")


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _quote_part(value: str) -> str:
    if not value:
        return '""'
    if any(ch.isspace() for ch in value) or any(ch in value for ch in {"(", ")", "'"}):
        return '"' + value.replace('"', '\\"') + '"'
    return value
