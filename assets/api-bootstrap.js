/* Runtime configuration shared by GitHub Pages and the Python server. */
(function () {
  var override = new URLSearchParams(window.location.search).get("api");
  var base = window.OMICS_GEM_API_BASE;
  if (override) {
    try {
      var url = new URL(override);
      if ((url.protocol === "https:" || url.protocol === "http:") && !url.username && !url.password && !url.search && !url.hash) {
        base = url.href.replace(/\/$/, "");
      }
    } catch (_) { /* Keep the configured default when the URL is invalid. */ }
  }
  if (!base) {
    base = /\.github\.io$/i.test(window.location.hostname)
      ? "https://aivc-tcls.onrender.com"
      : window.location.origin;
  }
  window.OMICS_GEM_API_BASE = base.replace(/\/$/, "");
})();
