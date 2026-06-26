"""TVmaze metadata provider (TV only, no API key).

Free and key-less. The best source for episode/season counts and the next
upcoming episode's air date. TVmaze does not cover movies — those stay with the
Wikipedia / TMDB providers, and the combined search in ``providers/__init__``
takes TV results from here and everything else from the active provider.
"""
from __future__ import annotations

import html
import re
from typing import Optional

import requests

from .base import Provider, SearchResult, TitleDetails

API_ROOT = "https://api.tvmaze.com"
USER_AGENT = "ReelTogether/0.1 (Home Assistant add-on)"

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})

_TAGS = re.compile(r"<[^>]+>")


def _clean(summary: Optional[str]) -> str:
    """Strip TVmaze's HTML summary down to plain text."""
    if not summary:
        return ""
    return html.unescape(_TAGS.sub("", summary)).strip()


def _year(premiered: Optional[str]) -> Optional[int]:
    if premiered and len(premiered) >= 4 and premiered[:4].isdigit():
        return int(premiered[:4])
    return None


def _poster(show: dict) -> Optional[str]:
    img = show.get("image") or {}
    return img.get("medium") or img.get("original")


def _next_ep(node: Optional[dict]) -> Optional[dict]:
    if not node or not node.get("airstamp"):
        return None
    return {
        "airstamp": node.get("airstamp"),
        "season": node.get("season"),
        "number": node.get("number"),
        "name": node.get("name"),
    }


class TVmazeProvider(Provider):
    name = "tvmaze"

    def _get(self, path: str, params=None):
        r = _session.get(f"{API_ROOT}{path}", params=params, timeout=8)
        r.raise_for_status()
        return r.json()

    def _result(self, show: dict) -> SearchResult:
        return SearchResult(
            source="tvmaze",
            source_id=str(show.get("id")),
            title=show.get("name") or "",
            type="tv",
            year=_year(show.get("premiered")),
            overview=_clean(show.get("summary")),
            poster_url=_poster(show),
            source_url=show.get("url"),
        )

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        if not query or not query.strip():
            return []
        try:
            data = self._get("/search/shows", {"q": query})
        except (requests.RequestException, ValueError):
            return []
        out: list[SearchResult] = []
        for item in data:
            show = item.get("show") or {}
            if show.get("id"):
                out.append(self._result(show))
            if len(out) >= limit:
                break
        return out

    def details(self, source_id: str, type_: str = "tv") -> Optional[TitleDetails]:
        try:
            show = self._get(
                f"/shows/{source_id}",
                [("embed[]", "seasons"), ("embed[]", "nextepisode")],
            )
        except (requests.RequestException, ValueError):
            return None

        emb = show.get("_embedded") or {}
        seasons_arr = emb.get("seasons") or []
        aired = [s for s in seasons_arr if s.get("episodeOrder")]
        seasons = len(aired) or (len(seasons_arr) or None)
        episodes = sum(s["episodeOrder"] for s in aired) or None

        extra = {
            "seasons": seasons,
            "episodes": episodes,
            "genres": show.get("genres") or [],
            "status": show.get("status"),
            "tvmaze_rating": (show.get("rating") or {}).get("average"),
        }
        ne = _next_ep(emb.get("nextepisode"))
        if ne:
            extra["next_episode"] = ne

        return TitleDetails(
            source="tvmaze",
            source_id=str(source_id),
            title=show.get("name") or str(source_id),
            type="tv",
            year=_year(show.get("premiered")),
            overview=_clean(show.get("summary")),
            poster_url=_poster(show),
            source_url=show.get("url"),
            extra=extra,
        )

    def next_episode(self, source_id: str) -> Optional[dict]:
        """Just the upcoming episode (for the periodic airing refresh)."""
        try:
            show = self._get(f"/shows/{source_id}", [("embed[]", "nextepisode")])
        except (requests.RequestException, ValueError):
            return None
        return _next_ep((show.get("_embedded") or {}).get("nextepisode"))
