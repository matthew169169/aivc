"""External MATLAB/GECKO runner for exported GECKO packages."""

from __future__ import annotations

import os
import csv
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .constraints import write_csv, write_json

REQUIRED_PACKAGE_FILES = [
    "gecko_export_manifest.json",
    "protocol_template.m",
    "model.xml",
    "protein_abundance.tsv",
    "kcat_table.tsv",
]

SHEWANELLA_EXTERNAL_OUTPUTS = {
    "full_ecmodel": "shewanella_full_ecModel.yml",
    "high_ecmodel": "shewanella_highO2_ecModel.yml",
    "low_ecmodel": "shewanella_lowO2_ecModel.yml",
    "flux_high": "gecko_flux_highO2.csv",
    "flux_low": "gecko_flux_lowO2.csv",
    "flux_delta": "gecko_flux_delta_high_vs_low.csv",
    "enzyme_usage_high": "gecko_enzyme_usage_highO2.csv",
    "enzyme_usage_low": "gecko_enzyme_usage_lowO2.csv",
}


@dataclass(slots=True)
class GeckoRunResult:
    """Summary returned by the external GECKO runner."""

    status: str
    output_dir: str
    message: str
    files: dict[str, str]


def run_gecko_external_workflow(
    package_dir: str | Path,
    output_dir: str | Path,
    matlab_cmd: str = "matlab",
    gecko_home: str | Path | None = None,
    dry_run: bool = False,
    require_gecko: bool = False,
    timeout_seconds: int = 3600,
) -> GeckoRunResult:
    """Run or stage a MATLAB/GECKO execution for an exported package."""

    package = Path(package_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "summary": str(output / "gecko_external_run_summary.csv"),
        "manifest": str(output / "gecko_external_run_manifest.json"),
        "command": str(output / "gecko_execution_command.txt"),
        "stdout": str(output / "gecko_stdout.log"),
        "stderr": str(output / "gecko_stderr.log"),
    }

    package_status = validate_gecko_package(package)
    effective_matlab_cmd = os.environ.get("MATLAB_CMD", "").strip() if matlab_cmd == "matlab" else str(matlab_cmd).strip()
    effective_matlab_cmd = effective_matlab_cmd or "matlab"
    matlab_path = resolve_matlab_command(effective_matlab_cmd)
    resolved_gecko_home = str(gecko_home or os.environ.get("GECKO_HOME", "")).strip()
    gecko_home_exists = bool(resolved_gecko_home and Path(resolved_gecko_home).exists())
    command = build_matlab_batch_command(
        matlab_path or effective_matlab_cmd,
        package / "protocol_template.m",
    )
    Path(files["command"]).write_text(format_command(command), encoding="utf-8")

    readiness = build_run_readiness(package_status, matlab_path, resolved_gecko_home, gecko_home_exists)
    if readiness["status"] != "ready" or dry_run:
        status = "dry_run" if readiness["status"] == "ready" and dry_run else "skipped"
        message = "GECKO external run staged but not executed." if status == "dry_run" else readiness["message"]
        if require_gecko and status == "skipped":
            raise RuntimeError(message)
        write_run_outputs(
            files=files,
            package_dir=package,
            status=status,
            message=message,
            command=command,
            matlab_path=matlab_path,
            gecko_home=resolved_gecko_home,
            gecko_home_exists=gecko_home_exists,
            package_status=package_status,
            return_code=None,
            timeout_seconds=timeout_seconds,
        )
        return GeckoRunResult(status=status, output_dir=str(output), message=message, files=files)

    env = os.environ.copy()
    env["GECKO_HOME"] = resolved_gecko_home
    try:
        completed = subprocess.run(
            command,
            cwd=str(package),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        Path(files["stdout"]).write_text(completed.stdout or "", encoding="utf-8")
        Path(files["stderr"]).write_text(completed.stderr or "", encoding="utf-8")
        status = "completed" if completed.returncode == 0 else "failed"
        message = "GECKO external command completed." if status == "completed" else "GECKO external command failed."
        write_run_outputs(
            files=files,
            package_dir=package,
            status=status,
            message=message,
            command=command,
            matlab_path=matlab_path,
            gecko_home=resolved_gecko_home,
            gecko_home_exists=gecko_home_exists,
            package_status=package_status,
            return_code=completed.returncode,
            timeout_seconds=timeout_seconds,
        )
        return GeckoRunResult(status=status, output_dir=str(output), message=message, files=files)
    except subprocess.TimeoutExpired as exc:
        Path(files["stdout"]).write_text(exc.stdout or "", encoding="utf-8")
        Path(files["stderr"]).write_text(exc.stderr or "", encoding="utf-8")
        message = f"GECKO external command timed out after {timeout_seconds} seconds."
        write_run_outputs(
            files=files,
            package_dir=package,
            status="failed",
            message=message,
            command=command,
            matlab_path=matlab_path,
            gecko_home=resolved_gecko_home,
            gecko_home_exists=gecko_home_exists,
            package_status=package_status,
            return_code=None,
            timeout_seconds=timeout_seconds,
        )
        return GeckoRunResult(status="failed", output_dir=str(output), message=message, files=files)


def run_shewanella_gecko_external_workflow(
    package_dir: str | Path,
    output_dir: str | Path,
    matlab_cmd: str = "matlab",
    gecko_home: str | Path | None = None,
    raven_home: str | Path | None = None,
    solver: str = "",
    dry_run: bool = False,
    timeout_seconds: int = 7200,
    run_full_ecmodel: bool = True,
    run_condition_models: bool = True,
) -> GeckoRunResult:
    """Run the Shewanella full ecModel protocol from a staged GECKO package.

    The original ecShewanella project is not modified. All helper inputs,
    protocol files, logs, and exported model/analysis outputs are written to
    the package/output directories supplied by Omics-GEM Studio.
    """

    package = Path(package_dir)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "summary": str(output / "gecko_external_run_summary.csv"),
        "manifest": str(output / "gecko_external_run_manifest.json"),
        "command": str(output / "gecko_execution_command.txt"),
        "stdout": str(output / "gecko_stdout.log"),
        "stderr": str(output / "gecko_stderr.log"),
        "protocol": str(package / "shewanella_gecko_external_protocol.m"),
        "proteomics_high": str(output / "shewanella_proteomics_highO2.tsv"),
        "proteomics_low": str(output / "shewanella_proteomics_lowO2.tsv"),
        "condition_bounds": str(output / "shewanella_condition_bounds.csv"),
        **{key: str(output / name) for key, name in SHEWANELLA_EXTERNAL_OUTPUTS.items()},
    }
    package_status = validate_gecko_package(package)
    effective_matlab_cmd = os.environ.get("MATLAB_CMD", "").strip() if matlab_cmd == "matlab" else str(matlab_cmd).strip()
    effective_matlab_cmd = effective_matlab_cmd or "matlab"
    matlab_path = resolve_matlab_command(effective_matlab_cmd)
    resolved_gecko_home = str(os.environ.get("GECKO_HOME", "") if gecko_home is None else gecko_home).strip()
    resolved_raven_home = str(os.environ.get("RAVEN_HOME", "") if raven_home is None else raven_home).strip()
    gecko_home_exists = bool(resolved_gecko_home and Path(resolved_gecko_home).exists())
    raven_home_exists = bool(resolved_raven_home and Path(resolved_raven_home).exists())

    prepare_shewanella_external_inputs(package, output, files)
    Path(files["protocol"]).write_text(
        build_shewanella_external_protocol(
            run_full_ecmodel=run_full_ecmodel,
            run_condition_models=run_condition_models,
        ),
        encoding="utf-8",
    )
    command = build_matlab_batch_command(matlab_path or effective_matlab_cmd, files["protocol"])
    Path(files["command"]).write_text(format_command(command), encoding="utf-8")

    readiness = build_run_readiness(package_status, matlab_path, resolved_gecko_home, gecko_home_exists)
    if readiness["status"] == "ready" and resolved_raven_home and not raven_home_exists:
        readiness = {"status": "blocked", "message": f"RAVEN_HOME does not exist: {resolved_raven_home}"}
    if readiness["status"] != "ready" or dry_run:
        status = "dry_run" if readiness["status"] == "ready" and dry_run else "skipped"
        message = "Shewanella GECKO external run staged but not executed." if status == "dry_run" else readiness["message"]
        write_shewanella_run_outputs(
            files=files,
            package_dir=package,
            output_dir=output,
            status=status,
            message=message,
            command=command,
            matlab_path=matlab_path,
            gecko_home=resolved_gecko_home,
            gecko_home_exists=gecko_home_exists,
            raven_home=resolved_raven_home,
            raven_home_exists=raven_home_exists,
            package_status=package_status,
            return_code=None,
            timeout_seconds=timeout_seconds,
        )
        return GeckoRunResult(status=status, output_dir=str(output), message=message, files=files)

    env = os.environ.copy()
    env["GECKO_HOME"] = resolved_gecko_home
    if resolved_raven_home:
        env["RAVEN_HOME"] = resolved_raven_home
    env["GECKO_RUN_OUTPUT_DIR"] = str(output.resolve())
    if solver:
        env["OMICS_GEM_SOLVER"] = solver
    try:
        completed = subprocess.run(
            command,
            cwd=str(package),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        Path(files["stdout"]).write_text(completed.stdout or "", encoding="utf-8", errors="replace")
        Path(files["stderr"]).write_text(completed.stderr or "", encoding="utf-8", errors="replace")
        postprocess_shewanella_outputs(output)
        expected = collect_shewanella_output_status(files)
        if completed.returncode == 0 and all(row["exists"] for row in expected if row["required"]):
            status = "completed"
            message = "Shewanella GECKO external command completed."
        elif completed.returncode == 0:
            status = "completed_with_missing_outputs"
            message = "Shewanella GECKO command completed but some expected outputs are missing."
        else:
            status = "failed"
            message = "Shewanella GECKO external command failed."
        write_shewanella_run_outputs(
            files=files,
            package_dir=package,
            output_dir=output,
            status=status,
            message=message,
            command=command,
            matlab_path=matlab_path,
            gecko_home=resolved_gecko_home,
            gecko_home_exists=gecko_home_exists,
            raven_home=resolved_raven_home,
            raven_home_exists=raven_home_exists,
            package_status=package_status,
            return_code=completed.returncode,
            timeout_seconds=timeout_seconds,
            output_status=expected,
        )
        return GeckoRunResult(status=status, output_dir=str(output), message=message, files=files)
    except subprocess.TimeoutExpired as exc:
        Path(files["stdout"]).write_text(exc.stdout or "", encoding="utf-8", errors="replace")
        Path(files["stderr"]).write_text(exc.stderr or "", encoding="utf-8", errors="replace")
        message = f"Shewanella GECKO external command timed out after {timeout_seconds} seconds."
        write_shewanella_run_outputs(
            files=files,
            package_dir=package,
            output_dir=output,
            status="failed",
            message=message,
            command=command,
            matlab_path=matlab_path,
            gecko_home=resolved_gecko_home,
            gecko_home_exists=gecko_home_exists,
            raven_home=resolved_raven_home,
            raven_home_exists=raven_home_exists,
            package_status=package_status,
            return_code=None,
            timeout_seconds=timeout_seconds,
        )
        return GeckoRunResult(status="failed", output_dir=str(output), message=message, files=files)


def validate_gecko_package(package_dir: str | Path) -> dict[str, object]:
    """Check whether an exported GECKO package has the expected files."""

    package = Path(package_dir)
    missing = [name for name in REQUIRED_PACKAGE_FILES if not (package / name).exists()]
    adapter_config = package / "gecko_adapter_config.json"
    adapter_readiness = package / "gecko_adapter_readiness.csv"
    adapter_file = package / "generated_adapter.m"
    adapter_status = "configured" if adapter_config.exists() and adapter_file.exists() else "adapter_missing"
    if adapter_readiness.exists():
        adapter_status = _adapter_status_from_readiness(adapter_readiness) or adapter_status
    return {
        "package_dir": str(package),
        "exists": package.exists(),
        "missing_files": missing,
        "adapter_status": adapter_status,
        "adapter_config_exists": adapter_config.exists(),
        "adapter_file_exists": adapter_file.exists(),
        "adapter_readiness_exists": adapter_readiness.exists(),
        "status": "ready" if package.exists() and not missing else "missing_files",
    }


def prepare_shewanella_external_inputs(package: Path, output: Path, files: dict[str, str]) -> None:
    """Write condition-specific proteomics and bounds files for MATLAB."""

    run_dir = package.parent
    _copy_shewanella_gecko_database_cache(run_dir, package)
    absolute_path = _first_existing(run_dir / "inputs" / "omics", "absolute_proteomics__*.csv")
    condition_path = _first_existing(run_dir / "inputs" / "condition", "condition_exchange_bounds__*.csv")
    high_rows = _condition_protein_rows(absolute_path, "highO2", preferred_sample="highO2_sample1")
    low_rows = _condition_protein_rows(absolute_path, "lowO2", preferred_sample="lowO2_sample4")
    write_tsv_file(files["proteomics_high"], high_rows, ["genes", "abundances"])
    write_tsv_file(files["proteomics_low"], low_rows, ["genes", "abundances"])
    if condition_path and condition_path.exists():
        shutil.copyfile(condition_path, files["condition_bounds"])
    else:
        Path(files["condition_bounds"]).write_text(
            "condition,reaction_id,lower_bound,upper_bound\n",
            encoding="utf-8",
        )


def _copy_shewanella_gecko_database_cache(run_dir: Path, package: Path) -> None:
    """Copy cached UniProt/KEGG files from the read-only source into the run package."""

    source_manifest = run_dir / "source_manifest.json"
    if not source_manifest.exists():
        return
    try:
        manifest = json.loads(source_manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    files = manifest.get("files", {})
    data_dir = package / "data"
    copied_rows: list[dict[str, str]] = []
    for key, target_name in [("uniprot", "uniprot.tsv"), ("kegg", "kegg.tsv")]:
        source_path = Path(str(files.get(key, {}).get("path", "")))
        target_path = data_dir / target_name
        status = "missing_source"
        if source_path.exists():
            data_dir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, target_path)
            status = "copied"
        copied_rows.append(
            {
                "database": key,
                "source_path": str(source_path) if str(source_path) else "",
                "target_path": str(target_path),
                "status": status,
            }
        )
    if copied_rows:
        write_csv(package / "gecko_database_cache_summary.csv", copied_rows)


def build_shewanella_external_protocol(
    *,
    run_full_ecmodel: bool = True,
    run_condition_models: bool = True,
) -> str:
    """Return the MATLAB protocol for the Shewanella external GECKO run."""

    full_flag = "true" if run_full_ecmodel else "false"
    condition_flag = "true" if run_condition_models else "false"
    return f"""% Shewanella GECKO external protocol generated by Omics-GEM Studio.
% All outputs are written to GECKO_RUN_OUTPUT_DIR; source project folders are not modified.

packageDir = fileparts(mfilename('fullpath'));
outputDir = getenv('GECKO_RUN_OUTPUT_DIR');
if isempty(outputDir)
    outputDir = fullfile(fileparts(packageDir), 'gecko_run_results');
end
if ~exist(outputDir, 'dir'), mkdir(outputDir); end
diary(fullfile(outputDir, 'shewanella_gecko_matlab_diary.log'));
cleanupObj = onCleanup(@() diary('off'));

runFullEcModel = {full_flag};
runConditionModels = {condition_flag};
geckoHome = getenv('GECKO_HOME');
ravenHome = getenv('RAVEN_HOME');
solverName = getenv('OMICS_GEM_SOLVER');
if isempty(geckoHome) || ~isfolder(geckoHome), error('GECKO_HOME missing or invalid'); end
addpath(genpath(geckoHome));
if ~isempty(ravenHome)
    if ~isfolder(ravenHome), error('RAVEN_HOME missing or invalid'); end
    addpath(genpath(ravenHome));
end
if exist('GECKOInstaller','class') || exist('GECKOInstaller','file')
    try, GECKOInstaller.install; catch ME, fprintf('GECKOInstaller warning: %s\\n', ME.message); end
end
if ~isempty(solverName)
    try, setRavenSolver(solverName); catch ME, fprintf('solver warning: %s\\n', ME.message); end
end

adapterConfig = jsondecode(fileread(fullfile(packageDir, 'gecko_adapter_config.json')));
adapterFile = fullfile(packageDir, [char(adapterConfig.adapter_class_name) '.m']);
if ~isfile(adapterFile)
    adapterFile = fullfile(packageDir, 'generated_adapter.m');
end
adapter = ModelAdapterManager.setDefault(adapterFile);
params = adapter.getParameters();
modelFile = fullfile(packageDir, 'model.xml');
kcatFile = fullfile(packageDir, 'kcat_table.tsv');
boundsFile = fullfile(outputDir, 'shewanella_condition_bounds.csv');

fprintf('OMICS_GEM_SHEWANELLA_GECKO_START\\n');
fprintf('packageDir=%s\\n', packageDir);
fprintf('outputDir=%s\\n', outputDir);
fprintf('adapter=%s\\n', class(adapter));

model = load_shewanella_conventional_model(modelFile);
convModelForMapping = model;
try
    convModelForMapping = ravenCobraWrapper(model);
catch ME
    fprintf('ravenCobraWrapper warning: %s\\n', ME.message);
end

if runFullEcModel
    [ecModel, noUniprot] = makeEcModel(model, false);
    fprintf('noUniprot_count=%d\\n', numel(noUniprot));
    ecModel = apply_shewanella_kcats(ecModel, model, kcatFile);
    [ecModel, rxnsMissingGPR, standardMW, standardKcat] = getStandardKcat(ecModel);
    fprintf('rxnsMissingGPR_count=%d standardMW=%g standardKcat=%g\\n', numel(rxnsMissingGPR), standardMW, standardKcat);
    ecModel = applyKcatConstraints(ecModel);
    ecModel = setProtPoolSize(ecModel);
    ecModel = ensure_model_metadata(ecModel, 'shewanella_full_ecModel');
    writeYAMLmodel(ecModel, fullfile(outputDir, 'shewanella_full_ecModel.yml'));
    save(fullfile(outputDir, 'shewanella_full_ecModel.mat'), 'ecModel', 'noUniprot', 'rxnsMissingGPR');
else
    ecModel = readYAMLmodel(fullfile(outputDir, 'shewanella_full_ecModel.yml'));
end

if runConditionModels
    highModel = build_condition_ecmodel(ecModel, convModelForMapping, fullfile(outputDir, 'shewanella_proteomics_highO2.tsv'), boundsFile, 'Taylor_20pctO2_relaxed', params, 'highO2');
    lowModel = build_condition_ecmodel(ecModel, convModelForMapping, fullfile(outputDir, 'shewanella_proteomics_lowO2.tsv'), boundsFile, 'Taylor_8p5pctO2_relaxed', params, 'lowO2');
    highModel = ensure_model_metadata(highModel, 'shewanella_highO2_ecModel');
    lowModel = ensure_model_metadata(lowModel, 'shewanella_lowO2_ecModel');
    writeYAMLmodel(highModel, fullfile(outputDir, 'shewanella_highO2_ecModel.yml'));
    writeYAMLmodel(lowModel, fullfile(outputDir, 'shewanella_lowO2_ecModel.yml'));
    save(fullfile(outputDir, 'shewanella_condition_ecModels.mat'), 'highModel', 'lowModel');
    export_condition_fluxes(highModel, convModelForMapping, fullfile(outputDir, 'gecko_flux_highO2.csv'), fullfile(outputDir, 'gecko_enzyme_usage_highO2.csv'), params);
    export_condition_fluxes(lowModel, convModelForMapping, fullfile(outputDir, 'gecko_flux_lowO2.csv'), fullfile(outputDir, 'gecko_enzyme_usage_lowO2.csv'), params);
end

fprintf('OMICS_GEM_SHEWANELLA_GECKO_DONE\\n');

function model = ensure_model_metadata(model, fallbackId)
    if ~isfield(model, 'id') || isempty(model.id)
        model.id = fallbackId;
    end
    if ~isfield(model, 'description') || isempty(model.description)
        model.description = fallbackId;
    end
    model = sanitize_duplicate_met_ids(model);
end

function model = sanitize_duplicate_met_ids(model)
    if ~isfield(model, 'mets') || isempty(model.mets)
        return;
    end
    seen = containers.Map('KeyType', 'char', 'ValueType', 'double');
    for i = 1:numel(model.mets)
        key = char(model.mets{{i}});
        if isKey(seen, key)
            n = seen(key) + 1;
            seen(key) = n;
            model.mets{{i}} = [char(model.mets{{i}}) '_dup' num2str(n)];
        else
            seen(key) = 1;
        end
    end
    if isfield(model, 'metNames') && isfield(model, 'metComps')
        seenNames = containers.Map('KeyType', 'char', 'ValueType', 'double');
        for i = 1:numel(model.metNames)
            compLabel = '';
            try
                compIdx = model.metComps(i);
                if isfield(model, 'comps') && compIdx > 0 && compIdx <= numel(model.comps)
                    compLabel = char(model.comps{{compIdx}});
                else
                    compLabel = num2str(compIdx);
                end
            catch
                compLabel = '';
            end
            key = [char(model.metNames{{i}}) '[' compLabel ']'];
            if isKey(seenNames, key)
                n = seenNames(key) + 1;
                seenNames(key) = n;
                model.metNames{{i}} = [char(model.metNames{{i}}) '_dup' num2str(n)];
            else
                seenNames(key) = 1;
            end
        end
    end
end

function model = load_shewanella_conventional_model(modelFile)
    try
        model = loadConventionalGEM();
    catch
        try
            model = importModel(modelFile);
        catch
            model = readCbModel(modelFile);
        end
    end
end

function ecModel = apply_shewanella_kcats(ecModel, convModel, kcatFile)
    try, ecModel = getECfromGEM(ecModel); catch ME, fprintf('getECfromGEM warning: %s\\n', ME.message); end
    try
        noEC = cellfun(@isempty, ecModel.ec.eccodes);
        ecModel = getECfromDatabase(ecModel, noEC);
    catch ME
        fprintf('getECfromDatabase warning: %s\\n', ME.message);
    end
    try
        kcatList_fuzzy = fuzzyKcatMatching(ecModel);
    catch ME
        fprintf('fuzzyKcatMatching warning: %s\\n', ME.message);
        kcatList_fuzzy = empty_kcat_list();
    end
    kcatList_external = map_external_kcats(ecModel, convModel, kcatFile);
    fprintf('external_kcat_count=%d\\n', numel([kcatList_external.kcats]));
    if has_kcat_entries(kcatList_external)
        kcatList_merged = mergeDLKcatAndFuzzyKcats(kcatList_external, kcatList_fuzzy);
    else
        kcatList_merged = kcatList_fuzzy;
    end
    if has_kcat_entries(kcatList_merged)
        ecModel = selectKcatValue(ecModel, kcatList_merged);
    else
        fprintf('kcat selection skipped: no custom or fuzzy kcat entries were available.\\n');
    end
end

function yes = has_kcat_entries(kcatList)
    yes = false;
    if isstruct(kcatList) && isfield(kcatList, 'kcats')
        try
            yes = ~isempty([kcatList.kcats]);
        catch
            yes = false;
        end
    end
end

function kcatList = empty_kcat_list()
    kcatList = struct();
    kcatList.genes = {{}};
    kcatList.rxns = {{}};
    kcatList.kcats = [];
    kcatList.source = {{}};
    kcatList.substrates = {{}};
end

function kcatList = map_external_kcats(ecModel, convModel, kcatFile)
    kcatList = empty_kcat_list();
    if ~isfile(kcatFile), return; end
    T = readtable(kcatFile, 'FileType', 'text', 'Delimiter', '\\t', 'TextType', 'string');
    if height(T) == 0, return; end
    convKegg = strings(numel(convModel.rxns),1);
    if isfield(convModel, 'rxnKEGGID')
        convKegg = string(convModel.rxnKEGGID(:));
    end
    genes = {{}};
    rxns = {{}};
    kcats = [];
    sources = {{}};
    substrates = {{}};
    for i = 1:numel(ecModel.ec.rxns)
        baseRxn = regexprep(string(ecModel.ec.rxns{{i}}), '(_REV)?(_EXP_\\d+)?$', '');
        candidates = unique([baseRxn, "R_" + baseRxn, erase(baseRxn, "R_")]);
        match = false(height(T),1);
        if any(strcmp(T.Properties.VariableNames, 'model_reaction_id'))
            match = match | ismember(string(T.model_reaction_id), candidates);
        end
        if any(strcmp(T.Properties.VariableNames, 'cobra_reaction_id'))
            match = match | ismember(string(T.cobra_reaction_id), candidates);
        end
        convIdx = find(strcmp(string(convModel.rxns), baseRxn), 1);
        if ~isempty(convIdx) && convIdx <= numel(convKegg) && strlength(convKegg(convIdx)) > 0
            if any(strcmp(T.Properties.VariableNames, 'target_id'))
                match = match | contains(string(T.target_id), convKegg(convIdx));
            end
        end
        idx = find(match & T.kcat_per_s > 0, 1);
        if ~isempty(idx)
            genes{{end+1,1}} = '';
            rxns{{end+1,1}} = char(ecModel.ec.rxns{{i}});
            kcats(end+1,1) = T.kcat_per_s(idx);
            sources{{end+1,1}} = 'omics_gem_gotenzymes2';
            substrates{{end+1,1}} = '';
        end
    end
    if isempty(kcats)
        kcatList = empty_kcat_list();
    else
        kcatList = struct('genes',{{genes}},'rxns',{{rxns}},'kcats',kcats,'source',{{sources}},'substrates',{{substrates}});
    end
end

function conditionModel = build_condition_ecmodel(ecModel, convModel, proteomicsFile, boundsFile, conditionName, params, label)
    conditionModel = ecModel;
    conditionModel = apply_condition_bounds(conditionModel, boundsFile, conditionName);
    protData = read_condition_proteomics(proteomicsFile);
    for i = 1:numel(protData.uniprotIDs)
        geneID = protData.uniprotIDs{{i}};
        idx = find(strcmp(conditionModel.ec.genes, geneID), 1);
        if ~isempty(idx), protData.uniprotIDs{{i}} = conditionModel.ec.enzymes{{idx}}; end
    end
    try
        conditionModel = fillEnzConcs(conditionModel, protData, 1);
        conditionModel = constrainEnzConcs(conditionModel);
    catch ME
        fprintf('proteomics constraint warning (%s): %s\\n', label, ME.message);
    end
    try, conditionModel = setProtPoolSize(conditionModel); catch ME, fprintf('setProtPoolSize warning: %s\\n', ME.message); end
    try
        sol = solveLP(conditionModel);
        if isempty(sol.x) && exist('flexibilizeEnzConcs', 'file')
            conditionModel = flexibilizeEnzConcs(conditionModel, 0.1, 10);
        end
    catch ME
        fprintf('condition feasibility warning (%s): %s\\n', label, ME.message);
    end
end

function model = apply_condition_bounds(model, boundsFile, conditionName)
    if ~isfile(boundsFile), return; end
    T = readtable(boundsFile, 'TextType', 'string');
    T = T(strcmp(string(T.condition), conditionName), :);
    for i = 1:height(T)
        rxn = char(T.reaction_id(i));
        if ~any(strcmp(model.rxns, rxn)) && startsWith(rxn, 'R_')
            rxn = rxn(3:end);
        end
        if ~any(strcmp(model.rxns, rxn)), continue; end
        if any(strcmp(T.Properties.VariableNames, 'lower_bound')) && ~ismissing(T.lower_bound(i)) && strlength(string(T.lower_bound(i))) > 0
            model = setParam(model, 'lb', rxn, str2double(string(T.lower_bound(i))));
        end
        if any(strcmp(T.Properties.VariableNames, 'upper_bound')) && ~ismissing(T.upper_bound(i)) && strlength(string(T.upper_bound(i))) > 0
            model = setParam(model, 'ub', rxn, str2double(string(T.upper_bound(i))));
        end
    end
end

function protData = read_condition_proteomics(path)
    T = readtable(path, 'FileType', 'text', 'Delimiter', '\\t', 'TextType', 'string');
    protData.uniprotIDs = cellstr(T.genes);
    protData.abundances = T.abundances;
end

function export_condition_fluxes(ecModel, convModel, fluxFile, usageFile, params)
    try
        ecModel = setParam(ecModel, 'obj', params.bioRxn, 1);
    catch
    end
    sol = solveLP(ecModel);
    if isempty(sol.x), error('Condition model was infeasible.'); end
    try
        [mappedFlux, enzUsageFlux, usageEnz] = mapRxnsToConv(ecModel, convModel, sol.x);
        write_flux_csv(fluxFile, convModel.rxns, convModel.rxnNames, mappedFlux);
        write_usage_csv(usageFile, usageEnz, enzUsageFlux);
    catch ME
        fprintf('mapRxnsToConv warning: %s\\n', ME.message);
        names = ecModel.rxns;
        if isfield(ecModel, 'rxnNames'), names = ecModel.rxnNames; end
        write_flux_csv(fluxFile, ecModel.rxns, names, sol.x);
        write_usage_csv(usageFile, {{}}, []);
    end
end

function write_flux_csv(path, rxns, names, fluxes)
    fid = fopen(path, 'w');
    fprintf(fid, 'reaction_id,reaction_name,flux\\n');
    for i = 1:numel(rxns)
        name = '';
        if i <= numel(names), name = names{{i}}; end
        fprintf(fid, '%s,%s,%.15g\\n', escape_csv(rxns{{i}}), escape_csv(name), fluxes(i));
    end
    fclose(fid);
end

function write_usage_csv(path, usageEnz, enzUsageFlux)
    fid = fopen(path, 'w');
    fprintf(fid, 'enzyme_id,usage\\n');
    n = min(numel(usageEnz), numel(enzUsageFlux));
    for i = 1:n
        fprintf(fid, '%s,%.15g\\n', escape_csv(usageEnz{{i}}), enzUsageFlux(i));
    end
    fclose(fid);
end

function text = escape_csv(value)
    text = char(string(value));
    text = strrep(text, '\"', '\"\"');
    if contains(text, ',') || contains(text, '\"')
        text = ['\"' text '\"'];
    end
end
"""


def write_shewanella_run_outputs(
    *,
    files: dict[str, str],
    package_dir: Path,
    output_dir: Path,
    status: str,
    message: str,
    command: list[str],
    matlab_path: str,
    gecko_home: str,
    gecko_home_exists: bool,
    raven_home: str,
    raven_home_exists: bool,
    package_status: dict[str, object],
    return_code: int | None,
    timeout_seconds: int,
    output_status: list[dict[str, object]] | None = None,
) -> None:
    output_status = output_status or collect_shewanella_output_status(files)
    summary = {
        "status": status,
        "message": message,
        "package_dir": str(package_dir),
        "output_dir": str(output_dir),
        "package_status": package_status.get("status", ""),
        "adapter_status": package_status.get("adapter_status", "adapter_missing"),
        "matlab_path": matlab_path,
        "gecko_home": gecko_home,
        "gecko_home_exists": gecko_home_exists,
        "raven_home": raven_home,
        "raven_home_exists": raven_home_exists,
        "return_code": "" if return_code is None else return_code,
        "timeout_seconds": timeout_seconds,
        "expected_output_count": len(output_status),
        "available_output_count": sum(1 for row in output_status if row["exists"]),
    }
    write_csv(files["summary"], [summary])
    write_json(
        files["manifest"],
        {
            **summary,
            "command": command,
            "package_status_detail": package_status,
            "ec_model_mode": _read_ec_model_mode(package_dir),
            "adapter_file": str(package_dir / "generated_adapter.m"),
            "output_status": output_status,
            "files": files,
        },
    )
    Path(files["stdout"]).touch(exist_ok=True)
    Path(files["stderr"]).touch(exist_ok=True)


def collect_shewanella_output_status(files: dict[str, str]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    required_roles = {"full_ecmodel", "high_ecmodel", "low_ecmodel", "flux_high", "flux_low", "flux_delta"}
    for role in SHEWANELLA_EXTERNAL_OUTPUTS:
        path = Path(files[role])
        rows.append(
            {
                "role": role,
                "path": str(path),
                "exists": path.exists() and path.stat().st_size > 0,
                "size_bytes": path.stat().st_size if path.exists() else 0,
                "required": role in required_roles,
            }
        )
    return rows


def postprocess_shewanella_outputs(output: Path) -> None:
    high_path = output / SHEWANELLA_EXTERNAL_OUTPUTS["flux_high"]
    low_path = output / SHEWANELLA_EXTERNAL_OUTPUTS["flux_low"]
    delta_path = output / SHEWANELLA_EXTERNAL_OUTPUTS["flux_delta"]
    if not high_path.exists() or not low_path.exists():
        return
    high = _read_flux_map(high_path)
    low = _read_flux_map(low_path)
    rows = []
    for reaction_id in sorted(set(high) | set(low)):
        high_flux = high.get(reaction_id, 0.0)
        low_flux = low.get(reaction_id, 0.0)
        rows.append(
            {
                "reaction_id": reaction_id,
                "flux_highO2": high_flux,
                "flux_lowO2": low_flux,
                "flux_delta_high_minus_low": high_flux - low_flux,
                "abs_flux_delta": abs(high_flux) - abs(low_flux),
            }
        )
    write_csv(delta_path, rows)


def _read_flux_map(path: Path) -> dict[str, float]:
    rows: dict[str, float] = {}
    if not path.exists() or path.stat().st_size == 0:
        return rows
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        for row in csv.DictReader(handle):
            reaction_id = row.get("reaction_id", "")
            if reaction_id:
                rows[reaction_id] = _to_float(row.get("flux")) or 0.0
    return rows


def _first_existing(root: Path, pattern: str) -> Path | None:
    if not root.exists():
        return None
    for path in sorted(root.glob(pattern)):
        if path.exists():
            return path
    return None


def _condition_protein_rows(path: Path | None, condition: str, *, preferred_sample: str) -> list[dict[str, object]]:
    if not path or not path.exists():
        return []
    with path.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        rows = list(csv.DictReader(handle))
    selected = [row for row in rows if row.get("condition") == condition and row.get("sample") == preferred_sample]
    if not selected:
        selected = [row for row in rows if row.get("condition") == condition]
    merged: dict[str, list[float]] = {}
    for row in selected:
        gene = row.get("gene_id") or row.get("protein_id")
        abundance = _to_float(row.get("mass_abundance_mg_gDCW"))
        if gene and abundance is not None and abundance > 0:
            merged.setdefault(gene, []).append(abundance)
    output = []
    for gene, values in sorted(merged.items()):
        output.append({"genes": gene, "abundances": sum(values) / len(values)})
    return output


def write_tsv_file(path: str | Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _to_float(value: object) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def resolve_matlab_command(matlab_cmd: str) -> str:
    """Resolve a MATLAB command to an executable path when possible."""

    if not matlab_cmd:
        return ""
    candidate = Path(matlab_cmd)
    if candidate.exists():
        return str(candidate)
    resolved = shutil.which(matlab_cmd)
    return resolved or ""


def build_matlab_batch_command(matlab_cmd: str, protocol_path: str | Path) -> list[str]:
    """Build a MATLAB -batch command for the package protocol."""

    protocol = str(Path(protocol_path).resolve()).replace("'", "''")
    return [matlab_cmd, "-batch", f"run('{protocol}')"]


def build_run_readiness(
    package_status: dict[str, object],
    matlab_path: str,
    gecko_home: str,
    gecko_home_exists: bool,
) -> dict[str, str]:
    """Return readiness status and blocking message."""

    if package_status.get("status") != "ready":
        missing = ", ".join(package_status.get("missing_files", []))
        return {"status": "blocked", "message": f"GECKO package is incomplete: {missing}"}
    if not matlab_path:
        return {"status": "blocked", "message": "MATLAB command was not found."}
    if not gecko_home:
        return {"status": "blocked", "message": "GECKO_HOME is not set; skipped external GECKO execution."}
    if not gecko_home_exists:
        return {"status": "blocked", "message": f"GECKO_HOME does not exist: {gecko_home}"}
    return {"status": "ready", "message": "Ready to run MATLAB/GECKO."}


def write_run_outputs(
    *,
    files: dict[str, str],
    package_dir: Path,
    status: str,
    message: str,
    command: list[str],
    matlab_path: str,
    gecko_home: str,
    gecko_home_exists: bool,
    package_status: dict[str, object],
    return_code: int | None,
    timeout_seconds: int,
) -> None:
    """Write summary and manifest files for a GECKO external run."""

    summary = {
        "status": status,
        "message": message,
        "package_dir": str(package_dir),
        "package_status": package_status.get("status", ""),
        "adapter_status": package_status.get("adapter_status", "adapter_missing"),
        "matlab_path": matlab_path,
        "gecko_home": gecko_home,
        "gecko_home_exists": gecko_home_exists,
        "return_code": return_code,
        "timeout_seconds": timeout_seconds,
    }
    write_csv(files["summary"], [summary])
    write_json(
        files["manifest"],
        {
            **summary,
            "command": command,
            "package_status_detail": package_status,
            "ec_model_mode": _read_ec_model_mode(package_dir),
            "adapter_file": str(package_dir / "generated_adapter.m"),
            "files": files,
        },
    )
    Path(files["stdout"]).touch(exist_ok=True)
    Path(files["stderr"]).touch(exist_ok=True)


def format_command(command: list[str]) -> str:
    """Format a command list for display/copying."""

    return " ".join(_quote_part(part) for part in command)


def _quote_part(value: str) -> str:
    if not value:
        return '""'
    if any(ch.isspace() for ch in value) or any(ch in value for ch in {"(", ")", "'"}):
        return '"' + value.replace('"', '\\"') + '"'
    return value


def _adapter_status_from_readiness(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if "needs_adapter_input" in text or ",missing" in text:
        return "needs_adapter_input"
    return "adapter_configured"


def _read_ec_model_mode(package_dir: Path) -> str:
    manifest = package_dir / "gecko_export_manifest.json"
    if not manifest.exists():
        return ""
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return ""
    return str(data.get("ec_model_mode", ""))
