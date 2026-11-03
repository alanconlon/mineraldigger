#!/usr/bin/env python3
"""Draft or publish the MineralDigger Facebook Page post for this week.

Dry run is the default. The script prints the post and does not call
Facebook. --publish sends it to the Page in growth/facebook_page.json
after Alan has OK'd the text. The post text uses mineraldigger.com/... .
The full https URL is only the link field. Publish refuses a text that
contains !, an en dash, an em dash, or https://. It also refuses
FairDigger or AuctionDigger wording, and a link that is not on
mineraldigger.com or mineraldigger.co.uk. After Graph accepts the post,
the script reads it back and exits with status 1 when the live text
does not match, or when a returned link attachment is off this brand.

Approved queue copy is an explicit source. Pass --queue-item and --queue
every time. An explicit text file is --text-file with --link. There is
no default path, and a leftover temp file is never read. The queue
item site must be mineral.

The page token is looked up in this order. Nothing here is committed,
and a missing token names each place without printing a value.

1. MINERALDIGGER_FB_PAGE_TOKEN
2. The matching page in ~/.secrets/fb_pages.json
3. A user token named fb_user_token (MINERALDIGGER_FB_USER_TOKEN, then
   FB_USER_TOKEN, then the fb_user_token key in that file, then
   ~/.secrets/fb_user_token). Graph exchanges it for this page's token.

Before posting, unless --force is set, recent posts are read from
/{page-id}/posts. /{page-id}/feed is not read: that needs
pages_read_engagement. The same link already on the Page stops the
post. If /posts cannot be read, the log is the only duplicate check.

Posts are logged in growth/facebook_posts.json under the ISO week
(2026-W44). A week that is already logged is skipped unless --force
is set.

Examples:
  python3 scripts/facebook_post.py --queue-item mineral-november-glance-2026-11-03 --queue /path/to/queue.json
  python3 scripts/facebook_post.py --queue-item mineral-november-glance-2026-11-03 --queue /path/to/queue.json --publish
  python3 scripts/facebook_post.py --text-file /path/to/post.txt --link mineraldigger.com --publish
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
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from social_copy import (  # noqa: E402
    ANGLES,
    TYPE_ORDER,
    USER_TOKEN_KEYS,
    SocialError,
    absolute_link,
    add_explicit_arguments,
    bare_link,
    build_post,
    display_path,
    display_secret,
    explicit_log_key,
    explicit_mode,
    facebook_readback_error,
    load_json,
    load_log,
    load_queue_item,
    load_shows,
    load_site,
    now_stamp,
    post_from_queue,
    post_from_text_file,
    print_draft,
    publish_refusal,
    read_secret_file,
    redact,
    save_log,
    token_from_pages,
    user_token_from_pages,
    week_recorded,
)

PAGE_PATH = ROOT / "growth" / "facebook_page.json"
LOG_PATH = ROOT / "growth" / "facebook_posts.json"
SECRETS_PATH = Path.home() / ".secrets" / "fb_pages.json"
ENV_TOKEN = "MINERALDIGGER_FB_PAGE_TOKEN"
USER_TOKEN_ENVS = ("MINERALDIGGER_FB_USER_TOKEN", "FB_USER_TOKEN")
USER_TOKEN_FILE = "fb_user_token"
GRAPH = "https://graph.facebook.com/v23.0"
USER_TOKEN_FILE_KEYS = ("access_token", "token", "user_token", "fb_user_token")


def page_id_from(path: Path) -> str:
    page_id = str(load_json(path).get("page_id") or "").strip()
    if not page_id.isdigit():
        raise SocialError(f"{display_path(path)} needs a numeric page_id.")
    return page_id


def missing_page_token_message(page_id: str, secrets_path: Path) -> str:
    user_file = secrets_path.parent / USER_TOKEN_FILE
    env_names = " or ".join(USER_TOKEN_ENVS)
    return (
        f"No MineralDigger Facebook page token for page {page_id}. "
        f"Looked for the environment variable {ENV_TOKEN}, "
        f"a token for that page in {display_secret(secrets_path)}, "
        f"and a user token named {USER_TOKEN_KEYS[0]} "
        f"(environment variables {env_names}, "
        f"the {USER_TOKEN_KEYS[0]} key in {display_secret(secrets_path)}, "
        f"or the file {display_secret(user_file)}) "
        "to derive a page token from Graph. "
        "Nothing posted. Values are not printed."
    )


def _graph_target(url: str) -> str:
    """Path only, so a token in the query string is never shown."""
    return urllib.parse.urlsplit(url).path or "/"


def graph_get(url: str, token: str) -> dict:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "MineralDiggerSocial/1 (+https://mineraldigger.com)",
        },
    )
    target = _graph_target(url)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = ""
        if exc.fp is not None:
            detail = exc.read().decode("utf-8", errors="replace")
        message_text = detail
        try:
            parsed = json.loads(detail) if detail else {}
            if isinstance(parsed, dict) and isinstance(parsed.get("error"), dict):
                message_text = str(parsed["error"].get("message") or detail)
        except json.JSONDecodeError:
            message_text = detail
        message_text = redact(message_text, [token])
        if len(message_text) > 300:
            message_text = message_text[:300]
        raise SocialError(f"Facebook returned HTTP {exc.code} for {target}. {message_text}") from exc
    except urllib.error.URLError as exc:
        raise SocialError(redact(f"Facebook request failed for {target}. {exc.reason}", [token])) from exc
    try:
        parsed = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise SocialError(f"Facebook returned a response that was not JSON for {target}.") from exc
    if not isinstance(parsed, dict):
        raise SocialError(f"Facebook returned an unexpected response for {target}.")
    error = parsed.get("error")
    if isinstance(error, dict):
        message_text = redact(str(error.get("message") or "Facebook returned an error."), [token])
        raise SocialError(f"Facebook rejected {target}. {message_text}")
    return parsed


def _user_token(secrets_path: Path, pages: dict | None) -> tuple[str | None, str]:
    for name in USER_TOKEN_ENVS:
        env = os.environ.get(name, "").strip()
        if env:
            return env, f"environment variable {name}"
    if isinstance(pages, dict):
        found = user_token_from_pages(pages)
        if found:
            return found, f"the {USER_TOKEN_KEYS[0]} key in {display_secret(secrets_path)}"
    file_path = secrets_path.parent / USER_TOKEN_FILE
    found = read_secret_file(file_path, USER_TOKEN_FILE_KEYS)
    if found:
        return found, f"the file {display_secret(file_path)}"
    return None, ""


def derive_page_token(page_id: str, user_token: str, api_base: str, source: str) -> str:
    """Exchange a user token for this Page's token. Raises when Graph does not return one."""
    base = api_base.rstrip("/")
    errors: list[str] = []
    direct_url = f"{base}/{page_id}?fields=access_token"
    payload: dict = {}
    try:
        payload = graph_get(direct_url, user_token)
    except SocialError as exc:
        errors.append(str(exc))
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if isinstance(token, str) and token.strip():
        return token.strip()

    accounts_url = f"{base}/me/accounts?fields=id,access_token&limit=100"
    payload = {}
    try:
        payload = graph_get(accounts_url, user_token)
    except SocialError as exc:
        errors.append(str(exc))
    rows = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict) or str(row.get("id") or "").strip() != page_id:
                continue
            found = row.get("access_token")
            if isinstance(found, str) and found.strip():
                return found.strip()
    detail = " ".join(errors) if errors else "Facebook returned no access_token for this page."
    message = (
        f"A user token named {USER_TOKEN_KEYS[0]} ({source}) did not return a page token for {page_id}. "
        f"Asked Graph for /{page_id} and /me/accounts. {detail} "
        "Nothing posted. Values are not printed."
    )
    raise SocialError(redact(message, [user_token]))


def resolve_token(page_id: str, secrets_path: Path, api_base: str = GRAPH) -> str | None:
    """Page token from the environment, the pages file, or a derived user token.

    Returns None when every source is missing. Raises SocialError when a user
    token is present but Graph does not return a page token for page_id.
    """
    env = os.environ.get(ENV_TOKEN, "").strip()
    if env:
        return env
    pages = None
    if secrets_path.is_file():
        pages = load_json(secrets_path)
        found = token_from_pages(pages, page_id)
        if found:
            return found
    user_token, source = _user_token(secrets_path, pages)
    if not user_token:
        return None
    return derive_page_token(page_id, user_token, api_base, source)


def fetch_page_posts(page_id: str, token: str, api_base: str = GRAPH) -> list[dict]:
    """Recent posts published by the Page.

    /{page-id}/posts is used because /{page-id}/feed needs pages_read_engagement.
    """
    url = (
        f"{api_base.rstrip('/')}/{page_id}/posts"
        "?fields=id,message,permalink_url,created_time&limit=25"
    )
    payload = graph_get(url, token)
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise SocialError(f"Facebook /{page_id}/posts did not return a list of posts.")
    return [row for row in rows if isinstance(row, dict)]


def _text_has_link(value: object, needles: tuple[str, ...]) -> bool:
    if isinstance(value, str):
        return any(needle and needle in value for needle in needles)
    if isinstance(value, dict):
        return any(_text_has_link(item, needles) for item in value.values())
    if isinstance(value, list):
        return any(_text_has_link(item, needles) for item in value)
    return False


def matching_page_post(posts: list[dict], link: str) -> dict | None:
    bare = bare_link(link)
    needles = tuple(item for item in (link.strip(), bare) if item)
    for post in posts:
        if _text_has_link(post, needles):
            return post
    return None


def _public_post_id(value: object) -> str:
    text = str(value or "").strip()
    parts = text.split("_")
    if text and all(part.isdigit() for part in parts):
        return text
    return ""


def read_back_page_post(post_id: str, token: str, message: str, link: str, api_base: str) -> None:
    """Fetch the Page post from Graph and raise when it is not the text we sent."""
    fields = "message,permalink_url,attachments{unshimmed_url,url,title}"
    url = f"{api_base.rstrip('/')}/{post_id}?fields={fields}"
    try:
        live = graph_get(url, token)
    except SocialError as exc:
        raise SocialError(
            f"Facebook accepted the post ({post_id}) but the read-back failed, so it is not confirmed. {exc}"
        ) from exc
    mismatch = facebook_readback_error(live, message, link)
    if mismatch:
        raise SocialError(f"{mismatch} Live post id: {post_id}. The log was not updated.")


def publish_page(page_id: str, token: str, message: str, link: str, api_base: str = GRAPH) -> dict:
    link = absolute_link(link)
    blocked = publish_refusal(message, link)
    if blocked:
        raise SocialError(blocked)
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
    read_back_page_post(post_id, token, message, link, api_base)
    permalink = None
    if "_" in post_id:
        page, story = post_id.split("_", 1)
        permalink = f"https://www.facebook.com/{page}/posts/{story}"
    return {"id": post_id, "url": permalink}


def _print_explicit_draft(chosen: dict, text: str, link: str, text_file: Path | None) -> None:
    print("Dry run. Nothing posted.")
    if chosen["source"] == "queue":
        print(f"Queue item: {chosen['queue_item']}")
    else:
        print(f"Text file: {display_path(text_file or Path(''))}")
    print(f"Link: {link}")
    print("Facebook:")
    print(text)


def run_explicit(args: argparse.Namespace) -> int | None:
    """Publish from --queue-item or --text-file. None means use the show catalogue.

    The text comes only from the path on the command. There is no default
    and no leftover temp file.
    """
    try:
        mode = explicit_mode(args.queue, args.queue_item, args.text_file, args.link)
    except SocialError as exc:
        print(exc, file=sys.stderr)
        return 1
    if not mode:
        return None
    try:
        if mode == "queue":
            item = load_queue_item(args.queue, args.queue_item or "")
            chosen = post_from_queue(item, "facebook")
        else:
            chosen = post_from_text_file(args.text_file, args.link or "", "facebook")
        log = load_log(args.log)
    except SocialError as exc:
        print(exc, file=sys.stderr)
        return 1

    text = chosen["text"]
    link = chosen["link"]
    blocked = publish_refusal(text, link)
    if blocked:
        print(f"{blocked} Nothing posted.", file=sys.stderr)
        return 1
    if not args.publish:
        _print_explicit_draft(chosen, text, link, args.text_file)
        return 0

    log_key = explicit_log_key(chosen)
    if week_recorded(log, log_key) and not args.force:
        print(
            f"{log_key} is already in {display_path(args.log)}. "
            "Nothing posted. Pass --force to post it again.",
            file=sys.stderr,
        )
        return 1

    try:
        page_id = page_id_from(args.page_file)
        token = resolve_token(page_id, args.secrets, args.api)
    except SocialError as exc:
        print(exc, file=sys.stderr)
        return 1
    if not token:
        print(missing_page_token_message(page_id, args.secrets), file=sys.stderr)
        return 1

    try:
        result = publish_page(page_id, token, text, link, args.api)
    except SocialError as exc:
        print(redact(str(exc), [token]), file=sys.stderr)
        return 1

    log[log_key] = {
        "source": chosen["source"],
        "queue_item": chosen.get("queue_item"),
        "link": link,
        "text": text,
        "published_at": now_stamp(),
        "post_id": result["id"],
        "url": result["url"],
    }
    try:
        save_log(args.log, log)
    except OSError as exc:
        print(f"Facebook accepted the post ({result['id']}) but the log was not written. {exc}", file=sys.stderr)
        return 1
    if chosen["source"] == "queue":
        print(f"Posted queue item {chosen['queue_item']} to the MineralDigger Facebook Page.")
    else:
        print("Posted the text file to the MineralDigger Facebook Page.")
    if result.get("url"):
        print(result["url"])
    print("Read-back matched the MineralDigger text.")
    return 0


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
    add_explicit_arguments(parser)
    args = parser.parse_args(argv)

    explicit = run_explicit(args)
    if explicit is not None:
        return explicit

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

    blocked = publish_refusal(post["facebook"], post["link"])
    if blocked:
        print(blocked, file=sys.stderr)
        return 1

    try:
        token = resolve_token(page_id or "", args.secrets, args.api)
    except SocialError as exc:
        print(exc, file=sys.stderr)
        return 1
    if not token:
        print(missing_page_token_message(page_id or "", args.secrets), file=sys.stderr)
        return 1

    if not args.force:
        try:
            already = matching_page_post(fetch_page_posts(page_id or "", token, args.api), post["link"])
        except SocialError as exc:
            print(
                redact(
                    f"Could not read recent Page posts from /{page_id}/posts. "
                    f"The duplicate check used the log only. {exc}",
                    [token],
                ),
                file=sys.stderr,
            )
        else:
            if already:
                shown = _public_post_id(already.get("id"))
                label = f" (post {shown})" if shown else ""
                print(
                    f"This link is already on the MineralDigger Page{label}. "
                    "Nothing posted. Pass --force to post again.",
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
