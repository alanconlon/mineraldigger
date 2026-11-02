"""Parser tests. Fixture HTML is reduced from the organiser pages checked on 25 October 2026.

These tests read the saved fixtures and data/organiser-overrides.json. They do not fetch organiser sites.
"""

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from assemble import assemble  # noqa: E402
from parsers.hampshire import parse_hampshire  # noqa: E402
from parsers.nature_unearthed import parse_nature  # noqa: E402
from parsers.oxfordshows import parse_oxford  # noqa: E402
from overrides import apply_row_override, scrub_shows  # noqa: E402
from parsers.rockexchange import parse_rockexchange  # noqa: E402
from parsers.rockngem import parse_rockngem  # noqa: E402
from parsers.smls import parse_smls  # noqa: E402
from refresh import rows_from_fixtures  # noqa: E402

TODAY = date(2026, 10, 25)
FIXTURES = ROOT / "fixtures"
BAKEWELL_HTML = (FIXTURES / "rockexchange.html").read_text(encoding="utf-8")


def banned(value: str) -> bool:
    text = value.lower()
    needles = (
        "healing",
        "psychic",
        "tarot",
        "wellbeing",
        "mind-body",
        "mind body",
        "white light",
        "crystal spirit",
        "gumroad",
        "crystaldigger",
    )
    return any(needle in text for needle in needles) or "!" in value or "\u2014" in value


class FixtureTests(unittest.TestCase):
    def test_rockngem_counts_and_prices(self):
        rows = parse_rockngem((FIXTURES / "rockngem.html").read_text(encoding="utf-8"), today=TODAY)
        self.assertEqual(len(rows), 30)
        self.assertEqual(sum(not row["provisional"] for row in rows), 3)
        self.assertEqual(sum(row["provisional"] for row in rows), 27)
        kempton = next(row for row in rows if row["start"] == "2026-10-31")
        self.assertEqual(kempton["end"], "2026-11-01")
        self.assertEqual(kempton["entry_adult_gbp"], 6)
        self.assertEqual(kempton["postcode"], "TW16 5AQ")
        self.assertIn("Saturday 10:00 to 17:00", kempton["times_summary"])
        self.assertIn("Sunday 10:00 to 16:00", kempton["times_summary"])
        worcester = next(row for row in rows if row["start"] == "2026-11-07")
        self.assertEqual(worcester["entry_kind"], "unknown")
        self.assertIsNone(worcester["times_summary"])
        richmond = next(row for row in rows if row["start"] == "2027-07-10")
        self.assertEqual(richmond["end"], "2027-07-10")
        self.assertEqual(richmond["postcode"], "SS7 5HA")
        self.assertTrue(richmond["provisional"])
        westgate = next(row for row in rows if row["start"] == "2027-01-30")
        self.assertEqual(westgate["postcode"], "CT1 2BT")
        brock = next(row for row in rows if row["start"] == "2027-07-31")
        self.assertEqual(brock["end"], "2027-08-01")
        self.assertIn("Community Centre", brock["venue_name"])
        later_kempton = next(row for row in rows if row["start"] == "2027-02-20")
        self.assertEqual(later_kempton["entry_kind"], "unknown")
        self.assertEqual(kempton["organiser_phone"], "07712 276041")
        self.assertTrue(all(row["types"] == ["rock", "gem", "bead"] for row in rows))
        self.assertNotIn("same series", kempton["summary"])
        self.assertNotIn("fossil fair", kempton["summary"])
        self.assertIn("Minerals, fossils and lapidary stock are part of this show too.", kempton["summary"])

    def test_nature_does_not_invent_an_undated_march(self):
        home = (FIXTURES / "nature-home.html").read_text(encoding="utf-8")
        only_home = parse_nature(home, "", today=TODAY)
        self.assertEqual([row["start"] for row in only_home], ["2026-10-17"])
        self.assertEqual(only_home[0]["entry_adult_gbp"], 5)
        self.assertEqual(only_home[0]["types"], ["gem", "mineral", "fossil", "bead"])
        both = parse_nature(home, (FIXTURES / "nature-exhibitors.html").read_text(encoding="utf-8"), today=TODAY)
        self.assertEqual([row["start"] for row in both], ["2026-10-17", "2027-03-13", "2027-10-16"])
        self.assertEqual(both[0]["types"], ["gem", "mineral", "fossil", "bead"])
        self.assertEqual(both[1]["types"], ["gem", "mineral"])
        self.assertEqual(both[2]["types"], ["mineral"])
        march = both[1]
        self.assertEqual(march["entry_kind"], "unknown")
        self.assertIsNone(march["times_summary"])
        self.assertNotIn("Jubilee", march["venue_name"])
        self.assertEqual(both[0]["organiser_email"], "info@natureunearthed.co.uk")

    def test_oxford_dedupes_and_is_free(self):
        rows = parse_oxford((FIXTURES / "oxford.html").read_text(encoding="utf-8"), today=TODAY)
        self.assertEqual([row["start"] for row in rows], ["2027-03-21", "2027-05-23", "2027-07-25", "2026-11-29"])
        self.assertTrue(all(row["entry_kind"] == "free" for row in rows))
        assembled = [show for show in assemble(rows_from_fixtures(TODAY)) if show["organiser"]["id"] == "oxford-shows"]
        self.assertTrue(assembled)
        self.assertTrue(all(show["entry"]["label"] == "Free entry" for show in assembled))
        self.assertTrue(all(show["entry"]["notes"] in (None, "") for show in assembled))
        self.assertTrue(all(not show["summary"].lower().endswith("free entry.") for show in assembled))
        self.assertTrue(all("free entry" not in show["summary"].lower() for show in assembled))
        self.assertTrue(all(row["end"] == row["start"] for row in rows))
        self.assertEqual(rows[0]["postcode"], "OX5 1AB")
        self.assertEqual(rows[0]["dealers"], "30+")
        self.assertIn("10:00 to 16:00", rows[0]["times_summary"])

    def test_bakewell_both_years(self):
        rows = parse_rockexchange(BAKEWELL_HTML, today=TODAY)
        self.assertEqual([(row["start"], row["end"]) for row in rows], [("2026-10-10", "2026-10-11"), ("2027-10-09", "2027-10-10")])
        self.assertEqual(rows[1]["entry_adult_gbp"], 3)
        self.assertIn("£5 for both days", rows[1]["entry_notes"])
        self.assertIn("Saturday 10:00 to 17:00", rows[0]["times_summary"])
        self.assertEqual(rows[0]["dealers"], "70+")
        self.assertEqual(rows[0]["organiser_phone"], "01433 620304")
        self.assertEqual(rows[1]["organiser_phone"], "01433 620304")
        for day in (date(2026, 10, 1), TODAY, date(2028, 1, 1)):
            parsed = parse_rockexchange(BAKEWELL_HTML, today=day)
            self.assertEqual(len(parsed), 2)
            for row in parsed:
                self.assertIsNone(row["organiser_url"])
                self.assertIsNone(row["source_url"])
                self.assertNotIn("rockexchange.uk", json_blob([row]))

    def test_bakewell_override_can_name_a_replacement_and_still_blocks_the_host(self):
        replacement = {
            "organisers": {"bakewell-rock-exchange": {"url": "https://peaklapidary.example/shows"}},
            "blocked_hosts": ["rockexchange.uk"],
        }
        rows = parse_rockexchange(BAKEWELL_HTML, today=date(2026, 10, 1), overrides=replacement)
        self.assertTrue(rows)
        self.assertTrue(all(row["organiser_url"] == "https://peaklapidary.example/shows" for row in rows))
        self.assertTrue(all(row["source_url"] is None for row in rows))
        blocked = {
            "organisers": {"bakewell-rock-exchange": {"url": "https://www.rockexchange.uk/next"}},
            "blocked_hosts": ["rockexchange.uk"],
        }
        row = apply_row_override(
            {
                "organiser_id": "bakewell-rock-exchange",
                "organiser_url": "https://rockexchange.uk/",
                "source_url": "https://rockexchange.uk/",
            },
            blocked,
        )
        self.assertIsNone(row["organiser_url"])
        self.assertIsNone(row["source_url"])
        kept = scrub_shows(
            [
                {
                    "organiser": {"id": "bakewell-rock-exchange", "url": "https://rockexchange.uk/", "phone": "01433 620304"},
                    "source": {
                        "url": "https://www.rockexchange.uk/",
                        "also": [{"url": "https://rockexchange.uk/dates"}],
                    },
                }
            ]
        )
        self.assertIsNone(kept[0]["organiser"]["url"])
        self.assertEqual(kept[0]["organiser"]["phone"], "01433 620304")
        self.assertIsNone(kept[0]["source"]["url"])
        self.assertEqual(kept[0]["source"]["also"], [])

    def test_smls_year_is_matched_not_printed(self):
        rows = parse_smls((FIXTURES / "smls.html").read_text(encoding="utf-8"), today=TODAY)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["start"], "2026-11-14")
        self.assertTrue(rows[0]["year_inferred"])
        self.assertEqual(rows[0]["entry_adult_gbp"], 5)
        self.assertIn("10:00 to 16:30", rows[0]["times_summary"])
        self.assertEqual(rows[0]["postcode"], None)
        self.assertEqual(parse_smls((FIXTURES / "smls.html").read_text(encoding="utf-8"), today=date(2028, 1, 1)), [])

    def test_hampshire(self):
        rows = parse_hampshire((FIXTURES / "hampshire.html").read_text(encoding="utf-8"), today=TODAY)
        self.assertEqual(rows[0]["start"], "2026-09-19")
        self.assertEqual(rows[0]["entry_adult_gbp"], 2)
        self.assertIn("SO16 0XN", rows[0]["source_notes"])
        self.assertIn("10:00 to 16:00", rows[0]["times_summary"])

    def test_assembled_seed_has_no_banned_copy(self):
        shows = assemble(rows_from_fixtures(TODAY))
        self.assertEqual(len(shows), 41)
        self.assertEqual(sum(show["provisional"] for show in shows), 27)
        blob = json_blob(shows)
        self.assertNotIn("\u2014", blob)
        self.assertNotIn("!", blob)
        for show in shows:
            self.assertFalse(banned(show["summary"]), show["id"])
            self.assertFalse(banned(show["name"]), show["id"])
            self.assertEqual(show["source"]["retrieved"], "2026-10-25")
        for show in shows:
            if show["entry"]["kind"] == "unknown":
                self.assertEqual(show["entry"]["label"], "Check with organiser")
            self.assertNotEqual(show["entry"]["label"], "Unknown")
        rgbs = [show for show in shows if show["organiser"]["id"] == "rockngem"]
        self.assertTrue(rgbs)
        self.assertTrue(all(show["types"] == ["rock", "gem", "bead"] for show in rgbs))
        sussex = next(show for show in shows if show["organiser"]["id"] == "smls")
        self.assertNotIn("rockexchange.uk", blob)
        for year in ("2026-10-10", "2027-10-09"):
            bakewell = next(show for show in shows if show["id"] == f"bakewell-rock-exchange-{year}-de451ja")
            self.assertIsNone(bakewell["organiser"]["url"])
            self.assertIsNone(bakewell["source"]["url"])
            self.assertEqual(bakewell["organiser"]["phone"], "01433 620304")
        self.assertEqual(sussex["venue"]["postcode"], "RH16 1LT")
        self.assertEqual(sussex["venue"]["street"], "Harlands Road")
        self.assertIn("college contact page", sussex["source"]["notes"])


def json_blob(shows: list[dict]) -> str:
    import json

    return json.dumps(shows)


if __name__ == "__main__":
    unittest.main()
