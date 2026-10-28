#!/usr/bin/env python3
"""Create or update the MineralDigger Friday email as a Buttondown draft.

Reads out/newsletter-YYYY-MM-DD.md (written by scripts/digest.py) and uploads
it to https://api.buttondown.com/v1. The request uses
Authorization: Token <key> and status "draft".

Environment:
  MINERALDIGGER_BUTTONDOWN_API_KEY
    API key for the mineraldigger newsletter
    (https://buttondown.com/mineraldigger).
    This script does not read BUTTONDOWN_API_KEY.
    If the variable is unset, the run is a dry run and no request is made.

A draft with the same subject is updated in place. A second draft is not
created. The script never sends, never schedules, and never sets a status
other than draft. There is no publish_date.

Examples:
  python3 scripts/digest.py
  python3 scripts/buttondown_draft.py
  python3 scripts/buttondown_draft.py --dry-run
  python3 scripts/buttondown_draft.py --file out/newsletter-2026-10-30.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from digest import issue_friday, newsletter_path, parse_iso  # noqa: E402

API = "https://api.buttondown.com/v1"
OUT_DIR = ROOT / "out"
ENV_KEY = "MINERALDIGGER_BUTTONDOWN_API_KEY"
MAX_PAGES = 20


class ButtondownError(RuntimeError):
    pass


def api_key() -> str | None:
    """Key for the mineraldigger newsletter. No shared BUTTONDOWN_API_KEY fallback."""
    value = os.environ.get(ENV_KEY, "").strip()
    return value or None


def split_subject(markdown: str) -> tuple[str, str]:
    """Take the subject from the first Markdown H1. Leave the editor-mode comment in the body."""
    subject = None
    kept: list[str] = []
    for line in markdown.splitlines():
        if subject is None and line.startswith("# "):
            subject = line[2:].strip()
            continue
        kept.append(line)
    if not subject:
        raise ButtondownError("Newsletter has no H1 subject line.")
    body = "\n".join(kept).strip() + "\n"
    return subject, body


class Buttondown:
    def __init__(self, token: str, base_url: str = API):
        self.token = token
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, url: str, payload: dict | None = None) -> dict:
        if payload is not None:
            if payload.get("status") != "draft":
                raise ButtondownError("Refusing a Buttondown status other than draft.")
            if payload.get("publish_date"):
                raise ButtondownError("Refusing to schedule a Buttondown email.")
        if not url.startswith("http"):
            url = f"{self.base_url}{url}"
        headers = {
            "Authorization": f"Token {self.token}",
            "Accept": "application/json",
            "User-Agent": "MineralDiggerDraft/1 (+https://mineraldigger.com)",
        }
        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise ButtondownError(f"Buttondown {method} failed with HTTP {exc.code}. {detail}") from exc
        except urllib.error.URLError as exc:
            raise ButtondownError(f"Buttondown {method} failed. {exc.reason}") from exc
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ButtondownError("Buttondown returned a response that was not JSON.") from exc
        return parsed if isinstance(parsed, dict) else {"results": parsed}

    def drafts_with_subject(self, subject: str) -> list[dict]:
        matches: list[dict] = []
        url: str | None = f"{self.base_url}/emails?status=draft"
        pages = 0
        while url and pages < MAX_PAGES:
            pages += 1
            payload = self._request("GET", url)
            results = payload.get("results") or []
            for email in results:
                if email.get("status") == "draft" and email.get("subject") == subject:
                    matches.append(email)
            nxt = payload.get("next")
            url = nxt if isinstance(nxt, str) and nxt else None
        return matches

    def save_draft(self, subject: str, body: str) -> tuple[str, str]:
        payload = {"subject": subject, "body": body, "status": "draft"}
        matches = self.drafts_with_subject(subject)
        if matches:
            email_id = matches[0].get("id")
            if not email_id:
                raise ButtondownError("Matching draft had no id.")
            saved = self._request("PATCH", f"{self.base_url}/emails/{email_id}", payload)
            return "updated", str(saved.get("id") or email_id)
        saved = self._request("POST", f"{self.base_url}/emails", payload)
        email_id = saved.get("id")
        if not email_id:
            raise ButtondownError("Buttondown created a draft but returned no id.")
        return "created", str(email_id)


def default_newsletter(today: date, out_dir: Path) -> Path:
    return newsletter_path(out_dir, issue_friday(today))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upload the Friday email as a Buttondown draft.")
    parser.add_argument("--file", type=Path, help="Newsletter Markdown. Defaults to this week's file in out/.")
    parser.add_argument("--today", help="YYYY-MM-DD used to pick the default file. Defaults to today.")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--dry-run", action="store_true", help="Print the subject and do not call Buttondown.")
    parser.add_argument("--api", default=API, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    today = parse_iso(args.today) if args.today else date.today()
    path = args.file if args.file else default_newsletter(today, args.out)
    if not path.is_file():
        print(f"No newsletter file at {path}. Nothing drafted.")
        return 0

    try:
        subject, body = split_subject(path.read_text(encoding="utf-8"))
    except ButtondownError as exc:
        print(exc, file=sys.stderr)
        return 1

    key = api_key()
    if args.dry_run or not key:
        print("Dry run. No Buttondown request.")
        print(f"Subject: {subject}")
        print(f"File: {path}")
        print("Status would be draft. Nothing is sent.")
        if not key:
            print(f"{ENV_KEY} is not set.")
        return 0

    try:
        action, email_id = Buttondown(key, args.api).save_draft(subject, body)
    except ButtondownError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"{action.capitalize()} Buttondown draft {email_id}. Status is draft. Nothing was sent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
