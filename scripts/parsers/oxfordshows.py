"""Oxford Mineral & Fossil Shows: https://oxfordshows.co.uk/"""

import re
from datetime import date

from dates import MONTHS

SOURCE = "https://oxfordshows.co.uk/"
TYPES = ["rock", "gem", "mineral", "fossil"]
TOKEN = re.compile(r"\b(\d{2})-([A-Z]{3})-(\d{4})\b")


def parse_oxford(html: str, today: date | None = None, retrieved: str | None = None) -> list[dict]:
    today = today or date.today()
    retrieved = retrieved or today.isoformat()
    from htmltext import html_to_text

    text = html_to_text(html)
    dates = []
    seen = set()
    for day, mon, year in TOKEN.findall(html):
        month = MONTHS.get(mon.lower())
        if not month:
            continue
        start = date(int(year), month, int(day)).isoformat()
        if start in seen:
            continue
        seen.add(start)
        dates.append(start)
    if not dates:
        return []

    free = bool(re.search(r"free entrance", text, re.I))
    times = None
    times_notes = None
    if re.search(r"Sunday\s+10\s*am\s+until\s+4\s*pm", text, re.I) or re.search(r"10:00\s*AM", html):
        times = "Sunday 10:00 to 16:00."
    if re.search(r"no public entry before 10", text, re.I) or re.search(r"Doors open to public at 10", text, re.I):
        times_notes = "No public entry before 10:00, while exhibitors set up."
    dealers = "30+" if re.search(r"over 30 exhibitors", text, re.I) else None
    parking = None
    if re.search(r"free parking", text, re.I):
        parking = "Free parking if you enter your vehicle registration on the keypad at the entrance."
    phone = None
    phone_match = re.search(r"\b(07\d{3}\s*\d{6})\b", text)
    if phone_match:
        digits = re.sub(r"\s+", "", phone_match.group(1))
        phone = f"{digits[:5]} {digits[5:]}"
    email = None
    mail = re.search(r"info@oxfordshows\.co\.uk", text, re.I)
    if mail:
        email = "info@oxfordshows.co.uk"
    postcode = "OX5 1AB" if re.search(r"OX5\s*1AB", text, re.I) else None
    street = "Oxford Road" if re.search(r"Oxford Road", text, re.I) else None

    rows = []
    for start in dates:
        rows.append(
            {
                "organiser_id": "oxford-shows",
                "organiser_name": "Oxford Shows",
                "organiser_url": SOURCE,
                "organiser_phone": phone,
                "organiser_email": email,
                "name": "Oxford Mineral & Fossil Show",
                "types": list(TYPES),
                "start": start,
                "end": start,
                "provisional": False,
                "year_inferred": False,
                "venue_name": "Exeter Hall",
                "street": street,
                "postcode": postcode,
                "times_summary": times,
                "times_notes": times_notes,
                "entry_kind": "free" if free else "unknown",
                "entry_adult_gbp": 0 if free else None,
                "entry_notes": "Free entrance." if free else None,
                "dealers": dealers,
                "parking": parking,
                "access_notes": None,
                "source_url": SOURCE,
                "source_retrieved": retrieved,
                "source_notes": "Date card and entry conditions are on oxfordshows.co.uk.",
                "summary": "Mineral and fossil show for collectors. The organiser also lists gems and rocks. Free entry.",
            }
        )
    return rows
