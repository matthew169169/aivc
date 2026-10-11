# Summary Panel Boundary

## Scope

`frontend/src/features/summary/CasePanels.tsx` owns the pure display layer for:

- case readiness strip
- case story card
- case QA matrix
- final readiness decision panel
- report exit shell and report preset grid
- model comparison summary card
- report and traceability file panels
- evidence detail panels for failed jobs, SAMMI checks, and readiness flags
- issue and passed-check panels for Summary readiness

The panels consume props and callbacks from `App.tsx`. They do not fetch, call `ApiClient`, write hash state, or own workflow orchestration.

## Current Components

- `CaseReadinessStrip`: renders the active case readiness ladder and next actions.
- `CaseStoryCard`: renders story title, summary, evidence labels, caveats, and case actions.
- `CaseStoryMetaGrid`: renders default pair, default scope, and display status for the story card.
- `CaseQaMatrixPanel`: renders the cross-stage QA matrix for case display readiness.
- `SummaryDecisionPanel`: renders the final readiness decision, repair feedback, primary and secondary actions, and decision metrics.
- `SummaryReportExitPanel`: renders the report/evidence exit shell, report actions, and report preset cards while accepting nested evidence panels as children.
- `SummaryCompareCard`: renders the selected pair summary, graph/overlay metrics, missing-item guidance, and the Compare navigation action.
- `SummaryFilePanels`: renders report files, key traceability files, and missing-file guidance.
- `SummaryEvidenceDetails`: renders failed jobs, SAMMI checker rows, readiness flags, and related missing guidance.
- `SummaryIssuesPanel`: renders actionable Summary issues, repair buttons, no-issue copy, and passed-check chips.

## State Boundary

`App.tsx` remains responsible for:

- loading case manifest entries
- loading case readiness
- calling prepare-preview and prepare-lite
- loading QA matrix data
- computing the final readiness decision and primary repair/report action
- providing the report build callback, Analysis navigation callback, report presets, and nested report/evidence panels
- computing Summary compare metrics and missing items
- collecting report and key traceability file rows
- providing the API base URL used for file links
- selecting evidence detail rows and columns for failed jobs, SAMMI checks, and readiness flags
- computing Summary issue rules, passed rules, checklist items, and repair actions
- tracking expanded/checking/preparing state

The Summary feature only renders the data snapshot it receives.

## Copy And Encoding

Chinese labels in these panels must be valid UTF-8 source text. If mojibake appears in rendered UI, fix the source text in `CasePanels.tsx`; do not add duplicate workaround labels in `App.tsx`.

## Regression Checks

After changing Summary panels, run:

```powershell
node tools\check_workflow_routing.mjs
cd frontend; npm.cmd run typecheck
cd frontend; npm.cmd run build
node tools\run_browser_smoke_qa.mjs --url http://127.0.0.1:5173 --json-output .tmp\browser_smoke_latest.json --append-log
```

Manual QA should confirm:

- Summary still shows `STAGE 04 / SUMMARY`.
- Case story renders readable Chinese labels.
- Case QA matrix renders case, stage, status, missing items, and next action.
- Check display readiness and Prepare demo artifacts buttons still call the parent callbacks.
