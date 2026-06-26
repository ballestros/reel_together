"""TMDB metadata provider (requires a free API key).

Richer than Wikipedia: real poster art via the TMDB image CDN, reliable
movie/TV typing, genres, runtime and TMDB's user score. Used as the active
provider when ``metadata_provider`` resolves to ``tmdb``, and as the enricher
for titles originally added from Wikipedia.
"""
from __future__ import annotations

from typing import Optional

import requests

from .base import Provider, SearchResult, TitleDetails

API_ROOT = "https://api.themoviedb.org/3"
IMG_BASE = "https://image.tmdb.org/t/p/w342"
USER_AGENT = "ReelTogether/0.1 (Home Assistant add-on)"

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})


def _year(date_str: Optional[str]) -> Optional[int]:
    if date_str and len(date_str) >= 4 and date_str[:4].isdigit():
        return int(date_str[:4])
    return None


def _img(path: Optional[str]) -> Optional[str]:
    return f"{IMG_BASE}{path}" if path else None


class TMDBProvider(Provider):
    name = "tmdb"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def _get(self, path: str, params: Optional[dict] = None) -> dict:
        params = dict(params or {})
        params["api_key"] = self.api_key
        r = _session.get(f"{API_ROOT}{path}", params=params, timeout=8)
        r.raise_for_status()
        return r.json()

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        if not query or not query.strip():
            return []
        try:
            data = self._get("/search/multi", {"query": query, "include_adult": "false"})
        except (requests.RequestException, ValueError):
            return []

        out: list[SearchResult] = []
        for item in data.get("results", []):
            mt = item.get("media_type")
            if mt not in ("movie", "tv"):
                continue
            date = item.get("release_date") or item.get("first_air_date")
            out.append(
                SearchResult(
                    source="tmdb",
                    source_id=str(item.get("id")),
                    title=item.get("title") or item.get("name") or "",
                    type=mt,
                    year=_year(date),
                    overview=item.get("overview") or "",
                    poster_url=_img(item.get("poster_path")),
                    source_url=f"https://www.themoviedb.org/{mt}/{item.get('id')}",
                )
            )
            if len(out) >= limit:
                break
        return out

    def details(self, source_id: str, type_: str = "movie") -> Optional[TitleDetails]:
        kind = "tv" if type_ == "tv" else "movie"
        try:
            item = self._get(f"/{kind}/{source_id}")
        except (requests.RequestException, ValueError):
            return None

        date = item.get("release_date") or item.get("first_air_date")
        runtime = item.get("runtime")
        if runtime is None:
            runtime = (item.get("episode_run_time") or [None])[0]
        return TitleDetails(
            source="tmdb",
            source_id=str(source_id),
            title=item.get("title") or item.get("name") or "",
            type=kind,
            year=_year(date),
            overview=item.get("overview") or "",
            poster_url=_img(item.get("poster_path")),
            source_url=f"https://www.themoviedb.org/{kind}/{source_id}",
            extra={
                "genres": [g.get("name") for g in item.get("genres", [])],
                "runtime": runtime,
                "tmdb_rating": item.get("vote_average"),
                "tagline": item.get("tagline"),
                "seasons": item.get("number_of_seasons"),
                "episodes": item.get("number_of_episodes"),
            },
        )

    def enrich(self, title: str, year: Optional[int] = None, type_: str = "unknown") -> Optional[TitleDetails]:
        """Best-effort match of a known title by name (and year) → TitleDetails."""
        try:
            if type_ in ("movie", "tv"):
                params = {"query": title}
                if year and type_ == "movie":
                    params["year"] = year
                if year and type_ == "tv":
                    params["first_air_date_year"] = year
                results = self._get(f"/search/{type_}", params).get("results") or []
                media_type = type_
            else:
                results = [
                    r for r in self._get("/search/multi", {"query": title}).get("results", [])
                    if r.get("media_type") in ("movie", "tv")
                ]
                media_type = results[0].get("media_type") if results else "movie"
            if not results:
                return None
            return self.details(str(results[0].get("id")), media_type)
        except (requests.RequestException, ValueError):
            return None
