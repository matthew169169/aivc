# Omics-GEM Studio Domain Language

This file records stable project terms used by architecture reviews and refactors.

## Workflow Workspace Terms

- `Case Context`: the pure module that resolves visible case, composite case, stage-to-run mapping, default compare pair, default scope, and report preset decisions.
- `Workflow Runtime`: the pure module that resolves workflow shell state, current stage/module/subview, nav rows, refresh intent, and workflow state payload decisions.
- `Model Compare Workspace`: the pure module that resolves Model Compare pair, scope, graph status/load plan, dashboard metrics, legend semantics, and guidance.
- `Analysis Workspace`: the pure module that resolves Analysis/Summary paper reproduction context, active analysis/summary runs, paper workbench visibility, section status, trigger report preset, and guidance.
- `Resource Lineage Tree`: the pure module that resolves Resource Atlas biological placement, broad resource categories, empty-species visibility, and lineage selection targets.
- `Tree Viewport`: the Resource Atlas renderer/interaction layer that owns SVG/CSS tree layout, blank-canvas pan, zoom buttons, horizontal scroll controls, and right-drawer callbacks.
- `Resource Curation Workspace`: the backend module that owns the persistent Atlas curation draft lifecycle: resource snapshots, versioned curated-file previews, content-bound identifier mapping artifacts, stage eligibility, and atomic Run Package publication. Its interface is typed create/query/execute commands; local files remain an internal seam.
- `Run Package Resolver`: the backend read-only module that resolves package identity, artifact inventory, stage readiness, variant context, and paper/report context for a run package.

## Shewanella Demo Terms

- `Shewanella integrated case`: the visible composite demo case that uses the GECKO run for Input/Model Generator/Model Compare and the transcriptional trigger run for Analysis/Summary/report.
- `Paper Reproduction Workbench`: the Analysis view for the Shewanella transcriptional trigger paper. It displays Growth State Map, Trigger Timeline, GDM-lite, D2T2 reported triggers, and dFBA/glycogen scenario status.
- `Trigger report preset`: the Summary report preset `shewanella_trigger_reproduction_report`; it is selected only for the paper reproduction context.
