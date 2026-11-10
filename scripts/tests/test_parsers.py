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
        self.assertEqual(worcester["end"], "2026-11-08")
        self.assertEqual(worcester["entry_kind"], "unknown")
        self.assertIsNone(worcester["times_summary"])
        self.assertFalse(any(row["start"] == "2026-11-06" for row in rows))
        worcester_2027 = next(row for row in rows if row["start"] == "2027-11-06")
        self.assertEqual(worcester_2027["end"], "2027-11-07")
        self.assertTrue(worcester_2027["provisional"])
        self.assertIn("Provisional 2027 Dates", worcester_2027["source_notes"])
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

    def test_plain_2027_dates_heading_keeps_worcester_november_in_2027(self):
        """A heading of 2027 Dates, without the word provisional, is still 2027.

        Checked against the organiser homepage on 5 November 2026. The next-show
        block is 7 and 8 November at Worcester. The 6 and 7 November Worcester
        line sits under 2027 Dates.
        """
        html = """
        <p>NEXT SHOW</p>
        <p>7th &amp; 8th November</p>
        <p>Worcester Racecourse</p>
        <p>WR1 3EJ</p>
        <p>Entry by ticket purchased on the door Admission £5, accompanying under 12s free.</p>
        <p>Free Parking as well as free tea and coffee</p>
        <p>Open: Saturday 10am to 4pm</p>
        <p>Sunday 10am to 4pm</p>
        <p>Last entry 1 hour before closing</p>
        <p>07712276041</p>
        <p>2026 Dates</p>
        <p>7th &amp; 8th November Worcester Racecourse WR1 3EJ</p>
        <p>14th &amp; 15th November Newcastle Racecourse NE3 5HP</p>
        <p>2027 Dates</p>
        <p>6th &amp; 7th November Worcester Racecourse WR1 3EJ</p>
        <p>Who's at Worcester Racecourse</p>
        """
        rows = parse_rockngem(html, today=date(2026, 11, 5), retrieved="2026-11-05")
        self.assertFalse(any(row["start"] == "2026-11-06" for row in rows))
        worcester = next(row for row in rows if row["start"] == "2026-11-07")
        self.assertEqual(worcester["end"], "2026-11-08")
        self.assertEqual(worcester["postcode"], "WR1 3EJ")
        self.assertFalse(worcester["provisional"])
        self.assertEqual(worcester["times_summary"], "Saturday 10:00 to 16:00. Sunday 10:00 to 16:00.")
        self.assertEqual(worcester["times_notes"], "Last entry one hour before closing.")
        self.assertEqual(worcester["entry_kind"], "paid")
        self.assertEqual(worcester["entry_adult_gbp"], 5)
        self.assertEqual(worcester["entry_notes"], "Pay on the door. Accompanying under 12s free.")
        self.assertEqual(worcester["parking"], "Free parking")
        self.assertIn("2026 date list", worcester["source_notes"])
        self.assertIn("next-show block", worcester["source_notes"])
        later = next(row for row in rows if row["postcode"] == "WR1 3EJ" and row["start"] == "2027-11-06")
        self.assertEqual(later["end"], "2027-11-07")
        self.assertFalse(later["provisional"])
        self.assertIsNone(later["times_summary"])
        self.assertEqual(later["entry_kind"], "unknown")
        self.assertNotIn("Provisional 2027", later["source_notes"])
        self.assertIn("Printed in the 2027 date list, which is not marked provisional.", later["source_notes"])
        self.assertNotIn("marked provisional", later["summary"])
        newcastle = next(row for row in rows if row["start"] == "2026-11-14")
        self.assertEqual(newcastle["entry_kind"], "unknown")
        self.assertIsNone(newcastle["times_summary"])
        shows = assemble(rows)
        slugs = [show["slug"] for show in shows]
        self.assertNotIn("rock-gem-and-bead-show-worcester-2026-11-06", slugs)
        published = next(show for show in shows if show["slug"] == "rock-gem-and-bead-show-worcester-2026-11-07")
        self.assertEqual(published["end"], "2026-11-08")
        self.assertEqual(published["times"]["summary"], "Saturday 10:00 to 16:00. Sunday 10:00 to 16:00.")
        self.assertEqual(published["times"]["notes"], "Last entry one hour before closing.")
        self.assertEqual(published["entry"]["kind"], "paid")
        self.assertEqual(published["entry"]["label"], "Entry £5")
        self.assertEqual(published["entry"]["adult_gbp"], 5)
        self.assertEqual(published["entry"]["notes"], "Pay on the door. Accompanying under 12s free.")
        self.assertEqual(published["parking"], "Free parking")
        self.assertEqual(published["venue"]["postcode"], "WR1 3EJ")
        self.assertFalse(published["provisional"])

    def test_next_show_without_2026_list_keeps_newcastle(self):
        """When the 2026 date list is gone, the next-show block is still a show.

        Checked against the organiser homepage on 10 November 2026. The next
        show is 14 and 15 November at Newcastle Racecourse, printed as
        Newvase Racecourse. There is no 2026 Dates heading, only 2027 Dates.
        """
        html = """
        <p>NEXT SHOW</p>
        <p>14th &amp; 15th November</p>
        <p>Newvase Racecourse</p>
        <p>NE3 5HP</p>
        <p>Entry by ticket purchased on the door Admission £5, accompanying under 12s free.</p>
        <p>Free Parking and a cafe.</p>
        <p>Open: Saturday 10am to 4.30pm</p>
        <p>Sunday 10am to 4pm</p>
        <p>Last entry 1 hour before closing</p>
        <p>07712276041</p>
        <p>2027 Dates</p>
        <p>8th &amp; 9th May Newcastle Racecourse NE3 5HP</p>
        <p>25th &amp; 26th September Newcastle Racecourse NE3 5HP</p>
        <p>Who's at Newcastle Racecourse</p>
        """
        rows = parse_rockngem(html, today=date(2026, 11, 10), retrieved="2026-11-10")
        newcastle = next(row for row in rows if row["start"] == "2026-11-14")
        self.assertEqual(newcastle["end"], "2026-11-15")
        self.assertEqual(newcastle["venue_name"], "Newcastle Racecourse")
        self.assertEqual(newcastle["postcode"], "NE3 5HP")
        self.assertFalse(newcastle["provisional"])
        self.assertEqual(newcastle["times_summary"], "Saturday 10:00 to 16:30. Sunday 10:00 to 16:00.")
        self.assertEqual(newcastle["times_notes"], "Last entry one hour before closing.")
        self.assertEqual(newcastle["entry_kind"], "paid")
        self.assertEqual(newcastle["entry_adult_gbp"], 5)
        self.assertEqual(newcastle["entry_notes"], "Pay on the door. Accompanying under 12s free.")
        self.assertEqual(newcastle["parking"], "Free parking")
        self.assertIn("next-show block", newcastle["source_notes"])
        self.assertNotIn("2026 date list", newcastle["source_notes"])
        self.assertFalse(any("Newvase" in (row["venue_name"] or "") for row in rows))
        later = [row for row in rows if row["postcode"] == "NE3 5HP" and row["start"].startswith("2027-")]
        self.assertEqual([row["start"] for row in later], ["2027-05-08", "2027-09-25"])
        self.assertTrue(all(row["entry_kind"] == "unknown" for row in later))
        self.assertTrue(all(row["times_summary"] is None for row in later))
        shows = assemble(rows)
        published = next(
            show for show in shows if show["slug"] == "rock-gem-and-bead-show-newcastle-upon-tyne-2026-11-14"
        )
        self.assertEqual(published["venue"]["name"], "Newcastle Racecourse")
        self.assertEqual(published["times"]["summary"], "Saturday 10:00 to 16:30. Sunday 10:00 to 16:00.")
        self.assertEqual(published["entry"]["adult_gbp"], 5)

    def test_named_weekend_keeps_its_price_on_the_sunday(self):
        """The next-show block names 7 and 8 November at Worcester.

        Checked on the homepage on 8 November 2026, the Sunday of that weekend.
        The same postcode is also printed for 23 and 24 January 2027. The £5
        door price and the opening times belong to the November weekend.
        """
        html = """
        <p>NEXT SHOW</p>
        <p>7th &amp; 8th November</p>
        <p>Worcester Racecourse</p>
        <p>WR1 3EJ</p>
        <p>Entry by ticket purchased on the door Admission £5, accompanying under 12s free.</p>
        <p>Free Parking as well as free tea and coffee</p>
        <p>Open: Saturday 10am to 4pm</p>
        <p>Sunday 10am to 4pm</p>
        <p>Last entry 1 hour before closing</p>
        <p>2026 Dates</p>
        <p>7th &amp; 8th November Worcester Racecourse WR1 3EJ</p>
        <p>2027 Dates</p>
        <p>23rd &amp; 24th January Worcester Racecourse WR1 3EJ</p>
        <p>Who's at Worcester Racecourse</p>
        """
        rows = parse_rockngem(html, today=date(2026, 11, 8), retrieved="2026-11-08")
        worcester = next(row for row in rows if row["start"] == "2026-11-07")
        self.assertEqual(worcester["end"], "2026-11-08")
        self.assertEqual(worcester["entry_adult_gbp"], 5)
        self.assertEqual(worcester["times_summary"], "Saturday 10:00 to 16:00. Sunday 10:00 to 16:00.")
        later = next(row for row in rows if row["start"] == "2027-01-23")
        self.assertIsNone(later["times_summary"])
        self.assertEqual(later["entry_kind"], "unknown")
        self.assertIsNone(later["entry_adult_gbp"])

    def test_westpoint_exeter_is_geocoded_and_not_given_another_weekends_price(self):
        """15 and 16 November 2025 at Westpoint Arena was on the homepage.

        The Internet Archive copy from 5 November 2025 prints that line under
        2025 Dates, and again above the list. The next-show block prices
        Kempton. Westpoint does not repeat a price or opening times. EX5 1DJ
        has to be in venues.json or assemble refuses the whole source.
        """
        html = """
        <p>NEXT SHOW</p>
        <p>8th &amp; 9th November</p>
        <p>Kempton Park Racecourse TW16 5AQ</p>
        <p>Entry by ticket purchased on the door Admission £6, accompanying under 12s free.</p>
        <p>Free Parking and a cafe</p>
        <p>Open: Saturday 10am to 5pm</p>
        <p>Sunday 10am to 4pm</p>
        <p>Last entry 1 hour before closing</p>
        <p>15th &amp; 16th November Westpoint Arena EX5 1DJ</p>
        <p>2025 Dates</p>
        <p>8th &amp; 9th November Kempton Park Racecourse TW16 5AQ</p>
        <p>15th &amp; 16th November Westpoint Arena EX5 1DJ</p>
        <p>2026 Dates</p>
        <p>Who's at Kempton Park Racecourse</p>
        """
        rows = parse_rockngem(html, today=date(2025, 11, 5), retrieved="2025-11-05")
        westpoint = next(row for row in rows if row["postcode"] == "EX5 1DJ")
        self.assertEqual(westpoint["start"], "2025-11-15")
        self.assertEqual(westpoint["end"], "2025-11-16")
        self.assertEqual(westpoint["venue_name"], "Westpoint Arena")
        self.assertEqual(westpoint["entry_kind"], "unknown")
        self.assertIsNone(westpoint["entry_adult_gbp"])
        self.assertIsNone(westpoint["times_summary"])
        self.assertEqual(westpoint["source_url"], "https://www.rockngem.co/")
        self.assertEqual(westpoint["organiser_url"], "https://www.rockngem.co/")
        kempton = next(row for row in rows if row["start"] == "2025-11-08")
        self.assertEqual(kempton["entry_adult_gbp"], 6)
        self.assertIn("Saturday 10:00 to 17:00", kempton["times_summary"])
        shows = assemble(rows)
        published = next(show for show in shows if show["venue"]["postcode"] == "EX5 1DJ")
        self.assertEqual(published["slug"], "rock-gem-and-bead-show-exeter-2025-11-15")
        self.assertEqual(published["venue"]["name"], "Westpoint Arena")
        self.assertEqual(published["venue"]["town"], "Exeter")
        self.assertEqual(published["venue"]["county"], "Devon")
        self.assertEqual(published["venue"]["nation"], "England")
        self.assertEqual(published["venue"]["lat"], 50.711371)
        self.assertEqual(published["venue"]["lng"], -3.439555)
        self.assertIn("Sowton", published["venue"]["place_note"])
        self.assertEqual(published["entry"]["kind"], "unknown")
        self.assertEqual(published["entry"]["label"], "Check with organiser")
        self.assertIsNone(published["times"]["summary"])
        self.assertEqual(published["source"]["url"], "https://www.rockngem.co/")
        self.assertNotIn("\u2014", published["venue"]["place_note"])
        self.assertNotIn("!", published["venue"]["place_note"])

    def test_a_later_westpoint_weekend_does_not_inherit_the_named_price(self):
        """A door price stays on the weekend named in the next-show block.

        The second Westpoint line is only here so a later copy cannot pick up
        the price. rockngem.co did not print a 2026 Westpoint date on 8 November 2026.
        """
        html = """
        <p>NEXT SHOW</p>
        <p>15th &amp; 16th November</p>
        <p>Westpoint Arena</p>
        <p>EX5 1DJ</p>
        <p>Entry by ticket purchased on the door Admission £5, accompanying under 12s free.</p>
        <p>Open: Saturday 10am to 4pm</p>
        <p>Sunday 10am to 4pm</p>
        <p>2025 Dates</p>
        <p>15th &amp; 16th November Westpoint Arena EX5 1DJ</p>
        <p>2026 Dates</p>
        <p>15th &amp; 16th November Westpoint Arena EX5 1DJ</p>
        <p>Who's at Westpoint Arena</p>
        """
        for today in (date(2025, 11, 16), date(2025, 11, 17)):
            rows = parse_rockngem(html, today=today, retrieved="2025-11-16")
            current = next(row for row in rows if row["start"] == "2025-11-15")
            later = next(row for row in rows if row["start"] == "2026-11-15")
            self.assertEqual(current["entry_adult_gbp"], 5, today)
            self.assertEqual(current["times_summary"], "Saturday 10:00 to 16:00. Sunday 10:00 to 16:00.")
            self.assertEqual(later["entry_kind"], "unknown", today)
            self.assertIsNone(later["entry_adult_gbp"], today)
            self.assertIsNone(later["times_summary"], today)

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
