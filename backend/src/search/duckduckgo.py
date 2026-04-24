"""
DuckDuckGo-backed search helpers.
"""
from __future__ import annotations

from urllib.parse import urlparse

from ..cache import build_cache_key, get_json, get_ttl_seconds, set_json

try:
    from duckduckgo_search import DDGS
except Exception:  # pragma: no cover - dependency availability varies by environment
    DDGS = None

TARGETED_LEGAL_SITE_FILTERS = (
    "site:gov.cn",
    "site:court.gov.cn",
    "site:npc.gov.cn",
    "site:moj.gov.cn",
    "site:pkulaw.com",
)


def _site_name_from_url(url: str) -> str:
    hostname = urlparse(url).hostname or ""
    return hostname.removeprefix("www.")


def _normalize_results(raw_results: list[dict], *, max_results: int) -> list[dict]:
    normalized: list[dict] = []
    seen_urls: set[str] = set()

    for item in raw_results:
        url = str(item.get("href") or item.get("url") or "").strip()
        title = str(item.get("title") or "").strip()
        snippet = str(item.get("body") or item.get("snippet") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        normalized.append(
            {
                "title": title,
                "url": url,
                "snippet": snippet,
                "site_name": _site_name_from_url(url),
            }
        )
        if len(normalized) >= max_results:
            break

    return normalized


def _run_text_search(query: str, *, max_results: int) -> list[dict]:
    normalized_query = query.strip()
    if not normalized_query or DDGS is None:
        return []

    cache_key = build_cache_key(
        "search",
        {
            "provider": "duckduckgo",
            "query": normalized_query,
            "max_results": max_results,
        },
    )
    cached_results = get_json(cache_key)
    if isinstance(cached_results, list):
        return cached_results

    try:
        with DDGS() as ddgs:
            raw_results = list(ddgs.text(normalized_query, region="cn-zh", safesearch="moderate", max_results=max_results))
    except Exception:
        return []

    normalized = _normalize_results(raw_results, max_results=max_results)
    set_json(cache_key, normalized, get_ttl_seconds("search"))
    return normalized


def search_web(query: str, max_results: int = 5) -> list[dict]:
    return _run_text_search(query, max_results=max_results)


def search_legal_sources(query: str, max_results: int = 5) -> list[dict]:
    results: list[dict] = []
    seen_urls: set[str] = set()
    per_query_limit = max(2, min(max_results, 3))

    for site_filter in TARGETED_LEGAL_SITE_FILTERS:
        site_query = f"{query} {site_filter}"
        for result in _run_text_search(site_query, max_results=per_query_limit):
            url = str(result.get("url", "")).strip()
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            results.append(result)
            if len(results) >= max_results:
                return results

    return results


def search_legal(query: str, max_results: int = 3) -> str:
    results = search_legal_sources(query, max_results=max_results)
    if not results:
        return ""

    lines = ["[Live Legal Search]"]
    for index, result in enumerate(results, start=1):
        lines.append(f"{index}. {result.get('title', '')}")
        if result.get("snippet"):
            lines.append(f"   {result.get('snippet')}")
        if result.get("url"):
            lines.append(f"   {result.get('url')}")
    return "\n".join(lines)


def build_search_context(routing: dict, entities: dict) -> str:
    """Return static legal references used by the review pipeline."""
    return """
【基础法律依据】：
1. 《民法典》第584条：当事人一方不履行合同义务或者履行合同义务不符合约定的，应当承担继续履行、采取补救措施或者赔偿损失等违约责任。
2. 《民法典》第585条：约定的违约金过分高于造成的损失的，人民法院或者仲裁机构可以根据当事人的请求予以适当减少。
3. 《民法典》第587条：债务人按照约定履行债务的，债权人应当返还定金。
4. 《城市房屋租赁管理办法》第九条：承租人应当按照约定的方法使用租赁房屋。
5. 《最高人民法院关于审理民间借贷案件适用法律若干问题的规定》第二十五条：借贷双方约定的利率超过合同成立时一年期贷款市场报价利率四倍的，超出部分人民法院不予支持。
"""
