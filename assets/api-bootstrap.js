/* Runtime configuration shared by GitHub Pages and the Python server. */
(function () {
  var override = new URLSearchParams(window.location.search).get("api");
  var base = window.OMICS_GEM_API_BASE;
  var requestedMode = new URLSearchParams(window.location.search).get("mode");
  if (override) {
    try {
      var url = new URL(override);
      if ((url.protocol === "https:" || url.protocol === "http:") && !url.username && !url.password && !url.search && !url.hash) {
        base = url.href.replace(/\/$/, "");
      }
    } catch (_) { /* Keep the configured default when the URL is invalid. */ }
  }
  var browserMode = requestedMode === "browser" || (!base && /\.github\.io$/i.test(window.location.hostname));
  if (browserMode) {
    var source = typeof document !== "undefined" && document.currentScript ? document.currentScript.src : window.location.origin + "/aivc/assets/api-bootstrap.js";
    base = new URL("../browser-api", source).href;
  } else if (!base) base = window.location.origin;
  window.OMICS_GEM_EXECUTION_MODE = browserMode ? "browser" : "server";
  window.OMICS_GEM_API_BASE = base.replace(/\/$/, "");
})();
