import { map, tileLayer, layerGroup, marker, divIcon } from "/vendor/leaflet/leaflet-src.esm.js";
import { formatRange, frameForPoints, thisWeekend, overlaps, comingLater, iso } from "./format.js";

const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';
const POSTCODE = /^[A-Z]{1,2}\d[A-Z\d]?\d[A-Z]{2}$/;
const OUTCODE = /^[A-Z]{1,2}\d[A-Z\d]?$/;

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function pinIcon(provisional) {
  const classes = ["pin"];
  if (provisional) classes.push("pin-provisional");
  return divIcon({
    className: "pin-wrap",
    html: `<span class="${classes.join(" ")}"></span>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  });
}

function addTiles(view) {
  tileLayer(TILES, { attribution: ATTR, maxZoom: 19 }).addTo(view);
}

function mountDetail() {
  const el = document.getElementById("detail-map");
  if (!el) return;
  const lat = Number(el.dataset.lat);
  const lng = Number(el.dataset.lng);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
  const view = map(el, { scrollWheelZoom: false });
  addTiles(view);
  marker([lat, lng], {
    icon: divIcon({
      className: "pin-wrap",
      html: '<span class="pin"></span>',
      iconSize: [14, 14],
      iconAnchor: [7, 7],
    }),
  }).addTo(view);
  view.setView([lat, lng], 13);
}

function visibleCards() {
  return [...document.querySelectorAll(".card")].filter((card) => !card.hidden);
}

function milesBetween(lat1, lng1, lat2, lng2) {
  const radius = 3958.8;
  const rad = (degrees) => degrees * Math.PI / 180;
  const dLat = rad(lat2 - lat1);
  const dLng = rad(lng2 - lng1);
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(lat1)) * Math.cos(rad(lat2)) * Math.sin(dLng / 2) ** 2;
  return 2 * radius * Math.asin(Math.sqrt(h));
}

function radiusMiles() {
  const value = Number(document.getElementById("radius")?.value);
  return [15, 30, 60, 100].includes(value) ? value : 30;
}

function setStatus(text) {
  const status = document.getElementById("search-status");
  if (status) status.textContent = text || "";
}

function countLine(count, relation, label) {
  const noun = count === 1 ? "show" : "shows";
  return `Showing ${count} ${noun} ${relation} ${label}.`;
}

function appendCountyBrowse(parent) {
  parent.append(document.createTextNode("Try a nearby town or "));
  const link = document.createElement("a");
  link.href = "/county/";
  link.textContent = "browse by county";
  parent.append(link, document.createTextNode("."));
}

function fillNoShows() {
  setStatus("");
}

function renderSuggestions(labels) {
  const status = document.getElementById("search-status");
  if (!status) return;
  status.replaceChildren(document.createTextNode("Did you mean "));
  labels.forEach((label, index) => {
    if (index > 0) status.append(document.createTextNode(index === labels.length - 1 ? " or " : ", "));
    const button = document.createElement("button");
    button.type = "button";
    button.className = "hint-place";
    button.textContent = label;
    button.addEventListener("click", () => {
      const input = document.getElementById("q");
      if (input) input.value = label;
      search({ scroll: true });
    });
    status.append(button);
  });
  status.append(document.createTextNode("?"));
}

function scrollToResults() {
  const target = document.getElementById(visibleCards().length ? "show-list" : "empty");
  if (!target) return;
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  target.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
}

const homes = new Map();
let origin = null;
let suggestions = null;
let requestSeq = 0;
let placeNote = "";

const KNOWN_COUNTIES = [
  "Bedfordshire", "Berkshire", "Bristol", "Buckinghamshire", "Cambridgeshire", "Cheshire",
  "Cornwall", "Cumbria", "Derbyshire", "Devon", "Dorset", "County Durham", "Durham",
  "East Sussex", "East Riding of Yorkshire", "Essex", "Gloucestershire", "Greater London",
  "Greater Manchester", "Hampshire", "Herefordshire", "Hertfordshire", "Isle of Wight",
  "Kent", "Lancashire", "Leicestershire", "Lincolnshire", "London", "Merseyside",
  "Norfolk", "North Yorkshire", "Northamptonshire", "Northumberland", "Nottinghamshire",
  "Oxfordshire", "Rutland", "Shropshire", "Somerset", "South Yorkshire", "Staffordshire",
  "Suffolk", "Surrey", "Sussex", "Tyne and Wear", "Warwickshire", "West Midlands",
  "West Sussex", "West Yorkshire", "Wiltshire", "Worcestershire", "Yorkshire",
  "Anglesey", "Blaenau Gwent", "Bridgend", "Caerphilly", "Cardiff", "Carmarthenshire",
  "Ceredigion", "Conwy", "Denbighshire", "Flintshire", "Gwynedd", "Merthyr Tydfil",
  "Monmouthshire", "Neath Port Talbot", "Newport", "Pembrokeshire", "Powys",
  "Rhondda Cynon Taf", "Swansea", "Torfaen", "Vale of Glamorgan", "Wrexham",
  "Aberdeenshire", "Angus", "Argyll and Bute", "Clackmannanshire", "Dumfries and Galloway",
  "Dundee", "East Ayrshire", "East Dunbartonshire", "East Lothian", "East Renfrewshire",
  "Edinburgh", "Falkirk", "Fife", "Glasgow", "Highland", "Inverclyde", "Midlothian",
  "Moray", "North Ayrshire", "North Lanarkshire", "Orkney", "Perth and Kinross",
  "Renfrewshire", "Scottish Borders", "Shetland", "South Ayrshire", "South Lanarkshire",
  "Stirling", "West Dunbartonshire", "West Lothian", "Western Isles",
  "Antrim", "Armagh", "Down", "Fermanagh", "Londonderry", "Tyrone",
];

function rememberHomes() {
  for (const card of document.querySelectorAll("#show-list .card")) {
    if (!homes.has(card)) homes.set(card, card.parentElement);
  }
}

function clearDistance(card) {
  card.querySelector(".dist")?.remove();
  delete card.dataset.miles;
}

function restoreOrder() {
  const flat = document.getElementById("distance-list");
  if (flat) {
    flat.replaceChildren();
    flat.hidden = true;
  }
  for (const [card, parent] of homes) {
    clearDistance(card);
    parent.appendChild(card);
  }
}

function showDistances(ranked) {
  const list = document.getElementById("show-list");
  let flat = document.getElementById("distance-list");
  if (!flat) {
    flat = document.createElement("div");
    flat.id = "distance-list";
    list.prepend(flat);
  }
  flat.hidden = false;
  flat.replaceChildren();
  for (const card of ranked) {
    const miles = Number(card.dataset.miles);
    let dist = card.querySelector(".dist");
    if (!dist) {
      dist = document.createElement("p");
      dist.className = "meta dist";
      card.querySelector(".card-link > div:last-child")?.appendChild(dist);
    }
    if (dist) dist.textContent = miles < 1 ? "Under 1 mile" : `${Math.round(miles)} miles`;
    flat.appendChild(card);
  }
  for (const month of document.querySelectorAll("#show-list > .month")) {
    month.hidden = true;
  }
}

function townCentre(raw) {
  const low = raw.toLowerCase();
  const hits = [...document.querySelectorAll(".card")].filter((card) => {
    return (card.dataset.town || "").toLowerCase() === low && Number.isFinite(Number(card.dataset.lat));
  });
  if (!hits.length) return null;
  const lat = hits.reduce((sum, card) => sum + Number(card.dataset.lat), 0) / hits.length;
  const lng = hits.reduce((sum, card) => sum + Number(card.dataset.lng), 0) / hits.length;
  return { lat, lng, label: hits[0].dataset.town };
}

function countyNames() {
  return [...new Set([...document.querySelectorAll(".card")].map((card) => card.dataset.county).filter(Boolean))];
}

function areaFromCards(raw) {
  const low = raw.toLowerCase();
  const counties = countyNames();
  const exact = counties.find((name) => name.toLowerCase() === low);
  if (exact) return { kind: "area", label: exact, counties: [exact], relation: "in" };
  const parts = counties.filter((name) => name.toLowerCase().endsWith(` ${low}`));
  if (!parts.length) return null;
  const sample = parts[0];
  const label = sample.slice(sample.length - raw.length);
  return { kind: "area", label, counties: parts, relation: "in" };
}

function knownCounty(raw) {
  const low = raw.toLowerCase();
  return KNOWN_COUNTIES.find((name) => name.toLowerCase() === low) || "";
}

function showsWithin(lat, lng) {
  const limit = radiusMiles();
  return [...document.querySelectorAll(".card")].filter((card) => {
    const lat2 = Number(card.dataset.lat);
    const lng2 = Number(card.dataset.lng);
    if (!Number.isFinite(lat2) || !Number.isFinite(lng2)) return false;
    return milesBetween(lat, lng, lat2, lng2) <= limit;
  }).length;
}

function townOptions(raw) {
  const low = raw.toLowerCase();
  const groups = new Map();
  for (const card of document.querySelectorAll(".card")) {
    const town = card.dataset.town || "";
    const name = town.toLowerCase();
    if (!town || !Number.isFinite(Number(card.dataset.lat))) continue;
    if (name !== low && !name.startsWith(`${low} `) && !name.startsWith(`${low}-`)) continue;
    if (!groups.has(town)) groups.set(town, []);
    groups.get(town).push(card);
  }
  return [...groups.entries()].map(([label, cards]) => {
    const lat = cards.reduce((sum, card) => sum + Number(card.dataset.lat), 0) / cards.length;
    const lng = cards.reduce((sum, card) => sum + Number(card.dataset.lng), 0) / cards.length;
    return {
      label,
      type: "town",
      lat,
      lng,
      count: showsWithin(lat, lng),
      origin: { lat, lng, label, kind: "near", relation: "near" },
    };
  });
}

function nameMatchesQuery(query, name) {
  const wanted = query.toLowerCase();
  const value = String(name || "").toLowerCase();
  return value === wanted || value.startsWith(`${wanted} `) || value.startsWith(`${wanted}-`);
}

async function apiTowns(raw) {
  const data = await (await fetch(`https://api.postcodes.io/places?limit=10&q=${encodeURIComponent(raw)}`)).json();
  const results = Array.isArray(data?.result) ? data.result : [];
  const allowed = new Set(["city", "town"]);
  return results
    .filter((item) => allowed.has(String(item?.local_type || "").toLowerCase()))
    .filter((item) => nameMatchesQuery(raw, item.name_1))
    .filter((item) => Number.isFinite(item.latitude) && Number.isFinite(item.longitude))
    .map((item) => ({
      label: item.name_1,
      type: String(item.local_type || "").toLowerCase(),
      lat: item.latitude,
      lng: item.longitude,
      count: showsWithin(item.latitude, item.longitude),
      origin: {
        lat: item.latitude,
        lng: item.longitude,
        label: item.name_1,
        kind: "near",
        relation: "near",
      },
    }));
}

function mergeOptions(groups) {
  const byName = new Map();
  for (const item of groups.flat()) {
    const key = item.label.toLowerCase();
    const existing = byName.get(key);
    if (!existing || (item.type === "city" && existing.type !== "city")) byName.set(key, item);
  }
  return [...byName.values()];
}

function biggerFirst(options) {
  const rank = { city: 0, town: 1 };
  return [...options].sort((a, b) => {
    const type = (rank[a.type] ?? 2) - (rank[b.type] ?? 2);
    if (type) return type;
    return b.count - a.count || a.label.localeCompare(b.label, "en-GB");
  });
}

async function lookupPlace(raw) {
  const compact = raw.toUpperCase().replace(/\s+/g, "");
  if (POSTCODE.test(compact)) {
    const data = await (await fetch(`https://api.postcodes.io/postcodes/${encodeURIComponent(compact)}`)).json();
    if (data?.result) return { lat: data.result.latitude, lng: data.result.longitude, label: data.result.postcode };
    return null;
  }
  if (OUTCODE.test(compact)) {
    const data = await (await fetch(`https://api.postcodes.io/outcodes/${encodeURIComponent(compact)}`)).json();
    if (data?.result) return { lat: data.result.latitude, lng: data.result.longitude, label: data.result.outcode };
    return null;
  }
  const exactTown = townCentre(raw);
  if (exactTown) return { ...exactTown, kind: "near", relation: "near" };
  const area = areaFromCards(raw);
  if (area) return area;
  let remote = [];
  try {
    remote = await apiTowns(raw);
  } catch {
    remote = [];
  }
  const found = biggerFirst(mergeOptions([townOptions(raw), remote])).filter((item) => item.count > 0);
  if (found.length > 1) return { suggestions: found.map((item) => item.label) };
  if (found.length === 1) return found[0].origin;
  const county = knownCounty(raw);
  if (county) return { label: county, kind: "empty", relation: "in" };
  const named = remote.find((item) => item.label.toLowerCase() === raw.toLowerCase());
  if (named) return { label: named.label, kind: "empty", relation: "near" };
  return null;
}

async function search(options = {}) {
  const seq = ++requestSeq;
  const raw = (document.getElementById("q")?.value || "").trim();
  origin = null;
  suggestions = null;
  placeNote = "";
  if (!raw) {
    setStatus("");
    applyFilters();
    return;
  }
  setStatus("Searching...");
  try {
    const found = await lookupPlace(raw);
    if (seq !== requestSeq) return;
    if (found?.suggestions) suggestions = found.suggestions;
    else if (found) origin = found;
    else if (POSTCODE.test(raw.toUpperCase().replace(/\s+/g, "")) || OUTCODE.test(raw.toUpperCase().replace(/\s+/g, ""))) {
      placeNote = "Could not find that postcode. Try the outward part, or a town.";
    }
  } catch {
    if (seq !== requestSeq) return;
    placeNote = "Search is unavailable right now. Try a town name.";
  }
  applyFilters();
  if (options.scroll) scrollToResults();
}

function applyFilters() {
  const list = document.getElementById("show-list");
  if (!list) {
    drawMarkers();
    return;
  }
  rememberHomes();
  restoreOrder();
  const today = new Date();
  const todayISO = iso(today);
  const weekend = thisWeekend(today);
  const when = document.querySelector('.chip[data-when][aria-pressed="true"]')?.dataset.when || "all";
  const queryRaw = (document.getElementById("q")?.value || "").trim().toLowerCase();
  const query = queryRaw.replace(/\s+/g, "");
  const limit = radiusMiles();

  for (const card of document.querySelectorAll(".card")) {
    const ended = card.dataset.end < todayISO;
    let whenOk = true;
    if (when === "weekend") whenOk = overlaps({ start: card.dataset.start, end: card.dataset.end }, weekend.start, weekend.end);
    if (when === "later") whenOk = comingLater({ start: card.dataset.start }, weekend.end);
    const hay = card.dataset.search || "";
    const compact = hay.replace(/\s+/g, "");
    const textOk = !queryRaw || hay.includes(queryRaw) || compact.includes(query);
    let nearOk = true;
    if (origin?.kind === "area") {
      const names = new Set((origin.counties || []).map((name) => name.toLowerCase()));
      nearOk = names.has((card.dataset.county || "").toLowerCase());
    } else if (origin?.kind === "empty") {
      nearOk = false;
    } else if (origin) {
      const lat = Number(card.dataset.lat);
      const lng = Number(card.dataset.lng);
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) nearOk = false;
      else {
        const miles = milesBetween(origin.lat, origin.lng, lat, lng);
        card.dataset.miles = String(miles);
        nearOk = miles <= limit;
      }
    }
    const textFiltered = suggestions ? false : (origin ? !nearOk : !textOk);
    card.hidden = ended || !whenOk || textFiltered;
  }

  if (origin && origin.kind !== "area" && origin.kind !== "empty") {
    const ranked = visibleCards().sort((a, b) => Number(a.dataset.miles) - Number(b.dataset.miles) || a.dataset.start.localeCompare(b.dataset.start));
    if (ranked.length) showDistances(ranked);
    else {
      for (const month of document.querySelectorAll("#show-list > .month")) month.hidden = true;
    }
    if (ranked.length) setStatus(countLine(ranked.length, "near", origin.label));
    else fillNoShows();
  } else {
    for (const month of document.querySelectorAll("#show-list > .month")) {
      const any = [...month.querySelectorAll(".card")].some((card) => !card.hidden);
      month.hidden = !any;
    }
    if (suggestions?.length) renderSuggestions(suggestions);
    else if (origin?.kind === "area") {
      const shownHere = visibleCards().length;
      if (shownHere) setStatus(countLine(shownHere, "in", origin.label));
      else fillNoShows();
    } else if (origin?.kind === "empty") fillNoShows();
    else setStatus(placeNote);
  }

  const shown = visibleCards();
  const count = document.getElementById("result-count");
  const tail = document.getElementById("result-count-tail");
  if (count) {
    const total = Number(count.dataset.total);
    const totalNoun = total === 1 ? "show" : "shows";
    const narrowed = Boolean(queryRaw) || when !== "all";
    if (Number.isFinite(total) && narrowed && shown.length > 0 && shown.length !== total) {
      count.textContent = shown.length === 1
        ? `1 of ${total} shows matches`
        : `${shown.length} of ${total} shows match`;
      if (tail) tail.hidden = true;
    } else if (Number.isFinite(total)) {
      count.textContent = `${total} ${totalNoun}`;
      if (tail) tail.hidden = false;
    }
  }

  const empty = document.getElementById("empty");
  const title = document.getElementById("empty-title");
  const copy = document.getElementById("empty-copy");
  if (empty && title && copy) {
    empty.hidden = shown.length !== 0;
    if (shown.length === 0) {
      if (origin) {
        title.textContent = `No shows in or near ${origin.label} yet.`;
        copy.replaceChildren();
        appendCountyBrowse(copy);
      } else if (when === "weekend") {
        title.textContent = "Nothing listed for this weekend.";
        copy.textContent = `This weekend is ${formatRange(weekend.start, weekend.end)}. Coming later has the next published dates.`;
      } else if (queryRaw) {
        title.textContent = placeNote || "Nothing matches that postcode or town.";
        copy.textContent = "Try the town, the county, or the outward part of the postcode.";
      } else {
        title.textContent = "Nothing in this window.";
        copy.textContent = "Try all upcoming shows, or another type.";
      }
    } else {
      title.textContent = "";
      copy.textContent = "";
    }
  }

  drawMarkers();
  const params = new URLSearchParams();
  if (when !== "all") params.set("when", when);
  if (queryRaw) params.set("q", queryRaw);
  if (origin && limit !== 30) params.set("r", String(limit));
  const next = params.toString();
  const url = next ? `${location.pathname}?${next}` : location.pathname;
  history.replaceState(null, "", url);
}

let view;
let group;

function applyFrame(points) {
  const frame = frameForPoints(points);
  if (frame.method === "setView") view.setView(frame.center, frame.zoom);
  else view.fitBounds(frame.points, { padding: [28, 28], maxZoom: frame.maxZoom });
}

function drawMarkers() {
  const frame = document.getElementById("map");
  if (!frame || !view || !group) return;
  group.clearLayers();
  const venues = new Map();
  for (const card of visibleCards()) {
    const lat = Number(card.dataset.lat);
    const lng = Number(card.dataset.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;
    const key = `${lat},${lng}`;
    if (!venues.has(key)) venues.set(key, []);
    venues.get(key).push(card);
  }
  const points = [];
  for (const cards of venues.values()) {
    cards.sort((a, b) => a.dataset.start.localeCompare(b.dataset.start) || (a.dataset.name || "").localeCompare(b.dataset.name || ""));
    const next = cards[0];
    const lat = Number(next.dataset.lat);
    const lng = Number(next.dataset.lng);
    points.push([lat, lng]);
    const lines = cards.map((card) => {
      const when = formatRange(card.dataset.start, card.dataset.end);
      const state = card.dataset.provisional === "1" ? "Provisional" : "Confirmed";
      return `<a href="${esc(card.dataset.href)}">${esc(card.dataset.name)}</a><br>${esc(when)} (${state})`;
    });
    marker([lat, lng], { icon: pinIcon(next.dataset.provisional === "1") }).bindPopup(lines.join("<br>")).addTo(group);
  }
  if (origin && Number.isFinite(origin.lat) && Number.isFinite(origin.lng)) {
    points.push([origin.lat, origin.lng]);
    marker([origin.lat, origin.lng], {
      icon: divIcon({
        className: "pin-wrap",
        html: '<span class="pin pin-origin"></span>',
        iconSize: [14, 14],
        iconAnchor: [7, 7],
      }),
    }).bindPopup(esc(origin.label)).addTo(group);
  }
  applyFrame(points);
}

function mountList() {
  const frame = document.getElementById("map");
  if (!frame) return;
  view = map(frame, {
    scrollWheelZoom: window.matchMedia("(pointer: fine)").matches,
  });
  addTiles(view);
  group = layerGroup().addTo(view);
  const params = new URLSearchParams(location.search);
  const when = params.get("when");
  if (when) {
    const button = document.querySelector(`.chip[data-when="${when}"]`);
    if (button) setWhen(button);
  }
  const input = document.getElementById("q");
  const radius = document.getElementById("radius");
  if (radius && ["15", "30", "60", "100"].includes(params.get("r") || "")) radius.value = params.get("r");
  if (input && params.get("q")) input.value = params.get("q");
  document.querySelectorAll(".chip[data-when]").forEach((button) => {
    button.addEventListener("click", () => {
      setWhen(button);
      applyFilters();
    });
  });
  document.getElementById("search")?.addEventListener("submit", (event) => {
    event.preventDefault();
    search({ scroll: true });
  });
  radius?.addEventListener("change", () => {
    if (origin) applyFilters();
    else if ((input?.value || "").trim()) search();
  });
  input?.addEventListener("input", () => {
    if (!(input.value || "").trim()) {
      origin = null;
      suggestions = null;
      placeNote = "";
      applyFilters();
    }
  });
  if ((input?.value || "").trim()) search();
  else applyFilters();
  setTimeout(() => {
    if (!view) return;
    view.invalidateSize();
    drawMarkers();
  }, 50);
}

function setWhen(active) {
  document.querySelectorAll(".chip[data-when]").forEach((button) => {
    button.setAttribute("aria-pressed", button === active ? "true" : "false");
  });
}

const mapHost = document.getElementById("map") || document.getElementById("detail-map");
if (mapHost) {
  try {
    mountDetail();
    mountList();
  } catch (error) {
    mapHost.innerHTML = '<p class="map-fallback">The map could not load. The list is still complete.</p>';
    console.error(error);
  }
}
