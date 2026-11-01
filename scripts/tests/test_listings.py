"""Low show counts warn, and they do not drop a listing page."""

from __future__ import annotations

import io
import json
import sys
import unittest
import urllib.error
from contextlib import redirect_stderr
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from listings import (  # noqa: E402
    WARN_BELOW,
    fetch_live_sitemap,
    listing_urls_from_sitemap,
    load_listings,
    low_count_message,
    low_count_warnings,
    retain_listings,
    slugify,
    warn_low_counts,
)

TODAY = date(2026, 11, 1)
SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://mineraldigger.com/county/</loc></url>
<url><loc>https://mineraldigger.com/county/devon/</loc></url>
<url><loc>https://mineraldigger.com/town/exeter/</loc></url>
<url><loc>https://mineraldigger.com/region/south-west/</loc></url>
<url><loc>https://mineraldigger.com/rock/</loc></url>
<url><loc>https://mineraldigger.com/show/example/</loc></url>
<url><loc>https://mineraldigger.co.uk/town/exeter/</loc></url>
</urlset>
"""


def show(end, town, county, types, region=""):
    return {
        "end": end,
        "types": types,
        "venue": {"town": town, "county": county, "nation": "England", "region": region},
    }


class ListingTests(unittest.TestCase):
    def test_slug_matches_the_site(self):
        self.assertEqual(slugify("Sunbury-on-Thames"), "sunbury-on-thames")
        self.assertEqual(slugify("Tyne and Wear"), "tyne-and-wear")
        self.assertEqual(WARN_BELOW, 1)

    def test_saved_page_stays_when_it_has_no_upcoming_shows(self):
        saved = {
            "counties": [{"slug": "hampshire", "name": "Hampshire", "nation": "England"}],
            "towns": [{"slug": "southampton", "name": "Southampton", "county": "Hampshire", "nation": "England"}],
            "regions": [{"slug": "south-west", "name": "South West", "nation": "England"}],
        }
        shows = [
            show("2026-09-19", "Southampton", "Hampshire", ["mineral"]),
            show("2026-12-01", "Exeter", "Devon", ["rock", "gem", "mineral", "fossil", "bead"]),
        ]
        retained = retain_listings(saved, shows, TODAY)
        slugs = {row["slug"] for row in retained["towns"]}
        self.assertIn("southampton", slugs)
        self.assertIn("exeter", slugs)
        self.assertIn("hampshire", {row["slug"] for row in retained["counties"]})
        self.assertIn("devon", {row["slug"] for row in retained["counties"]})
        self.assertEqual([row["slug"] for row in retained["regions"]], ["south-west"])
        messages = low_count_warnings(retained, shows, TODAY)
        self.assertIn(low_count_message("/town/southampton/", 0), messages)
        self.assertIn(low_count_message("/county/hampshire/", 0), messages)
        self.assertIn(low_count_message("/region/south-west/", 0), messages)
        self.assertFalse(any("/town/exeter/" in message for message in messages))
        self.assertFalse(any("/devon" in message for message in messages))
        self.assertFalse(any("noindex" in message or "coming soon" in message for message in messages))

    def test_past_only_town_is_not_added(self):
        shows = [show("2026-09-19", "Southampton", "Hampshire", ["mineral"])]
        retained = retain_listings({"counties": [], "towns": [], "regions": []}, shows, TODAY)
        self.assertEqual(retained["towns"], [])
        self.assertEqual(retained["counties"], [])

    def test_one_upcoming_show_is_not_a_warning(self):
        saved = {"counties": [], "towns": [{"slug": "exeter", "name": "Exeter", "county": "Devon", "nation": "England"}], "regions": []}
        shows = [show("2026-12-01", "Exeter", "Devon", ["rock", "gem", "mineral", "fossil", "bead"])]
        retained = retain_listings(saved, shows, TODAY)
        messages = low_count_warnings(retained, shows, TODAY)
        self.assertFalse(any("/town/exeter/" in message for message in messages))
        self.assertFalse(any(message.startswith("/rock/") for message in messages))

    def test_warning_lines_include_the_actions_annotation(self):
        saved = {"counties": [], "towns": [{"slug": "exeter", "name": "Exeter", "county": "Devon", "nation": "England"}], "regions": []}
        shows = [show("2026-09-19", "Exeter", "Devon", ["rock", "gem", "mineral", "fossil", "bead"])]
        buffer = io.StringIO()
        with redirect_stderr(buffer):
            warn_low_counts(saved, shows, TODAY)
        output = buffer.getvalue()
        message = low_count_message("/town/exeter/", 0)
        self.assertIn(f"Warning: {message}", output)
        self.assertIn(f"::warning::{message}", output)

    def test_sitemap_keeps_listing_urls_only(self):
        urls = listing_urls_from_sitemap(SITEMAP)
        self.assertEqual(
            urls,
            [
                "https://mineraldigger.com/county/devon/",
                "https://mineraldigger.com/town/exeter/",
                "https://mineraldigger.com/region/south-west/",
            ],
        )

    def test_live_sitemap_urls_are_kept(self):
        saved = {"counties": [], "towns": [], "regions": []}
        retained = retain_listings(saved, [], TODAY, listing_urls_from_sitemap(SITEMAP))
        self.assertEqual([row["slug"] for row in retained["towns"]], ["exeter"])
        self.assertEqual(retained["towns"][0]["name"], "Exeter")
        self.assertEqual([row["slug"] for row in retained["regions"]], ["south-west"])

    def test_live_sitemap_name_comes_from_the_catalogue(self):
        shows = [show("2026-08-01", "Newcastle upon Tyne", "Tyne and Wear", ["rock"])]
        retained = retain_listings(
            {"counties": [], "towns": [], "regions": []},
            shows,
            TODAY,
            ["https://mineraldigger.com/town/newcastle-upon-tyne/"],
        )
        self.assertEqual(retained["towns"][0]["name"], "Newcastle upon Tyne")
        self.assertEqual(retained["towns"][0]["county"], "Tyne and Wear")

    def test_sitemap_fetch_failure_keeps_going(self):
        with patch("listings.urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
            buffer = io.StringIO()
            with redirect_stderr(buffer):
                urls = fetch_live_sitemap()
        self.assertEqual(urls, [])
        self.assertIn("Saved listing pages stay", buffer.getvalue())

    def test_current_registry_matches_pages_that_are_live_on_1_november_2026(self):
        shows = json.loads((ROOT / "data" / "shows.json").read_text(encoding="utf-8"))["shows"]
        saved = load_listings(ROOT / "data" / "listings.json")
        retained = retain_listings(saved, shows, TODAY)
        self.assertEqual([row["slug"] for row in retained["counties"]], [row["slug"] for row in saved["counties"]])
        self.assertEqual([row["slug"] for row in retained["towns"]], [row["slug"] for row in saved["towns"]])
        self.assertEqual(retained["regions"], [])
        self.assertIn("surrey", {row["slug"] for row in saved["counties"]})
        self.assertIn("sunbury-on-thames", {row["slug"] for row in saved["towns"]})
        self.assertNotIn("southampton", {row["slug"] for row in saved["towns"]})
        self.assertEqual(low_count_warnings(saved, shows, TODAY), [])
