#!/usr/bin/env python3
"""Tell IndexNow about MineralDigger URLs that are new or have a new lastmod.

Reads dist/sitemap.xml and compares each lastmod with data/indexnow_state.json.
POSTs only the new or changed URLs to https://api.indexnow.org/indexnow.
The host is mineraldigger.com. mineraldigger.co.uk is never submitted.

The first run, with an empty state file, sends every sitemap URL. URLs go in
batches of at most 10000. The state file is rewritten only after HTTP 200 or
202. Any other response is logged. The process still exits 0, so a deploy is
not failed by IndexNow.

  python3 scripts/indexnow.py
  python3 scripts/indexnow.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOST = "mineraldigger.com"
ENDPOINT = "https://api.indexnow.org/indexnow"
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
BATCH = 10000


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


def changed_urls(sitemap: dict[str, str], previous: dict[str, str]) -> list[str]:
    """URLs that are missing from the state file, or whose lastmod differs."""
    return [url for url, lastmod in sitemap.items() if previous.get(url) != lastmod]


def batches(urls: list[str], size: int = BATCH) -> list[list[str]]:
    step = size if size > 0 else BATCH
    return [urls[index:index + step] for index in range(0, len(urls), step)]


def state_after_success(sitemap: dict[str, str], previous: dict[str, str], accepted: list[str]) -> dict[str, str]:
    """Keep lastmods for URLs still on the sitemap. Record only accepted ones."""
    urls = {url: lastmod for url, lastmod in previous.items() if url in sitemap}
    for url in accepted:
        if url in sitemap:
            urls[url] = sitemap[url]
    return urls


def load_state(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    urls = data.get("urls") if isinstance(data, dict) else None
    if not isinstance(urls, dict):
        return {}
    return {str(url): str(lastmod) for url, lastmod in urls.items()}


def save_state(path: Path, urls: dict[str, str]) -> None:
    payload = {"host": HOST, "urls": dict(sorted(urls.items()))}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


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
    previous = load_state(state_path)
    changed = changed_urls(sitemap, previous)
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
    save_state(state_path, state_after_success(sitemap, previous, accepted))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Submit new or changed MineralDigger URLs to IndexNow.")
    parser.add_argument("--dry-run", action="store_true", help="Print the URLs and do not POST or update the state file.")
    parser.add_argument("--sitemap", type=Path, default=ROOT / "dist" / "sitemap.xml")
    parser.add_argument("--state", type=Path, default=ROOT / "data" / "indexnow_state.json")
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    args = parser.parse_args(argv)
    try:
        run(args.sitemap, args.state, args.dist, args.dry_run)
    except Exception as exc:
        print(f"IndexNow skipped: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
