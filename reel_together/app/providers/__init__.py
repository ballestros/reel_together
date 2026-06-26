"""Provider registry.

``get_provider()`` returns the active search provider based on configuration.
``get_enricher()`` returns a TMDB provider when a key is set, regardless of the
active provider, so Wikipedia-added titles can be enriched on demand.
"""
from __future__ import annotations

from typing import Optional

from .. import config
from .base import Provider, SearchResult, TitleDetails
from .wikipedia import WikipediaProvider
from .tmdb import TMDBProvider
from .tvmaze import TVmazeProvider

__all__ = [
    "Provider", "SearchResult", "TitleDetails",
    "get_provider", "get_enricher", "provider_for_source", "combined_search",
]


def get_provider() -> Provider:
    name = config.active_provider_name()
    if name == "tmdb" and config.TMDB_API_KEY:
        return TMDBProvider(config.TMDB_API_KEY)
    return WikipediaProvider()


def provider_for_source(source: str) -> Provider:
    """Provider that can fetch details for a title from a given source."""
    if source == "tvmaze":
        return TVmazeProvider()
    if source == "tmdb" and config.TMDB_API_KEY:
        return TMDBProvider(config.TMDB_API_KEY)
    return WikipediaProvider()


def _relevance(title: str, query: str) -> int:
    t, q = (title or "").lower(), (query or "").lower()
    if t == q:
        return 3
    if t.startswith(q):
        return 2
    if q in t:
        return 1
    return 0


def combined_search(query: str, limit: int = 10) -> list[SearchResult]:
    """TV results from TVmaze + movies/other from the active provider.

    TVmaze is TV-only, so it supplies the shows; the active provider (Wikipedia
    or TMDB) supplies movies and anything not typed as TV. Duplicates of a TVmaze
    show are dropped, and the strongest title matches are floated to the top.
    """
    tv = TVmazeProvider().search(query, limit=limit)
    base = get_provider().search(query, limit=limit)
    tv_keys = {(r.title.lower(), r.year) for r in tv}
    # Keep every base result that isn't a duplicate of a TVmaze show. We dedupe
    # by title+year rather than by type, so a show that's on Wikipedia but not on
    # TVmaze (obscure/old/international) still shows up.
    extras = [r for r in base if (r.title.lower(), r.year) not in tv_keys]
    merged = tv + extras
    merged.sort(key=lambda r: -_relevance(r.title, query))  # stable sort
    return merged[: max(limit, 12)]


def get_enricher() -> Optional[TMDBProvider]:
    if config.TMDB_API_KEY:
        return TMDBProvider(config.TMDB_API_KEY)
    return None
