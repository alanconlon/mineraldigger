"""Turn parser rows into the public show records."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"

TYPES = ("rock", "gem", "mineral", "fossil", "bead")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def slugify(value: str) -> str:
    text = value.lower().replace("&", " and ")
    text = text.replace("'", "").replace("’", "")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def entry_fields(row: dict) -> dict:
    kind = row.get("entry_kind") or "unknown"
    amount = row.get("entry_adult_gbp")
    if kind == "free" or amount == 0:
        return {"kind": "free", "label": "Free", "adult_gbp": 0, "notes": row.get("entry_notes")}
    if kind == "paid" and isinstance(amount, int) and amount > 0:
        return {
            "kind": "paid",
            "label": f"Entry £{amount}",
            "adult_gbp": amount,
            "notes": row.get("entry_notes"),
        }
    return {"kind": "unknown", "label": "Unknown", "adult_gbp": None, "notes": row.get("entry_notes")}


def assemble(rows: list[dict]) -> list[dict]:
    venues = load_json(DATA / "venues.json")
    supplements = load_json(DATA / "venue-supplements.json")
    shows = []
    problems = []
    for row in rows:
        venue_name = row.get("venue_name") or ""
        postcode = row.get("postcode")
        street = row.get("street")
        notes = row.get("source_notes") or ""
        extra_sources = []
        if not postcode and venue_name in supplements:
            extra = supplements[venue_name]
            postcode = extra.get("postcode")
            street = street or extra.get("street")
            if extra.get("note"):
                notes = (notes + " " + extra["note"]).strip()
            if extra.get("source_url"):
                extra_sources.append({"url": extra["source_url"], "note": extra.get("note") or ""})
        venue = venues.get(postcode or "")
        if not postcode or not venue or str(postcode).startswith("_"):
            problems.append(f"{row.get('name')} {row.get('start')} has no geocoded postcode ({postcode})")
            continue
        types = [item for item in row.get("types") or [] if item in TYPES]
        if not types:
            problems.append(f"{row.get('name')} {row.get('start')} has no type")
            continue
        ident = f"{row['organiser_id']}-{row['start']}-{postcode.replace(' ', '').lower()}"
        slug = slugify(f"{row['name']}-{venue['town']}-{row['start']}")
        entry = entry_fields(row)
        place_note = venue.get("place_note") or None
        record = {
            "id": ident,
            "slug": slug,
            "name": row["name"],
            "summary": row.get("summary") or "",
            "organiser": {
                "id": row["organiser_id"],
                "name": row["organiser_name"],
                "url": row["organiser_url"],
                "phone": row.get("organiser_phone"),
                "email": row.get("organiser_email"),
            },
            "types": types,
            "start": row["start"],
            "end": row["end"],
            "provisional": bool(row.get("provisional")),
            "year_inferred": bool(row.get("year_inferred")),
            "times": {
                "summary": row.get("times_summary"),
                "notes": row.get("times_notes"),
            },
            "entry": entry,
            "venue": {
                "name": venue_name,
                "street": street,
                "postcode": postcode,
                "town": venue["town"],
                "county": venue["county"],
                "nation": venue["nation"],
                "lat": venue["lat"],
                "lng": venue["lng"],
                "place_note": place_note,
            },
            "dealers": row.get("dealers"),
            "parking": row.get("parking"),
            "access_notes": row.get("access_notes"),
            "source": {
                "url": row["source_url"],
                "retrieved": row["source_retrieved"],
                "notes": notes,
                "also": extra_sources,
            },
        }
        shows.append(record)
    if problems:
        raise SystemExit("Could not place every parsed show:\n- " + "\n- ".join(problems))
    shows.sort(key=lambda item: (item["start"], item["name"], item["id"]))
    seen = {}
    for record in shows:
        base = record["slug"]
        count = seen.get(base, 0) + 1
        seen[base] = count
        if count > 1:
            record["slug"] = f"{base}-{count}"
    return shows
