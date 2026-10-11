# Transcriptomics Flux Methods

This module adds a flux-oriented transcriptomics layer next to the existing
context-model layer.

## Implemented workflows

### E-Flux

Entry point:

```bash
python tools/run_transcriptomics_flux.py
```

Inputs:

- `examples/ecoli/generated_constraints/reaction_expression_evidence.csv`
- `examples/ecoli/generated_constraints/exchange_bounds.csv`
- `examples/ecoli/generated_constraints/flux_validation_targets.csv`
- `examples/ecoli/iJO1366 (1).xml`

Outputs:

- `examples/ecoli/transcriptomics_flux_results/eflux_reaction_bounds.csv`
- `examples/ecoli/transcriptomics_flux_results/eflux_summary.csv`
- `examples/ecoli/transcriptomics_flux_results/eflux_fluxes.csv`
- `examples/ecoli/transcriptomics_flux_results/eflux_flux_validation_comparison.csv`
- `examples/ecoli/transcriptomics_flux_results/eflux_flux_validation_summary.csv`

Implementation detail:

- Reaction expression scores are normalized within each condition.
- Measured GPR reactions receive a capacity fraction between
  `min_expression_fraction` and `1.0`.
- Objective and measured exchange reactions are protected.
- Reactions with no GPR or no measured gene remain unconstrained.

The result should be interpreted as expression-informed flux guidance, not as
absolute flux truth.

### Delta-FBA Lite

The delta layer uses E-Flux condition fluxes as the flux baseline and compares a
reference condition against each target condition.

Outputs:

- `examples/ecoli/transcriptomics_flux_results/delta_fba_expression_deltas.csv`
- `examples/ecoli/transcriptomics_flux_results/delta_fba_flux_deltas.csv`
- `examples/ecoli/transcriptomics_flux_results/delta_fba_measured_delta_comparison.csv`
- `examples/ecoli/transcriptomics_flux_results/delta_fba_summary.csv`

Default reference selection:

1. User-provided `--reference-condition`, when present.
2. `glucose_aerobic`, when present.
3. First available condition.

Why "lite":

- This implementation compares condition-wise transcriptomics-constrained flux
  solutions.
- It does not yet implement the full optimization formulation from specialized
  delta-FBA variants.
- It is useful for directional interpretation and measured-delta validation.

## Pipeline status

The default E. coli pipeline now includes:

```text
transcriptomics_flux
```

The Streamlit Evidence Comparison page and integrated HTML report both display
E-Flux and Delta-FBA Lite summaries.

## Reaction Drill-Down

The Streamlit `Evidence Comparison` page now reuses the existing reaction
lookup box for transcriptomics-flux outputs.

Example queries:

- `R_PFK`
- `R_PYK`
- `R_PDH`
- `R_ICL`
- `R_MALS`
- `R_EX_ac_e`

For a matched reaction, the UI displays:

- E-Flux original bounds and expression-constrained bounds.
- E-Flux predicted flux by condition.
- Delta-FBA Lite expression direction for each condition pair.
- Predicted flux delta and predicted activity direction.
- Measured flux delta residual when fluxomics targets contain the reaction.
