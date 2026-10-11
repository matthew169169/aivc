# GEM Model QC

This module runs lightweight, local quality checks before omics integration.
It is meant to answer a practical question: is the model structure healthy
enough for TROPPO, enzyme constraints, thermodynamic constraints, or later
MEMOTE-style validation?

## Run

```powershell
python tools\run_model_qc.py
python tools\build_cobra_report.py
```

The default output directory is:

```text
examples\ecoli\model_qc_results
```

## Outputs

- `model_qc_summary.csv`: one-row model health summary.
- `model_qc_objective_reactions.csv`: objective reaction IDs, coefficients, and bounds.
- `model_qc_compartments.csv`: metabolite annotation completeness by compartment.
- `model_qc_reaction_flags.csv`: per-reaction GPR, exchange, blocked, and mass-balance flags.
- `model_qc_recommendations.csv`: practical warnings before downstream integration.
- `model_qc_manifest.json`: parameters and output file index.

## Interpretation

The `qc_label` column is a compact readiness label:

- `ready`: suitable for downstream modules.
- `usable_with_caution`: acceptable, but report the listed caveats.
- `needs_review`: inspect model structure, bounds, or annotations first.
- `needs_repair`: baseline FBA is not optimal, so fix model/media feasibility before omics integration.

This is not a replacement for MEMOTE. It is a fast local preflight check that
can later sit beside an optional full MEMOTE backend.

## MEMOTE Runner

For a standardized MEMOTE snapshot report, run:

```powershell
python tools\run_memote_external.py
python tools\build_cobra_report.py
```

If MEMOTE is unavailable, the external runner writes a `skipped` manifest and
keeps the rest of the pipeline usable. Details are in
`docs\MEMOTE_EXTERNAL_RUNNER.md`.
