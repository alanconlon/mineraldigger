import { formatDay, formatRange, monthKey, monthLabel, shortStack, digestWeekend, overlaps } from "../src/js/format.js";
import { stripeReady } from "./feature.mjs";

const TYPES = [
  ["rock", "Rock", "/rock/"],
  ["gem", "Gem", "/gem/"],
  ["mineral", "Mineral", "/mineral/"],
  ["fossil", "Fossil", "/fossil/"],
  ["bead", "Bead", "/bead/"],
];

const TYPE_INTRO = {
  rock: "Rock shows, and the rock, gem and bead weekends that include them.",
  gem: "Gem shows, including the rock, gem and bead weekends.",
  mineral: "Mineral shows and society fairs with a date on the organiser site.",
  fossil: "Fossil shows, and mineral weekends that include fossils.",
  bead: "Bead shows, including the rock, gem and bead weekends.",
};

const SHARE_ALT = "MineralDigger: Rock, gem, mineral, fossil and bead shows across the UK, on one map.";
const SITE_BLURB = "Rock, gem, mineral, fossil and bead shows across the UK, on one map.";

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
    ["/digest/", "Friday list"],
    ["/about/", "About"],
  ];
  return items
    .map(([href, label]) => `<a href="${href}"${href === path ? ' aria-current="page"' : ""}>${label}</a>`)
    .join("");
}

function footer(generated) {
  const types = TYPES.map(([key, label, href]) => `<a href="${href}">${label}</a>`).join("");
  return `<footer class="site-footer">
    <div class="wrap">
      <p>Rock, gem, mineral, fossil and bead shows across the UK.</p>
      <p>Dates checked against organiser websites. Always confirm with the organiser before you travel.</p>
      <p class="fine">Show data retrieved ${esc(formatDay(generated))}.</p>
      <nav class="types" aria-label="Show types">${types}</nav>
    </div>
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

function layout({ site, path, title, description, body, map = false, generated, robots, structuredData = "" }) {
  const canonical = new URL(path, site.url).href;
  const image = new URL("/og-image.jpg", site.url).href;
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
  <meta property="og:title" content="${esc(title)}">
  <meta property="og:description" content="${esc(description)}">
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
    <div class="wrap">
      <a class="logo" href="/">Mineral<span>Digger</span></a>
      <nav class="nav" aria-label="Primary">${nav(path)}</nav>
    </div>
  </header>
  <main id="main">${body}</main>
  ${footer(generated)}
  ${map ? '<script type="module" src="/js/site.js"></script>' : ""}
</body>
</html>
`;
}

function pills(show) {
  const bits = [`<span class="pill pill-${esc(show.entry.kind)}">${esc(show.entry.label)}</span>`];
  if (show.provisional) bits.push('<span class="pill pill-provisional">Provisional</span>');
  if (show.featured) bits.push('<span class="pill pill-featured">Featured</span>');
  for (const type of show.types) bits.push(`<span class="pill">${esc(type)}</span>`);
  return bits.join("");
}

function card(show) {
  const stack = shortStack(show.start, show.end);
  const place = [show.venue.town, show.venue.county].filter(Boolean).join(", ");
  const search = [show.name, show.venue.name, show.venue.town, show.venue.county, show.venue.postcode, show.organiser.name]
    .join(" ")
    .toLowerCase();
  const times = show.times.summary ? `<p class="meta">${esc(show.times.summary)}</p>` : "";
  const dealers = show.dealers ? `<p class="dealers">${esc(show.dealers)} dealers</p>` : "";
  return `<article class="card${show.featured ? " featured" : ""}" data-start="${esc(show.start)}" data-end="${esc(show.end)}" data-lat="${esc(show.venue.lat)}" data-lng="${esc(show.venue.lng)}" data-name="${esc(show.name)}" data-place="${esc(`${show.venue.name}, ${place}`)}" data-href="/show/${esc(show.slug)}/" data-provisional="${show.provisional ? "1" : "0"}" data-featured="${show.featured ? "1" : "0"}" data-search="${esc(search)}">
    <a class="card-link" href="/show/${esc(show.slug)}/">
      <div class="when-block">
        <span class="wd">${esc(stack.wd)}</span>
        <span class="dn">${esc(stack.day)}</span>
        <span class="mo">${esc(stack.mon)}</span>
        ${stack.span ? `<span class="span">${esc(stack.span)}</span>` : ""}
      </div>
      <div>
        <h3>${esc(show.name)}</h3>
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
  }).join("");
  return all + rest;
}

export function renderListing({ site, path, title, description, heading, lede, shows, generated, home = false, typeLock = null }) {
  const featured = shows.filter((show) => show.featured);
  const rest = shows.filter((show) => !show.featured);
  const note = shows.some((show) => show.provisional)
    ? `<p class="fine">Dates marked provisional are printed that way by the organiser. Rock, Gem &amp; Bead Shows mark their 2027 list as provisional.</p>`
    : "";
  const hero = home
    ? `<section class="hero"><div class="wrap">
        <p class="eyebrow">UK shows directory</p>
        <h1>${esc(heading)}</h1>
        <p class="lede">${esc(lede)}</p>
        <p class="count-line"><strong id="result-count">${shows.length} shows</strong> from organiser websites, on one map.</p>
      </div></section>`
    : `<section class="hero"><div class="wrap">
        <p class="eyebrow">Show type</p>
        <h1>${esc(heading)}</h1>
        <p class="lede">${esc(lede)}</p>
        <p class="count-line"><strong id="result-count">${shows.length} shows</strong></p>
      </div></section>`;
  const body = `${hero}
    <div class="wrap">
      <div class="filters">
        <div class="chip-row" role="group" aria-label="Date window">
          <button type="button" class="chip" data-when="all" aria-pressed="true">All upcoming</button>
          <button type="button" class="chip" data-when="weekend" aria-pressed="false">This weekend</button>
          <button type="button" class="chip" data-when="later" aria-pressed="false">Coming later</button>
        </div>
        <div class="chip-row" aria-label="Type">${typeLinks(typeLock)}</div>
        <input id="q" type="search" aria-label="Town or postcode" placeholder="Town or postcode">
      </div>
      ${note}
      <div class="layout">
        <div>
          <noscript><p class="noscript">The map and the weekend filter need Javascript. The list below is every upcoming show on this page.</p></noscript>
          <div id="empty" class="empty" hidden>
            <h2>Nothing listed for this weekend.</h2>
            <p>Coming later has the next published dates.</p>
          </div>
          <div id="show-list">
            ${featured.length ? `<section class="month"><h2>Featured</h2>${featured.map(card).join("")}</section>` : ""}
            ${months(rest)}
          </div>
        </div>
        <aside class="map-col">
          <div class="map-frame"><div id="map" role="region" aria-label="Map of shows"></div></div>
          <p class="map-note">Green pins are confirmed dates. Copper pins are provisional. The pin sits on the venue postcode.</p>
        </aside>
      </div>
    </div>`;
  return layout({
    site,
    path,
    title,
    description,
    body,
    map: true,
    generated,
    structuredData: home ? siteGraph(site) : "",
  });
}

export function renderHome(ctx) {
  return renderListing({
    ...ctx,
    path: "/",
    title: "MineralDigger. UK rock, gem, mineral, fossil and bead shows",
    description: "Dates, venues and entry in one place. Check before you travel; always confirm with the organiser.",
    heading: "UK rock, gem, mineral, fossil and bead shows on one map.",
    lede: "Dates, venues and entry in one place. Check before you travel; always confirm with the organiser.",
    home: true,
    typeLock: null,
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
    description: TYPE_INTRO[key],
    heading: `${label} shows`,
    lede: TYPE_INTRO[key],
    home: false,
    typeLock: key,
  });
}

function placeLine(show) {
  return [show.venue.town, show.venue.county, show.venue.nation].filter(Boolean).join(", ");
}

function jsonLd(show, site) {
  const data = {
    "@context": "https://schema.org",
    "@type": "Event",
    name: show.name,
    startDate: show.start,
    endDate: show.end,
    eventAttendanceMode: "https://schema.org/OfflineEventAttendanceMode",
    eventStatus: "https://schema.org/EventScheduled",
    description: show.summary,
    url: new URL(`/show/${show.slug}/`, site.url).href,
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
    organizer: {
      "@type": "Organization",
      name: show.organiser.name,
    },
  };
  if (show.organiser.url) data.organizer.url = show.organiser.url;
  if (show.entry.kind === "free") {
    data.isAccessibleForFree = true;
    data.offers = { "@type": "Offer", price: "0", priceCurrency: "GBP" };
  } else if (show.entry.kind === "paid") {
    data.isAccessibleForFree = false;
    data.offers = { "@type": "Offer", price: String(show.entry.adult_gbp), priceCurrency: "GBP" };
  }
  if (data.offers && show.organiser.url) data.offers.url = show.organiser.url;
  return `<script type="application/ld+json">${JSON.stringify(data).replace(/</g, "\\u003c")}</script>`;
}

export function renderShow({ site, show, generated, todayISO }) {
  const past = show.end < todayISO;
  const banners = [];
  if (past) banners.push(`<div class="callout past"><p>This date has passed. Check the organiser for the next one.</p></div>`);
  if (show.provisional) banners.push(`<div class="callout"><p>The organiser lists this date as provisional. Check their site before you travel.</p></div>`);
  if (show.year_inferred) banners.push(`<div class="callout"><p>${esc(show.source.notes)}</p></div>`);
  const address = [show.venue.street, placeLine(show), show.venue.postcode].filter(Boolean).join(", ");
  const facts = [
    ["When", `${formatRange(show.start, show.end)}${show.times.summary ? `. ${show.times.summary}` : ""}${show.times.notes ? ` ${show.times.notes}` : ""}`],
    ["Entry", [show.entry.label, show.entry.notes].filter(Boolean).join(". ")],
    ["Venue", `${show.venue.name}, ${address}`],
    ["Organiser", show.organiser.name],
  ];
  if (show.dealers) facts.push(["Dealers", `${show.dealers} on the organiser page`]);
  if (show.parking) facts.push(["Parking", show.parking]);
  if (show.access_notes) facts.push(["Access", show.access_notes]);
  const factHtml = facts
    .map(([label, value]) => `<div class="fact"><h2>${esc(label)}</h2><p>${esc(value)}</p></div>`)
    .join("");
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
  const osm = `https://www.openstreetmap.org/directions?to=${show.venue.lat}%2C${show.venue.lng}`;
  const body = `<article class="page"><div class="wrap-narrow">
      <p class="eyebrow"><a href="/">Shows</a></p>
      <h1>${esc(show.name)}</h1>
      <p class="lede">${esc(show.summary)}</p>
      <div class="pills">${pills(show)}</div>
      ${banners.join("")}
      <p>Types: ${types}</p>
      <div class="facts">${factHtml}</div>
      ${phone}
      ${email}
      ${website}
      <div class="actions">
        <a href="/show/${esc(show.slug)}/event.ics">Add to calendar</a>
        <a href="${esc(osm)}">Directions</a>
        <a href="/feature/">Feature this show</a>
      </div>
      <div class="map-frame" style="height:320px;min-height:0"><div id="detail-map" data-lat="${esc(show.venue.lat)}" data-lng="${esc(show.venue.lng)}" role="region" aria-label="Map of the venue"></div></div>
      <p class="map-note">The pin is the venue postcode, not a surveyed entrance.${show.venue.place_note ? ` ${esc(show.venue.place_note)}` : ""}</p>
      <h2>Where this date came from</h2>
      <p>${esc(show.source.notes)}</p>
      ${retrieved}
      ${also}
      <p>Always check the organiser's page for times, tickets and any changes before you set off.</p>
    </div></article>
    ${jsonLd(show, site)}`;
  return layout({
    site,
    path: `/show/${show.slug}/`,
    title: `${show.name}, ${formatRange(show.start, show.end)} | MineralDigger`,
    description: `${show.summary} ${placeLine(show)}.`,
    body,
    map: true,
    generated,
  });
}

function payControl(href, label, ready) {
  if (!ready) return `<p class="soon">Coming soon</p>`;
  return `<a class="pay" href="${esc(href)}">${esc(label)}</a>`;
}

function paymentCopy(ready, prices) {
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
        <li>Email your logo, a one-line message, and which package to mineraldigger.hq@gmail.com.</li>
        <li>Your slot is live within 2 working days.</li>
      </ol>`,
    };
  }
  if (noneOpen) {
    return {
      notice: `<div class="notice">
        <p>Card payment is coming soon. The prices above are the ones we will charge. Until then, email mineraldigger.hq@gmail.com.</p>
      </div>`,
      featureSteps: `<ol>
        <li>Make sure the show is listed. If it is not, <a href="/submit/">submit it free</a> first.</li>
        <li>Card payment for a featured show or a year pass is coming soon.</li>
        <li>Until then, email mineraldigger.hq@gmail.com with the show, or the organiser for a year pass.</li>
      </ol>`,
      sponsorSteps: `<ol>
        <li>Choose the site, at £${prices.site_sponsor} a month, or one Friday email at £${prices.friday_email}.</li>
        <li>Card payment is coming soon.</li>
        <li>Email your name, a short line and your link to mineraldigger.hq@gmail.com.</li>
        <li>You are live within two working days of payment.</li>
      </ol>`,
    };
  }
  return {
    notice: `<div class="notice">
        <p>Some card payments are still coming soon. Pay only where a button is shown. For the rest, email mineraldigger.hq@gmail.com.</p>
      </div>`,
    featureSteps: `<ol>
        <li>Make sure the show is listed. If it is not, <a href="/submit/">submit it free</a> first.</li>
        <li>Pay by card through Stripe where a button is shown. At checkout, say which show it is, or which organiser for the year pass.</li>
        <li>You get a Stripe receipt by email. We feature the show within one working day, and we email if we need anything else.</li>
      </ol>`,
    sponsorSteps: `<ol>
        <li>Choose the site, at £${prices.site_sponsor} a month, or one Friday email at £${prices.friday_email}.</li>
        <li>Pay by card through Stripe where a button is shown. Options marked coming soon are not open yet.</li>
        <li>Email your logo, a one-line message, and which package to mineraldigger.hq@gmail.com.</li>
        <li>Your slot is live within 2 working days of payment.</li>
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
      <h1>Feature a show</h1>
      <p class="lede">Put your show in front of people looking for rock, gem, mineral, fossil and bead shows. Listing is free. Featuring and sponsorship are optional, and they are labelled when they are on.</p>
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
            <li>Pinned at the top of the list for 28 days, or until the show date if that is sooner</li>
            <li>A highlighted pin on the map</li>
            <li>A Featured label on the list and the show page</li>
            <li>In the featured slot of the Friday list the weekend it runs</li>
          </ul>
          ${payControl(links.featured_show, `Pay £${prices.featured_show} with Stripe`, ready.featured_show)}
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
            <li>One issue. You pick the Friday.</li>
          </ul>
          ${payControl(links.friday_email, `Pay £${prices.friday_email} with Stripe`, ready.friday_email)}
        </section>
      </div>
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
    </div></article>`;
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
  const body = `<article class="page"><div class="wrap-narrow prose">
      <p class="eyebrow">Payment received</p>
      <h1>Thank you</h1>
      <p class="lede">Thank you. Your payment has gone through. You get a Stripe receipt by email. We feature the show within one working day (with a year pass, all of that organiser's shows for 12 months from the day you pay), and we email if we need anything else.</p>
      <p><strong>Sponsoring the site or the Friday email?</strong> Please email your logo, a one-line message, and which package you paid for to <a href="mailto:${esc(email)}">${esc(email)}</a>. Your slot starts within 2 working days.</p>
      <p class="fine">Questions about your listing? Reply to the Stripe receipt or email <a href="mailto:${esc(email)}">${esc(email)}</a>.</p>
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
      <h1>Submit a show</h1>
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
              <option value="unknown">Unknown</option>
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
      <p>We focus on trade and collector shows: Rock, Gem &amp; Bead circuits, society mineral and fossil fairs, and gem expos. We do not list mind-body-spirit or psychic fairs.</p>
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

export function renderDigest({ site, shows, sponsors, generated, today, stripe }) {
  const weekend = digestWeekend(today);
  const rows = shows.filter((show) => overlaps(show, weekend.start, weekend.end));
  const friday = sponsors && sponsors.friday;
  const fridayPrice = stripe?.prices?.friday_email ?? 12;
  const fridayOpen = stripeReady(stripe?.links?.friday_email);
  const sponsor = friday && friday.issue === weekend.start
    ? `<aside class="example"><p class="eyebrow">Sponsored</p><p><a rel="sponsored" href="${esc(friday.url)}">${esc(friday.name)}</a>. ${esc(friday.line || "")}</p></aside>`
    : fridayOpen
      ? `<aside class="example"><p class="eyebrow">Friday email sponsor</p><p>No sponsor for this issue. <a href="/feature/">Sponsor one issue for £${fridayPrice}</a>.</p></aside>`
      : `<aside class="example"><p class="eyebrow">Friday email sponsor</p><p>No sponsor for this issue. <a href="/feature/">Friday email sponsorship is coming soon</a> (£${fridayPrice} an issue).</p></aside>`;
  const list = rows.length
    ? `<ul>${rows.map((show) => `<li><a href="/show/${esc(show.slug)}/">${esc(show.name)}</a>, ${esc(formatRange(show.start, show.end))}, ${esc(show.venue.town)}. ${esc(show.entry.label)}.</li>`).join("")}</ul>`
    : `<p>No shows in the list fall on that weekend.</p>`;
  const body = `<article class="page"><div class="wrap-narrow prose">
      <p class="eyebrow">Not sent yet</p>
      <h1>Friday list</h1>
      <p class="lede">A preview of the Friday email. Nothing is sent yet. Mail is still to be connected.</p>
      <h2>${esc(formatRange(weekend.start, weekend.end))}</h2>
      ${sponsor}
      ${list}
      <p class="fine">The Friday list covers the coming Friday to Sunday. On a Saturday or Sunday it looks ahead to the next weekend.</p>
    </div></article>`;
  return layout({
    site,
    path: "/digest/",
    title: "Friday list | MineralDigger",
    description: "A preview of the MineralDigger Friday email. Mail is not sent yet.",
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
