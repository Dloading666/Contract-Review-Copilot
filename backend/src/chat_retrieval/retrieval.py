from __future__ import annotations

import re
from urllib.parse import urlparse

from ..search.duckduckgo import search_legal_sources, search_web
from ..vectorstore.store import retrieve_similar_chunks

EXTERNAL_CONTEXT_HINT_PATTERN = re.compile(r"(最新|最近|近期|当地|本地|法院|判例|案例|政策|通知|怎么判|实务|实践)")
GENERAL_WEB_HINT_PATTERN = re.compile(r"(最新|最近|近期|案例|判例|新闻|实务|经验|平台|曝光|黑猫|社交)")


def _extract_site_name(url: str | None) -> str | None:
    if not url:
        return None
    hostname = urlparse(url).hostname or ""
    return hostname.removeprefix("www.") or None


def retrieve_pgvector_evidence(
    queries: list[dict[str, object]],
    *,
    top_k: int,
    min_similarity: float,
) -> list[dict[str, object]]:
    evidence_by_key: dict[str, dict[str, object]] = {}

    for query in queries:
        query_text = str(query.get("text", "")).strip()
        query_priority = float(query.get("priority", 0.5))
        if not query_text:
            continue

        hits = retrieve_similar_chunks(
            query_text,
            top_k=top_k,
            min_similarity=min_similarity,
        )
        for hit in hits:
            metadata = hit.get("metadata") or {}
            hit_id = hit.get("id")
            dedupe_key = f"pgvector:{hit_id}" if hit_id is not None else f"pgvector:{query_text}:{hit.get('chunk_index')}"
            similarity = float(hit.get("similarity", 0.0))
            snippet = str(hit.get("chunk_text", "")).strip()
            title = str(metadata.get("title") or metadata.get("source_key") or "Local Legal Knowledge Base")
            current = evidence_by_key.get(dedupe_key)
            candidate = {
                "source_type": "pgvector",
                "category": "regulation",
                "title": title,
                "site_name": "Local Legal Knowledge Base",
                "url": None,
                "snippet": snippet[:400],
                "authority_score": 0.98,
                "relevance_score": similarity + (query_priority * 0.12),
                "dedupe_key": dedupe_key,
                "law_name": title,
                "metadata": metadata,
            }
            if current is None or float(candidate["relevance_score"]) > float(current["relevance_score"]):
                evidence_by_key[dedupe_key] = candidate

    return list(evidence_by_key.values())


def should_search_targeted_legal(
    *,
    question: str,
    pgvector_items: list[dict[str, object]],
    minimum_hits: int,
    minimum_top_score: float,
) -> bool:
    if EXTERNAL_CONTEXT_HINT_PATTERN.search(question):
        return True
    if len(pgvector_items) < minimum_hits:
        return True
    top_score = max((float(item.get("relevance_score", 0.0)) for item in pgvector_items), default=0.0)
    unique_titles = len({str(item.get("title", "")).strip() for item in pgvector_items if str(item.get("title", "")).strip()})
    return top_score < minimum_top_score or unique_titles < 2


def retrieve_targeted_legal_evidence(
    queries: list[dict[str, object]],
    *,
    max_results: int,
) -> list[dict[str, object]]:
    evidence_by_key: dict[str, dict[str, object]] = {}

    for query in queries:
        query_text = str(query.get("text", "")).strip()
        query_priority = float(query.get("priority", 0.5))
        if not query_text:
            continue

        results = search_legal_sources(query_text, max_results=max_results)
        for index, result in enumerate(results):
            url = str(result.get("url", "")).strip() or None
            title = str(result.get("title", "")).strip() or "Legal Search Result"
            snippet = str(result.get("snippet", "")).strip()
            dedupe_key = url or f"legal:{title}:{index}"
            candidate = {
                "source_type": "legal_search",
                "category": "regulation",
                "title": title,
                "site_name": result.get("site_name") or _extract_site_name(url),
                "url": url,
                "snippet": snippet[:400],
                "authority_score": 0.9,
                "relevance_score": 0.72 + (query_priority * 0.1) - (index * 0.02),
                "dedupe_key": dedupe_key,
                "law_name": title,
            }
            current = evidence_by_key.get(dedupe_key)
            if current is None or float(candidate["relevance_score"]) > float(current["relevance_score"]):
                evidence_by_key[dedupe_key] = candidate

    return list(evidence_by_key.values())


def should_search_general_web(
    *,
    question: str,
    targeted_items: list[dict[str, object]],
    minimum_hits: int,
) -> bool:
    if GENERAL_WEB_HINT_PATTERN.search(question):
        return True
    return len(targeted_items) < minimum_hits


def retrieve_general_web_evidence(
    queries: list[dict[str, object]],
    *,
    max_results: int,
) -> list[dict[str, object]]:
    evidence_by_key: dict[str, dict[str, object]] = {}

    for query in queries:
        query_text = str(query.get("text", "")).strip()
        query_priority = float(query.get("priority", 0.5))
        if not query_text:
            continue

        results = search_web(f"{query_text} 合同 法律", max_results=max_results)
        for index, result in enumerate(results):
            url = str(result.get("url", "")).strip() or None
            title = str(result.get("title", "")).strip() or "Web Search Result"
            snippet = str(result.get("snippet", "")).strip()
            dedupe_key = url or f"web:{title}:{index}"
            candidate = {
                "source_type": "web_search",
                "category": "web",
                "title": title,
                "site_name": result.get("site_name") or _extract_site_name(url),
                "url": url,
                "snippet": snippet[:320],
                "authority_score": 0.62,
                "relevance_score": 0.54 + (query_priority * 0.08) - (index * 0.02),
                "dedupe_key": dedupe_key,
            }
            current = evidence_by_key.get(dedupe_key)
            if current is None or float(candidate["relevance_score"]) > float(current["relevance_score"]):
                evidence_by_key[dedupe_key] = candidate

    return list(evidence_by_key.values())


def rerank_evidence_items(
    items: list[dict[str, object]],
    *,
    max_items: int,
) -> list[dict[str, object]]:
    sorted_items = sorted(
        items,
        key=lambda item: (
            float(item.get("authority_score", 0.0)) * 0.45
            + float(item.get("relevance_score", 0.0)) * 0.55
        ),
        reverse=True,
    )

    deduped: list[dict[str, object]] = []
    seen_titles: set[str] = set()
    for item in sorted_items:
        title = str(item.get("title", "")).strip().lower()
        url = str(item.get("url", "")).strip().lower()
        title_key = title or url
        if title_key and title_key in seen_titles:
            continue
        if title_key:
            seen_titles.add(title_key)
        deduped.append(item)
        if len(deduped) >= max_items:
            break

    return deduped


def build_answer_evidence_context(items: list[dict[str, object]]) -> str:
    if not items:
        return "No external supporting evidence was retrieved."

    lines: list[str] = []
    for index, item in enumerate(items, start=1):
        lines.append(
            "\n".join(
                [
                    f"[Evidence {index}]",
                    f"Source type: {item.get('source_type', 'unknown')}",
                    f"Title: {item.get('title', '')}",
                    f"Site: {item.get('site_name', '') or 'N/A'}",
                    f"URL: {item.get('url', '') or 'N/A'}",
                    f"Snippet: {item.get('snippet', '')}",
                ]
            )
        )
    return "\n\n".join(lines)


def build_source_payload(items: list[dict[str, object]]) -> list[dict[str, str]]:
    payload: list[dict[str, str]] = []
    for item in items:
        payload.append(
            {
                "category": str(item.get("category", "web")),
                "title": str(item.get("title", "")).strip(),
                "site_name": str(item.get("site_name", "")).strip(),
                "url": str(item.get("url", "")).strip(),
                "snippet": str(item.get("snippet", "")).strip(),
            }
        )
    return payload
