# Browser mode — free, without an API server

Open [Omics-GEM Studio](https://matthew169169.github.io/aivc/) in a current desktop
Chrome, Edge, Firefox or Safari browser. The GitHub Pages site selects browser
mode automatically. Nothing needs installing, and no Oracle/cloud account is
needed. A dedicated Web Worker runs Python/GLPK using
[Pyodide](https://pyodide.org/en/stable/usage/webworker.html).

## First visit

The first visit downloads about **43 MB** of application/example archives plus
the Python runtime. Scientific packages download on the first calculation.
Loading progress appears at the bottom of the workbench. Keep the tab open while
calculating; large models take time and use your device's CPU and memory.
The top indicator shows **Loading browser**, **Browser ready**, or a browser
startup failure. A failure displays its actual cause and a retry button; it does
not mean you need to configure a remote API server.
Internet access is needed to load the site and its runtime packages. This is not
a promise of complete offline operation.

Uploads and generated results remain in this browser's sandbox. They are not
sent to Render, Oracle, or a computation API. Runtime code and bundled public
example data are downloaded from this site, Pyodide's pinned CDN and PyPI.
Resource Atlas searches use the bundled metadata, rather than live repository
queries. External services need their own network access and compatible inputs.

## Workflows

The worker reuses the application's Python workflows for uploads, projects,
Atlas staging/curation, model generation, comparisons, FBA/pFBA, single-process
FVA, supported omics analyses, network maps, SAMMI exports, reports and ML
profiles/exports. Results and logs retain their actual success/failure status.

The SBML adapter supports steady-state Core Level 2/3, FBC v1/v2 bounds and
objectives, legacy COBRA kinetic-law bounds, GPR rules, notes and annotations.
Its reader is tested against native libSBML/COBRA on all three bundled models;
toy tests also check pFBA, FVA and SBML export/import. Dynamic SBML rules/events,
unsupported required packages and missing objectives are rejected explicitly.
This adapter does **not** provide full libSBML standards validation.

MATLAB, external GECKO/RAVEN, DLKcat, native executables and multiprocessing do
not run inside a browser. Package preparation/export remains available. Their
actual external execution needs a compatible runtime and any applicable
licenses; browser mode does not claim to replace those engines.

## Save, back up and restore

Projects, uploads, curation files, job records and results are stored in
[IndexedDB](https://developer.mozilla.org/en-US/docs/Web/API/IndexedDB_API) for
this browser profile and site origin. Changes are flushed after each mutation.
The app requests persistent storage, but the browser decides whether to grant
it. Clearing site data, private browsing, quota exhaustion, or browser eviction
can remove files. Files do not automatically sync to another device.

Use **Back up projects** in the bottom bar to download a ZIP of the workspace.
Keep a copy outside the browser. **Restore backup** accepts that ZIP and asks
before replacing matching files; back up current work before restoring. A
restore validates paths, CRCs and an uncompressed 768 MB / 25,000 file limit
before writing. Large backups need enough browser memory and storage.

Use one workbench tab at a time. Browsers supporting Web Locks reject a second
writer tab to prevent conflicting changes. Keep the original tab open while
using report previews or downloading generated files, which are served from
that tab's worker through a service worker. Reloading restores saved files;
an interrupted calculation itself is not resumed automatically.

## Optional server mode

An explicit `?api=https%3A%2F%2Fyour-server.example` selects the Python server
instead. Browser/server workspaces are separate; switching modes does not copy
files between them. The server can support additional native dependencies and
larger models when installed. `?mode=browser` explicitly selects the browser
engine on a static deployment containing the browser bundles.

## Development checks

`python tools/build_browser_bundle.py` packages tracked application modules,
public resources and the three named example runs into content-addressed ZIPs.
It never sweeps arbitrary new user runs into the public website. The worker
verifies each archive's SHA-256 before extraction. Rebuild after changing Python
sources or bundled data, and commit the manifest and archives together.

The browser CI starts **only a static HTTP server**, opens Chromium, exercises
the real workbench/solver, checks downloads and a reload, and rejects any request
to the previous Render API. Python tests separately compare scientific results
to the native solver. Runtime package downloads require access to the CDN/PyPI.
