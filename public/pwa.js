/* Home-screen support: registers the service worker (offline copies of pages you've viewed).
   No automatic pop-ups. The browser's own install prompt is held back and only offered from the
   "Add MineralDigger to this phone" button on /app/, never on Android (that prompt is a WebAPK
   Play Protect can block). */
(function () {
  var nav = window.navigator, deferred = null;
  var android = /Android/i.test(nav.userAgent || "") || (nav.userAgentData && /Android/i.test(nav.userAgentData.platform || ""));
  var local = location.hostname === "localhost" || location.hostname === "127.0.0.1";
  if ("serviceWorker" in nav && (location.protocol === "https:" || local)) {
    window.addEventListener("load", function () { nav.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {}); });
  }
  var mm = function (q) { return window.matchMedia && window.matchMedia(q).matches; };
  var standalone = mm("(display-mode: standalone)") || mm("(display-mode: fullscreen)") || mm("(display-mode: minimal-ui)") || nav.standalone === true;
  function $(id) { return document.getElementById(id); }
  function ready(fn) { if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn); }
  ready(function () { if (standalone && $("a2hs-done")) $("a2hs-done").hidden = false; });
  window.addEventListener("beforeinstallprompt", function (e) {
    e.preventDefault(); deferred = e;
    if (android) return;
    var box = $("a2hs-install"); if (!box) return;
    box.hidden = false;
    var b = box.querySelector("button");
    b.onclick = function () {
      if (!deferred) return;
      deferred.prompt();
      deferred.userChoice.then(function (c) { if (c && c.outcome === "accepted") { box.hidden = true; if ($("a2hs-done")) $("a2hs-done").hidden = false; } }, function () {});
      deferred = null;
    };
  });
  window.addEventListener("appinstalled", function () { var box = $("a2hs-install"); if (box) box.hidden = true; if ($("a2hs-done")) $("a2hs-done").hidden = false; });
})();
