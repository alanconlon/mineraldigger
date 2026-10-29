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
    phone = _phone(html)
    target = _attach_target(events, next_block.get("postcode"), today)

    rows = []
    for event in events:
        attached = event is target
        notes = (
            "Date from the organiser homepage. "
            + (
                "2027 dates are printed under the heading Provisional 2027 Dates."
                if event["provisional"]
                else "Printed in the 2026 date list, which is not marked provisional."
            )
        )
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


def _summary(provisional: bool) -> str:
    base = (
        "Rock, gem and bead show. The organiser also describes mineral, fossil and lapidary stock, "
        "but each date is the same series rather than a separate mineral or fossil fair."
    )
    if provisional:
        return base + " This 2027 date is marked provisional on their site."
    return base


def _next_show_block(lines: list[str]) -> dict:
    start = next((i for i, line in enumerate(lines) if re.search(r"next show", line, re.I)), None)
    end = next((i for i, line in enumerate(lines) if re.search(r"2026\s+dates", line, re.I)), None)
    block = lines[start:end] if start is not None and end is not None and end > start else []
    text = " ".join(block)
    price = None
    price_match = re.search(r"Admission\s+£\s*(\d+)", text, re.I)
    if price_match:
        price = int(price_match.group(1))
    saturday = sunday = None
    for line in block:
        if re.search(r"saturday", line, re.I):
            found = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*(?:to|–|—|-)\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", line, re.I)
            if found:
                saturday = clock_range(found.group(1))
        if re.search(r"sunday", line, re.I):
            found = re.search(r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)?\s*(?:to|–|—|-)\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)?)", line, re.I)
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
        "postcode": normalise_postcode(text),
        "price": price,
        "times": times,
        "times_notes": notes,
        "entry_notes": entry_notes,
        "parking": any(re.search(r"free parking", line, re.I) for line in block),
    }


def _date_rows(lines: list[str]) -> list[dict]:
    section = None
    events = []
    for line in lines:
        if re.search(r"2026\s+dates", line, re.I):
            section = 2026
            continue
        if re.search(r"provisional\s+2027", line, re.I):
            section = 2027
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
        parsed["provisional"] = section == 2027
        events.append(parsed)
    return events


def _attach_target(events: list[dict], postcode: str | None, today: date) -> dict | None:
    if not postcode:
        return None
    dated = []
    for event in events:
        if event.get("postcode") != postcode:
            continue
        try:
            start = date.fromisoformat(event["start"])
        except ValueError:
            continue
        if start >= today:
            dated.append((start, event))
    if not dated:
        return None
    dated.sort(key=lambda item: item[0])
    return dated[0][1]


def _phone(html: str) -> str | None:
    match = re.search(r"\b(07\d{9})\b", html)
    if not match:
        return None
    digits = match.group(1)
    return f"{digits[:5]} {digits[5:]}"
