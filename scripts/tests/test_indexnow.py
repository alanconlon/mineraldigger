"""IndexNow submits a URL only when it is new or its content hash changed."""

from __future__ import annotations

import io
import json
import sys
import unittest
import urllib.error
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import indexnow  # noqa: E402

KEY = "3b35b2fc93db4757a34032329daf6509"
SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://mineraldigger.com/</loc><lastmod>2026-10-28</lastmod></url>
<url><loc>https://mineraldigger.com/show/a/</loc><lastmod>2026-10-29</lastmod></url>
<url><loc>https://mineraldigger.co.uk/</loc><lastmod>2026-10-29</lastmod></url>
<url><loc>https://www.mineraldigger.co.uk/show/a/</loc><lastmod>2026-10-29</lastmod></url>
</urlset>
"""


HOME = "<html><p>Home shows</p><p>Data last refreshed 28 October 2026.</p><script src=\"/js/site.js?v=aaaaaaaaaaaa\"></script></html>"
SHOW = "<html><p>Show A</p><p>Retrieved 28 October 2026 from the organiser.</p><script type=\"application/ld+json\">{\"validFrom\":\"2026-10-28T00:00:00+01:00\"}</script></html>"
SHOW_CHANGED = "<html><p>Show A, now with fossils</p><p>Retrieved 30 October 2026 from the organiser.</p></html>"


def write_site(root: Path, state: dict | None, show_html: str = SHOW) -> tuple[Path, Path, Path]:
    dist = root / "dist"
    (dist / "show" / "a").mkdir(parents=True)
    (dist / "index.html").write_text(HOME, encoding="utf-8")
    (dist / "show" / "a" / "index.html").write_text(show_html, encoding="utf-8")
    (dist / "sitemap.xml").write_text(SITEMAP, encoding="utf-8")
    (dist / f"{KEY}.txt").write_text(KEY + "\n", encoding="utf-8")
    state_path = root / "data" / "indexnow_state.json"
    state_path.parent.mkdir()
    if state is not None:
        state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")
    return dist / "sitemap.xml", state_path, dist


def entry(html: str, lastmod: str) -> dict[str, str]:
    return {"hash": indexnow.content_hash(html), "lastmod": lastmod}


def run_main(argv: list[str]) -> tuple[int, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = indexnow.main(argv)
    return code, stdout.getvalue() + stderr.getvalue()


class DiffTests(unittest.TestCase):
    def test_refresh_dates_do_not_change_the_hash(self):
        later = HOME.replace("28 October 2026", "30 October 2026").replace("?v=aaaaaaaaaaaa", "?v=bbbbbbbbbbbb")
        self.assertEqual(indexnow.content_hash(HOME), indexnow.content_hash(later))
        retrieved = SHOW.replace("28 October 2026", "30 October 2026").replace(
            "2026-10-28T00:00:00+01:00", "2026-10-30T00:00:00+00:00"
        )
        self.assertEqual(indexnow.content_hash(SHOW), indexnow.content_hash(retrieved))
        self.assertNotEqual(indexnow.content_hash(SHOW), indexnow.content_hash(SHOW_CHANGED))

    def test_first_run_sends_every_url(self):
        pages = {
            "https://mineraldigger.com/": indexnow.content_hash(HOME),
            "https://mineraldigger.com/show/a/": indexnow.content_hash(SHOW),
        }
        self.assertEqual(indexnow.changed_urls(pages, {}), list(pages))

    def test_unchanged_hash_is_skipped_and_a_new_or_edited_url_is_sent(self):
        home = indexnow.content_hash(HOME)
        pages = {
            "https://mineraldigger.com/": home,
            "https://mineraldigger.com/show/a/": indexnow.content_hash(SHOW_CHANGED),
            "https://mineraldigger.com/town/sunbury-on-thames/": "new",
        }
        previous = {
            "https://mineraldigger.com/": {"hash": home, "lastmod": "2026-10-30"},
            "https://mineraldigger.com/show/a/": {"hash": indexnow.content_hash(SHOW), "lastmod": "2026-10-30"},
            "https://mineraldigger.com/old/": {"hash": "gone", "lastmod": "2026-10-01"},
        }
        self.assertEqual(
            indexnow.changed_urls(pages, previous),
            [
                "https://mineraldigger.com/show/a/",
                "https://mineraldigger.com/town/sunbury-on-thames/",
            ],
        )

    def test_stamp_keeps_the_stored_date_until_the_hash_changes(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            sitemap, state, dist = write_site(
                root,
                {
                    "host": "mineraldigger.com",
                    "urls": {"https://mineraldigger.com/": entry(HOME, "2026-10-30")},
                },
            )
            code, _ = run_main(["--stamp-sitemap", "--date", "2026-11-02", "--sitemap", str(sitemap), "--state", str(state), "--dist", str(dist)])
            text = sitemap.read_text(encoding="utf-8")
            self.assertEqual(code, 0)
            self.assertIn("<loc>https://mineraldigger.com/</loc><lastmod>2026-10-30</lastmod>", text)
            self.assertIn("<loc>https://mineraldigger.com/show/a/</loc><lastmod>2026-11-02</lastmod>", text)

    def test_check_keeps_stored_dates_and_accepts_the_build_date_when_content_changes(self):
        home = indexnow.content_hash(HOME)
        show = indexnow.content_hash(SHOW)
        changed_home = indexnow.content_hash(HOME.replace("Home shows", "Home shows today"))
        changed_show = indexnow.content_hash(SHOW_CHANGED)
        previous = {
            "https://mineraldigger.com/": {"hash": home, "lastmod": "2026-10-30"},
            "https://mineraldigger.com/show/a/": {"hash": show, "lastmod": "2026-10-29"},
            "https://mineraldigger.com/old/": {"hash": "gone", "lastmod": "2026-10-01"},
        }
        unchanged_pages = {
            "https://mineraldigger.com/": home,
            "https://mineraldigger.com/show/a/": show,
        }
        self.assertEqual(
            indexnow.sitemap_lastmod_errors(
                {
                    "https://mineraldigger.com/": "2026-10-30",
                    "https://mineraldigger.com/show/a/": "2026-10-29",
                },
                unchanged_pages,
                previous,
                "2026-11-03",
            ),
            [],
        )
        bumped = indexnow.sitemap_lastmod_errors(
            {
                "https://mineraldigger.com/": "2026-11-03",
                "https://mineraldigger.com/show/a/": "2026-11-03",
            },
            unchanged_pages,
            previous,
            "2026-11-03",
        )
        self.assertEqual(
            bumped,
            [
                "Homepage sitemap lastmod should stay on the stored content date while the page is unchanged.",
                "Sitemap lastmod should stay on the stored content date while the page is unchanged: https://mineraldigger.com/show/a/",
            ],
        )
        changed_pages = {
            "https://mineraldigger.com/": changed_home,
            "https://mineraldigger.com/show/a/": changed_show,
            "https://mineraldigger.com/town/new/": "new",
        }
        self.assertNotEqual("2026-11-03", previous["https://mineraldigger.com/"]["lastmod"])
        self.assertEqual(
            indexnow.sitemap_lastmod_errors(
                {
                    "https://mineraldigger.com/": "2026-11-03",
                    "https://mineraldigger.com/show/a/": "2026-11-03",
                    "https://mineraldigger.com/town/new/": "2026-11-03",
                },
                changed_pages,
                previous,
                "2026-11-03",
            ),
            [],
        )
        stale = indexnow.sitemap_lastmod_errors(
            {
                "https://mineraldigger.com/": "2026-10-30",
                "https://mineraldigger.com/show/a/": "2026-10-29",
                "https://mineraldigger.com/town/new/": "2026-10-01",
            },
            changed_pages,
            previous,
            "2026-11-03",
        )
        self.assertEqual(
            stale,
            [
                "Homepage sitemap lastmod should be the build date when the page content changed.",
                "Sitemap lastmod should be the build date when the page content changed: https://mineraldigger.com/show/a/",
                "Sitemap lastmod should be the build date when the page content changed: https://mineraldigger.com/town/new/",
            ],
        )

    def test_stamp_and_check_pass_for_an_unchanged_and_a_changed_homepage(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            sitemap, state, dist = write_site(
                root,
                {
                    "host": "mineraldigger.com",
                    "urls": {
                        "https://mineraldigger.com/": entry(HOME, "2026-10-30"),
                        "https://mineraldigger.com/show/a/": entry(SHOW, "2026-10-29"),
                    },
                },
            )
            paths = ["--date", "2026-11-03", "--sitemap", str(sitemap), "--state", str(state), "--dist", str(dist)]
            code, output = run_main(["--stamp-sitemap", *paths])
            self.assertEqual(code, 0, output)
            text = sitemap.read_text(encoding="utf-8")
            self.assertIn("<loc>https://mineraldigger.com/</loc><lastmod>2026-10-30</lastmod>", text)
            self.assertIn("<loc>https://mineraldigger.com/show/a/</loc><lastmod>2026-10-29</lastmod>", text)
            code, output = run_main(["--check-sitemap", *paths])
            self.assertEqual(code, 0, output)

            (dist / "index.html").write_text(HOME.replace("Home shows", "Home shows today"), encoding="utf-8")
            code, output = run_main(["--stamp-sitemap", *paths])
            self.assertEqual(code, 0, output)
            text = sitemap.read_text(encoding="utf-8")
            self.assertIn("<loc>https://mineraldigger.com/</loc><lastmod>2026-11-03</lastmod>", text)
            self.assertIn("<loc>https://mineraldigger.com/show/a/</loc><lastmod>2026-10-29</lastmod>", text)
            self.assertNotIn("<lastmod>2026-10-30</lastmod>", text)
            code, output = run_main(["--check-sitemap", *paths])
            self.assertEqual(code, 0, output)

            sitemap.write_text(
                text.replace(
                    "<loc>https://mineraldigger.com/</loc><lastmod>2026-11-03</lastmod>",
                    "<loc>https://mineraldigger.com/</loc><lastmod>2026-10-30</lastmod>",
                ),
                encoding="utf-8",
            )
            code, output = run_main(["--check-sitemap", *paths])
            self.assertEqual(code, 1)
            self.assertIn("Homepage sitemap lastmod should be the build date when the page content changed.", output)

            sitemap.write_text(text, encoding="utf-8")
            bumped = text.replace(
                "<loc>https://mineraldigger.com/show/a/</loc><lastmod>2026-10-29</lastmod>",
                "<loc>https://mineraldigger.com/show/a/</loc><lastmod>2026-11-03</lastmod>",
            )
            sitemap.write_text(bumped, encoding="utf-8")
            code, output = run_main(["--check-sitemap", *paths])
            self.assertEqual(code, 1)
            self.assertIn(
                "Sitemap lastmod should stay on the stored content date while the page is unchanged: https://mineraldigger.com/show/a/",
                output,
            )

    def test_page_check_does_not_demand_the_stored_date_unconditionally(self):
        source = (ROOT / "scripts" / "check.mjs").read_text(encoding="utf-8")
        self.assertIn('"--check-sitemap"', source)
        self.assertNotIn("${homeIndexNow.lastmod}", source)

    def test_page_check_follows_the_catalogue_instead_of_named_weekends(self):
        source = (ROOT / "scripts" / "check.mjs").read_text(encoding="utf-8")
        for needle in (
            "rock-gem-and-bead-show-worcester-2026-11-07",
            "rock-gem-and-bead-show-sunbury-on-thames-2026-10-31",
            "bakewell-rock-exchange-bakewell-2026-10-10",
            "Kempton Park",
            "Haywards Heath: Sussex",
            "Unexpected show count",
            "Not enough upcoming shows",
        ):
            self.assertNotIn(needle, source)
        self.assertIn("entryLabel", source)
        self.assertIn("listedName", source)
        self.assertIn("example-past-show", source)
        self.assertIn("example-free-show", source)

    def test_sitemap_ignores_co_uk_hosts(self):
        with TemporaryDirectory() as tmp:
            sitemap, _, _ = write_site(Path(tmp), None)
            urls = indexnow.parse_sitemap(sitemap)
        self.assertEqual(
            list(urls),
            ["https://mineraldigger.com/", "https://mineraldigger.com/show/a/"],
        )

    def test_batches_stay_within_10000(self):
        urls = [f"https://mineraldigger.com/{index}/" for index in range(10001)]
        groups = indexnow.batches(urls)
        self.assertEqual(len(groups), 2)
        self.assertEqual(len(groups[0]), 10000)
        self.assertEqual(len(groups[1]), 1)

    def test_success_records_the_accepted_hash_and_drops_removed_urls(self):
        home = indexnow.content_hash(HOME)
        show = indexnow.content_hash(SHOW)
        pages = {
            "https://mineraldigger.com/": home,
            "https://mineraldigger.com/show/a/": show,
        }
        previous = {
            "https://mineraldigger.com/": {"hash": home, "lastmod": "2026-10-30"},
            "https://mineraldigger.com/gone/": {"hash": "old", "lastmod": "2026-10-01"},
        }
        updated = indexnow.state_after_success(
            pages,
            previous,
            ["https://mineraldigger.com/show/a/"],
            {"https://mineraldigger.com/show/a/": "2026-10-30"},
        )
        self.assertEqual(
            updated,
            {
                "https://mineraldigger.com/": {"hash": home, "lastmod": "2026-10-30"},
                "https://mineraldigger.com/show/a/": {"hash": show, "lastmod": "2026-10-30"},
            },
        )


class RunTests(unittest.TestCase):
    def test_dry_run_prints_the_diff_and_leaves_the_state_file(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            sitemap, state, dist = write_site(root, {"host": "mineraldigger.com", "urls": {}})
            before = state.read_text(encoding="utf-8")
            with mock.patch("urllib.request.urlopen") as post:
                code, output = run_main(["--dry-run", "--sitemap", str(sitemap), "--state", str(state), "--dist", str(dist)])
            post.assert_not_called()
            self.assertEqual(code, 0)
            self.assertIn("https://mineraldigger.com/show/a/", output)
            self.assertNotIn("mineraldigger.co.uk", output)
            self.assertEqual(state.read_text(encoding="utf-8"), before)

    def test_http_200_updates_the_state_file(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            sitemap, state, dist = write_site(
                root,
                {"host": "mineraldigger.com", "urls": {"https://mineraldigger.com/": entry(HOME, "2026-10-30")}},
            )
            response = mock.Mock()
            response.status = 200
            response.__enter__ = mock.Mock(return_value=response)
            response.__exit__ = mock.Mock(return_value=False)
            with mock.patch("urllib.request.urlopen", return_value=response) as post:
                code, output = run_main(["--sitemap", str(sitemap), "--state", str(state), "--dist", str(dist)])
            self.assertEqual(code, 0)
            self.assertIn("IndexNow 200 for 1 URLs", output)
            body = json.loads(post.call_args.args[0].data.decode("utf-8"))
            self.assertEqual(body["host"], "mineraldigger.com")
            self.assertEqual(body["key"], KEY)
            self.assertEqual(body["keyLocation"], f"https://mineraldigger.com/{KEY}.txt")
            self.assertEqual(body["urlList"], ["https://mineraldigger.com/show/a/"])
            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(saved["urls"]["https://mineraldigger.com/show/a/"]["hash"], indexnow.content_hash(SHOW))
            self.assertEqual(saved["urls"]["https://mineraldigger.com/show/a/"]["lastmod"], "2026-10-29")
            self.assertEqual(saved["urls"]["https://mineraldigger.com/"]["hash"], indexnow.content_hash(HOME))
            self.assertEqual(saved["urls"]["https://mineraldigger.com/"]["lastmod"], "2026-10-30")

    def test_http_202_updates_the_state_file(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            sitemap, state, dist = write_site(root, {"host": "mineraldigger.com", "urls": {}})
            response = mock.Mock()
            response.status = 202
            response.__enter__ = mock.Mock(return_value=response)
            response.__exit__ = mock.Mock(return_value=False)
            with mock.patch("urllib.request.urlopen", return_value=response):
                code, output = run_main(["--sitemap", str(sitemap), "--state", str(state), "--dist", str(dist)])
            self.assertEqual(code, 0)
            self.assertIn("IndexNow 202 for 2 URLs", output)
            saved = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(saved["urls"]["https://mineraldigger.com/"]["hash"], indexnow.content_hash(HOME))
            self.assertEqual(saved["urls"]["https://mineraldigger.com/show/a/"]["hash"], indexnow.content_hash(SHOW))

    def test_http_400_logs_the_code_and_keeps_the_state_file(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            sitemap, state, dist = write_site(root, {"host": "mineraldigger.com", "urls": {}})
            before = state.read_text(encoding="utf-8")
            with mock.patch("urllib.request.urlopen", side_effect=urllib.error.HTTPError(indexnow.ENDPOINT, 400, "Bad request", hdrs=None, fp=None)):
                code, output = run_main(["--sitemap", str(sitemap), "--state", str(state), "--dist", str(dist)])
            self.assertEqual(code, 0)
            self.assertIn("IndexNow 400", output)
            self.assertEqual(state.read_text(encoding="utf-8"), before)


if __name__ == "__main__":
    unittest.main()
