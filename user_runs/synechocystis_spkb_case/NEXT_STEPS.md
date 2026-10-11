# User Run Package: synechocystis_spkb_case

Status: `ready_for_review`

This directory contains the staged model, uploaded omics tables,
`input_file_map.csv`, and exported run configuration files.

Recommended next checks:

1. Confirm each omics table role in `input_file_map.csv`.
2. Confirm gene, protein, metabolite, and reaction identifier columns.
3. Review `inputs/condition` if condition setup tables are attached.
4. Add organism-specific mapping tables if the IDs do not match the GEM.
5. Run model QC before applying omics-derived constraints.

The packaged files are intentionally staged before execution so that
column mapping and identifier compatibility can be reviewed first.
