"""
Search module — static legal references only.
"""
from .duckduckgo import build_search_context, search_legal, search_legal_sources, search_web

__all__ = [
    "build_search_context",
    "search_legal",
    "search_legal_sources",
    "search_web",
]
