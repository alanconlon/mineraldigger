#!/usr/bin/env python3
"""Weekly MineralDigger post copy from the show catalogue.

Facebook and Bluesky drafts share this module so the pair stays aligned.
Even ISO weeks lead with the next UK show. Odd weeks lead with a type hub
and the next show of that type. Prices are included only when the catalogue
already has them.

The copy is plain British English: no em dashes, no en dashes, no
exclamation marks, and no Ireland listings. The post text names the
page as mineraldigger.com/... . The full https URL stays in the link
card or the link field, and publish refuses a text that contains one.
"""

from __future__ import annotations

import json
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


def publish_refusal(text: str) -> str | None:
    """Why --publish must stop, or None when the text is allowed out.

    The visible post may say mineraldigger.com/.... It may not contain
    an exclamation mark, an en dash, an em dash, or an https:// URL.
    """
    if "!" in text or "\u2013" in text or "\u2014" in text or "https://" in text.casefold():
        return (
            "Refusing to publish. The post text contains '!', an en dash, an em dash, or 'https://'."
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
