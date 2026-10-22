/* Cloud request handling for the bundled UI. Mutations are never retried. */
(function () {
  "use strict";
  var cache = new Map();
  var inflight = new Map();
  var cacheEpoch = 0;
  var transient = new Set([429, 502, 503, 504]);
  var delay = function (ms) { return new Promise(function (resolve) { setTimeout(resolve, ms); }); };
  var nativeFetch = window.fetch.bind(window);

  function notify(state, message, jobId) {
    if (typeof window.dispatchEvent === "function" && typeof CustomEvent !== "undefined") {
      window.dispatchEvent(new CustomEvent("omics-cloud-status", { detail: { state: state, message: message, jobId: jobId || "" } }));
    }
  }
  function failure(ErrorClass, message, status) {
    var error = new ErrorClass(message, status || 0);
    error.status = status || 0;
    return error;
  }
  async function exchange(url, options, ErrorClass) {
    var isGet = (options.method || "GET") === "GET";
    var attempts = isGet ? 3 : 1;
    for (var attempt = 0; attempt < attempts; attempt++) {
      var controller = new AbortController();
      var timer = setTimeout(function () { controller.abort(); }, 60000);
      try {
        var response = await nativeFetch(url, Object.assign({ credentials: "include" }, options, { signal: controller.signal }));
        if (isGet && transient.has(response.status) && attempt + 1 < attempts) {
          var retryAfter = Number(response.headers.get("Retry-After"));
          await response.text();
          clearTimeout(timer);
          notify("reconnecting", "Reconnecting to the cloud service…");
          await delay(Math.min(10000, Math.max(500 * Math.pow(2, attempt), (retryAfter || 0) * 1000)));
          continue;
        }
        var text = await response.text();
        var data;
        try { data = text ? JSON.parse(text) : {}; }
        catch (_) {
          throw failure(ErrorClass, "The cloud service returned an invalid response. Try refreshing once it is ready.", response.status);
        }
        if (!response.ok) {
          throw failure(ErrorClass, typeof data.detail === "string" ? data.detail : "Cloud request failed (" + response.status + ").", response.status);
        }
        return data;
      } catch (error) {
        if (error.status) { throw error; }
        if (isGet && attempt + 1 < attempts) {
          notify("reconnecting", "Reconnecting to the cloud service…");
          await delay(500 * Math.pow(2, attempt));
          continue;
        }
        notify("offline", "Cloud connection interrupted. Check Jobs before resubmitting an analysis.");
        throw failure(ErrorClass, "Cloud connection interrupted. " + (isGet ? "Please refresh and try again." : "The request may have reached the server. Check Jobs before submitting it again."), 0);
      } finally { clearTimeout(timer); }
    }
  }
  function cacheable(path, options) {
    return (options.method || "GET") === "GET" && /^\/api\/(resources\/(search|species|atlas-summary)(\?|$)|environment\/backend$|case-studies$)/.test(path);
  }
  async function request(base, path, options, ErrorClass) {
    options = options || {};
    ErrorClass = ErrorClass || Error;
    var url = base + path;
    var useCache = cacheable(path, options);
    var cached = cache.get(url);
    if (useCache && cached && cached.expires > Date.now()) { return JSON.parse(cached.value); }
    var isGet = (options.method || "GET") === "GET";
    if (isGet && inflight.has(url)) { return JSON.parse(await inflight.get(url)); }
    var epoch = cacheEpoch;
    var pending = exchange(url, options, ErrorClass);
    var shared = pending.then(function (data) { return JSON.stringify(data); });
    // Always attach a rejection handler; mutations do not have coalesced readers.
    shared.catch(function () {});
    if (isGet) { inflight.set(url, shared); }
    try {
      var data = await pending;
      if (!isGet) { cache.clear(); cacheEpoch++; }
      if (useCache && epoch === cacheEpoch) {
        if (cache.size >= 32) { cache.delete(cache.keys().next().value); }
        cache.set(url, { value: JSON.stringify(data), expires: Date.now() + 15000 });
      }
      if (!isGet && data.job_id && (data.status === "queued" || data.status === "running")) {
        var jobId = data.job_id;
        var started = Date.now();
        var lost = 0;
        while (data.status === "queued" || data.status === "running") {
          notify("working", data.status === "queued" ? "Analysis queued. You can keep browsing." : "Analysis is running in the cloud…", jobId);
          if (Date.now() - started > 3 * 60 * 60 * 1000) {
            throw failure(ErrorClass, "Job " + jobId + " is still running. Open Jobs to check its result.", 408);
          }
          await delay(1500);
          try {
            data = await exchange(base + "/api/jobs/" + encodeURIComponent(jobId), { method: "GET" }, ErrorClass);
            lost = 0;
          } catch (error) {
            if (error.status === 401 || error.status === 403 || error.status === 404 || ++lost >= 4) {
              throw failure(ErrorClass, "Unable to follow job " + jobId + ". Its work may continue on the server; check Jobs before resubmitting. " + error.message, error.status);
            }
            await delay(3000);
          }
        }
        cache.clear(); cacheEpoch++;
      }
      notify("ready", "");
      return data;
    } finally {
      if (isGet && inflight.get(url) === shared) { inflight.delete(url); }
    }
  }
  window.OMICS_GEM_REQUEST = request;
})();
