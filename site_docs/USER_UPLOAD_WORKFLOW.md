# User Upload Workflow

The Streamlit app now supports a staging workflow for custom user data.

## What It Does

The `Data Check` tab still inspects uploaded model and omics tables. It now also
adds a `User Upload Workflow` section that lets the user:

1. Review inferred omics roles for each uploaded table.
2. Override the role with a selectbox.
3. Ignore files that should not enter the run package.
4. Create a reusable package under `user_runs/<run_id>`.

## Package Layout

Each package contains:

```text
user_runs/<run_id>/
  inputs/
    model/
    omics/
  input_file_map.csv
  upload_manifest.json
  run_config.json
  run_config.yaml
  NEXT_STEPS.md
```

## Why This Is Staged Before Execution

User-uploaded data often needs identifier and column mapping before constraint
generation:

- gene IDs may not match the GEM gene IDs;
- protein IDs may require a UniProt or gene mapping table;
- metabolite IDs may require exchange or compartment mapping;
- reaction IDs in fluxomics may need SBML `R_` aliases;
- organism-specific model formats may need MEMOTE/COBRA parsing first.

The package gives users a stable handoff point before applying model-altering
methods such as context extraction, E-Flux, GECKO, or pyTFA.

## Core Module

The workflow lives in:

```text
omics_router/upload_workflow.py
```

Main API:

```python
stage_user_run_package(...)
infer_omics_role_candidates(...)
choose_default_role(...)
```
