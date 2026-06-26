"""Background TMDB enrichment.

When a TMDB key is configured, titles added from Wikipedia are upgraded to TMDB
data (real poster, reliable type/year, genres, season/episode counts) without the
user doing anything. Enrichment runs on a daemon worker thread so it never adds
latency to the add request:

* on add, the new title id is enqueued;
* on startup, any existing un-enriched titles are swept in;
* the board polls periodically, so the upgraded poster simply appears.

With no key configured, every entry point is a cheap no-op.
"""
from __future__ import annotations

import json
import logging
import queue
import threading
import time

from . import config, db
from .providers import get_enricher

log = logging.getLogger("reel_together.enrich")

_queue: "queue.Queue[int]" = queue.Queue()
_inflight: set[int] = set()
_lock = threading.Lock()
_started = False


def _extra(title: dict) -> dict:
    raw = title.get("extra")
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw) if raw else {}
    except (ValueError, TypeError):
        return {}


def enrich_title(title_id: int) -> bool:
    """Enrich one title from TMDB. Returns True if the title was updated."""
    enricher = get_enricher()
    if not enricher:
        return False
    title = db.get_title(title_id)
    if not title or title["source"] != "wikipedia":
        return False
    extra = _extra(title)
    if extra.get("enriched"):
        return False

    det = enricher.enrich(title["title"], title.get("year"), title.get("type"))
    if not det:
        return False
    _apply(title, det, override=False)
    log.info("Enriched title %s -> %s", title_id, det.title)
    return True


def _apply(title: dict, det, override: bool) -> None:
    """Write TMDB details onto a title.

    ``override`` replaces season/episode counts and clears them when switching
    to a movie — used when the user manually picks a different match.
    """
    extra = _extra(title)
    merged = {**extra, **(det.extra or {}), "tmdb_id": det.source_id, "enriched": True}
    fields = {
        "type": det.type if det.type != "unknown" else title["type"],
        "year": det.year or title.get("year"),
        "overview": det.overview or title.get("overview"),
        "poster_url": det.poster_url or title.get("poster_url"),
        "extra": merged,
    }
    dx = det.extra or {}
    if det.type == "tv":
        if dx.get("seasons") and (override or not title.get("seasons")):
            fields["seasons"] = dx["seasons"]
        if dx.get("episodes") and (override or not title.get("episodes_total")):
            fields["episodes_total"] = dx["episodes"]
    elif override and det.type == "movie":
        fields["seasons"] = None
        fields["episodes_total"] = None
    db.update_title(title["id"], fields)
    db.add_activity(None, title["id"], "enriched", det.title)


def apply_match(title_id: int, tmdb_id: str, type_: str) -> bool:
    """Apply a specific TMDB entry chosen by the user (re-match)."""
    if not config.TMDB_API_KEY:
        return False
    from .providers.tmdb import TMDBProvider

    det = TMDBProvider(config.TMDB_API_KEY).details(str(tmdb_id), type_)
    title = db.get_title(title_id)
    if not det or not title:
        return False
    _apply(title, det, override=True)
    log.info("Re-matched title %s -> %s", title_id, det.title)
    return True


def tmdb_candidates(query: str, limit: int = 8) -> list[dict]:
    """TMDB search results for the re-match picker."""
    if not config.TMDB_API_KEY:
        return []
    from .providers.tmdb import TMDBProvider

    return [r.to_dict() for r in TMDBProvider(config.TMDB_API_KEY).search(query, limit=limit)]


def enqueue(title_id: int) -> None:
    if not config.TMDB_API_KEY:
        return
    with _lock:
        if title_id in _inflight:
            return
        _inflight.add(title_id)
    _queue.put(title_id)


def _worker() -> None:
    while True:
        title_id = _queue.get()
        try:
            enrich_title(title_id)
        except Exception as exc:  # never let the worker die
            log.warning("Enrichment failed for %s: %s", title_id, exc)
        finally:
            with _lock:
                _inflight.discard(title_id)
            _queue.task_done()
            time.sleep(0.3)  # be polite to the TMDB API


def start(sweep: bool = True) -> None:
    """Start the worker and (optionally) enqueue existing un-enriched titles."""
    global _started
    if _started or not config.TMDB_API_KEY:
        return
    _started = True
    threading.Thread(target=_worker, name="enrich-worker", daemon=True).start()
    if sweep:
        try:
            for tid in db.titles_needing_enrichment():
                enqueue(tid)
        except Exception as exc:
            log.warning("Enrichment sweep failed: %s", exc)
