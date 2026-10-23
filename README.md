# Omics-GEM Studio

A browser workbench for GEM models, multi-omics evidence, analysis, and reports,
based on the Omics-GEM Studio Windows browser distribution.

- [Public app](https://matthew169169.github.io/aivc/)
- [Browser mode guide](docs/BROWSER_MODE.md)
- [Live API health](https://aivc-tcls.onrender.com/api/health)
- [API documentation](https://aivc-tcls.onrender.com/docs)

The public app defaults to **browser mode**: Python and GLPK run in a Web Worker,
and projects/results are saved in this browser's IndexedDB. No Oracle account,
API hosting, Python installation or local server is required. The first visit
downloads the browser runtime and example data; the solver loads on first use.
Use **Back up projects** to keep a portable copy outside browser storage.

For an optional cloud VM with one website address and persistent storage, see
[the cloud deployment guide](docs/FREE_CLOUD.md). No software needs to run on
your personal device. Docker images are tested on Linux x86 and ARM in CI.

An existing Python API is also available for server mode. Open the app with
`?api=https%3A%2F%2Faivc-tcls.onrender.com` to use that separate server workspace.
Browser mode does not contact Render and does not automatically migrate server data.

## Run locally

Python 3.13 is the tested runtime. Install the solver and spreadsheet dependencies
as well as the API dependencies to enable the Python analysis workflows:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
# Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt -r requirements-optional.txt
python run_local.py
```

Open http://127.0.0.1:8765. The frontend uses the local API automatically.
`OMICS_GEM_HOST` and `OMICS_GEM_PORT` override the bind address and port.
A core-only installation with `requirements.txt` can display existing artifacts,
but cannot recompute COBRA-backed analyses.

## Available workflows

| Function | Runtime or input requirement |
| --- | --- |
| Resource Atlas search, species, filters, details, templates | Bundled resource index and cached metadata |
| Candidate staging and curation workspaces | Local model plus ready evidence, or uploaded curated tables |
| Projects, workspace switching, uploads, imports, archive and restore | Browser storage or writable server workspace |
| Built-in example presets | Shewanella, Putida, and Synechocystis packages are included |
| Baseline model generation, FBA, pFBA, FVA, E-Flux and production analyses | COBRA/GLPK and suitable model/omics/condition inputs |
| Comparison, interactive network maps, SAMMI session export and reports | Staged model and generated or bundled artifacts |
| ML/HYBRID profiles, lightweight benchmarks and exports | Feature matrix and appropriate target column |
| FASTcore execution | Separately installed TROPPO backend |
| Thermodynamic execution | Separately installed pyTFA and a compatible thermodynamic database |
| External GECKO execution | MATLAB, GECKO, RAVEN and a configured solver |
| External DLKcat, MEMOTE and deep-learning integrations | Their separate runtimes and configured input/output locations |
| Native SAMMI application | Optional standalone assets; the built-in interactive viewer and session export work independently |

Browser mode uses a steady-state SBML adapter for Core Level 2/3 with FBC or legacy
COBRA bounds; dynamic SBML constructs and full libSBML validation require a server.
FVA runs in one process. Browser memory limits the size of models and workspaces.

External runtimes are not included in browser mode or the Render deployment. Their readiness and
missing requirements appear in Settings. Generated export packages do not mean
an external computation has run. Infeasible scientific conditions and analysis
failures retain their status labels; they are not replaced with successful or
zero-valued results.

The three bundled run packages include existing comparison, analysis, report and
SAMMI artifacts. Their input maps and exported file links resolve after moving
between Windows, macOS and Linux. Atlas entries use these same bundled inputs.

`POST /api/projects` creates and activates a workspace (optional `name` and
`project_id`). `POST /api/runs/{run_id}/pipeline` executes the same workflow as
`POST /api/runs/{run_id}/workflow/run`, accepting the same optional selections.
Jobs expose their execution result and logs through `/api/jobs`. In server mode computations
return HTTP 202 and execute in a bounded background queue; the browser follows
the job until it finishes. Duplicate submissions for an active run are rejected.
Jobs interrupted by a server restart are marked failed with a retry explanation.
Set `OMICS_GEM_JOB_MODE=inline` only for scripts that require synchronous results. The case menu
uses the latest saved readiness check; opening the case readiness endpoint runs
the detailed validation and refreshes that result.

## Deploy the backend

[Deploy on Render](https://render.com/deploy?repo=https://github.com/matthew169169/aivc)
using `render.yaml`. The build installs both dependency files and fails if the
analysis dependencies cannot be installed. Render checks `/api/health`.

A new Render service can receive a different hostname. Open the Pages app with
an explicit API address to select server mode:

```text
https://matthew169169.github.io/aivc/?api=https%3A%2F%2Fyour-service.onrender.com
```

The override applies to that page load; stale saved API addresses are not reused.
Keep `OMICS_GEM_ALLOWED_ORIGINS=https://matthew169169.github.io` on the backend.
The existing deployed service is `aivc-tcls.onrender.com`.

Render's free filesystem is temporary. Uploaded data, new projects, jobs and
analysis outputs can be lost on restart or redeploy; use persistent storage for
work that must survive. A sleeping free service may take time to respond.

Shared-password authentication is off by default for this public demonstration.
To enable it, configure `OMICS_GEM_AUTH_ENABLED=true`,
`OMICS_GEM_PASSWORD_HASH`, and `OMICS_GEM_SESSION_SECRET`.

## Checks

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
node --test tests/test_api_bootstrap.cjs tests/test_api_transport.cjs
```

GitHub Actions runs the checks on Linux and Windows with Python 3.13. Tests use
temporary workspaces and cover uploads, moved Windows packages, an actual FBA
solve, omics mapping, job statuses, maps/SAMMI export, reports, ML exports,
projects, Atlas staging, curation, examples and file-access boundaries.
