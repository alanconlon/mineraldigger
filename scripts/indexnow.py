#!/usr/bin/env python3
"""Tell IndexNow about MineralDigger URLs whose page content changed.

Reads the built HTML for each sitemap URL and compares a content hash with
data/indexnow_state.json. The hash ignores the "Data last refreshed" date,
the show "Retrieved" date, the offer validFrom stamp, and asset ?v= tokens.
POSTs only new or changed URLs to https://api.indexnow.org/indexnow.
The host is mineraldigger.com. mineraldigger.co.uk is never submitted.
Every mineraldigger.com URL in the sitemap is eligible. A low show count does not remove one.

--stamp-sitemap rewrites each sitemap lastmod. An unchanged page keeps the
stored date. A new or changed page uses the build date. The state file is
rewritten only after HTTP 200 or 202. Any other response is logged. The
submit command still exits 0, so a deploy is not failed by IndexNow.

  python3 scripts/indexnow.py
  python3 scripts/indexnow.py --dry-run
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
HOST = "mineraldigger.com"
ENDPOINT = "https://api.indexnow.org/indexnow"
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
BATCH = 10000
REFRESHED = re.compile(r"Data last refreshed \d{1,2} [A-Z][a-z]+ \d{4}")
RETRIEVED = re.compile(r"Retrieved \d{1,2} [A-Z][a-z]+ \d{4}")
VALID_FROM = re.compile(r'"validFrom":"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}"')
ASSET_VERSION = re.compile(r"\?v=[0-9a-f]{12}")


def find_key(dist: Path) -> str | None:
    """The public IndexNow key is the name of one 32-hex file in the site root."""
    found = []
    if not dist.is_dir():
        return None
    for path in sorted(dist.glob("*.txt")):
        stem = path.stem
        if len(stem) != 32 or any(ch not in "0123456789abcdef" for ch in stem):
            continue
        if path.read_text(encoding="utf-8").strip() == stem:
            found.append(stem)
    if len(found) != 1:
        return None
    return found[0]


def parse_sitemap(path: Path) -> dict[str, str]:
    """mineraldigger.com URLs in sitemap order, each mapped to its lastmod."""
    root = ET.parse(path).getroot()
    urls: dict[str, str] = {}
    for node in root.findall("sm:url", SITEMAP_NS):
        loc = (node.findtext("sm:loc", default="", namespaces=SITEMAP_NS) or "").strip()
        if not loc.startswith(f"https://{HOST}/") and loc != f"https://{HOST}":
            continue
        lastmod = (node.findtext("sm:lastmod", default="", namespaces=SITEMAP_NS) or "").strip()
        urls[loc] = lastmod
    return urls


def stable_html(html: str) -> str:
    """Drop refresh stamps so a daily rebuild does not look like a new page."""
    html = REFRESHED.sub("Data last refreshed", html)
    html = RETRIEVED.sub("Retrieved", html)
    html = VALID_FROM.sub('"validFrom":""', html)
    return ASSET_VERSION.sub("", html)


def content_hash(html: str) -> str:
    return hashlib.sha256(stable_html(html).encode("utf-8")).hexdigest()


def page_file(dist: Path, url: str) -> Path | None:
    path = urllib.parse.urlparse(url).path.strip("/")
    candidate = dist / "index.html" if not path else dist / path / "index.html"
    if candidate.is_file():
        return candidate
    direct = dist / path if path else None
    if direct is not None and direct.is_file():
        return direct
    return None


def page_hashes(dist: Path, urls: list[str]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for url in urls:
        file = page_file(dist, url)
        hashes[url] = content_hash(file.read_text(encoding="utf-8")) if file else ""
    return hashes


def changed_urls(pages: dict[str, str], previous: dict[str, dict[str, str]]) -> list[str]:
    """URLs that are new, or whose content hash differs from the state file."""
    changed = []
    for url, digest in pages.items():
        prior = previous.get(url) or {}
        if prior.get("hash") != digest:
            changed.append(url)
    return changed


def lastmod_for(url: str, digest: str, previous: dict[str, dict[str, str]], today: str) -> str:
    """Keep the stored date while the content hash matches. Otherwise use the build date."""
    prior = previous.get(url) or {}
    if prior.get("hash") and prior.get("hash") == digest and prior.get("lastmod"):
        return prior["lastmod"]
    return today


def batches(urls: list[str], size: int = BATCH) -> list[list[str]]:
    step = size if size > 0 else BATCH
    return [urls[index:index + step] for index in range(0, len(urls), step)]


def state_after_success(
    pages: dict[str, str],
    previous: dict[str, dict[str, str]],
    accepted: list[str],
    lastmods: dict[str, str],
) -> dict[str, dict[str, str]]:
    """Record hashes only for accepted URLs that still have a page. Drop the rest."""
    urls: dict[str, dict[str, str]] = {}
    accepted_set = set(accepted)
    for url, digest in pages.items():
        prior = previous.get(url) or {}
        if url in accepted_set and digest:
            urls[url] = {"hash": digest, "lastmod": lastmods.get(url) or prior.get("lastmod") or ""}
        elif prior.get("hash"):
            urls[url] = {"hash": prior["hash"], "lastmod": prior.get("lastmod") or ""}
    return urls


def load_state(path: Path) -> dict[str, dict[str, str]]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    urls = data.get("urls") if isinstance(data, dict) else None
    if not isinstance(urls, dict):
        return {}
    loaded: dict[str, dict[str, str]] = {}
    for url, value in urls.items():
        if isinstance(value, str):
            loaded[str(url)] = {"hash": "", "lastmod": value}
        elif isinstance(value, dict):
            loaded[str(url)] = {"hash": str(value.get("hash") or ""), "lastmod": str(value.get("lastmod") or "")}
    return loaded


def save_state(path: Path, urls: dict[str, dict[str, str]]) -> None:
    ordered = {}
    for url in sorted(urls):
        entry = urls[url]
        ordered[url] = {"hash": entry.get("hash") or "", "lastmod": entry.get("lastmod") or ""}
    payload = {"host": HOST, "urls": ordered}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def rewrite_lastmods(path: Path, lastmods: dict[str, str]) -> None:
    root = ET.parse(path).getroot()
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for node in root.findall("sm:url", SITEMAP_NS):
        loc = (node.findtext("sm:loc", default="", namespaces=SITEMAP_NS) or "").strip()
        lastmod = lastmods.get(loc) or (node.findtext("sm:lastmod", default="", namespaces=SITEMAP_NS) or "").strip()
        lines.append(f"<url><loc>{escape(loc)}</loc><lastmod>{escape(lastmod)}</lastmod></url>")
    lines.append("</urlset>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def stamp_sitemap(sitemap_path: Path, state_path: Path, dist: Path, today: str) -> None:
    sitemap = parse_sitemap(sitemap_path)
    pages = page_hashes(dist, list(sitemap))
    previous = load_state(state_path)
    lastmods = {url: lastmod_for(url, pages.get(url, ""), previous, today) for url in sitemap}
    rewrite_lastmods(sitemap_path, lastmods)


def post_batch(payload: dict) -> int | None:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except urllib.error.URLError as exc:
        print(f"IndexNow request failed: {exc.reason}", file=sys.stderr)
        return None


def run(sitemap_path: Path, state_path: Path, dist: Path, dry_run: bool) -> None:
    key = find_key(dist)
    if not key:
        print("IndexNow skipped: no key file in the site root.", file=sys.stderr)
        return
    if not sitemap_path.is_file():
        print(f"IndexNow skipped: sitemap not found at {sitemap_path}.", file=sys.stderr)
        return
    sitemap = parse_sitemap(sitemap_path)
    pages = page_hashes(dist, list(sitemap))
    previous = load_state(state_path)
    changed = changed_urls(pages, previous)
    if not changed:
        print("IndexNow: no new or changed URLs.")
        return
    payload_base = {
        "host": HOST,
        "key": key,
        "keyLocation": f"https://{HOST}/{key}.txt",
    }
    if dry_run:
        print(f"IndexNow dry run: {len(changed)} URLs on {HOST}")
        for url in changed:
            print(url)
        return
    accepted: list[str] = []
    for batch in batches(changed):
        status = post_batch({**payload_base, "urlList": batch})
        print(f"IndexNow {status if status is not None else 'error'} for {len(batch)} URLs")
        if status in (200, 202):
            accepted.extend(batch)
    if not accepted:
        return
    save_state(state_path, state_after_success(pages, previous, accepted, sitemap))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Submit new or changed MineralDigger URLs to IndexNow.")
    parser.add_argument("--dry-run", action="store_true", help="Print the URLs and do not POST or update the state file.")
    parser.add_argument("--stamp-sitemap", action="store_true", help="Set each sitemap lastmod from the content hash. Do not POST.")
    parser.add_argument("--date", default="", help="Build date for a page whose content hash changed. Defaults to today.")
    parser.add_argument("--sitemap", type=Path, default=ROOT / "dist" / "sitemap.xml")
    parser.add_argument("--state", type=Path, default=ROOT / "data" / "indexnow_state.json")
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    args = parser.parse_args(argv)
    if args.stamp_sitemap:
        try:
            stamp_sitemap(args.sitemap, args.state, args.dist, args.date or date.today().isoformat())
        except Exception as exc:
            print(f"IndexNow sitemap stamp failed: {exc}", file=sys.stderr)
            return 1
        return 0
    try:
        run(args.sitemap, args.state, args.dist, args.dry_run)
    except Exception as exc:
        print(f"IndexNow skipped: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
