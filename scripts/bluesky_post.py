#!/usr/bin/env python3
"""Draft or publish the MineralDigger Bluesky post for this week.

Dry run is the default. The script prints the post and does not call
Bluesky. --publish sends it as mineraldigger.com after Alan has OK'd
the text.

The app password is MINERALDIGGER_BLUESKY_APP_PASSWORD, or the
mineraldigger.com entry in ~/.secrets/bluesky.json. That file is not
committed.

Posts are logged in growth/bluesky_posts.json under the ISO week
(2026-W44). A week that is already logged is skipped unless --force
is set. The text matches the Facebook draft for the same week and angle.

Examples:
  python3 scripts/bluesky_post.py
  python3 scripts/bluesky_post.py --today 2026-10-28
  python3 scripts/bluesky_post.py --today 2026-10-28 --publish
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from social_copy import (  # noqa: E402
    ANGLES,
    BLUESKY_HANDLE,
    TYPE_ORDER,
    SocialError,
    build_post,
    display_path,
    link_facet,
    load_json,
    load_log,
    load_shows,
    load_site,
    normal_handle,
    now_stamp,
    password_from_bluesky,
    print_draft,
    redact,
    save_log,
    week_recorded,
)

LOG_PATH = ROOT / "growth" / "bluesky_posts.json"
SECRETS_PATH = Path.home() / ".secrets" / "bluesky.json"
ENV_PASSWORD = "MINERALDIGGER_BLUESKY_APP_PASSWORD"
PDS = "https://bsky.social"


def resolve_password(secrets_path: Path) -> str | None:
    env = os.environ.get(ENV_PASSWORD, "").strip()
    if env:
        return env
    if not secrets_path.is_file():
        return None
    return password_from_bluesky(load_json(secrets_path), BLUESKY_HANDLE)


def _xrpc(pds: str, method: str, payload: dict, token: str | None, secrets: list[str]) -> dict:
    request = urllib.request.Request(
        f"{pds.rstrip('/')}/xrpc/{method}",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "MineralDiggerSocial/1 (+https://mineraldigger.com)",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = ""
        if exc.fp is not None:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise SocialError(redact(f"Bluesky {method} failed with HTTP {exc.code}. {detail}", secrets)) from exc
    except urllib.error.URLError as exc:
        raise SocialError(redact(f"Bluesky {method} failed. {exc.reason}", secrets)) from exc
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise SocialError(f"Bluesky {method} returned a response that was not JSON.") from exc
    if not isinstance(parsed, dict):
        raise SocialError(f"Bluesky {method} returned an unexpected response.")
    return parsed


def publish_post(password: str, text: str, link: str, pds: str = PDS) -> dict:
    secrets = [password]
    session = _xrpc(
        pds,
        "com.atproto.server.createSession",
        {"identifier": BLUESKY_HANDLE, "password": password},
        token=None,
        secrets=secrets,
    )
    signed_in = str(session.get("handle") or "")
    if normal_handle(signed_in) != normal_handle(BLUESKY_HANDLE):
        shown = signed_in or "an unknown handle"
        raise SocialError(f"Bluesky signed in as {shown}. Expected {BLUESKY_HANDLE}. Nothing posted.")
    jwt = session.get("accessJwt")
    did = session.get("did")
    if not isinstance(jwt, str) or not jwt or not isinstance(did, str) or not did:
        raise SocialError("Bluesky session did not return a token.")
    secrets.append(jwt)
    record = {
        "$type": "app.bsky.feed.post",
        "text": text,
        "createdAt": now_stamp(),
        "langs": ["en-GB"],
    }
    facet = link_facet(text, link)
    if facet:
        record["facets"] = [facet]
    created = _xrpc(
        pds,
        "com.atproto.repo.createRecord",
        {"repo": did, "collection": "app.bsky.feed.post", "record": record},
        token=jwt,
        secrets=secrets,
    )
    uri = created.get("uri")
    if not isinstance(uri, str) or not uri:
        raise SocialError("Bluesky did not return a post uri.")
    rkey = uri.rstrip("/").split("/")[-1]
    return {
        "uri": uri,
        "cid": created.get("cid"),
        "url": f"https://bsky.app/profile/{BLUESKY_HANDLE}/post/{rkey}",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Draft or publish the weekly MineralDigger Bluesky post.")
    parser.add_argument("--publish", action="store_true", help="Post to Bluesky. The default is a dry run.")
    parser.add_argument("--force", action="store_true", help="Post even when this ISO week is already in the log.")
    parser.add_argument("--today", help="YYYY-MM-DD for the week and the show list. Defaults to today.")
    parser.add_argument("--angle", choices=ANGLES, help="next-show or type-hub. Defaults to the week's rotation.")
    parser.add_argument("--type", dest="kind", choices=TYPE_ORDER, help="Type hub to lead with on a type-hub week.")
    parser.add_argument("--shows", type=Path, default=ROOT / "data" / "shows.json", help=argparse.SUPPRESS)
    parser.add_argument("--site", type=Path, default=ROOT / "data" / "site.json", help=argparse.SUPPRESS)
    parser.add_argument("--log", type=Path, default=LOG_PATH, help=argparse.SUPPRESS)
    parser.add_argument("--secrets", type=Path, default=SECRETS_PATH, help=argparse.SUPPRESS)
    parser.add_argument("--pds", default=PDS, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    today = date.today()
    if args.today:
        try:
            today = date.fromisoformat(args.today)
        except ValueError:
            print("Pass --today as YYYY-MM-DD.", file=sys.stderr)
            return 1

    try:
        shows = load_shows(args.shows)
        site = load_site(args.site)
        post = build_post(shows, today, site, angle=args.angle, kind=args.kind)
        log = load_log(args.log)
    except SocialError as exc:
        print(exc, file=sys.stderr)
        return 1

    if post is None:
        print("No upcoming UK shows. Nothing drafted.")
        return 0

    recorded = week_recorded(log, post["week"])
    if not args.publish:
        print_draft("Bluesky", post["bluesky"], post, args.log, recorded)
        return 0

    if recorded and not args.force:
        print(
            f"Week {post['week']} is already in {display_path(args.log)}. "
            "Nothing posted. Pass --force to post this week again.",
            file=sys.stderr,
        )
        return 1

    try:
        password = resolve_password(args.secrets)
    except SocialError as exc:
        print(exc, file=sys.stderr)
        return 1
    if not password:
        print(
            f"No Bluesky app password for {BLUESKY_HANDLE}. "
            f"Set {ENV_PASSWORD} or add that handle to ~/.secrets/bluesky.json.",
            file=sys.stderr,
        )
        return 1

    try:
        result = publish_post(password, post["bluesky"], post["link"], args.pds)
    except SocialError as exc:
        print(redact(str(exc), [password]), file=sys.stderr)
        return 1

    log[post["week"]] = {
        "week": post["week"],
        "angle": post["angle"],
        "kind": post["kind"],
        "link": post["link"],
        "text": post["bluesky"],
        "show_id": post["show_id"],
        "published_at": now_stamp(),
        "uri": result["uri"],
        "cid": result.get("cid"),
        "url": result["url"],
    }
    try:
        save_log(args.log, log)
    except OSError as exc:
        print(f"Bluesky accepted the post ({result['uri']}) but the log was not written. {exc}", file=sys.stderr)
        return 1
    print(f"Posted week {post['week']} to {BLUESKY_HANDLE} on Bluesky.")
    print(result["url"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
