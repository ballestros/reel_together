"""Keep TVmaze 'next episode' air dates fresh.

TVmaze-sourced titles store their upcoming episode under ``extra.next_episode``.
That date moves over time, so a daemon refreshes it once on startup and every
few hours after. With no TVmaze titles, this is a cheap no-op.
"""
from __future__ import annotations

import json
import logging
import threading
import time

from . import db
from .providers.tvmaze import TVmazeProvider

log = logging.getLogger("reel_together.airing")

_started = False
INTERVAL = 6 * 3600  # seconds


def _extra(title: dict) -> dict:
    raw = title.get("extra")
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        return {}


def refresh_one(title: dict) -> None:
    if title.get("source") != "tvmaze":
        return
    ne = TVmazeProvider().next_episode(title["source_id"])
    extra = _extra(title)
    if extra.get("next_episode") == ne:
        return
    extra["next_episode"] = ne  # may be None — clears a stale value
    db.update_title(title["id"], {"extra": extra})


def refresh_all() -> None:
    for t in db.titles_by_source("tvmaze"):
        try:
            refresh_one(t)
            time.sleep(0.25)  # be polite to the API
        except Exception as exc:  # never let the sweep die
            log.warning("airing refresh failed for %s: %s", t.get("id"), exc)


def _loop() -> None:
    while True:
        try:
            refresh_all()
        except Exception as exc:
            log.warning("airing sweep failed: %s", exc)
        time.sleep(INTERVAL)


def start() -> None:
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, daemon=True, name="airing-refresh").start()
