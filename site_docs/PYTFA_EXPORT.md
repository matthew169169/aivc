# pyTFA Export Package

This module exports a portable input package for a future pyTFA or
thermodynamic flux analysis run.

It does not require pyTFA at export time. The goal is to make intracellular
metabolomics bounds auditable, unit-normalized, and easy to hand off to a local
pyTFA environment with a thermodynamic database.

## Run

```powershell
python tools\export_pytfa_inputs.py
python tools\build_cobra_report.py
```

Default output:

```text
examples\ecoli\pytfa_package
```

## Inputs

- `intracellular_concentrations.csv`: condition-wise intracellular metabolite concentration bounds.
- `model.xml`: the source GEM copied into the export package.

Supported source units are `M`, `mM`, `uM`, and `nM`.

## Package Contents

- `model.xml`: source GEM copied into the package.
- `concentration_bounds.tsv`: condition-wise concentration bounds converted to M.
- `conditions.tsv`: condition and thermodynamic-readiness metadata.
- `thermo_qc_summary.csv`: coverage, mapping, unit, and bound diagnostics.
- `thermo_qc_recommendations.csv`: data-quality recommendations before TFA.
- `protocol_template.py`: conservative Python/pyTFA starting point.
- `README.md`: package-local instructions.
- `pytfa_export_manifest.json`: full file index and unit assumptions.

## Design Choice

pyTFA depends on a compatible thermodynamic database and local model-specific
namespace decisions. The router therefore exports a transparent package first,
then a future external runner can execute pyTFA when the user provides:

- Python environment with COBRApy and pyTFA
- thermodynamic database
- concentration-bound adapter logic for the local pyTFA version
- output folder for thermodynamic FBA/FVA results

The current E. coli demo has useful concentration anchors, but the coverage is
small, so the readiness label is expected to be `prototype` rather than
production `ready`.

## External Runner

After export, stage or execute the package with:

```powershell
python tools\run_pytfa_external.py
```

The external runner checks Python, COBRApy, pyTFA, `PYTFA_THERMO_DB`, and
package completeness. If the environment is incomplete, it writes a skipped
manifest rather than failing the rest of the router workflow.
