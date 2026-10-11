# Evidence Mode Comparison

This module compares the downstream inputs created from three evidence modes:

- `transcriptomics`
- `relative_proteomics`
- `consensus`

It is designed to answer a practical question before users over-interpret a
context model: which reactions would change if the downstream reconstruction
used a different omics evidence layer?

## Run

Generate constraints first:

```powershell
python tools\build_ecoli_demo_constraints.py
```

Then build the comparison tables:

```powershell
python tools\compare_evidence_modes.py
```

The default E. coli pipeline runs this step immediately after constraint
generation.

## Streamlit UI

The Streamlit app includes an `Evidence Comparison` tab. It shows:

- condition-level evidence-mode delta counts.
- interpretation notes for missing or conflicting modalities.
- per-mode evidence/core/context-policy summary tables.
- reaction-level deltas filtered by condition and delta status.
- a reaction drill-down for IDs such as `R_ICL`, `R_PFK`, or `R_MALS`.

The drill-down combines evidence mode rows, consensus context knockouts, and
TROPPO selected/removed membership so users can inspect one reaction without
opening several CSV files.

## Condition Interpretation Dashboard

After context feasibility and TROPPO finish, the pipeline builds a condition
dashboard:

```powershell
python tools\build_condition_dashboard.py
```

Outputs:

- `examples\ecoli\interpretation_results\condition_interpretation_summary.csv`
- `examples\ecoli\interpretation_results\condition_interpretation_recommendations.csv`
- `examples\ecoli\interpretation_results\condition_interpretation_manifest.json`

The dashboard assigns each condition one of:

- `red_guidance_only`: sparse coverage, mostly supporting reactions, or zero-objective TROPPO output.
- `yellow_review_needed`: useful but requires review of conflicts, missing modalities, or filtered core candidates.
- `green_usable_with_caution`: internally consistent enough for cautious interpretation.

For the bundled E. coli demo, this should usually remain `red_guidance_only`
because the compact teaching dataset touches only a small fraction of model GPR
reactions.

## Outputs

Default output directory:

```text
examples\ecoli\evidence_mode_results
```

Files:

- `evidence_mode_summary.csv`: per-mode counts for evidence tiers, context policy decisions, measured GPR coverage, and FASTcore core candidates.
- `evidence_mode_delta_summary.csv`: per-condition counts of changed evidence tiers, changed context decisions, changed core membership, and softened conflicts.
- `evidence_mode_reaction_deltas.csv`: reaction-level rows where comparable modes disagree.
- `evidence_mode_recommendations.csv`: short interpretation notes for each condition.
- `evidence_mode_comparison_manifest.json`: run status and file index.

## Interpretation

For the bundled E. coli demo, `acetate_overflow` has reaction-level changes
between transcriptomics and relative proteomics. The consensus mode softens
several high/low conflicts to medium support, including reactions such as
`R_ICL`, `R_MALS`, and `R_PFK`.

For `glucose_aerobic`, relative proteomics is unavailable in the compact demo
dataset. The comparison reports this as coverage missing, rather than treating
missing proteomics as disagreement.
