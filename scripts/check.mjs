import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { featuredIds, stripeReady } from "./feature.mjs";
import { offerValidFrom, renderFeature } from "./render.mjs";
import { validateSubmission } from "../functions/api/validate.js";
import submitWorker, { resetRateLimit, MINERALDIGGER_SUBMIT_FROM, MINERALDIGGER_SUBMIT_TO } from "../workers/submit/src/index.js";

const root = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const dist = join(root, "dist");
const failures = [];

function fail(message) {
  failures.push(message);
}

function jpegSize(buffer) {
  if (buffer[0] !== 0xff || buffer[1] !== 0xd8) return null;
  let offset = 2;
  while (offset + 9 < buffer.length) {
    if (buffer[offset] !== 0xff) return null;
    const marker = buffer[offset + 1];
    if (marker === 0xd8) {
      offset += 2;
      continue;
    }
    if (marker === 0xd9 || marker === 0xda) return null;
    const length = buffer.readUInt16BE(offset + 2);
    if (marker >= 0xc0 && marker <= 0xc3) {
      return { height: buffer.readUInt16BE(offset + 5), width: buffer.readUInt16BE(offset + 7) };
    }
    offset += 2 + length;
  }
  return null;
}

function pngSize(buffer) {
  if (buffer.subarray(0, 8).toString("hex") !== "89504e470d0a1a0a") return null;
  if (buffer.subarray(12, 16).toString("ascii") !== "IHDR") return null;
  return { width: buffer.readUInt32BE(16), height: buffer.readUInt32BE(20) };
}

function icoSizes(buffer) {
  if (buffer.length < 22 || buffer.readUInt16LE(0) !== 0 || buffer.readUInt16LE(2) !== 1) return null;
  const count = buffer.readUInt16LE(4);
  const sizes = [];
  for (let i = 0; i < count; i++) {
    const offset = 6 + i * 16;
    sizes.push({ width: buffer[offset] || 256, height: buffer[offset + 1] || 256 });
  }
  return sizes;
}

function textOnly(html) {
  return html
    .replace(/<!DOCTYPE[^>]*>/gi, "")
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/<script[\s\S]*?<\/script>/gi, "");
}

async function htmlFiles(dir) {
  const found = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) found.push(...(await htmlFiles(path)));
    else if (entry.name.endsWith(".html")) found.push(path);
  }
  return found;
}

const index = await readFile(join(dist, "index.html"), "utf8");
const tagline = "UK rock, gem, mineral, fossil and bead shows on one map.";
const subline = "Dates, venues and entry in one place. Check before you travel; always confirm with the organiser.";
const footer = "Rock, gem, mineral, fossil and bead shows across the UK.";
const homeTitle = "MineralDigger · UK rock, gem, mineral, fossil and bead shows map";
const homeDescription = "Free UK calendar of rock, gem, mineral, fossil and bead shows. Dates, venues and entry on one map. Always confirm with the organiser before you travel.";
const homeOgTitle = "MineralDigger · UK rock, gem, mineral, fossil and bead shows";
const homeOgDescription = "Dates, venues and entry on one map. Free calendar for collectors and traders. Check the organiser before you travel.";
if (!index.includes(`<h1>${tagline}</h1>`)) fail("Homepage H1 changed.");
if (!index.includes(`<p class="lede">${subline}</p>`)) fail("Homepage lede changed.");
if (!index.includes(`<title>${homeTitle}</title>`)) fail("Homepage title is wrong.");
if (!index.includes(`<meta name="description" content="${homeDescription}">`)) fail("Homepage meta description is wrong.");
if (!index.includes(`property="og:title" content="${homeOgTitle}"`)) fail("Homepage og:title is wrong.");
if (!index.includes(`property="og:description" content="${homeOgDescription}"`)) fail("Homepage og:description is wrong.");
if (!index.includes(footer)) fail("Homepage is missing the footer line.");
const hubs = {
  rock: {
    heading: "Rock shows",
    title: "Rock shows in the UK | MineralDigger",
    description: "UK rock shows and rock, gem and bead weekends on one map. Free calendar from organiser sites.",
    lede: "Rock shows across the UK, plus the rock, gem and bead weekends that include them. MineralDigger is a free calendar and map of dates and venues from organiser sites. Always confirm times and tickets with the organiser before you travel.",
  },
  gem: {
    heading: "Gem shows",
    title: "Gem shows in the UK | MineralDigger",
    description: "UK gem shows and rock, gem and bead weekends. Dates, venues and entry on MineralDigger.",
    lede: "Gem shows and the rock, gem and bead weekends that list gems. MineralDigger puts UK dates, venues and entry on one map so you can see what is on this weekend and later in the year. Confirm with the organiser before you set off.",
  },
  mineral: {
    heading: "Mineral shows",
    title: "Mineral shows in the UK | MineralDigger",
    description: "UK mineral shows and society fairs on one map. Free calendar; confirm with the organiser.",
    lede: "Mineral shows and society fairs with a date on the organiser site. MineralDigger is a free UK calendar and map for collectors, not a club or society. Check entry, times and any changes with the organiser before you travel.",
  },
  fossil: {
    heading: "Fossil shows",
    title: "Fossil shows in the UK | MineralDigger",
    description: "UK fossil shows and mineral weekends that include fossils. Free map calendar on MineralDigger.",
    lede: "Fossil shows, and mineral weekends that include fossils. MineralDigger lists UK dates and venues from organiser websites on one map. Use it as a finder, then confirm times, tickets and changes with the organiser before you go.",
  },
  bead: {
    heading: "Bead shows",
    title: "Bead shows in the UK | MineralDigger",
    description: "UK bead shows and rock, gem and bead weekends. Dates and venues on MineralDigger.",
    lede: "Bead shows, including the rock, gem and bead weekends. MineralDigger is a free UK calendar and map of dates, venues and entry from organiser sites. Use it to plan a trip, then check with the organiser before you travel.",
  },
};
for (const [key, copy] of Object.entries(hubs)) {
  const page = await readFile(join(dist, key, "index.html"), "utf8");
  if (!page.includes(`<h1>${copy.heading}</h1>`)) fail(`${key} hub H1 changed.`);
  if (!page.includes(`<p class="lede">${copy.lede}</p>`)) fail(`${key} hub lede is wrong.`);
  if (!page.includes(`<title>${copy.title}</title>`)) fail(`${key} hub title is wrong.`);
  if (!page.includes(`<meta name="description" content="${copy.description}">`)) fail(`${key} hub description is wrong.`);
  if (!page.includes(`property="og:title" content="${copy.title}"`)) fail(`${key} hub og:title should match the title.`);
  if (!page.includes(`property="og:description" content="${copy.description}"`)) fail(`${key} hub og:description should match the description.`);
}
if (!index.includes('rel="canonical" href="https://mineraldigger.com/"')) fail("Homepage canonical is not https://mineraldigger.com/.");
if (!index.includes('property="og:url" content="https://mineraldigger.com/"')) fail("Homepage og:url is not https://mineraldigger.com/.");
if (!index.includes('property="og:site_name" content="MineralDigger"')) fail("Homepage og:site_name is missing.");
if (!index.includes('property="og:locale" content="en_GB"')) fail("Homepage og:locale is not en_GB.");
if (!index.includes('property="og:image" content="https://mineraldigger.com/og-image.jpg"')) fail("Homepage og:image is missing.");
if (!index.includes('property="og:image:width" content="1200"')) fail("Homepage og:image width is not 1200.");
if (!index.includes('property="og:image:height" content="630"')) fail("Homepage og:image height is not 630.");
if (!index.includes('property="og:image:alt" content="MineralDigger: Rock, gem, mineral, fossil and bead shows across the UK, on one map."')) {
  fail("Homepage og:image alt does not match the site.");
}
if (!index.includes('name="twitter:card" content="summary_large_image"')) fail("Homepage twitter card is missing.");
if (!index.includes('rel="icon" href="/favicon.ico" sizes="32x32"')) fail("Homepage favicon.ico link is missing.");
if (!index.includes('rel="icon" href="/favicon.svg" type="image/svg+xml"')) fail("Homepage favicon.svg link is missing.");
if (!index.includes('rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png"')) fail("Homepage apple touch icon link is missing.");
const jsonLd = [...index.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)].map((match) => match[1]);
if (jsonLd.length !== 1) fail(`Homepage should have one JSON-LD script, found ${jsonLd.length}.`);
let graph;
try {
  graph = JSON.parse(jsonLd[0] || "");
} catch {
  fail("Homepage JSON-LD is not valid JSON.");
}
const website = graph?.["@graph"]?.[0];
const org = graph?.["@graph"]?.[1];
if (graph?.["@context"] !== "https://schema.org" || graph?.["@graph"]?.length !== 2) fail("Homepage JSON-LD is not a WebSite and Organization graph.");
if (website?.["@type"] !== "WebSite" || website?.["@id"] !== "https://mineraldigger.com/#website") fail("WebSite @id is wrong.");
if (website?.name !== "MineralDigger" || website?.url !== "https://mineraldigger.com/" || website?.inLanguage !== "en-GB") {
  fail("WebSite name, url, or language is wrong.");
}
if (website?.description !== "Rock, gem, mineral, fossil and bead shows across the UK, on one map.") fail("WebSite description does not match the site.");
if (website?.publisher?.["@id"] !== "https://mineraldigger.com/#org") fail("WebSite publisher does not point at the organization.");
if (org?.["@type"] !== "Organization" || org?.["@id"] !== "https://mineraldigger.com/#org") fail("Organization @id is wrong.");
if (org?.name !== "MineralDigger" || org?.url !== "https://mineraldigger.com/" || org?.email !== "mineraldigger.hq@gmail.com") {
  fail("Organization name, url, or email is wrong.");
}
if (org?.logo?.["@type"] !== "ImageObject" || org?.logo?.url !== "https://mineraldigger.com/logo.png" || org?.logo?.width !== 512 || org?.logo?.height !== 512) {
  fail("Organization logo is not the 512 logo.png.");
}
const sameAs = Array.isArray(org?.sameAs) ? org.sameAs.join("\n") : "";
if (sameAs !== "https://www.facebook.com/people/MineralDigger/61595681170967/\nhttps://bsky.app/profile/mineraldigger.com") {
  fail("Organization sameAs is not Facebook and Bluesky.");
}
if (!Array.isArray(org?.areaServed) || org.areaServed.join(",") !== "GB") fail("Organization areaServed should be GB.");
if (index.includes("Also from us")) fail("Homepage should not include a sister-site footer.");
if (!index.includes("Kempton Park")) fail("Homepage is missing the Rockngem Kempton show.");
if (!/Oxford Mineral|Sussex Mineral|Bakewell Rock Exchange|South of England Mineral Show/.test(index)) {
  fail("Homepage is missing an independent show.");
}
const banned = /healing|psychic|tarot|mediums|wellbeing|mind[ -]body|white light|crystal spirit|gumroad|crystaldigger/i;
if (banned.test(index)) fail("Homepage contains banned copy.");

const feature = await readFile(join(dist, "feature/index.html"), "utf8");
for (const price of ["£15", "£99", "£25", "£12"]) {
  if (!feature.includes(price)) fail(`Feature page is missing ${price}.`);
}
if (!feature.includes("a month") || !feature.includes("an issue")) fail("Feature page is missing the sponsor periods.");
if (!feature.includes("mineraldigger.hq@gmail.com")) fail("Feature page is missing mineraldigger.hq@gmail.com.");
if (feature.includes("once the mailbox is open") || feature.includes("hello@mineraldigger.com")) {
  fail("Feature page still waits on the old mailbox.");
}
if (/coming soon/i.test(feature)) fail("Feature page still says payment is coming soon.");
if ((feature.match(/class="soon"/g) || []).length !== 0) fail("Feature page still has a Coming soon placeholder.");
if (feature.includes("Stripe link still to be added") || feature.includes("disabled")) {
  fail("Feature page still has a disabled Stripe buy button.");
}
if (feature.includes("REPLACE_ME")) fail("Feature page still has a Stripe placeholder.");
if (!feature.includes("Free listing") || !feature.includes("Submit a show")) fail("Feature page is missing the free listing.");
if (!feature.includes("Pay by card through Stripe") || !feature.includes("within one working day")) {
  fail("Feature page is missing the live checkout steps.");
}
if (!feature.includes("logo") || !feature.includes("one-line message")) {
  fail("Feature page does not ask sponsors to email a logo and a one-line message.");
}
const liveLinks = {
  featured_show: "https://buy.stripe.com/28E28r9Ukcba0QM6rAgnK00",
  year_pass: "https://buy.stripe.com/28E14n8Qgfnmbvqg2agnK01",
  site_sponsor: "https://buy.stripe.com/fZuaEX3vW2AA42Y5nwgnK02",
  friday_email: "https://buy.stripe.com/fZueVd4A00ss8jebLUgnK03",
};
const payLinks = [...feature.matchAll(/<a class="pay" href="([^"]+)"/g)].map((match) => match[1]);
const expectedPayLinks = ["/submit/", ...Object.values(liveLinks)];
if (payLinks.join("\n") !== expectedPayLinks.join("\n")) {
  fail(`Feature page pay links should be the free form plus the four Payment Links, found ${payLinks.join(", ") || "none"}.`);
}
for (const label of ["Pay £15 with Stripe", "Pay £99 with Stripe", "Pay £25 a month with Stripe", "Pay £12 with Stripe"]) {
  if (!feature.includes(label)) fail(`Feature page is missing ${label}.`);
}
const digest = await readFile(join(dist, "digest/index.html"), "utf8");
if (!digest.includes("Sponsor one issue for £12")) fail("Digest should invite the live Friday sponsor payment.");
if (digest.includes("Friday email sponsorship is coming soon")) fail("Digest still says Friday sponsorship is coming soon.");
if (!digest.includes("Not sent yet") || !digest.includes("Nothing is sent yet")) fail("Digest should stay an unsent preview.");

const about = await readFile(join(dist, "about/index.html"), "utf8");
if (/\bfairs?\b/i.test(about)) fail("About page still calls shows fairs.");
if (!about.includes("society mineral and fossil shows")) fail("About page should say society mineral and fossil shows.");
if (!about.includes("psychic shows")) fail("About page should say psychic shows.");
if (!about.includes("across the UK")) fail("About page should stay UK-only.");
if (/Ireland|UK\s*&|UK\s*\+/i.test(about)) fail("About page should not mention Ireland.");

const stripeFile = JSON.parse(await readFile(join(root, "data/stripe.json"), "utf8"));
if (/leave the string empty/i.test(stripeFile._note || "")) fail("stripe.json note still says to leave links empty.");
for (const key of Object.keys(liveLinks)) {
  const link = stripeFile.links[key];
  if (typeof link !== "string" || !link.startsWith("https://")) {
    fail(`data/stripe.json links.${key} must be a non-empty https URL.`);
  }
  if (!link.startsWith("https://buy.stripe.com/")) {
    fail(`data/stripe.json links.${key} must be a buy.stripe.com Payment Link.`);
  }
  if (link !== liveLinks[key]) fail(`data/stripe.json links.${key} is not the live Payment Link.`);
  if (stripeFile.prices[key] !== { featured_show: 15, year_pass: 99, site_sponsor: 25, friday_email: 12 }[key]) {
    fail(`Price for ${key} changed.`);
  }
}
if (stripeReady("") || stripeReady(null) || stripeReady("   ")) fail("An empty Stripe URL should stay off.");
if (!stripeReady("https://buy.stripe.com/test_example")) fail("A non-empty https Stripe URL should turn the button on.");
const wired = renderFeature({
  site: { name: "MineralDigger", url: "https://mineraldigger.com" },
  stripe: {
    prices: stripeFile.prices,
    links: { featured_show: "https://buy.stripe.com/test_example", year_pass: "", site_sponsor: "", friday_email: "" },
  },
  generated: "2026-10-25",
});
if (!wired.includes('href="https://buy.stripe.com/test_example"')) fail("A filled Stripe URL did not become a link.");
if (!wired.includes("Pay £15 with Stripe")) fail("A filled Stripe URL did not become a pay button.");
if ((wired.match(/class="soon"/g) || []).length !== 3) fail("Empty Stripe URLs should say coming soon.");
if (wired.includes("Stripe link still to be added")) fail("Empty Stripe URLs should not use the old placeholder.");

const submit = await readFile(join(dist, "submit/index.html"), "utf8");
if (!submit.includes("<form") || !submit.includes('action="/api/submit"')) fail("Submit form is missing.");
const submitJs = await readFile(join(dist, "js/submit.js"), "utf8");
if (!submitJs.includes("Mail is not connected")) fail("Submit fallback should still say mail is not connected.");
if (!submitJs.includes("mineraldigger.hq@gmail.com")) fail("Submit fallback is missing mineraldigger.hq@gmail.com.");
if (submitJs.includes("once the mailbox is open") || submitJs.includes("hello@mineraldigger.com")) {
  fail("Submit fallback still waits on the old mailbox.");
}
const siteFile = JSON.parse(await readFile(join(root, "data/site.json"), "utf8"));
if (siteFile.email !== "mineraldigger.hq@gmail.com") fail("data/site.json email is not mineraldigger.hq@gmail.com.");
const wrangler = await readFile(join(root, "workers/submit/wrangler.toml"), "utf8");
if (!wrangler.includes('MINERALDIGGER_SUBMIT_TO = "mineraldigger.hq@gmail.com"')) {
  fail("Wrangler MINERALDIGGER_SUBMIT_TO is not mineraldigger.hq@gmail.com.");
}
if (!wrangler.includes('destination_address = "mineraldigger.hq@gmail.com"')) {
  fail("Wrangler destination_address is not mineraldigger.hq@gmail.com.");
}
if (wrangler.includes("hello@mineraldigger.com")) fail("Wrangler still names hello@mineraldigger.com.");
if (!wrangler.includes("period = 60") || wrangler.includes("period = 600")) {
  fail("Submit rate limit period must be 60 seconds.");
}
if (MINERALDIGGER_SUBMIT_TO !== "mineraldigger.hq@gmail.com") {
  fail("MINERALDIGGER_SUBMIT_TO is not mineraldigger.hq@gmail.com.");
}

const files = await htmlFiles(dist);
for (const file of files) {
  const raw = await readFile(file, "utf8");
  const html = textOnly(raw);
  if (html.includes("\u2014")) fail(`Em dash in ${file}`);
  if (html.includes("!")) fail(`Exclamation mark in ${file}`);
  if (/gumroad|crystaldigger/i.test(html)) fail(`Banned name in ${file}`);
  if (raw.includes("mineraldigger.co.uk")) fail(`mineraldigger.co.uk still linked in ${file}`);
  if (raw.includes("Also from us")) fail(`Sister footer must stay off ${file}`);
  if (!raw.includes('rel="icon" href="/favicon.ico" sizes="32x32"')) fail(`favicon.ico link missing in ${file}`);
  if (!raw.includes('rel="apple-touch-icon" sizes="180x180" href="/apple-touch-icon.png"')) fail(`apple touch icon missing in ${file}`);
  if (!raw.includes('property="og:image" content="https://mineraldigger.com/og-image.jpg"')) fail(`og:image missing in ${file}`);
  if (!raw.includes('property="og:site_name" content="MineralDigger"')) fail(`og:site_name missing in ${file}`);
  if (!raw.includes('property="og:locale" content="en_GB"')) fail(`og:locale missing in ${file}`);
  const footStart = raw.indexOf('<footer class="site-footer">');
  const footEnd = raw.indexOf("</footer>");
  if (footStart < 0 || footEnd < footStart) {
    fail(`Footer missing in ${file}`);
    continue;
  }
  const foot = raw.slice(footStart, footEnd);
  if (!foot.includes('class="wrap foot"')) fail(`Multi-column footer missing in ${file}`);
  if (!foot.includes(">Browse</h2>") || !foot.includes(">Organisers</h2>") || !foot.includes(">Show types</h2>")) {
    fail(`Footer columns missing in ${file}`);
  }
  for (const href of [
    "/",
    "/?when=weekend",
    "/?when=later",
    "/submit/",
    "/feature/",
    "/about/",
    "/digest/",
    "/rock/",
    "/gem/",
    "/mineral/",
    "/fossil/",
    "/bead/",
    "/privacy/",
  ]) {
    if (!foot.includes(`href="${href}"`)) fail(`Footer in ${file} is missing ${href}`);
  }
  if (!foot.includes('href="/submit/">Submit your show</a>')) fail(`Submit label missing in ${file}`);
  if (!foot.includes('href="/feature/">Feature your show</a>')) fail(`Feature label missing in ${file}`);
  if (!foot.includes('href="/about/">How we list shows</a>')) fail(`About label missing in ${file}`);
  if (!foot.includes('href="/digest/">Friday email</a>')) fail(`Friday email link missing in ${file}`);
  const headerEnd = raw.indexOf("</header>");
  const header = headerEnd > 0 ? raw.slice(0, headerEnd) : "";
  if (!/href="\/digest\/"(?: aria-current="page")?>Friday email<\/a>/.test(header)) {
    fail(`Header nav in ${file} is missing the Friday email label.`);
  }
  if (raw.includes("Friday list")) fail(`Friday list label still in ${file}`);
  if (!foot.includes('href="https://www.facebook.com/people/MineralDigger/61595681170967/" rel="me noopener" target="_blank">Facebook</a>')) {
    fail(`Facebook link missing in ${file}`);
  }
  if (!foot.includes('href="https://bsky.app/profile/mineraldigger.com" rel="me noopener" target="_blank">Bluesky</a>')) {
    fail(`Bluesky link missing in ${file}`);
  }
  if (!foot.includes("© 2026 MineralDigger.") || !foot.includes("Show data retrieved ")) fail(`Footer credit line missing in ${file}`);
  if (/Ireland|UK\s*&|UK\s*\+|fairdigger|auctiondigger|alanconlon\.com|\/newsletter\/|\/app\//i.test(foot)) {
    fail(`Footer in ${file} has a banned link or a non-UK blurb`);
  }
}

const robots = await readFile(join(dist, "robots.txt"), "utf8");
if (!robots.includes("Sitemap: https://mineraldigger.com/sitemap.xml")) fail("robots.txt sitemap is not on mineraldigger.com.");
const sitemap = await readFile(join(dist, "sitemap.xml"), "utf8");
if (!sitemap.includes("<loc>https://mineraldigger.com/</loc>")) fail("Sitemap is missing the .com homepage.");
if (sitemap.includes("mineraldigger.co.uk")) fail("Sitemap still points at mineraldigger.co.uk.");
if (!sitemap.includes("<loc>https://mineraldigger.com/privacy/</loc>")) fail("Sitemap is missing the privacy page.");
if (sitemap.includes("/thanks/payment")) fail("Thank-you page must stay out of the sitemap.");
if (sitemap.includes("404")) fail("404 page must stay out of the sitemap.");
const privacy = await readFile(join(dist, "privacy/index.html"), "utf8");
if (!privacy.includes("<title>Privacy | MineralDigger</title>")) fail("Privacy title is wrong.");
if (!privacy.includes('rel="canonical" href="https://mineraldigger.com/privacy/"')) fail("Privacy canonical is wrong.");
if (!privacy.includes("Alan Conlon")) fail("Privacy page does not name Alan Conlon.");
if (!privacy.includes("mineraldigger.hq@gmail.com")) fail("Privacy page is missing the contact email.");
if (!privacy.includes("Buttondown")) fail("Privacy page does not name Buttondown.");
if (!privacy.includes("Stripe")) fail("Privacy page does not name Stripe.");
if (!privacy.includes("Cloudflare")) fail("Privacy page does not name Cloudflare.");
if (!privacy.includes('href="https://www.dataprotection.ie/"')) fail("Privacy page does not point at the Irish DPC.");
if (!privacy.includes('href="/submit/"')) fail("Privacy page does not link the submit form.");
if (!privacy.includes('href="/digest/"')) fail("Privacy page does not link the Friday email.");
if (/fairdigger|auctiondigger|alanconlon\.com/i.test(privacy)) fail("Privacy page names a sister site.");
if (privacy.includes("UK & Ireland") || privacy.includes("UK+IE") || privacy.includes("Eircode")) {
  fail("Privacy page uses Fair's geography.");
}
const missing = await readFile(join(dist, "404.html"), "utf8");
if (!missing.includes("<title>Page not found | MineralDigger</title>")) fail("404 title changed.");
if (!missing.includes("<h1>That page is not on the map.</h1>")) fail("404 heading changed.");
if (!missing.includes('href="/">Back to upcoming shows</a>')) fail("404 home link is missing.");
if (!missing.includes('name="robots" content="noindex"')) fail("404 is missing noindex.");
if (missing.includes('"#website"') || missing.includes('"@graph"')) fail("404 should not include the homepage graph.");
const ogImage = await readFile(join(dist, "og-image.jpg"));
const ogSize = jpegSize(ogImage);
if (!ogSize || ogSize.width !== 1200 || ogSize.height !== 630) fail(`og-image.jpg should be 1200x630 JPEG, found ${ogSize ? `${ogSize.width}x${ogSize.height}` : "not a JPEG"}.`);
const logoPng = await readFile(join(dist, "logo.png"));
const logoSize = pngSize(logoPng);
if (!logoSize || logoSize.width !== 512 || logoSize.height !== 512) fail("logo.png should be a 512x512 PNG.");
const appleIcon = await readFile(join(dist, "apple-touch-icon.png"));
const appleSize = pngSize(appleIcon);
if (!appleSize || appleSize.width !== 180 || appleSize.height !== 180) fail("apple-touch-icon.png should be a 180x180 PNG.");
const faviconIco = await readFile(join(dist, "favicon.ico"));
const faviconSize = icoSizes(faviconIco);
if (!faviconSize || faviconSize.length !== 1 || faviconSize[0].width !== 32 || faviconSize[0].height !== 32) {
  fail("favicon.ico should contain a single 32x32 image.");
}
if (!(await readFile(join(dist, "favicon.svg"), "utf8")).includes("#143f36")) fail("favicon.svg lost the Mineral green.");
const headers = await readFile(join(dist, "_headers"), "utf8");
if (!headers.includes("X-Robots-Tag: noindex")) fail("Thank-you page is missing the noindex response header.");
const thanks = await readFile(join(dist, "thanks/payment/index.html"), "utf8");
if (!thanks.includes("<title>Payment received | MineralDigger</title>")) fail("Thank-you page title is wrong.");
if (!thanks.includes('rel="canonical" href="https://mineraldigger.com/thanks/payment/"')) {
  fail("Thank-you page canonical is not https://mineraldigger.com/thanks/payment/.");
}
if (!thanks.includes('name="robots" content="noindex"')) fail("Thank-you page is missing noindex.");
if (!thanks.includes("mineraldigger.hq@gmail.com")) fail("Thank-you page is missing mineraldigger.hq@gmail.com.");
if (thanks.includes("hello@")) fail("Thank-you page invented another mailbox.");
if (!thanks.includes("Stripe receipt") || !thanks.includes("one working day") || !thanks.includes("12 months")) {
  fail("Thank-you page is missing the receipt and featuring promise.");
}
if (!thanks.includes("logo") || !thanks.includes("one-line message") || !thanks.includes("2 working days")) {
  fail("Thank-you page is missing the sponsor follow-up.");
}
if (!thanks.includes(">Home</a>") || !thanks.includes(">Upcoming shows</a>")) {
  fail("Thank-you page is missing the home and upcoming-shows links.");
}

const catalogue = JSON.parse(await readFile(join(root, "data/shows.json"), "utf8"));
if (catalogue.shows.length < 35 || catalogue.shows.length > 50) fail(`Unexpected show count ${catalogue.shows.length}`);
const upcoming = catalogue.shows.filter((show) => show.end >= "2026-10-25");
if (upcoming.length < 35) fail(`Not enough upcoming shows: ${upcoming.length}`);
for (const show of upcoming) {
  if (JSON.stringify(show).includes("rockexchange.uk")) {
    fail(`${show.id} is still upcoming and still links to rockexchange.uk.`);
  }
}
const bakewell2027 = catalogue.shows.find((show) => show.slug === "bakewell-rock-exchange-bakewell-2027-10-09");
if (!bakewell2027) fail("Bakewell 2027 show is missing.");
else if (bakewell2027.organiser.url || bakewell2027.source.url) fail("Bakewell 2027 still publishes rockexchange.uk.");
else if (bakewell2027.organiser.phone !== "01433 620304") fail("Bakewell 2027 phone changed.");
const bakewellPage = await readFile(join(dist, "show/bakewell-rock-exchange-bakewell-2027-10-09/index.html"), "utf8");
if (bakewellPage.includes("rockexchange.uk")) fail("Bakewell 2027 page still links to rockexchange.uk.");
if (bakewellPage.includes("Organiser website")) fail("Bakewell 2027 page still renders an organiser website link.");
if (!bakewellPage.includes("01433 620304") || !bakewellPage.includes('href="tel:01433620304"')) {
  fail("Bakewell 2027 page is missing the organiser phone.");
}
const bakewellIcs = await readFile(join(dist, "show/bakewell-rock-exchange-bakewell-2027-10-09/event.ics"), "utf8");
if (bakewellIcs.includes("rockexchange.uk") || bakewellIcs.includes("URL:")) {
  fail("Bakewell 2027 calendar still links out.");
}

if (offerValidFrom("2026-10-25") !== "2026-10-25T00:00:00+01:00") fail("Offer validFrom on 25 October 2026 should be UK midnight in BST.");
if (offerValidFrom("2026-01-16") !== "2026-01-16T00:00:00+00:00") fail("Offer validFrom in January should be UK midnight in GMT.");
if (offerValidFrom("2026-07-25") !== "2026-07-25T00:00:00+01:00") fail("Offer validFrom in July should be UK midnight in BST.");

function eventJsonLd(html) {
  const blocks = [...html.matchAll(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/g)].map((match) => match[1]);
  const events = [];
  for (const block of blocks) {
    let data;
    try {
      data = JSON.parse(block);
    } catch {
      return { error: "invalid" };
    }
    if (data?.["@type"] === "Event") events.push(data);
  }
  return { events };
}

for (const show of catalogue.shows) {
  const pageUrl = `https://mineraldigger.com/show/${show.slug}/`;
  let html;
  try {
    html = await readFile(join(dist, "show", show.slug, "index.html"), "utf8");
  } catch {
    fail(`Show page missing for ${show.slug}.`);
    continue;
  }
  const parsed = eventJsonLd(html);
  if (parsed.error || parsed.events.length !== 1) {
    fail(`${show.slug} should have one Event JSON-LD script.`);
    continue;
  }
  const event = parsed.events[0];
  const refreshed = show.source?.retrieved || catalogue.generated;
  if (event.url !== pageUrl) fail(`${show.slug} Event url is not the mineraldigger.com show page.`);
  if (JSON.stringify(event.image) !== JSON.stringify(["https://mineraldigger.com/og-image.jpg"])) {
    fail(`${show.slug} Event image is not the og-image array.`);
  }
  if (event.organizer?.["@type"] !== "Organization" || event.organizer?.name !== show.organiser.name) {
    fail(`${show.slug} organizer name is wrong.`);
  }
  if ((event.organizer?.url || null) !== (show.organiser.url || null)) fail(`${show.slug} organizer url changed.`);
  if (JSON.stringify(event.performer) !== JSON.stringify(event.organizer)) {
    fail(`${show.slug} performer is not the same organization as organizer.`);
  }
  const offer = event.offers;
  if (!offer || offer["@type"] !== "Offer") {
    fail(`${show.slug} is missing an Offer.`);
    continue;
  }
  if (offer.availability !== "https://schema.org/InStock") fail(`${show.slug} offer availability is not InStock.`);
  if (offer.url !== pageUrl) fail(`${show.slug} offer url is not the mineraldigger.com show page.`);
  if (offer.validFrom !== offerValidFrom(refreshed)) fail(`${show.slug} offer validFrom is not the refresh date in UK time.`);
  if (String(offer.url).includes("mineraldigger.co.uk") || String(event.url).includes("mineraldigger.co.uk")) {
    fail(`${show.slug} Event links to mineraldigger.co.uk.`);
  }
  const free = show.entry.kind === "free" || show.entry.adult_gbp === 0;
  const priced = show.entry.kind === "paid" && Number.isFinite(show.entry.adult_gbp) && show.entry.adult_gbp > 0;
  if (free) {
    if (offer.price !== "0" || offer.priceCurrency !== "GBP" || event.isAccessibleForFree !== true) {
      fail(`${show.slug} free entry should be price 0 GBP and accessible for free.`);
    }
  } else if (priced) {
    if (offer.price !== String(show.entry.adult_gbp) || offer.priceCurrency !== "GBP" || event.isAccessibleForFree !== false) {
      fail(`${show.slug} paid entry should keep the door price in GBP.`);
    }
  } else if ("price" in offer || "priceCurrency" in offer || "isAccessibleForFree" in event) {
    fail(`${show.slug} unknown entry should not invent a price.`);
  }
}

const ids = featuredIds(
  [
    { id: "a", organiser: { id: "org" }, end: "2026-12-01" },
    { id: "b", organiser: { id: "org" }, end: "2026-01-01" },
  ],
  { shows: [{ id: "c", until: "2026-11-01" }], organisers: [{ id: "org", until: "2026-12-31" }] },
  "2026-10-25",
);
if (!ids.has("a") || !ids.has("c") || ids.has("b")) fail("Featured rules did not match.");

const good = validateSubmission({
  organiser_name: "Example Society",
  email: "fair@example.com",
  show_name: "Example Mineral Show",
  types: ["mineral", "fossil"],
  start_date: "2026-11-14",
  end_date: "2026-11-14",
  venue_name: "Hall",
  town: "Haywards Heath",
  postcode: "rh16 1lt",
  entry_kind: "paid",
  entry_price: "5",
  confirm_permission: "yes",
  confirm_scope: "yes",
});
if (!good.ok || good.clean.postcode !== "RH16 1LT") fail("Valid submission was rejected.");
const bad = validateSubmission({ show_name: "Nope" });
if (bad.ok) fail("Invalid submission was accepted.");

resetRateLimit();
const listing = {
  organiser_name: "Example Society",
  email: "fair@example.com",
  show_name: "Example Mineral Show",
  types: ["mineral", "fossil"],
  start_date: "2026-11-14",
  end_date: "2026-11-14",
  venue_name: "Hall",
  town: "Haywards Heath",
  postcode: "RH16 1LT",
  entry_kind: "paid",
  entry_price: "5",
  confirm_permission: "yes",
  confirm_scope: "yes",
};
const sent = [];
const env = {
  MINERALDIGGER_SUBMIT_TO,
  MINERALDIGGER_SUBMIT_FROM,
  SEND_EMAIL: {
    async send(message) {
      sent.push(message);
      return { messageId: "local-test" };
    },
  },
};
async function post(body, origin, ip = "203.0.113.8") {
  const headers = { "content-type": "application/json", "cf-connecting-ip": ip };
  if (origin) headers.Origin = origin;
  const response = await submitWorker.fetch(
    new Request("https://mineraldigger.com/api/submit", { method: "POST", headers, body: JSON.stringify(body) }),
    env,
  );
  return { status: response.status, body: await response.json() };
}
const foreign = await post(listing, "https://evil.example");
if (foreign.status !== 403 || foreign.body.error !== "Bad origin.") fail("Foreign origin was not refused.");
const honey = await post({ ...listing, company_website: "https://spam.example" }, "https://mineraldigger.com");
if (honey.status !== 200 || honey.body.delivery !== "accepted" || sent.length !== 0) fail("Honeypot should accept and not email.");
for (let i = 0; i < 5; i += 1) {
  const ok = await post(listing, "https://mineraldigger.co.uk");
  if (ok.status !== 200 || ok.body.delivery !== "emailed") fail(`Submission ${i + 1} was not emailed.`);
}
if (sent.length !== 5) fail(`Expected 5 emails, saw ${sent.length}.`);
const mail = sent[0];
const from = typeof mail.from === "string" ? mail.from : mail.from.email;
if (from !== "submissions@mineraldigger.com" || mail.to !== "mineraldigger.hq@gmail.com" || mail.replyTo !== "fair@example.com") {
  fail("Submission email was not addressed to mineraldigger.hq@gmail.com.");
}
if (!String(mail.text).includes("fossil")) fail("Submission email dropped the show types.");
const limited = await post(listing, "https://www.mineraldigger.com");
if (limited.status !== 429) fail("Rate limit did not trip on the sixth listing.");
resetRateLimit();
const openBinding = {
  ...env,
  SUBMIT_LIMIT: {
    async limit() {
      return { success: true };
    },
  },
};
async function postOpen(ip) {
  const response = await submitWorker.fetch(
    new Request("https://mineraldigger.com/api/submit", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        "cf-connecting-ip": ip,
        Origin: "https://mineraldigger.com",
      },
      body: JSON.stringify(listing),
    }),
    openBinding,
  );
  return { status: response.status, body: await response.json() };
}
for (let i = 0; i < 5; i += 1) {
  const ok = await postOpen("203.0.113.10");
  if (ok.status !== 200 || ok.body.delivery !== "emailed") fail(`Binding-open submission ${i + 1} was not emailed.`);
}
const stillLimited = await postOpen("203.0.113.10");
if (stillLimited.status !== 429) fail("In-worker window did not keep the sixth listing inside ten minutes.");
const unconfigured = await submitWorker.fetch(
  new Request("https://mineraldigger.com/api/submit", {
    method: "POST",
    headers: { "content-type": "application/json", "cf-connecting-ip": "203.0.113.9", Origin: "https://www.mineraldigger.co.uk" },
    body: JSON.stringify(listing),
  }),
  {},
);
const unconfiguredBody = await unconfigured.json();
if (unconfigured.status !== 200 || unconfiguredBody.delivery !== "unconfigured") fail("Missing email binding should stay unconfigured.");

if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log(`Checked ${files.length} pages and ${catalogue.shows.length} shows.`);
