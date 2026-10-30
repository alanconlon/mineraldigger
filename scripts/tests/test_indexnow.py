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
