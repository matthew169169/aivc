/* File/iframe bridge to the controlled tab's dedicated Python worker. */
"use strict";
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", event => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", event => {
  const url = new URL(event.request.url);
  if (url.origin !== self.location.origin || !(/\/browser-api\/api\//.test(url.pathname) || url.pathname.startsWith("/api/"))) return;
  event.respondWith((async () => {
    let client = event.clientId ? await self.clients.get(event.clientId) : null;
    // Navigating an iframe or download may have no usable clientId. Only a tab
    // that explicitly registered this runtime may answer the request.
    if (!client || client.frameType !== "top-level") {
      const all = await self.clients.matchAll({ type: "window", includeUncontrolled: false });
      client = all.find(candidate => candidate.frameType === "top-level" && candidate.url.startsWith(self.registration.scope));
    }
    if (!client) return new Response("Open the workbench tab to access its browser files.", { status: 503 });
    return new Promise(resolve => {
      const channel = new MessageChannel();
      const timer = setTimeout(() => { channel.port1.close(); resolve(new Response("The browser is busy. Keep the workbench tab open and retry after the calculation finishes.", { status: 504 })); }, 180000);
      channel.port1.onmessage = event => {
        clearTimeout(timer); channel.port1.close();
        if (event.data.error) { resolve(new Response(event.data.error, { status: 500 })); return; }
        const result = event.data.result;
        const bytes = Uint8Array.from(atob(result.body), c => c.charCodeAt(0));
        resolve(new Response(bytes, { status: result.status, headers: result.headers }));
      };
      const headers = {};
      event.request.headers.forEach((value, key) => { headers[key] = value; });
      client.postMessage({ type: "browser-api-request", request: { url: event.request.url, method: event.request.method, headers } }, [channel.port2]);
    });
  })());
});
