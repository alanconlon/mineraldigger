#!/usr/bin/env python3
"""Weekly MineralDigger post copy from the show catalogue.

Facebook and Bluesky drafts share this module so the pair stays aligned.
Even ISO weeks lead with the next UK show. Odd weeks lead with a type hub
and the next show of that type. Prices are included only when the catalogue
already has them.

The copy is plain British English: no em dashes, no en dashes, no
exclamation marks, and no Ireland listings. The post text names the
page as mineraldigger.com/... . The full https URL stays in the link
card or the link field. Publish refuses a text that contains one, and
it refuses FairDigger or AuctionDigger wording or a link off this brand.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from digest import MONTHS, TYPE_LABELS, TYPE_ORDER, WEEKDAYS, parse_iso, sort_shows

ROOT = Path(__file__).resolve().parents[1]
SHOWS_PATH = ROOT / "data" / "shows.json"
SITE_PATH = ROOT / "data" / "site.json"
GROWTH = ROOT / "growth"
SITE_URL = "https://mineraldigger.com"
BLUESKY_LIMIT = 300
BLUESKY_HANDLE = "mineraldigger.com"
BRAND_SITE = "mineral"
BRAND_NAME = "MineralDigger"
OWN_HOSTS = frozenset({"mineraldigger.com", "mineraldigger.co.uk"})
SITE_LABELS = {
    "mineral": "MineralDigger",
    "fair": "FairDigger",
    "auction": "AuctionDigger",
}
_OTHER_BRANDS = (
    (
        "FairDigger",
        re.compile(r"(?<![a-z0-9])fair[\s\-]*digger(?![a-z0-9])", re.IGNORECASE),
        ("fairdigger.co.uk", "fairdigger.com"),
    ),
    (
        "AuctionDigger",
        re.compile(r"(?<![a-z0-9])auction[\s\-]*digger(?![a-z0-9])", re.IGNORECASE),
        ("auctiondigger.ie",),
    ),
)
_TEXT_FIELDS = {"facebook": "facebook_text", "bluesky": "bluesky_text"}

UK_NATIONS = {
    "england",
    "scotland",
    "wales",
    "northern ireland",
    "uk",
    "united kingdom",
}
ANGLES = ("next-show", "type-hub")
REPEAT_DAYS = 14
GENERIC_VENUE_WORDS = {"racecourse", "showground", "hall", "centre", "center", "school", "academy", "club", "hotel"}


class SocialError(RuntimeError):
    pass


def week_parts(today: date) -> tuple[str, int]:
    iso = today.isocalendar()
    return f"{iso.year}-W{iso.week:02d}", iso.week


def week_key(today: date) -> str:
    return week_parts(today)[0]


def now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_angle(week_number: int) -> str:
    if week_number % 2 == 0:
        return "next-show"
    return "type-hub"


def default_kind(week_number: int) -> str:
    return TYPE_ORDER[week_number % len(TYPE_ORDER)]


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def load_json(path: Path) -> dict:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SocialError(f"{display_path(path)} is missing.") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SocialError(f"{display_path(path)} is not valid JSON.") from exc
    if not isinstance(data, dict):
        raise SocialError(f"{display_path(path)} must be a JSON object.")
    return data


def load_shows(path: Path) -> list[dict]:
    payload = load_json(path)
    shows = payload.get("shows")
    if not isinstance(shows, list):
        raise SocialError(f"{display_path(path)} has no shows list.")
    return shows


def load_site(path: Path) -> str:
    if not path.is_file():
        return SITE_URL
    url = (load_json(path).get("url") or SITE_URL).strip()
    return url.rstrip("/") or SITE_URL


def load_log(path: Path) -> dict:
    if not path.is_file():
        return {}
    data = load_json(path)
    return data


def save_log(path: Path, log: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(log, indent=2, ensure_ascii=False) + "\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def week_recorded(log: dict, week: str) -> bool:
    row = log.get(week)
    return isinstance(row, dict) and bool(row)


def redact(text: str, secrets: list[str]) -> str:
    cleaned = text
    for secret in secrets:
        if secret:
            cleaned = cleaned.replace(secret, "[redacted]")
    return cleaned


def _string_field(value: object, keys: tuple[str, ...]) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    if isinstance(value, dict):
        for key in keys:
            raw = value.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
    return None


def _normal_key(key: object) -> str:
    return str(key).strip().lower().replace(" ", "").replace("-", "_")


# A user token can mint a page token. It is not itself a page token.
USER_TOKEN_KEYS = ("fb_user_token", "user_token", "user_access_token")
BLUESKY_PASSWORD_KEY = "mineraldigger_bluesky_app_password"


def display_secret(path: Path) -> str:
    """~/.secrets/name when the file sits under the home directory."""
    try:
        relative = path.resolve().relative_to(Path.home().resolve())
    except ValueError:
        return str(path)
    return "~/" + relative.as_posix()


def read_secret_file(path: Path, keys: tuple[str, ...] = ()) -> str | None:
    """Read one secret from a file.

    A plain text file is the secret itself. A JSON object may hold it under
    one of keys. The file contents are never included in an error.
    """
    if not path.is_file():
        return None
    try:
        raw = path.read_text(encoding="utf-8-sig").strip()
    except OSError as exc:
        raise SocialError(f"Could not read {display_secret(path)}.") from exc
    if not raw:
        return None
    if raw[0] in "{[":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SocialError(f"{display_secret(path)} is not valid JSON.") from exc
        if isinstance(data, str) and data.strip():
            return data.strip()
        if isinstance(data, dict):
            found = _string_field(data, keys) if keys else None
            if found:
                return found
            for key in keys:
                found = named_secret(data, key)
                if found:
                    return found
            return None
        return None
    line = raw.splitlines()[0].strip()
    return line or None


def named_secret(data: dict, name: str) -> str | None:
    """The string stored under name, or a nested app_password, password, or token."""
    if not isinstance(data, dict):
        return None
    wanted = _normal_key(name)
    for key, value in data.items():
        if _normal_key(key) != wanted:
            continue
        found = _string_field(value, ("app_password", "password", "access_token", "token", "secret"))
        if found:
            return found
    return None


def user_token_from_pages(data: dict) -> str | None:
    """The stored user token in ~/.secrets/fb_pages.json, named fb_user_token.

    A user token is not a page token. The caller exchanges it for the Page.
    """
    if not isinstance(data, dict):
        return None
    by_name = {_normal_key(key): value for key, value in data.items()}
    for name in USER_TOKEN_KEYS:
        if name not in by_name:
            continue
        found = _string_field(by_name[name], ("access_token", "token", "user_token", "fb_user_token"))
        if found:
            return found
    return None


def token_from_pages(data: dict, page_id: str) -> str | None:
    """Pick the token for this Page id out of ~/.secrets/fb_pages.json.

    Accepted shapes:
    - {"1419...": "<token>"}
    - {"1419...": {"access_token": "<token>"}}
    - {"mineraldigger": {"page_id": "1419...", "access_token": "<token>"}}
    - {"pages": [ {"id": "1419...", "token": "<token>"} ]}
    A mineraldigger object with a different page_id is left unused.
    Keys named fb_user_token, user_token, or user_access_token are user
    tokens and are left unused here.
    """
    if not isinstance(data, dict):
        return None
    page_id = str(page_id).strip()
    direct = _string_field(data.get(page_id), ("access_token", "token", "page_token"))
    if direct:
        return direct

    pages = data.get("pages")
    nested: list[object] = []
    if isinstance(pages, dict):
        found = token_from_pages(pages, page_id)
        if found:
            return found
    elif isinstance(pages, list):
        nested.extend(pages)

    for key, value in data.items():
        if key == "pages":
            continue
        owner = ""
        if isinstance(value, dict):
            owner = str(value.get("page_id") or value.get("id") or "").strip()
        key_name = _normal_key(key)
        if key_name in USER_TOKEN_KEYS:
            continue
        if owner == page_id or (key_name == "mineraldigger" and owner in {"", page_id}):
            token = _string_field(value, ("access_token", "token", "page_token"))
            if token:
                return token

    for value in nested:
        if not isinstance(value, dict):
            continue
        owner = str(value.get("page_id") or value.get("id") or "").strip()
        if owner == page_id:
            token = _string_field(value, ("access_token", "token", "page_token"))
            if token:
                return token
    return None


def normal_handle(value: str) -> str:
    return value.strip().lower().lstrip("@")


def password_from_bluesky(data: dict, handle: str) -> str | None:
    """Pick the app password for mineraldigger.com out of ~/.secrets/bluesky.json.

    Accepted shapes:
    - {"mineraldigger.com": "<app password>"}
    - {"mineraldigger.com": {"app_password": "<app password>"}}
    - {"handle": "mineraldigger.com", "app_password": "<app password>"}
    - {"accounts": [{"handle": "mineraldigger.com", "app_password": "..."}]}
    - {"mineraldigger_bluesky_app_password": "<app password>"}
    The last shape is only used for the mineraldigger.com handle.
    """
    if not isinstance(data, dict):
        return None
    wanted = normal_handle(handle)

    for key, value in data.items():
        if normal_handle(str(key)) == wanted:
            found = _string_field(value, ("app_password", "password"))
            if found:
                return found

    owner = normal_handle(str(data.get("handle") or data.get("identifier") or ""))
    if owner == wanted:
        found = _string_field(data, ("app_password", "password"))
        if found:
            return found

    accounts = data.get("accounts")
    rows = accounts if isinstance(accounts, list) else []
    if not rows:
        rows = [value for value in data.values() if isinstance(value, dict)]
    for value in rows:
        if not isinstance(value, dict):
            continue
        owner = normal_handle(str(value.get("handle") or value.get("identifier") or ""))
        if owner == wanted:
            found = _string_field(value, ("app_password", "password"))
            if found:
                return found
    if wanted == normal_handle(BLUESKY_HANDLE):
        found = named_secret(data, BLUESKY_PASSWORD_KEY)
        if found:
            return found
    return None


def assert_voice(text: str) -> None:
    if "!" in text or "\u2014" in text or "\u2013" in text:
        raise SocialError("Post copy uses an em dash, an en dash, or an exclamation mark.")
    if "Ireland" in text:
        raise SocialError("Post copy mentions Ireland. MineralDigger lists UK shows.")
    if "Unknown" in text:
        raise SocialError("Post copy includes an unknown price.")


def link_host(url: str) -> str:
    """Hostname of a bare domain or a full URL, without a leading www."""
    text = (url or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "https://" + text
    host = urllib.parse.urlsplit(text).hostname or ""
    return host.casefold().removeprefix("www.")


def absolute_link(url: str) -> str:
    """https URL for the Facebook link field and the Bluesky card."""
    text = (url or "").strip()
    if not text:
        return ""
    lowered = text.casefold()
    if lowered.startswith("https://"):
        return "https://" + text[len("https://"):]
    if lowered.startswith("http://"):
        return "https://" + text[len("http://"):]
    return "https://" + text


def canonical_link(url: str) -> str:
    """Host and path, for comparing the link we sent with the live post.

    Scheme, a leading www, a trailing slash and a query string are ignored.
    """
    host = link_host(url)
    text = (url or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "https://" + text
    path = urllib.parse.urlsplit(text).path or ""
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    if path == "/":
        path = ""
    return host + path.casefold()


def is_own_host(host: str) -> bool:
    return host.casefold().removeprefix("www.") in OWN_HOSTS


def foreign_brand(value: str) -> str | None:
    """FairDigger or AuctionDigger when this MineralDigger text names one of them."""
    folded = value.casefold()
    for name, pattern, domains in _OTHER_BRANDS:
        if pattern.search(value) or any(domain in folded for domain in domains):
            return name
    return None


def destination_url(url: str) -> str:
    """Unwrap a Facebook l.php redirect so the real host can be checked."""
    text = (url or "").strip()
    if not text:
        return ""
    parts = urllib.parse.urlsplit(text if "://" in text else "https://" + text)
    host = (parts.hostname or "").casefold().removeprefix("www.")
    if host == "facebook.com" or host.endswith(".facebook.com") or host == "fb.com" or host.endswith(".fb.com"):
        query = urllib.parse.parse_qs(parts.query)
        target = (query.get("u") or query.get("url") or [""])[0].strip()
        if target and target != text:
            return destination_url(target)
    return text


def _same_text(left: str, right: str) -> bool:
    def normal(value: str) -> str:
        return value.replace("\r\n", "\n").replace("\r", "\n")

    return normal(left) == normal(right)


def publish_refusal(text: str, link: str | None = None) -> str | None:
    """Why publishing must stop, or None when the text and link are allowed.

    The visible post may name mineraldigger.com or mineraldigger.co.uk.
    It may not contain an exclamation mark, an en dash, an em dash, or an
    https:// URL. It may not mention FairDigger or AuctionDigger. When a
    link is given, that link must be on mineraldigger.com or mineraldigger.co.uk.
    Direct publish calls pass the link, so the brand check covers them too.
    """
    if "!" in text or "\u2013" in text or "\u2014" in text or "https://" in text.casefold():
        return (
            "Refusing to publish. The post text contains '!', an en dash, an em dash, or 'https://'."
        )
    other = foreign_brand(text)
    if other:
        return f"Refusing to publish. The post text mentions {other}, which is not {BRAND_NAME}."
    if link is None:
        return None
    other = foreign_brand(link)
    if other:
        return f"Refusing to publish. The link mentions {other}, which is not {BRAND_NAME}."
    host = link_host(link)
    if not is_own_host(host):
        shown = host or "a missing domain"
        return (
            f"Refusing to publish. The link {shown} is not a MineralDigger domain. "
            "Use mineraldigger.com or mineraldigger.co.uk."
        )
    return None


def bare_link(url: str) -> str:
    """mineraldigger.com/show/... for the post text. The https URL stays on the card."""
    text = url.strip()
    lowered = text.lower()
    for prefix in ("https://", "http://"):
        if lowered.startswith(prefix):
            return text[len(prefix):]
    return text


def _attachment_destinations(live: dict) -> list[str]:
    found: list[str] = []
    raw_link = live.get("link")
    if isinstance(raw_link, str) and raw_link.strip():
        found.append(destination_url(raw_link))
    attachments = live.get("attachments")
    rows = []
    if isinstance(attachments, dict) and isinstance(attachments.get("data"), list):
        rows = attachments["data"]
    elif isinstance(attachments, list):
        rows = attachments
    for row in rows:
        if not isinstance(row, dict):
            continue
        unshimmed = row.get("unshimmed_url")
        if isinstance(unshimmed, str) and unshimmed.strip():
            found.append(destination_url(unshimmed))
            continue
        for key in ("url", "link"):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                found.append(destination_url(value))
        target = row.get("target")
        if isinstance(target, dict) and isinstance(target.get("url"), str) and target["url"].strip():
            found.append(destination_url(target["url"]))
    return found


def bluesky_readback_error(live: dict, text: str, link: str, handle: str) -> str | None:
    """Why the live Bluesky post is not the one we sent, or None when it matches.

    The live text, the author handle, and every link facet or card must match.
    """
    if not isinstance(live, dict):
        return "Bluesky read-back mismatch. The live post was not returned."
    record = live.get("record") if isinstance(live.get("record"), dict) else {}
    live_text = record.get("text") if isinstance(record.get("text"), str) else ""
    if not _same_text(live_text, text):
        return (
            "Bluesky read-back mismatch. The live post text does not match "
            "the MineralDigger text that was sent."
        )
    author = live.get("author") if isinstance(live.get("author"), dict) else {}
    live_handle = normal_handle(str(author.get("handle") or ""))
    if live_handle != normal_handle(handle):
        shown = live_handle or "an unknown handle"
        return f"Bluesky read-back mismatch. The live post is by {shown}, not {handle}."
    uris: list[str] = []
    facets = record.get("facets") if isinstance(record.get("facets"), list) else []
    for facet in facets:
        if not isinstance(facet, dict):
            continue
        features = facet.get("features") if isinstance(facet.get("features"), list) else []
        for feature in features:
            if isinstance(feature, dict) and isinstance(feature.get("uri"), str) and feature["uri"].strip():
                uris.append(feature["uri"])
    embed = record.get("embed") if isinstance(record.get("embed"), dict) else {}
    external = embed.get("external") if isinstance(embed.get("external"), dict) else {}
    card = external.get("uri")
    if isinstance(card, str) and card.strip():
        uris.append(card)
    if not uris:
        return (
            "Bluesky read-back mismatch. The live post has no link facet or card "
            "for the MineralDigger link that was sent."
        )
    intended_host = link_host(link)
    intended = canonical_link(link)
    live_hosts = [link_host(uri) for uri in uris]
    if any(host != intended_host or not is_own_host(host) for host in live_hosts):
        shown = ", ".join(host or "a missing domain" for host in live_hosts)
        return (
            "Bluesky read-back mismatch. The live link facet or card domain is "
            f"{shown}, not {intended_host}."
        )
    if any(canonical_link(uri) != intended for uri in uris):
        return (
            "Bluesky read-back mismatch. The live link facet or card does not match "
            "the MineralDigger link that was sent."
        )
    return None


def facebook_readback_error(live: dict, text: str, link: str) -> str | None:
    """Why the live Page post is not the one we sent, or None when it matches.

    The message must match. When Graph returns a link attachment, that link
    must be the MineralDigger link that was sent.
    """
    if not isinstance(live, dict):
        return "Facebook read-back mismatch. The live Page post was not returned."
    live_text = live.get("message") if isinstance(live.get("message"), str) else ""
    if not _same_text(live_text, text):
        return (
            "Facebook read-back mismatch. The live Page post text does not match "
            "the MineralDigger text that was sent."
        )
    urls = _attachment_destinations(live)
    if not urls:
        bare = bare_link(link)
        if bare and bare in live_text:
            return None
        return (
            "Facebook read-back mismatch. The live Page post does not include "
            "the MineralDigger link that was sent."
        )
    intended_host = link_host(link)
    intended = canonical_link(link)
    if any(link_host(url) != intended_host or not is_own_host(link_host(url)) for url in urls):
        shown = ", ".join(link_host(url) or "a missing domain" for url in urls)
        return (
            "Facebook read-back mismatch. The live link domain is "
            f"{shown}, not {intended_host}."
        )
    if any(canonical_link(url) != intended for url in urls):
        return (
            "Facebook read-back mismatch. The live link does not match "
            "the MineralDigger link that was sent."
        )
    return None


def add_explicit_arguments(parser: argparse.ArgumentParser) -> None:
    """Flags for the only two explicit sources. Neither has a default path."""
    parser.add_argument(
        "--queue",
        type=Path,
        help="Posting queue JSON. Required with --queue-item. There is no default path.",
    )
    parser.add_argument(
        "--queue-item",
        help="Id of one item in --queue. The item site must be mineral.",
    )
    parser.add_argument(
        "--text-file",
        type=Path,
        help="Explicit UTF-8 text file. Required with --link. There is no default path.",
    )
    parser.add_argument(
        "--link",
        help="Link for --text-file. A bare mineraldigger.com path or an https URL on that host.",
    )


def explicit_mode(
    queue: Path | None,
    queue_item: str | None,
    text_file: Path | None,
    link: str | None,
) -> str:
    """'queue', 'text-file', or '' for the show catalogue.

    Raises SocialError when the flags are incomplete or both sources are set.
    There is no default path and no temp-file fallback.
    """
    wants_queue = bool((queue_item or "").strip()) or queue is not None
    wants_file = text_file is not None or bool((link or "").strip())
    if wants_queue and wants_file:
        raise SocialError(
            "Pass one source: --queue-item with --queue, or --text-file with --link. Nothing posted."
        )
    if wants_queue:
        if not (queue_item or "").strip() or queue is None:
            raise SocialError(
                "Pass both --queue-item and --queue with the queue JSON path. "
                "This script has no default queue and does not read a leftover temp file. Nothing posted."
            )
        return "queue"
    if wants_file:
        if text_file is None or not (link or "").strip():
            raise SocialError(
                "Pass both --text-file and --link. "
                "This script has no default text file and does not read a leftover temp file. Nothing posted."
            )
        if str(text_file) == "-":
            raise SocialError("Pass a file path to --text-file. Standard input is not read. Nothing posted.")
        return "text-file"
    return ""


def load_queue_item(path: Path, item_id: str) -> dict:
    """The one queue item, after checking it belongs to MineralDigger."""
    wanted = item_id.strip()
    if not wanted:
        raise SocialError("Pass --queue-item with the queue item id. Nothing posted.")
    data = load_json(path)
    items = data.get("items")
    if not isinstance(items, list):
        raise SocialError(f"{display_path(path)} has no items list. Nothing posted.")
    matches = [item for item in items if isinstance(item, dict) and str(item.get("id") or "") == wanted]
    if not matches:
        raise SocialError(f"Queue item {wanted} is not in {display_path(path)}. Nothing posted.")
    if len(matches) > 1:
        raise SocialError(f"Queue item {wanted} appears more than once in {display_path(path)}. Nothing posted.")
    item = matches[0]
    site = str(item.get("site") or "").strip().casefold()
    if site != BRAND_SITE:
        label = SITE_LABELS.get(site) or site or "missing"
        raise SocialError(
            f"Refusing to publish. Queue item {wanted} is {label}, not {BRAND_NAME}. "
            "This repo only publishes MineralDigger."
        )
    return item


def post_from_queue(item: dict, network: str) -> dict:
    field = _TEXT_FIELDS[network]
    text = item.get(field)
    if not isinstance(text, str) or not text.strip():
        raise SocialError(f"Queue item {item.get('id')} has no {field}. Nothing posted.")
    link = item.get("link")
    if not isinstance(link, str) or not link.strip():
        raise SocialError(f"Queue item {item.get('id')} has no link. Nothing posted.")
    return {
        "source": "queue",
        "queue_item": str(item.get("id")),
        "link": absolute_link(link),
        "text": text,
        "network": network,
    }


def read_explicit_text(path: Path) -> str:
    if str(path) == "-" or not path.is_file():
        raise SocialError(
            f"{display_path(path)} is missing. Pass the text file on --text-file. Nothing posted."
        )
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise SocialError(f"Could not read {display_path(path)}. Nothing posted.") from exc
    if raw.endswith("\r\n"):
        raw = raw[:-2]
    elif raw.endswith("\n"):
        raw = raw[:-1]
    if not raw.strip():
        raise SocialError(f"{display_path(path)} is empty. Nothing posted.")
    return raw


def post_from_text_file(path: Path, link: str, network: str) -> dict:
    return {
        "source": "text-file",
        "queue_item": None,
        "link": absolute_link(link),
        "text": read_explicit_text(path),
        "network": network,
    }


def explicit_log_key(explicit: dict) -> str:
    if explicit["source"] == "queue":
        return str(explicit["queue_item"])
    digest = hashlib.sha256(explicit["text"].encode("utf-8")).hexdigest()[:16]
    return f"text-file:{digest}"


def is_uk(show: dict) -> bool:
    nation = ((show.get("venue") or {}).get("nation") or "").strip().lower()
    return nation == "" or nation in UK_NATIONS


def upcoming_shows(shows: list[dict], today: date) -> list[dict]:
    today_iso = today.isoformat()
    rows = []
    for show in shows:
        if not isinstance(show, dict):
            continue
        if not show.get("slug") or not show.get("name") or not show.get("start") or not show.get("end"):
            continue
        if show["end"] < today_iso:
            continue
        if not is_uk(show):
            continue
        rows.append(show)
    return sort_shows(rows)


def first_of_type(rows: list[dict], kind: str) -> dict | None:
    for show in rows:
        if kind in (show.get("types") or []):
            return show
    return None


def ensure_period(text: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return cleaned
    if cleaned[-1] not in ".?":
        cleaned += "."
    return cleaned


def place_phrase(show: dict) -> str:
    venue = show.get("venue") or {}
    name = " ".join((venue.get("name") or "").split())
    town = " ".join((venue.get("town") or "").split())
    if name and town and town.casefold() not in name.casefold():
        return f"{name}, {town}"
    return name or town


def listed_name(show: dict) -> str:
    name = " ".join(str(show.get("name") or "").split())
    town = " ".join(((show.get("venue") or {}).get("town") or "").split())
    if town and not name.casefold().startswith(town.casefold()):
        return f"{town}: {name}"
    return name


def post_day(value: date, year: bool = False) -> str:
    """'Saturday 7 November' for post copy. The year is added only when asked."""
    text = f"{WEEKDAYS[value.weekday()]} {value.day} {MONTHS[value.month - 1]}"
    return f"{text} {value.year}" if year else text


def post_range(start: date, end: date, today: date | None = None) -> str:
    """Show dates for post copy, each date next to its weekday and no dashes:
    'Saturday 7 November', 'Saturday 7 and Sunday 8 November',
    'Saturday 31 October to Sunday 1 November'. The year appears only when the
    show is not in the year of the post."""
    year = today is not None and (start.year != today.year or end.year != today.year)
    if start == end:
        return post_day(start, year)
    if (start.year, start.month) == (end.year, end.month):
        joiner = " and " if (end - start).days == 1 else " to "
        return f"{WEEKDAYS[start.weekday()]} {start.day}{joiner}{post_day(end, year)}"
    return f"{post_day(start, year and start.year != end.year)} to {post_day(end, year)}"


def show_detail(show: dict, today: date | None = None) -> str:
    name = listed_name(show)
    place = place_phrase(show)
    when = post_range(parse_iso(show["start"]), parse_iso(show["end"]), today)
    where = f" at {place}" if place else ""
    return f"{name}{where}, {when}"


def on_now(show: dict, today: date) -> bool:
    return parse_iso(show["start"]) <= today <= parse_iso(show["end"])


def next_lead(show: dict, today: date) -> str:
    detail = show_detail(show, today)
    if on_now(show, today):
        return ensure_period(f"On the MineralDigger list now: {detail}")
    return ensure_period(f"Next on the MineralDigger list is the {detail}")


def type_lead(kind: str) -> str:
    return ensure_period(f"{TYPE_LABELS[kind]} on the MineralDigger map")


def type_follow(show: dict, today: date) -> str:
    detail = show_detail(show, today)
    if on_now(show, today):
        return ensure_period(f"On now: {detail}")
    return ensure_period(f"Next listed is the {detail}")


def entry_sentence(show: dict) -> str | None:
    entry = show.get("entry") or {}
    kind = entry.get("kind")
    if kind == "free":
        return "Free entry."
    if kind == "paid":
        label = " ".join((entry.get("label") or "").split())
        if label and label.casefold() != "unknown":
            return ensure_period(label)
    return None


def times_sentence(show: dict) -> str | None:
    summary = " ".join(((show.get("times") or {}).get("summary") or "").split())
    if not summary:
        return None
    return ensure_period(summary)


def extra_sentences(show: dict, short: bool) -> list[str]:
    lines = []
    if show.get("provisional"):
        lines.append("The organiser lists this date as provisional.")
    if show.get("year_inferred"):
        if short:
            lines.append("The year matches the weekday on the organiser page.")
        else:
            lines.append("The date uses the year that matches the weekday on the organiser page.")
    return lines


def show_url(site_url: str, show: dict) -> str:
    return f"{site_url.rstrip('/')}/show/{show['slug']}/"


def hub_url(site_url: str, kind: str) -> str:
    return f"{site_url.rstrip('/')}/{kind}/"


def join_parts(parts: list[str], link: str) -> str:
    body = [part.strip() for part in parts if part and part.strip()]
    shown = bare_link(link)
    if shown:
        body.append(shown)
    return "\n\n".join(body)


def fit_bluesky(parts: list[str], link: str) -> str:
    chosen = [part.strip() for part in parts if part and part.strip()]
    if not chosen:
        raise SocialError("Bluesky post has no text.")
    text = join_parts(chosen, link)
    while len(text) > BLUESKY_LIMIT and len(chosen) > 1:
        chosen.pop()
        text = join_parts(chosen, link)
    if len(text) <= BLUESKY_LIMIT:
        assert_voice(text)
        return text
    room = BLUESKY_LIMIT - len(bare_link(link)) - 2
    if room < 24:
        raise SocialError("Bluesky post does not fit in 300 characters.")
    shortened = chosen[0][:room].rsplit(" ", 1)[0].rstrip(" ,;:.")
    if not shortened:
        raise SocialError("Bluesky post does not fit in 300 characters.")
    chosen[0] = shortened + "."
    text = join_parts(chosen, link)
    if len(text) > BLUESKY_LIMIT:
        raise SocialError("Bluesky post does not fit in 300 characters.")
    assert_voice(text)
    return text


def link_facet(text: str, url: str) -> dict | None:
    """Link the bare domain in the text. The facet URI keeps the full https URL."""
    shown = bare_link(url)
    if not shown:
        return None
    start = text.rfind(shown)
    if start < 0:
        return None
    byte_start = len(text[:start].encode("utf-8"))
    byte_end = byte_start + len(shown.encode("utf-8"))
    return {
        "index": {"byteStart": byte_start, "byteEnd": byte_end},
        "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}],
    }


def link_card(link: str, text: str) -> dict:
    """Bluesky link card. The full URL lives here, not in the post text."""
    prose = ""
    for part in text.split("\n\n"):
        cleaned = part.strip()
        if cleaned and "mineraldigger.com" not in cleaned.casefold():
            prose = cleaned
            break
    if len(prose) > 280:
        prose = prose[:280].rsplit(" ", 1)[0].rstrip(" ,;:.")
        if prose and prose[-1] not in ".?":
            prose += "."
    if not prose:
        prose = "UK rock, gem, mineral, fossil and bead shows."
    return {
        "$type": "app.bsky.embed.external",
        "external": {
            "uri": link,
            "title": "MineralDigger",
            "description": prose,
        },
    }


def show_keys(show: dict) -> list[str]:
    """Strings that identify a show in an earlier post: its page slug, and its venue
    name with and without a generic last word ('Kempton Park Racecourse' and 'Kempton Park')."""
    keys = []
    slug = str(show.get("slug") or "").strip()
    if slug:
        keys.append(f"/show/{slug}")
    venue = " ".join(((show.get("venue") or {}).get("name") or "").split()).split(",")[0].strip()
    if len(venue) >= 6:
        keys.append(venue)
        words = venue.split()
        if len(words) > 2 and words[-1].casefold() in GENERIC_VENUE_WORDS:
            keys.append(" ".join(words[:-1]))
    return keys


def post_haystack(post: dict) -> str:
    """Text plus every link in a post (facets, link card), for repeat matching."""
    bits = [str(post.get("text") or "")]
    bits += [str(link) for link in post.get("links") or []]
    return "\n".join(bits).casefold()


def _stamp_date(value: str) -> date | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def recent_posts(posts: list[dict], today: date, days: int = REPEAT_DAYS) -> list[dict]:
    cutoff = today - timedelta(days=days)
    rows = []
    for post in posts:
        when = _stamp_date(post.get("posted_at") or "")
        if when is not None and cutoff <= when <= today:
            rows.append(post)
    return rows


def posts_from_log(log: dict) -> list[dict]:
    """Earlier posts in the repo log, shaped like feed posts."""
    rows = []
    for row in (log or {}).values():
        if not isinstance(row, dict):
            continue
        links = [row.get("link") or ""]
        if row.get("show_slug"):
            links.append(f"/show/{row['show_slug']}/")
        rows.append({"text": row.get("text") or "", "links": links, "posted_at": row.get("published_at") or ""})
    return rows


def repeated_slugs(shows: list[dict], posts: list[dict], today: date, days: int = REPEAT_DAYS) -> set[str]:
    """Slugs of upcoming shows already named or linked in a post from the last `days` days."""
    recent = [post_haystack(post) for post in recent_posts(posts, today, days)]
    found = set()
    seen_venues = set()
    for show in upcoming_shows(shows, today):
        keys = [key.casefold() for key in show_keys(show)]
        slug_key, venue_keys = keys[:1], keys[1:]
        # A venue name only counts for the next show at that venue, so a post about
        # Kempton Park this month does not hold back the Kempton show next February.
        if venue_keys and venue_keys[0] in seen_venues:
            venue_keys = []
        seen_venues.update(venue_keys[:1])
        if any(key in hay for hay in recent for key in slug_key + venue_keys):
            found.add(show["slug"])
    return found


def build_post(
    shows: list[dict],
    today: date,
    site_url: str = SITE_URL,
    angle: str | None = None,
    kind: str | None = None,
    skip: set[str] | None = None,
) -> dict | None:
    """Return the twin drafts for this ISO week, or None when nothing is upcoming.

    skip holds show slugs posted in the last 14 days (repeated_slugs). Those
    shows are passed over so the same show is not posted again within 14 days."""
    site_url = site_url.rstrip("/") or SITE_URL
    week, number = week_parts(today)
    angle = angle or default_angle(number)
    if angle not in ANGLES:
        raise SocialError("Angle must be next-show or type-hub.")

    rows = upcoming_shows(shows, today)
    if skip:
        rows = [show for show in rows if show.get("slug") not in skip]
    if not rows:
        return None

    chosen_kind = None
    if angle == "next-show":
        show = rows[0]
        link = show_url(site_url, show)
        lead = next_lead(show, today)
        follow = None
    else:
        chosen_kind = kind or default_kind(number)
        if chosen_kind not in TYPE_ORDER:
            raise SocialError("Type must be rock, gem, mineral, fossil or bead.")
        show = None
        start = TYPE_ORDER.index(chosen_kind)
        for offset in range(len(TYPE_ORDER)):
            candidate = TYPE_ORDER[(start + offset) % len(TYPE_ORDER)]
            found = first_of_type(rows, candidate)
            if found is not None:
                chosen_kind = candidate
                show = found
                break
        if show is None:
            return None
        link = hub_url(site_url, chosen_kind)
        lead = type_lead(chosen_kind)
        follow = type_follow(show, today)

    entry = entry_sentence(show)
    times = times_sentence(show)
    facebook_parts = [lead] if follow is None else [lead, follow]
    bluesky_parts = list(facebook_parts)
    if entry:
        facebook_parts.append(entry)
        bluesky_parts.append(entry)
    if times:
        facebook_parts.append(times)
    bluesky_parts.extend(extra_sentences(show, short=True))
    if times:
        bluesky_parts.append(times)
    facebook_parts.extend(extra_sentences(show, short=False))

    facebook = join_parts(facebook_parts, link)
    bluesky = fit_bluesky(bluesky_parts, link)
    assert_voice(facebook)
    if "mineraldigger.com" not in facebook or "mineraldigger.com" not in bluesky:
        raise SocialError("Post copy is missing the mineraldigger.com link.")

    return {
        "week": week,
        "angle": angle,
        "kind": chosen_kind,
        "link": link,
        "facebook": facebook,
        "bluesky": bluesky,
        "show_id": show.get("id"),
        "show_slug": show.get("slug"),
        "show_name": show.get("name"),
    }


def print_draft(heading: str, text: str, post: dict, log_path: Path, recorded: bool) -> None:
    print("Dry run. Nothing posted.")
    print(f"Week: {post['week']}")
    print(f"Angle: {post['angle']}")
    if post.get("kind"):
        print(f"Type: {post['kind']}")
    print(f"Link: {post['link']}")
    print(f"{heading}:")
    print(text)
    if recorded:
        print(
            f"Week {post['week']} is already in {display_path(log_path)}. "
            "--publish stops unless you pass --force."
        )
