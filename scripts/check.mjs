import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { featuredIds, stripeReady } from "./feature.mjs";
import { renderFeature } from "./render.mjs";
import { validateSubmission } from "../functions/api/validate.js";
import submitWorker, { resetRateLimit, MINERALDIGGER_SUBMIT_FROM, MINERALDIGGER_SUBMIT_TO } from "../workers/submit/src/index.js";

const root = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const dist = join(root, "dist");
const failures = [];

function fail(message) {
  failures.push(message);
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
if (!index.includes(tagline)) fail("Homepage is missing the tagline.");
if (!index.includes(subline)) fail("Homepage is missing the subline.");
if (!index.includes(footer)) fail("Homepage is missing the footer line.");
if (!index.includes('rel="canonical" href="https://mineraldigger.com/"')) fail("Homepage canonical is not https://mineraldigger.com/.");
if (!index.includes('property="og:url" content="https://mineraldigger.com/"')) fail("Homepage og:url is not https://mineraldigger.com/.");
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
const comingSoon = feature.match(/class="soon"/g) || [];
if (comingSoon.length !== 4) fail(`Expected 4 coming soon notes, found ${comingSoon.length}.`);
if (!feature.includes("Coming soon")) fail("Feature page is missing Coming soon.");
if (feature.includes("Stripe link still to be added") || feature.includes("disabled")) {
  fail("Feature page still has a disabled Stripe buy button.");
}
if (/stripe/i.test(feature) || feature.includes("buy.stripe.com") || feature.includes("REPLACE_ME")) {
  fail("Feature page still offers a Stripe buy path.");
}
const payLinks = [...feature.matchAll(/<a class="pay" href="([^"]+)"/g)].map((match) => match[1]);
if (payLinks.length !== 1 || payLinks[0] !== "/submit/") {
  fail(`Feature page pay links should only be the free submit form, found ${payLinks.join(", ") || "none"}.`);
}
const digest = await readFile(join(dist, "digest/index.html"), "utf8");
if (digest.includes("Sponsor one issue")) fail("Digest still invites a live Friday sponsor payment.");
if (!digest.includes("Friday email sponsorship is coming soon")) fail("Digest should say Friday sponsorship is coming soon.");

const stripeFile = JSON.parse(await readFile(join(root, "data/stripe.json"), "utf8"));
for (const key of ["featured_show", "year_pass", "site_sponsor", "friday_email"]) {
  if (stripeFile.links[key] !== "") fail(`data/stripe.json links.${key} should start empty.`);
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
}

const robots = await readFile(join(dist, "robots.txt"), "utf8");
if (!robots.includes("Sitemap: https://mineraldigger.com/sitemap.xml")) fail("robots.txt sitemap is not on mineraldigger.com.");
const sitemap = await readFile(join(dist, "sitemap.xml"), "utf8");
if (!sitemap.includes("<loc>https://mineraldigger.com/</loc>")) fail("Sitemap is missing the .com homepage.");
if (sitemap.includes("mineraldigger.co.uk")) fail("Sitemap still points at mineraldigger.co.uk.");

const catalogue = JSON.parse(await readFile(join(root, "data/shows.json"), "utf8"));
if (catalogue.shows.length < 35 || catalogue.shows.length > 50) fail(`Unexpected show count ${catalogue.shows.length}`);
const upcoming = catalogue.shows.filter((show) => show.end >= "2026-10-25");
if (upcoming.length < 35) fail(`Not enough upcoming shows: ${upcoming.length}`);

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
