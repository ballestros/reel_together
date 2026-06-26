"""Provider interface shared by every metadata source.

A provider turns a free-text query into a list of :class:`SearchResult` and can
return fuller :class:`TitleDetails` for one item. Keeping this contract small is
what makes the source pluggable: the rest of the app never imports a concrete
provider directly.
"""
from __future__ import annotations

import dataclasses
from abc import ABC, abstractmethod
from typing import Optional


@dataclasses.dataclass
class SearchResult:
    source: str                      # 'wikipedia' | 'tmdb'
    source_id: str                   # stable id within that source
    title: str
    type: str = "unknown"            # 'movie' | 'tv' | 'unknown'
    year: Optional[int] = None
    overview: str = ""
    poster_url: Optional[str] = None
    source_url: Optional[str] = None

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class TitleDetails(SearchResult):
    extra: dict = dataclasses.field(default_factory=dict)


class Provider(ABC):
    name: str = "base"

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        ...

    def details(self, source_id: str, type_: str = "unknown") -> Optional[TitleDetails]:
        """Optional richer lookup. Defaults to None when unsupported."""
        return None
