# Enzyme Constraint Bridge

This module prepares lightweight enzyme-capacity inputs for GECKO,
sMOMENT, AutoPACMEN, ECMpy, or a future full ecGEM backend.

It does not yet rewrite the GEM into an enzyme-constrained model. Instead, it
turns absolute proteomics and kcat priors into auditable reaction capacity
tables and reports whether the data are strong enough for a prototype ecGEM.

## Run

```powershell
python tools\run_enzyme_constraints.py
python tools\build_cobra_report.py
```

Default output:

```text
examples\ecoli\enzyme_results
```

## Inputs

- `protein_abundance.csv`: condition-wise absolute protein abundance in `mmol_per_gDW`.
- `kcat_priors.csv`: reaction-level kcat priors in `per_s` with confidence/source metadata.
- SBML/FBC GPR rules from the GEM.
- Optional `predicted_fluxes.csv` from the COBRA baseline runner.

## Outputs

- `reaction_enzyme_capacity.csv`: condition-wise capacity per kcat-target reaction.
- `enzyme_flux_capacity_check.csv`: optional comparison of predicted FBA flux against capacity.
- `enzyme_qc_summary.csv`: readiness summary by condition.
- `enzyme_qc_recommendations.csv`: guidance for GECKO/sMOMENT readiness.
- `enzyme_constraint_manifest.json`: file and parameter index.

## Notes

Capacity is computed as:

```text
protein_abundance_mmol_per_gDW * kcat_per_s * 3600
```

GPR abundance is approximated with `AND = min` and `OR = max`. This is a
transparent preflight approximation, not a substitute for a curated enzyme
stoichiometry table.
