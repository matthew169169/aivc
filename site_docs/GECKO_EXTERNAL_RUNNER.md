# GECKO External Runner

This module stages or executes a MATLAB/GECKO run from an exported
`gecko_package`.

It is intentionally an external adapter. Omics-GEM Studio remains usable
without MATLAB, RAVEN, solver-specific setup, or GECKO. When those tools are
unavailable, the runner writes a `skipped` manifest plus the command it would
execute.

## Run

Stage or run with the current environment:

```powershell
python tools\run_gecko_external.py
python tools\build_cobra_report.py
```

Force a dry run:

```powershell
python tools\run_gecko_external.py --dry-run
```

Run with explicit GECKO and MATLAB paths:

```powershell
python tools\run_gecko_external.py --gecko-home D:\tools\GECKO --matlab-cmd D:\Matlab\bin\matlab.exe
```

## Adapter Probe

Before a real external run, the API can run a lightweight GECKO adapter probe:

```text
POST /api/runs/{run_id}/gecko/adapter-probe
```

The probe checks:

- MATLAB command availability
- `GECKO_HOME`
- optional RAVEN path
- generated `generated_adapter.m`
- `ModelAdapterManager.setDefault(adapterFile)`
- key GECKO functions such as `makeEcModel`

Probe output is written into `gecko_run_results`:

- `gecko_adapter_probe_manifest.json`
- `gecko_adapter_probe_summary.csv`
- `gecko_adapter_probe_command.txt`
- `gecko_adapter_probe_stdout.log`
- `gecko_adapter_probe_stderr.log`

If MATLAB or GECKO is missing, the probe returns `skipped / missing_matlab` or
`skipped / missing_gecko_home` instead of failing the whole workflow.

## Requirements For Execution

- A complete `gecko_package`
- `generated_adapter.m`
- `gecko_adapter_config.json`
- `gecko_adapter_readiness.csv` without unresolved required fields
- MATLAB command available
- `GECKO_HOME` set, or `--gecko-home` provided
- local GECKO/RAVEN installation
- solver setup compatible with the selected model

## Outputs

Default output:

```text
examples\ecoli\gecko_run_results
```

Files:

- `gecko_external_run_summary.csv`
- `gecko_external_run_manifest.json`
- `gecko_execution_command.txt`
- `gecko_stdout.log`
- `gecko_stderr.log`

The external runner records adapter status, ecModel mode, MATLAB command,
GECKO path, and package completeness. A real GECKO execution still requires
the user to confirm organism-specific ModelAdapter settings.
