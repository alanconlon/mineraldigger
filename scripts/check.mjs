import { existsSync } from "node:fs";
import { readFile, readdir } from "node:fs/promises";
import { join, relative, sep } from "node:path";
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
const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
function isoToday(date = new Date()) {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}
function longDateFromISO(value) {
  const [year, month, day] = String(value).slice(0, 10).split("-").map(Number);
  return `${day} ${MONTH_NAMES[month - 1]} ${year}`;
}
const homeCatalogue = JSON.parse(await readFile(join(root, "data/shows.json"), "utf8"));
const homeCount = homeCatalogue.shows.filter((show) => show.end >= isoToday()).length;
const homeNoun = homeCount === 1 ? "show" : "shows";
const homeDescription = `Free UK calendar of ${homeCount} rock, gem, mineral, fossil and bead ${homeNoun}. Dates, venues and entry on one map. Always confirm with the organiser before you travel.`;
const homeOgTitle = "MineralDigger · UK rock, gem, mineral, fossil and bead shows";
const homeOgDescription = `${homeCount} ${homeNoun} with dates, venues and entry on one map. Free calendar for collectors and traders. Check the organiser before you travel.`;
if (!index.includes(`<h1>${tagline}</h1>`)) fail("Homepage H1 changed.");
if (!index.includes(`<p class="lede">${subline}</p>`)) fail("Homepage lede changed.");
if (!index.includes(`<title>${homeTitle}</title>`)) fail("Homepage title is wrong.");
if (!index.includes(`<meta name="description" content="${homeDescription}">`)) fail("Homepage meta description is wrong.");
if (!index.includes(`property="og:title" content="${homeOgTitle}"`)) fail("Homepage og:title is wrong.");
if (!index.includes(`property="og:description" content="${homeOgDescription}"`)) fail("Homepage og:description is wrong.");
if (!index.includes(footer)) fail("Homepage is missing the footer line.");
if (!index.includes('id="newsletter"')) fail("Homepage is missing the Friday email sign-up.");
if (!index.includes('action="https://buttondown.com/api/emails/embed-subscribe/mineraldigger"')) {
  fail("Homepage form does not post to Buttondown.");
}
if (!index.includes('data-thanks="/thanks/"')) fail("Homepage form does not point at /thanks/.");
if (!index.includes('src="/js/newsletter.js"')) fail("Homepage is missing the sign-up script.");
if (!index.includes('Emails are sent by <a href="https://buttondown.com/" rel="noopener">Buttondown</a>; you\'ll get a link to confirm.')) {
  fail("Homepage sign-up fine print should name Buttondown and the confirm link.");
}
if (/Not sent yet|Nothing is sent yet|Mail is still to be connected/i.test(index)) {
  fail("Homepage still says mail is not connected.");
}
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
if (org?.name !== "MineralDigger" || org?.url !== "https://mineraldigger.com/" || org?.email !== "hello@mineraldigger.com") {
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
if (!index.includes('class="nav-toggle"') || !index.includes('id="primary-nav"')) fail("Homepage is missing the mobile menu.");
if (!index.includes('href="#main">Skip to content</a>')) fail("Skip to content link is missing.");
if (!index.includes(">Search</button>")) fail("Search button is missing.");
if (!index.includes('placeholder="Postcode or town, e.g. RH16"')) fail("Search placeholder is wrong.");
if (!index.includes('role="group" aria-label="When"')) fail("Homepage should have one When row.");
if (!index.includes('class="chip-row chip-scroll" role="group" aria-label="Type"')) fail("Homepage should have one sideways Type row.");
if (index.includes('aria-label="Show filters"')) fail("When and Type should be separate rows.");
const homeMain = index.slice(0, index.indexOf('<footer class="site-footer">'));
const weekendLabels = homeMain.match(/>This weekend</g) || [];
if (weekendLabels.length !== 1) fail(`Homepage should say This weekend once above the footer, found ${weekendLabels.length}.`);
const listAt = homeMain.indexOf('id="show-list"');
const placesAt = homeMain.indexOf('aria-label="Places"');
if (listAt < 0 || placesAt < listAt) fail("Counties and Towns should sit below the show list.");
if (!homeMain.slice(placesAt).includes('href="/county/">Counties</a>') || !homeMain.slice(placesAt).includes('href="/towns/">Towns</a>')) {
  fail("Place links under the list should be Counties and Towns.");
}
const beforeList = homeMain.slice(0, listAt);
if (beforeList.includes('href="/county/">Counties</a>') || beforeList.includes('href="/towns/">Towns</a>')) {
  fail("Counties and Towns should not sit above the list.");
}
if (index.includes("<h2>Nothing listed for this weekend.</h2>")) fail("Homepage still has the hidden weekend heading.");
if (!index.includes("<h3>Haywards Heath: Sussex Mineral, Crystal &amp; Fossil Show</h3>")) fail("Homepage show names should lead with the town.");
const monthKeys = [...index.matchAll(/data-month="(\d{4}-\d{2})"/g)].map((match) => match[1]);
if (!monthKeys.length || new Set(monthKeys).size !== monthKeys.length) fail("Homepage should have one heading per month.");
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
if (!feature.includes("sponsors@mineraldigger.com")) fail("Feature page is missing sponsors@mineraldigger.com.");
if (!feature.includes('href="mailto:sponsors@mineraldigger.com"')) fail("Feature page sponsor address is not a mailto link.");
if (feature.includes("mineraldigger.hq@gmail.com")) fail("Feature page still names the HQ Gmail.");
if (feature.includes("once the mailbox is open") || feature.includes("hello@mineraldigger.com")) {
  fail("Feature page should use the sponsors address, not the general mailbox.");
}
if (/coming soon/i.test(feature)) fail("Feature page still says payment is coming soon.");
if ((feature.match(/class="soon"/g) || []).length !== 0) fail("Feature page still has a Coming soon placeholder.");
if (feature.includes("Stripe link still to be added") || feature.includes("disabled")) {
  fail("Feature page still has a disabled Stripe buy button.");
}
if (feature.includes("REPLACE_ME")) fail("Feature page still has a Stripe placeholder.");
if (!feature.includes("Free listing") || !feature.includes("Submit a show")) fail("Feature page is missing the free listing.");
if (!feature.includes("for 4 weeks")) fail("Feature page should describe featuring as 4 weeks.");
if (feature.includes("28 days")) fail("Feature page still says 28 days.");
if (!feature.includes('id="feature-pick"') || !feature.includes('src="/js/feature.js"')) {
  fail("Feature page should be able to show the show passed in the query.");
}
if (!feature.includes('id="feature-heading"')) fail("Feature page should have a heading the show name can replace.");
if (!feature.includes('id="featured-pay"')) fail("Featured show payment link should be marked so the show can be passed through.");
const featureJs = await readFile(join(dist, "js/feature.js"), "utf8");
if (!featureJs.includes('heading.textContent = "Feature: " + name')) fail("Feature page should title the page Feature: and the show name.");
if (!featureJs.includes('client_reference_id')) fail("Featured payment link should pass the show as client_reference_id.");
const siteJs = await readFile(join(dist, "js/site.js"), "utf8");
if (!siteJs.includes("Showing ") || !siteJs.includes(" near ")) fail("Search status should say Showing N shows near a place.");
if (!siteJs.includes("No shows found near ")) fail("Search should say when no shows are near a place.");
if (!siteJs.includes("Try a nearby town or browse by county.")) fail("No-match copy should suggest a nearby town or a county.");
if (!siteJs.includes("scrollIntoView")) fail("Search should scroll to the results.");
if (!siteJs.includes("countyCentre")) fail("A county search should resolve like a place search.");
if (!siteJs.includes("shows match")) fail("A narrowed list should say how many of the total match.");
if (!siteJs.includes("dataset.total")) fail("The intro count should keep the full total.");
const siteCss = await readFile(join(dist, "site.css"), "utf8");
if (!siteCss.includes(".show-date { display: none; }")) fail("The show date should be hidden on small screens so it is not printed twice.");
if (!feature.includes("Pay by card through Stripe") || !feature.includes("We feature the show within one working day")) {
  fail("Feature page is missing the live checkout steps.");
}
if (!feature.includes("Your slot is live within one working day of receiving your logo and message.")) {
  fail("Feature page sponsor turnaround is wrong.");
}
if (!feature.includes("Featured in the Friday email sent the week of your show")) {
  fail("Featured show Friday email line is wrong.");
}
if (feature.includes("Friday email the weekend it runs") || feature.includes("You pick the Friday")) {
  fail("Feature page still has the old Friday email lines.");
}
if (!feature.includes("Same pin, label and Friday slot as a single featured show")) fail("Year pass Friday slot line changed.");
if (!feature.includes("Sponsor any Friday you choose (not tied to a show date)")) {
  fail("Friday email sponsorship line is wrong.");
}
if (!feature.includes('href="/terms/"')) fail("Feature page should link to the terms near the prices.");
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
const digest = await readFile(join(dist, "newsletter/index.html"), "utf8");
const digestDescription = "The Friday email: a free weekly list of UK rock, gem, mineral, fossil and bead shows for the coming weekend.";
const digestFinePrint = 'A free Friday email of upcoming UK rock, gem, mineral, fossil and bead shows. Unsubscribe any time. Emails are sent by <a href="https://buttondown.com/" rel="noopener">Buttondown</a>; you\'ll get a link to confirm.';
if (digest.includes("This weekend's shows")) fail("Digest should not list this weekend's shows under the form.");
if (digest.includes("Friday email sponsor") || digest.includes("Sponsor one issue") || digest.includes("No sponsor for this issue")) {
  fail("Digest should not show a sponsor box under the form.");
}
if (digest.includes("see the sponsor options") || digest.includes("lapidary shop")) {
  fail("Digest sign-up page should not include the Friday email sponsor invitation.");
}
if (digest.includes("No shows in the list fall on that weekend.")) fail("Digest should not preview an empty weekend.");
if (digest.includes("Friday email sponsorship is coming soon")) fail("Digest still says Friday sponsorship is coming soon.");
if (/Not sent yet|Nothing is sent yet|Mail is not sent yet|Mail is still to be connected|mail is not connected/i.test(digest)) {
  fail("Digest still says mail is not connected.");
}
if (!digest.includes("<h1>The Friday email</h1>")) fail("Digest heading should be The Friday email.");
if (!digest.includes('rel="canonical" href="https://mineraldigger.com/newsletter/"')) fail("Friday email canonical should be /newsletter/.");
if (!digest.includes("<title>The Friday email | MineralDigger</title>")) fail("Digest title is wrong.");
if (!digest.includes(`<meta name="description" content="${digestDescription}">`)) fail("Digest meta description is wrong.");
if (!digest.includes(`property="og:description" content="${digestDescription}"`)) fail("Digest og:description is wrong.");
if (!digest.includes(`name="twitter:description" content="${digestDescription}"`)) fail("Digest twitter:description is wrong.");
if (!digest.includes('action="https://buttondown.com/api/emails/embed-subscribe/mineraldigger"')) {
  fail("Digest form does not post to the MineralDigger Buttondown embed.");
}
if (!digest.includes('method="post"')) fail("Digest form method is not post.");
if (!digest.includes('type="email" name="email" required')) fail("Digest email field is not required.");
if (!digest.includes('name="metadata__postcode"')) fail("Digest form is missing the optional postcode.");
if (!digest.includes('type="hidden" name="embed" value="1"')) fail("Digest form is missing the hidden embed field.");
if (!digest.includes('data-thanks="/thanks/"')) fail("Digest form does not send sign-ups to /thanks/.");
if (!digest.includes(">Sign me up</button>")) fail("Digest button should say Sign me up.");
if (!digest.includes(digestFinePrint)) fail("Digest fine print should name Buttondown and the confirm link.");
if (!digest.includes('src="/js/newsletter.js"')) fail("Digest is missing the sign-up script.");
const digestFormEnd = digest.indexOf("</form>");
const digestFooter = digest.indexOf('<footer class="site-footer">');
if (digestFormEnd < 0 || digestFooter < digestFormEnd) fail("Digest form should sit above the footer.");
const digestAfterForm = digest.slice(digestFormEnd, digestFooter);
if (/<h[1-6]|<ul|<ol|<aside|<article/i.test(digestAfterForm)) {
  fail("Digest should go from the sign-up form to the footer.");
}
const digestFoot = digest.slice(digestFooter, digest.indexOf("</footer>"));
if (!digestFoot.includes(">Stay in touch</h2>") || !digestFoot.includes('href="/app/">Add to your phone</a>')) {
  fail("Digest footer should still include Stay in touch and Add to your phone.");
}
const newsletterJs = await readFile(join(dist, "js/newsletter.js"), "utf8");
if (!newsletterJs.includes('location.href = f.getAttribute("data-thanks") || "/thanks/"')) {
  fail("Sign-up script does not follow data-thanks to /thanks/.");
}
if (!newsletterJs.includes('mode: "no-cors"')) fail("Sign-up script should post to Buttondown in the background.");

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
const sponsorTurnaround = "Your slot is live within one working day of receiving your logo and message.";
if (!wired.includes(sponsorTurnaround)) fail("Partial Stripe feature page is missing the sponsor turnaround.");
if (/2 working days|two working days/i.test(wired)) fail("Partial Stripe feature page still says 2 working days.");
const unwired = renderFeature({
  site: { name: "MineralDigger", url: "https://mineraldigger.com" },
  stripe: {
    prices: stripeFile.prices,
    links: { featured_show: "", year_pass: "", site_sponsor: "", friday_email: "" },
  },
  generated: "2026-10-25",
});
if (!unwired.includes(sponsorTurnaround)) fail("Unpaid feature page is missing the sponsor turnaround.");
if (/2 working days|two working days/i.test(unwired)) fail("Unpaid feature page still says 2 working days.");

const submit = await readFile(join(dist, "submit/index.html"), "utf8");
if (!submit.includes("<form") || !submit.includes('action="/api/submit"')) fail("Submit form is missing.");
if (!submit.includes("<h1>Add your show</h1>")) fail("Submit page heading should be Add your show.");
const submitJs = await readFile(join(dist, "js/submit.js"), "utf8");
if (!submitJs.includes("Mail is not connected")) fail("Submit fallback should still say mail is not connected.");
if (!submitJs.includes('href="mailto:hello@mineraldigger.com"')) fail("Submit fallback is missing a mailto to hello@mineraldigger.com.");
if (submitJs.includes("mineraldigger.hq@gmail.com")) fail("Submit fallback still names the HQ Gmail.");
if (submitJs.includes("once the mailbox is open")) fail("Submit fallback still waits on the old mailbox.");
const siteFile = JSON.parse(await readFile(join(root, "data/site.json"), "utf8"));
if (siteFile.email !== "hello@mineraldigger.com") fail("data/site.json email is not hello@mineraldigger.com.");
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
  if (/2 working days|two working days/i.test(raw)) fail(`Old working-day turnaround in ${file}`);
  if (/gumroad|crystaldigger/i.test(html)) fail(`Banned name in ${file}`);
  if (raw.includes("mineraldigger.hq@gmail.com")) fail(`Generated page still names the HQ Gmail: ${file}`);
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
  if (!foot.includes(">Browse</h2>") || !foot.includes(">Organisers</h2>") || !foot.includes(">Show types</h2>") || !foot.includes(">Stay in touch</h2>")) {
    fail(`Footer columns missing in ${file}`);
  }
  for (const href of [
    "/",
    "/this-weekend/",
    "/?when=later",
    "/county/",
    "/towns/",
    "/submit/",
    "/feature/",
    "/about/",
    "/newsletter/",
    "/rock/",
    "/gem/",
    "/mineral/",
    "/fossil/",
    "/bead/",
    "/privacy/",
    "/terms/",
  ]) {
    if (!foot.includes(`href="${href}"`)) fail(`Footer in ${file} is missing ${href}`);
  }
  if (!foot.includes('href="/submit/">Submit your show</a>')) fail(`Submit label missing in ${file}`);
  if (!foot.includes('href="/feature/">Feature your show</a>')) fail(`Feature label missing in ${file}`);
  if (!foot.includes('href="/about/">How we list shows</a>')) fail(`About label missing in ${file}`);
  if (!foot.includes('href="/newsletter/">Friday email</a>')) fail(`Friday email link missing in ${file}`);
  if (!foot.includes('href="/app/">Add to your phone</a>')) fail(`Add to your phone link missing in ${file}`);
  if (!raw.includes('<link rel="manifest" href="/manifest.webmanifest">')) fail(`Manifest link missing in ${file}`);
  if (!raw.includes('<meta name="theme-color" content="#143f36">')) fail(`Theme colour missing in ${file}`);
  if (!raw.includes('src="/pwa.js"')) fail(`pwa.js missing in ${file}`);
  const headerEnd = raw.indexOf("</header>");
  const header = headerEnd > 0 ? raw.slice(0, headerEnd) : "";
  if (!/href="\/newsletter\/"(?: aria-current="page")?>Friday email<\/a>/.test(header)) {
    fail(`Header nav in ${file} is missing the Friday email label.`);
  }
  if (raw.includes("Friday list")) fail(`Friday list label still in ${file}`);
  if (raw.includes("Javascript")) fail(`Javascript typo in ${file}`);
  if (raw.includes(">Unknown<")) fail(`Visitor-facing Unknown label in ${file}`);
  if (!foot.includes('href="https://www.facebook.com/people/MineralDigger/61595681170967/" rel="me noopener" target="_blank">Facebook</a>')) {
    fail(`Facebook link missing in ${file}`);
  }
  if (!foot.includes('href="https://bsky.app/profile/mineraldigger.com" rel="me noopener" target="_blank">Bluesky</a>')) {
    fail(`Bluesky link missing in ${file}`);
  }
  if (!foot.includes("© 2026 MineralDigger.") || !foot.includes("Data last refreshed ")) fail(`Footer credit line missing in ${file}`);
  if (!/Data last refreshed \d{1,2} [A-Z][a-z]+ \d{4}\./.test(foot)) fail(`Footer date in ${file} should be a long date.`);
  if (/Data last refreshed \d{4}-\d{2}-\d{2}/.test(foot)) fail(`Footer date in ${file} is still an ISO date.`);
  if (!foot.includes('href="/privacy/">Privacy</a> · <a href="/terms/">Terms</a>')) {
    fail(`Footer in ${file} should put Terms next to Privacy.`);
  }
  if (/\bVAT\b/i.test(textOnly(raw))) fail(`VAT wording in ${file}`);
  if (/Ireland|UK\s*&|UK\s*\+|fairdigger|auctiondigger|alanconlon\.com|\/digest\//i.test(foot)) {
    fail(`Footer in ${file} has a banned link or a non-UK blurb`);
  }
}

const robots = await readFile(join(dist, "robots.txt"), "utf8");
if (!robots.includes("Sitemap: https://mineraldigger.com/sitemap.xml")) fail("robots.txt sitemap is not on mineraldigger.com.");
const sitemap = await readFile(join(dist, "sitemap.xml"), "utf8");
if (!sitemap.includes("<loc>https://mineraldigger.com/</loc>")) fail("Sitemap is missing the .com homepage.");
if (sitemap.includes("mineraldigger.co.uk")) fail("Sitemap still points at mineraldigger.co.uk.");
if (!sitemap.includes("<loc>https://mineraldigger.com/privacy/</loc>")) fail("Sitemap is missing the privacy page.");
if (!sitemap.includes("<loc>https://mineraldigger.com/terms/</loc>")) fail("Sitemap is missing the terms page.");
if (sitemap.includes("/thanks/payment")) fail("Thank-you page must stay out of the sitemap.");
if (sitemap.includes("<loc>https://mineraldigger.com/thanks/</loc>")) fail("Sign-up thank-you page must stay out of the sitemap.");
if (!sitemap.includes("<loc>https://mineraldigger.com/newsletter/</loc>")) fail("Sitemap is missing the Friday email.");
if (sitemap.includes("/digest")) fail("Digest alias must stay out of the sitemap.");
const redirects = await readFile(join(dist, "_redirects"), "utf8");
if (!redirects.includes("/digest /newsletter/ 301") || !redirects.includes("/digest/ /newsletter/ 301")) {
  fail("/digest/ should redirect to /newsletter/.");
}
if (!redirects.includes("/shows/surrey /county/surrey/ 301") || !redirects.includes("/shows/surrey/ /county/surrey/ 301")) {
  fail("/shows/surrey/ should redirect to the Surrey county page.");
}
if (sitemap.includes("404")) fail("404 page must stay out of the sitemap.");
if (!sitemap.includes("<loc>https://mineraldigger.com/app/</loc>")) fail("Sitemap is missing the add-to-phone page.");
if (sitemap.includes("/offline")) fail("Offline page must stay out of the sitemap.");
const privacy = await readFile(join(dist, "privacy/index.html"), "utf8");
if (!privacy.includes("<title>Privacy | MineralDigger</title>")) fail("Privacy title is wrong.");
if (!privacy.includes('rel="canonical" href="https://mineraldigger.com/privacy/"')) fail("Privacy canonical is wrong.");
if (!privacy.includes("Alan Conlon")) fail("Privacy page does not name Alan Conlon.");
if (!privacy.includes("hello@mineraldigger.com")) fail("Privacy page is missing the contact email.");
if (!privacy.includes('href="mailto:hello@mineraldigger.com"')) fail("Privacy contact is not a mailto link.");
if (privacy.includes("mineraldigger.hq@gmail.com")) fail("Privacy page still names the HQ Gmail.");
if (!privacy.includes("Buttondown")) fail("Privacy page does not name Buttondown.");
if (!privacy.includes("Stripe")) fail("Privacy page does not name Stripe.");
if (!privacy.includes("Cloudflare")) fail("Privacy page does not name Cloudflare.");
if (!privacy.includes('href="https://www.dataprotection.ie/"')) fail("Privacy page does not point at the Irish DPC.");
if (!privacy.includes('href="/submit/"')) fail("Privacy page does not link the submit form.");
if (!privacy.includes('href="/newsletter/"')) fail("Privacy page does not link the Friday email.");
if (!privacy.includes("Cloudflare Web Analytics, which is cookieless and does not track you across sites.")) {
  fail("Privacy page does not disclose Cloudflare Web Analytics.");
}
if (!privacy.includes("It counts page views and gives rough visitor numbers.")) {
  fail("Privacy page does not describe what Cloudflare Web Analytics counts.");
}
if (!privacy.includes("does not collect personal data")) fail("Privacy page should say Web Analytics collects no personal data.");
if (!privacy.includes("lite mode")) fail("Privacy page should say Web Analytics runs in lite mode.");
if (!privacy.includes("does not add the analytics script for visitors from the EU")) {
  fail("Privacy page should say lite mode does not record visitors from the EU.");
}
if (!privacy.includes("__cf_bm")) fail("Privacy page should name the Cloudflare security cookie __cf_bm.");
if (!privacy.includes("30 minutes of inactivity")) fail("Privacy page should say how long __cf_bm lasts.");
if (!privacy.includes("Last updated 29 October 2026")) fail("Privacy last updated line is wrong.");
if (privacy.includes("Last updated:")) fail("Privacy Last updated should not use a colon.");
if (/does not use analytics|doesn't use analytics|do not use analytics/i.test(privacy)) {
  fail("Privacy page still says there are no analytics.");
}
if (/Nothing is sent yet|does not ask you to sign up|once that email is connected/i.test(privacy)) {
  fail("Privacy page still says the Friday email is not connected.");
}
if (!privacy.includes("your postcode if you choose to give it")) {
  fail("Privacy page does not mention the optional Friday email postcode.");
}
if (/fairdigger|auctiondigger|alanconlon\.com/i.test(privacy)) fail("Privacy page names a sister site.");
if (privacy.includes("UK & Ireland") || privacy.includes("UK+IE") || privacy.includes("Eircode")) {
  fail("Privacy page uses Fair's geography.");
}
if (!privacy.includes("saved on that phone")) fail("Privacy page does not mention pages saved on the phone.");
const terms = await readFile(join(dist, "terms/index.html"), "utf8");
if (!terms.includes("<title>Terms | MineralDigger</title>")) fail("Terms title is wrong.");
if (!terms.includes("<h1>Terms</h1>")) fail("Terms heading is wrong.");
if (!terms.includes('rel="canonical" href="https://mineraldigger.com/terms/"')) fail("Terms canonical is wrong.");
if (terms.includes('name="robots" content="noindex"')) fail("Terms page should be indexed.");
if (!terms.includes("These terms cover featured listings and sponsorship on MineralDigger (mineraldigger.com). Listing on MineralDigger is free. These terms only apply when you pay for something.")) {
  fail("Terms intro is wrong.");
}
if (!terms.includes("<h2>What you can buy</h2>")) fail("Terms is missing What you can buy.");
if (!terms.includes("Featured show, £15:")) fail("Terms is missing the featured show.");
if (!terms.includes("Year pass, £99 for 12 months:")) fail("Terms is missing the year pass.");
if (!terms.includes("Site sponsor, £25 a month:")) fail("Terms is missing the site sponsor.");
if (!terms.includes("Friday email, £12 an issue:")) fail("Terms is missing the Friday email product.");
if (!terms.includes("Featured in the Friday email sent the week of your show.")) {
  fail("Terms featured show Friday email line is wrong.");
}
if (!terms.includes("Sponsor any Friday you choose (not tied to a show date).")) {
  fail("Terms Friday email product line is wrong.");
}
if (terms.includes("You pick the Friday") || terms.includes("weekend it runs")) fail("Terms still has the old Friday email lines.");
if (!terms.includes("<h2>When it goes live</h2>")) fail("Terms is missing When it goes live.");
if (!terms.includes("A featured show is featured within one working day of payment.")) fail("Terms featuring turnaround is wrong.");
if (!terms.includes("A sponsor slot is live within one working day of getting your logo and message.")) fail("Terms sponsor turnaround is wrong.");
if (!terms.includes("<h2>Renewals and cancelling</h2>")) fail("Terms is missing Renewals and cancelling.");
if (!terms.includes("Monthly options renew each month until you cancel. There is no contract.")) fail("Terms monthly renewal line is wrong.");
if (!terms.includes("To cancel, email")) fail("Terms cancel line is missing.");
if (!terms.includes('href="mailto:sponsors@mineraldigger.com"')) fail("Terms cancel address is not a mailto link.");
if (!terms.includes("Cancelling stops the next renewal, and your slot runs to the end of the period you have paid for.")) {
  fail("Terms cancellation effect is wrong.");
}
if (/billing\.stripe\.com|customer portal/i.test(terms)) fail("Terms invented a Stripe customer portal link.");
if (!terms.includes("<h2>Refunds</h2>")) fail("Terms is missing Refunds.");
if (!terms.includes("If we can't put your slot or featured show live, we refund you in full.")) fail("Terms full-refund line is wrong.");
if (!terms.includes("If the show is cancelled before your slot runs, tell us and we refund you in full.")) fail("Terms cancelled-show refund is wrong.");
if (!terms.includes("Otherwise we don't refund part-used periods or slots that have already run.")) fail("Terms no-refund line is wrong.");
if (!terms.includes("<h2>Prices and payment</h2>")) fail("Terms is missing Prices and payment.");
if (!terms.includes("Prices are in pounds and are as shown at checkout.")) fail("Terms currency line is wrong.");
if (!terms.includes("Prices shown are the total you pay.")) fail("Terms total-price line is wrong.");
if (!terms.includes("Payments are taken by Stripe, and you get a receipt by email.")) fail("Terms Stripe receipt line is wrong.");
if (!terms.includes("<h2>Content</h2>")) fail("Terms is missing Content.");
if (!terms.includes("We can decline or remove anything misleading, unlawful or unsuitable, and refund you if we do.")) {
  fail("Terms content line is wrong.");
}
if (!terms.includes("always check with the organiser or auctioneer before you travel or bid.")) fail("Terms travel line is wrong.");
if (!terms.includes("<h2>Contact</h2>")) fail("Terms is missing Contact.");
if (!terms.includes("Questions:") || !terms.includes('href="mailto:hello@mineraldigger.com"')) fail("Terms contact line is wrong.");
if (!terms.includes("Sponsorship and featured listings:")) fail("Terms sponsorship contact is wrong.");
if (!terms.includes("Last updated 29 October 2026")) fail("Terms last updated date is wrong.");
if (terms.includes("Last updated:")) fail("Terms Last updated should not use a colon.");
if (!terms.includes("for 4 weeks")) fail("Terms should describe featuring as 4 weeks.");
if (terms.includes("28 days")) fail("Terms still says 28 days.");
const termsArticle = terms.slice(terms.indexOf("<article"), terms.indexOf("</article>"));
const termsHeadings = [...termsArticle.matchAll(/<h2>([^<]+)<\/h2>/g)].map((match) => match[1]);
const expectedTermsHeadings = ["What you can buy", "When it goes live", "Renewals and cancelling", "Refunds", "Prices and payment", "Content", "Contact"];
if (termsHeadings.join("|") !== expectedTermsHeadings.join("|")) {
  fail(`Terms headings changed: ${termsHeadings.join(", ")}`);
}
const app = await readFile(join(dist, "app/index.html"), "utf8");
if (!app.includes("<title>Add MineralDigger to your phone</title>")) fail("Add-to-phone title is wrong.");
if (!app.includes('rel="canonical" href="https://mineraldigger.com/app/"')) fail("Add-to-phone canonical is wrong.");
if (!app.includes("<h1>Add MineralDigger to your phone</h1>")) fail("Add-to-phone heading is wrong.");
if (!app.includes("<h2 class=\"mt\">iPhone or iPad</h2>") || !app.includes("<h2 class=\"mt\">Android</h2>")) {
  fail("Add-to-phone steps are missing.");
}
if (!app.includes("Add to Home Screen") || !app.includes("Add to Home screen")) fail("Add-to-phone is missing the home screen steps.");
if (!app.includes("Play Protect") || !app.includes("Skip <strong>Install app</strong>")) fail("Add-to-phone should warn about the Android install prompt.");
if (!app.includes('id="a2hs-done"') || !app.includes('id="a2hs-install"')) fail("Add-to-phone is missing the install hooks.");
if (!app.includes('src="/icons/icon-192.png"')) fail("Add-to-phone is missing the icon.");
const offline = await readFile(join(dist, "offline/index.html"), "utf8");
if (!offline.includes("<h1>You're offline</h1>")) fail("Offline heading is wrong.");
if (!offline.includes('name="robots" content="noindex"')) fail("Offline page is missing noindex.");
if (!offline.includes("md-pages-")) fail("Offline page does not read the saved-page cache.");
const manifest = JSON.parse(await readFile(join(dist, "manifest.webmanifest"), "utf8"));
if (manifest.short_name !== "MineralDigger" || !manifest.name.includes("MineralDigger")) fail("Manifest name is wrong.");
if (manifest.display !== "standalone" || manifest.start_url !== "/" || manifest.lang !== "en-GB") fail("Manifest display settings are wrong.");
if (manifest.theme_color !== "#143f36" || manifest.background_color !== "#143f36") fail("Manifest colours are not the Mineral green.");
const iconSrcs = (manifest.icons || []).map((icon) => icon.src);
for (const src of ["/icons/icon-192.png", "/icons/icon-512.png", "/icons/icon-maskable-512.png"]) {
  if (!iconSrcs.includes(src)) fail(`Manifest is missing ${src}.`);
}
if (!manifest.shortcuts?.some((item) => item.url === "/this-weekend/") || !manifest.shortcuts?.some((item) => item.url === "/newsletter/")) {
  fail("Manifest shortcuts should offer this weekend and the Friday email.");
}
const pwaJs = await readFile(join(dist, "pwa.js"), "utf8");
if (!pwaJs.includes('serviceWorker.register("/sw.js"')) fail("pwa.js does not register the service worker.");
if (!pwaJs.includes("beforeinstallprompt") || !pwaJs.includes("a2hs-install")) fail("pwa.js does not hold the install prompt for /app/.");
if (!pwaJs.includes("if (android) return;")) fail("pwa.js should not offer the install prompt on Android.");
const swJs = await readFile(join(dist, "sw.js"), "utf8");
if (swJs.includes("__MD_VERSION__")) fail("Service worker version was not stamped.");
if (!swJs.includes('PREFIX = "md-"') || !swJs.includes('"/offline/"')) fail("Service worker is not the MineralDigger offline cache.");
const icon192 = pngSize(await readFile(join(dist, "icons/icon-192.png")));
const icon512 = pngSize(await readFile(join(dist, "icons/icon-512.png")));
const iconMask = pngSize(await readFile(join(dist, "icons/icon-maskable-512.png")));
if (!icon192 || icon192.width !== 192 || icon192.height !== 192) fail("icon-192.png should be 192x192.");
if (!icon512 || icon512.width !== 512 || icon512.height !== 512) fail("icon-512.png should be 512x512.");
if (!iconMask || iconMask.width !== 512 || iconMask.height !== 512) fail("icon-maskable-512.png should be 512x512.");
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
if (!headers.includes("/offline/\n  X-Robots-Tag: noindex")) fail("Offline page is missing the noindex response header.");
if (!headers.includes("Content-Type: application/manifest+json")) fail("Manifest content type is missing.");
if (!headers.includes("/sw.js\n  Cache-Control: no-cache")) fail("Service worker should not be cached.");
const thanks = await readFile(join(dist, "thanks/payment/index.html"), "utf8");
if (!thanks.includes("<title>Payment received | MineralDigger</title>")) fail("Thank-you page title is wrong.");
if (!thanks.includes('rel="canonical" href="https://mineraldigger.com/thanks/payment/"')) {
  fail("Thank-you page canonical is not https://mineraldigger.com/thanks/payment/.");
}
if (!thanks.includes('name="robots" content="noindex"')) fail("Thank-you page is missing noindex.");
if (!thanks.includes("sponsors@mineraldigger.com")) fail("Thank-you page is missing sponsors@mineraldigger.com.");
if (!thanks.includes('href="mailto:sponsors@mineraldigger.com"')) fail("Thank-you sponsor address is not a mailto link.");
if (!thanks.includes("hello@mineraldigger.com")) fail("Thank-you page is missing hello@mineraldigger.com.");
if (!thanks.includes('href="mailto:hello@mineraldigger.com"')) fail("Thank-you listing address is not a mailto link.");
if (thanks.includes("mineraldigger.hq@gmail.com")) fail("Thank-you page still names the HQ Gmail.");
if (!thanks.includes("Stripe receipt") || !thanks.includes("one working day") || !thanks.includes("12 months")) {
  fail("Thank-you page is missing the receipt and featuring promise.");
}
if (!thanks.includes("logo") || !thanks.includes("one-line message") || !thanks.includes("within one working day of receiving your logo and message")) {
  fail("Thank-you page is missing the sponsor follow-up.");
}
if (!thanks.includes("Featured in the Friday email sent the week of your show.")) {
  fail("Thank-you page featured show Friday line is wrong.");
}
if (!thanks.includes("Sponsor any Friday you choose (not tied to a show date).")) {
  fail("Thank-you page Friday email line is wrong.");
}
if (thanks.includes("You pick the Friday") || thanks.includes("weekend it runs")) {
  fail("Thank-you page still has the old Friday email lines.");
}
if (!thanks.includes('href="/terms/"')) fail("Thank-you page should link to the terms near the payment copy.");
if (!thanks.includes(">Home</a>") || !thanks.includes(">Upcoming shows</a>")) {
  fail("Thank-you page is missing the home and upcoming-shows links.");
}
const signedUp = await readFile(join(dist, "thanks/index.html"), "utf8");
if (!signedUp.includes("<title>Check your inbox | MineralDigger</title>")) fail("Sign-up thank-you title is wrong.");
if (!signedUp.includes('rel="canonical" href="https://mineraldigger.com/thanks/"')) {
  fail("Sign-up thank-you canonical is not https://mineraldigger.com/thanks/.");
}
if (!signedUp.includes('name="robots" content="noindex"')) fail("Sign-up thank-you page is missing noindex.");
if (!signedUp.includes("Nearly there")) fail("Sign-up thank-you page is missing Nearly there.");
if (!signedUp.includes("<h1>Check your inbox to confirm</h1>")) fail("Sign-up thank-you heading is wrong.");
if (!signedUp.includes("short email from MineralDigger")) fail("Sign-up thank-you page does not name MineralDigger.");
if (!signedUp.includes("Friday show email")) fail("Sign-up thank-you page does not name the Friday show email.");
if (!signedUp.includes("spam or Promotions")) fail("Sign-up thank-you page does not mention spam or Promotions.");
if (!signedUp.includes("you won't hear from us")) fail("Sign-up thank-you page is missing the ignore note.");
if (!signedUp.includes('href="/">Upcoming shows</a>') || !signedUp.includes('href="/this-weekend/">This weekend</a>')) {
  fail("Sign-up thank-you page is missing the show links.");
}
if (signedUp.includes("Payment received") || signedUp.includes("Stripe receipt")) {
  fail("Sign-up thank-you page is using the payment copy.");
}

const catalogue = JSON.parse(await readFile(join(root, "data/shows.json"), "utf8"));
const refreshedLong = longDateFromISO(catalogue.generated || isoToday());
if (!index.includes(`Data last refreshed ${refreshedLong}.`)) {
  fail(`Footer should say Data last refreshed ${refreshedLong}.`);
}
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
const rgbs = catalogue.shows.filter((show) => show.organiser?.id === "rockngem");
if (rgbs.length < 20) fail(`Expected the Rock, Gem & Bead series, found ${rgbs.length}.`);
for (const show of rgbs) {
  if (JSON.stringify(show.types) !== JSON.stringify(["rock", "gem", "bead"])) {
    fail(`${show.id} is still tagged with more than rock, gem and bead.`);
  }
}
for (const show of catalogue.shows) {
  if (show.entry?.label === "Unknown") fail(`${show.id} still labels entry as Unknown.`);
  if (show.entry?.kind === "unknown" && show.entry.label !== "Check with organiser") {
    fail(`${show.id} unknown entry label is ${show.entry?.label}.`);
  }
}
if (!sitemap.includes("<loc>https://mineraldigger.com/this-weekend/</loc>")) fail("Sitemap is missing this weekend.");
if (!sitemap.includes("<loc>https://mineraldigger.com/county/</loc>")) fail("Sitemap is missing the county index.");
if (!sitemap.includes("<loc>https://mineraldigger.com/county/surrey/</loc>")) fail("Sitemap is missing Surrey.");
if (!sitemap.includes("<loc>https://mineraldigger.com/towns/</loc>")) fail("Sitemap is missing the town index.");
const weekendPage = await readFile(join(dist, "this-weekend/index.html"), "utf8");
if (!weekendPage.includes("<h1>Shows this weekend</h1>")) fail("This weekend page heading is wrong.");
if (!weekendPage.includes('rel="canonical" href="https://mineraldigger.com/this-weekend/"')) fail("This weekend canonical is wrong.");
if (!weekendPage.includes(">Next weekend</h2>")) fail("This weekend page is missing next weekend.");
if (weekendPage.includes("shows has dates") || weekendPage.includes(">1 shows<") || weekendPage.includes("show have dates")) {
  fail("Weekend page date grammar does not match the count.");
}
const datedAfter = weekendPage.match(/<a href="\/">(\d+) (show|shows)<\/a> (has|have) dates after that\./);
const noneAfter = weekendPage.includes("No further shows are listed after that.");
if (!datedAfter && !noneAfter) fail("Weekend page should say how many shows have dates after that.");
if (datedAfter) {
  const afterCount = Number(datedAfter[1]);
  const afterNoun = datedAfter[2];
  const afterVerb = datedAfter[3];
  if (afterCount === 1 && (afterNoun !== "show" || afterVerb !== "has")) fail("One later show should read: 1 show has dates.");
  if (afterCount !== 1 && (afterNoun !== "shows" || afterVerb !== "have")) fail("Later shows should use the plural have.");
}
const worcester = await readFile(join(dist, "show/rock-gem-and-bead-show-worcester-2026-11-07/index.html"), "utf8");
if (!worcester.includes(">Check with organiser<")) fail("Worcester entry badge should say check with the organiser.");
const worcesterCopy = worcester.replace(/<script[\s\S]*?<\/script>/gi, "");
if ((worcesterCopy.match(/Check with organiser/g) || []).length !== 1) {
  fail("Worcester should say Check with organiser once.");
}
if (worcester.includes(">Unknown<")) fail("Worcester entry badge still says Unknown.");
const countyIndex = await readFile(join(dist, "county/index.html"), "utf8");
if (!countyIndex.includes("<h1>Shows by county</h1>") || !countyIndex.includes('href="/county/surrey/"')) {
  fail("County index is missing Surrey.");
}
const surrey = await readFile(join(dist, "county/surrey/index.html"), "utf8");
if (!surrey.includes("<h1>Shows in Surrey</h1>")) fail("Surrey page heading is wrong.");
if (!surrey.includes("Sunbury-on-Thames")) fail("Surrey page is missing its town.");
const townIndex = await readFile(join(dist, "towns/index.html"), "utf8");
if (!townIndex.includes("<h1>Shows by town</h1>") || !townIndex.includes('href="/town/sunbury-on-thames/"')) {
  fail("Town index is missing Sunbury-on-Thames.");
}
const mineralPage = await readFile(join(dist, "mineral/index.html"), "utf8");
const rockPage = await readFile(join(dist, "rock/index.html"), "utf8");
const fossilPage = await readFile(join(dist, "fossil/index.html"), "utf8");
const beadPage = await readFile(join(dist, "bead/index.html"), "utf8");
const rgbsLinks = (html) => (html.match(/rock-gem-and-bead-show/g) || []).length;
if (rgbsLinks(rockPage) < 10) fail("Rock page is missing the Rock, Gem and Bead series.");
if (rgbsLinks(beadPage) < 10) fail("Bead page is missing the Rock, Gem and Bead series.");
if (rgbsLinks(mineralPage) !== 0) fail("Mineral page still lists the Rock, Gem and Bead series.");
if (rgbsLinks(fossilPage) !== 0) fail("Fossil page still lists the Rock, Gem and Bead series.");
if (mineralPage === rockPage) fail("Mineral and rock pages are still identical.");

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
  if (event.name !== show.name) fail(`${show.slug} structured data name should stay the catalogue name.`);
  if (event.url !== pageUrl) fail(`${show.slug} Event url is not the mineraldigger.com show page.`);
  if (/year is matched|year was matched|matches the weekday|does not print the year|college contact page/i.test(html)) {
    fail(`${show.slug} publishes an internal note.`);
  }
  if (!html.includes('aria-label="Breadcrumb"') || !html.includes('"@type":"BreadcrumbList"')) {
    fail(`${show.slug} is missing the breadcrumb.`);
  }
  if (!html.includes(">Home</a>")) fail(`${show.slug} breadcrumb should start at Home.`);
  if (!html.includes('class="crumb-sep" aria-hidden="true">›</span>')) fail(`${show.slug} breadcrumb should use ›.`);
  if (html.includes("same series rather than a separate")) fail(`${show.slug} still has the internal series note.`);
  if (!html.includes(`href="/feature/?show=${show.slug}">Feature your show</a>`)) {
    fail(`${show.slug} should label the feature link Feature your show.`);
  }
  const whenStart = html.indexOf("<h2>When</h2>");
  const whenEnd = html.indexOf("<h2>", whenStart + 4);
  const whenCard = whenStart >= 0 && whenEnd > whenStart ? html.slice(whenStart, whenEnd) : "";
  if (show.times?.summary && !whenCard.includes(show.times.summary)) {
    fail(`${show.slug} When card is missing the opening times.`);
  }
  if (!html.includes("https://www.google.com/maps/dir/?api=1&amp;destination=")) {
    fail(`${show.slug} directions are not Google Maps.`);
  }
  if (!html.includes(`href="/feature/?show=${show.slug}"`)) fail(`${show.slug} feature link should pass the show slug.`);
  if (!html.includes('class="show-date"')) fail(`${show.slug} should show the date under the heading.`);
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
  if (String(event.url).includes("mineraldigger.co.uk")) {
    fail(`${show.slug} Event links to mineraldigger.co.uk.`);
  }
  const offer = event.offers;
  const free = show.entry.kind === "free" || show.entry.adult_gbp === 0;
  const priced = show.entry.kind === "paid" && Number.isFinite(show.entry.adult_gbp) && show.entry.adult_gbp > 0;
  if (free || priced) {
    if (!offer || offer["@type"] !== "Offer") {
      fail(`${show.slug} is missing an Offer.`);
      continue;
    }
    if (offer.availability !== "https://schema.org/InStock") fail(`${show.slug} offer availability is not InStock.`);
    if (offer.url !== pageUrl) fail(`${show.slug} offer url is not the mineraldigger.com show page.`);
    if (offer.validFrom !== offerValidFrom(refreshed)) fail(`${show.slug} offer validFrom is not the refresh date in UK time.`);
    if (String(offer.url).includes("mineraldigger.co.uk")) fail(`${show.slug} Event links to mineraldigger.co.uk.`);
    if (free) {
      if (offer.price !== "0" || offer.priceCurrency !== "GBP" || event.isAccessibleForFree !== true) {
        fail(`${show.slug} free entry should be price 0 GBP and accessible for free.`);
      }
    } else if (offer.price !== String(show.entry.adult_gbp) || offer.priceCurrency !== "GBP" || event.isAccessibleForFree !== false) {
      fail(`${show.slug} paid entry should keep the door price in GBP.`);
    }
  } else if (offer) {
    fail(`${show.slug} unknown entry should omit offers rather than emit an incomplete Offer.`);
  } else if (show.entry.kind === "paid") {
    if (event.isAccessibleForFree !== false) {
      fail(`${show.slug} paid entry with an unknown price should stay not free, without an Offer.`);
    }
  } else if ("isAccessibleForFree" in event) {
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

const publicExt = /\.(html|js|json|txt|xml|ics|webmanifest|css|svg)$/;
async function generatedFiles(dir) {
  const found = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) found.push(...(await generatedFiles(path)));
    else if (publicExt.test(entry.name)) found.push(path);
  }
  return found;
}
for (const file of await generatedFiles(dist)) {
  const raw = await readFile(file, "utf8");
  if (raw.includes("mineraldigger.hq@gmail.com")) fail(`Generated file still names the HQ Gmail: ${file}`);
}

function pageDir(file) {
  const rel = relative(dist, file).split(sep).join("/");
  const slash = rel.lastIndexOf("/");
  return slash < 0 ? "/" : `/${rel.slice(0, slash + 1)}`;
}

function localTarget(file, raw) {
  const pathOnly = raw.split("#")[0].split("?")[0];
  if (!pathOnly || /^[a-z]+:/i.test(pathOnly)) return null;
  let urlPath = pathOnly;
  if (!urlPath.startsWith("/")) {
    const parts = `${pageDir(file)}${urlPath}`.split("/");
    const stack = [];
    for (const part of parts) {
      if (!part || part === ".") continue;
      if (part === "..") stack.pop();
      else stack.push(part);
    }
    urlPath = `/${stack.join("/")}`;
  }
  const relativePath = urlPath.replace(/^\/+/, "");
  if (urlPath.endsWith("/")) return join(dist, relativePath, "index.html");
  return join(dist, relativePath);
}

for (const file of files) {
  const raw = await readFile(file, "utf8");
  for (const match of raw.matchAll(/\s(?:href|src)="([^"]*)"/g)) {
    const target = localTarget(file, match[1]);
    if (!target) continue;
    if (!existsSync(target)) fail(`Broken link ${match[1]} in ${relative(dist, file)}`);
  }
}

if (failures.length) {
  console.error(failures.join("\n"));
  process.exit(1);
}
console.log(`Checked ${files.length} pages and ${catalogue.shows.length} shows.`);
