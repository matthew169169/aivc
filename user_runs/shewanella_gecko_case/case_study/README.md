# Shewanella GECKO Case Study

This run package was generated from the read-only source project:

`D:\MatExt\GECKO\ecShewanella`

## Default Workflow

- Model generation: baseline GEM, E-Flux, GECKO-ready full ecModel, consensus context.
- Analysis: FBA/pFBA, Delta-FBA, evidence comparison, PCA/clustering/LASSO-lite, production/ecFactory-lite readiness.
- GECKO external MATLAB execution is staged but disabled by default. Run the adapter probe before any external GECKO run.

## Key Outputs After Running The Workflow

- `workflow_results/model_variant_registry.csv`
- `gecko_package/generated_adapter.m`
- `gecko_package/protocol_template.m`
- `variant_cobra_results/variant_fba_summary.csv`
- `ml_results/ml_pca_scores.csv`
- `production_results/production_target_ranking.csv`
- `report_results/full_audit_report.html`

## Suggested Visualization Filter

Use this reaction filter for the default production target readiness map:

`R_EX_cpd00029_e0;R_EX_cpd00020_e0;R_EX_cpd00047_e0;R_EX_cpd00050_p0;R_EX_cpd00015_c0;R_EX_cpd00036_e0`

It covers acetate, pyruvate, formate, FMN, FAD, and succinate. Riboflavin and H2 are retained in target discovery as high-value candidates, but are marked as missing exchange/sink support unless you explicitly add demand/sink tests.

## Rebuild Command

```powershell
python tools\prepare_shewanella_case_study.py --source-dir D:\MatExt\GECKO\ecShewanella --output-root D:\generate\user_runs --run-id shewanella_gecko_case --overwrite
```
