#!/usr/bin/env python3
"""Weekly MineralDigger post copy from the show catalogue.

Facebook and Bluesky drafts share this module so the pair stays aligned.
Even ISO weeks lead with the next UK show. Odd weeks lead with a type hub
and the next show of that type. Prices are included only when the catalogue
already has them.

The copy is plain British English: no em dashes, no en dashes, no
exclamation marks, and no Ireland listings.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from digest import TYPE_LABELS, TYPE_ORDER, format_range, parse_iso, sort_shows

ROOT = Path(__file__).resolve().parents[1]
SHOWS_PATH = ROOT / "data" / "shows.json"
SITE_PATH = ROOT / "data" / "site.json"
GROWTH = ROOT / "growth"
SITE_URL = "https://mineraldigger.com"
BLUESKY_LIMIT = 300
BLUESKY_HANDLE = "mineraldigger.com"

UK_NATIONS = {
    "england",
    "scotland",
    "wales",
    "northern ireland",
    "uk",
    "united kingdom",
}
ANGLES = ("next-show", "type-hub")


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


def token_from_pages(data: dict, page_id: str) -> str | None:
    """Pick the token for this Page id out of ~/.secrets/fb_pages.json.

    Accepted shapes:
    - {"1419...": "<token>"}
    - {"1419...": {"access_token": "<token>"}}
    - {"mineraldigger": {"page_id": "1419...", "access_token": "<token>"}}
    - {"pages": [ {"id": "1419...", "token": "<token>"} ]}
    A mineraldigger object with a different page_id is left unused.
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
        key_name = str(key).strip().lower().replace(" ", "")
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
    return None


def assert_voice(text: str) -> None:
    if "!" in text or "\u2014" in text or "\u2013" in text:
        raise SocialError("Post copy uses an em dash, an en dash, or an exclamation mark.")
    if "Ireland" in text:
        raise SocialError("Post copy mentions Ireland. MineralDigger lists UK shows.")
    if "Unknown" in text:
        raise SocialError("Post copy includes an unknown price.")


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


def show_detail(show: dict) -> str:
    name = listed_name(show)
    place = place_phrase(show)
    when = format_range(parse_iso(show["start"]), parse_iso(show["end"]))
    where = f" at {place}" if place else ""
    return f"{name}{where}, {when}"


def on_now(show: dict, today: date) -> bool:
    return parse_iso(show["start"]) <= today <= parse_iso(show["end"])


def next_lead(show: dict, today: date) -> str:
    detail = show_detail(show)
    if on_now(show, today):
        return ensure_period(f"On the MineralDigger list now: {detail}")
    return ensure_period(f"Next on the MineralDigger list is the {detail}")


def type_lead(kind: str) -> str:
    return ensure_period(f"{TYPE_LABELS[kind]} on the MineralDigger map")


def type_follow(show: dict, today: date) -> str:
    detail = show_detail(show)
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
    body.append(link.strip())
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
    room = BLUESKY_LIMIT - len(link) - 2
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
    start = text.rfind(url)
    if start < 0:
        return None
    byte_start = len(text[:start].encode("utf-8"))
    byte_end = byte_start + len(url.encode("utf-8"))
    return {
        "index": {"byteStart": byte_start, "byteEnd": byte_end},
        "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}],
    }


def build_post(
    shows: list[dict],
    today: date,
    site_url: str = SITE_URL,
    angle: str | None = None,
    kind: str | None = None,
) -> dict | None:
    """Return the twin drafts for this ISO week, or None when nothing is upcoming."""
    site_url = site_url.rstrip("/") or SITE_URL
    week, number = week_parts(today)
    angle = angle or default_angle(number)
    if angle not in ANGLES:
        raise SocialError("Angle must be next-show or type-hub.")

    rows = upcoming_shows(shows, today)
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
