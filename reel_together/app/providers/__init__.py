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

__all__ = [
    "Provider", "SearchResult", "TitleDetails",
    "get_provider", "get_enricher", "provider_for_source",
]


def get_provider() -> Provider:
    name = config.active_provider_name()
    if name == "tmdb" and config.TMDB_API_KEY:
        return TMDBProvider(config.TMDB_API_KEY)
    return WikipediaProvider()


def provider_for_source(source: str) -> Provider:
    """Provider that can fetch details for a title from a given source."""
    if source == "tmdb" and config.TMDB_API_KEY:
        return TMDBProvider(config.TMDB_API_KEY)
    return WikipediaProvider()


def get_enricher() -> Optional[TMDBProvider]:
    if config.TMDB_API_KEY:
        return TMDBProvider(config.TMDB_API_KEY)
    return None
