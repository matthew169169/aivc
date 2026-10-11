# TROPPO FASTcore Backend

This optional backend connects the router's context-specific constraint tables
to TROPPO FASTcore.

## Inputs

Run the constraint builder first:

```powershell
python tools\build_ecoli_demo_constraints.py
```

The FASTcore runner then reads:

- `examples\ecoli\iJO1366 (1).xml`
- `examples\ecoli\generated_constraints\consensus_fastcore_core_reactions.csv`
- `examples\ecoli\generated_constraints\exchange_bounds.csv`
- `examples\ecoli\generated_constraints\multi_omics_consensus_reaction_evidence.csv`

The runner converts the COBRA model into the `S/lb/ub/core` inputs expected by
TROPPO FASTcore. Objective reactions and measured exchange reactions are
protected by default so the reconstructed context model can still be checked by
FBA.

Before calling TROPPO, the runner filters core candidates that cannot carry the
FASTcore threshold flux under the current exchange bounds. This keeps high
expression transport reactions for unavailable substrates from making the hard
core inconsistent. Disable this with `--no-filter-inactive-core` when you want
to inspect raw algorithm behavior.

## Run

```powershell
python tools\run_troppo_fastcore.py
python tools\build_cobra_report.py
```

The default evidence mode is `consensus`, which uses conservative
transcriptomics + relative-proteomics consensus tables. For comparison runs,
use `--evidence-mode transcriptomics` or `--evidence-mode relative_proteomics`.

To prepare iMAT, GIMME, and CORDA inputs from the same evidence mode, run:

```powershell
python tools\prepare_troppo_methods.py --evidence-mode consensus
```

See `docs\TROPPO_METHOD_MATRIX.md` for the method matrix and staged algorithm
inputs.

Use `--require-troppo` if the command should fail when TROPPO is unavailable.
Without that flag, it writes a `skipped` manifest and leaves the rest of the
workflow usable.

## Outputs

The default output directory is:

```text
examples\ecoli\troppo_results
```

Files:

- `troppo_fastcore_summary.csv`: condition-level status, selected reaction count, and FBA feasibility check.
- `troppo_fastcore_core_inputs.csv`: evidence core plus protected objective/exchange reactions passed as FASTcore core.
- `troppo_fastcore_selected_reactions.csv`: reactions retained in each context model.
- `troppo_fastcore_removed_reactions.csv`: reactions excluded from each context model.
- `omics_signal_quality.csv`: condition-level signal diagnostics for gene/reaction coverage and TROPPO specificity.
- `omics_signal_recommendations.csv`: interpretation notes when the data should be treated as sparse or guidance-only evidence.
- `troppo_fastcore_manifest.json`: dependency status, parameters, logs, and output file index.

The feasibility check reports `optimal_zero_objective` when the selected
context model is mathematically feasible but cannot support a positive biomass
objective at the FASTcore threshold. That usually means a later gap-fill or task
protection step is needed, not that the TROPPO run failed.

## Interpreting Omics Signal Quality

The QC layer is deliberately diagnostic rather than corrective. It does not
rescue the model. It reports whether the omics evidence is strong enough to
interpret a context model as phenotype-specific, or whether it is better treated
as directional guidance.

Useful columns:

- `measured_gpr_fraction`: fraction of model GPR reactions touched by measured genes.
- `troppo_filtered_core_fraction`: FASTcore core candidates removed because they cannot carry threshold flux under the current exchange bounds.
- `supporting_fraction`: selected reactions that TROPPO needed for network consistency but were not direct omics core inputs.
- `signal_quality`: `exploratory`, `guidance_only`, `usable_with_caution`, or `strong`.

For the bundled E. coli demo, `signal_quality` is `exploratory`: only about
1.5% of GPR reactions have measured-gene coverage, roughly half of candidate
core reactions are filtered by condition feasibility, and most selected
reactions are supporting reactions. This is expected for a compact teaching
dataset and should not be interpreted as a biological failure.
