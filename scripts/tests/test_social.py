"""Weekly Facebook and Bluesky drafts. No live tokens and no network."""

from __future__ import annotations

import io
import json
import os
import unittest
import urllib.error
import urllib.parse
from contextlib import redirect_stderr, redirect_stdout
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
import sys

sys.path.insert(0, str(ROOT / "scripts"))

import bluesky_post  # noqa: E402
import facebook_post  # noqa: E402
from social_copy import (  # noqa: E402
    BLUESKY_LIMIT,
    BLUESKY_PASSWORD_KEY,
    SocialError,
    build_post,
    fit_bluesky,
    link_facet,
    load_shows,
    password_from_bluesky,
    post_range,
    read_secret_file,
    publish_refusal,
    repeated_slugs,
    token_from_pages,
    user_token_from_pages,
    week_key,
)

TODAY = date(2026, 10, 28)
SHOWS = load_shows(ROOT / "data" / "shows.json")
SITE = "https://mineraldigger.com"
PAGE_ID = "1419817424553579"
TOKEN_KEYS = (
    "MINERALDIGGER_FB_PAGE_TOKEN",
    "MINERALDIGGER_FB_USER_TOKEN",
    "FB_USER_TOKEN",
    "MINERALDIGGER_BLUESKY_APP_PASSWORD",
)


class JsonResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def request_path(request) -> str:
    return urllib.parse.urlparse(request.full_url).path


def banned(value: str) -> bool:
    return (
        "!" in value
        or "\u2014" in value
        or "\u2013" in value
        or "https://" in value.casefold()
        or "Ireland" in value
        or "Unknown" in value
    )


def run_facebook(argv: list[str]) -> tuple[int, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = facebook_post.main(argv)
    return code, stdout.getvalue() + stderr.getvalue()


def run_bluesky(argv: list[str]) -> tuple[int, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = bluesky_post.main(argv)
    return code, stdout.getvalue() + stderr.getvalue()


class EnvGuard(unittest.TestCase):
    def setUp(self):
        self.saved = {key: os.environ.pop(key, None) for key in TOKEN_KEYS}

    def tearDown(self):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class CopyTests(unittest.TestCase):
    def test_week_of_28_october_2026_is_the_next_show(self):
        self.assertEqual(week_key(TODAY), "2026-W44")
        post = build_post(SHOWS, TODAY, SITE)
        self.assertIsNotNone(post)
        self.assertEqual(post["angle"], "next-show")
        self.assertEqual(post["week"], "2026-W44")
        self.assertIn("Rock, Gem & Bead Show", post["facebook"])
        self.assertIn("Kempton Park Racecourse, Sunbury-on-Thames", post["facebook"])
        self.assertIn("Entry £6.", post["facebook"])
        self.assertIn("Saturday 10:00 to 17:00. Sunday 10:00 to 16:00.", post["facebook"])
        shown = "mineraldigger.com/show/rock-gem-and-bead-show-sunbury-on-thames-2026-10-31/"
        self.assertIn(shown, post["facebook"])
        self.assertEqual(post["facebook"].rstrip().splitlines()[-1], shown)
        self.assertEqual(post["bluesky"].rstrip().splitlines()[-1], shown)
        self.assertEqual(post["link"], "https://" + shown)
        self.assertNotIn("https://", post["facebook"])
        self.assertNotIn("https://", post["bluesky"])
        self.assertIn("Entry £6.", post["bluesky"])
        self.assertIn("mineraldigger.com", post["bluesky"])
        self.assertLessEqual(len(post["bluesky"]), BLUESKY_LIMIT)
        self.assertFalse(banned(post["facebook"]))
        self.assertFalse(banned(post["bluesky"]))
        self.assertNotIn("Kidlington", post["facebook"])

    def test_odd_week_leads_with_the_rock_hub(self):
        post = build_post(SHOWS, date(2026, 11, 4), SITE)
        self.assertEqual(post["week"], "2026-W45")
        self.assertEqual(post["angle"], "type-hub")
        self.assertEqual(post["kind"], "rock")
        self.assertEqual(post["link"], "https://mineraldigger.com/rock/")
        self.assertIn("Rock shows on the MineralDigger map.", post["facebook"])
        self.assertIn("Worcester", post["facebook"])
        self.assertNotIn("£", post["facebook"])
        self.assertNotIn("Unknown", post["facebook"])
        self.assertLessEqual(len(post["bluesky"]), BLUESKY_LIMIT)
        self.assertFalse(banned(post["bluesky"]))

    def test_fossil_hub_keeps_the_matched_year(self):
        post = build_post(SHOWS, date(2026, 11, 9), SITE, angle="type-hub", kind="fossil")
        self.assertIn("Haywards Heath", post["facebook"])
        self.assertIn("Entry £5.", post["facebook"])
        self.assertIn("matches the weekday on the organiser page", post["facebook"])
        self.assertNotIn("does not print the year", post["facebook"])
        self.assertEqual(post["link"], "https://mineraldigger.com/fossil/")
        self.assertIn("weekday", post["bluesky"])
        self.assertLessEqual(len(post["bluesky"]), BLUESKY_LIMIT)
        self.assertFalse(banned(post["facebook"]))

    def test_provisional_date_is_labelled_and_has_no_invented_price(self):
        post = build_post(SHOWS, date(2026, 11, 30), SITE, angle="next-show")
        self.assertIn("Brighton", post["facebook"])
        self.assertIn("provisional", post["facebook"])
        self.assertNotIn("£", post["facebook"])
        self.assertFalse(banned(post["facebook"]))
        self.assertLessEqual(len(post["bluesky"]), BLUESKY_LIMIT)

    def test_ireland_shows_are_left_off_the_list(self):
        show = {
            "id": "dublin",
            "slug": "dublin-mineral-show",
            "name": "Dublin Mineral Show",
            "start": "2026-12-01",
            "end": "2026-12-01",
            "types": ["mineral"],
            "venue": {"name": "Hall", "town": "Dublin", "nation": "Ireland"},
            "entry": {"kind": "paid", "label": "Entry £4"},
        }
        self.assertIsNone(build_post([show], date(2026, 11, 1), SITE))

    def test_long_bluesky_text_keeps_the_link(self):
        link = "https://mineraldigger.com/rock/"
        shown = "mineraldigger.com/rock/"
        text = fit_bluesky(["Next on the list is " + ("quartz " * 80), "Entry £6.", "Saturday 10:00 to 17:00."], link)
        self.assertLessEqual(len(text), BLUESKY_LIMIT)
        self.assertTrue(text.endswith(shown))
        self.assertIn(".\n\n" + shown, text)
        self.assertNotIn("https://", text)
        self.assertFalse(banned(text))

    def test_link_facet_counts_utf8_bytes(self):
        url = "https://mineraldigger.com/"
        shown = "mineraldigger.com/"
        text = f"Entry £6.\n\n{shown}"
        facet = link_facet(text, url)
        self.assertEqual(facet["index"]["byteStart"], len("Entry £6.\n\n".encode("utf-8")))
        self.assertEqual(facet["index"]["byteEnd"], len(text.encode("utf-8")))
        self.assertEqual(facet["features"][0]["uri"], url)


class SecretShapeTests(unittest.TestCase):
    def test_page_token_matches_this_page_only(self):
        page_id = PAGE_ID
        self.assertEqual(token_from_pages({page_id: "flat-token"}, page_id), "flat-token")
        self.assertEqual(
            token_from_pages({"mineraldigger": {"page_id": page_id, "access_token": "object-token"}}, page_id),
            "object-token",
        )
        self.assertEqual(
            token_from_pages({"pages": [{"id": page_id, "token": "list-token"}]}, page_id),
            "list-token",
        )
        self.assertIsNone(token_from_pages({"fairdigger": {"page_id": "1", "access_token": "fair"}}, page_id))
        self.assertIsNone(
            token_from_pages({"mineraldigger": {"page_id": "999", "access_token": "wrong-page"}}, page_id)
        )
        user_only = {"fb_user_token": {"page_id": page_id, "access_token": "user-secret"}}
        self.assertIsNone(token_from_pages(user_only, page_id))
        self.assertEqual(user_token_from_pages(user_only), "user-secret")

    def test_bluesky_password_matches_the_handle_only(self):
        handle = "mineraldigger.com"
        self.assertEqual(password_from_bluesky({handle: "app-pass"}, handle), "app-pass")
        self.assertEqual(
            password_from_bluesky({"handle": handle, "app_password": "nested"}, handle),
            "nested",
        )
        self.assertEqual(
            password_from_bluesky({"accounts": [{"handle": handle, "app_password": "from-list"}]}, handle),
            "from-list",
        )
        self.assertIsNone(password_from_bluesky({"fairdigger.co.uk": "fair-pass"}, handle))
        self.assertEqual(
            password_from_bluesky({BLUESKY_PASSWORD_KEY: "named-pass", "fairdigger.co.uk": "fair-pass"}, handle),
            "named-pass",
        )
        self.assertIsNone(password_from_bluesky({BLUESKY_PASSWORD_KEY: "named-pass"}, "fairdigger.co.uk"))


class FacebookFlowTests(EnvGuard):
    def test_repo_page_id(self):
        page = json.loads((ROOT / "growth" / "facebook_page.json").read_text(encoding="utf-8"))
        self.assertEqual(page["page_id"], PAGE_ID)
        log = json.loads((ROOT / "growth" / "facebook_posts.json").read_text(encoding="utf-8"))
        self.assertIsInstance(log, dict)

    def test_dry_run_prints_the_draft_and_leaves_the_log(self):
        with TemporaryDirectory() as tmp:
            log = Path(tmp) / "facebook_posts.json"
            log.write_text("{}\n", encoding="utf-8")
            before = log.read_text(encoding="utf-8")
            os.environ["MINERALDIGGER_FB_PAGE_TOKEN"] = "super-secret-token"
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network")):
                code, output = run_facebook(["--today", "2026-10-28", "--log", str(log), "--shows", str(ROOT / "data" / "shows.json")])
            self.assertEqual(code, 0)
            self.assertIn("Dry run. Nothing posted.", output)
            self.assertIn("2026-W44", output)
            self.assertIn("Sunbury-on-Thames", output)
            self.assertNotIn("super-secret-token", output)
            self.assertEqual(log.read_text(encoding="utf-8"), before)

    def test_publish_uses_the_page_and_records_the_week(self):
        with TemporaryDirectory() as tmp:
            log = Path(tmp) / "facebook_posts.json"
            secrets = Path(tmp) / "fb_pages.json"
            secrets.write_text(json.dumps({PAGE_ID: "from-file", "111": "other-page"}), encoding="utf-8")
            calls = []
            posted = {}

            def fake_urlopen(request, timeout=30):
                calls.append(request)
                self.assertNotIn("from-file", request.full_url)
                if request.get_method() == "GET":
                    self.assertEqual(request.get_header("Authorization"), "Bearer from-file")
                    path = request_path(request)
                    if path.endswith("/posts"):
                        self.assertFalse(path.endswith("/feed"))
                        return JsonResponse({"data": []})
                    self.assertIn(f"{PAGE_ID}_555", path)
                    return JsonResponse(
                        {
                            "id": f"{PAGE_ID}_555",
                            "message": posted["message"],
                            "attachments": {"data": [{"unshimmed_url": posted["link"]}]},
                        }
                    )
                payload = json.loads(request.data.decode("utf-8"))
                self.assertEqual(payload["access_token"], "from-file")
                self.assertIn("mineraldigger.com", payload["message"])
                self.assertNotIn("https://", payload["message"])
                self.assertNotIn("!", payload["message"])
                self.assertTrue(payload["link"].startswith("https://mineraldigger.com/"))
                self.assertEqual(payload["message"].rstrip().splitlines()[-1], payload["link"].removeprefix("https://"))
                self.assertTrue(payload["published"])
                self.assertTrue(request_path(request).endswith("/feed"))
                posted["message"] = payload["message"]
                posted["link"] = payload["link"]
                return JsonResponse({"id": f"{PAGE_ID}_555"})

            with mock.patch("urllib.request.urlopen", fake_urlopen):
                code, output = run_facebook(
                    [
                        "--today",
                        "2026-10-28",
                        "--publish",
                        "--log",
                        str(log),
                        "--secrets",
                        str(secrets),
                        "--page-file",
                        str(ROOT / "growth" / "facebook_page.json"),
                    ]
                )
            self.assertEqual(code, 0, output)
            self.assertEqual(len(calls), 3)
            self.assertTrue(request_path(calls[0]).endswith("/posts"))
            self.assertTrue(request_path(calls[1]).endswith("/feed"))
            self.assertIn(f"{PAGE_ID}_555", request_path(calls[2]))
            saved = json.loads(log.read_text(encoding="utf-8"))
            self.assertIn("2026-W44", saved)
            self.assertEqual(saved["2026-W44"]["post_id"], f"{PAGE_ID}_555")
            self.assertNotIn("from-file", log.read_text(encoding="utf-8"))
            self.assertIn("Sunbury-on-Thames", saved["2026-W44"]["text"])

            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("second post")):
                again, message = run_facebook(["--today", "2026-10-28", "--publish", "--log", str(log), "--secrets", str(secrets)])
            self.assertEqual(again, 1)
            self.assertIn("already in", message)
            self.assertIn("--force", message)

    def test_env_token_is_preferred_and_errors_are_redacted(self):
        with TemporaryDirectory() as tmp:
            log = Path(tmp) / "facebook_posts.json"
            secrets = Path(tmp) / "fb_pages.json"
            secrets.write_text(json.dumps({PAGE_ID: "from-file"}), encoding="utf-8")
            os.environ["MINERALDIGGER_FB_PAGE_TOKEN"] = "from-env"

            def fake_urlopen(request, timeout=30):
                if request.data:
                    payload = json.loads(request.data.decode("utf-8"))
                    self.assertEqual(payload["access_token"], "from-env")
                body = json.dumps({"error": {"message": "bad from-env"}}).encode("utf-8")
                raise urllib.error.HTTPError(request.full_url, 400, "Bad", None, io.BytesIO(body))

            with mock.patch("urllib.request.urlopen", fake_urlopen):
                code, output = run_facebook(
                    ["--today", "2026-10-28", "--publish", "--log", str(log), "--secrets", str(secrets)]
                )
            self.assertEqual(code, 1)
            self.assertIn("[redacted]", output)
            self.assertNotIn("from-env", output)
            self.assertFalse(log.exists())

    def test_publish_without_a_token_stops(self):
        with TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.json"
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network")):
                code, output = run_facebook(
                    ["--today", "2026-10-28", "--publish", "--log", str(Path(tmp) / "log.json"), "--secrets", str(missing)]
                )
            self.assertEqual(code, 1)
            self.assertIn("MINERALDIGGER_FB_PAGE_TOKEN", output)

    def test_force_replaces_one_week_and_keeps_the_rest(self):
        with TemporaryDirectory() as tmp:
            log = Path(tmp) / "facebook_posts.json"
            log.write_text(
                json.dumps(
                    {
                        "2026-W43": {"week": "2026-W43", "text": "keep me"},
                        "2026-W44": {"week": "2026-W44", "text": "old"},
                    }
                ),
                encoding="utf-8",
            )
            os.environ["MINERALDIGGER_FB_PAGE_TOKEN"] = "token-1"
            calls = []
            posted = {}

            def fake_urlopen(request, timeout=30):
                calls.append(request.get_method() + " " + request_path(request))
                if request.get_method() == "POST":
                    payload = json.loads(request.data.decode("utf-8"))
                    posted["message"] = payload["message"]
                    posted["link"] = payload["link"]
                    return JsonResponse({"id": f"{PAGE_ID}_9"})
                return JsonResponse(
                    {
                        "id": f"{PAGE_ID}_9",
                        "message": posted["message"],
                        "attachments": {"data": [{"unshimmed_url": posted["link"]}]},
                    }
                )

            with mock.patch("urllib.request.urlopen", fake_urlopen):
                code, output = run_facebook(["--today", "2026-10-28", "--publish", "--force", "--log", str(log)])
            self.assertEqual(code, 0, output)
            self.assertEqual(
                calls,
                [f"POST /v23.0/{PAGE_ID}/feed", f"GET /v23.0/{PAGE_ID}_9"],
            )
            saved = json.loads(log.read_text(encoding="utf-8"))
            self.assertEqual(saved["2026-W43"]["text"], "keep me")
            self.assertEqual(saved["2026-W44"]["post_id"], f"{PAGE_ID}_9")
            self.assertNotIn("token-1", log.read_text(encoding="utf-8"))


class BlueskyFlowTests(EnvGuard):
    def test_repo_log_is_an_object(self):
        log = json.loads((ROOT / "growth" / "bluesky_posts.json").read_text(encoding="utf-8"))
        self.assertIsInstance(log, dict)

    def test_dry_run_matches_the_facebook_week(self):
        with TemporaryDirectory() as tmp:
            log = Path(tmp) / "bluesky_posts.json"
            before_missing = not log.exists()
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network")):
                code, output = run_bluesky(["--today", "2026-10-28", "--log", str(log)])
            self.assertEqual(code, 0)
            self.assertIn("Dry run. Nothing posted.", output)
            self.assertIn("2026-W44", output)
            self.assertIn("mineraldigger.com", output)
            self.assertTrue(before_missing)
            self.assertFalse(log.exists())

    def test_publish_checks_the_handle_and_the_week_key(self):
        with TemporaryDirectory() as tmp:
            log = Path(tmp) / "bluesky_posts.json"
            secrets = Path(tmp) / "bluesky.json"
            secrets.write_text(
                json.dumps({"fairdigger.co.uk": "fair-pass", "mineraldigger.com": "mineral-pass"}),
                encoding="utf-8",
            )
            calls = []
            sent = {}

            def fake_urlopen(request, timeout=30):
                calls.append(request)
                if request.get_method() == "GET":
                    self.assertIsNone(request.get_header("Authorization"))
                    self.assertNotIn("mineral-pass", request.full_url)
                    self.assertIn("app.bsky.feed.getPosts", request.full_url)
                    record = sent["record"]
                    return JsonResponse(
                        {
                            "posts": [
                                {
                                    "uri": "at://did:plc:mineral/app.bsky.feed.post/rkey1",
                                    "author": {"handle": "mineraldigger.com"},
                                    "record": {
                                        "text": record["text"],
                                        "facets": record.get("facets"),
                                        "embed": record.get("embed"),
                                    },
                                }
                            ]
                        }
                    )
                payload = json.loads(request.data.decode("utf-8"))
                if request.full_url.endswith("createSession"):
                    self.assertEqual(payload["identifier"], "mineraldigger.com")
                    self.assertEqual(payload["password"], "mineral-pass")

                    class Response:
                        def __enter__(self):
                            return self

                        def __exit__(self, *args):
                            return False

                        def read(self):
                            return json.dumps(
                                {"accessJwt": "jwt-1", "did": "did:plc:mineral", "handle": "mineraldigger.com"}
                            ).encode("utf-8")

                    return Response()
                self.assertTrue(request.full_url.endswith("createRecord"))
                self.assertEqual(request.get_header("Authorization"), "Bearer jwt-1")
                self.assertNotIn("mineral-pass", request.data.decode("utf-8"))
                record = payload["record"]
                self.assertLessEqual(len(record["text"]), BLUESKY_LIMIT)
                self.assertIn("mineraldigger.com", record["text"])
                self.assertNotIn("https://", record["text"])
                self.assertNotIn("!", record["text"])
                self.assertEqual(record["langs"], ["en-GB"])
                facet = record["facets"][0]
                shown = record["text"].rstrip().splitlines()[-1]
                start = record["text"].rfind(shown)
                self.assertEqual(facet["index"]["byteStart"], len(record["text"][:start].encode("utf-8")))
                self.assertEqual(
                    facet["index"]["byteEnd"],
                    len(record["text"][:start].encode("utf-8")) + len(shown.encode("utf-8")),
                )
                self.assertEqual(facet["features"][0]["uri"], "https://" + shown)
                self.assertEqual(record["embed"]["external"]["uri"], "https://" + shown)
                self.assertNotIn("https://", record["embed"]["external"]["description"])
                self.assertEqual(payload["repo"], "did:plc:mineral")
                self.assertEqual(payload["collection"], "app.bsky.feed.post")
                sent["record"] = record

                class Created:
                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        return False

                    def read(self):
                        return json.dumps(
                            {"uri": "at://did:plc:mineral/app.bsky.feed.post/rkey1", "cid": "cid1"}
                        ).encode("utf-8")

                return Created()

            with mock.patch("urllib.request.urlopen", fake_urlopen), mock.patch.object(
                bluesky_post, "fetch_recent_posts", return_value=[]
            ):
                code, output = run_bluesky(
                    ["--today", "2026-10-28", "--publish", "--log", str(log), "--secrets", str(secrets)]
                )
            self.assertEqual(code, 0, output)
            self.assertEqual(len(calls), 3)
            saved = json.loads(log.read_text(encoding="utf-8"))
            self.assertEqual(saved["2026-W44"]["url"], "https://bsky.app/profile/mineraldigger.com/post/rkey1")
            raw = log.read_text(encoding="utf-8")
            self.assertNotIn("mineral-pass", raw)
            self.assertNotIn("jwt-1", raw)
            self.assertNotIn("fair-pass", raw)

            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("duplicate")), mock.patch.object(
                bluesky_post, "fetch_recent_posts", return_value=[]
            ):
                again, message = run_bluesky(
                    ["--today", "2026-10-28", "--publish", "--log", str(log), "--secrets", str(secrets)]
                )
            self.assertEqual(again, 1)
            self.assertIn("2026-W44", message)

    def test_wrong_handle_is_not_posted(self):
        with TemporaryDirectory() as tmp:
            log = Path(tmp) / "bluesky_posts.json"
            os.environ["MINERALDIGGER_BLUESKY_APP_PASSWORD"] = "app-pass"
            calls = []

            def fake_urlopen(request, timeout=30):
                calls.append(request.full_url)

                class Response:
                    def __enter__(self):
                        return self

                    def __exit__(self, *args):
                        return False

                    def read(self):
                        return json.dumps(
                            {"accessJwt": "jwt-1", "did": "did:plc:fair", "handle": "fairdigger.co.uk"}
                        ).encode("utf-8")

                return Response()

            with mock.patch("urllib.request.urlopen", fake_urlopen), mock.patch.object(
                bluesky_post, "fetch_recent_posts", return_value=[]
            ):
                code, output = run_bluesky(["--today", "2026-10-28", "--publish", "--log", str(log)])
            self.assertEqual(code, 1)
            self.assertEqual(calls, ["https://bsky.social/xrpc/com.atproto.server.createSession"])
            self.assertIn("fairdigger.co.uk", output)
            self.assertIn("Nothing posted", output)
            self.assertNotIn("app-pass", output)
            self.assertFalse(log.exists())



KEMPTON = "rock-gem-and-bead-show-sunbury-on-thames-2026-10-31"
KEMPTON_POSTS = [
    {"text": "Next up: Kempton Park this weekend, Worcester 7 and 8 November.", "links": [], "posted_at": "2026-10-27T09:28:29Z"},
    {"text": "On this weekend: Rock, Gem & Bead Show at Kempton Park Racecourse.",
     "links": [f"https://mineraldigger.com/show/{KEMPTON}/"], "posted_at": "2026-10-31T09:57:01Z"},
]


class DatesAndRepeats(EnvGuard):
    def test_dates_sit_next_to_their_weekday(self):
        self.assertEqual(post_range(date(2026, 11, 7), date(2026, 11, 8), TODAY), "Saturday 7 and Sunday 8 November")
        self.assertEqual(post_range(date(2026, 11, 7), date(2026, 11, 7), TODAY), "Saturday 7 November")
        self.assertEqual(
            post_range(date(2026, 10, 31), date(2026, 11, 1), TODAY), "Saturday 31 October to Sunday 1 November"
        )
        self.assertEqual(post_range(date(2027, 1, 9), date(2027, 1, 10), TODAY), "Saturday 9 and Sunday 10 January 2027")
        post = build_post(SHOWS, TODAY, SITE)
        self.assertIn("Saturday 31 October to Sunday 1 November", post["bluesky"])
        self.assertNotIn("https://", post["bluesky"])
        self.assertNotIn("2026", post["bluesky"].split("mineraldigger.com")[0])

    def test_a_show_posted_in_the_last_14_days_is_passed_over(self):
        skip = repeated_slugs(SHOWS, KEMPTON_POSTS, date(2026, 10, 31))
        self.assertIn(KEMPTON, skip)
        self.assertNotIn("Worcester", " ".join(skip).title())
        post = build_post(SHOWS, date(2026, 10, 31), SITE, angle="next-show", skip=skip)
        self.assertNotIn("Kempton", post["bluesky"])
        self.assertNotIn(KEMPTON, post["link"])

    def test_the_guard_lapses_after_14_days(self):
        self.assertEqual(repeated_slugs(SHOWS, KEMPTON_POSTS[:1], date(2026, 11, 11)) & {KEMPTON}, set())

    def test_publish_stops_when_the_feed_cannot_be_read(self):
        with TemporaryDirectory() as tmp:
            log = Path(tmp) / "bluesky_posts.json"
            os.environ["MINERALDIGGER_BLUESKY_APP_PASSWORD"] = "app-pass"
            with mock.patch("urllib.request.urlopen", side_effect=urllib.error.URLError("offline")):
                code, output = run_bluesky(["--today", "2026-10-31", "--publish", "--log", str(log)])
            self.assertEqual(code, 1)
            self.assertIn("Nothing posted", output)
            self.assertFalse(log.exists())

    def test_dry_run_reports_the_repeat(self):
        with TemporaryDirectory() as tmp:
            log = Path(tmp) / "bluesky_posts.json"
            with mock.patch.object(bluesky_post, "fetch_recent_posts", return_value=KEMPTON_POSTS):
                code, output = run_bluesky(["--today", "2026-10-31", "--angle", "next-show", "--log", str(log)])
            self.assertEqual(code, 0)
            self.assertIn(KEMPTON, output.split("Bluesky:")[0])
            self.assertNotIn("Kempton", output.split("Bluesky:")[1])
            self.assertNotIn("https://", output.split("Bluesky:")[1])

    def test_allow_repeat_keeps_the_recent_show(self):
        with TemporaryDirectory() as tmp:
            log = Path(tmp) / "bluesky_posts.json"
            with mock.patch.object(bluesky_post, "fetch_recent_posts", return_value=KEMPTON_POSTS):
                code, output = run_bluesky(
                    ["--today", "2026-10-31", "--angle", "next-show", "--allow-repeat", "--log", str(log)]
                )
            self.assertEqual(code, 0)
            self.assertIn("Kempton", output.split("Bluesky:")[1])
            self.assertNotIn("Passing over", output)
            self.assertFalse(log.exists())


def _forbidden_post(text: str) -> dict:
    return {
        "week": "2026-W44",
        "angle": "next-show",
        "kind": None,
        "link": "https://mineraldigger.com/rock/",
        "facebook": text,
        "bluesky": text,
        "show_id": "x",
        "show_slug": "x",
    }


class PublishRefusalTests(EnvGuard):
    def test_both_scripts_refuse_forbidden_text_and_do_not_post(self):
        samples = (
            "See you there!",
            "Open 10\u201316.",
            "Open 10\u201416.",
            "Details at https://mineraldigger.com/rock/",
            "Details at HTTPS://mineraldigger.com/rock/",
            "Stamp fairs are now on FairDigger.\n\nfairdigger.co.uk/stamps",
            "New on AuctionDigger.\n\nauctiondigger.ie",
        )
        for text in samples:
            post = _forbidden_post(text)
            with TemporaryDirectory() as tmp:
                log = Path(tmp) / "posts.json"
                with mock.patch.object(bluesky_post, "fetch_recent_posts", return_value=[]), mock.patch.object(
                    bluesky_post, "build_post", return_value=post
                ), mock.patch("urllib.request.urlopen", side_effect=AssertionError("posted")):
                    code, output = run_bluesky(["--today", "2026-10-28", "--publish", "--log", str(log)])
                self.assertEqual(code, 1, text)
                self.assertIn("Refusing to publish", output)
                self.assertFalse(log.exists())

                with mock.patch.object(facebook_post, "build_post", return_value=post), mock.patch(
                    "urllib.request.urlopen", side_effect=AssertionError("posted")
                ):
                    code, output = run_facebook(["--today", "2026-10-28", "--publish", "--log", str(log)])
                self.assertEqual(code, 1, text)
                self.assertIn("Refusing to publish", output)
                self.assertFalse(log.exists())


def _graph_error(request, message: str, status: int = 400):
    body = json.dumps({"error": {"message": message}}).encode("utf-8")
    raise urllib.error.HTTPError(request.full_url, status, "Bad", None, io.BytesIO(body))


class CredentialLookupTests(EnvGuard):
    def test_secret_file_reads_text_or_json_and_hides_a_broken_file(self):
        with TemporaryDirectory() as tmp:
            plain = Path(tmp) / "mineraldigger_bluesky_app_password"
            plain.write_text("  app-pass  \n", encoding="utf-8")
            self.assertEqual(read_secret_file(plain, ("app_password",)), "app-pass")
            shaped = Path(tmp) / "fb_user_token"
            shaped.write_text(json.dumps({"access_token": "json-user"}), encoding="utf-8")
            self.assertEqual(read_secret_file(shaped, ("access_token", "token")), "json-user")
            nested = Path(tmp) / "nested.json"
            nested.write_text(
                json.dumps({BLUESKY_PASSWORD_KEY: {"app_password": "nested-pass"}}),
                encoding="utf-8",
            )
            self.assertEqual(
                read_secret_file(nested, ("app_password", BLUESKY_PASSWORD_KEY)),
                "nested-pass",
            )
            broken = Path(tmp) / "broken"
            broken.write_text('{"access_token": "LEAKME"', encoding="utf-8")
            with self.assertRaises(SocialError) as caught:
                read_secret_file(broken, ("access_token",))
            self.assertNotIn("LEAKME", str(caught.exception))
            self.assertIn("not valid JSON", str(caught.exception))

    def test_facebook_env_page_token_wins_and_does_not_call_graph(self):
        with TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "fb_pages.json"
            secrets.write_text(json.dumps({PAGE_ID: "from-file", "fb_user_token": "from-key"}), encoding="utf-8")
            (Path(tmp) / "fb_user_token").write_text("from-user-file\n", encoding="utf-8")
            os.environ["MINERALDIGGER_FB_PAGE_TOKEN"] = "from-env"
            os.environ["FB_USER_TOKEN"] = "from-user-env"
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("graph")):
                token = facebook_post.resolve_token(PAGE_ID, secrets)
            self.assertEqual(token, "from-env")

    def test_facebook_pages_file_wins_over_a_user_token(self):
        with TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "fb_pages.json"
            secrets.write_text(
                json.dumps({PAGE_ID: "from-file", "fb_user_token": "from-key"}),
                encoding="utf-8",
            )
            (Path(tmp) / "fb_user_token").write_text("from-user-file\n", encoding="utf-8")
            os.environ["FB_USER_TOKEN"] = "from-user-env"
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("graph")):
                token = facebook_post.resolve_token(PAGE_ID, secrets)
            self.assertEqual(token, "from-file")

    def _derived(self, request, user_token: str, page_token: str):
        self.assertNotIn(user_token, request.full_url)
        self.assertNotIn(page_token, request.full_url)
        self.assertEqual(request.get_header("Authorization"), f"Bearer {user_token}")
        self.assertEqual(request.get_method(), "GET")
        path = request_path(request)
        self.assertFalse(path.endswith("/feed"))
        if path.endswith("/accounts"):
            return JsonResponse(
                {"data": [{"id": "111", "access_token": "other-page-secret"}, {"id": PAGE_ID, "access_token": page_token}]}
            )
        self.assertTrue(path.endswith("/" + PAGE_ID))
        return JsonResponse({"id": PAGE_ID})

    def test_facebook_user_token_env_is_exchanged_for_the_page(self):
        with TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "fb_pages.json"
            secrets.write_text(json.dumps({"fb_user_token": "from-key"}), encoding="utf-8")
            (Path(tmp) / "fb_user_token").write_text("from-user-file\n", encoding="utf-8")
            os.environ["FB_USER_TOKEN"] = "shared-user"
            os.environ["MINERALDIGGER_FB_USER_TOKEN"] = "mineral-user"
            with mock.patch("urllib.request.urlopen", lambda request, timeout=30: self._derived(request, "mineral-user", "derived-page")):
                token = facebook_post.resolve_token(PAGE_ID, secrets)
            self.assertEqual(token, "derived-page")

    def test_facebook_shared_user_token_env_is_used_when_the_mineral_one_is_unset(self):
        with TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "fb_pages.json"
            os.environ["FB_USER_TOKEN"] = "shared-user"

            def fake_urlopen(request, timeout=30):
                self.assertEqual(request.get_header("Authorization"), "Bearer shared-user")
                return JsonResponse({"access_token": "derived-page", "id": PAGE_ID})

            with mock.patch("urllib.request.urlopen", fake_urlopen):
                token = facebook_post.resolve_token(PAGE_ID, secrets)
            self.assertEqual(token, "derived-page")

    def test_facebook_user_token_key_uses_accounts_when_the_page_field_is_empty(self):
        with TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "fb_pages.json"
            secrets.write_text(json.dumps({"111": "other-page-secret", "fb_user_token": "from-key"}), encoding="utf-8")
            calls = []

            def fake_urlopen(request, timeout=30):
                calls.append(request_path(request))
                return self._derived(request, "from-key", "derived-page")

            with mock.patch("urllib.request.urlopen", fake_urlopen):
                token = facebook_post.resolve_token(PAGE_ID, secrets)
            self.assertEqual(token, "derived-page")
            self.assertTrue(calls[0].endswith("/" + PAGE_ID))
            self.assertTrue(calls[1].endswith("/accounts"))
            self.assertNotIn("other-page-secret", token)

    def test_facebook_user_token_file_is_exchanged_without_calling_accounts(self):
        with TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "missing-pages.json"
            (Path(tmp) / "fb_user_token").write_text(json.dumps({"fb_user_token": "file-user"}), encoding="utf-8")
            calls = []

            def fake_urlopen(request, timeout=30):
                calls.append(request_path(request))
                self.assertEqual(request.get_header("Authorization"), "Bearer file-user")
                self.assertNotIn("file-user", request.full_url)
                return JsonResponse({"access_token": "derived-page", "id": PAGE_ID})

            with mock.patch("urllib.request.urlopen", fake_urlopen):
                token = facebook_post.resolve_token(PAGE_ID, secrets)
            self.assertEqual(token, "derived-page")
            self.assertEqual(len(calls), 1)
            self.assertTrue(calls[0].endswith("/" + PAGE_ID))

    def test_facebook_user_token_that_cannot_mint_a_page_token_is_redacted(self):
        with TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "fb_pages.json"
            secrets.write_text("{}\n", encoding="utf-8")
            (Path(tmp) / "fb_user_token").write_text("USERSECRET\n", encoding="utf-8")

            def fake_urlopen(request, timeout=30):
                self.assertNotIn("USERSECRET", request.full_url)
                _graph_error(request, "Invalid OAuth access token USERSECRET")

            with mock.patch("urllib.request.urlopen", fake_urlopen):
                code, output = run_facebook(
                    ["--today", "2026-10-28", "--publish", "--log", str(Path(tmp) / "log.json"), "--secrets", str(secrets)]
                )
            self.assertEqual(code, 1)
            self.assertNotIn("USERSECRET", output)
            self.assertIn("[redacted]", output)
            self.assertIn(f"/{PAGE_ID}", output)
            self.assertIn("/me/accounts", output)
            self.assertIn("Nothing posted", output)
            self.assertFalse((Path(tmp) / "log.json").exists())

    def test_facebook_missing_everything_names_each_place_and_prints_no_value(self):
        with TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "fb_pages.json"
            secrets.write_text(json.dumps({"111": "OTHERPAGESECRET"}), encoding="utf-8")
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("graph")):
                code, output = run_facebook(
                    ["--today", "2026-10-28", "--publish", "--log", str(Path(tmp) / "log.json"), "--secrets", str(secrets)]
                )
            self.assertEqual(code, 1)
            self.assertIn("MINERALDIGGER_FB_PAGE_TOKEN", output)
            self.assertIn("fb_pages.json", output)
            self.assertIn("fb_user_token", output)
            self.assertIn("MINERALDIGGER_FB_USER_TOKEN or FB_USER_TOKEN", output)
            self.assertIn(PAGE_ID, output)
            self.assertIn("Values are not printed.", output)
            self.assertNotIn("OTHERPAGESECRET", output)
            self.assertFalse((Path(tmp) / "log.json").exists())

    def test_broken_user_token_file_does_not_print_its_contents(self):
        with TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "fb_pages.json"
            (Path(tmp) / "fb_user_token").write_text('{"access_token": "SECRETVALUE"', encoding="utf-8")
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("graph")):
                code, output = run_facebook(
                    ["--today", "2026-10-28", "--publish", "--log", str(Path(tmp) / "log.json"), "--secrets", str(secrets)]
                )
            self.assertEqual(code, 1)
            self.assertIn("not valid JSON", output)
            self.assertNotIn("SECRETVALUE", output)

    def test_bluesky_env_password_wins(self):
        with TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "bluesky.json"
            secrets.write_text(json.dumps({"mineraldigger.com": "from-json"}), encoding="utf-8")
            (Path(tmp) / BLUESKY_PASSWORD_KEY).write_text("from-file\n", encoding="utf-8")
            os.environ["MINERALDIGGER_BLUESKY_APP_PASSWORD"] = "from-env"
            self.assertEqual(bluesky_post.resolve_password(secrets), "from-env")

    def test_bluesky_json_handle_is_used_when_the_env_is_unset(self):
        with TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "bluesky.json"
            secrets.write_text(
                json.dumps({"fairdigger.co.uk": "fair-pass", "mineraldigger.com": "from-json"}),
                encoding="utf-8",
            )
            (Path(tmp) / BLUESKY_PASSWORD_KEY).write_text("from-file\n", encoding="utf-8")
            self.assertEqual(bluesky_post.resolve_password(secrets), "from-json")

    def test_bluesky_named_key_is_used_when_the_handle_is_absent(self):
        with TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "bluesky.json"
            secrets.write_text(
                json.dumps({"fairdigger.co.uk": "fair-pass", BLUESKY_PASSWORD_KEY: "from-key"}),
                encoding="utf-8",
            )
            self.assertEqual(bluesky_post.resolve_password(secrets), "from-key")

    def test_bluesky_named_secret_file_is_used_when_bluesky_json_is_missing(self):
        with TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "bluesky.json"
            named = Path(tmp) / BLUESKY_PASSWORD_KEY
            named.write_text(json.dumps({"app_password": "from-file"}), encoding="utf-8")
            self.assertEqual(bluesky_post.resolve_password(secrets), "from-file")

    def test_bluesky_missing_everything_names_each_place_and_prints_no_value(self):
        with TemporaryDirectory() as tmp:
            secrets = Path(tmp) / "bluesky.json"
            secrets.write_text(json.dumps({"fairdigger.co.uk": "fair-pass"}), encoding="utf-8")
            log = Path(tmp) / "bluesky_posts.json"
            with mock.patch.object(bluesky_post, "fetch_recent_posts", return_value=[]), mock.patch(
                "urllib.request.urlopen", side_effect=AssertionError("posted")
            ):
                code, output = run_bluesky(
                    ["--today", "2026-10-28", "--publish", "--log", str(log), "--secrets", str(secrets)]
                )
            self.assertEqual(code, 1)
            self.assertIn("MINERALDIGGER_BLUESKY_APP_PASSWORD", output)
            self.assertIn("bluesky.json", output)
            self.assertIn("mineraldigger.com", output)
            self.assertIn(BLUESKY_PASSWORD_KEY, output)
            self.assertIn("Values are not printed.", output)
            self.assertNotIn("fair-pass", output)
            self.assertFalse(log.exists())


class DuplicateCheckTests(EnvGuard):
    def test_posts_endpoint_blocks_a_link_already_on_the_page(self):
        with TemporaryDirectory() as tmp:
            os.environ["MINERALDIGGER_FB_PAGE_TOKEN"] = "PAGESECRET"
            post = build_post(SHOWS, TODAY, SITE)
            calls = []

            def fake_urlopen(request, timeout=30):
                calls.append(request)
                self.assertEqual(request.get_method(), "GET")
                self.assertTrue(request_path(request).endswith("/posts"))
                self.assertFalse(request_path(request).endswith("/feed"))
                self.assertNotIn("PAGESECRET", request.full_url)
                self.assertEqual(request.get_header("Authorization"), "Bearer PAGESECRET")
                return JsonResponse(
                    {
                        "data": [
                            {
                                "id": f"{PAGE_ID}_77",
                                "message": "UNIQUEPAGEBODY " + post["link"],
                                "permalink_url": "https://www.facebook.com/example/posts/77",
                            }
                        ]
                    }
                )

            with mock.patch("urllib.request.urlopen", fake_urlopen):
                code, output = run_facebook(
                    ["--today", "2026-10-28", "--publish", "--log", str(Path(tmp) / "log.json")]
                )
            self.assertEqual(code, 1)
            self.assertEqual(len(calls), 1)
            self.assertIn(f"post {PAGE_ID}_77", output)
            self.assertIn("--force", output)
            self.assertIn("Nothing posted", output)
            self.assertNotIn("PAGESECRET", output)
            self.assertNotIn("UNIQUEPAGEBODY", output)
            self.assertFalse((Path(tmp) / "log.json").exists())

    def test_posts_failure_uses_the_log_and_still_publishes(self):
        with TemporaryDirectory() as tmp:
            os.environ["MINERALDIGGER_FB_PAGE_TOKEN"] = "PAGESECRET"
            log = Path(tmp) / "facebook_posts.json"
            calls = []
            posted = {}

            def fake_urlopen(request, timeout=30):
                path = request_path(request)
                calls.append((request.get_method(), path))
                self.assertNotIn("PAGESECRET", request.full_url)
                if request.get_method() == "GET" and path.endswith("/posts"):
                    self.assertFalse(path.endswith("/feed"))
                    _graph_error(request, "(#200) Requires pages_read_engagement permission to read this Page.")
                if request.get_method() == "GET":
                    return JsonResponse(
                        {
                            "id": f"{PAGE_ID}_9",
                            "message": posted["message"],
                            "attachments": {"data": [{"unshimmed_url": posted["link"]}]},
                        }
                    )
                payload = json.loads(request.data.decode("utf-8"))
                posted["message"] = payload["message"]
                posted["link"] = payload["link"]
                self.assertTrue(path.endswith("/feed"))
                return JsonResponse({"id": f"{PAGE_ID}_9"})

            with mock.patch("urllib.request.urlopen", fake_urlopen):
                code, output = run_facebook(["--today", "2026-10-28", "--publish", "--log", str(log)])
            self.assertEqual(code, 0, output)
            self.assertEqual(
                calls,
                [
                    ("GET", f"/v23.0/{PAGE_ID}/posts"),
                    ("POST", f"/v23.0/{PAGE_ID}/feed"),
                    ("GET", f"/v23.0/{PAGE_ID}_9"),
                ],
            )
            self.assertIn("duplicate check used the log only", output)
            self.assertIn("/posts", output)
            self.assertIn("pages_read_engagement", output)
            self.assertNotIn("PAGESECRET", output)
            saved = json.loads(log.read_text(encoding="utf-8"))
            self.assertEqual(saved["2026-W44"]["post_id"], f"{PAGE_ID}_9")
            self.assertNotIn("PAGESECRET", log.read_text(encoding="utf-8"))

    def test_nested_link_counts_as_the_same_post(self):
        link = "https://mineraldigger.com/rock/"
        found = facebook_post.matching_page_post(
            [{"id": f"{PAGE_ID}_1", "attachments": {"data": [{"url": link}]}}],
            link,
        )
        self.assertEqual(found["id"], f"{PAGE_ID}_1")
        self.assertIsNone(facebook_post.matching_page_post([{"id": "1", "message": "Worcester"}], link))


QUEUE_ITEM = "mineral-november-glance-2026-11-03"
FAIR_ITEM = "fair-stamps-section-2026-11-02"
MINERAL_FACEBOOK = (
    "Rock, gem, mineral and fossil shows in the UK this November:\n\n"
    "Saturday 7 and Sunday 8 November: Rock, Gem & Bead Show, Worcester Racecourse\n"
    "Saturday 14 and Sunday 15 November: Rock, Gem & Bead Show, Newcastle Racecourse\n"
    "Saturday 14 November: Sussex Mineral, Crystal & Fossil Show, Haywards Heath College, "
    "10:00 to 16:30, entry £5\n"
    "Sunday 29 November: Oxford Mineral & Fossil Show, Exeter Hall, Kidlington, "
    "10:00 to 16:00, free entry\n\n"
    "Check with the organiser before you travel. Map and details for every show: mineraldigger.com"
)
MINERAL_BLUESKY = (
    "UK rock, gem and mineral shows this November:\n\n"
    "Worcester Racecourse, Saturday 7 and Sunday 8 November\n"
    "Newcastle Racecourse, Saturday 14 and Sunday 15 November\n"
    "Haywards Heath, Saturday 14 November\n"
    "Kidlington, Sunday 29 November\n\n"
    "Map and details: mineraldigger.com"
)
FAIR_LAUNCH = (
    "Stamp fairs are now on FairDigger: over 70 upcoming UK stamp and postcard fairs on one map, "
    "from AMP Fairs, Swindon Philatelic Society and more.\n\n"
    "This week: Cirencester Wednesday 4 November, Stafford Stamp Show Friday 6 November.\n\n"
    "Thanks to Xanthe's Stamp Magazine.\n\n"
    "fairdigger.co.uk/stamps"
)


def write_queue(path: Path, items: list[dict]) -> None:
    path.write_text(json.dumps({"items": items}), encoding="utf-8")


def mineral_item(**overrides) -> dict:
    item = {
        "id": QUEUE_ITEM,
        "site": "mineral",
        "facebook_text": MINERAL_FACEBOOK,
        "bluesky_text": MINERAL_BLUESKY,
        "link": "mineraldigger.com",
    }
    item.update(overrides)
    return item


def fair_item() -> dict:
    return {
        "id": FAIR_ITEM,
        "site": "fair",
        "facebook_text": FAIR_LAUNCH,
        "bluesky_text": FAIR_LAUNCH,
        "link": "fairdigger.co.uk/stamps",
    }


def serve_facebook(test, token, post_id, live):
    posted = {}
    calls = []

    def fake(request, timeout=30):
        calls.append((request.get_method(), request_path(request)))
        test.assertNotIn(token, request.full_url)
        if request.get_method() == "GET":
            test.assertEqual(request.get_header("Authorization"), f"Bearer {token}")
            body = live(posted) if callable(live) else live
            return JsonResponse(body)
        payload = json.loads(request.data.decode("utf-8"))
        test.assertEqual(payload["access_token"], token)
        posted["message"] = payload["message"]
        posted["link"] = payload["link"]
        return JsonResponse({"id": post_id})

    return fake, calls, posted


def serve_bluesky(test, password, live):
    sent = {}
    calls = []

    def fake(request, timeout=30):
        calls.append(request.full_url)
        if request.get_method() == "GET":
            test.assertIsNone(request.get_header("Authorization"))
            test.assertNotIn(password, request.full_url)
            test.assertIn("app.bsky.feed.getPosts", request.full_url)
            return JsonResponse({"posts": [live(sent)]})
        payload = json.loads(request.data.decode("utf-8"))
        if request.full_url.endswith("createSession"):
            test.assertEqual(payload["identifier"], "mineraldigger.com")
            test.assertEqual(payload["password"], password)
            return JsonResponse(
                {"accessJwt": "jwt-1", "did": "did:plc:mineral", "handle": "mineraldigger.com"}
            )
        test.assertNotIn(password, request.data.decode("utf-8"))
        sent["record"] = payload["record"]
        return JsonResponse({"uri": "at://did:plc:mineral/app.bsky.feed.post/rkey1", "cid": "cid1"})

    return fake, calls, sent


class BrandGuardTests(EnvGuard):
    def test_brand_guard_accepts_mineral_copy_and_blocks_other_brands(self):
        self.assertIsNone(publish_refusal(MINERAL_BLUESKY, "mineraldigger.com"))
        self.assertIsNone(publish_refusal(MINERAL_FACEBOOK, "https://www.mineraldigger.co.uk/show/x/"))
        self.assertIsNone(publish_refusal(MINERAL_BLUESKY))
        self.assertIn("FairDigger", publish_refusal(FAIR_LAUNCH, "https://mineraldigger.com"))
        self.assertIn("example.com", publish_refusal(MINERAL_BLUESKY, "https://example.com/shows"))
        self.assertIn("AuctionDigger", publish_refusal(MINERAL_BLUESKY, "https://auctiondigger.ie/lots"))
        self.assertIn("FairDigger", publish_refusal("See the list.\n\nfairdigger.com/stamps", "https://mineraldigger.com"))
        self.assertIn("Refusing to publish", publish_refusal("See you there!", "https://mineraldigger.com"))
        self.assertIn("Refusing to publish", publish_refusal("Open 10\u201316.", "https://mineraldigger.com"))
        self.assertIn(
            "Refusing to publish",
            publish_refusal("Details at https://mineraldigger.com", "https://mineraldigger.com"),
        )

    def test_missing_queue_path_does_not_read_a_leftover_file(self):
        with TemporaryDirectory() as tmp:
            leftover = Path(tmp) / "post.txt"
            leftover.write_text(FAIR_LAUNCH, encoding="utf-8")
            os.environ["MINERALDIGGER_QUEUE"] = str(leftover)
            try:
                with mock.patch("urllib.request.urlopen", side_effect=AssertionError("posted")):
                    code, output = run_facebook(["--queue-item", QUEUE_ITEM, "--publish"])
                    blue, blue_output = run_bluesky(["--queue-item", QUEUE_ITEM, "--publish"])
            finally:
                os.environ.pop("MINERALDIGGER_QUEUE", None)
        self.assertEqual(code, 1)
        self.assertEqual(blue, 1)
        self.assertIn("leftover temp file", output)
        self.assertIn("leftover temp file", blue_output)
        self.assertIn("Nothing posted", output)
        self.assertNotIn("Stamp fairs", output)
        self.assertNotIn("FairDigger", output)

    def test_another_brands_queue_item_is_refused(self):
        with TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.json"
            write_queue(queue, [fair_item(), mineral_item()])
            log = Path(tmp) / "log.json"
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("posted")):
                code, output = run_facebook(
                    ["--queue-item", FAIR_ITEM, "--queue", str(queue), "--publish", "--log", str(log)]
                )
                blue, blue_output = run_bluesky(
                    ["--queue-item", FAIR_ITEM, "--queue", str(queue), "--publish", "--log", str(log)]
                )
        self.assertEqual(code, 1)
        self.assertEqual(blue, 1)
        self.assertIn("FairDigger", output)
        self.assertIn("not MineralDigger", output)
        self.assertIn("not MineralDigger", blue_output)
        self.assertNotIn("Stamp fairs are now", output)
        self.assertFalse(log.exists())

    def test_mineral_item_carrying_fair_text_is_refused(self):
        with TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.json"
            write_queue(queue, [mineral_item(facebook_text=FAIR_LAUNCH, bluesky_text=FAIR_LAUNCH)])
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("posted")):
                code, output = run_bluesky(
                    ["--queue-item", QUEUE_ITEM, "--queue", str(queue), "--publish", "--log", str(Path(tmp) / "log.json")]
                )
        self.assertEqual(code, 1)
        self.assertIn("mentions FairDigger", output)
        self.assertIn("Nothing posted", output)
        self.assertFalse((Path(tmp) / "log.json").exists())

    def test_wrong_domain_link_is_refused(self):
        with TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.json"
            write_queue(queue, [mineral_item(link="https://example.com/shows")])
            fair_link = Path(tmp) / "fair-link.json"
            write_queue(fair_link, [mineral_item(link="fairdigger.co.uk/stamps")])
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("posted")):
                code, output = run_facebook(
                    ["--queue-item", QUEUE_ITEM, "--queue", str(queue), "--publish"]
                )
                blue, blue_output = run_bluesky(
                    ["--queue-item", QUEUE_ITEM, "--queue", str(fair_link), "--publish"]
                )
                text = Path(tmp) / "post.txt"
                text.write_text(MINERAL_FACEBOOK + "\n", encoding="utf-8")
                filed, filed_output = run_facebook(
                    ["--text-file", str(text), "--link", "https://auctiondigger.ie", "--publish"]
                )
        self.assertEqual(code, 1)
        self.assertIn("example.com", output)
        self.assertIn("not a MineralDigger domain", output)
        self.assertEqual(blue, 1)
        self.assertIn("FairDigger", blue_output)
        self.assertEqual(filed, 1)
        self.assertIn("AuctionDigger", filed_output)

    def test_direct_publish_refuses_before_the_network(self):
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("posted")):
            with self.assertRaises(SocialError) as caught:
                bluesky_post.publish_post("app-secret", FAIR_LAUNCH, "https://mineraldigger.com")
            self.assertIn("FairDigger", str(caught.exception))
            self.assertNotIn("app-secret", str(caught.exception))
            with self.assertRaises(SocialError) as caught:
                facebook_post.publish_page(PAGE_ID, "page-secret", MINERAL_FACEBOOK, "https://example.com/shows")
            self.assertIn("example.com", str(caught.exception))
            self.assertNotIn("page-secret", str(caught.exception))

    def test_text_file_of_another_brand_is_refused_and_a_link_is_required(self):
        with TemporaryDirectory() as tmp:
            text = Path(tmp) / "post.txt"
            text.write_text(FAIR_LAUNCH + "\n", encoding="utf-8")
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("posted")):
                code, output = run_facebook(
                    ["--text-file", str(text), "--link", "mineraldigger.com", "--publish"]
                )
                missing, missing_output = run_bluesky(["--text-file", str(text), "--publish"])
        self.assertEqual(code, 1)
        self.assertIn("mentions FairDigger", output)
        self.assertEqual(missing, 1)
        self.assertIn("--link", missing_output)
        self.assertIn("leftover temp file", missing_output)

    def test_facebook_queue_item_publishes_the_approved_text(self):
        with TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.json"
            write_queue(queue, [fair_item(), mineral_item()])
            log = Path(tmp) / "facebook_posts.json"
            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network")):
                dry, dry_output = run_facebook(["--queue-item", QUEUE_ITEM, "--queue", str(queue), "--log", str(log)])
            self.assertEqual(dry, 0)
            self.assertIn("Dry run. Nothing posted.", dry_output)
            self.assertIn(MINERAL_FACEBOOK, dry_output)
            self.assertNotIn("Stamp fairs are now", dry_output)
            self.assertFalse(log.exists())

            os.environ["MINERALDIGGER_FB_PAGE_TOKEN"] = "page-token"
            post_id = f"{PAGE_ID}_555"

            def live(posted):
                return {
                    "id": post_id,
                    "message": posted["message"],
                    "attachments": {"data": [{"unshimmed_url": posted["link"]}]},
                }

            fake, calls, posted = serve_facebook(self, "page-token", post_id, live)
            with mock.patch("urllib.request.urlopen", fake):
                code, output = run_facebook(
                    ["--queue-item", QUEUE_ITEM, "--queue", str(queue), "--publish", "--log", str(log)]
                )
            self.assertEqual(code, 0, output)
            self.assertEqual(posted["message"], MINERAL_FACEBOOK)
            self.assertEqual(posted["link"], "https://mineraldigger.com")
            self.assertEqual(calls[0][0], "POST")
            self.assertTrue(calls[0][1].endswith("/feed"))
            self.assertEqual(calls[1][0], "GET")
            self.assertIn(post_id, calls[1][1])
            self.assertIn("Read-back matched", output)
            self.assertNotIn("page-token", output)
            self.assertNotIn("Stamp fairs", output)
            saved = json.loads(log.read_text(encoding="utf-8"))
            self.assertEqual(saved[QUEUE_ITEM]["text"], MINERAL_FACEBOOK)
            self.assertEqual(saved[QUEUE_ITEM]["queue_item"], QUEUE_ITEM)
            self.assertNotIn("page-token", log.read_text(encoding="utf-8"))

            with mock.patch("urllib.request.urlopen", side_effect=AssertionError("second")):
                again, message = run_facebook(
                    ["--queue-item", QUEUE_ITEM, "--queue", str(queue), "--publish", "--log", str(log)]
                )
            self.assertEqual(again, 1)
            self.assertIn("already in", message)

    def test_bluesky_queue_item_publishes_the_approved_text(self):
        with TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.json"
            write_queue(queue, [fair_item(), mineral_item()])
            log = Path(tmp) / "bluesky_posts.json"
            os.environ["MINERALDIGGER_BLUESKY_APP_PASSWORD"] = "app-secret"

            def live(sent):
                record = sent["record"]
                return {
                    "uri": "at://did:plc:mineral/app.bsky.feed.post/rkey1",
                    "author": {"handle": "mineraldigger.com"},
                    "record": {
                        "text": record["text"],
                        "facets": record.get("facets"),
                        "embed": record.get("embed"),
                    },
                }

            fake, calls, sent = serve_bluesky(self, "app-secret", live)
            with mock.patch("urllib.request.urlopen", fake):
                code, output = run_bluesky(
                    ["--queue-item", QUEUE_ITEM, "--queue", str(queue), "--publish", "--log", str(log)]
                )
            self.assertEqual(code, 0, output)
            record = sent["record"]
            self.assertEqual(record["text"], MINERAL_BLUESKY)
            self.assertEqual(record["embed"]["external"]["uri"], "https://mineraldigger.com")
            self.assertEqual(record["facets"][0]["features"][0]["uri"], "https://mineraldigger.com")
            self.assertTrue(any("getPosts" in url for url in calls))
            self.assertIn("Read-back matched", output)
            self.assertNotIn("app-secret", output)
            self.assertNotIn("Stamp fairs", output)
            saved = json.loads(log.read_text(encoding="utf-8"))
            self.assertEqual(saved[QUEUE_ITEM]["text"], MINERAL_BLUESKY)
            self.assertEqual(saved[QUEUE_ITEM]["url"], "https://bsky.app/profile/mineraldigger.com/post/rkey1")
            self.assertNotIn("app-secret", log.read_text(encoding="utf-8"))
            self.assertNotIn("jwt-1", log.read_text(encoding="utf-8"))

    def test_facebook_readback_mismatch_fails(self):
        with TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.json"
            write_queue(queue, [mineral_item()])
            log = Path(tmp) / "facebook_posts.json"
            os.environ["MINERALDIGGER_FB_PAGE_TOKEN"] = "page-token"

            def wrong_text(_posted):
                return {
                    "id": f"{PAGE_ID}_9",
                    "message": FAIR_LAUNCH,
                    "attachments": {"data": [{"unshimmed_url": "https://fairdigger.co.uk/stamps"}]},
                }

            fake, calls, _posted = serve_facebook(self, "page-token", f"{PAGE_ID}_9", wrong_text)
            with mock.patch("urllib.request.urlopen", fake):
                code, output = run_facebook(
                    ["--queue-item", QUEUE_ITEM, "--queue", str(queue), "--publish", "--log", str(log)]
                )
            self.assertEqual(code, 1, output)
            self.assertIn("read-back mismatch", output)
            self.assertIn("does not match", output)
            self.assertNotIn("page-token", output)
            self.assertFalse(log.exists())
            self.assertTrue(any(method == "POST" for method, _path in calls))

            def wrong_card(posted):
                return {
                    "id": f"{PAGE_ID}_9",
                    "message": posted["message"],
                    "attachments": {"data": [{"unshimmed_url": "https://auctiondigger.ie"}]},
                }

            fake, calls, _posted = serve_facebook(self, "page-token", f"{PAGE_ID}_9", wrong_card)
            with mock.patch("urllib.request.urlopen", fake):
                code, output = run_facebook(
                    ["--queue-item", QUEUE_ITEM, "--queue", str(queue), "--publish", "--log", str(log)]
                )
            self.assertEqual(code, 1, output)
            self.assertIn("read-back mismatch", output)
            self.assertIn("auctiondigger.ie", output)
            self.assertNotIn("page-token", output)
            self.assertFalse(log.exists())

    def test_bluesky_readback_mismatch_fails(self):
        with TemporaryDirectory() as tmp:
            queue = Path(tmp) / "queue.json"
            write_queue(queue, [mineral_item()])
            log = Path(tmp) / "bluesky_posts.json"
            os.environ["MINERALDIGGER_BLUESKY_APP_PASSWORD"] = "app-secret"

            def wrong_card(sent):
                record = sent["record"]
                return {
                    "author": {"handle": "mineraldigger.com"},
                    "record": {
                        "text": record["text"],
                        "facets": [{"features": [{"uri": "https://fairdigger.co.uk/stamps"}]}],
                        "embed": {"external": {"uri": "https://fairdigger.co.uk/stamps"}},
                    },
                }

            fake, calls, _sent = serve_bluesky(self, "app-secret", wrong_card)
            with mock.patch("urllib.request.urlopen", fake):
                code, output = run_bluesky(
                    ["--queue-item", QUEUE_ITEM, "--queue", str(queue), "--publish", "--log", str(log)]
                )
            self.assertEqual(code, 1, output)
            self.assertIn("read-back mismatch", output)
            self.assertIn("fairdigger.co.uk", output)
            self.assertNotIn("app-secret", output)
            self.assertFalse(log.exists())
            self.assertTrue(any("createRecord" in url for url in calls))

            def wrong_handle(sent):
                record = sent["record"]
                return {
                    "author": {"handle": "fairdigger.co.uk"},
                    "record": {
                        "text": record["text"],
                        "facets": record.get("facets"),
                        "embed": record.get("embed"),
                    },
                }

            fake, _calls, _sent = serve_bluesky(self, "app-secret", wrong_handle)
            with mock.patch("urllib.request.urlopen", fake):
                code, output = run_bluesky(
                    ["--queue-item", QUEUE_ITEM, "--queue", str(queue), "--publish", "--log", str(log)]
                )
            self.assertEqual(code, 1, output)
            self.assertIn("read-back mismatch", output)
            self.assertIn("fairdigger.co.uk", output)
            self.assertIn("not mineraldigger.com", output)
            self.assertFalse(log.exists())

    def test_text_file_of_the_approved_copy_publishes(self):
        with TemporaryDirectory() as tmp:
            text = Path(tmp) / "post.txt"
            text.write_text(MINERAL_BLUESKY + "\n", encoding="utf-8")
            log = Path(tmp) / "bluesky_posts.json"
            os.environ["MINERALDIGGER_BLUESKY_APP_PASSWORD"] = "app-secret"

            def live(sent):
                record = sent["record"]
                return {
                    "author": {"handle": "mineraldigger.com"},
                    "record": {
                        "text": record["text"],
                        "facets": record.get("facets"),
                        "embed": record.get("embed"),
                    },
                }

            fake, _calls, sent = serve_bluesky(self, "app-secret", live)
            with mock.patch("urllib.request.urlopen", fake):
                code, output = run_bluesky(
                    [
                        "--text-file",
                        str(text),
                        "--link",
                        "mineraldigger.com",
                        "--publish",
                        "--log",
                        str(log),
                    ]
                )
            self.assertEqual(code, 0, output)
            self.assertEqual(sent["record"]["text"], MINERAL_BLUESKY)
            self.assertIn("Read-back matched", output)
            self.assertNotIn("app-secret", output)


if __name__ == "__main__":
    unittest.main()
