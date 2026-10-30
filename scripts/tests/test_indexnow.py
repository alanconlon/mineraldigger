"""IndexNow submits a URL only when it is new or its lastmod changed."""

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


def write_site(root: Path, state: dict | None) -> tuple[Path, Path, Path]:
    dist = root / "dist"
    dist.mkdir()
    (dist / "sitemap.xml").write_text(SITEMAP, encoding="utf-8")
    (dist / f"{KEY}.txt").write_text(KEY + "\n", encoding="utf-8")
    state_path = root / "data" / "indexnow_state.json"
    state_path.parent.mkdir()
    if state is not None:
        state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")
    return dist / "sitemap.xml", state_path, dist


def run_main(argv: list[str]) -> tuple[int, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = indexnow.main(argv)
    return code, stdout.getvalue() + stderr.getvalue()


class DiffTests(unittest.TestCase):
    def test_first_run_sends_every_com_url(self):
        urls = {
            "https://mineraldigger.com/": "2026-10-28",
            "https://mineraldigger.com/show/a/": "2026-10-29",
        }
        self.assertEqual(indexnow.changed_urls(urls, {}), list(urls))

    def test_unchanged_lastmod_is_skipped_and_a_new_or_edited_url_is_sent(self):
        sitemap = {
            "https://mineraldigger.com/": "2026-10-28",
            "https://mineraldigger.com/show/a/": "2026-10-30",
            "https://mineraldigger.com/town/sunbury-on-thames/": "2026-10-30",
        }
        previous = {
            "https://mineraldigger.com/": "2026-10-28",
            "https://mineraldigger.com/show/a/": "2026-10-29",
            "https://mineraldigger.com/old/": "2026-10-01",
        }
        self.assertEqual(
            indexnow.changed_urls(sitemap, previous),
            [
                "https://mineraldigger.com/show/a/",
                "https://mineraldigger.com/town/sunbury-on-thames/",
            ],
        )

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

    def test_success_records_accepted_lastmods_only(self):
        sitemap = {
            "https://mineraldigger.com/": "2026-10-28",
            "https://mineraldigger.com/show/a/": "2026-10-30",
        }
        previous = {
            "https://mineraldigger.com/": "2026-10-28",
            "https://mineraldigger.com/gone/": "2026-10-01",
        }
        updated = indexnow.state_after_success(sitemap, previous, ["https://mineraldigger.com/show/a/"])
        self.assertEqual(
            updated,
            {
                "https://mineraldigger.com/": "2026-10-28",
                "https://mineraldigger.com/show/a/": "2026-10-30",
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
                {"host": "mineraldigger.com", "urls": {"https://mineraldigger.com/": "2026-10-28"}},
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
            self.assertEqual(saved["urls"]["https://mineraldigger.com/show/a/"], "2026-10-29")
            self.assertEqual(saved["urls"]["https://mineraldigger.com/"], "2026-10-28")

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
