# MineralDigger

UK rock, gem, mineral, fossil and bead shows on one map.

Dates, venues and entry in one place. The site is a static build for Cloudflare Pages: JSON show data, a small Node build, and Python parsers that read organiser websites.

## Run locally

```bash
npm install
npm test
npm run dev
```

`npm run dev` builds `dist/` and serves it at http://127.0.0.1:4317 . Set `PORT` if you need another port.

`npm test` runs the parser tests, builds the site, and checks the homepage copy, the four feature prices, and the submit form.

`npm start` serves an existing build without rebuilding.

## Pages

- `/` upcoming shows, with an OpenStreetMap map, type links, and date filters (this weekend, coming later). Pins sit on the venue postcode.
- `/rock/`, `/gem/`, `/mineral/`, `/fossil/`, `/bead/` type pages
- `/show/…/` one page per show, plus an `event.ics` calendar file
- `/feature/` free listing, featured show £15, year pass £99, site sponsor £25 a month, Friday email £12 an issue
- `/submit/` organiser form
- `/digest/` a preview of the Friday email. Nothing is sent
- `/about/` how shows are listed

## Data

`data/shows.json` is the catalogue the site builds from. It was generated on 25 October 2026 from organiser HTML.

| Source | Page | Rows in the seed |
| --- | --- | --- |
| Rock, Gem & Bead Shows | https://www.rockngem.co/ | 30 (3 dated 2026, 27 provisional 2027) |
| Nature Unearthed | https://www.natureunearthed.co.uk/ and the exhibitor page | 3 |
| Oxford Shows | https://oxfordshows.co.uk/ | 4 |
| Bakewell Rock Exchange | https://rockexchange.uk/ | 2 |
| Sussex Mineral and Lapidary Society | https://www.smls.online/show | 1 |
| Southampton Mineral & Fossil Society | https://sotonminfoss.org.uk/smfsshow.htm | 1 |

41 weekends in total. On 25 October 2026, 38 of them are still ahead. The Hampshire show (19 September 2026), Bakewell 2026 and the October 2026 Ardingly show stay in the file and on their own pages, and drop off the homepage once the date has passed.

Rules the parsers follow:

- Dates come from the organiser's own HTML. Dealer diaries, Mineralica and Facebook are not sources.
- Rockngem's homepage is the source for their dates. Their `robots.txt` allows `/`.
- 2027 Rockngem dates are stored as provisional because the page headings say so.
- A door price or a clock time is stored only when that page prints it for that weekend. Otherwise the list says Unknown.
- The Sussex page prints "Saturday 14th November" and no year. 14 November 2026 is that Saturday, so the row uses it and the show page says the year was matched, not printed.
- Haywards Heath College's street and postcode come from the college contact page, not from the show page. See `data/venue-supplements.json`.
- Map coordinates are postcode centroids from postcodes.io, saved in `data/venues.json`.

Refresh from the saved fixtures (no network):

```bash
python3 scripts/refresh.py --fixtures --write --today 2026-10-25
```

Refresh from the live sites:

```bash
python3 scripts/refresh.py --live --write
```

Live refresh fetches the six sources above and replaces `data/shows.json` only if every source returns a page. A partial refresh will not overwrite the file. `rockexchange.uk` answers a browser user agent. The script sends one.

Then run `npm run build`.

## Stripe

Prices on `/feature/`:

| Product | Price |
| --- | --- |
| Featured show | £15 |
| Year pass | £99 for 12 months |
| Site sponsor | £25 a month |
| Friday email | £12 an issue |

Payment Links live in `data/stripe.json` under `links`. Each one starts as an empty string. On `/feature/`, that product's button says "Stripe link still to be added" until the value is a non-empty `https://` URL. Then the button is a real link. Prices stay in `prices` and are not the links.

| Product | Price key | Link key |
| --- | --- | --- |
| Featured show | `prices.featured_show` (£15) | `links.featured_show` |
| Year pass | `prices.year_pass` (£99) | `links.year_pass` |
| Site sponsor | `prices.site_sponsor` (£25 a month) | `links.site_sponsor` |
| Friday email | `prices.friday_email` (£12) | `links.friday_email` |

When the live links exist, paste each `https://buy.stripe.com/…` URL into that key, or export these before the build (they win over the file):

- `STRIPE_FEATURED_SHOW_URL`
- `STRIPE_YEAR_PASS_URL`
- `STRIPE_SITE_SPONSOR_URL`
- `STRIPE_FRIDAY_EMAIL_URL`

Rebuild and upload `dist/` after changing them. Do not invent Payment Link ids. There is no Gumroad path.

Paid placement data, still empty:

- `data/featured.json` for a show id or an organiser id, with an inclusive `until` date
- `data/sponsors.json` for a site sponsor, or a Friday sponsor whose `issue` is that Friday (`YYYY-MM-DD`)

## Submit form

`/submit/` posts JSON to `/api/submit`.

- Locally, with no webhook, the server writes `data/inbox/*.json`. That folder is gitignored. The reply says it was saved on the machine and not emailed.
- On the public hostnames, `workers/submit/` is the mail worker. It accepts POST `/api/submit` from `https://mineraldigger.com`, `https://www.mineraldigger.com`, `https://mineraldigger.co.uk` and `https://www.mineraldigger.co.uk`. A filled honeypot (`company_website`) is accepted and not emailed. The sixth listing from the same IP inside ten minutes is refused. The message is from `submissions@mineraldigger.com` to `hello@mineraldigger.com` (`MINERALDIGGER_SUBMIT_TO` in `workers/submit/src/index.js` and in `workers/submit/wrangler.toml`).
- `hello@mineraldigger.com` has to be a verified Email Routing destination before Cloudflare will deliver that mail. The worker is in the repo. It does not assume routing is already on. If the binding is missing, or the destination is not verified, the form says mail is not connected and shows a copy of the listing. Nothing is stored.
- `functions/api/submit.js` remains a Pages fallback for when that zone route is not attached. It forwards to `SUBMISSION_WEBHOOK_URL` only when that variable is set.

Deploy the worker from `workers/submit/` after `npx wrangler login`:

```bash
npx wrangler deploy
```

The account id in `wrangler.toml` is `f856dac626b67bcd86aee0824fad569f`. The routes are only `/api/submit` on `mineraldigger.com` and `mineraldigger.co.uk`, including `www`. There is no secret for the destination address. Alan verifies `hello@mineraldigger.com` in Email Routing, and the sender domain `mineraldigger.com` has to be on the same account so `submissions@mineraldigger.com` can send.

## Deploy to Cloudflare Pages

The public site URL is `https://mineraldigger.com`. Canonical links, Open Graph URLs, the sitemap and `robots.txt` all use that host. They come from `url` in `data/site.json`. Rebuild after changing it.

`mineraldigger.co.uk` should be a second custom domain on the same Pages project, serving the same files. Do not add a redirect from `.co.uk` to `.com`.

Git-connected project (if you create one later):

- Build command: `npm run build`
- Output directory: `dist`
- Root directory: the repo root, so Pages compiles `functions/` beside `dist`
- Environment variables: the four `STRIPE_*` URLs, and `SUBMISSION_WEBHOOK_URL` when mail exists

Direct Upload of the static site, from the repo root:

```bash
npm run build
npx wrangler pages deploy dist --project-name mineraldigger --branch main
```

`dist` is the Pages root for that command. Wrangler also picks up `functions/` beside it. Dashboard drag and drop of a zip publishes the static files only and does not compile `functions/`. The public `/api/submit` mail path is the worker route above, not the Pages function.

`dist/_headers` sets a few basic response headers. `robots.txt` points at `https://mineraldigger.com/sitemap.xml`.

## Still to do before a public launch

- Keep `mineraldigger.co.uk` on the same Pages project as `mineraldigger.com`, with no redirect between them
- Create the four Stripe Payment Links and paste them into `data/stripe.json` `links` (see above), then rebuild and upload
- In Email Routing, verify the destination `hello@mineraldigger.com`, then run `npx wrangler deploy` from `workers/submit/`

Not in this version: live checkout, DNS, sending the Friday email, social accounts, Facebook scraping, mind-body-spirit listings, and Ireland.

## Brand

The name is MineralDigger. Types are rock, gem, mineral, fossil and bead. The homepage does not carry mind-body-spirit, psychic, healing or wellbeing copy. Spelling is British. The published pages do not use em dashes or exclamation marks.
