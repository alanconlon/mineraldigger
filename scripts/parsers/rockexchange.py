"""Bakewell Rock Exchange: https://rockexchange.uk/"""

import re
from datetime import date

SOURCE = "https://rockexchange.uk/"
TYPES = ["rock", "gem", "mineral", "fossil"]


def parse_rockexchange(html: str, today: date | None = None, retrieved: str | None = None) -> list[dict]:
    today = today or date.today()
    retrieved = retrieved or today.isoformat()
    from htmltext import html_to_text

    text = html_to_text(html)
    spans = []
    primary = re.search(
        r"(\d{1,2})(?:st|nd|rd|th)?\s*&\s*(\d{1,2})(?:st|nd|rd|th)?\s+October\s+(20\d\d)",
        text,
        re.I,
    )
    if primary:
        year = int(primary.group(3))
        spans.append((date(year, 10, int(primary.group(1))).isoformat(), date(year, 10, int(primary.group(2))).isoformat()))
    later = re.search(
        r"dates for\s+(20\d\d)\s+(\d{1,2})(?:st|nd|rd|th)?\s*&\s*(\d{1,2})(?:st|nd|rd|th)?\s+October",
        text,
        re.I,
    )
    if later:
        year = int(later.group(1))
        spans.append((date(year, 10, int(later.group(2))).isoformat(), date(year, 10, int(later.group(3))).isoformat()))

    times = None
    times_match = re.search(
        r"Saturday\s+([\d.:]+\s*(?:am|pm)?)\s*(?:to|–|—|-)\s*([\d.:]+\s*(?:am|pm)?)\s+and\s+Sunday\s+([\d.:]+\s*(?:am|pm)?)\s*(?:to|–|—|-)\s*([\d.:]+\s*(?:am|pm)?)",
        text,
        re.I,
    )
    if times_match:
        from dates import clock

        sat_s = clock(times_match.group(1), "start")
        sat_e = clock(times_match.group(2), "end")
        sun_s = clock(times_match.group(3), "start")
        sun_e = clock(times_match.group(4), "end")
        if sat_s and sat_e and sun_s and sun_e:
            times = f"Saturday {sat_s} to {sat_e}. Sunday {sun_s} to {sun_e}."
    price = None
    price_match = re.search(r"Admission:\s*£\s*(\d+)", text, re.I)
    if price_match:
        price = int(price_match.group(1))
    notes = []
    both = re.search(r"£\s*(\d+)\s*(?:\.00)?\s*for both days", text, re.I)
    if both:
        notes.append(f"£{int(both.group(1))} for both days.")
    early = re.search(r"£\s*(\d+)\s+early entry", text, re.I)
    if early:
        notes.append(f"Saturday early entry from 09:00 is £{int(early.group(1))} and covers both days.")
    if re.search(r"children free", text, re.I):
        notes.append("Accompanied children free.")
    dealers = "70+" if re.search(r"more than 70", text, re.I) else None
    parking = "Free parking" if re.search(r"free parking", text, re.I) else None
    access = "Disabled access." if re.search(r"disabled access", text, re.I) else None
    phone = None
    phone_match = re.search(r"\b(0\d{4}\s*\d{6})\b", text)
    if phone_match:
        digits = re.sub(r"\s+", "", phone_match.group(1))
        if not set(digits) <= {"0"}:
            phone = f"{digits[:5]} {digits[5:]}"
    postcode = "DE45 1JA" if re.search(r"DE45\s*1JA", text, re.I) else None

    rows = []
    for start, end in spans:
        # rockexchange.uk is the only known society site. Its certificate expired
        # in 2021 and the host returns HTTP 500. There is no replacement URL.
        # A weekend that has not ended does not publish that address. The phone stays.
        publish_url = None if end >= today.isoformat() else SOURCE
        rows.append(
            {
                "organiser_id": "bakewell-rock-exchange",
                "organiser_name": "Peak Lapidary and Mineral Society",
                "organiser_url": publish_url,
                "organiser_phone": phone,
                "name": "Bakewell Rock Exchange",
                "types": list(TYPES),
                "start": start,
                "end": end,
                "provisional": False,
                "year_inferred": False,
                "venue_name": "Lady Manners School",
                "street": None,
                "postcode": postcode,
                "times_summary": times,
                "times_notes": None,
                "entry_kind": "paid" if price else "unknown",
                "entry_adult_gbp": price,
                "entry_notes": " ".join(notes) or None,
                "dealers": dealers,
                "parking": parking,
                "access_notes": access,
                "source_url": publish_url,
                "source_retrieved": retrieved,
                "source_notes": "Both weekends, the door price and the opening times are on the one show page.",
                "summary": "Rocks, minerals, fossils and gemstones. Organised by the Peak Lapidary and Mineral Society.",
            }
        )
    return rows
