import { createHash } from "node:crypto";
import { cp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { addDays, iso, parseISO } from "../src/js/format.js";
import { featuredIds } from "./feature.mjs";
import {
  renderAbout,
  renderApp,
  renderDigest,
  renderFeature,
  renderHome,
  renderNotFound,
  renderOffline,
  renderPrivacy,
  renderCounty,
  renderCountyIndex,
  renderShow,
  renderSignupThanks,
  renderSitemap,
  renderSubmit,
  renderThanks,
  renderTerms,
  renderTown,
  renderTownIndex,
  renderType,
  renderWeekend,
  groupPlaces,
} from "./render.mjs";

const root = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const dist = join(root, "dist");

function loadEnvFile() {
  return readFile(join(root, ".env"), "utf8")
    .then((text) => {
      for (const line of text.split("\n")) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith("#") || !trimmed.includes("=")) continue;
        const index = trimmed.indexOf("=");
        const key = trimmed.slice(0, index).trim();
        const value = trimmed.slice(index + 1).trim();
        if (key && process.env[key] === undefined) process.env[key] = value;
      }
    })
    .catch(() => {});
}

async function readJson(path) {
  return JSON.parse(await readFile(path, "utf8"));
}

function applyStripe(stripe) {
  const env = {
    featured_show: process.env.STRIPE_FEATURED_SHOW_URL,
    year_pass: process.env.STRIPE_YEAR_PASS_URL,
    site_sponsor: process.env.STRIPE_SITE_SPONSOR_URL,
    friday_email: process.env.STRIPE_FRIDAY_EMAIL_URL,
  };
  const links = { ...stripe.links };
  for (const [key, value] of Object.entries(env)) {
    if (value) links[key] = value;
  }
  return { ...stripe, links };
}

function icsEscape(value) {
  return String(value).replace(/\\/g, "\\\\").replace(/\n/g, "\\n").replace(/,/g, "\\,").replace(/;/g, "\\;");
}

function ics(show, todayISO, site) {
  const end = iso(addDays(parseISO(show.end), 1)).replace(/-/g, "");
  const start = show.start.replace(/-/g, "");
  const stamp = `${todayISO.replace(/-/g, "")}T120000Z`;
  const host = new URL(site.url).host;
  const location = [show.venue.name, show.venue.street, show.venue.town, show.venue.postcode].filter(Boolean).join(", ");
  const description = show.source.url
    ? `Confirm times and entry with the organiser before you travel. ${show.source.url}`
    : "Confirm times and entry with the organiser before you travel.";
  const lines = [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//MineralDigger//EN",
    "CALSCALE:GREGORIAN",
    "BEGIN:VEVENT",
    `UID:${show.id}@${host}`,
    `DTSTAMP:${stamp}`,
    `DTSTART;VALUE=DATE:${start}`,
    `DTEND;VALUE=DATE:${end}`,
    `SUMMARY:${icsEscape(show.name)}`,
    `LOCATION:${icsEscape(location)}`,
  ];
  if (show.source.url) lines.push(`URL:${show.source.url}`);
  lines.push(`DESCRIPTION:${icsEscape(description)}`, "END:VEVENT", "END:VCALENDAR", "");
  return lines.join("\r\n");
}

async function writePage(path, html) {
  const file = join(dist, path);
  await mkdir(dirname(file), { recursive: true });
  await writeFile(file, html);
}

async function copyAssets() {
  await mkdir(join(dist, "fonts"), { recursive: true });
  await mkdir(join(dist, "vendor/leaflet"), { recursive: true });
  await mkdir(join(dist, "js"), { recursive: true });
  const fonts = [
    ["@fontsource/fraunces/files/fraunces-latin-500-normal.woff2", "fraunces-latin-500-normal.woff2"],
    ["@fontsource/fraunces/files/fraunces-latin-600-normal.woff2", "fraunces-latin-600-normal.woff2"],
    ["@fontsource/fraunces/files/fraunces-latin-700-normal.woff2", "fraunces-latin-700-normal.woff2"],
    ["@fontsource/outfit/files/outfit-latin-400-normal.woff2", "outfit-latin-400-normal.woff2"],
    ["@fontsource/outfit/files/outfit-latin-500-normal.woff2", "outfit-latin-500-normal.woff2"],
    ["@fontsource/outfit/files/outfit-latin-600-normal.woff2", "outfit-latin-600-normal.woff2"],
  ];
  for (const [from, name] of fonts) {
    await cp(join(root, "node_modules", from), join(dist, "fonts", name));
  }
  await cp(join(root, "node_modules/leaflet/dist/leaflet-src.esm.js"), join(dist, "vendor/leaflet/leaflet-src.esm.js"));
  await cp(join(root, "node_modules/leaflet/dist/leaflet.css"), join(dist, "vendor/leaflet/leaflet.css"));
  await cp(join(root, "node_modules/leaflet/dist/images"), join(dist, "vendor/leaflet/images"), { recursive: true });
  await cp(join(root, "src/site.css"), join(dist, "site.css"));
  await cp(join(root, "src/js/format.js"), join(dist, "js/format.js"));
  await cp(join(root, "src/js/site.js"), join(dist, "js/site.js"));
  await cp(join(root, "src/js/submit.js"), join(dist, "js/submit.js"));
  await cp(join(root, "src/js/newsletter.js"), join(dist, "js/newsletter.js"));
  await cp(join(root, "functions/api/validate.js"), join(dist, "js/validate.js"));
  await cp(join(root, "public/favicon.svg"), join(dist, "favicon.svg"));
  await cp(join(root, "public/favicon.ico"), join(dist, "favicon.ico"));
  await cp(join(root, "public/apple-touch-icon.png"), join(dist, "apple-touch-icon.png"));
  await cp(join(root, "public/og-image.jpg"), join(dist, "og-image.jpg"));
  await cp(join(root, "public/logo.png"), join(dist, "logo.png"));
  await cp(join(root, "public/manifest.webmanifest"), join(dist, "manifest.webmanifest"));
  await cp(join(root, "public/pwa.js"), join(dist, "pwa.js"));
  await cp(join(root, "public/icons"), join(dist, "icons"), { recursive: true });
  const swSource = await readFile(join(root, "public/sw.js"), "utf8");
  const swVersion = createHash("sha256").update(swSource).digest("hex").slice(0, 12);
  await writeFile(join(dist, "sw.js"), swSource.replaceAll("__MD_VERSION__", swVersion));
  await writeFile(
    join(dist, "_headers"),
    "/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n  X-Frame-Options: SAMEORIGIN\n\n/thanks/\n  X-Robots-Tag: noindex\n\n/thanks/*\n  X-Robots-Tag: noindex\n\n/thanks/payment/*\n  X-Robots-Tag: noindex\n\n/offline/\n  X-Robots-Tag: noindex\n\n/sw.js\n  Cache-Control: no-cache\n\n/manifest.webmanifest\n  Content-Type: application/manifest+json\n",
  );
  await writeFile(
    join(dist, "_redirects"),
    [
      "/newsletter /digest/ 301",
      "/newsletter/ /digest/ 301",
      "/shows/surrey /county/surrey/ 301",
      "/shows/surrey/ /county/surrey/ 301",
      "/counties /county/ 301",
      "/counties/ /county/ 301",
      "",
    ].join("\n"),
  );
}

async function main() {
  await loadEnvFile();
  const today = new Date();
  const todayISO = iso(today);
  const catalogue = await readJson(join(root, "data/shows.json"));
  const stripe = applyStripe(await readJson(join(root, "data/stripe.json")));
  const featured = await readJson(join(root, "data/featured.json"));
  const site = await readJson(join(root, "data/site.json"));
  const generated = catalogue.generated || todayISO;
  const shows = catalogue.shows;
  const featuredSet = featuredIds(shows, featured, todayISO);
  for (const show of shows) show.featured = featuredSet.has(show.id);
  const upcoming = shows.filter((show) => show.end >= todayISO);

  await rm(dist, { recursive: true, force: true });
  await mkdir(dist, { recursive: true });
  await copyAssets();
  const origin = new URL(site.url).origin;
  await writeFile(join(dist, "robots.txt"), `User-agent: *\nAllow: /\nSitemap: ${origin}/sitemap.xml\n`);

  const ctx = { site, shows: upcoming, generated, today, todayISO, stripe };
  const places = groupPlaces(upcoming);
  const placeSets = {
    counties: new Set(places.counties.keys()),
    towns: new Set(places.towns.keys()),
  };
  await writePage("index.html", renderHome(ctx));
  await writePage("this-weekend/index.html", renderWeekend(ctx));
  await writePage("county/index.html", renderCountyIndex(ctx, places.counties));
  await writePage("towns/index.html", renderTownIndex(ctx, places.towns));
  for (const county of places.counties.values()) {
    await writePage(`county/${county.slug}/index.html`, renderCounty(ctx, county, places.towns));
  }
  for (const town of places.towns.values()) {
    await writePage(`town/${town.slug}/index.html`, renderTown(ctx, town));
  }
  for (const key of ["rock", "gem", "mineral", "fossil", "bead"]) {
    await writePage(`${key}/index.html`, renderType(ctx, key));
  }
  await writePage("feature/index.html", renderFeature({ site, stripe, generated }));
  await writePage("thanks/index.html", renderSignupThanks({ site, generated }));
  await writePage("thanks/payment/index.html", renderThanks({ site, generated }));
  await writePage("submit/index.html", renderSubmit({ site, generated }));
  await writePage("about/index.html", renderAbout({ site, generated }));
  await writePage("digest/index.html", renderDigest({ site, generated }));
  await writePage("app/index.html", renderApp({ site, generated }));
  await writePage("offline/index.html", renderOffline({ site, generated }));
  await writePage("privacy/index.html", renderPrivacy({ site, generated }));
  await writePage("terms/index.html", renderTerms({ site, stripe, generated }));
  await writePage("404.html", renderNotFound({ site, generated }));

  // /thanks/, /thanks/payment/ and /offline/ are noindex and stay out of the sitemap. /newsletter/ redirects to /digest/. This site does not ping IndexNow.
  const paths = ["/", "/this-weekend/", "/county/", "/towns/", "/feature/", "/submit/", "/digest/", "/app/", "/about/", "/privacy/", "/terms/", "/rock/", "/gem/", "/mineral/", "/fossil/", "/bead/"];
  for (const county of places.counties.values()) paths.push(`/county/${county.slug}/`);
  for (const town of places.towns.values()) paths.push(`/town/${town.slug}/`);
  for (const show of shows) {
    await writePage(`show/${show.slug}/index.html`, renderShow({ site, show, generated, todayISO, places: placeSets }));
    await writePage(`show/${show.slug}/event.ics`, ics(show, todayISO, site));
    paths.push(`/show/${show.slug}/`);
  }
  await writeFile(join(dist, "sitemap.xml"), renderSitemap(site, paths));
  await mkdir(join(dist, "data"), { recursive: true });
  await writeFile(join(dist, "data/shows.json"), JSON.stringify({ generated, shows }, null, 2));
  console.log(`Built ${upcoming.length} upcoming shows, ${shows.length} pages, as of ${todayISO}`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
