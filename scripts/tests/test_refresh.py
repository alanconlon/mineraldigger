"""Refresh fetch rules and the keep-previous fallback. No live network."""

import email.message
import ssl
import sys
import unittest
import urllib.error
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import refresh  # noqa: E402
from refresh import (  # noqa: E402
    BROWSER_UA,
    LIVE,
    UA,
    UNVERIFIED_HOST,
    fetch,
    merge_kept,
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
