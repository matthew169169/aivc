# MEMOTE External Runner

This module stages or executes a MEMOTE snapshot report for a GEM.

It complements the router's lightweight `model_qc` module. Lightweight QC gives
fast local checks that are easy to summarize in CSV; MEMOTE provides a broader
standardized HTML report when the local environment has MEMOTE installed.

## Run

Stage or run with the current environment:

```powershell
python tools\run_memote_external.py
python tools\build_cobra_report.py
```

Force a dry run after readiness checks pass:

```powershell
python tools\run_memote_external.py --dry-run
```

Run with an explicit MEMOTE command:

```powershell
python tools\run_memote_external.py --memote-cmd D:\envs\gem-qc\Scripts\memote.exe
```

## Requirements For Execution

- A GEM file, usually SBML/FBC
- MEMOTE available as a command-line executable
- Solver dependencies configured in the MEMOTE environment

Optional flags are passed through to the generated command:

- `--solver`
- `--solver-timeout`
- repeated `--skip`
- repeated `--exclusive`

## Outputs

Default output:

```text
examples\ecoli\memote_results
```

Files:

- `memote_external_run_summary.csv`
- `memote_external_run_manifest.json`
- `memote_execution_command.txt`
- `memote_stdout.log`
- `memote_stderr.log`
- `memote_snapshot_report.html`

When MEMOTE is not installed, the runner writes `skipped` summary files instead
of failing the rest of the router workflow.
