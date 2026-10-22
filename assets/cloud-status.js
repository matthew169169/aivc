/* Connection and background-job feedback without blocking the workbench. */
(function () {
  var banner;
  window.addEventListener("omics-cloud-status", function (event) {
    if (!banner) {
      banner = document.createElement("div");
      banner.setAttribute("role", "status");
      banner.setAttribute("aria-live", "polite");
      banner.style.cssText = "position:fixed;bottom:18px;right:18px;z-index:10000;max-width:420px;padding:12px 16px;border-radius:10px;background:#17252a;color:white;font:14px/1.5 system-ui;box-shadow:0 3px 18px #0003";
      document.body.appendChild(banner);
    }
    var detail = event.detail;
    banner.hidden = !detail.message;
    banner.textContent = detail.message + (detail.jobId ? " Job: " + detail.jobId : "");
  });
})();
