# PputidaAcetateGeckoAdapter

- Organism: Pseudomonas putida KT2440
- KEGG organism id: ppu
- Biomass reaction: `R_BIOMASS_KT2440_WT3`
- Carbon source reaction used for adapter template: `R_EX_glc__D_e`
- kcat priors selected: 745
- kcat source mode: local
- GECKO mode: gecko_ready_package

## Case-specific caveats
- Proteomics values are Top3 percent abundance from the paper supplement.
- Protein pool conversion is a proxy unless an absolute protein mass calibration is supplied.
- Acetate and glucose+acetate are case conditions; no uptake bounds are invented here.

## Proteomics mapping
- Protein abundance rows: 34600
- Mapped rows: 12160
- Mapping fraction: 0.351
