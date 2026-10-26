"""Nature Unearthed / South of England Mineral Show.

Homepage: https://www.natureunearthed.co.uk/
Dates confirmed on: https://www.natureunearthed.co.uk/pages/exhibitor-information
"""

import re
from datetime import date

from dates import month_num

HOME = "https://www.natureunearthed.co.uk/"
EXHIBITORS = "https://www.natureunearthed.co.uk/pages/exhibitor-information"
TYPES = ["rock", "gem", "mineral", "fossil", "bead"]

DATED = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s*(?:/|and)\s*(\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(20\d\d)",
    re.I,
)


def parse_nature(home_html: str, exhibitors_html: str = "", today: date | None = None, retrieved: str | None = None) -> list[dict]:
    today = today or date.today()
    retrieved = retrieved or today.isoformat()
    from htmltext import html_to_text

    home = html_to_text(home_html or "")
    extra = html_to_text(exhibitors_html or "")
    combined = home + "\n" + extra
    found = {}
    for blob in (extra, home):
        for match in DATED.finditer(blob):
            day1 = int(match.group(1))
            day2 = int(match.group(2))
            month = month_num(match.group(3))
            year = int(match.group(4))
            if not month:
                continue
            start = date(year, month, day1).isoformat()
            end = date(year, month, day2).isoformat()
            found.setdefault(start, end)

    email = None
    mail = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", combined)
    if mail and not mail.group(0).lower().endswith((".png", ".jpg", ".svg")):
        email = mail.group(0)

    october_price = bool(re.search(r"Adult entries are £\s*5", home, re.I))
    october_times = bool(re.search(r"10\s*am to 4\s*pm both Saturday and Sunday", home, re.I))
    hall = "Queen's Jubilee Hall" in home or "Queen’s Jubilee Hall" in home
    gates = "North Gate" in home and "Green Gate" in home
    postcode = "RH17 6TL" if re.search(r"RH17\s*6TL", combined, re.I) else None

    rows = []
    for start in sorted(found):
        end = found[start]
        is_published_weekend = start == "2026-10-17"
        venue = "South of England Showground"
        if is_published_weekend and hall:
            venue = "Queen's Jubilee Hall, South of England Showground"
        notes = "Confirmed date on the Nature Unearthed site."
        if is_published_weekend:
            notes = "Date, door price and opening times are on the show page for this October weekend."
        else:
            notes = (
                "Date confirmed on the exhibitor information page. "
                "Door price and opening times are not repeated for this weekend."
            )
        access = None
        if is_published_weekend and gates:
            access = "The show page says to use the North Gate and then the Green Gate."
        rows.append(
            {
                "organiser_id": "nature-unearthed",
                "organiser_name": "Nature Unearthed",
                "organiser_url": HOME,
                "organiser_phone": None,
                "organiser_email": email,
                "name": "South of England Mineral Show",
                "types": list(TYPES),
                "start": start,
                "end": end,
                "provisional": False,
                "year_inferred": False,
                "venue_name": venue,
                "street": None,
                "postcode": postcode,
                "times_summary": "Saturday 10:00 to 16:00. Sunday 10:00 to 16:00." if is_published_weekend and october_times else None,
                "times_notes": None,
                "entry_kind": "paid" if is_published_weekend and october_price else "unknown",
                "entry_adult_gbp": 5 if is_published_weekend and october_price else None,
                "entry_notes": "On the door, or buy a ticket on the organiser site. Children under 5 go free with an adult." if is_published_weekend and october_price else None,
                "dealers": None,
                "parking": "Free parking" if is_published_weekend and re.search(r"free parking", home, re.I) else None,
                "access_notes": access,
                "source_url": EXHIBITORS if not is_published_weekend else HOME,
                "source_retrieved": retrieved,
                "source_notes": notes,
                "summary": "Mineral show at the South of England Showground, with fossils, gems, beads and rocks.",
            }
        )
    return rows
