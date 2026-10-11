# TROPPO Method Matrix

The FASTcore backend is already executable in this project. This module extends
the TROPPO layer by preparing method-specific inputs for:

- FASTcore
- iMAT
- GIMME
- CORDA

The goal is to make the next algorithm integrations explicit and auditable
without pretending that every method is already equally connected.

## Run

```powershell
python tools\prepare_troppo_methods.py --evidence-mode consensus
```

Default output directory:

```text
examples\ecoli\troppo_method_results
```

Files:

- `troppo_method_run_matrix.csv`: method class, properties class, input strategy, execution status, and entry point.
- `troppo_method_input_summary.csv`: condition/method counts for prepared inputs.
- `troppo_method_reaction_inputs.csv`: reaction-level method inputs.
- `troppo_method_manifest.json`: run manifest.

## Input Strategy

- FASTcore receives core reaction indicators from high evidence.
- iMAT receives a reaction expression vector: `high=2`, `medium=1`, `low=0`, `unknown/no_gpr=-1`.
- GIMME receives the same expression vector and will later need objective constraints for direct execution.
- CORDA receives confidence categories: `high`, `medium`, `negative`, or `unknown`.

Current execution status:

- FASTcore: connected runner.
- iMAT/GIMME/CORDA: input-ready execution pending.

This makes the algorithm expansion concrete: we now have the method-aligned
input tables and can connect direct runners one at a time.
