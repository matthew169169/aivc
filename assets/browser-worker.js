/* Dedicated browser Python worker. Requests never leave this worker for a server. */
"use strict";
let python, initialization, science, spreadsheets, storageWarning, engineReady = false, chain = Promise.resolve();
const runtimeBase = new URL("./browser/", self.location.href);
function status(message, state = "loading") {
  if (storageWarning && state === "ready") { message = storageWarning; state = "error"; }
  self.postMessage({ type: "status", message, state, initialized: engineReady });
}
function sync(populate = false) {
  return new Promise((resolve, reject) => python.FS.syncfs(populate, error => error ? reject(error) : resolve()));
}
async function bundle(entry) {
  const url = new URL(entry.file, runtimeBase).href;
  const response = await fetch(url, { cache: "force-cache" });
  if (!response.ok) throw new Error("Browser package download failed (" + response.status + "). Reload to retry.");
  const bytes = new Uint8Array(await response.arrayBuffer());
  const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)), b => b.toString(16).padStart(2, "0")).join("");
  if (hash !== entry.sha256) throw new Error("Browser package integrity check failed. Reload to download a fresh copy.");
  return bytes;
}
async function initialize() {
  if (initialization) return initialization;
  initialization = (async () => {
    if (self.navigator.locks) {
      await new Promise((resolve, reject) => self.navigator.locks.request("omics-gem-browser-workspace", { ifAvailable: true }, lock => {
        if (!lock) { reject(new Error("Another workbench tab is using these projects. Close it, then reload this tab.")); return; }
        resolve();
        return new Promise(() => {});
      }).catch(reject));
    }
    status("Loading browser engine. The first visit downloads Python and examples…");
    const response = await fetch(new URL("manifest.json", runtimeBase), { cache: "no-cache" });
    if (!response.ok) throw new Error("Browser runtime manifest could not be loaded.");
    const manifest = await response.json();
    const indexURL = "https://cdn.jsdelivr.net/pyodide/v" + manifest.pyodide + "/full/";
    importScripts(indexURL + "pyodide.js");
    python = await loadPyodide({ indexURL });
    python.FS.mkdirTree("/app"); python.FS.mkdirTree("/data");
    python.FS.mount(python.FS.filesystems.IDBFS, {}, "/data");
    await sync(true);
    status("Loading the workbench and restoring saved projects…");
    python.unpackArchive(await bundle(manifest.bundles.application), "zip", { extractDir: "/app" });
    if (!python.FS.analyzePath("/data/.browser_examples_initialized.json").exists) {
      status("Preparing the three example projects for first use…");
      python.unpackArchive(await bundle(manifest.bundles.examples), "zip", { extractDir: "/data" });
      python.FS.writeFile("/data/.browser_examples_initialized.json", JSON.stringify({ version: 1 }));
    }
    python.FS.symlink("/data/user_runs", "/app/user_runs");
    python.FS.chdir("/app");
    await python.loadPackage(["micropip", "fastapi", "httpx"]);
    await python.runPythonAsync(`
import sys, os
sys.path.insert(0, '/app')
os.environ['XDG_CACHE_HOME'] = '/tmp/cache'
import micropip
await micropip.install('python-multipart==0.0.20')
from browser import runtime
runtime.APP = runtime.initialize()
`);
    engineReady = true;
    try { await sync(); } catch (error) {
      storageWarning = "Browser storage could not be saved. Keep this tab open and use Back up projects. " + String(error.message || error);
    }
    status("Browser mode ready · files stay in this browser", "ready");
  })();
  return initialization;
}
async function loadScience() {
  if (science) return science;
  science = (async () => {
    status("Loading the browser solver for the first calculation…");
    await python.loadPackage(["numpy", "pandas", "scipy", "swiglpk", "sympy", "rich", "ruamel.yaml"]);
    await python.runPythonAsync(`
await micropip.install(['appdirs==1.4.4', 'depinfo==2.2.0', 'future==1.0.0', 'optlang==1.9.0'])
await micropip.install('cobra==0.31.1', deps=False)
from browser.sbml import install
install()
import cobra
cobra.Configuration().solver = 'glpk'
cobra.Configuration().processes = 1
`);
    status("Browser solver ready", "ready");
  })().catch(error => { science = null; throw error; });
  return science;
}
function needsScience(request) {
  return request.method !== "GET" && /^\/api\/runs\/[^/]+\/(pipeline|workflow\/run|ml-hybrid\/profiles)(\/|$)/.test(request.path);
}
async function loadSpreadsheets() {
  if (!spreadsheets) spreadsheets = python.runPythonAsync("await micropip.install(['openpyxl==3.1.5', 'xlrd==2.0.2'])").catch(error => { spreadsheets = null; throw error; });
  return spreadsheets;
}
async function request(message) {
  await initialize();
  if (message.request.method !== "GET") await loadSpreadsheets();
  if (needsScience(message.request)) await loadScience();
  python.globals.set("browser_request_json", JSON.stringify(message.request));
  status(message.request.method === "GET" ? "Opening project data…" : "Calculating in your browser…", "working");
  try {
    const result = JSON.parse(await python.runPythonAsync("await runtime.handle(browser_request_json)"));
    if (message.request.method !== "GET") {
      status("Saving changes in this browser…", "working");
      try { await sync(); storageWarning = null; } catch (error) {
        storageWarning = "The calculation finished, but browser storage could not be saved. Keep this tab open and use Back up projects. " + String(error.message || error);
      }
    }
    self.postMessage({ type: "response", id: message.id, result });
    status("Browser mode · saved on this device", "ready");
  } finally { python.globals.delete("browser_request_json"); }
}
self.onmessage = event => {
  if (event.data.type !== "request") return;
  const message = event.data;
  chain = chain.then(() => request(message)).catch(error => {
    self.postMessage({ type: "error", id: message.id, error: String(error.message || error) });
    status("Browser engine: " + String(error.message || error), "error");
  });
};
