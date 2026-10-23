/* Enable the same workbench on static hosting, backed by Python in a worker. */
(function () {
  "use strict";
  if (window.OMICS_GEM_EXECUTION_MODE !== "browser") return;
  const scriptURL = new URL(document.currentScript.src);
  const siteRoot = new URL("../", scriptURL);
  const base = window.OMICS_GEM_API_BASE;
  const originalFetch = window.fetch.bind(window);
  const workerURL = new URL("browser-worker.js", scriptURL);
  workerURL.search = scriptURL.search;
  const worker = new Worker(workerURL);
  const pending = new Map();
  let sequence = 0, banner, messageText = "Preparing browser mode…";
  let closed = false;
  function show(message, state) {
    messageText = message;
    if (banner) { banner.textContent = message; banner.dataset.state = state || "loading"; }
  }
  worker.onmessage = event => {
    const message = event.data;
    if (message.type === "status") { show(message.message, message.state); return; }
    const task = pending.get(message.id);
    if (!task) return;
    pending.delete(message.id);
    message.type === "error" ? task.reject(new Error(message.error)) : task.resolve(message.result);
  };
  worker.onerror = error => {
    closed = true;
    const detail = "The browser engine stopped. Reload to recover saved work. " + (error.message || "");
    show(detail, "error");
    for (const task of pending.values()) task.reject(new Error(detail));
    pending.clear();
  };
  function call(request) {
    if (closed) return Promise.reject(new Error("The browser engine stopped. Reload to recover saved work."));
    return new Promise((resolve, reject) => {
      const id = ++sequence;
      pending.set(id, { resolve, reject });
      worker.postMessage({ type: "request", id, request });
    });
  }
  function encode(bytes) {
    let binary = "";
    for (let i = 0; i < bytes.length; i += 32768) binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 32768));
    return btoa(binary);
  }
  function decode(value) { return Uint8Array.from(atob(value), c => c.charCodeAt(0)); }
  function pathFor(url) {
    if (url.href.startsWith(base + "/api/")) return url.href.slice(base.length);
    if (url.origin === siteRoot.origin && url.pathname.startsWith("/api/")) return url.pathname + url.search;
    return null;
  }
  async function execute(request, path) {
    const headers = {};
    request.headers.forEach((value, key) => { if (key !== "content-length" && key !== "host") headers[key] = value; });
    const body = request.method === "GET" || request.method === "HEAD" ? "" : encode(new Uint8Array(await request.arrayBuffer()));
    return call({ path, method: request.method, headers, body });
  }
  window.fetch = async function (input, options) {
    const request = new Request(input, options);
    const path = pathFor(new URL(request.url));
    if (!path) return originalFetch(request);
    if (request.signal.aborted) throw new DOMException("Aborted", "AbortError");
    // Once admitted, a mutation runs exactly once even if the UI timeout expires.
    // It must never be retried as a second calculation.
    const result = await execute(request, path);
    return new Response(decode(result.body), { status: result.status, headers: result.headers });
  };
  async function controls() {
    const bar = document.createElement("aside");
    bar.id = "browser-runtime-status";
    bar.style.cssText = "position:fixed;bottom:10px;left:12px;z-index:99990;max-width:min(750px,90vw);padding:9px 12px;border:1px solid #b9c9d2;border-radius:9px;background:#f6fbff;color:#213b4c;font:12px/1.45 system-ui;box-shadow:0 2px 12px #102f4215;display:flex;gap:12px;align-items:center;flex-wrap:wrap";
    banner = document.createElement("span");
    banner.setAttribute("role", "status");
    banner.setAttribute("aria-live", "polite");
    banner.textContent = messageText;
    const backup = document.createElement("button");
    backup.textContent = "Back up projects";
    const restore = document.createElement("button");
    restore.textContent = "Restore backup";
    const input = document.createElement("input");
    input.type = "file"; input.accept = ".zip"; input.hidden = true;
    for (const button of [backup, restore]) button.style.cssText = "cursor:pointer;background:white;border:1px solid #b9c9d2;border-radius:5px;padding:3px 7px;color:inherit;font:inherit";
    backup.onclick = async () => {
      backup.disabled = true;
      try {
        const response = await window.fetch(base + "/api/browser/backup");
        if (!response.ok) throw new Error(await response.text());
        const url = URL.createObjectURL(await response.blob());
        const link = document.createElement("a");
        link.href = url; link.download = "omics-gem-browser-backup.zip"; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 60000);
      } catch (error) { show("Backup failed: " + error.message, "error"); }
      finally { backup.disabled = false; }
    };
    restore.onclick = () => input.click();
    input.onchange = async () => {
      const file = input.files[0];
      if (!file) return;
      // Restoration is the only user action that can overwrite existing projects.
      if (!window.confirm("Restore this backup? Files with matching names will be replaced. Back up current projects first.")) return;
      restore.disabled = true;
      try {
        const response = await window.fetch(base + "/api/browser/restore", { method: "POST", body: file });
        if (!response.ok) throw new Error((await response.json()).detail);
        window.location.reload();
      } catch (error) { show("Restore failed: " + error.message, "error"); }
      finally { restore.disabled = false; input.value = ""; }
    };
    const note = document.createElement("span");
    note.textContent = "Keep this tab open during calculations. Back up before clearing browser data.";
    note.style.cssText = "width:100%;font-size:11px;color:#526c7b";
    bar.append(banner, backup, restore, input, note);
    document.body.append(bar);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", controls); else controls();
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.addEventListener("message", async event => {
      if (event.data.type !== "browser-api-request" || !event.ports[0]) return;
      try {
        const req = event.data.request;
        const path = pathFor(new URL(req.url));
        if (!path) throw new Error("Unsupported browser file path.");
        const result = await call({ path, method: req.method, headers: req.headers, body: req.body || "" });
        event.ports[0].postMessage({ result });
      } catch (error) { event.ports[0].postMessage({ error: error.message }); }
    });
    const serviceURL = new URL("browser-sw.js", siteRoot);
    serviceURL.search = scriptURL.search;
    navigator.serviceWorker.register(serviceURL, { scope: siteRoot.pathname, updateViaCache: "none" }).catch(error => show("Browser file downloads need service-worker access: " + error.message, "error"));
  } else show("This browser needs service-worker support for report previews and downloads.", "error");
  if (navigator.storage && navigator.storage.persist) navigator.storage.persist().catch(() => {});
  window.OMICS_GEM_BROWSER = { call, base };
})();
