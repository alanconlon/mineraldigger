"""Organiser URL overrides the parsers apply before a row is published.

A null organiser url clears the website. A host in blocked_hosts is removed
from the organiser url, the source url and any extra source, even when the
override names that host and even when an older catalogue row is kept.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
OVERRIDES_PATH = ROOT / "data" / "organiser-overrides.json"


def load_overrides(path: Path = OVERRIDES_PATH) -> dict:
    if not path.is_file():
        return {"organisers": {}, "blocked_hosts": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {"organisers": {}, "blocked_hosts": []}
    organisers = data.get("organisers")
    hosts = data.get("blocked_hosts")
    return {
        "organisers": organisers if isinstance(organisers, dict) else {},
        "blocked_hosts": [normal_host(host) for host in hosts or [] if normal_host(host)],
    }


def normal_host(value: str) -> str:
    host = str(value or "").strip().lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def url_host(value: str | None) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        return normal_host(urlparse(value.strip()).hostname or "")
    except ValueError:
        return ""


def host_blocked(value: str | None, hosts: list[str]) -> bool:
    host = url_host(value)
    if not host:
        return False
    return any(host == blocked or host.endswith("." + blocked) for blocked in hosts)


def _cleared(value: str | None, hosts: list[str]) -> str | None:
    if host_blocked(value, hosts):
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def apply_row_override(row: dict, overrides: dict | None = None) -> dict:
    """Replace one parser row's published URLs. The row is updated in place."""
    spec = overrides if overrides is not None else load_overrides()
    hosts = list(spec.get("blocked_hosts") or [])
    organisers = spec.get("organisers") or {}
    chosen = organisers.get(row.get("organiser_id"))
    if isinstance(chosen, dict) and "url" in chosen:
        row["organiser_url"] = chosen.get("url") or None
    row["organiser_url"] = _cleared(row.get("organiser_url"), hosts)
    row["source_url"] = _cleared(row.get("source_url"), hosts)
    return row


def apply_show_override(show: dict, overrides: dict | None = None) -> dict:
    """Clear blocked hosts on an assembled show, including one kept from disk."""
    spec = overrides if overrides is not None else load_overrides()
    hosts = list(spec.get("blocked_hosts") or [])
    organisers = spec.get("organisers") or {}
    organiser = show.get("organiser")
    if isinstance(organiser, dict):
        chosen = organisers.get(organiser.get("id"))
        if isinstance(chosen, dict) and "url" in chosen:
            organiser["url"] = chosen.get("url") or None
        organiser["url"] = _cleared(organiser.get("url"), hosts)
    source = show.get("source")
    if isinstance(source, dict):
        source["url"] = _cleared(source.get("url"), hosts)
        also = source.get("also")
        if isinstance(also, list):
            source["also"] = [
                item for item in also if not (isinstance(item, dict) and host_blocked(item.get("url"), hosts))
            ]
    return show


def scrub_shows(shows: list[dict], overrides: dict | None = None) -> list[dict]:
    spec = overrides if overrides is not None else load_overrides()
    return [apply_show_override(show, spec) if isinstance(show, dict) else show for show in shows]
