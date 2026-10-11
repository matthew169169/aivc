# GECKO Export Package

This module exports a portable GECKO 3 input package plus a generated
ModelAdapter profile. It does not require MATLAB, RAVEN, or GECKO at export
time. The goal is to make enzyme-constraint inputs and GECKO adapter parameters
auditable before the user chooses to run MATLAB externally.

## Run

```powershell
python tools\export_gecko_inputs.py
python tools\build_cobra_report.py
```

Default output:

```text
examples\ecoli\gecko_package
```

## Package Contents

- `model.xml`: source GEM copied into the package.
- `protein_abundance.tsv`: condition-wise absolute protein abundance.
- `kcat_table.tsv`: reaction-level kcat priors with confidence/source metadata.
- `conditions.tsv`: condition and enzyme-readiness metadata.
- `reaction_enzyme_capacity.csv`: router-generated capacity precheck.
- `enzyme_qc_summary.csv`: enzyme-readiness diagnostics.
- `enzyme_qc_recommendations.csv`: warnings before ecGEM construction.
- `gecko_adapter_config.json`: normalized GECKO ModelAdapter parameters.
- `gecko_adapter_summary.csv`: flat adapter parameter summary.
- `generated_adapter.m`: generated organism/model-specific adapter class draft.
- `gecko_protocol_config.json`: protocol settings consumed by the MATLAB template.
- `gecko_adapter_readiness.csv`: missing-field and compatibility checks.
- `protocol_template.m`: MATLAB/GECKO starting point that calls
  `ModelAdapterManager.setDefault(generated_adapter.m)`.
- `README.md`: package-local instructions.
- `gecko_export_manifest.json`: full file index and unit assumptions.

## Full vs Light ecModel

The export supports two GECKO 3 routes:

- `full_ecModel`: recommended when absolute proteomics and later measured
  protein integration are expected.
- `light_ecModel`: lightweight protein-pool route for faster setup. It is not
  intended for measured proteomics integration.

The mode is recorded in `gecko_adapter_config.json`,
`gecko_protocol_config.json`, and `gecko_export_manifest.json`.

## ModelAdapter Parameters

The generated adapter profile captures the parameters GECKO expects to be
organism/model specific:

- adapter class name
- model id and conventional GEM path
- organism name
- KEGG organism id and gene id field
- UniProt type, id, gene id field, and reviewed-only setting
- Complex Portal taxonomic id
- biomass reaction (`bioRxn`)
- carbon source exchange reaction (`c_source`)
- enzyme compartment (`enzyme_comp`)
- `sigma`, `Ptot`, `f`, `gR_exp`
- optional `c_UptakeExp`
- spontaneous reaction strategy
- optional files: `spontaneousReactions.tsv`, `pseudoRxns.tsv`,
  `customKcats.tsv`, `uniprotConversion.tsv`

Missing required identifiers such as `bioRxn`, `c_source`, or `enzyme_comp`
are reported as `needs_adapter_input` in `gecko_adapter_readiness.csv`.

## API

The React/FastAPI UI uses:

```text
POST /api/runs/{run_id}/gecko/adapter-preview
POST /api/runs/{run_id}/gecko/adapter-probe
GET /api/runs/{run_id}/gecko/status
```

Workflow runs can also pass:

```text
model_generation_methods = ["enzyme_gecko"]
gecko_ec_model_mode = "full_ecModel" | "light_ecModel"
gecko_adapter_parameters = {...}
run_gecko_probe = false
run_gecko_external = false
```

## Design Choice

GECKO is a MATLAB toolbox and depends on local GECKO/RAVEN setup plus a
model-specific adapter. Omics-GEM Studio therefore exports a package first,
then an optional probe or external runner can call MATLAB when the user
provides:

- `GECKO_HOME`
- MATLAB command path
- optional RAVEN path
- solver configuration
- confirmed ModelAdapter parameters

This keeps the main workflow usable even when GECKO is not installed.
