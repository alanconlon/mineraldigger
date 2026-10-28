/* Friday email sign-up: post to Buttondown, then open our own /thanks/ page.
   data-thanks on the form is that page. Without JavaScript the form posts to Buttondown. */
(function () {
  document.querySelectorAll("form.nl").forEach(function (f) {
    f.addEventListener("submit", function (ev) {
      if (f.dataset.native === "1") return;
      if (!window.fetch || !window.URLSearchParams) return;
      ev.preventDefault();
      var b = f.querySelector("button");
      if (b) {
        b.disabled = true;
        b.textContent = "Signing you up…";
      }
      var body = new URLSearchParams(new FormData(f));
      var done = false;
      var go = function () {
        if (done) return;
        done = true;
        location.href = f.getAttribute("data-thanks") || "/thanks/";
      };
      fetch(f.action, { method: "POST", mode: "no-cors", body: body }).then(go, function () {
        f.dataset.native = "1";
        f.submit();
      });
      setTimeout(go, 6000);
    });
  });
})();
