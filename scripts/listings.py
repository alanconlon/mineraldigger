#!/usr/bin/env python3
"""Listing pages that stay live when the upcoming show count is low.

A county, town or region page used to be built only when it had at least
WARN_BELOW upcoming shows. Below that it was left out, so the URL 404ed and
dropped out of the sitemap and IndexNow. WARN_BELOW is now a warning level.
The page stays in the build, the sitemap and IndexNow.

Type pages were already built with any count, including zero. A type page
below WARN_BELOW is warned about in the same way, and it is not noindexed.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LISTINGS_PATH = ROOT / "data" / "listings.json"
LIVE_SITEMAP = "https://mineraldigger.com/sitemap.xml"
HOST = "mineraldigger.com"
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

# Old rule: omit the page unless it had this many upcoming shows.
WARN_BELOW = 1

TYPES = ("rock", "gem", "mineral", "fossil", "bead")
NOTE = (
    "County, town and region pages in this file stay on the site when the upcoming "
    "show count is low. A refresh adds a page the first time it has an upcoming show, "
    "and it does not remove that page."
)
LISTING_PATH = re.compile(r"^/(county|town|region)/([a-z0-9-]+)/$")
UA = "Mozilla/5.0 (compatible; MineralDiggerRefresh/0.1; +https://mineraldigger.com)"


def slugify(value: str) -> str:
    text = str(value or "").lower().replace("&", " and ").replace("'", "").replace("’", "")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def iso_day(today: date | str) -> str:
    return today.isoformat() if isinstance(today, date) else str(today)


def empty_listings() -> dict:
    return {"note": NOTE, "counties": [], "towns": [], "regions": []}


def load_listings(path: Path = LISTINGS_PATH) -> dict:
    if not path.is_file():
        return empty_listings()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return empty_listings()
    loaded = empty_listings()
    loaded["note"] = str(data.get("note") or NOTE)
    for bucket in ("counties", "towns", "regions"):
        rows = data.get(bucket) or []
        if isinstance(rows, list):
            loaded[bucket] = [dict(row) for row in rows if isinstance(row, dict) and row.get("slug")]
    return loaded


def _county(slug: str, name: str, nation: str) -> dict:
    return {"slug": slug, "name": name, "nation": nation or "UK"}


def _town(slug: str, name: str, county: str, nation: str) -> dict:
    return {"slug": slug, "name": name, "county": county or "", "nation": nation or "UK"}


def _region(slug: str, name: str, nation: str) -> dict:
    return {"slug": slug, "name": name, "nation": nation or "UK"}


def _normalise(listings: dict) -> dict:
    result = {"note": str(listings.get("note") or NOTE), "counties": [], "towns": [], "regions": []}
    for row in listings.get("counties") or []:
        result["counties"].append(_county(row["slug"], row.get("name") or row["slug"], row.get("nation") or "UK"))
    for row in listings.get("towns") or []:
        result["towns"].append(
            _town(row["slug"], row.get("name") or row["slug"], row.get("county") or "", row.get("nation") or "UK")
        )
    for row in listings.get("regions") or []:
        result["regions"].append(_region(row["slug"], row.get("name") or row["slug"], row.get("nation") or "UK"))
    for bucket in ("counties", "towns", "regions"):
        result[bucket].sort(key=lambda item: item["slug"])
    return result


def save_listings(path: Path, listings: dict) -> bool:
    """Write the registry when it changed. Existing pages are never dropped here."""
    payload = _normalise(listings)
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return True


def _has(rows: list[dict], slug: str) -> bool:
    return any(row.get("slug") == slug for row in rows)


def _add(rows: list[dict], record: dict) -> None:
    slug = record.get("slug") or ""
    if slug and not _has(rows, slug):
        rows.append(record)


def _place_from_shows(shows: list[dict], kind: str, slug: str) -> dict | None:
    for show in shows:
        venue = show.get("venue") or {}
        nation = venue.get("nation") or "UK"
        if kind == "county" and slugify(venue.get("county") or "") == slug:
            return _county(slug, venue.get("county") or slug, nation)
        if kind == "town" and slugify(venue.get("town") or "") == slug:
            return _town(slug, venue.get("town") or slug, venue.get("county") or "", nation)
        if kind == "region" and slugify(venue.get("region") or "") == slug:
            return _region(slug, venue.get("region") or slug, nation)
    return None


def _fallback_name(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.split("-") if part)


def listing_urls_from_sitemap(text: str) -> list[str]:
    """County, town and region URLs on mineraldigger.com. Other URLs are ignored."""
    root = ET.fromstring(text)
    found: list[str] = []
    for node in root.findall("sm:url", SITEMAP_NS):
        loc = (node.findtext("sm:loc", default="", namespaces=SITEMAP_NS) or "").strip()
        parsed = urllib.parse.urlparse(loc)
        if parsed.netloc != HOST:
            continue
        path = parsed.path or "/"
        if not path.endswith("/"):
            path += "/"
        if LISTING_PATH.match(path):
            found.append(f"https://{HOST}{path}")
    return found


def fetch_live_sitemap(url: str = LIVE_SITEMAP) -> list[str]:
    """Best effort. A failure keeps the saved pages and does not stop the refresh."""
    request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/xml,text/xml"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            text = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"Warning: could not read the live sitemap ({exc}). Saved listing pages stay.", file=sys.stderr)
        return []
    try:
        return listing_urls_from_sitemap(text)
    except ET.ParseError as exc:
        print(f"Warning: could not read the live sitemap ({exc}). Saved listing pages stay.", file=sys.stderr)
        return []


def retain_listings(saved: dict, shows: list[dict], today: date | str, extra_urls: list[str] | None = None) -> dict:
    """Saved pages stay. A place with an upcoming show is added. Nothing is removed."""
    retained = _normalise(saved)
    day = iso_day(today)
    for show in shows:
        if (show.get("end") or "") < day:
            continue
        venue = show.get("venue") or {}
        nation = venue.get("nation") or "UK"
        county = venue.get("county") or ""
        town = venue.get("town") or ""
        region = venue.get("region") or ""
        if county:
            _add(retained["counties"], _county(slugify(county), county, nation))
        if town:
            _add(retained["towns"], _town(slugify(town), town, county, nation))
        if region:
            _add(retained["regions"], _region(slugify(region), region, nation))
    for url in extra_urls or []:
        parsed = urllib.parse.urlparse(url)
        path = parsed.path or "/"
        if not path.endswith("/"):
            path += "/"
        match = LISTING_PATH.match(path)
        if parsed.netloc not in ("", HOST) or not match:
            continue
        kind, slug = match.group(1), match.group(2)
        bucket = {"county": "counties", "town": "towns", "region": "regions"}[kind]
        if _has(retained[bucket], slug):
            continue
        record = _place_from_shows(shows, kind, slug)
        if record is None:
            name = _fallback_name(slug)
            if kind == "county":
                record = _county(slug, name, "UK")
            elif kind == "town":
                record = _town(slug, name, "", "UK")
            else:
                record = _region(slug, name, "UK")
        _add(retained[bucket], record)
    return _normalise(retained)


def count_upcoming(shows: list[dict], today: date | str, kind: str, slug: str) -> int:
    day = iso_day(today)
    total = 0
    for show in shows:
        if (show.get("end") or "") < day:
            continue
        venue = show.get("venue") or {}
        if kind == "county" and slugify(venue.get("county") or "") == slug:
            total += 1
        elif kind == "town" and slugify(venue.get("town") or "") == slug:
            total += 1
        elif kind == "region" and slugify(venue.get("region") or "") == slug:
            total += 1
        elif kind == "type" and slug in (show.get("types") or []):
            total += 1
    return total


def low_count_message(path: str, count: int) -> str:
    noun = "show" if count == 1 else "shows"
    return f"{path} has {count} upcoming {noun}, below {WARN_BELOW}. The page stays live."


def low_count_warnings(listings: dict, shows: list[dict], today: date | str) -> list[str]:
    rows: list[tuple[str, str, str]] = []
    for row in listings.get("counties") or []:
        rows.append(("county", row["slug"], f"/county/{row['slug']}/"))
    for row in listings.get("towns") or []:
        rows.append(("town", row["slug"], f"/town/{row['slug']}/"))
    for row in listings.get("regions") or []:
        rows.append(("region", row["slug"], f"/region/{row['slug']}/"))
    for slug in TYPES:
        rows.append(("type", slug, f"/{slug}/"))
    messages = []
    for kind, slug, path in rows:
        count = count_upcoming(shows, today, kind, slug)
        if count < WARN_BELOW:
            messages.append(low_count_message(path, count))
    messages.sort()
    return messages


def warn_low_counts(listings: dict, shows: list[dict], today: date | str) -> list[str]:
    """Log a warning, and a GitHub Actions ::warning::, for each low page."""
    messages = low_count_warnings(listings, shows, today)
    for message in messages:
        print(f"Warning: {message}", file=sys.stderr)
        print(f"::warning::{message}", file=sys.stderr)
    return messages
