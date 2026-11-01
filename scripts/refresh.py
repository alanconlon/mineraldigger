#!/usr/bin/env python3
"""Rebuild data/shows.json from fixtures or from organiser websites.

Examples:
  python3 scripts/refresh.py --fixtures
  python3 scripts/refresh.py --fixtures --write
  python3 scripts/refresh.py --live --write
  python3 scripts/refresh.py --live rockngem oxford-shows

Live mode fetches HTML only. It does not read Facebook, Mineralica, or dealer diaries.
Rock, Gem & Bead Shows robots.txt allows /. Their homepage is the source for their dates.
rockexchange.uk is the one host fetched with unverified TLS and a browser user agent.
If one organiser site fails, that organiser's previous shows are kept and the run continues.
A county, town or region page with a low upcoming count is warned about and kept.
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from assemble import assemble  # noqa: E402
from listings import LISTINGS_PATH, fetch_live_sitemap, load_listings, retain_listings, save_listings, warn_low_counts  # noqa: E402
from parsers.hampshire import parse_hampshire  # noqa: E402
from parsers.nature_unearthed import parse_nature  # noqa: E402
from parsers.oxfordshows import parse_oxford  # noqa: E402
from parsers.rockexchange import parse_rockexchange  # noqa: E402
from parsers.rockngem import parse_rockngem  # noqa: E402
from parsers.smls import parse_smls  # noqa: E402

FIXTURES = ROOT / "fixtures"
OUT = ROOT / "data" / "shows.json"
UA = (
    "Mozilla/5.0 (compatible; MineralDiggerRefresh/0.1; +https://mineraldigger.com) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
# rockexchange.uk serves a self-signed certificate that expired in 2021, and it
# answers 403 to the refresh user agent. A normal browser user agent with
# unverified TLS is what returns the page.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
UNVERIFIED_HOST = "rockexchange.uk"

LIVE = {
    "rockngem": ["https://www.rockngem.co/"],
    "nature-unearthed": [
        "https://www.natureunearthed.co.uk/",
        "https://www.natureunearthed.co.uk/pages/exhibitor-information",
    ],
    "oxford-shows": ["https://oxfordshows.co.uk/"],
    "bakewell-rock-exchange": ["https://rockexchange.uk/"],
    "smls": ["https://www.smls.online/show"],
    "southampton-minfoss": ["https://sotonminfoss.org.uk/smfsshow.htm"],
}


def fetch(url: str) -> str:
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    if host == UNVERIFIED_HOST:
        print(f"  {UNVERIFIED_HOST}: unverified TLS and a browser user agent")
        headers = {
            "User-Agent": BROWSER_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-GB,en;q=0.9",
        }
        context = ssl._create_unverified_context()
    else:
        headers = {"User-Agent": UA, "Accept": "text/html"}
        context = ssl.create_default_context()
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, context=context, timeout=45) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def read_fixture(name: str) -> str:
    path = FIXTURES / name
    if not path.exists():
        raise SystemExit(f"Missing fixture {path}")
    return path.read_text(encoding="utf-8")


def rows_from_fixtures(today: date) -> list[dict]:
    retrieved = today.isoformat()
    rows = []
    rows.extend(parse_rockngem(read_fixture("rockngem.html"), today=today, retrieved=retrieved))
    rows.extend(
        parse_nature(
            read_fixture("nature-home.html"),
            read_fixture("nature-exhibitors.html"),
            today=today,
            retrieved=retrieved,
        )
    )
    rows.extend(parse_oxford(read_fixture("oxford.html"), today=today, retrieved=retrieved))
    rows.extend(parse_rockexchange(read_fixture("rockexchange.html"), today=today, retrieved=retrieved))
    rows.extend(parse_smls(read_fixture("smls.html"), today=today, retrieved=retrieved))
    rows.extend(parse_hampshire(read_fixture("hampshire.html"), today=today, retrieved=retrieved))
    return rows


def parse_source(key: str, pages: list[str], today: date, retrieved: str) -> list[dict]:
    if key == "rockngem":
        return parse_rockngem(pages[0], today=today, retrieved=retrieved)
    if key == "nature-unearthed":
        home, exhibitors = pages
        return parse_nature(home, exhibitors, today=today, retrieved=retrieved)
    if key == "oxford-shows":
        return parse_oxford(pages[0], today=today, retrieved=retrieved)
    if key == "bakewell-rock-exchange":
        return parse_rockexchange(pages[0], today=today, retrieved=retrieved)
    if key == "smls":
        return parse_smls(pages[0], today=today, retrieved=retrieved)
    if key == "southampton-minfoss":
        return parse_hampshire(pages[0], today=today, retrieved=retrieved)
    raise KeyError(key)


def rows_from_live(keys: list[str], today: date) -> tuple[list[dict], list[str]]:
    """Fetch and parse each source. A failed source is listed, not fatal.

    Returns assembled shows for the sources that succeeded, plus the source
    keys that failed. Callers keep the previous shows for those keys.
    """
    retrieved = today.isoformat()
    shows = []
    failed = []
    for key in keys:
        urls = LIVE[key]
        print(f"Fetching {key} ({len(urls)} page{'s' if len(urls) != 1 else ''})")
        try:
            pages = [fetch(url) for url in urls]
            shows.extend(assemble(parse_source(key, pages, today, retrieved)))
        except (Exception, SystemExit) as exc:
            failed.append(key)
            print(
                f"Warning: {key} failed ({type(exc).__name__}: {exc}). "
                "Keeping the previous shows for that organiser.",
                file=sys.stderr,
            )
    return shows, failed


def previous_shows() -> list[dict]:
    if not OUT.exists():
        return []
    payload = json.loads(OUT.read_text(encoding="utf-8"))
    shows = payload.get("shows") if isinstance(payload, dict) else None
    return list(shows) if isinstance(shows, list) else []


def merge_kept(fresh: list[dict], kept: list[dict]) -> list[dict]:
    """Fresh rows win on id. A kept slug that clashes is given a numeric suffix."""
    fresh_ids = {show.get("id") for show in fresh}
    slugs = {show.get("slug") for show in fresh}
    merged = list(fresh)
    for show in kept:
        if show.get("id") in fresh_ids:
            continue
        slug = show.get("slug") or ""
        if slug in slugs:
            show = dict(show)
            suffix = 2
            while f"{slug}-{suffix}" in slugs:
                suffix += 1
            show["slug"] = f"{slug}-{suffix}"
        slugs.add(show.get("slug"))
        merged.append(show)
    merged.sort(key=lambda item: (item.get("start") or "", item.get("name") or "", item.get("id") or ""))
    return merged


def write_shows(shows: list[dict], today: date) -> None:
    payload = {
        "generated": today.isoformat(),
        "generator": "scripts/refresh.py",
        "shows": shows,
    }
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def summarise(shows: list[dict]) -> None:
    by_org = {}
    provisional = 0
    for show in shows:
        by_org[show["organiser"]["id"]] = by_org.get(show["organiser"]["id"], 0) + 1
        provisional += int(show["provisional"])
    print(f"{len(shows)} shows, {provisional} provisional")
    for key in sorted(by_org):
        print(f"  {key}: {by_org[key]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh MineralDigger show data from organiser HTML.")
    parser.add_argument("--fixtures", action="store_true", help="Parse the saved HTML fixtures.")
    parser.add_argument("--live", action="store_true", help="Fetch organiser websites.")
    parser.add_argument("--write", action="store_true", help="Write data/shows.json.")
    parser.add_argument("--today", default=date.today().isoformat(), help="Retrieval date, YYYY-MM-DD.")
    parser.add_argument("sources", nargs="*", help="With --live, limit to these source keys.")
    args = parser.parse_args()
    if args.fixtures == args.live:
        parser.error("Choose one of --fixtures or --live")
    today = date.fromisoformat(args.today)
    if args.fixtures:
        shows = assemble(rows_from_fixtures(today))
    else:
        keys = args.sources or list(LIVE)
        unknown = [key for key in keys if key not in LIVE]
        if unknown:
            parser.error("Unknown sources: " + ", ".join(unknown))
        shows, failed = rows_from_live(keys, today)
        if failed:
            kept = [
                show
                for show in previous_shows()
                if isinstance(show, dict) and (show.get("organiser") or {}).get("id") in failed
            ]
            print(
                f"Warning: kept {len(kept)} previous show{'s' if len(kept) != 1 else ''} "
                f"for {', '.join(failed)}.",
                file=sys.stderr,
            )
            shows = merge_kept(shows, kept)
    extra_urls = fetch_live_sitemap() if args.live else []
    retained = retain_listings(load_listings(LISTINGS_PATH), shows, today, extra_urls)
    warn_low_counts(retained, shows, today)
    summarise(shows)
    if args.write:
        if args.live and args.sources:
            raise SystemExit("Refusing to --write a partial live refresh. Run --live --write with every source, or merge by hand.")
        if not shows:
            raise SystemExit("No shows to write.")
        write_shows(shows, today)
        print(f"Wrote {OUT}")
        if save_listings(LISTINGS_PATH, retained):
            print(f"Wrote {LISTINGS_PATH}")


if __name__ == "__main__":
    main()
