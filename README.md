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
- `/this-weekend/` the shows on this weekend, and the next weekend, as a real page
- `/county/` and `/county/…/` upcoming shows by county. `/shows/surrey/` redirects to `/county/surrey/`
- `/towns/` and `/town/…/` upcoming shows by town
- `/rock/`, `/gem/`, `/mineral/`, `/fossil/`, `/bead/` type pages
- `/show/…/` one page per show, plus an `event.ics` calendar file
- `/feature/` free listing, featured show £15, year pass £99, site sponsor £25 a month, Friday email £12 an issue. The four paid cards link to live Stripe checkout.
- `/thanks/payment/` post-payment thank-you page. It is `noindex` and is not in the sitemap. IndexNow is not given this URL.
- `/thanks/` after a Friday email sign-up. It is `noindex` and is not in the sitemap.
- `/submit/` organiser form
- `/newsletter/` the Friday email. Visitors sign up through Buttondown. After the form, the page goes to the site footer. It does not send the issue. Drafts are made with the scripts in Friday email drafts below.
- `/digest/` redirects to `/newsletter/`.
- `/app/` how to add MineralDigger to a phone home screen. Nothing to install from an app store.
- `/offline/` shown when there is no signal and that page has not been saved on the phone. It is `noindex` and is not in the sitemap.
- `/about/` how shows are listed
- `/privacy/` what the site collects, who handles it, and how to ask about it
- `/terms/` what a featured show and a sponsor slot include, when they go live, renewals, cancelling and refunds

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
- A door price or a clock time is stored only when that page prints it for that weekend. Otherwise the list says check with the organiser.
- Rock, Gem & Bead Shows are tagged rock, gem and bead. The date list does not assign mineral or fossil to each weekend, so those type pages are not a copy of that series. Nature Unearthed is tagged from the weekend the page actually describes.
- The Sussex page prints "Saturday 14th November" and no year. 14 November 2026 is that Saturday, so the row uses it and the show page says the year was matched, not printed.
- Haywards Heath College's street and postcode come from the college contact page, not from the show page. See `data/venue-supplements.json`.
- Map coordinates are postcode centroids from postcodes.io, saved in `data/venues.json`.
- Upcoming Bakewell rows do not publish https://rockexchange.uk/. That host has an expired certificate and returns HTTP 500, and there is no replacement URL. The phone number stays. The 2026 weekend has passed, so that row still records the URL it was read from.

Refresh from the saved fixtures (no network):

```bash
python3 scripts/refresh.py --fixtures --write --today 2026-10-25
```

Refresh from the live sites:

```bash
python3 scripts/refresh.py --live --write
```

Live refresh fetches the six sources above. `rockexchange.uk` is the one host fetched with unverified TLS and a browser user agent, because its certificate is self-signed and expired and it refuses the refresh user agent. If one organiser site fails, the script logs a warning and keeps that organiser's shows from the current `data/shows.json`. The other sources are still written. Naming only some sources with `--live --write` is still refused.

Then run `npm run build`.

## Stripe

Prices on `/feature/`:

| Product | Price |
| --- | --- |
| Featured show | £15 |
| Year pass | £99 for 12 months |
| Site sponsor | £25 a month |
| Friday email | £12 an issue |

Featured show: Featured in the Friday email sent the week of your show. Friday email: Sponsor any Friday you choose (not tied to a show date).

The four live Payment Links are in `data/stripe.json` under `links`. Prices stay in `prices`. On `/feature/`, a non-empty `https://` URL is a pay button (`Pay £… with Stripe`). An empty link still says "Coming soon" and is not a buy button.

| Product | Price key | Link |
| --- | --- | --- |
| Featured show | `prices.featured_show` (£15) | `links.featured_show` |
| Year pass | `prices.year_pass` (£99) | `links.year_pass` |
| Site sponsor | `prices.site_sponsor` (£25 a month) | `links.site_sponsor` |
| Friday email | `prices.friday_email` (£12) | `links.friday_email` |

These environment variables override the file at build time:

- `STRIPE_FEATURED_SHOW_URL`
- `STRIPE_YEAR_PASS_URL`
- `STRIPE_SITE_SPONSOR_URL`
- `STRIPE_FRIDAY_EMAIL_URL`

Rebuild and upload `dist/` after changing a link. Do not invent Payment Link ids. There is no Gumroad path.

After payment, Stripe customers should land on `https://mineraldigger.com/thanks/payment/`. That page is `noindex`, omitted from `sitemap.xml`, and not submitted anywhere else. It asks sponsors to email a logo, a one-line message, and which package to `sponsors@mineraldigger.com`. A featured listing is live within one working day. A sponsor slot is live within one working day of receiving the logo and message. Questions about a listing go to `hello@mineraldigger.com`.

Paid placement data, still empty:

- `data/featured.json` for a show id or an organiser id, with an inclusive `until` date
- `data/sponsors.json` for a site sponsor, or a Friday sponsor whose `issue` is that Friday (`YYYY-MM-DD`). The Friday sponsor is written into the email draft. When that slot is empty, the draft invites a sponsor instead. The sign-up page does not show it.

## Submit form

`/submit/` posts JSON to `/api/submit`.

- Locally, with no webhook, the server writes `data/inbox/*.json`. That folder is gitignored. The reply says it was saved on the machine and not emailed.
- On the public hostnames, `workers/submit/` is the mail worker. It accepts POST `/api/submit` from `https://mineraldigger.com`, `https://www.mineraldigger.com`, `https://mineraldigger.co.uk` and `https://www.mineraldigger.co.uk`. `/submit/` loads Cloudflare Turnstile and sends the token as `cf-turnstile-response`. The worker checks that token with Cloudflare before it emails the listing. The check uses `TURNSTILE_SECRET_KEY`, the token, and `CF-Connecting-IP`. A missing or failed check is HTTP 403, and the page asks the visitor to try the security check again. A filled honeypot (`company_website`) is accepted and not emailed, and it is not sent to Turnstile. The sixth listing from the same IP inside ten minutes is refused. The message is from `submissions@mineraldigger.com` to `mineraldigger.hq@gmail.com` (`MINERALDIGGER_SUBMIT_TO` in `workers/submit/src/index.js` and in `workers/submit/wrangler.toml`).
- `mineraldigger.hq@gmail.com` has to be a verified Email Routing destination before Cloudflare will deliver that mail. The worker is in the repo. It does not assume routing is already on. If the binding is missing, or the destination is not verified, the form says mail is not connected and shows a copy of the listing. Nothing is stored.
- `functions/api/submit.js` remains a Pages fallback for when that zone route is not attached. It uses the same Turnstile check, then forwards to `SUBMISSION_WEBHOOK_URL` only when that variable is set. On localhost and `127.0.0.1` the page can still save a listing in `data/inbox/` when the widget has no token. The public worker does not allow that.

Deploy the site first, then the worker. The live worker ignores the extra token field, so listings keep working while the new page goes out. After the worker deploy, a listing without a passing token is refused. Deploying the worker first would refuse listings until the new page is live.

Deploy the worker from `workers/submit/` after `npx wrangler login`:

```bash
npx wrangler deploy
```

That command keeps secrets already stored on the worker, including `TURNSTILE_SECRET_KEY`. Do not put that value in the repo or in the workflow.

The account id in `wrangler.toml` is `f856dac626b67bcd86aee0824fad569f`. The routes are only `/api/submit` on `mineraldigger.com` and `mineraldigger.co.uk`, including `www`. There is no secret for the destination address. Alan verifies `mineraldigger.hq@gmail.com` as an Email Routing destination, and the sender domain `mineraldigger.com` has to be on the same account so `submissions@mineraldigger.com` can send.

`.github/workflows/deploy-submit-worker.yml` deploys the same worker when someone starts it from the Actions tab. A merge does not deploy it. It reads two repository secrets, the same names the Pages workflow uses:

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`

The token needs permission to deploy this worker. The workflow does not set `TURNSTILE_SECRET_KEY`. If the Pages fallback is actually reached, that project needs the same secret name. The custom-domain routes above win when they are attached, so the fallback stays unused.

## Deploy to Cloudflare Pages

The public site URL is `https://mineraldigger.com`. Canonical links, Open Graph URLs, the sitemap and `robots.txt` all use that host. They come from `url` in `data/site.json`. Rebuild after changing it.

`mineraldigger.co.uk` should be a second custom domain on the same Pages project, serving the same files. Do not add a redirect from `.co.uk` to `.com`.

Git-connected project (if you create one later):

- Build command: `npm run build`
- Output directory: `dist`
- Root directory: the repo root, so Pages compiles `functions/` beside `dist`
- Environment variables: the four `STRIPE_*` URLs, and `SUBMISSION_WEBHOOK_URL` when mail exists

Direct Upload of the static site, from the repo root. After the deploy has finished, tell IndexNow about pages on mineraldigger.com:

```bash
npm run build
npx wrangler pages deploy dist --project-name mineraldigger --branch main
python3 scripts/indexnow.py
```

`dist` is the Pages root for that command. Wrangler also picks up `functions/` beside it. Dashboard drag and drop of a zip publishes the static files only and does not compile `functions/`. The public `/api/submit` mail path is the worker route above, not the Pages function.

Daily refresh is `.github/workflows/refresh-and-deploy.yml`. It runs at 05:15 UTC (05:15 GMT, 06:15 BST), and it can also be started by hand with `workflow_dispatch`. The job fetches the organiser pages (`python3 scripts/refresh.py --live --write`), runs `npm run build`, and deploys with Wrangler. It does not commit `data/shows.json`. Catalogue changes on main still go through pull requests. The deployment is marked dirty because the refreshed catalogue exists only on the runner. When IndexNow accepts URLs, the job commits `data/indexnow_state.json` with `[skip ci]` in the message, and rebases if another push lands first.

```bash
npx wrangler pages deploy dist --project-name mineraldigger --branch main
```

The workflow reads two repository secrets, the same names FairDigger uses:

- `CLOUDFLARE_API_TOKEN`
- `CLOUDFLARE_ACCOUNT_ID`

It does not deploy on a push. A merge of this workflow does not by itself publish the site.

After that Pages deploy succeeds, the workflow runs `python3 scripts/indexnow.py`. The build stamps each sitemap `lastmod` first. A page whose content is unchanged keeps the stored date. A new or changed page uses the build date. The script then hashes the built HTML for each `mineraldigger.com` sitemap URL and compares it with `data/indexnow_state.json`. The hash ignores the "Data last refreshed" date, the show "Retrieved" date, the offer `validFrom` stamp, and asset `?v=` tokens, so the daily rebuild does not submit the same pages again. It POSTs only new or changed URLs to `https://api.indexnow.org/indexnow`. The JSON body is `host`, `key`, `keyLocation`, and `urlList`, with at most 10000 URLs in one request. `host` is `mineraldigger.com`. URLs on `mineraldigger.co.uk` are not submitted. The key file is `3b35b2fc93db4757a34032329daf6509.txt` at the site root, so `https://mineraldigger.com/3b35b2fc93db4757a34032329daf6509.txt` serves the key. The key is public by design. The state file records the content hash and `lastmod` for each URL already accepted, including the 94 URLs accepted on 30 October 2026. The state file is updated only after HTTP 200 or 202. Any other response is logged, and the script still exits 0, so IndexNow cannot fail the deploy. `--dry-run` prints the URLs and does not POST or write the state file.

The state file is written only after HTTP 200 or 202. The workflow then commits it when the file changed, so the next run skips URLs whose content hash is unchanged. An unchanged file is left uncommitted. A manual upload should still commit the state file if the script rewrote it outside the workflow.

`dist/_headers` sets a few basic response headers, including `application/manifest+json` for `manifest.webmanifest` and `no-cache` for `sw.js`. `dist/_redirects` sends `/digest/` to `/newsletter/`. `robots.txt` points at `https://mineraldigger.com/sitemap.xml`.

The home screen install uses `manifest.webmanifest`, `pwa.js` and `sw.js` at the site root, plus `icons/icon-192.png`, `icons/icon-512.png` and `icons/icon-maskable-512.png`. On Android the in-page install button stays hidden, because that prompt can trigger Play Protect. The `/app/` steps use Add to Home screen instead.

## Friday email drafts

`scripts/digest.py` reads `data/shows.json` and writes `out/newsletter-YYYY-MM-DD.md`. The date is the coming Friday. On a Saturday or Sunday it looks ahead to the next weekend. That list is for the email draft. `/newsletter/` is the sign-up page and does not print it.

If that Friday has no sponsor in `data/sponsors.json`, the draft adds one sponsor line, as its own paragraph straight after the opening intro: this week's sponsor slot is free, this Friday email is £12, or the site is £25 a month, linking to `https://mineraldigger.com/feature/`. A booked Friday sponsor replaces that line.

The note lists shows that weekend and for the next couple of weeks (the two weekends after it): date, venue, times and entry when the catalogue already has them. It does not invent a price or a show. A weekend with nothing on is left out. If that whole window is empty and later shows are still listed, the file is a short coming-up note. If nothing is upcoming, it writes nothing.

`scripts/buttondown_draft.py` uploads that file to the [mineraldigger](https://buttondown.com/mineraldigger) Buttondown newsletter as a draft. It calls `https://api.buttondown.com/v1` with `Authorization: Token` and `status` set to `draft`. It never sends or schedules. If a draft with the same subject already exists, it updates that draft and does not create a second one.

Set `MINERALDIGGER_BUTTONDOWN_API_KEY` to the API key for that newsletter. The script does not read `BUTTONDOWN_API_KEY`. With the variable unset, or with `--dry-run`, it prints the subject and makes no request, so a run without a key still exits cleanly.

```bash
python3 scripts/digest.py
python3 scripts/buttondown_draft.py
```

`out/` is generated and is not committed. Sign-up on `/newsletter/` posts to Buttondown. These scripts create a draft only. They do not send or schedule the list.

## Facebook and Bluesky

Ann drafts the weekly posts. The Diggers CEO publishes them after Alan has OK'd the text.

`scripts/facebook_post.py` and `scripts/bluesky_post.py` read upcoming UK shows from `data/shows.json`. With no extra flag they print a draft and stop. A dry run leaves both logs untouched. The Facebook dry run makes no request. The Bluesky dry run reads the public `@mineraldigger.com` feed, without logging in, so it can pass over a show posted in the last 14 days by its page link or its venue. `--allow-repeat` keeps that show. If the feed cannot be read, a dry run uses the log only and `--publish` stops without posting.

Even ISO weeks lead with the next show and link to that show on mineraldigger.com. Odd weeks lead with a type hub (`/rock/`, `/gem/`, `/mineral/`, `/fossil/`, `/bead/`) and the next show of that type. The copy is plain British English, in the same voice as the Friday email, with no em dashes, no en dashes and no exclamation marks. Dates sit next to the weekday, as in Saturday 7 November. A door price is included only when the catalogue already has one.

The post text writes the page as `mineraldigger.com/...`. The full `https://mineraldigger.com/...` URL is only the Facebook link field or the Bluesky link card. `--publish` refuses the post when the text contains `!`, an en dash, an em dash, or `https://`.

```bash
python3 scripts/facebook_post.py --today 2026-10-28
python3 scripts/bluesky_post.py --today 2026-10-28
```

Use the same `--today` on the draft and on the publish, so the text Alan saw is the text that goes out.

After Alan OKs both drafts:

```bash
python3 scripts/facebook_post.py --today 2026-10-28 --publish
python3 scripts/bluesky_post.py --today 2026-10-28 --publish
```

Each network keeps a log keyed by ISO week (`2026-W44`): `growth/facebook_posts.json` and `growth/bluesky_posts.json`. When that week is already there, `--publish` stops. `--force` posts the week again and replaces that one key.

Facebook posts to the Page in `growth/facebook_page.json` (Graph id `1419817424553579`). The page token is `MINERALDIGGER_FB_PAGE_TOKEN`, or the entry for that page id in `~/.secrets/fb_pages.json`. That file stays on the machine. It can map the page id to a token, or use `page_id` and `access_token`.

Bluesky posts as `mineraldigger.com`. The app password is `MINERALDIGGER_BLUESKY_APP_PASSWORD`, or the `mineraldigger.com` entry in `~/.secrets/bluesky.json`.

## Still to do before a public launch

- Keep `mineraldigger.co.uk` on the same Pages project as `mineraldigger.com`, with no redirect between them
- In Email Routing, verify the destination `mineraldigger.hq@gmail.com`, then run `npx wrangler deploy` from `workers/submit/` after the submit page that sends the Turnstile token is already live

Not in this version: DNS, mailing the Friday list automatically, Facebook scraping, mind-body-spirit listings, and Ireland. Sign-up is on `/newsletter/` through Buttondown. The Friday email scripts above create a Buttondown draft only. Weekly Facebook and Bluesky posts are drafted with the scripts above and go out only when someone runs both with `--publish` after Alan has OK'd the text. Live Stripe checkout for the four products is on `/feature/`. Facebook and Bluesky are linked from the footer.

## Brand

The name is MineralDigger. Types are rock, gem, mineral, fossil and bead. The homepage does not carry mind-body-spirit, psychic, healing or wellbeing copy. Spelling is British. The published pages do not use em dashes or exclamation marks.
