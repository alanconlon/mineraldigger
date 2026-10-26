"""Hampshire Mineral & Fossil Show: https://sotonminfoss.org.uk/smfsshow.htm"""

import re
from datetime import date

SOURCE = "https://sotonminfoss.org.uk/smfsshow.htm"
TYPES = ["mineral", "fossil"]


def parse_hampshire(html: str, today: date | None = None, retrieved: str | None = None) -> list[dict]:
    today = today or date.today()
    retrieved = retrieved or today.isoformat()
    from htmltext import html_to_text

    text = html_to_text(html)
    match = re.search(
        r"(\d{1,2})(?:st|nd|rd|th)?\s+September\s+(20\d\d)",
        text,
        re.I,
    )
    if not match:
        return []
    start = date(int(match.group(2)), 9, int(match.group(1)))
    times = None
    hours = re.search(
        r"from\s+(\d{1,2}[.:]\d{2})\s*(?:to|–|—|-)\s*(\d{1,2}[.:]\d{2})",
        text,
        re.I,
    )
    if hours:
        from dates import clock

        open_at = clock(hours.group(1), "start")
        close_at = clock(hours.group(2), "end")
        if open_at and close_at:
            times = f"Saturday {open_at} to {close_at}."
    price = None
    adult = re.search(r"Adults:\s*£\s*(\d+)", text, re.I)
    if adult:
        price = int(adult.group(1))
    notes = []
    child = re.search(r"children\s*\(5 to 14\):\s*£\s*(\d+)", text, re.I)
    if child:
        notes.append(f"Accompanied children aged 5 to 14: £{int(child.group(1))}.")
    if re.search(r"cash", text, re.I):
        notes.append("Pay cash at the door. No pre-booking.")
    satnav = None
    sat = re.search(r"sat\.?\s*nav\.?\s*use\s+([A-Z]{1,2}\d[A-Z\d]?\s*\d[A-Z]{2})", text, re.I)
    if sat:
        from dates import normalise_postcode

        satnav = normalise_postcode(sat.group(1))
    source_notes = "Date, venue and door price are on the society show page."
    if satnav:
        source_notes += f" The page also gives satnav postcode {satnav}."
    street = "Romsey Road" if re.search(r"Romsey Road", text, re.I) else None
    postcode = "SO16 8FA" if re.search(r"SO16\s*8FA", text, re.I) else None
    return [
        {
            "organiser_id": "southampton-minfoss",
            "organiser_name": "Southampton Mineral & Fossil Society",
            "organiser_url": "https://sotonminfoss.org.uk/",
            "organiser_phone": None,
            "name": "Hampshire Mineral & Fossil Show",
            "types": list(TYPES),
            "start": start.isoformat(),
            "end": start.isoformat(),
            "provisional": False,
            "year_inferred": False,
            "venue_name": "Oasis Academy Lord's Hill",
            "street": street,
            "postcode": postcode,
            "times_summary": times,
            "times_notes": None,
            "entry_kind": "paid" if price else "unknown",
            "entry_adult_gbp": price,
            "entry_notes": " ".join(notes) or None,
            "dealers": None,
            "parking": "Free parking on site, next door at the rugby club, and nearby at Sainsbury's." if re.search(r"Parking is free", text, re.I) else None,
            "access_notes": "One hall, level access." if re.search(r"wheelchair accessible", text, re.I) else None,
            "source_url": SOURCE,
            "source_retrieved": retrieved,
            "source_notes": source_notes,
            "summary": "Mineral and fossil show run by the Southampton Mineral & Fossil Society.",
        }
    ]
