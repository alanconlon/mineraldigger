#!/usr/bin/env python3
"""Write the MineralDigger Friday email as Markdown.

Reads data/shows.json (the catalogue built from organiser pages) and writes
out/newsletter-YYYY-MM-DD.md. The date is the issue Friday: the coming Friday,
or the next Friday when today is Saturday or Sunday. /digest/ is the
sign-up page and does not list that window.

The note lists shows on that weekend and over the next couple of weeks
(the two weekends after it). Each line uses the date, venue, and entry
already stored for that show. A door price is included only when the
catalogue has one. Empty weekends are left out. If that window is empty
and later shows are still on the list, the file is a short coming-up note.
If nothing is upcoming, nothing is written.

This script does not send email. When sponsors.friday is empty, or its issue
is not that Friday, the draft includes one invitation to sponsor the email
(£12 an issue) or the site (£25 a month). A booked Friday sponsor replaces
that line. The sign-up page does not show either.

Examples:
  python3 scripts/digest.py
  python3 scripts/digest.py --today 2026-10-28
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHOWS_PATH = ROOT / "data" / "shows.json"
SITE_PATH = ROOT / "data" / "site.json"
SPONSORS_PATH = ROOT / "data" / "sponsors.json"
FEATURED_PATH = ROOT / "data" / "featured.json"
OUT_DIR = ROOT / "out"

SITE_URL = "https://mineraldigger.com"
EDITOR_MODE = "<!-- buttondown-editor-mode: plaintext -->"
# Sunday of the second weekend after the issue Friday.
NEAR_END_OFFSET = 16
COMING_UP_LIMIT = 4

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MONTHS = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]
TYPE_ORDER = ("rock", "gem", "mineral", "fossil", "bead")
TYPE_LABELS = {
    "rock": "Rock shows",
    "gem": "Gem shows",
    "mineral": "Mineral shows",
    "fossil": "Fossil shows",
    "bead": "Bead shows",
}


def parse_iso(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def issue_friday(today: date) -> date:
    """Coming Friday, or the next Friday when today is Saturday or Sunday.

    Same rule as digestWeekend in src/js/format.js. JavaScript's getDay is
    Sunday 0 through Saturday 6. Python's weekday is Monday 0 through Sunday 6.
    """
    js_day = (today.weekday() + 1) % 7
    if js_day == 6:
        return today + timedelta(days=6)
    if js_day == 0:
        return today + timedelta(days=5)
    if js_day == 5:
        return today
    return today + timedelta(days=5 - js_day)


def format_day(value: date) -> str:
    return f"{WEEKDAYS[value.weekday()]} {value.day} {MONTHS[value.month - 1]} {value.year}"


def format_range(start: date, end: date) -> str:
    if start == end:
        return format_day(start)
    return f"{format_day(start)} to {format_day(end)}"


def subject_for(friday: date) -> str:
    return f"Mineral shows for {friday.day} {MONTHS[friday.month - 1]} {friday.year}"


def newsletter_path(out_dir: Path, friday: date) -> Path:
    return out_dir / f"newsletter-{friday.isoformat()}.md"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def featured_ids(shows: list[dict], featured: dict | None, today: date) -> set[str]:
    """Match scripts/feature.mjs. until is inclusive."""
    today_iso = today.isoformat()
    found: set[str] = set()
    featured = featured or {}
    for row in featured.get("shows") or []:
        if row and row.get("id") and str(row.get("until") or "") >= today_iso:
            found.add(row["id"])
    organisers = {
        row["id"]
        for row in (featured.get("organisers") or [])
        if row and row.get("id") and str(row.get("until") or "") >= today_iso
    }
    for show in shows:
        organiser = (show.get("organiser") or {}).get("id")
        if organiser in organisers and show.get("end", "") >= today_iso:
            found.add(show["id"])
    return found


def overlaps(show: dict, start: date, end: date) -> bool:
    return show["start"] <= end.isoformat() and show["end"] >= start.isoformat()


def weekend_friday(day: date) -> date:
    js_day = (day.weekday() + 1) % 7
    if js_day == 5:
        return day
    if js_day == 6:
        return day - timedelta(days=1)
    if js_day == 0:
        return day - timedelta(days=2)
    return day + timedelta(days=5 - js_day)


def _clean(value: str | None) -> str:
    return (value or "").strip().rstrip(".")


def entry_bits(entry: dict | None) -> list[str]:
    entry = entry or {}
    kind = entry.get("kind")
    notes = _clean(entry.get("notes"))
    if kind == "paid":
        label = _clean(entry.get("label"))
        bits = []
        if label and label.lower() != "unknown":
            bits.append(label)
        if notes:
            bits.append(notes)
        return bits
    if kind == "free":
        return [notes] if notes else ["Free entry"]
    return []


def time_bits(times: dict | None) -> list[str]:
    times = times or {}
    bits = []
    summary = _clean(times.get("summary"))
    notes = _clean(times.get("notes"))
    if summary:
        bits.append(summary)
    if notes:
        bits.append(notes)
    return bits


def venue_phrase(venue: dict | None) -> str:
    venue = venue or {}
    parts: list[str] = []
    for key in ("name", "street", "town", "postcode"):
        value = (venue.get(key) or "").strip()
        if value and value not in parts:
            parts.append(value)
    return ", ".join(parts)


def show_bits(show: dict, featured: set[str]) -> list[str]:
    start = parse_iso(show["start"])
    end = parse_iso(show["end"])
    bits = [format_range(start, end)]
    place = venue_phrase(show.get("venue"))
    if place:
        bits.append(place)
    bits.extend(entry_bits(show.get("entry")))
    bits.extend(time_bits(show.get("times")))
    if show.get("provisional"):
        bits.append("The organiser lists this date as provisional")
    if show.get("year_inferred"):
        bits.append("The year is matched from the weekday, and the organiser page does not print the year")
    if show.get("id") in featured:
        bits.insert(0, "Featured")
    return bits


def show_markdown(show: dict, site_url: str, featured: set[str]) -> str:
    slug = show["slug"]
    url = f"{site_url.rstrip('/')}/show/{slug}/"
    town = ((show.get("venue") or {}).get("town") or "").strip()
    title = show["name"]
    if town:
        title = f"{title}, {town}"
    sentence = ". ".join(show_bits(show, featured)) + "."
    return f"[{title}]({url})\n\n{sentence}\n"


def heading_span(shows: list[dict]) -> str:
    start = min(parse_iso(show["start"]) for show in shows)
    end = max(parse_iso(show["end"]) for show in shows)
    if start == end:
        return f"{start.day} {MONTHS[start.month - 1]}"
    if start.month == end.month and start.year == end.year:
        return f"{start.day} to {end.day} {MONTHS[start.month - 1]}"
    if start.year == end.year:
        return f"{start.day} {MONTHS[start.month - 1]} to {end.day} {MONTHS[end.month - 1]}"
    return (
        f"{start.day} {MONTHS[start.month - 1]} {start.year} "
        f"to {end.day} {MONTHS[end.month - 1]} {end.year}"
    )


def empty_friday_sponsor(site_url: str) -> str:
    """Invitation used when no Friday email sponsor is booked for that issue.

    Copy approved 28 October 2026. Amounts match /feature/: Friday email £12
    an issue, site sponsor £25 a month.
    """
    base = site_url.rstrip("/")
    return (
        "Run a rock, gem or lapidary shop? Sponsor this email for £12 an issue, "
        f"or the site for £25 a month: [see the sponsor options]({base}/feature/)."
    )


def sponsor_markdown(sponsors: dict | None, friday: date, site_url: str = SITE_URL) -> str:
    """Booked Friday sponsor, or the empty-slot invitation when that issue is open."""
    row = (sponsors or {}).get("friday") if isinstance(sponsors, dict) else None
    if isinstance(row, dict) and row.get("issue") == friday.isoformat():
        name = (row.get("name") or "").strip()
        if name:
            url = (row.get("url") or "").strip()
            line = (row.get("line") or "").strip()
            head = f"[{name}]({url})" if url.startswith("https://") else name
            text = f"Sponsored. {head}."
            if line:
                text = f"{text} {line}"
            return text
    return empty_friday_sponsor(site_url)


def hub_lines(shows: list[dict], site_url: str) -> list[str]:
    base = site_url.rstrip("/")
    present = {kind for show in shows for kind in show.get("types") or []}
    lines = [f"- [All shows]({base}/)"]
    for kind in TYPE_ORDER:
        if kind in present:
            lines.append(f"- [{TYPE_LABELS[kind]}]({base}/{kind}/)")
    return lines


def sort_shows(shows: list[dict]) -> list[dict]:
    return sorted(shows, key=lambda show: (show["start"], (show.get("venue") or {}).get("town") or "", show["name"], show["id"]))


def render_newsletter(
    shows: list[dict],
    today: date,
    site_url: str = SITE_URL,
    sponsors: dict | None = None,
    featured: dict | None = None,
) -> tuple[date, str] | None:
    """Return (issue Friday, markdown), or None when no show is still ahead."""
    site_url = site_url.rstrip("/")
    friday = issue_friday(today)
    friday_iso = friday.isoformat()
    upcoming = [show for show in shows if show.get("end", "") >= friday_iso]
    if not upcoming:
        return None

    window_end = friday + timedelta(days=NEAR_END_OFFSET)
    weekend_end = friday + timedelta(days=2)
    pinned = featured_ids(shows, featured, today)
    this_weekend = sort_shows([show for show in upcoming if overlaps(show, friday, weekend_end)])
    this_ids = {show["id"] for show in this_weekend}
    following = sort_shows(
        [
            show
            for show in upcoming
            if show["id"] not in this_ids and overlaps(show, weekend_end + timedelta(days=1), window_end)
        ]
    )
    later = sort_shows([show for show in upcoming if show["start"] > window_end.isoformat()])

    listed = this_weekend + following
    coming_up: list[dict] = []
    if not listed:
        coming_up = later[:COMING_UP_LIMIT]
        listed = coming_up
        if not listed:
            return None

    blocks: list[str] = [
        EDITOR_MODE,
        "",
        f"# {subject_for(friday)}",
        "",
        (
            "A Friday list of UK rock, gem, mineral, fossil and bead shows. "
            "Dates, venues, times and entry come from the MineralDigger catalogue, "
            "checked against organiser websites. Confirm with the organiser before you travel."
        ),
        "",
    ]
    blocks.extend([sponsor_markdown(sponsors, friday, site_url), ""])

    if this_weekend:
        blocks.extend(["## This weekend", ""])
        for show in this_weekend:
            blocks.extend([show_markdown(show, site_url, pinned).rstrip(), ""])

    if following:
        blocks.extend(["## The next couple of weeks", ""])
        groups: dict[date, list[dict]] = {}
        for show in following:
            groups.setdefault(weekend_friday(parse_iso(show["start"])), []).append(show)
        for key in sorted(groups):
            group = groups[key]
            blocks.extend([f"### {heading_span(group)}", ""])
            for show in group:
                blocks.extend([show_markdown(show, site_url, pinned).rstrip(), ""])

    if coming_up:
        blocks.extend(["## Coming up", "", "The next dates on the list.", ""])
        for show in coming_up:
            blocks.extend([show_markdown(show, site_url, pinned).rstrip(), ""])
        rest = len(later) - len(coming_up)
        if rest:
            blocks.extend([f"Another {rest} {'show is' if rest == 1 else 'shows are'} on the map.", ""])
    elif later:
        blocks.extend(["Further dates are on the map.", ""])

    blocks.extend(["## On the map", ""])
    blocks.extend(hub_lines(listed, site_url))
    blocks.extend(
        [
            "",
            f"Subscribe and find shows at [{site_url.removeprefix('https://').removeprefix('http://')}]({site_url}/).",
            "",
        ]
    )
    return friday, "\n".join(blocks)


def write_newsletter(
    today: date,
    shows_path: Path = SHOWS_PATH,
    site_path: Path = SITE_PATH,
    sponsors_path: Path = SPONSORS_PATH,
    featured_path: Path = FEATURED_PATH,
    out_dir: Path = OUT_DIR,
) -> Path | None:
    payload = load_json(shows_path)
    shows = payload.get("shows") if isinstance(payload, dict) else payload
    site_url = SITE_URL
    if site_path.is_file():
        site_url = (load_json(site_path).get("url") or SITE_URL).rstrip("/")
    sponsors = load_json(sponsors_path) if sponsors_path.is_file() else None
    featured = load_json(featured_path) if featured_path.is_file() else None
    rendered = render_newsletter(shows or [], today, site_url, sponsors, featured)
    if rendered is None:
        return None
    friday, markdown = rendered
    path = newsletter_path(out_dir, friday)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the MineralDigger Friday email as Markdown.")
    parser.add_argument("--today", help="Issue date as YYYY-MM-DD. Defaults to today.")
    parser.add_argument("--shows", type=Path, default=SHOWS_PATH)
    parser.add_argument("--site", type=Path, default=SITE_PATH)
    parser.add_argument("--sponsors", type=Path, default=SPONSORS_PATH)
    parser.add_argument("--featured", type=Path, default=FEATURED_PATH)
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    args = parser.parse_args(argv)
    today = parse_iso(args.today) if args.today else date.today()
    path = write_newsletter(today, args.shows, args.site, args.sponsors, args.featured, args.out)
    if path is None:
        print("No upcoming shows. Nothing written.")
        return 0
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
