"""Rock, Gem & Bead Shows homepage: https://www.rockngem.co/"""

import re
from datetime import date

from dates import clock_range, normalise_postcode, parse_show_span

SOURCE = "https://www.rockngem.co/"
# Every date line is the same Rock, Gem & Bead show. The homepage also
# describes mineral, fossil and lapidary stock, but it does not assign those
# to a weekend. Tagging every row with all five types made the type pages
# the same list, so mineral and fossil stay off the row.
TYPES = ["rock", "gem", "bead"]


def parse_rockngem(html: str, today: date | None = None, retrieved: str | None = None) -> list[dict]:
    today = today or date.today()
    retrieved = retrieved or today.isoformat()
    from htmltext import html_to_lines

    lines = html_to_lines(html)
    next_block = _next_show_block(lines)
    events = _date_rows(lines)
    events = _include_next_show(events, next_block, today)
    phone = _phone(html)
    target = _attach_target(
        events,
        next_block.get("postcode"),
        next_block.get("span"),
        today,
    )

    rows = []
    for event in events:
        attached = event is target
        if event.get("from_next_show") and not event.get("list_year") and attached:
            notes = (
                "Date, door price and opening times are printed in the next-show "
                "block on the organiser homepage."
            )
        else:
            notes = "Date from the organiser homepage. " + _list_sentence(event)
            if attached:
                notes += " Door price and opening times are printed in the next-show block for this weekend."
            else:
                notes += " This date line does not repeat a door price or opening times."
        row = {
            "organiser_id": "rockngem",
            "organiser_name": "Rock, Gem & Bead Shows",
            "organiser_url": SOURCE,
            "organiser_phone": phone,
            "name": "Rock, Gem & Bead Show",
            "types": list(TYPES),
            "start": event["start"],
            "end": event["end"],
            "provisional": event["provisional"],
            "year_inferred": False,
            "venue_name": event["venue_name"],
            "street": None,
            "postcode": event["postcode"],
            "times_summary": next_block.get("times") if attached else None,
            "times_notes": next_block.get("times_notes") if attached else None,
            "entry_kind": "paid" if attached and next_block.get("price") else "unknown",
            "entry_adult_gbp": next_block.get("price") if attached else None,
            "entry_notes": next_block.get("entry_notes") if attached else None,
            "dealers": None,
            "parking": "Free parking" if attached and next_block.get("parking") else None,
            "access_notes": None,
            "source_url": SOURCE,
            "source_retrieved": retrieved,
            "source_notes": notes,
            "summary": _summary(event["provisional"]),
        }
        rows.append(row)
    return rows


def _list_sentence(event: dict) -> str:
    """Say which heading the date came from. Provisional follows that heading."""
    if event.get("from_next_show") and not event.get("list_year"):
        return "Printed in the next-show block."
    year = event.get("list_year") or int(str(event["start"])[:4])
    if event["provisional"]:
        return f"{year} dates are printed under the heading Provisional {year} Dates."
    return f"Printed in the {year} date list, which is not marked provisional."


def _summary(provisional: bool) -> str:
    base = (
        "Rock, gem and bead show. Minerals, fossils and lapidary stock are part of this show too."
    )
    if provisional:
        return base + " This 2027 date is marked provisional on their site."
    return base


# Homepage typo seen on 10 November 2026: "Newvase Racecourse" for Newcastle.
_VENUE_CORRECTIONS = {
    "newvase racecourse": "Newcastle Racecourse",
}


def _correct_text(text: str) -> str:
    out = text
    for typo, proper in _VENUE_CORRECTIONS.items():
        out = re.sub(re.escape(typo), proper, out, flags=re.I)
    return out


def _correct_venue(name: str | None) -> str | None:
    if not name:
        return name
    return _correct_text(name)


def _next_show_block(lines: list[str]) -> dict:
    start = next((i for i, line in enumerate(lines) if re.search(r"next show", line, re.I)), None)
    end = None
    if start is not None:
        end = next(
            (
                i
                for i, line in enumerate(lines[start + 1 :], start + 1)
                if _YEAR_HEADING.search(line) or re.search(r"who'?s at", line, re.I)
            ),
            len(lines),
        )
    block = lines[start:end] if start is not None and end is not None and end > start else []
    text = " ".join(block)
    price = None
    price_match = re.search(r"Admission\s+£\s*(\d+)", text, re.I)
    if price_match:
        price = int(price_match.group(1))
    saturday = sunday = None
    for line in block:
        if re.search(r"saturday", line, re.I):
            found = re.search(r"(\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?\s*(?:to|–|—|-)\s*\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?)", line, re.I)
            if found:
                saturday = clock_range(found.group(1))
        if re.search(r"sunday", line, re.I):
            found = re.search(r"(\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?\s*(?:to|–|—|-)\s*\d{1,2}(?:[:.]\d{2})?\s*(?:am|pm)?)", line, re.I)
            if found:
                sunday = clock_range(found.group(1))
    times = None
    bits = []
    if saturday:
        bits.append(f"Saturday {saturday}")
    if sunday:
        bits.append(f"Sunday {sunday}")
    if bits:
        times = ". ".join(bits) + "."
    notes = None
    if any(re.search(r"last entry", line, re.I) for line in block):
        notes = "Last entry one hour before closing."
    entry_notes = None
    if price is not None:
        entry_notes = "Pay on the door. Accompanying under 12s free."
    return {
        "lines": block,
        "postcode": normalise_postcode(text),
        "span": _month_day_span(block),
        "price": price,
        "times": times,
        "times_notes": notes,
        "entry_notes": entry_notes,
        "parking": any(re.search(r"free parking", line, re.I) for line in block),
    }


def _month_day_span(lines: list[str]) -> tuple[str, str] | None:
    """Month and day of the weekend named in the next-show block.

    The block often prints the days without a year, and sometimes without the
    venue on that line. The year comes from the date list.
    """
    for line in lines:
        for candidate in (line, f"{line} Venue"):
            parsed = parse_show_span(candidate, 2000)
            if not parsed:
                continue
            if candidate is not line and parsed["venue_name"] != "Venue":
                continue
            return parsed["start"][5:], parsed["end"][5:]
    return None


# "2027 Dates" is the year 2027. The word provisional is optional and is the
# only thing that marks that list provisional. Matching only "provisional 2027"
# left a plain "2027 Dates" heading inside the 2026 list.
_YEAR_HEADING = re.compile(
    r"\b(?P<provisional>provisional\s+)?(?P<year>20\d{2})\s+dates\b",
    re.I,
)


def _date_rows(lines: list[str]) -> list[dict]:
    section = None
    section_provisional = False
    events = []
    for line in lines:
        heading = _YEAR_HEADING.search(line)
        if heading:
            section = int(heading.group("year"))
            section_provisional = heading.group("provisional") is not None
            continue
        if section and re.search(r"who'?s at", line, re.I):
            break
        if not section:
            continue
        if re.fullmatch(r"[A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2}", line, re.I):
            if events and not events[-1]["postcode"]:
                events[-1]["postcode"] = normalise_postcode(line)
            continue
        parsed = parse_show_span(line, section)
        if not parsed:
            continue
        parsed["provisional"] = section_provisional
        parsed["list_year"] = section
        parsed["venue_name"] = _correct_venue(parsed.get("venue_name"))
        events.append(parsed)
    return events


def _join_next_show_place(block: list[str]) -> str:
    """Date, venue and postcode lines from the next-show block, typo-corrected."""
    bits = []
    for line in block:
        if re.search(r"next show", line, re.I):
            continue
        if re.search(
            r"admission|entry by|free parking|open:|saturday|sunday|last entry",
            line,
            re.I,
        ):
            break
        if _YEAR_HEADING.search(line) or re.search(r"who'?s at", line, re.I):
            break
        bits.append(_correct_text(line))
    return " ".join(bits)


def _next_show_event(next_block: dict, today: date) -> dict | None:
    """Build a date row when the next show is not in a year-dated list.

    After a show weekend the homepage often drops the 2026 date list and leaves
    only the next-show block plus the following year's dates. The year is this
    year when that weekend has not yet ended.
    """
    block = next_block.get("lines") or []
    if not block:
        return None
    parsed = parse_show_span(_join_next_show_place(block), today.year)
    if not parsed:
        return None
    parsed["venue_name"] = _correct_venue(parsed.get("venue_name"))
    if not parsed.get("postcode"):
        parsed["postcode"] = next_block.get("postcode") or normalise_postcode(" ".join(block))
    try:
        end = date.fromisoformat(parsed["end"])
    except ValueError:
        return None
    if end < today:
        return None
    parsed["provisional"] = False
    parsed["from_next_show"] = True
    parsed["list_year"] = None
    return parsed


def _include_next_show(events: list[dict], next_block: dict, today: date) -> list[dict]:
    extra = _next_show_event(next_block, today)
    if not extra:
        return events
    for event in events:
        if (
            event.get("start") == extra["start"]
            and event.get("end") == extra["end"]
            and (event.get("postcode") or "") == (extra.get("postcode") or "")
        ):
            return events
    return [extra, *events]


def _attach_target(
    events: list[dict],
    postcode: str | None,
    span: tuple[str, str] | None,
    today: date,
) -> dict | None:
    """Attach the next-show price and times to the weekend that block names.

    Matching only the next future start date moved Saturday's door price onto
    a later weekend at the same postcode once Sunday arrived. A named span
    stays on the closest weekend with those days, so next year's copy does
    not inherit it. With no span, the earliest date at that postcode that
    has not ended is used.
    """
    if not postcode:
        return None
    dated = []
    for event in events:
        if event.get("postcode") != postcode:
            continue
        if span and (event["start"][5:], event["end"][5:]) != span:
            continue
        try:
            start = date.fromisoformat(event["start"])
            end = date.fromisoformat(event["end"])
        except ValueError:
            continue
        dated.append((start, end, event))
    if not dated:
        return None
    if span:
        dated.sort(key=lambda item: (_day_distance(item[0], item[1], today), item[0]))
        return dated[0][2]
    current = [item for item in dated if item[0] <= today <= item[1]]
    if current:
        current.sort(key=lambda item: item[0])
        return current[0][2]
    upcoming = [item for item in dated if item[1] >= today]
    if upcoming:
        upcoming.sort(key=lambda item: item[0])
        return upcoming[0][2]
    return None


def _day_distance(start: date, end: date, today: date) -> int:
    if start <= today <= end:
        return 0
    if today < start:
        return (start - today).days
    return (today - end).days


def _phone(html: str) -> str | None:
    match = re.search(r"\b(07\d{9})\b", html)
    if not match:
        return None
    digits = match.group(1)
    return f"{digits[:5]} {digits[5:]}"
