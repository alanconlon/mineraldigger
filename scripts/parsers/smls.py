"""Sussex Mineral and Lapidary Society show page: https://www.smls.online/show

The page prints Saturday 14th November and does not print a year. The year is
taken only when that weekday matches, close to the retrieval date.
The college street and postcode are not on the show page. They are added from
the college's own contact page in data/venue-supplements.json.
"""

import re
from datetime import date

from dates import clock, infer_weekday_date

SOURCE = "https://www.smls.online/show"
TYPES = ["gem", "mineral", "fossil"]


def parse_smls(html: str, today: date | None = None, retrieved: str | None = None) -> list[dict]:
    today = today or date.today()
    retrieved = retrieved or today.isoformat()
    from htmltext import html_to_text

    text = html_to_text(html)
    explicit = re.search(
        r"Saturday\s+(\d{1,2})(?:st|nd|rd|th)?\s+November\s+(20\d\d)",
        text,
        re.I,
    )
    inferred = False
    if explicit:
        start = date(int(explicit.group(2)), 11, int(explicit.group(1)))
    else:
        loose = re.search(r"Saturday\s+(\d{1,2})(?:st|nd|rd|th)?\s+November", text, re.I)
        if not loose:
            return []
        start = infer_weekday_date("Saturday", 11, int(loose.group(1)), today)
        if start is None:
            return []
        inferred = True

    public = _range_after(text, r"(\d{1,2}:\d{2}\s*(?:am|pm)?)\s*(?:to|–|—|-)\s*(\d{1,2}:\d{2}\s*(?:am|pm)?)")
    early = None
    early_match = re.search(r"Early Entry\s+(\d{1,2}:\d{2}\s*(?:am|pm)?)", text, re.I)
    if early_match:
        early = clock(early_match.group(1), "start")
    times = None
    if public:
        times = f"Saturday {public}."
    times_notes = f"Early entry from {early}." if early else None
    adult = re.search(r"Adults\s+£\s*(\d+)", text, re.I)
    price = int(adult.group(1)) if adult else None
    notes = []
    child = re.search(r"Children\s+£\s*(\d+)", text, re.I)
    if child:
        notes.append(f"Children £{int(child.group(1))}.")
    early_price = re.search(r"Early Entry\s+£\s*(\d+)", text, re.I)
    if early_price:
        notes.append(f"Early entry £{int(early_price.group(1))}.")
    dealers = "40+" if re.search(r"40\+", text) else None
    parking = "Free parking, and it fills quickly." if re.search(r"free parking", text, re.I) else None
    year_note = (
        "The show page prints Saturday "
        f"{start.day} November and does not print the year. "
        f"{start.day} {start.strftime('%B %Y')} is that Saturday, so that is the date used here."
        if inferred
        else "The year is printed on the show page."
    )
    return [
        {
            "organiser_id": "smls",
            "organiser_name": "Sussex Mineral and Lapidary Society",
            "organiser_url": SOURCE,
            "organiser_phone": None,
            "name": "Sussex Mineral, Crystal & Fossil Show",
            "types": list(TYPES),
            "start": start.isoformat(),
            "end": start.isoformat(),
            "provisional": False,
            "year_inferred": inferred,
            "venue_name": "Haywards Heath College",
            "street": None,
            "postcode": None,
            "times_summary": times,
            "times_notes": times_notes,
            "entry_kind": "paid" if price else "unknown",
            "entry_adult_gbp": price,
            "entry_notes": " ".join(notes) or None,
            "dealers": dealers,
            "parking": parking,
            "access_notes": None,
            "source_url": SOURCE,
            "source_retrieved": retrieved,
            "source_notes": year_note,
            "summary": "Mineral, fossil and gem show run by the Sussex Mineral and Lapidary Society.",
        }
    ]


def _range_after(text: str, pattern: str) -> str | None:
    match = re.search(pattern, text, re.I)
    if not match:
        return None
    from dates import clock

    start = clock(match.group(1), "start")
    end = clock(match.group(2), "end")
    if not start or not end:
        return None
    return f"{start} to {end}"
