import { map, tileLayer, layerGroup, marker, divIcon } from "/vendor/leaflet/leaflet-src.esm.js";
import { formatRange, thisWeekend, overlaps, comingLater, iso } from "./format.js";

const TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>';

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

function applyFilters() {
  const list = document.getElementById("show-list");
  if (!list) return;
  const today = new Date();
  const todayISO = iso(today);
  const weekend = thisWeekend(today);
  const when = document.querySelector('.chip[data-when][aria-pressed="true"]')?.dataset.when || "all";
  const query = (document.getElementById("q")?.value || "").trim().toLowerCase().replace(/\s+/g, "");
  const queryRaw = (document.getElementById("q")?.value || "").trim().toLowerCase();

  for (const card of document.querySelectorAll(".card")) {
    const ended = card.dataset.end < todayISO;
    let whenOk = true;
    if (when === "weekend") whenOk = overlaps({ start: card.dataset.start, end: card.dataset.end }, weekend.start, weekend.end);
    if (when === "later") whenOk = comingLater({ start: card.dataset.start }, weekend.end);
    const hay = card.dataset.search || "";
    const compact = hay.replace(/\s+/g, "");
    const searchOk = !queryRaw || hay.includes(queryRaw) || compact.includes(query);
    card.hidden = ended || !whenOk || !searchOk;
  }

  for (const month of document.querySelectorAll(".month")) {
    const any = [...month.querySelectorAll(".card")].some((card) => !card.hidden);
    month.hidden = !any;
  }

  const shown = visibleCards();
  const count = document.getElementById("result-count");
  if (count) {
    const noun = shown.length === 1 ? "show" : "shows";
    count.textContent = `${shown.length} ${noun}`;
  }

  const empty = document.getElementById("empty");
  if (empty) {
    empty.hidden = shown.length !== 0;
    const title = empty.querySelector("h2");
    const copy = empty.querySelector("p");
    if (shown.length === 0 && title && copy) {
      if (when === "weekend") {
        title.textContent = "Nothing listed for this weekend.";
        copy.textContent = `This weekend is ${formatRange(weekend.start, weekend.end)}. Coming later has the next published dates.`;
      } else if (queryRaw) {
        title.textContent = "Nothing matches that town or postcode.";
        copy.textContent = "Try the town, the county, or the outward part of the postcode.";
      } else {
        title.textContent = "Nothing in this window.";
        copy.textContent = "Try all upcoming shows, or another type.";
      }
    }
  }

  drawMarkers();
  const params = new URLSearchParams();
  if (when !== "all") params.set("when", when);
  if (queryRaw) params.set("q", queryRaw);
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
  if (input && params.get("q")) input.value = params.get("q");
  document.querySelectorAll(".chip[data-when]").forEach((button) => {
    button.addEventListener("click", () => {
      setWhen(button);
      applyFilters();
    });
  });
  input?.addEventListener("input", applyFilters);
  applyFilters();
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
