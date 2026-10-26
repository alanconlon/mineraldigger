"""Parser tests. Fixture HTML is reduced from the organiser pages checked on 25 October 2026.

If a full page was downloaded to /tmp/md-sources, the same expectations are run against it.
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
from parsers.rockexchange import parse_rockexchange  # noqa: E402
from parsers.rockngem import parse_rockngem  # noqa: E402
from parsers.smls import parse_smls  # noqa: E402
from refresh import rows_from_fixtures  # noqa: E402

TODAY = date(2026, 10, 25)
FIXTURES = ROOT / "fixtures"
LIVE = Path("/tmp/md-sources")


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

    def test_nature_does_not_invent_an_undated_march(self):
        home = (FIXTURES / "nature-home.html").read_text(encoding="utf-8")
        only_home = parse_nature(home, "", today=TODAY)
        self.assertEqual([row["start"] for row in only_home], ["2026-10-17"])
        self.assertEqual(only_home[0]["entry_adult_gbp"], 5)
        both = parse_nature(home, (FIXTURES / "nature-exhibitors.html").read_text(encoding="utf-8"), today=TODAY)
        self.assertEqual([row["start"] for row in both], ["2026-10-17", "2027-03-13", "2027-10-16"])
        march = both[1]
        self.assertEqual(march["entry_kind"], "unknown")
        self.assertIsNone(march["times_summary"])
        self.assertNotIn("Jubilee", march["venue_name"])
        self.assertEqual(both[0]["organiser_email"], "info@natureunearthed.co.uk")

    def test_oxford_dedupes_and_is_free(self):
        rows = parse_oxford((FIXTURES / "oxford.html").read_text(encoding="utf-8"), today=TODAY)
        self.assertEqual([row["start"] for row in rows], ["2027-03-21", "2027-05-23", "2027-07-25", "2026-11-29"])
        self.assertTrue(all(row["entry_kind"] == "free" for row in rows))
        self.assertTrue(all(row["end"] == row["start"] for row in rows))
        self.assertEqual(rows[0]["postcode"], "OX5 1AB")
        self.assertEqual(rows[0]["dealers"], "30+")
        self.assertIn("10:00 to 16:00", rows[0]["times_summary"])

    def test_bakewell_both_years(self):
        rows = parse_rockexchange((FIXTURES / "rockexchange.html").read_text(encoding="utf-8"), today=TODAY)
        self.assertEqual([(row["start"], row["end"]) for row in rows], [("2026-10-10", "2026-10-11"), ("2027-10-09", "2027-10-10")])
        self.assertEqual(rows[1]["entry_adult_gbp"], 3)
        self.assertIn("£5 for both days", rows[1]["entry_notes"])
        self.assertIn("Saturday 10:00 to 17:00", rows[0]["times_summary"])
        self.assertEqual(rows[0]["dealers"], "70+")
        self.assertEqual(rows[0]["organiser_phone"], "01433 620304")

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
        sussex = next(show for show in shows if show["organiser"]["id"] == "smls")
        self.assertEqual(sussex["venue"]["postcode"], "RH16 1LT")
        self.assertEqual(sussex["venue"]["street"], "Harlands Road")
        self.assertIn("college contact page", sussex["source"]["notes"])


def json_blob(shows: list[dict]) -> str:
    import json

    return json.dumps(shows)


class LiveHtmlTests(unittest.TestCase):
    def test_downloaded_rockngem(self):
        path = LIVE / "rockngem.html"
        if not path.exists():
            self.skipTest("no download")
        rows = parse_rockngem(path.read_text(encoding="utf-8", errors="replace"), today=TODAY)
        self.assertEqual(len(rows), 30)
        self.assertEqual(sum(row["provisional"] for row in rows), 27)
        kempton = next(row for row in rows if row["start"] == "2026-10-31")
        self.assertEqual(kempton["entry_adult_gbp"], 6)

    def test_downloaded_independents(self):
        if not (LIVE / "oxford.html").exists():
            self.skipTest("no download")
        oxford = parse_oxford((LIVE / "oxford.html").read_text(encoding="utf-8", errors="replace"), today=TODAY)
        self.assertEqual(sorted(row["start"] for row in oxford), ["2026-11-29", "2027-03-21", "2027-05-23", "2027-07-25"])
        nature = parse_nature(
            (LIVE / "nature.html").read_text(encoding="utf-8", errors="replace"),
            (LIVE / "nature-ex.html").read_text(encoding="utf-8", errors="replace"),
            today=TODAY,
        )
        self.assertEqual([row["start"] for row in nature], ["2026-10-17", "2027-03-13", "2027-10-16"])
        bakewell = parse_rockexchange((LIVE / "bakewell.html").read_text(encoding="utf-8", errors="replace"), today=TODAY)
        self.assertEqual([row["start"] for row in bakewell], ["2026-10-10", "2027-10-09"])
        smls = parse_smls((LIVE / "smls.html").read_text(encoding="utf-8", errors="replace"), today=TODAY)
        self.assertEqual(smls[0]["start"], "2026-11-14")
        self.assertTrue(smls[0]["year_inferred"])
        hants = parse_hampshire((LIVE / "hants.html").read_text(encoding="utf-8", errors="replace"), today=TODAY)
        self.assertEqual(hants[0]["start"], "2026-09-19")
        self.assertEqual(hants[0]["entry_adult_gbp"], 2)


if __name__ == "__main__":
    unittest.main()
