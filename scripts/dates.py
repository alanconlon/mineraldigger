"""Date and clock parsing for organiser pages."""

import re
from datetime import date, timedelta

MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

DAY = r"\d{1,2}(?:st|nd|rd|th)?"
MON = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
PC_RE = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?)\s*(\d[A-Z]{2})\b", re.I)
RANGE_SPLIT = re.compile(r"\s*(?:to|–|—|-)\s*", re.I)


def month_num(token: str) -> int | None:
    if not token:
        return None
    return MONTHS.get(token[:3].lower())


def day_num(token: str) -> int:
    return int(re.match(r"\d{1,2}", token).group(0))


def normalise_postcode(value: str) -> str | None:
    match = PC_RE.search(value or "")
    if not match:
        return None
    return f"{match.group(1).upper()} {match.group(2).upper()}"


def strip_postcode(value: str) -> tuple[str, str | None]:
    match = PC_RE.search(value or "")
    if not match:
        return re.sub(r"\s+", " ", value).strip(" .,"), None
    postcode = f"{match.group(1).upper()} {match.group(2).upper()}"
    rest = (value[: match.start()] + " " + value[match.end() :]).strip(" .,")
    rest = re.sub(r"\s+", " ", rest).strip(" .,")
    return rest, postcode


def iso(year: int, month: int, day: int) -> str:
    return date(year, month, day).isoformat()


def parse_show_span(line: str, year: int) -> dict | None:
    """Parse a Rockngem-style date line. Returns start, end, and the venue rest."""
    cross = re.compile(
        rf"^(?P<d1>{DAY})\s+(?P<m1>{MON})\s*(?:&|and)?\s*(?P<d2>{DAY})\s+(?P<m2>{MON})\s+(?P<rest>.+)$",
        re.I,
    )
    same = re.compile(
        rf"^(?P<d1>{DAY})\s*(?:&|and)\s*(?P<d2>{DAY})\s+(?P<m>{MON})\s+(?P<rest>.+)$",
        re.I,
    )
    single = re.compile(rf"^(?P<d1>{DAY})\s+(?P<m>{MON})\s+(?P<rest>.+)$", re.I)

    match = cross.match(line) or same.match(line) or single.match(line)
    if not match:
        return None
    parts = match.groupdict()
    if "m1" in parts and parts.get("m1"):
        m1 = month_num(parts["m1"])
        m2 = month_num(parts["m2"])
        if not m1 or not m2:
            return None
        end_year = year + 1 if m2 < m1 else year
        start = iso(year, m1, day_num(parts["d1"]))
        end = iso(end_year, m2, day_num(parts["d2"]))
    elif parts.get("m") and parts.get("d2"):
        month = month_num(parts["m"])
        if not month:
            return None
        d1 = day_num(parts["d1"])
        d2 = day_num(parts["d2"])
        start = iso(year, month, d1)
        end = iso(year, month, d2)
    else:
        month = month_num(parts["m"])
        if not month:
            return None
        start = iso(year, month, day_num(parts["d1"]))
        end = start
    venue, postcode = strip_postcode(parts["rest"])
    if not venue:
        return None
    return {"start": start, "end": end, "venue_name": tidy_venue(venue), "postcode": postcode}


def tidy_venue(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip(" .,")
    bits = name.split(" ")
    if len(bits) >= 3 and bits[0].lower() == bits[-1].lower():
        name = " ".join(bits[:-1])
    return name


def clock(token: str, role: str) -> str | None:
    """Normalise a time token to HH:MM. role is 'start' or 'end'."""
    raw = token.strip().lower().strip(".,;").replace(".", ":")
    match = re.match(r"^(\d{1,2})(?::(\d{2}))?\s*(am|pm)?$", raw)
    if not match:
        return None
    hour = int(match.group(1))
    minute = int(match.group(2) or 0)
    meridiem = match.group(3)
    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    elif not meridiem:
        if role == "end" and hour <= 7:
            hour += 12
        elif role == "start" and hour <= 7:
            hour += 12
    if hour > 23 or minute > 59:
        return None
    return f"{hour:02d}:{minute:02d}"


def clock_range(fragment: str) -> str | None:
    parts = [p for p in RANGE_SPLIT.split(fragment.strip()) if p]
    if len(parts) != 2:
        return None
    start = clock(parts[0], "start")
    end = clock(parts[1], "end")
    if not start or not end:
        return None
    return f"{start} to {end}"


def infer_weekday_date(weekday: str, month: int, day: int, today: date) -> date | None:
    """Pick the Saturday (or other weekday) matching a day/month near today.

    Used only when the organiser prints the weekday and the day/month, and
    omits the year. Returns nothing if no candidate sits in a short window.
    """
    want = weekday.lower()
    candidates = []
    for year in range(today.year - 1, today.year + 3):
        try:
            found = date(year, month, day)
        except ValueError:
            continue
        if found.strftime("%A").lower() == want:
            candidates.append(found)
    earliest = today - timedelta(days=40)
    latest = today + timedelta(days=400)
    fresh = [item for item in candidates if earliest <= item <= latest]
    return fresh[0] if fresh else None
