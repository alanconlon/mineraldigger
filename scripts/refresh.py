#!/usr/bin/env python3
"""Rebuild data/shows.json from fixtures or from organiser websites.

Examples:
  python3 scripts/refresh.py --fixtures
  python3 scripts/refresh.py --fixtures --write
  python3 scripts/refresh.py --live --write
  python3 scripts/refresh.py --live rockngem oxford-shows

Live mode fetches HTML only. It does not read Facebook, Mineralica, or dealer diaries.
Rock, Gem & Bead Shows robots.txt allows /. Their homepage is the source for their dates.
"""

from __future__ import annotations

import argparse
import json
import ssl
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from assemble import assemble  # noqa: E402
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
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    context = ssl.create_default_context()
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


def rows_from_live(keys: list[str], today: date) -> list[dict]:
    retrieved = today.isoformat()
    pages = {}
    for key in keys:
        urls = LIVE[key]
        print(f"Fetching {key} ({len(urls)} page{'s' if len(urls) != 1 else ''})")
        pages[key] = [fetch(url) for url in urls]
    rows = []
    if "rockngem" in pages:
        rows.extend(parse_rockngem(pages["rockngem"][0], today=today, retrieved=retrieved))
    if "nature-unearthed" in pages:
        home, exhibitors = pages["nature-unearthed"]
        rows.extend(parse_nature(home, exhibitors, today=today, retrieved=retrieved))
    if "oxford-shows" in pages:
        rows.extend(parse_oxford(pages["oxford-shows"][0], today=today, retrieved=retrieved))
    if "bakewell-rock-exchange" in pages:
        rows.extend(parse_rockexchange(pages["bakewell-rock-exchange"][0], today=today, retrieved=retrieved))
    if "smls" in pages:
        rows.extend(parse_smls(pages["smls"][0], today=today, retrieved=retrieved))
    if "southampton-minfoss" in pages:
        rows.extend(parse_hampshire(pages["southampton-minfoss"][0], today=today, retrieved=retrieved))
    return rows


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
        rows = rows_from_fixtures(today)
    else:
        keys = args.sources or list(LIVE)
        unknown = [key for key in keys if key not in LIVE]
        if unknown:
            parser.error("Unknown sources: " + ", ".join(unknown))
        rows = rows_from_live(keys, today)
    shows = assemble(rows)
    summarise(shows)
    if args.write:
        if args.live and args.sources:
            raise SystemExit("Refusing to --write a partial live refresh. Run --live --write with every source, or merge by hand.")
        write_shows(shows, today)
        print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
