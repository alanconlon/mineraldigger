"""Refresh fetch rules and the keep-previous fallback. No live network."""

import email.message
import io
import json
import ssl
import sys
import tempfile
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import refresh  # noqa: E402
from assemble import assemble  # noqa: E402
from digest import INTERNAL_NOTE  # noqa: E402
from refresh import (  # noqa: E402
    BROWSER_UA,
    LIVE,
    UA,
    UNVERIFIED_HOST,
    added_shows,
    fetch,
    include_added,
    merge_kept,
    rows_from_fixtures,
    rows_from_live,
)

FIXTURES = ROOT / "fixtures"


class FakeResponse:
    def __init__(self, body: bytes = b"<html></html>"):
        self.headers = email.message.EmailMessage()
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class FetchHostTests(unittest.TestCase):
    def _capture(self, url):
        captured = {}

        def fake_open(request, context=None, timeout=None):
            captured["ua"] = request.get_header("User-agent")
            captured["accept"] = request.get_header("Accept")
            captured["language"] = request.get_header("Accept-language")
            captured["context"] = context
            return FakeResponse()

        with patch("refresh.urllib.request.urlopen", fake_open):
            fetch(url)
        return captured

    def test_rockexchange_uses_unverified_tls_and_browser_ua(self):
        captured = self._capture("https://rockexchange.uk/")
        self.assertEqual(captured["ua"], BROWSER_UA)
        self.assertIn("text/html", captured["accept"])
        self.assertEqual(captured["language"], "en-GB,en;q=0.9")
        context = captured["context"]
        self.assertEqual(context.verify_mode, ssl.CERT_NONE)
        self.assertFalse(context.check_hostname)

    def test_other_hosts_keep_verified_tls_and_refresh_ua(self):
        captured = self._capture("https://www.rockngem.co/")
        self.assertEqual(captured["ua"], UA)
        self.assertNotIn(UNVERIFIED_HOST, captured["ua"])
        context = captured["context"]
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)


class KeepPreviousTests(unittest.TestCase):
    def test_failed_source_is_kept_from_previous_shows(self):
        pages = {
            "https://www.rockngem.co/": (FIXTURES / "rockngem.html").read_text(encoding="utf-8"),
            "https://www.natureunearthed.co.uk/": (FIXTURES / "nature-home.html").read_text(encoding="utf-8"),
            "https://www.natureunearthed.co.uk/pages/exhibitor-information": (
                FIXTURES / "nature-exhibitors.html"
            ).read_text(encoding="utf-8"),
            "https://oxfordshows.co.uk/": (FIXTURES / "oxford.html").read_text(encoding="utf-8"),
            "https://www.smls.online/show": (FIXTURES / "smls.html").read_text(encoding="utf-8"),
            "https://sotonminfoss.org.uk/smfsshow.htm": (FIXTURES / "hampshire.html").read_text(encoding="utf-8"),
        }

        def fake_fetch(url):
            if UNVERIFIED_HOST in url:
                raise urllib.error.URLError("certificate")
            return pages[url]

        with patch("refresh.fetch", fake_fetch):
            shows, failed = rows_from_live(list(LIVE), date(2026, 10, 29))
        self.assertEqual(failed, ["bakewell-rock-exchange"])
        self.assertFalse(any(show["organiser"]["id"] == "bakewell-rock-exchange" for show in shows))
        self.assertTrue(any(show["organiser"]["id"] == "rockngem" for show in shows))
        previous = [
            {
                "id": "bakewell-rock-exchange-2026-10-10-de451dr",
                "slug": "bakewell-rock-exchange-bakewell-2026-10-10",
                "name": "Bakewell Rock Exchange",
                "start": "2026-10-10",
                "organiser": {"id": "bakewell-rock-exchange"},
            },
            {
                "id": "rockngem-should-not-return",
                "slug": "stale-rockngem",
                "name": "Stale",
                "start": "2026-01-01",
                "organiser": {"id": "rockngem"},
            },
        ]
        merged = merge_kept(shows, [show for show in previous if show["organiser"]["id"] in failed])
        kept_ids = [show["id"] for show in merged if show["organiser"]["id"] == "bakewell-rock-exchange"]
        self.assertEqual(kept_ids, ["bakewell-rock-exchange-2026-10-10-de451dr"])
        self.assertNotIn("rockngem-should-not-return", [show["id"] for show in merged])

    def test_clashing_kept_slug_gets_a_suffix(self):
        fresh = [{"id": "fresh", "slug": "same-slug", "name": "Fresh", "start": "2026-11-01", "organiser": {"id": "rockngem"}}]
        kept = [{"id": "old", "slug": "same-slug", "name": "Old", "start": "2026-10-01", "organiser": {"id": "smls"}}]
        merged = merge_kept(fresh, kept)
        by_id = {show["id"]: show["slug"] for show in merged}
        self.assertEqual(by_id["fresh"], "same-slug")
        self.assertEqual(by_id["old"], "same-slug-2")
        self.assertEqual([show["id"] for show in merged], ["old", "fresh"])


SATURDAY = "https://www.deanheritagecentre.org/event-details-registration/christmas-market-2026-11-21-10-00"
SUNDAY = "https://www.deanheritagecentre.org/event-details-registration/christmas-market-2026-11-22-10-00"


class AddedShowTests(unittest.TestCase):
    def test_hand_added_show_survives_a_fixture_rebuild(self):
        parsed = assemble_fixtures()
        self.assertFalse(any(show["organiser"]["id"] == "dean-heritage-centre" for show in parsed))
        merged = include_added(parsed)
        again = include_added(merged)
        shows = [show for show in again if show["organiser"]["id"] == "dean-heritage-centre"]
        self.assertEqual(len(shows), 1)
        show = shows[0]
        self.assertEqual(show["id"], "dean-heritage-centre-2026-11-21-gl142ub")
        self.assertEqual(show["slug"], "dean-heritage-centre-christmas-market-soudley-2026-11-21")
        self.assertEqual(show["name"], "Dean Heritage Centre Christmas Market")
        self.assertEqual(show["start"], "2026-11-21")
        self.assertEqual(show["end"], "2026-11-22")
        self.assertEqual(show["times"]["summary"], "Saturday 10:00 to 16:00. Sunday 10:00 to 16:00.")
        self.assertEqual(show["entry"]["kind"], "free")
        self.assertEqual(show["entry"]["adult_gbp"], 0)
        self.assertEqual(show["entry"]["label"], "Free entry")
        self.assertEqual(show["types"], ["fossil", "mineral"])
        self.assertEqual(show["venue"]["name"], "Dean Heritage Centre")
        self.assertEqual(show["venue"]["street"], "Camp Mill")
        self.assertEqual(show["venue"]["postcode"], "GL14 2UB")
        self.assertEqual(show["venue"]["town"], "Soudley")
        self.assertEqual(show["venue"]["county"], "Gloucestershire")
        self.assertEqual(show["venue"]["nation"], "England")
        self.assertEqual(show["venue"]["lat"], 51.790134)
        self.assertEqual(show["venue"]["lng"], -2.487043)
        self.assertIn("Forest of Dean", show["venue"]["place_note"])
        self.assertIn("makers' market", show["summary"])
        self.assertIn("Herefordshire & Worcestershire Earth Heritage Trust", show["summary"])
        self.assertIn("fossil and mineral stall", show["summary"])
        self.assertIn("School Fossil Box", show["summary"])
        self.assertIsNone(INTERNAL_NOTE.search(show["summary"]))
        self.assertIsNone(INTERNAL_NOTE.search(show["venue"]["place_note"] or ""))
        blob = json.dumps(show)
        self.assertNotIn("Baggott", blob)
        self.assertNotIn("Facebook", blob)
        self.assertNotIn("UK Fossils", blob)
        self.assertNotIn("!", blob)
        self.assertNotIn("\u2013", blob)
        self.assertNotIn("\u2014", blob)
        self.assertNotIn("facebook.com", blob)
        self.assertEqual(show["organiser"]["url"], SATURDAY)
        self.assertEqual(show["source"]["url"], SATURDAY)
        self.assertEqual(show["source"]["retrieved"], "2026-11-03")
        self.assertEqual([item["url"] for item in show["source"]["also"]], [SUNDAY])
        self.assertEqual(len(again), len(parsed) + 1)

    def test_committed_catalogue_matches_the_added_file(self):
        extra = added_shows()
        self.assertEqual(len(extra), 1)
        catalogue = json.loads((ROOT / "data" / "shows.json").read_text(encoding="utf-8"))["shows"]
        stored = next(show for show in catalogue if show["id"] == extra[0]["id"])
        self.assertEqual(stored, extra[0])
        listings = json.loads((ROOT / "data" / "listings.json").read_text(encoding="utf-8"))
        self.assertIn("gloucestershire", [row["slug"] for row in listings["counties"]])
        self.assertIn("soudley", [row["slug"] for row in listings["towns"]])

    def test_parsed_row_wins_when_the_id_matches(self):
        parsed = assemble_fixtures()
        sample = next(show for show in parsed if show["organiser"]["id"] == "rockngem")
        row = {
            "organiser_id": "rockngem",
            "organiser_name": "Should not replace",
            "organiser_url": "https://www.rockngem.co/",
            "name": "Should not replace",
            "summary": "Should not replace.",
            "types": ["rock"],
            "start": sample["start"],
            "end": sample["end"],
            "venue_name": sample["venue"]["name"],
            "postcode": sample["venue"]["postcode"],
            "source_url": "https://www.rockngem.co/",
            "source_retrieved": "2026-11-03",
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "added-shows.json"
            path.write_text(json.dumps({"shows": [row]}), encoding="utf-8")
            merged = include_added(parsed, path)
        self.assertEqual(len(merged), len(parsed))
        kept = next(show for show in merged if show["id"] == sample["id"])
        self.assertEqual(kept["name"], sample["name"])
        self.assertNotEqual(kept["name"], "Should not replace")

    def test_fixture_refresh_counts_the_hand_added_show_without_writing(self):
        stdout = io.StringIO()
        with patch.object(sys, "argv", ["refresh.py", "--fixtures", "--today", "2026-11-03"]):
            with redirect_stdout(stdout), redirect_stderr(io.StringIO()):
                refresh.main()
        self.assertIn("dean-heritage-centre: 1", stdout.getvalue())
        self.assertNotIn("Wrote", stdout.getvalue())


def assemble_fixtures():
    return assemble(rows_from_fixtures(date(2026, 10, 25)))
