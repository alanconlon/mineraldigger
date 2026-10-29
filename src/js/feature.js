(function () {
  var box = document.getElementById("feature-pick");
  if (!box) return;
  var slug = (new URLSearchParams(location.search).get("show") || "").trim();
  if (!/^[a-z0-9-]+$/.test(slug)) return;

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
      var strong = document.createElement("strong");
      strong.textContent = "Featuring this show. ";
      paragraph.appendChild(strong);
      paragraph.appendChild(document.createTextNode(listedName(show)));
      var date = when(show.start);
      if (date && show.end && show.end !== show.start) date = when(show.start) + " to " + when(show.end);
      if (date) paragraph.appendChild(document.createTextNode(". " + date + "."));
      else paragraph.appendChild(document.createTextNode("."));
      paragraph.appendChild(document.createTextNode(" "));
      var link = document.createElement("a");
      link.href = "/show/" + slug + "/";
      link.textContent = "Show page";
      paragraph.appendChild(link);
      box.appendChild(paragraph);
    })
    .catch(function () {});
})();
