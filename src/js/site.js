import { map, tileLayer, layerGroup, marker, divIcon } from "/vendor/leaflet/leaflet-src.esm.js";
import { formatRange, thisWeekend, overlaps, comingLater, iso } from "./format.js";

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

function pinIcon(card) {
  const classes = ["pin"];
  if (card.dataset.provisional === "1") classes.push("pin-provisional");
  if (card.dataset.featured === "1") classes.push("pin-featured");
  const size = card.dataset.featured === "1" ? 18 : 14;
  return divIcon({
    className: "pin-wrap",
    html: `<span class="${classes.join(" ")}"></span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
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

const homes = new Map();
let origin = null;
let requestSeq = 0;
let placeNote = "";

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

function countyNamed(raw) {
  const low = raw.toLowerCase();
  if (low.length < 3) return "";
  const hit = [...document.querySelectorAll(".card")].find((card) => (card.dataset.county || "").toLowerCase().includes(low));
  return hit?.dataset.county || "";
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
  const town = townCentre(raw);
  if (town) return town;
  if (countyNamed(raw)) return null;
  const data = await (await fetch(`https://api.postcodes.io/places?limit=1&q=${encodeURIComponent(raw)}`)).json();
  const place = data?.result?.[0];
  if (!place || !Number.isFinite(place.latitude) || !Number.isFinite(place.longitude)) return null;
  return { lat: place.latitude, lng: place.longitude, label: place.name_1 || raw };
}

async function search() {
  const seq = ++requestSeq;
  const raw = (document.getElementById("q")?.value || "").trim();
  origin = null;
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
    if (found) origin = found;
    else if (POSTCODE.test(raw.toUpperCase().replace(/\s+/g, "")) || OUTCODE.test(raw.toUpperCase().replace(/\s+/g, ""))) {
      placeNote = "Could not find that postcode. Try the outward part, or a town.";
    }
  } catch {
    if (seq !== requestSeq) return;
    placeNote = "Search is unavailable right now. Try a town name.";
  }
  applyFilters();
}

function applyFilters() {
  const list = document.getElementById("show-list");
  if (!list) return;
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
    if (origin) {
      const lat = Number(card.dataset.lat);
      const lng = Number(card.dataset.lng);
      if (!Number.isFinite(lat) || !Number.isFinite(lng)) nearOk = false;
      else {
        const miles = milesBetween(origin.lat, origin.lng, lat, lng);
        card.dataset.miles = String(miles);
        nearOk = miles <= limit;
      }
    }
    card.hidden = ended || !whenOk || (origin ? !nearOk : !textOk);
  }

  if (origin) {
    const ranked = visibleCards().sort((a, b) => Number(a.dataset.miles) - Number(b.dataset.miles) || a.dataset.start.localeCompare(b.dataset.start));
    if (ranked.length) showDistances(ranked);
    else {
      for (const month of document.querySelectorAll("#show-list > .month")) month.hidden = true;
    }
    const noun = ranked.length === 1 ? "show" : "shows";
    setStatus(placeNote || `${ranked.length} ${noun} within ${limit} miles of ${origin.label}.`);
  } else {
    for (const month of document.querySelectorAll("#show-list > .month")) {
      const any = [...month.querySelectorAll(".card")].some((card) => !card.hidden);
      month.hidden = !any;
    }
    setStatus(placeNote);
  }

  const shown = visibleCards();
  const count = document.getElementById("result-count");
  if (count) {
    const noun = shown.length === 1 ? "show" : "shows";
    count.textContent = `${shown.length} ${noun}`;
  }

  const empty = document.getElementById("empty");
  const title = document.getElementById("empty-title");
  const copy = document.getElementById("empty-copy");
  if (empty && title && copy) {
    empty.hidden = shown.length !== 0;
    if (shown.length === 0) {
      if (origin) {
        title.textContent = `Nothing within ${limit} miles.`;
        copy.textContent = "Try a larger distance, or search for the town.";
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

function drawMarkers() {
  const frame = document.getElementById("map");
  if (!frame || !view || !group) return;
  group.clearLayers();
  const points = [];
  for (const card of visibleCards()) {
    const lat = Number(card.dataset.lat);
    const lng = Number(card.dataset.lng);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) continue;
    const point = [lat, lng];
    points.push(point);
    const place = card.dataset.place || "";
    const html = `<strong>${esc(card.dataset.name)}</strong><br>${esc(place)}<br><a href="${esc(card.dataset.href)}">Show page</a>`;
    marker(point, { icon: pinIcon(card) }).bindPopup(html).addTo(group);
  }
  if (origin) {
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
  if (!points.length) {
    view.setView([54.5, -3], 5.5);
    return;
  }
  const lats = points.map((point) => point[0]);
  const lngs = points.map((point) => point[1]);
  const tight = Math.max(...lats) - Math.min(...lats) < 0.02 && Math.max(...lngs) - Math.min(...lngs) < 0.02;
  if (points.length === 1 || tight) view.setView(points[0], 11);
  else view.fitBounds(points, { padding: [28, 28], maxZoom: 10 });
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
    search();
  });
  radius?.addEventListener("change", () => {
    if (origin) applyFilters();
    else if ((input?.value || "").trim()) search();
  });
  input?.addEventListener("input", () => {
    if (!(input.value || "").trim()) {
      origin = null;
      placeNote = "";
      applyFilters();
    }
  });
  if ((input?.value || "").trim()) search();
  else applyFilters();
  setTimeout(() => view.invalidateSize(), 50);
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
