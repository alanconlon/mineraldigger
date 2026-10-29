import { addDays, formatDay, formatRange, iso, longDate, monthKey, monthLabel, overlaps, parseISO, shortStack, thisWeekend } from "../src/js/format.js";
import { stripeReady } from "./feature.mjs";

const TYPES = [
  ["rock", "Rock", "/rock/"],
  ["gem", "Gem", "/gem/"],
  ["mineral", "Mineral", "/mineral/"],
  ["fossil", "Fossil", "/fossil/"],
  ["bead", "Bead", "/bead/"],
];

const TYPE_INTRO = {
  rock: "Rock shows across the UK, plus the rock, gem and bead weekends that include them. MineralDigger is a free calendar and map of dates and venues from organiser sites. Always confirm times and tickets with the organiser before you travel.",
  gem: "Gem shows and the rock, gem and bead weekends that list gems. MineralDigger puts UK dates, venues and entry on one map so you can see what is on this weekend and later in the year. Confirm with the organiser before you set off.",
  mineral: "Mineral shows and society fairs with a date on the organiser site. MineralDigger is a free UK calendar and map for collectors, not a club or society. Check entry, times and any changes with the organiser before you travel.",
  fossil: "Fossil shows, and mineral weekends that include fossils. MineralDigger lists UK dates and venues from organiser websites on one map. Use it as a finder, then confirm times, tickets and changes with the organiser before you go.",
  bead: "Bead shows, including the rock, gem and bead weekends. MineralDigger is a free UK calendar and map of dates, venues and entry from organiser sites. Use it to plan a trip, then check with the organiser before you travel.",
};

const TYPE_DESCRIPTION = {
  rock: "UK rock shows and rock, gem and bead weekends on one map. Free calendar from organiser sites.",
  gem: "UK gem shows and rock, gem and bead weekends. Dates, venues and entry on MineralDigger.",
  mineral: "UK mineral shows and society fairs on one map. Free calendar; confirm with the organiser.",
  fossil: "UK fossil shows and mineral weekends that include fossils. Free map calendar on MineralDigger.",
  bead: "UK bead shows and rock, gem and bead weekends. Dates and venues on MineralDigger.",
};

const SHARE_ALT = "MineralDigger: Rock, gem, mineral, fossil and bead shows across the UK, on one map.";
const SITE_BLURB = "Rock, gem, mineral, fossil and bead shows across the UK, on one map.";
const SPONSORS_EMAIL = "sponsors@mineraldigger.com";

const NEWSLETTER_PATH = "/newsletter/";

export function slugify(value) {
  return String(value ?? "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/['’]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

// Town first in lists and headings. The catalogue name stays on structured data.
export function listedName(show) {
  const name = String(show?.name || "").trim();
  const town = String(show?.venue?.town || "").trim();
  if (!town || name.toLowerCase().startsWith(town.toLowerCase())) return name;
  return `${town}: ${name}`;
}

const FREE_NOTE = /^(free|free entry|free entrance|entrance free|free admission|admission free)\.?$/i;

export function entryLabel(entry) {
  if (!entry || entry.kind === "unknown" || !entry.label || entry.label === "Unknown") return "Check with organiser";
  if (entry.kind === "free" || entry.adult_gbp === 0) return "Free entry";
  return entry.label;
}

function visitorSummary(show) {
  let text = publicNote(show.summary);
  const free = show.entry?.kind === "free" || show.entry?.adult_gbp === 0;
  if (free) text = text.replace(/\s+Free(?:\s+(?:entry|entrance|admission))?\.?$/i, "").trim();
  return text;
}

function entryDetail(entry) {
  const notes = publicNote(entry?.notes);
  if (!notes || FREE_NOTE.test(notes.trim())) return "";
  return notes;
}

export function groupPlaces(shows) {
  const counties = new Map();
  const towns = new Map();
  for (const show of shows) {
    const countyName = show.venue.county;
    const townName = show.venue.town;
    const nation = show.venue.nation || "UK";
    if (countyName) {
      const slug = slugify(countyName);
      const existing = counties.get(slug);
      if (existing && existing.name !== countyName) throw new Error(`County slug clash: ${slug}`);
      if (!existing) counties.set(slug, { slug, name: countyName, nation, shows: [] });
      counties.get(slug).shows.push(show);
    }
    if (townName) {
      const slug = slugify(townName);
      const existing = towns.get(slug);
      if (existing && existing.name !== townName) throw new Error(`Town slug clash: ${slug}`);
      if (!existing) towns.set(slug, { slug, name: townName, county: countyName, nation, shows: [] });
      towns.get(slug).shows.push(show);
    }
  }
  return { counties, towns };
}

const NATION_ORDER = ["England", "Wales", "Scotland", "Northern Ireland"];

function byNation(items) {
  return [...items].sort((a, b) => {
    const ai = NATION_ORDER.indexOf(a.nation);
    const bi = NATION_ORDER.indexOf(b.nation);
    const nation = (ai < 0 ? 99 : ai) - (bi < 0 ? 99 : bi);
    if (nation) return nation;
    return a.name.localeCompare(b.name, "en-GB");
  });
}

export function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function nav(path) {
  const items = [
    ["/", "Shows"],
    ["/feature/", "Feature"],
    ["/submit/", "Submit a show"],
    [NEWSLETTER_PATH, "Friday email"],
    ["/about/", "About"],
  ];
  return items
    .map(([href, label]) => `<a href="${href}"${href === path ? ' aria-current="page"' : ""}>${label}</a>`)
    .join("\n");
}

function footer(generated) {
  const types = TYPES.map(([, label, href]) => `<a href="${href}">${label}</a>`).join("\n");
  return `<footer class="site-footer">
    <div class="wrap foot">
      <div>
        <a class="logo" href="/">Mineral<span>Digger</span></a>
        <p class="muted">Rock, gem, mineral, fossil and bead shows across the UK. On one map.<br>Dates checked against organiser websites. Always confirm with the organiser before you travel.</p>
        <p class="social"><a href="https://www.facebook.com/people/MineralDigger/61595681170967/" rel="me noopener" target="_blank">Facebook</a> <a href="https://bsky.app/profile/mineraldigger.com" rel="me noopener" target="_blank">Bluesky</a></p>
      </div>
      <div>
        <h2>Browse</h2>
        <a href="/">Upcoming shows</a>
        <a href="/this-weekend/">This weekend</a>
        <a href="/?when=later">Coming later</a>
        <a href="/county/">Counties</a>
        <a href="/towns/">Towns</a>
      </div>
      <div>
        <h2>Organisers</h2>
        <a href="/submit/">Submit your show</a>
        <a href="/feature/">Feature your show</a>
        <a href="/about/">How we list shows</a>
      </div>
      <div>
        <h2>Show types</h2>
        ${types}
      </div>
      <div>
        <h2>Stay in touch</h2>
        <a href="${NEWSLETTER_PATH}">Friday email</a>
        <a href="/app/">Add to your phone</a>
      </div>
    </div>
    <div class="wrap muted small">© 2026 MineralDigger. Data last refreshed ${esc(longDate(generated))}. <a href="/privacy/">Privacy</a> · <a href="/terms/">Terms</a></div>
  </footer>`;
}

function siteGraph(site) {
  const page = new URL("/", site.url).href;
  const origin = new URL(site.url).origin;
  const data = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "WebSite",
        "@id": `${origin}/#website`,
        name: site.name,
        url: page,
        inLanguage: "en-GB",
        description: SITE_BLURB,
        publisher: { "@id": `${origin}/#org` },
      },
      {
        "@type": "Organization",
        "@id": `${origin}/#org`,
        name: site.name,
        url: page,
        logo: {
          "@type": "ImageObject",
          url: new URL("/logo.png", site.url).href,
          width: 512,
          height: 512,
        },
        email: site.email,
        sameAs: [
          "https://www.facebook.com/people/MineralDigger/61595681170967/",
          "https://bsky.app/profile/mineraldigger.com",
        ],
        areaServed: ["GB"],
      },
    ],
  };
  return `<script type="application/ld+json">${JSON.stringify(data).replace(/</g, "\\u003c")}</script>`;
}

function layout({ site, path, title, description, ogTitle, ogDescription, body, map = false, generated, robots, structuredData = "" }) {
  const canonical = new URL(path, site.url).href;
  const image = new URL("/og-image.jpg", site.url).href;
  const openTitle = ogTitle ?? title;
  const openDescription = ogDescription ?? description;
  return `<!DOCTYPE html>
<html lang="en-GB">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${esc(title)}</title>
  <meta name="description" content="${esc(description)}">
  ${robots ? `<meta name="robots" content="${esc(robots)}">` : ""}
  <link rel="canonical" href="${esc(canonical)}">
  <link rel="icon" href="/favicon.ico" sizes="32x32">
  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <link rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png">
  <link rel="manifest" href="/manifest.webmanifest">
  <meta name="theme-color" content="#143f36">
  <meta name="mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-title" content="MineralDigger">
  <meta name="apple-mobile-web-app-status-bar-style" content="black">
  <meta property="og:title" content="${esc(openTitle)}">
  <meta property="og:description" content="${esc(openDescription)}">
  <meta property="og:type" content="website">
  <meta property="og:url" content="${esc(canonical)}">
  <meta property="og:site_name" content="${esc(site.name)}">
  <meta property="og:locale" content="en_GB">
  <meta property="og:image" content="${esc(image)}">
  <meta property="og:image:width" content="1200">
  <meta property="og:image:height" content="630">
  <meta property="og:image:alt" content="${esc(SHARE_ALT)}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="${esc(title)}">
  <meta name="twitter:description" content="${esc(description)}">
  <meta name="twitter:image" content="${esc(image)}">
  <link rel="stylesheet" href="/site.css">
  ${map ? '<link rel="stylesheet" href="/vendor/leaflet/leaflet.css">' : ""}
  ${structuredData}
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>
  <header class="site-header">
    <div class="wrap bar">
      <a class="logo" href="/">Mineral<span>Digger</span></a>
      <button type="button" class="nav-toggle" aria-expanded="false" aria-controls="primary-nav">Menu</button>
      <nav id="primary-nav" class="nav" aria-label="Primary">${nav(path)}</nav>
    </div>
  </header>
  <main id="main">${body}</main>
  ${footer(generated)}
  ${map ? '<script type="module" src="/js/site.js"></script>' : ""}
  <script defer src="/js/newsletter.js"></script>
  <script defer src="/pwa.js" data-app="MineralDigger"></script>
  <script>
    (function () {
      var button = document.querySelector(".nav-toggle");
      var menu = document.getElementById("primary-nav");
      if (!button || !menu) return;
      function setOpen(open) {
        menu.classList.toggle("is-open", open);
        button.setAttribute("aria-expanded", open ? "true" : "false");
        button.textContent = open ? "Close" : "Menu";
      }
      button.addEventListener("click", function () {
        setOpen(!menu.classList.contains("is-open"));
      });
      menu.addEventListener("click", function (event) {
        if (event.target.closest("a")) setOpen(false);
      });
      document.addEventListener("keydown", function (event) {
        if (event.key === "Escape") setOpen(false);
      });
    })();
  </script>
</body>
</html>
`;
}

function pills(show, withTypes = true) {
  const bits = [`<span class="pill pill-${esc(show.entry.kind)}">${esc(entryLabel(show.entry))}</span>`];
  if (show.provisional) bits.push('<span class="pill pill-provisional">Provisional</span>');
  if (show.featured) bits.push('<span class="pill pill-featured">Featured</span>');
  if (withTypes) {
    for (const type of show.types) bits.push(`<span class="pill">${esc(type)}</span>`);
  }
  return bits.join(" ");
}

function byDate(shows) {
  return [...shows].sort((a, b) => a.start.localeCompare(b.start) || a.name.localeCompare(b.name, "en-GB") || String(a.id).localeCompare(String(b.id)));
}

function card(show) {
  const stack = shortStack(show.start, show.end);
  const place = [show.venue.town, show.venue.county].filter(Boolean).join(", ");
  const label = listedName(show);
  const search = [show.name, label, show.venue.name, show.venue.town, show.venue.county, show.venue.postcode, show.organiser.name]
    .join(" ")
    .toLowerCase();
  const times = show.times.summary ? `<p class="meta">${esc(show.times.summary)}</p>` : "";
  const dealers = show.dealers ? `<p class="dealers">${esc(show.dealers)} dealers</p>` : "";
  return `<article class="card${show.featured ? " featured" : ""}" data-start="${esc(show.start)}" data-end="${esc(show.end)}" data-lat="${esc(show.venue.lat)}" data-lng="${esc(show.venue.lng)}" data-town="${esc(show.venue.town)}" data-county="${esc(show.venue.county)}" data-name="${esc(label)}" data-place="${esc(`${show.venue.name}, ${place}`)}" data-href="/show/${esc(show.slug)}/" data-provisional="${show.provisional ? "1" : "0"}" data-featured="${show.featured ? "1" : "0"}" data-search="${esc(search)}">
    <a class="card-link" href="/show/${esc(show.slug)}/">
      <div class="when-block">
        <span class="wd">${esc(stack.wd)}</span>
        <span class="dn">${esc(stack.day)}</span>
        <span class="mo">${esc(stack.mon)}</span>
        ${stack.span ? `<span class="span">${esc(stack.span)}</span>` : ""}
      </div>
      <div>
        <h3>${esc(label)}</h3>
        <p class="where">${esc(show.venue.name)}, ${esc(place)}</p>
        ${times}
        ${dealers}
        <div class="pills">${pills(show)}</div>
      </div>
    </a>
  </article>`;
}

function months(shows) {
  const groups = [];
  for (const show of shows) {
    const key = monthKey(show.start);
    const last = groups[groups.length - 1];
    if (!last || last.key !== key) groups.push({ key, label: monthLabel(show.start), shows: [show] });
    else last.shows.push(show);
  }
  return groups
    .map(
      (group) => `<section class="month" data-month="${esc(group.key)}">
        <h2>${esc(group.label)}</h2>
        ${group.shows.map(card).join("")}
      </section>`,
    )
    .join("");
}

function typeLinks(current) {
  const all = `<a class="chip" href="/"${current ? "" : ' aria-current="page"'}>All types</a>`;
  const rest = TYPES.map(([key, label, href]) => {
    const here = current === key ? ' aria-current="page"' : "";
    return `<a class="chip" href="${href}"${here}>${label}</a>`;
  });
  return [all, ...rest].join("\n");
}

function signupForm() {
  return `<form class="nl" action="https://buttondown.com/api/emails/embed-subscribe/mineraldigger" method="post" data-thanks="/thanks/">
        <input type="email" name="email" required placeholder="you@example.com" aria-label="Email" autocomplete="email">
        <input type="text" name="metadata__postcode" placeholder="Your postcode (optional)" aria-label="Postcode" autocomplete="postal-code" maxlength="12">
        <input type="hidden" name="embed" value="1">
        <button class="pay" type="submit">Sign me up</button>
        <p class="small muted">A free Friday email of upcoming UK rock, gem, mineral, fossil and bead shows. Unsubscribe any time. Emails are sent by <a href="https://buttondown.com/" rel="noopener">Buttondown</a>; you'll get a link to confirm.</p>
      </form>`;
}

function homeSignup() {
  return `<section class="wrap newsletter" id="newsletter">
      <div>
        <p class="eyebrow">Stay in touch</p>
        <h2>The Friday email</h2>
        <p>Every Friday morning: a free email of the UK rock, gem, mineral, fossil and bead shows on that weekend. One email a week.</p>
      </div>
      ${signupForm()}
    </section>`;
}

const SERIES_NOTE = `<p class="fine">Rock, Gem &amp; Bead Shows are one series. Those weekends are listed under rock, gem and bead, and not under mineral or fossil, because the date list does not split them.</p>`;

function browseLinks() {
  return `<div class="chip-row" aria-label="Browse">
    <a class="chip" href="/this-weekend/">This weekend</a>
    <a class="chip" href="/county/">Counties</a>
    <a class="chip" href="/towns/">Towns</a>
  </div>`;
}

function whenFilters() {
  return `<div class="chip-row" role="group" aria-label="When">
          <button type="button" class="chip" data-when="all" aria-pressed="true">All upcoming</button>
          <button type="button" class="chip" data-when="weekend" aria-pressed="false">This weekend</button>
          <button type="button" class="chip" data-when="later" aria-pressed="false">Coming later</button>
        </div>`;
}

function placeLinks() {
  return `<div class="chip-row place-links" aria-label="Places">
            <a class="chip" href="/county/">Counties</a>
            <a class="chip" href="/towns/">Towns</a>
          </div>`;
}

export function renderListing({ site, path, title, description, ogTitle, ogDescription, heading, lede, shows, generated, home = false, typeLock = null, eyebrow = null, preface = "" }) {
  const ordered = byDate(shows);
  const featured = ordered.filter((show) => show.featured);
  const rest = ordered.filter((show) => !show.featured);
  const note = shows.some((show) => show.provisional)
    ? `<p class="fine">Dates marked provisional are printed that way by the organiser. Rock, Gem &amp; Bead Shows mark their 2027 list as provisional.</p>`
    : "";
  const eyebrowText = eyebrow || (home ? "UK shows directory" : "Show type");
  const countTail = home ? " from organiser websites, on one map." : "";
  const hero = `<section class="hero"><div class="wrap">
        <p class="eyebrow">${esc(eyebrowText)}</p>
        <h1>${esc(heading)}</h1>
        <p class="lede">${esc(lede)}</p>
        <p class="count-line"><strong id="result-count" data-total="${shows.length}">${shows.length} ${shows.length === 1 ? "show" : "shows"}</strong>${countTail ? `<span id="result-count-tail">${countTail}</span>` : ""}</p>
      </div></section>`;
  const body = `${hero}
    <div class="wrap">
      ${preface}
      <div class="filters">
        ${whenFilters()}
        <div class="chip-row chip-scroll" role="group" aria-label="Type">
          ${typeLinks(typeLock)}
        </div>
        <form id="search" class="search" role="search" action="" method="get">
          <input id="q" name="q" type="search" inputmode="search" enterkeyhint="search" autocomplete="off" aria-label="Postcode or town" placeholder="Postcode or town, e.g. RH16">
          <select id="radius" name="r" aria-label="Distance">
            <option value="15">15 miles</option>
            <option value="30" selected>30 miles</option>
            <option value="60">60 miles</option>
            <option value="100">100 miles</option>
          </select>
          <button id="go" type="submit">Search</button>
        </form>
        <p id="search-status" class="muted small" aria-live="polite"></p>
      </div>
      ${note}
      <div class="layout">
        <div>
          <noscript><p class="noscript">The map and the weekend filter need JavaScript. The list below is every upcoming show on this page.</p></noscript>
          <div id="empty" class="empty" hidden>
            <p id="empty-title"></p>
            <p id="empty-copy"></p>
          </div>
          <div id="show-list">
            ${featured.length ? `<section class="month"><h2>Featured</h2>${featured.map(card).join("")}</section>` : ""}
            ${months(rest)}
          </div>
          ${home ? placeLinks() : ""}
        </div>
        <aside class="map-col">
          <div class="map-frame"><div id="map" role="region" aria-label="Map of shows"></div></div>
          <p class="map-note">Green pins are confirmed dates. Copper pins are provisional. The pin sits on the venue postcode.</p>
        </aside>
      </div>
    </div>
    ${home ? homeSignup() : ""}`;
  return layout({
    site,
    path,
    title,
    description,
    ogTitle,
    ogDescription,
    body,
    map: true,
    generated,
    structuredData: home ? siteGraph(site) : "",
  });
}

export function renderHome(ctx) {
  const count = ctx.shows.length;
  const noun = count === 1 ? "show" : "shows";
  return renderListing({
    ...ctx,
    path: "/",
    title: "MineralDigger · UK rock, gem, mineral, fossil and bead shows map",
    description: `Free UK calendar of ${count} rock, gem, mineral, fossil and bead ${noun}. Dates, venues and entry on one map. Always confirm with the organiser before you travel.`,
    ogTitle: "MineralDigger · UK rock, gem, mineral, fossil and bead shows",
    ogDescription: `${count} ${noun} with dates, venues and entry on one map. Free calendar for collectors and traders. Check the organiser before you travel.`,
    heading: "UK rock, gem, mineral, fossil and bead shows on one map.",
    lede: "Dates, venues and entry in one place. Check before you travel; always confirm with the organiser.",
    home: true,
    typeLock: null,
    preface: "",
  });
}

export function renderType(ctx, key) {
  const label = TYPES.find((item) => item[0] === key)[1];
  const shows = ctx.shows.filter((show) => show.types.includes(key));
  return renderListing({
    ...ctx,
    shows,
    path: `/${key}/`,
    title: `${label} shows in the UK | MineralDigger`,
    description: TYPE_DESCRIPTION[key],
    heading: `${label} shows`,
    lede: TYPE_INTRO[key],
    home: false,
    typeLock: key,
    preface: `${browseLinks()}${["rock", "gem", "bead"].includes(key) ? SERIES_NOTE : ""}`,
  });
}

function shiftWeekend(range, days) {
  return {
    start: iso(addDays(parseISO(range.start), days)),
    end: iso(addDays(parseISO(range.end), days)),
  };
}

function weekendBlock(title, range, shows) {
  const when = formatRange(range.start, range.end);
  const list = shows.length
    ? `<div class="month">${shows.map(card).join("")}</div>`
    : `<p>Nothing listed for ${esc(title.toLowerCase())}.</p>`;
  return `<section>
      <h2>${esc(title)}</h2>
      <p class="fine">${esc(when)}</p>
      ${list}
    </section>`;
}

function laterDatesLine(count) {
  if (!count) return `<p class="fine">No further shows are listed after that. <a href="/">See all upcoming shows</a>.</p>`;
  const noun = count === 1 ? "show" : "shows";
  const verb = count === 1 ? "has" : "have";
  return `<p class="fine"><a href="/">${count} ${noun}</a> ${verb} dates after that.</p>`;
}

export function renderWeekend(ctx) {
  const weekend = thisWeekend(ctx.today);
  const next = shiftWeekend(weekend, 7);
  const now = byDate(ctx.shows.filter((show) => overlaps(show, weekend.start, weekend.end)));
  const later = byDate(ctx.shows.filter((show) => overlaps(show, next.start, next.end)));
  const span = formatRange(weekend.start, weekend.end);
  const noun = now.length === 1 ? "show" : "shows";
  const body = `<section class="hero"><div class="wrap">
        <p class="eyebrow">This weekend</p>
        <h1>Shows this weekend</h1>
        <p class="lede">${esc(span)}. ${now.length} ${noun} across the UK, from organiser websites. Check with the organiser before you travel.</p>
      </div></section>
    <div class="wrap">
      ${browseLinks()}
      <div class="layout">
        <div>
          <noscript><p class="noscript">The map needs JavaScript. The list on this page is complete without it.</p></noscript>
          ${weekendBlock("This weekend", weekend, now)}
          ${weekendBlock("Next weekend", next, later)}
          ${laterDatesLine(ctx.shows.filter((show) => show.start > next.end).length)}
        </div>
        <aside class="map-col">
          <div class="map-frame"><div id="map" role="region" aria-label="Map of shows"></div></div>
          <p class="map-note">Green pins are confirmed dates. Copper pins are provisional. The pin sits on the venue postcode.</p>
        </aside>
      </div>
    </div>`;
  return layout({
    site: ctx.site,
    path: "/this-weekend/",
    title: `Shows this weekend (${span}) | MineralDigger`,
    description: `Rock, gem, mineral, fossil and bead shows on ${span}. Dates, venues and entry from organiser sites.`,
    body,
    map: true,
    generated: ctx.generated,
  });
}

function indexPage({ site, path, title, description, eyebrow, heading, lede, generated, inner }) {
  const body = `<section class="hero"><div class="wrap">
        <p class="eyebrow">${esc(eyebrow)}</p>
        <h1>${esc(heading)}</h1>
        <p class="lede">${esc(lede)}</p>
      </div></section>
    <div class="wrap">
      ${browseLinks()}
      ${inner}
    </div>`;
  return layout({ site, path, title, description, body, generated });
}

export function renderCountyIndex(ctx, counties) {
  const grouped = new Map();
  for (const county of byNation(counties.values())) {
    if (!grouped.has(county.nation)) grouped.set(county.nation, []);
    grouped.get(county.nation).push(county);
  }
  const inner = [...grouped.entries()]
    .map(([nation, list]) => {
      const chips = list
        .map((county) => `<a class="chip" href="/county/${county.slug}/">${esc(county.name)} <b>${county.shows.length}</b></a>`)
        .join("");
      return `<section class="month"><h2>${esc(nation)}</h2><div class="chip-row">${chips}</div></section>`;
    })
    .join("");
  const count = counties.size;
  return indexPage({
    site: ctx.site,
    path: "/county/",
    title: "Shows by county | MineralDigger",
    description: "UK rock, gem, mineral, fossil and bead shows by county. Dates and venues from organiser websites.",
    eyebrow: "Places",
    heading: "Shows by county",
    lede: `${count} ${count === 1 ? "county has" : "counties have"} an upcoming show. Each listing is checked against the organiser's own site.`,
    generated: ctx.generated,
    inner,
  });
}

export function renderTownIndex(ctx, towns) {
  const chips = byNation(towns.values())
    .map((town) => `<a class="chip" href="/town/${town.slug}/">${esc(town.name)} <b>${town.shows.length}</b></a>`)
    .join("");
  const count = towns.size;
  return indexPage({
    site: ctx.site,
    path: "/towns/",
    title: "Shows by town | MineralDigger",
    description: "UK rock, gem, mineral, fossil and bead shows by town. Dates and venues from organiser websites.",
    eyebrow: "Places",
    heading: "Shows by town",
    lede: `${count} ${count === 1 ? "town has" : "towns have"} an upcoming show. Open a town for the dates and the venue.`,
    generated: ctx.generated,
    inner: `<div class="chip-row">${chips}</div>`,
  });
}

export function renderCounty(ctx, county, towns) {
  const local = [...towns.values()]
    .filter((town) => town.county === county.name)
    .sort((a, b) => a.name.localeCompare(b.name, "en-GB"));
  const townChips = local
    .map((town) => `<a class="chip" href="/town/${town.slug}/">${esc(town.name)}</a>`)
    .join("");
  return renderListing({
    ...ctx,
    shows: county.shows,
    path: `/county/${county.slug}/`,
    title: `Shows in ${county.name} | MineralDigger`,
    description: `Upcoming rock, gem, mineral, fossil and bead shows in ${county.name}. Dates, venues and entry from organiser sites.`,
    heading: `Shows in ${county.name}`,
    lede: `Upcoming shows in ${county.name}. Dates and venues come from organiser websites. Check with the organiser before you travel.`,
    eyebrow: county.nation,
    preface: `${browseLinks()}${townChips ? `<div class="chip-row" aria-label="Towns">${townChips}</div>` : ""}`,
  });
}

export function renderTown(ctx, town) {
  const countyBit = town.county ? `, ${town.county}` : "";
  return renderListing({
    ...ctx,
    shows: town.shows,
    path: `/town/${town.slug}/`,
    title: `Shows in ${town.name} | MineralDigger`,
    description: `Upcoming rock, gem, mineral, fossil and bead shows in ${town.name}${countyBit}. Dates, venues and entry from organiser sites.`,
    heading: `Shows in ${town.name}`,
    lede: `Upcoming shows in ${town.name}${countyBit}. Dates and venues come from organiser websites. Check with the organiser before you travel.`,
    eyebrow: town.county || town.nation,
    preface: `${browseLinks()}${town.county ? `<p class="fine"><a href="/county/${slugify(town.county)}/">${esc(town.county)}</a></p>` : ""}`,
  });
}

function placeLine(show) {
  return [show.venue.town, show.venue.county, show.venue.nation].filter(Boolean).join(", ");
}

function londonOffsetMinutes(utcMs) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Europe/London",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(utcMs));
  const pick = (type) => Number(parts.find((part) => part.type === type).value);
  const asUtc = Date.UTC(pick("year"), pick("month") - 1, pick("day"), pick("hour"), pick("minute"));
  return Math.round((asUtc - utcMs) / 60000);
}

// Midnight in the UK on the catalogue refresh day, with the offset that applied then.
export function offerValidFrom(dateISO) {
  const day = String(dateISO).slice(0, 10);
  const [year, month, date] = day.split("-").map(Number);
  const utcMidnight = Date.UTC(year, month - 1, date, 0, 0, 0);
  const offset = londonOffsetMinutes(utcMidnight - londonOffsetMinutes(utcMidnight) * 60000);
  const sign = offset >= 0 ? "+" : "-";
  const abs = Math.abs(offset);
  const hours = String(Math.floor(abs / 60)).padStart(2, "0");
  const minutes = String(abs % 60).padStart(2, "0");
  return `${day}T00:00:00${sign}${hours}:${minutes}`;
}

function eventOffer(show, pageUrl, validFrom) {
  const free = show.entry.kind === "free" || show.entry.adult_gbp === 0;
  const priced = show.entry.kind === "paid" && Number.isFinite(show.entry.adult_gbp) && show.entry.adult_gbp > 0;
  // An Offer without price and priceCurrency is incomplete. Search Console warns on it.
  // Unknown admission omits offers. Publishing 0 would claim the show is free.
  if (!free && !priced) return null;
  return {
    "@type": "Offer",
    price: free ? "0" : String(show.entry.adult_gbp),
    priceCurrency: "GBP",
    availability: "https://schema.org/InStock",
    url: pageUrl,
    validFrom,
  };
}

function jsonLd(show, site, generated) {
  const pageUrl = new URL(`/show/${show.slug}/`, site.url).href;
  const organizer = {
    "@type": "Organization",
    name: show.organiser.name,
  };
  if (show.organiser.url) organizer.url = show.organiser.url;
  const refreshed = show.source?.retrieved || generated;
  const data = {
    "@context": "https://schema.org",
    "@type": "Event",
    name: show.name,
    startDate: show.start,
    endDate: show.end,
    eventAttendanceMode: "https://schema.org/OfflineEventAttendanceMode",
    eventStatus: "https://schema.org/EventScheduled",
    description: visitorSummary(show) || undefined,
    image: [new URL("/og-image.jpg", site.url).href],
    url: pageUrl,
    location: {
      "@type": "Place",
      name: show.venue.name,
      address: {
        "@type": "PostalAddress",
        streetAddress: show.venue.street || undefined,
        addressLocality: show.venue.town,
        addressRegion: show.venue.county,
        postalCode: show.venue.postcode,
        addressCountry: "GB",
      },
    },
    organizer,
    // Mineral shows are not performances. The organiser fills performer so Search Console stops flagging the field.
    performer: { ...organizer },
  };
  const offer = eventOffer(show, pageUrl, offerValidFrom(refreshed));
  if (offer) data.offers = offer;
  // Set only when entry says free or paid. Unknown admission leaves it off.
  if (show.entry.kind === "free" || show.entry.adult_gbp === 0) data.isAccessibleForFree = true;
  else if (show.entry.kind === "paid") data.isAccessibleForFree = false;
  return `<script type="application/ld+json">${JSON.stringify(data).replace(/</g, "\\u003c")}</script>`;
}

function whereLinks(show, places) {
  const townSlug = slugify(show.venue.town);
  const countySlug = slugify(show.venue.county);
  const town = places?.towns?.has(townSlug)
    ? `<a href="/town/${townSlug}/">${esc(show.venue.town)}</a>`
    : esc(show.venue.town);
  const county = places?.counties?.has(countySlug)
    ? `<a href="/county/${countySlug}/">${esc(show.venue.county)}</a>`
    : esc(show.venue.county);
  return [town, county, esc(show.venue.nation)].filter(Boolean).join(", ");
}

const INTERNAL_NOTE = /year is matched|year was matched|matches the weekday|does not print the year|does not print them|college contact page|organiser homepage|date line does not|printed under the heading|provisional 2027 dates|satnav postcode|venue-supplements|source note/i;

function publicNote(value) {
  const text = String(value || "").trim();
  if (!text || INTERNAL_NOTE.test(text)) return "";
  return text;
}

function breadcrumb(show, site, places) {
  const crumbs = [{ name: "Home", href: "/" }];
  if (show.venue.county) {
    const slug = slugify(show.venue.county);
    crumbs.push({ name: show.venue.county, href: places?.counties?.has(slug) ? `/county/${slug}/` : "" });
  }
  if (show.venue.town) {
    const slug = slugify(show.venue.town);
    crumbs.push({ name: show.venue.town, href: places?.towns?.has(slug) ? `/town/${slug}/` : "" });
  }
  const html = `<nav class="crumbs" aria-label="Breadcrumb">${crumbs
    .map((crumb, index) => {
      const label = crumb.href ? `<a href="${crumb.href}">${esc(crumb.name)}</a>` : `<span>${esc(crumb.name)}</span>`;
      const sep = index ? `<span class="crumb-sep" aria-hidden="true">›</span> ` : "";
      return `${sep}${label}`;
    })
    .join(" ")}</nav>`;
  const data = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: crumbs.map((crumb, index) => {
      const item = { "@type": "ListItem", position: index + 1, name: crumb.name };
      if (crumb.href) item.item = new URL(crumb.href, site.url).href;
      return item;
    }),
  };
  const script = `<script type="application/ld+json">${JSON.stringify(data).replace(/</g, "\\u003c")}</script>`;
  return { html, script };
}

function mapsDirections(show) {
  const destination = [show.venue.name, show.venue.street, show.venue.town, show.venue.postcode].filter(Boolean).join(", ");
  const query = destination || (Number.isFinite(Number(show.venue.lat)) ? `${show.venue.lat},${show.venue.lng}` : "");
  if (!query) return "";
  return `https://www.google.com/maps/dir/?api=1&destination=${encodeURIComponent(query)}`;
}

export function renderShow({ site, show, generated, todayISO, places = null }) {
  const past = show.end < todayISO;
  const banners = [];
  if (past) banners.push(`<div class="callout past"><p>This date has passed. Check the organiser for the next one.</p></div>`);
  if (show.provisional) banners.push(`<div class="callout"><p>The organiser lists this date as provisional. Check their site before you travel.</p></div>`);
  const address = [show.venue.street, placeLine(show), show.venue.postcode].filter(Boolean).join(", ");
  const whenBits = [`<p>${esc(formatRange(show.start, show.end))}</p>`];
  const opening = publicNote(show.times.summary);
  const timeNotes = publicNote(show.times.notes);
  if (opening) whenBits.push(`<p>${esc(opening)}</p>`);
  if (timeNotes) whenBits.push(`<p>${esc(timeNotes)}</p>`);
  const entryNotes = entryDetail(show.entry);
  const facts = [
    ["Venue", `${show.venue.name}, ${address}`],
    ["Organiser", show.organiser.name],
  ];
  if (entryNotes) facts.unshift(["Entry", `${entryLabel(show.entry)}. ${entryNotes}`]);
  if (show.dealers) facts.push(["Dealers", `${show.dealers} on the organiser page`]);
  const parking = publicNote(show.parking);
  const access = publicNote(show.access_notes);
  if (parking) facts.push(["Parking", parking]);
  if (access) facts.push(["Access", access]);
  const factHtml = `<div class="fact"><h2>When</h2>${whenBits.join("")}</div>${facts
    .map(([label, value]) => `<div class="fact"><h2>${esc(label)}</h2><p>${esc(value)}</p></div>`)
    .join("")}`;
  const phone = show.organiser.phone ? `<p>Phone: <a href="tel:${esc(show.organiser.phone.replace(/\s+/g, ""))}">${esc(show.organiser.phone)}</a></p>` : "";
  const email = show.organiser.email ? `<p>Email: <a href="mailto:${esc(show.organiser.email)}">${esc(show.organiser.email)}</a></p>` : "";
  const website = show.organiser.url ? `<p><a href="${esc(show.organiser.url)}">Organiser website</a></p>` : "";
  const retrieved = show.source.url
    ? `<p>Retrieved ${esc(formatDay(show.source.retrieved))} from <a href="${esc(show.source.url)}">${esc(show.source.url)}</a>.</p>`
    : `<p>Retrieved ${esc(formatDay(show.source.retrieved))}.</p>`;
  const also = (show.source.also || [])
    .map((item) => `<p>Also: <a href="${esc(item.url)}">${esc(item.url)}</a></p>`)
    .join("");
  const types = show.types.map((type) => `<a href="/${esc(type)}/">${esc(type)}</a>`).join(", ");
  const directions = mapsDirections(show);
  const crumbs = breadcrumb(show, site, places);
  const placeNote = publicNote(show.venue.place_note);
  const label = listedName(show);
  const body = `<article class="page"><div class="wrap-narrow">
      ${crumbs.html}
      <h1>${esc(label)}</h1>
      <p class="show-date">${esc(formatRange(show.start, show.end))}</p>
      <p class="lede">${esc(visitorSummary(show))}</p>
      <div class="pills">${pills(show, false)}</div>
      ${banners.join("")}
      <p>Types: ${types}</p>
      <p>Where: ${whereLinks(show, places)}</p>
      <div class="facts">${factHtml}</div>
      ${phone}
      ${email}
      ${website}
      <div class="actions">
        <a href="/show/${esc(show.slug)}/event.ics">Add to calendar</a>
        ${directions ? `<a href="${esc(directions)}" rel="noopener" target="_blank">Directions</a>` : ""}
        <a href="/feature/?show=${esc(show.slug)}">Feature your show</a>
      </div>
      <div class="map-frame" style="height:320px;min-height:0"><div id="detail-map" data-lat="${esc(show.venue.lat)}" data-lng="${esc(show.venue.lng)}" role="region" aria-label="Map of the venue"></div></div>
      <p class="map-note">The pin is the venue postcode, not a surveyed entrance.${placeNote ? ` ${esc(placeNote)}` : ""}</p>
      <h2>Where this date came from</h2>
      ${retrieved}
      ${also}
      <p>Always check the organiser's page for times, tickets and any changes before you set off.</p>
    </div></article>
    ${jsonLd(show, site, generated)}
    ${crumbs.script}`;
  return layout({
    site,
    path: `/show/${show.slug}/`,
    title: `${label}, ${formatRange(show.start, show.end)} | MineralDigger`,
    description: `${visitorSummary(show)} ${placeLine(show)}.`.trim(),
    body,
    map: true,
    generated,
  });
}

function payControl(href, label, ready, id = "") {
  if (!ready) return `<p class="soon">Coming soon</p>`;
  const idAttr = id ? ` id="${esc(id)}"` : "";
  return `<a class="pay" href="${esc(href)}"${idAttr}>${esc(label)}</a>`;
}

function mailLink(address) {
  return `<a href="mailto:${esc(address)}">${esc(address)}</a>`;
}

function paymentCopy(ready, prices) {
  const sponsors = mailLink(SPONSORS_EMAIL);
  const open = Object.values(ready).filter(Boolean).length;
  const allOpen = open === Object.keys(ready).length;
  const noneOpen = open === 0;
  if (allOpen) {
    return {
      notice: "",
      featureSteps: `<ol>
        <li>Make sure the show is listed. If it is not, <a href="/submit/">submit it free</a> first.</li>
        <li>Choose an option and pay by card through Stripe. At checkout, say which show it is, or which organiser for the year pass.</li>
        <li>You get a Stripe receipt by email. We feature the show within one working day, and we email if we need anything else.</li>
      </ol>`,
      sponsorSteps: `<ol>
        <li>Choose the site, at £${prices.site_sponsor} a month, or one Friday email at £${prices.friday_email}.</li>
        <li>Pay by card through Stripe.</li>
        <li>Email your logo, a one-line message, and which package to ${sponsors}.</li>
        <li>Your slot is live within one working day of receiving your logo and message.</li>
      </ol>`,
    };
  }
  if (noneOpen) {
    return {
      notice: `<div class="notice">
        <p>Card payment is coming soon. The prices above are the ones we will charge. Until then, email ${sponsors}.</p>
      </div>`,
      featureSteps: `<ol>
        <li>Make sure the show is listed. If it is not, <a href="/submit/">submit it free</a> first.</li>
        <li>Card payment for a featured show or a year pass is coming soon.</li>
        <li>Until then, email ${sponsors} with the show, or the organiser for a year pass.</li>
      </ol>`,
      sponsorSteps: `<ol>
        <li>Choose the site, at £${prices.site_sponsor} a month, or one Friday email at £${prices.friday_email}.</li>
        <li>Card payment is coming soon.</li>
        <li>Email your logo, a one-line message, and which package to ${sponsors}.</li>
        <li>Your slot is live within one working day of receiving your logo and message.</li>
      </ol>`,
    };
  }
  return {
    notice: `<div class="notice">
        <p>Some card payments are still coming soon. Pay only where a button is shown. For the rest, email ${sponsors}.</p>
      </div>`,
    featureSteps: `<ol>
        <li>Make sure the show is listed. If it is not, <a href="/submit/">submit it free</a> first.</li>
        <li>Pay by card through Stripe where a button is shown. At checkout, say which show it is, or which organiser for the year pass.</li>
        <li>You get a Stripe receipt by email. We feature the show within one working day, and we email if we need anything else.</li>
      </ol>`,
    sponsorSteps: `<ol>
        <li>Choose the site, at £${prices.site_sponsor} a month, or one Friday email at £${prices.friday_email}.</li>
        <li>Pay by card through Stripe where a button is shown. Options marked coming soon are not open yet.</li>
        <li>Email your logo, a one-line message, and which package to ${sponsors}.</li>
        <li>Your slot is live within one working day of receiving your logo and message.</li>
      </ol>`,
  };
}

export function renderFeature({ site, stripe, generated }) {
  const prices = stripe.prices;
  const links = stripe.links;
  const ready = {
    featured_show: stripeReady(links.featured_show),
    year_pass: stripeReady(links.year_pass),
    site_sponsor: stripeReady(links.site_sponsor),
    friday_email: stripeReady(links.friday_email),
  };
  const copy = paymentCopy(ready, prices);
  const body = `<article class="page"><div class="wrap">
      <p class="eyebrow">For organisers and sponsors</p>
      <h1 id="feature-heading">Feature a show</h1>
      <p class="lede">Put your show in front of people looking for rock, gem, mineral, fossil and bead shows. Listing is free. Featuring and sponsorship are optional, and they are labelled when they are on.</p>
      <div id="feature-pick" class="callout" hidden></div>
      <div class="ladder">
        <section class="price-card">
          <h2>Free listing</h2>
          <p class="price">£0</p>
          <ul>
            <li>On the map and in the list</li>
            <li>A page with the date, venue and entry</li>
            <li>Shown on the type pages it belongs to</li>
          </ul>
          <a class="pay" href="/submit/">Submit a show</a>
        </section>
        <section class="price-card lead">
          <h2>Featured show</h2>
          <p class="price">£${prices.featured_show}</p>
          <ul>
            <li>Pinned at the top of the list for 4 weeks, or until the show date if that is sooner</li>
            <li>A highlighted pin on the map</li>
            <li>A Featured label on the list and the show page</li>
            <li>Featured in the Friday email sent the week of your show</li>
          </ul>
          ${payControl(links.featured_show, `Pay £${prices.featured_show} with Stripe`, ready.featured_show, "featured-pay")}
        </section>
        <section class="price-card">
          <h2>Year pass</h2>
          <p class="price">£${prices.year_pass} <small>for 12 months</small></p>
          <ul>
            <li>Every show you organise is featured for 12 months from the day you pay</li>
            <li>Same pin, label and Friday slot as a single featured show</li>
          </ul>
          ${payControl(links.year_pass, `Pay £${prices.year_pass} with Stripe`, ready.year_pass)}
        </section>
        <section class="price-card">
          <h2>Site sponsor</h2>
          <p class="price">£${prices.site_sponsor} <small>a month</small></p>
          <ul>
            <li>Your name, one short line and a link on the homepage and the type pages</li>
            <li>Labelled as a sponsor</li>
            <li>Monthly. You can cancel any time.</li>
          </ul>
          ${payControl(links.site_sponsor, `Pay £${prices.site_sponsor} a month with Stripe`, ready.site_sponsor)}
        </section>
        <section class="price-card">
          <h2>Friday email</h2>
          <p class="price">£${prices.friday_email} <small>an issue</small></p>
          <ul>
            <li>The only sponsor in that Friday email</li>
            <li>Sponsor any Friday you choose (not tied to a show date)</li>
          </ul>
          ${payControl(links.friday_email, `Pay £${prices.friday_email} with Stripe`, ready.friday_email)}
        </section>
      </div>
      <p>See the <a href="/terms/">terms</a> for what is included, when it goes live, renewals and refunds.</p>
      ${copy.notice}
      <h2>How it works</h2>
      ${copy.featureSteps}
      <p>Free listings stay free. Featured shows are labelled.</p>
      <h2>What a sponsor looks like</h2>
      <div class="example">
        <p class="eyebrow">Example only. Not a real sponsor.</p>
        <p><strong>Northstone Lapidary.</strong> Rough, slabs and findings for collectors.</p>
      </div>
      <h2>How sponsoring works</h2>
      ${copy.sponsorSteps}
      <p>Sponsors are labelled, and the link is marked as sponsored. We take sponsors that suit collectors of rocks, gems, minerals, fossils and beads.</p>
    </div></article>
    <script src="/js/feature.js" defer></script>`;
  return layout({
    site,
    path: "/feature/",
    title: "Feature a show | MineralDigger",
    description: `Featured show £${prices.featured_show}, year pass £${prices.year_pass}, site sponsor £${prices.site_sponsor} a month, Friday email £${prices.friday_email} an issue.`,
    body,
    generated,
  });
}

export function renderThanks({ site, generated }) {
  const email = site.email;
  const sponsors = mailLink(SPONSORS_EMAIL);
  const body = `<article class="page"><div class="wrap-narrow prose">
      <p class="eyebrow">Payment received</p>
      <h1>Thank you</h1>
      <p class="lede">Thank you. Your payment has gone through. You get a Stripe receipt by email. We feature the show within one working day (with a year pass, all of that organiser's shows for 12 months from the day you pay), and we email if we need anything else.</p>
      <p>Featured show: Featured in the Friday email sent the week of your show. Friday email: Sponsor any Friday you choose (not tied to a show date).</p>
      <p><strong>Sponsoring the site or the Friday email?</strong> Please email your logo, a one-line message, and which package you paid for to ${sponsors}. Your slot is live within one working day of receiving your logo and message.</p>
      <p>See the <a href="/terms/">terms</a> for what is included, when it goes live, renewals and refunds.</p>
      <p class="fine">Questions about your listing? Reply to the Stripe receipt or email ${mailLink(email)}.</p>
      <div class="actions">
        <a href="/">Home</a>
        <a href="/">Upcoming shows</a>
      </div>
    </div></article>`;
  return layout({
    site,
    path: "/thanks/payment/",
    title: "Payment received | MineralDigger",
    description: "Payment received for a MineralDigger featured show or sponsorship.",
    body,
    generated,
    robots: "noindex",
  });
}

export function renderSubmit({ site, generated }) {
  const types = TYPES.map(
    ([key, label]) => `<label><input type="checkbox" name="types" value="${key}"> ${label}</label>`,
  ).join("");
  const body = `<article class="page"><div class="wrap-narrow">
      <p class="eyebrow">Free listing</p>
      <h1>Add your show</h1>
      <p class="lede">Tell us about a rock, gem, mineral, fossil or bead show. We check the organiser website before it goes on the map.</p>
      <p>Read <a href="/about/">how we list shows</a>.</p>
      <div id="form-errors" class="errors" hidden></div>
      <div id="form-ok" class="ok" hidden>
        <p id="ok-line"></p>
        <label>Copy of your listing
          <textarea id="receipt" class="receipt" readonly></textarea>
        </label>
      </div>
      <form id="submit-form" class="stack" method="post" action="/api/submit">
        <div class="hp" aria-hidden="true">
          <label>Company website <input type="text" name="company_website" tabindex="-1" autocomplete="off"></label>
        </div>
        <div class="row-2">
          <label class="field">Organiser name <input name="organiser_name" type="text" required maxlength="120" autocomplete="organization"></label>
          <label class="field">Email <input name="email" type="email" required maxlength="160" autocomplete="email"></label>
        </div>
        <div class="row-2">
          <label class="field">Phone <span class="hint">optional</span><input name="phone" type="tel" maxlength="40" autocomplete="tel"></label>
          <label class="field">Show website <span class="hint">optional</span><input name="website" type="url" maxlength="300" placeholder="https://"></label>
        </div>
        <label class="field">Show name <input name="show_name" type="text" required maxlength="160"></label>
        <fieldset>
          <legend>Types</legend>
          <div class="checks">${types}</div>
        </fieldset>
        <div class="row-2">
          <label class="field">Start date <input name="start_date" type="date" required></label>
          <label class="field">End date <input name="end_date" type="date" required></label>
        </div>
        <label class="field">Opening times <span class="hint">optional</span><input name="times" type="text" maxlength="200" placeholder="Saturday 10:00 to 17:00"></label>
        <label class="field">Venue <input name="venue_name" type="text" required maxlength="160"></label>
        <label class="field">Street <span class="hint">optional</span><input name="street" type="text" maxlength="160"></label>
        <div class="row-2">
          <label class="field">Town <input name="town" type="text" required maxlength="80"></label>
          <label class="field">Postcode <input name="postcode" type="text" required maxlength="12" placeholder="TW16 5AQ"></label>
        </div>
        <div class="row-2">
          <label class="field">Entry
            <select name="entry_kind" required>
              <option value="unknown">Check with organiser</option>
              <option value="free">Free</option>
              <option value="paid">Paid</option>
            </select>
          </label>
          <label class="field">Adult price in pounds <span class="hint">if paid</span><input name="entry_price" type="text" inputmode="numeric" maxlength="3" placeholder="6"></label>
        </div>
        <label class="field">Entry notes <span class="hint">optional</span><input name="entry_notes" type="text" maxlength="300" placeholder="Under 12s free"></label>
        <label class="field">Anything else <span class="hint">optional</span><textarea name="notes" maxlength="2000"></textarea></label>
        <div class="confirm">
          <label><input type="checkbox" name="confirm_scope" value="yes" required> This is a rock, gem, mineral, fossil or bead show.</label>
          <label><input type="checkbox" name="confirm_permission" value="yes" required> I am the organiser, or I have their permission to send this.</label>
        </div>
        <button class="pay" type="submit">Send listing</button>
      </form>
    </div></article>
    <script type="module" src="/js/submit.js"></script>`;
  return layout({
    site,
    path: "/submit/",
    title: "Submit a show | MineralDigger",
    description: "Send a rock, gem, mineral, fossil or bead show. Listing is free. We check the organiser website before it goes on the map.",
    body,
    generated,
  });
}

export function renderAbout({ site, generated }) {
  const body = `<article class="page"><div class="wrap-narrow prose">
      <p class="eyebrow">About this list</p>
      <h1>How MineralDigger lists shows</h1>
      <p>MineralDigger lists rock, gem, mineral, fossil and bead shows across the UK. We pull dates from organiser websites and from shows submitted here, then put them on a map so you can see what is on this weekend and later in the year.</p>
      <p>We focus on trade and collector shows: Rock, Gem &amp; Bead circuits, society mineral and fossil shows, and gem expos. We do not list mind-body-spirit or psychic shows.</p>
      <p>Rock, Gem &amp; Bead Shows publish one date list. Those weekends are tagged rock, gem and bead. A mineral or fossil page includes a show only when that programme names the type. If a page does not print a door price, the listing says check with the organiser.</p>
      <p>Browse <a href="/this-weekend/">this weekend</a>, <a href="/county/">counties</a> and <a href="/towns/">towns</a>.</p>
      <p>Always check the organiser's page for times, tickets and any changes before you set off.</p>
      <h2>Where a date comes from</h2>
      <p>Each show page names the organiser URL and the day we read it. If a page prints a weekday and a day of the month but no year, we use that date only when the weekday matches, and we say so on the show page. If a date is unclear, we leave it off.</p>
      <p>Rock, Gem &amp; Bead Shows mark their 2027 list as provisional. Those rows stay on the map with a provisional label.</p>
      <p>Map pins are the venue postcode, not a surveyed gate.</p>
      <h2>Corrections</h2>
      <p>Organisers can <a href="/submit/">submit a show</a> or send a correction the same way. We would rather keep a listing incomplete than invent a time or a price.</p>
    </div></article>`;
  return layout({
    site,
    path: "/about/",
    title: "About this list | MineralDigger",
    description: "MineralDigger lists rock, gem, mineral, fossil and bead shows across the UK from organiser websites and submitted shows.",
    body,
    generated,
  });
}

const DIGEST_DESCRIPTION = "The Friday email: a free weekly list of UK rock, gem, mineral, fossil and bead shows for the coming weekend.";

export function renderDigest({ site, generated }) {
  const body = `<article class="page"><div class="wrap-narrow prose">
      <p class="eyebrow">Free weekly email</p>
      <h1>The Friday email</h1>
      <p class="lede">Every Friday morning: a free email of the UK rock, gem, mineral, fossil and bead shows on that weekend.</p>
      ${signupForm()}
    </div></article>`;
  return layout({
    site,
    path: NEWSLETTER_PATH,
    title: "The Friday email | MineralDigger",
    description: DIGEST_DESCRIPTION,
    body,
    generated,
  });
}

export function renderSignupThanks({ site, generated }) {
  const body = `<article class="page"><div class="wrap-narrow prose">
      <p class="eyebrow">Nearly there</p>
      <h1>Check your inbox to confirm</h1>
      <p class="lede">We've just sent you a short email from MineralDigger. Tap the confirm link in it and you're on the list for the Friday show email.</p>
      <p>It can take a minute or two to arrive. If you can't see it, check your spam or Promotions folder.</p>
      <p class="fine">Signed up by mistake? Just ignore that email and you won't hear from us.</p>
      <div class="actions">
        <a href="/">Upcoming shows</a>
        <a href="/this-weekend/">This weekend</a>
      </div>
    </div></article>`;
  return layout({
    site,
    path: "/thanks/",
    title: "Check your inbox | MineralDigger",
    description: "Confirm your MineralDigger Friday email sign-up.",
    body,
    generated,
    robots: "noindex",
  });
}

export function renderPrivacy({ site, generated }) {
  const email = site.email;
  const body = `<article class="page"><div class="wrap-narrow prose">
      <p class="eyebrow">Privacy</p>
      <h1>Privacy</h1>
      <p class="fine">Last updated 29 October 2026</p>
      <p class="lede">MineralDigger (mineraldigger.com) is run by Alan Conlon in Ireland. This page explains what information we collect, why, who handles it for us, and how long we keep it. Questions or requests: <a href="mailto:${esc(email)}">${esc(email)}</a>.</p>
      <h2>Browsing the site</h2>
      <p>You do not need an account to use MineralDigger. We use Cloudflare Web Analytics, which is cookieless and does not track you across sites. It counts page views and gives rough visitor numbers. It does not collect personal data. Web Analytics on this site runs in lite mode. In lite mode Cloudflare does not add the analytics script for visitors from the EU, so those visits are not counted. Cloudflare's notes on the same setting also cover visitors whose traffic reaches a data centre in the UK or the rest of the EEA, so those visits may not be counted either. MineralDigger does not use advertising trackers or its own cookies. Cloudflare may set a security cookie called __cf_bm when it checks that a visitor is not a bot. It expires after 30 minutes of inactivity. It is not an analytics cookie, and Cloudflare does not use it to track you from site to site.</p>
      <ul>
        <li><strong>Hosting.</strong> The site is hosted by Cloudflare. Like any web host, Cloudflare handles the technical details of each visit (such as your IP address and browser type) to deliver pages and protect the site from abuse. Cloudflare Web Analytics is part of that hosting. It is cookieless, it does not collect personal data, and in lite mode it is not added for visitors from the EU.</li>
        <li><strong>Search and maps.</strong> A postcode search, or a place name that is not already a town on the page, is sent to postcodes.io so shows can be sorted by distance. postcodes.io sees your IP address and the place you search for. A town that is already listed is matched on this page. Maps load tiles from OpenStreetMap, which sees your IP address when your browser requests a tile. The map code is served from this site.</li>
        <li><strong>On your phone.</strong> If you add MineralDigger to your home screen, pages you open are saved on that phone so they still open with a weak signal. That copy stays on your device. We do not receive it.</li>
      </ul>
      <h2>The Friday email</h2>
      <p>If you <a href="${NEWSLETTER_PATH}">sign up for the Friday email</a>, we collect your email address, and your postcode if you choose to give it, so we can send the weekly list of shows. Sign-ups and sending are handled by Buttondown. Every email has an unsubscribe link. We keep your address until you unsubscribe.</p>
      <h2>Submitting a show</h2>
      <p>The <a href="/submit/">submit form</a> asks for the show details (name, types, dates, times, venue, street, town, postcode, entry and website) and the organiser's name, email and phone. We use this to check and list the show, and to contact you about it. The form is sent by email to <a href="mailto:${esc(email)}">${esc(email)}</a> through Cloudflare. The show details are published on the site. Your email address is not. We keep submission emails while the show is listed and for a reasonable time afterwards in case of questions, and will delete them sooner if you ask.</p>
      <h2>Payments</h2>
      <p>Featured listings and sponsorships are paid through Stripe. Stripe processes the payment, and we never see your full card details. We receive your name, email address, billing address where Stripe asks for it, and what you tell checkout (which show it is, or which organiser for a year pass), so we can set up what you paid for. We keep payment records for as long as Irish tax law requires (generally six years). Keeping them is a legal obligation.</p>
      <h2>Emailing us</h2>
      <p>If you email <a href="mailto:${esc(email)}">${esc(email)}</a>, your message and email address are stored in Google's Gmail. We use them only to reply and to deal with your request.</p>
      <h2>Who handles your information</h2>
      <ul>
        <li><strong>Buttondown</strong>: Friday email sign-ups and sending.</li>
        <li><strong>Stripe</strong>: payments for featured shows and sponsorships.</li>
        <li><strong>Cloudflare</strong>: hosting, Web Analytics, and passing on the submission form.</li>
        <li><strong>postcodes.io</strong>: postcode and place lookups when you search by distance.</li>
        <li><strong>Google (Gmail)</strong>: our email inbox.</li>
      </ul>
      <p>Some of these services are based in, or process data in, the US. They rely on the EU-US Data Privacy Framework or standard contractual clauses, as set out in their own terms.</p>
      <p>We do not sell your information or share it with anyone beyond the services named on this page.</p>
      <h2>Your rights</h2>
      <p>Under the GDPR you can ask us for a copy of the information we hold about you, ask us to correct it, or ask us to delete it. Email <a href="mailto:${esc(email)}">${esc(email)}</a>. You can unsubscribe from the Friday email at any time using the link in any email. If you are unhappy with how we have handled your information, you can complain to Ireland's Data Protection Commission at <a href="https://www.dataprotection.ie/" rel="noopener">dataprotection.ie</a>.</p>
    </div></article>`;
  return layout({
    site,
    path: "/privacy/",
    title: "Privacy | MineralDigger",
    description: "How MineralDigger handles personal information for the UK show list, the submit form, Stripe payments and the Friday email.",
    body,
    generated,
  });
}

export function renderTerms({ site, stripe, generated }) {
  const prices = stripe.prices;
  const email = mailLink(site.email);
  const sponsors = mailLink(SPONSORS_EMAIL);
  const body = `<article class="page"><div class="wrap-narrow prose">
      <p class="eyebrow">Terms</p>
      <h1>Terms</h1>
      <p class="fine">Last updated 29 October 2026</p>
      <p class="lede">These terms cover featured listings and sponsorship on MineralDigger (mineraldigger.com). Listing on MineralDigger is free. These terms only apply when you pay for something.</p>
      <h2>What you can buy</h2>
      <ul>
        <li>Featured show, £${prices.featured_show}: pinned at the top of the list for 4 weeks, or until the show date if that is sooner, a highlighted pin on the map, a Featured label on the list and the show page. Featured in the Friday email sent the week of your show.</li>
        <li>Year pass, £${prices.year_pass} for 12 months: every show you organise is featured for 12 months from the day you pay, with the same pin, label and Friday slot as a single featured show.</li>
        <li>Site sponsor, £${prices.site_sponsor} a month: your name, one short line and a link on the homepage and the type pages, labelled as a sponsor.</li>
        <li>Friday email, £${prices.friday_email} an issue: the only sponsor in that Friday email. Sponsor any Friday you choose (not tied to a show date).</li>
      </ul>
      <h2>When it goes live</h2>
      <ul>
        <li>A featured show is featured within one working day of payment.</li>
        <li>A sponsor slot is live within one working day of getting your logo and message.</li>
      </ul>
      <h2>Renewals and cancelling</h2>
      <ul>
        <li>Monthly options renew each month until you cancel. There is no contract.</li>
        <li>To cancel, email ${sponsors}. Cancelling stops the next renewal, and your slot runs to the end of the period you have paid for.</li>
      </ul>
      <h2>Refunds</h2>
      <ul>
        <li>If we can't put your slot or featured show live, we refund you in full.</li>
        <li>If the show is cancelled before your slot runs, tell us and we refund you in full.</li>
        <li>Otherwise we don't refund part-used periods or slots that have already run.</li>
      </ul>
      <h2>Prices and payment</h2>
      <ul>
        <li>Prices are in pounds and are as shown at checkout.</li>
        <li>Prices shown are the total you pay.</li>
        <li>Payments are taken by Stripe, and you get a receipt by email.</li>
      </ul>
      <h2>Content</h2>
      <ul>
        <li>We can decline or remove anything misleading, unlawful or unsuitable, and refund you if we do.</li>
        <li>We check details with organisers where we can, but always check with the organiser or auctioneer before you travel or bid.</li>
      </ul>
      <h2>Contact</h2>
      <ul>
        <li>Questions: ${email}. Sponsorship and featured listings: ${sponsors}.</li>
      </ul>
    </div></article>`;
  return layout({
    site,
    path: "/terms/",
    title: "Terms | MineralDigger",
    description: "Terms for featured listings and sponsorship on MineralDigger.",
    body,
    generated,
  });
}

export function renderNotFound({ site, generated }) {
  const body = `<article class="page"><div class="wrap-narrow">
      <h1>That page is not on the map.</h1>
      <p><a href="/">Back to upcoming shows</a></p>
    </div></article>`;
  return layout({
    site,
    path: "/404.html",
    title: "Page not found | MineralDigger",
    description: "That page is not on MineralDigger.",
    body,
    generated,
    robots: "noindex",
  });
}

const SHARE_ICON = `<svg class="share-icon" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true"><path d="M12 3v12M7.5 7.5 12 3l4.5 4.5M5 11v9h14v-9" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;

export function renderApp({ site, generated }) {
  const body = `<article class="page"><div class="wrap-narrow prose">
      <p class="eyebrow">Home screen</p>
      <h1>Add MineralDigger to your phone</h1>
      <p class="lede">Put MineralDigger on your home screen and it opens in one tap, full screen, like any other icon on your phone. There's nothing to download from an app store and nothing to pay. It's the same website, so it's always up to date.</p>
      <p><img class="app-mark" src="/icons/icon-192.png" alt="MineralDigger icon" width="72" height="72"></p>
      <p id="a2hs-done" hidden><strong>You're using MineralDigger from your home screen already.</strong></p>
      <div id="a2hs-install" hidden><p><button type="button" class="pay">Add MineralDigger to this phone</button></p></div>
      <h2 class="mt">iPhone or iPad</h2>
      <ol>
        <li>Open <strong>mineraldigger.com</strong> in your browser.</li>
        <li>Tap the <strong>Share</strong> button ${SHARE_ICON} (or the browser's menu).</li>
        <li>Tap <strong>Add to Home Screen</strong> (you may need to scroll down), then <strong>Add</strong>.</li>
      </ol>
      <h2 class="mt">Android</h2>
      <ol>
        <li>Open <strong>mineraldigger.com</strong> in your browser.</li>
        <li>Tap the menu (<strong>⋮</strong>).</li>
        <li>Tap <strong>Add to Home screen</strong>, then confirm.</li>
      </ol>
      <p>Skip <strong>Install app</strong> if it appears in the menu. That path (and any in-page Install / Add to phone button that uses it) can trigger Google Play Protect with an "Unsafe app" warning. <strong>Add to Home screen</strong> is the one that works.</p>
      <p class="muted">Pages you've already looked at stay saved on your phone, so they still open with a weak signal. To remove it, press and hold the icon and choose Remove (or Uninstall).</p>
    </div></article>`;
  return layout({
    site,
    path: "/app/",
    title: "Add MineralDigger to your phone",
    description: "Put MineralDigger on your phone's home screen: how to add it on iPhone, iPad and Android. Free, no app store.",
    body,
    generated,
  });
}

export function renderOffline({ site, generated }) {
  const body = `<article class="page"><div class="wrap-narrow prose">
      <p class="eyebrow">No signal</p>
      <h1>You're offline</h1>
      <p class="lede">MineralDigger needs a signal to show the latest listings. Pages you've opened recently are saved on your phone.</p>
      <ul id="saved-pages"><li><a href="/">Home</a></li></ul>
      <p class="muted">Saved pages may be out of date. Always check with the organiser before you travel.</p>
      <p><a class="pay" href="">Try again</a></p>
    </div></article>
    <script>(function () {
      if (!window.caches) return;
      caches.keys().then(function (ks) {
        var k = ks.filter(function (n) { return n.indexOf("md-pages-") === 0; })[0];
        if (!k) return;
        return caches.open(k).then(function (c) { return c.keys(); }).then(function (rs) {
          var ul = document.getElementById("saved-pages");
          var seen = { "/": 1 };
          rs.reverse().slice(0, 25).forEach(function (r) {
            var u = new URL(r.url);
            if (seen[u.pathname] || u.pathname === "/offline/") return;
            seen[u.pathname] = 1;
            var a = document.createElement("a");
            a.href = u.pathname + u.search;
            var label = u.pathname === "/" ? "Home" : decodeURIComponent(u.pathname).split("/").filter(Boolean).join(", ").split("-").join(" ");
            a.textContent = label;
            var li = document.createElement("li");
            li.appendChild(a);
            ul.appendChild(li);
          });
        });
      });
    })();</script>`;
  return layout({
    site,
    path: "/offline/",
    title: "Offline | MineralDigger",
    description: "MineralDigger needs a signal to show the latest listings. Pages you have already opened stay on your phone.",
    body,
    generated,
    robots: "noindex",
  });
}

export function renderSitemap(site, paths) {
  const urls = paths
    .map((path) => `<url><loc>${esc(new URL(path, site.url).href)}</loc></url>`)
    .join("");
  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls}
</urlset>
`;
}
