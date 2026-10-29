"""Friday email digest and Buttondown draft tests. No live API key."""

from __future__ import annotations

import io
import json
import os
import sys
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import buttondown_draft  # noqa: E402
from digest import (  # noqa: E402
    empty_friday_sponsor,
    issue_friday,
    load_json,
    render_newsletter,
    subject_for,
    write_newsletter,
)

TODAY = date(2026, 10, 28)
SHOWS = load_json(ROOT / "data" / "shows.json")["shows"]
SITE = "https://mineraldigger.com"
INTRO = (
    "A Friday list of UK rock, gem, mineral, fossil and bead shows. "
    "Dates, venues, times and entry come from the MineralDigger catalogue, "
    "checked against organiser websites. Confirm with the organiser before you travel."
)
EMPTY_FRIDAY = (
    "**This week's sponsor slot is free.** Sponsor this Friday email for £12, "
    "or the site for £25 a month: "
    "[see the sponsor options](https://mineraldigger.com/feature/)."
)


def run_main(argv: list[str]) -> tuple[int, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = buttondown_draft.main(argv)
    return code, stdout.getvalue() + stderr.getvalue()


def paragraph_for(markdown: str, slug: str) -> str:
    needle = f"/show/{slug}/"
    lines = markdown.splitlines()
    for index, line in enumerate(lines):
        if needle in line:
            for follow in lines[index + 1 :]:
                if follow.strip():
                    return follow
    raise AssertionError(f"missing show {slug}")


def banned(value: str) -> bool:
    prose = value.replace("<!-- buttondown-editor-mode: plaintext -->", "")
    return "!" in prose or "\u2014" in prose or "\u2013" in prose or "Ireland" in prose


class DigestTests(unittest.TestCase):
    def test_issue_friday_matches_the_site_window(self):
        self.assertEqual(issue_friday(date(2026, 10, 28)), date(2026, 10, 30))
        self.assertEqual(issue_friday(date(2026, 10, 30)), date(2026, 10, 30))
        self.assertEqual(issue_friday(date(2026, 10, 31)), date(2026, 11, 6))
        self.assertEqual(issue_friday(date(2026, 11, 1)), date(2026, 11, 6))

    def test_seed_friday_uses_catalogue_facts_only(self):
        friday, markdown = render_newsletter(SHOWS, TODAY, SITE)
        self.assertEqual(friday, date(2026, 10, 30))
        self.assertTrue(markdown.startswith("<!-- buttondown-editor-mode: plaintext -->"))
        self.assertIn(f"# {subject_for(friday)}", markdown)
        self.assertFalse(banned(markdown))
        self.assertNotIn("Sponsored", markdown)
        self.assertNotIn("Run a rock, gem or lapidary shop?", markdown)
        self.assertEqual(markdown.count(EMPTY_FRIDAY), 1)
        self.assertEqual(markdown.count("**This week's sponsor slot is free.**"), 1)
        self.assertIn(f"{INTRO}\n\n{EMPTY_FRIDAY}\n\n## This weekend", markdown)
        self.assertNotIn("www.rockngem.co", markdown)
        self.assertNotIn("07712", markdown)
        self.assertNotIn("fills quickly", markdown)
        self.assertNotIn("Kidlington", markdown)
        self.assertNotIn("provisional", markdown.lower())

        sunbury = paragraph_for(markdown, "rock-gem-and-bead-show-sunbury-on-thames-2026-10-31")
        self.assertIn("Kempton Park Racecourse, Sunbury-on-Thames, TW16 5AQ", sunbury)
        self.assertIn("Entry £6", sunbury)
        self.assertIn("Saturday 10:00 to 17:00", sunbury)
        self.assertIn("Pay on the door", sunbury)

        worcester = paragraph_for(markdown, "rock-gem-and-bead-show-worcester-2026-11-07")
        self.assertIn("Worcester Racecourse, Worcester, WR1 3EJ", worcester)
        self.assertNotIn("£", worcester)
        self.assertNotIn("Unknown", worcester)
        self.assertNotIn("10:00", worcester)

        newcastle = paragraph_for(markdown, "rock-gem-and-bead-show-newcastle-upon-tyne-2026-11-14")
        self.assertIn("Newcastle Racecourse, Newcastle upon Tyne, NE3 5HP", newcastle)
        self.assertNotIn("£", newcastle)
        self.assertNotIn("Unknown", newcastle)

        sussex = paragraph_for(markdown, "sussex-mineral-crystal-and-fossil-show-haywards-heath-2026-11-14")
        self.assertIn("Haywards Heath College, Harlands Road, Haywards Heath, RH16 1LT", sussex)
        self.assertIn("Entry £5", sussex)
        self.assertIn("Early entry £10", sussex)
        self.assertIn("matches the weekday on the organiser page", sussex)
        self.assertNotIn("does not print the year", sussex)
        self.assertNotIn("year is matched", sussex)

        self.assertIn("## This weekend", markdown)
        self.assertIn("## The next couple of weeks", markdown)
        self.assertIn("### 7 to 8 November", markdown)
        self.assertIn("### 14 to 15 November", markdown)
        self.assertNotIn("## Coming up", markdown)
        self.assertIn("Further dates are on the map.", markdown)
        for hub in ("/rock/", "/gem/", "/mineral/", "/fossil/", "/bead/"):
            self.assertIn(f"{SITE}{hub}", markdown)
        self.assertIn("Subscribe and find shows at [mineraldigger.com](https://mineraldigger.com/).", markdown)

    def test_later_shows_become_a_short_coming_up(self):
        friday, markdown = render_newsletter(SHOWS, date(2026, 12, 4), SITE)
        self.assertEqual(friday, date(2026, 12, 4))
        self.assertIn("## Coming up", markdown)
        self.assertNotIn("## This weekend", markdown)
        self.assertIn("provisional", markdown)
        self.assertIn("Brighton", markdown)
        self.assertIn("Another ", markdown)
        self.assertLess(markdown.count("/show/"), 8)
        self.assertFalse(banned(markdown))

    def test_nothing_upcoming_is_skipped(self):
        self.assertIsNone(render_newsletter(SHOWS, date(2028, 6, 1), SITE))
        self.assertIsNone(render_newsletter([], TODAY, SITE))

    def test_sponsor_and_featured_use_stored_rows_only(self):
        sponsors = {
            "friday": {
                "issue": "2026-10-30",
                "name": "Northstone Lapidary",
                "url": "https://example.com/northstone",
                "line": "Rough and slabs.",
            }
        }
        featured = {"shows": [{"id": "rockngem-2026-10-31-tw165aq", "until": "2026-12-01"}], "organisers": []}
        _, markdown = render_newsletter(SHOWS, TODAY, SITE, sponsors, featured)
        booked_line = "Sponsored. [Northstone Lapidary](https://example.com/northstone). Rough and slabs."
        self.assertIn(booked_line, markdown)
        self.assertIn(f"{INTRO}\n\n{booked_line}\n\n## This weekend", markdown)
        self.assertNotIn(EMPTY_FRIDAY, markdown)
        sunbury = paragraph_for(markdown, "rock-gem-and-bead-show-sunbury-on-thames-2026-10-31")
        self.assertTrue(sunbury.startswith("Featured. "))
        other = paragraph_for(markdown, "rock-gem-and-bead-show-worcester-2026-11-07")
        self.assertFalse(other.startswith("Featured"))

        wrong_week = {"friday": {"issue": "2026-11-06", "name": "Not this week", "url": "https://example.com/no", "line": "No."}}
        _, plain = render_newsletter(SHOWS, TODAY, SITE, wrong_week, {"shows": [], "organisers": []})
        self.assertNotIn("Not this week", plain)
        self.assertNotIn("Sponsored", plain)
        self.assertIn(EMPTY_FRIDAY, plain)
        self.assertNotIn("see the sponsor options", markdown)

    def test_empty_friday_slot_invites_a_sponsor(self):
        self.assertEqual(empty_friday_sponsor(SITE), EMPTY_FRIDAY)
        stripe = load_json(ROOT / "data" / "stripe.json")
        self.assertEqual(stripe["prices"]["friday_email"], 12)
        self.assertEqual(stripe["prices"]["site_sponsor"], 25)
        self.assertNotIn("Run a rock, gem or lapidary shop?", EMPTY_FRIDAY)
        self.assertNotIn("!", EMPTY_FRIDAY)
        self.assertNotIn("\u2014", EMPTY_FRIDAY)
        self.assertNotIn("\u2013", EMPTY_FRIDAY)

        for sponsors in (
            None,
            {},
            {"site": None, "friday": None},
            {"friday": {}},
            {"friday": {"issue": "2026-10-30", "name": "  ", "url": "https://example.com/blank", "line": "No."}},
            {"friday": {"issue": "2026-11-06", "name": "Other week", "url": "https://example.com/other"}},
        ):
            _, markdown = render_newsletter(SHOWS, TODAY, SITE, sponsors)
            self.assertEqual(markdown.count(EMPTY_FRIDAY), 1)
            self.assertIn(f"{INTRO}\n\n{EMPTY_FRIDAY}\n\n", markdown)
            self.assertNotIn("Sponsored", markdown)
            self.assertNotIn("Run a rock, gem or lapidary shop?", markdown)
            self.assertNotIn("example.com", markdown)
            self.assertFalse(banned(markdown))

        booked = {
            "friday": {
                "issue": "2026-10-30",
                "name": "Quarry Lane",
                "url": "http://example.com/quarry",
                "line": "",
            }
        }
        _, named = render_newsletter(SHOWS, TODAY, SITE, booked)
        self.assertIn("Sponsored. Quarry Lane.", named)
        self.assertNotIn("see the sponsor options", named)
        self.assertNotIn(EMPTY_FRIDAY, named)

        _, later = render_newsletter(SHOWS, date(2026, 12, 4), SITE, {"friday": None})
        self.assertIn(f"{INTRO}\n\n{EMPTY_FRIDAY}\n\n## Coming up", later)

        _, markdown = render_newsletter(SHOWS, TODAY, SITE, {"friday": None})
        _, body = buttondown_draft.split_subject(markdown)
        self.assertIn(EMPTY_FRIDAY, body)
        self.assertNotIn("# Mineral shows", body)

    def test_write_uses_the_issue_friday_filename(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            path = write_newsletter(
                TODAY,
                shows_path=ROOT / "data" / "shows.json",
                site_path=ROOT / "data" / "site.json",
                sponsors_path=ROOT / "data" / "sponsors.json",
                featured_path=ROOT / "data" / "featured.json",
                out_dir=out,
            )
            self.assertEqual(path, out / "newsletter-2026-10-30.md")
            text = path.read_text(encoding="utf-8")
            self.assertIn("Sunbury-on-Thames", text)
            self.assertIn(EMPTY_FRIDAY, text)
            self.assertFalse(banned(text))


class DraftHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        drafts = [email for email in self.server.emails if email.get("status") == "draft"]
        self.server.calls.append(("GET", self.path))
        self._send(200, {"results": drafts, "next": None})

    def do_POST(self):
        payload = self._read()
        self.server.calls.append(("POST", payload.get("status"), payload.get("subject")))
        email = {"id": f"draft-{len(self.server.emails) + 1}", **payload}
        self.server.emails.append(email)
        self._send(201, email)

    def do_PATCH(self):
        payload = self._read()
        email_id = self.path.rstrip("/").rsplit("/", 1)[-1]
        self.server.calls.append(("PATCH", email_id, payload.get("status")))
        for email in self.server.emails:
            if email["id"] == email_id:
                email.update(payload)
                self._send(200, email)
                return
        self._send(404, {"detail": "missing"})

    def _read(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length).decode("utf-8"))
        auth = self.headers.get("Authorization") or ""
        if not auth.startswith("Token "):
            raise AssertionError("missing Token authorisation")
        if body.get("status") != "draft" or body.get("publish_date"):
            raise AssertionError(f"unsafe payload {body}")
        return body

    def _send(self, status: int, payload: dict) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt: str, *args) -> None:
        return


class DraftServer(ThreadingHTTPServer):
    def __init__(self):
        super().__init__(("127.0.0.1", 0), DraftHandler)
        self.emails: list[dict] = []
        self.calls: list[tuple] = []


class ButtondownTests(unittest.TestCase):
    def setUp(self):
        self._saved = os.environ.get("MINERALDIGGER_BUTTONDOWN_API_KEY")
        os.environ.pop("MINERALDIGGER_BUTTONDOWN_API_KEY", None)
        os.environ.pop("BUTTONDOWN_API_KEY", None)

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("MINERALDIGGER_BUTTONDOWN_API_KEY", None)
        else:
            os.environ["MINERALDIGGER_BUTTONDOWN_API_KEY"] = self._saved
        os.environ.pop("BUTTONDOWN_API_KEY", None)

    def test_key_is_mineral_only(self):
        os.environ["BUTTONDOWN_API_KEY"] = "shared-key"
        self.assertIsNone(buttondown_draft.api_key())
        os.environ["MINERALDIGGER_BUTTONDOWN_API_KEY"] = " mineral-key "
        self.assertEqual(buttondown_draft.api_key(), "mineral-key")

    def test_dry_run_makes_no_request(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = write_newsletter(TODAY, out_dir=Path(tmp))
            draft = path.read_text(encoding="utf-8")
            _, body = buttondown_draft.split_subject(draft)
            self.assertIn(EMPTY_FRIDAY, body)
            with mock.patch("buttondown_draft.urllib.request.urlopen", side_effect=AssertionError("network")):
                code, output = run_main(["--file", str(path), "--dry-run"])
            self.assertEqual(code, 0)
            self.assertIn("Dry run. No Buttondown request.", output)
            self.assertIn("Mineral shows for 30 October 2026", output)
            os.environ["BUTTONDOWN_API_KEY"] = "shared-key"
            with mock.patch("buttondown_draft.urllib.request.urlopen", side_effect=AssertionError("network")):
                code, output = run_main(["--file", str(path)])
            self.assertEqual(code, 0)
            self.assertIn("MINERALDIGGER_BUTTONDOWN_API_KEY is not set.", output)

    def test_missing_file_is_quiet(self):
        code, output = run_main(["--file", "/tmp/mineraldigger-no-such-newsletter.md", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("Nothing drafted.", output)

    def test_create_then_update_stays_a_draft(self):
        friday, markdown = render_newsletter(SHOWS, TODAY, SITE)
        subject, body = buttondown_draft.split_subject(markdown)
        self.assertEqual(subject, subject_for(friday))
        self.assertIn("buttondown-editor-mode: plaintext", body)
        self.assertIn(EMPTY_FRIDAY, body)
        self.assertNotIn(f"# {subject}", body)

        server = DraftServer()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            client = buttondown_draft.Buttondown("test-token", base)
            action, email_id = client.save_draft(subject, body)
            self.assertEqual(action, "created")
            self.assertEqual(email_id, "draft-1")
            action, email_id = client.save_draft(subject, body + "\nUpdated line.\n")
            self.assertEqual(action, "updated")
            self.assertEqual(email_id, "draft-1")
            self.assertEqual(len(server.emails), 1)
            self.assertEqual(server.emails[0]["status"], "draft")
            self.assertNotIn("publish_date", server.emails[0])
            methods = [call[0] for call in server.calls]
            self.assertEqual(methods.count("POST"), 1)
            self.assertEqual(methods.count("PATCH"), 1)
        finally:
            server.shutdown()
            server.server_close()

    def test_refuses_to_send(self):
        client = buttondown_draft.Buttondown("test-token", "http://127.0.0.1:9")
        with self.assertRaises(buttondown_draft.ButtondownError):
            client._request("POST", "/emails", {"subject": "x", "body": "y", "status": "sent"})
        with self.assertRaises(buttondown_draft.ButtondownError):
            client._request(
                "POST",
                "/emails",
                {"subject": "x", "body": "y", "status": "draft", "publish_date": "2026-10-30T08:00:00Z"},
            )

    def test_main_against_local_api(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            path = write_newsletter(TODAY, out_dir=Path(tmp))
            server = DraftServer()
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                os.environ["MINERALDIGGER_BUTTONDOWN_API_KEY"] = "test-token"
                code, first = run_main(["--file", str(path), "--api", base])
                self.assertEqual(code, 0)
                self.assertIn("Created Buttondown draft draft-1.", first)
                code, second = run_main(["--file", str(path), "--api", base])
                self.assertEqual(code, 0)
                self.assertIn("Updated Buttondown draft draft-1.", second)
                self.assertEqual(len(server.emails), 1)
                self.assertEqual(server.emails[0]["status"], "draft")
                self.assertIn(EMPTY_FRIDAY, server.emails[0]["body"])
                self.assertNotIn("Sponsored", server.emails[0]["body"])
                self.assertEqual(sum(call[0] == "POST" for call in server.calls), 1)
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    unittest.main()
