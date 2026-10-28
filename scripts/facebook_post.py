#!/usr/bin/env python3
"""Draft or publish the MineralDigger Facebook Page post for this week.

Dry run is the default. The script prints the post and does not call
Facebook. --publish sends it to the Page in growth/facebook_page.json
after Alan has OK'd the text.

The page token is MINERALDIGGER_FB_PAGE_TOKEN, or the matching page in
~/.secrets/fb_pages.json. That file is not committed.

Posts are logged in growth/facebook_posts.json under the ISO week
(2026-W44). A week that is already logged is skipped unless --force
is set.

Examples:
  python3 scripts/facebook_post.py
  python3 scripts/facebook_post.py --today 2026-10-28
  python3 scripts/facebook_post.py --today 2026-10-28 --publish
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
    TYPE_ORDER,
    SocialError,
    build_post,
    display_path,
    load_json,
    load_log,
    load_shows,
    load_site,
    now_stamp,
    print_draft,
    redact,
    save_log,
    token_from_pages,
    week_recorded,
)

PAGE_PATH = ROOT / "growth" / "facebook_page.json"
LOG_PATH = ROOT / "growth" / "facebook_posts.json"
SECRETS_PATH = Path.home() / ".secrets" / "fb_pages.json"
ENV_TOKEN = "MINERALDIGGER_FB_PAGE_TOKEN"
GRAPH = "https://graph.facebook.com/v23.0"


def page_id_from(path: Path) -> str:
    page_id = str(load_json(path).get("page_id") or "").strip()
    if not page_id.isdigit():
        raise SocialError(f"{display_path(path)} needs a numeric page_id.")
    return page_id


def resolve_token(page_id: str, secrets_path: Path) -> str | None:
    env = os.environ.get(ENV_TOKEN, "").strip()
    if env:
        return env
    if not secrets_path.is_file():
        return None
    return token_from_pages(load_json(secrets_path), page_id)


def publish_page(page_id: str, token: str, message: str, link: str, api_base: str = GRAPH) -> dict:
    url = f"{api_base.rstrip('/')}/{page_id}/feed"
    payload = {
        "message": message,
        "link": link,
        "published": True,
        "access_token": token,
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "MineralDiggerSocial/1 (+https://mineraldigger.com)",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = ""
        if exc.fp is not None:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
        message_text = detail
        try:
            parsed = json.loads(detail) if detail else {}
            if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict):
                message_text = str(parsed["error"].get("message") or detail)
        except json.JSONDecodeError:
            pass
        raise SocialError(redact(f"Facebook post failed with HTTP {exc.code}. {message_text}", [token])) from exc
    except urllib.error.URLError as exc:
        raise SocialError(redact(f"Facebook post failed. {exc.reason}", [token])) from exc
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise SocialError("Facebook returned a response that was not JSON.") from exc
    post_id = parsed.get("id") if isinstance(parsed, dict) else None
    if not isinstance(post_id, str) or not post_id:
        raise SocialError("Facebook did not return a post id.")
    permalink = None
    if "_" in post_id:
        page, story = post_id.split("_", 1)
        permalink = f"https://www.facebook.com/{page}/posts/{story}"
    return {"id": post_id, "url": permalink}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Draft or publish the weekly MineralDigger Facebook post.")
    parser.add_argument("--publish", action="store_true", help="Post to the Facebook Page. The default is a dry run.")
    parser.add_argument("--force", action="store_true", help="Post even when this ISO week is already in the log.")
    parser.add_argument("--today", help="YYYY-MM-DD for the week and the show list. Defaults to today.")
    parser.add_argument("--angle", choices=ANGLES, help="next-show or type-hub. Defaults to the week's rotation.")
    parser.add_argument("--type", dest="kind", choices=TYPE_ORDER, help="Type hub to lead with on a type-hub week.")
    parser.add_argument("--shows", type=Path, default=ROOT / "data" / "shows.json", help=argparse.SUPPRESS)
    parser.add_argument("--site", type=Path, default=ROOT / "data" / "site.json", help=argparse.SUPPRESS)
    parser.add_argument("--log", type=Path, default=LOG_PATH, help=argparse.SUPPRESS)
    parser.add_argument("--page-file", type=Path, default=PAGE_PATH, help=argparse.SUPPRESS)
    parser.add_argument("--secrets", type=Path, default=SECRETS_PATH, help=argparse.SUPPRESS)
    parser.add_argument("--api", default=GRAPH, help=argparse.SUPPRESS)
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
        page_id = page_id_from(args.page_file) if args.publish else None
    except SocialError as exc:
        print(exc, file=sys.stderr)
        return 1

    if post is None:
        print("No upcoming UK shows. Nothing drafted.")
        return 0

    recorded = week_recorded(log, post["week"])
    if not args.publish:
        print_draft("Facebook", post["facebook"], post, args.log, recorded)
        return 0

    if recorded and not args.force:
        print(
            f"Week {post['week']} is already in {display_path(args.log)}. "
            "Nothing posted. Pass --force to post this week again.",
            file=sys.stderr,
        )
        return 1

    try:
        token = resolve_token(page_id or "", args.secrets)
    except SocialError as exc:
        print(exc, file=sys.stderr)
        return 1
    if not token:
        print(
            "No MineralDigger Facebook page token. "
            f"Set {ENV_TOKEN} or add the page to ~/.secrets/fb_pages.json.",
            file=sys.stderr,
        )
        return 1

    try:
        result = publish_page(page_id or "", token, post["facebook"], post["link"], args.api)
    except SocialError as exc:
        print(redact(str(exc), [token]), file=sys.stderr)
        return 1

    log[post["week"]] = {
        "week": post["week"],
        "angle": post["angle"],
        "kind": post["kind"],
        "link": post["link"],
        "text": post["facebook"],
        "show_id": post["show_id"],
        "published_at": now_stamp(),
        "post_id": result["id"],
        "url": result["url"],
    }
    try:
        save_log(args.log, log)
    except OSError as exc:
        print(f"Facebook accepted the post ({result['id']}) but the log was not written. {exc}", file=sys.stderr)
        return 1
    print(f"Posted week {post['week']} to the MineralDigger Facebook Page.")
    if result.get("url"):
        print(result["url"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
