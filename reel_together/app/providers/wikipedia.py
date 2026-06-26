"""Wikipedia metadata provider (no API key required).

Uses the MediaWiki REST search endpoint for type-ahead and the page-summary
endpoint for fuller details. Wikipedia data is inconsistent for film/TV — there
is no clean "poster" field — so we infer type and year from the short
description and use the article's lead image as artwork. Good enough to add
titles quickly; TMDB enrichment fills the gaps when a key is configured.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import quote

import requests

from .base import Provider, SearchResult, TitleDetails

WIKI_LANG = "en"
API_ROOT = f"https://{WIKI_LANG}.wikipedia.org"
USER_AGENT = "ReelTogether/0.1 (Home Assistant add-on)"
_YEAR_RE = re.compile(r"\b(?:18|19|20)\d{2}\b")

_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})


def _https(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    return "https:" + url if url.startswith("//") else url


def _guess_type(text: str) -> str:
    t = (text or "").lower()
    if any(k in t for k in (
        "television series", "tv series", "tv show", "miniseries",
        "anime series", "web series", "streaming", "sitcom", "drama series",
    )):
        return "tv"
    if "series" in t and "film series" not in t:
        return "tv"
    if any(k in t for k in ("film", "movie")):
        return "movie"
    return "unknown"


def _guess_year(text: str) -> Optional[int]:
    m = _YEAR_RE.search(text or "")
    return int(m.group(0)) if m else None


class WikipediaProvider(Provider):
    name = "wikipedia"

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        if not query or not query.strip():
            return []
        try:
            r = _session.get(
                f"{API_ROOT}/w/rest.php/v1/search/page",
                params={"q": query, "limit": min(limit, 20)},
                timeout=8,
            )
            r.raise_for_status()
            pages = r.json().get("pages", [])
        except (requests.RequestException, ValueError):
            return []

        results: list[SearchResult] = []
        for p in pages:
            desc = p.get("description") or ""
            key = p.get("key") or p.get("title")
            thumb = (p.get("thumbnail") or {}).get("url")
            results.append(
                SearchResult(
                    source="wikipedia",
                    source_id=str(key),
                    title=p.get("title") or str(key),
                    type=_guess_type(desc),
                    year=_guess_year(desc),
                    overview=desc,
                    poster_url=_https(thumb),
                    source_url=f"{API_ROOT}/wiki/{quote(str(key).replace(' ', '_'))}",
                )
            )
        # Soft-prefer entries that look like a film or show.
        results.sort(key=lambda x: 0 if x.type in ("movie", "tv") else 1)
        return results

    def details(self, source_id: str, type_: str = "unknown") -> Optional[TitleDetails]:
        title = quote(str(source_id).replace(" ", "_"))
        try:
            r = _session.get(f"{API_ROOT}/api/rest_v1/page/summary/{title}", timeout=8)
            r.raise_for_status()
            data = r.json()
        except (requests.RequestException, ValueError):
            return None

        desc = data.get("description") or ""
        poster = (data.get("originalimage") or {}).get("source") or (
            data.get("thumbnail") or {}
        ).get("source")
        page = ((data.get("content_urls") or {}).get("desktop") or {}).get("page")
        return TitleDetails(
            source="wikipedia",
            source_id=str(source_id),
            title=data.get("title") or str(source_id),
            type=type_ if type_ != "unknown" else _guess_type(desc),
            year=_guess_year(desc),
            overview=data.get("extract") or desc,
            poster_url=poster,
            source_url=page or f"{API_ROOT}/wiki/{title}",
            extra={"description": desc},
        )
