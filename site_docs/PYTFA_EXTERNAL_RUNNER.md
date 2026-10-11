# pyTFA External Runner

This module stages or executes a Python/pyTFA run from an exported
`pytfa_package`.

It is intentionally an external adapter. The router remains usable without
pyTFA or a thermodynamic database. When those tools are unavailable, the runner
writes a `skipped` manifest plus the command it would execute.

## Run

Stage or run with the current environment:

```powershell
python tools\run_pytfa_external.py
python tools\build_cobra_report.py
```

Force a dry run after all readiness checks pass:

```powershell
python tools\run_pytfa_external.py --dry-run --thermo-db D:\data\thermo_data.json
```

Run with explicit Python and thermodynamic database paths:

```powershell
python tools\run_pytfa_external.py --python-cmd D:\envs\pytfa\python.exe --thermo-db D:\data\thermo_data.json
```

The thermodynamic database can also be provided through:

```powershell
$env:PYTFA_THERMO_DB = "D:\data\thermo_data.json"
```

## Requirements For Execution

- A complete `examples\ecoli\pytfa_package`
- Python command available
- COBRApy and pyTFA importable in that Python environment
- `PYTFA_THERMO_DB` set, or `--thermo-db` provided
- A local thermodynamic database and concentration-bound adapter compatible
  with the package's `protocol_template.py`

## Outputs

Default output:

```text
examples\ecoli\pytfa_run_results
```

Files:

- `pytfa_external_run_summary.csv`
- `pytfa_external_run_manifest.json`
- `pytfa_execution_command.txt`
- `pytfa_stdout.log`
- `pytfa_stderr.log`

The first runnable template is conservative and mostly verifies local pyTFA
staging. The next production step is to replace TODO sections in
`protocol_template.py` with a real thermodynamic database loader and
concentration-bound application workflow.
