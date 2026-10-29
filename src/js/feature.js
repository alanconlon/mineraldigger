(function () {
  var box = document.getElementById("feature-pick");
  if (!box) return;
  var slug = (new URLSearchParams(location.search).get("show") || "").trim();
  if (!/^[a-z0-9-]+$/.test(slug)) return;

  var pay = document.getElementById("featured-pay");
  if (pay && String(pay.getAttribute("href") || "").indexOf("https://") === 0) {
    var payment = new URL(pay.getAttribute("href"));
    payment.searchParams.set("client_reference_id", slug);
    pay.href = payment.toString();
  }

  function listedName(show) {
    var name = String((show && show.name) || "").trim();
    var town = String((show && show.venue && show.venue.town) || "").trim();
    if (!town || name.toLowerCase().indexOf(town.toLowerCase()) === 0) return name;
    return town + ": " + name;
  }

  function when(iso) {
    var parts = String(iso || "").split("-");
    if (parts.length !== 3) return "";
    var date = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
    if (Number.isNaN(date.getTime())) return "";
    var weekday = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"][date.getDay()];
    var month = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"][date.getMonth()];
    return weekday + " " + date.getDate() + " " + month + " " + date.getFullYear();
  }

  fetch("/data/shows.json")
    .then(function (response) { return response.json(); })
    .then(function (data) {
      var shows = (data && data.shows) || [];
      var show = null;
      for (var i = 0; i < shows.length; i += 1) {
        if (shows[i].slug === slug) show = shows[i];
      }
      box.hidden = false;
      box.replaceChildren();
      var paragraph = document.createElement("p");
      if (!show) {
        paragraph.textContent = "That show is not on the list. Submit it free first, then come back to feature it.";
        box.appendChild(paragraph);
        return;
      }
      var heading = document.getElementById("feature-heading");
      var name = listedName(show);
      if (heading) heading.textContent = "Feature: " + name;
      document.title = "Feature: " + name + " | MineralDigger";
      var date = when(show.start);
      if (date && show.end && show.end !== show.start) date = when(show.start) + " to " + when(show.end);
      if (date) paragraph.appendChild(document.createTextNode(date + ". "));
      var link = document.createElement("a");
      link.href = "/show/" + slug + "/";
      link.textContent = "Show page";
      paragraph.appendChild(link);
      box.appendChild(paragraph);
    })
    .catch(function () {});
})();
