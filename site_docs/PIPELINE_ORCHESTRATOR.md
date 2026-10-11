# Pipeline Orchestrator

The pipeline orchestrator turns the separate router modules into one auditable
workflow.

It records each step as `completed`, `skipped`, `dry_run`, `failed`,
`input_missing`, or `missing_outputs`. External tools such as GECKO, pyTFA, and
MEMOTE can safely report `skipped` when their local environment is incomplete.

## Run

Run the full E. coli demo pipeline:

```powershell
python tools\run_ecoli_pipeline.py
python tools\build_cobra_report.py
```

Use the Streamlit UI:

```powershell
python -m streamlit run app.py --server.port 8501
```

Open the `Pipeline Console` tab to inspect the latest run, backend
availability, and download the integrated HTML report.

Open the `Evidence Comparison` tab to compare transcriptomics,
relative-proteomics, and consensus evidence modes, and to drill into individual
reactions across context policy and TROPPO outputs.

Preview the command plan without executing steps:

```powershell
python tools\run_ecoli_pipeline.py --dry-run
```

Stop after the first failing step:

```powershell
python tools\run_ecoli_pipeline.py --stop-on-failure
```

## Default Step Order

1. Generate normalized omics constraint tables.
2. Compare transcriptomics, relative-proteomics, and consensus evidence modes.
3. Run lightweight GEM model QC.
4. Stage or run MEMOTE.
5. Run COBRApy FBA, pFBA, and targeted FVA.
6. Run E-Flux and delta-FBA-lite from transcriptomics evidence.
7. Check lightweight context feasibility with consensus multi-omics evidence.
8. Run TROPPO FASTcore with consensus multi-omics evidence when available.
9. Prepare iMAT, GIMME, CORDA, and FASTcore TROPPO inputs.
10. Build condition-level interpretation dashboard.
11. Build enzyme-capacity bridge tables.
12. Export GECKO package.
13. Stage or run GECKO.
14. Export pyTFA package.
15. Stage or run pyTFA.
16. Build the integrated HTML report.

## Outputs

Default output:

```text
examples\ecoli\pipeline_results
```

Files:

- `pipeline_steps.csv`: one row per step, with status, command, logs, and expected outputs.
- `pipeline_backend_status.csv`: backend availability checks.
- `pipeline_run_manifest.json`: full run manifest.
- `logs\*.stdout.log` and `logs\*.stderr.log`: per-step command logs.

The evidence-mode comparison step also writes:

- `examples\ecoli\evidence_mode_results\evidence_mode_summary.csv`
- `examples\ecoli\evidence_mode_results\evidence_mode_delta_summary.csv`
- `examples\ecoli\evidence_mode_results\evidence_mode_reaction_deltas.csv`
- `examples\ecoli\evidence_mode_results\evidence_mode_recommendations.csv`

The TROPPO method matrix step writes:

- `examples\ecoli\troppo_method_results\troppo_method_run_matrix.csv`
- `examples\ecoli\troppo_method_results\troppo_method_input_summary.csv`
- `examples\ecoli\troppo_method_results\troppo_method_reaction_inputs.csv`

The transcriptomics flux step writes:

- `examples\ecoli\transcriptomics_flux_results\eflux_reaction_bounds.csv`
- `examples\ecoli\transcriptomics_flux_results\eflux_summary.csv`
- `examples\ecoli\transcriptomics_flux_results\eflux_flux_validation_summary.csv`
- `examples\ecoli\transcriptomics_flux_results\delta_fba_summary.csv`

The condition interpretation step writes:

- `examples\ecoli\interpretation_results\condition_interpretation_summary.csv`
- `examples\ecoli\interpretation_results\condition_interpretation_recommendations.csv`

## Interpretation

- `completed`: the step ran and wrote expected outputs.
- `skipped`: a step safely degraded, usually because an optional external tool is unavailable.
- `completed_with_skips`: the whole pipeline produced a usable report, but at least one optional backend was skipped.
- `failed`: a required step failed or expected outputs were missing.

This makes the tool useful before every specialized backend is installed, while
still showing exactly what is missing for stricter downstream execution.

## Evidence Mode

The default E. coli pipeline passes `--evidence-mode consensus` into both
context feasibility and TROPPO. The same runners can also be called with
`transcriptomics` or `relative_proteomics` when you want to compare how a single
omics layer changes the downstream context model.
