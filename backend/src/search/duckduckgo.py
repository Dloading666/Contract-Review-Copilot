"""
DuckDuckGo Search — free, no API key required.
"""
import re
from duckduckgo_search import DDGS

from ..cache import build_cache_key, get_json, get_ttl_seconds, set_json


def search_web(query: str, max_results: int = 5) -> list[dict]:
    """
    Perform a web search using DuckDuckGo.

    Args:
        query: Search query string
        max_results: Maximum number of results to return (default 5)

    Returns:
        List of dicts with keys: title, url, description
    """
    cache_key = build_cache_key(
        "search",
        {
            "provider": "duckduckgo",
            "query": query,
            "max_results": max_results,
        },
    )
    cached_results = get_json(cache_key)
    if isinstance(cached_results, list):
        return cached_results

    try:
        results = []
        with DDGS(timeout=8) as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "description": r.get("body", ""),
                })
        set_json(cache_key, results, get_ttl_seconds("search"))
        return results
    except Exception as e:
        print(f"[DuckDuckGo] Search failed for '{query}': {e}")
        return []


def search_legal(query: str, max_results: int = 3) -> str:
    """
    Search for legal/regulatory information.

    Args:
        query: Legal search query (law name, regulation, etc.)
        max_results: Maximum number of results

    Returns:
        Formatted string of search results suitable for context injection
    """
    results = search_web(query, max_results=max_results)

    if not results:
        return f"未找到关于「{query}」的相关信息。"

    context_lines = [f"关于「{query}」的检索结果："]
    for i, r in enumerate(results, 1):
        context_lines.append(f"{i}. {r['title']}")
        context_lines.append(f"   来源：{r['url']}")
        if r.get("description"):
            context_lines.append(f"   摘要：{r['description'][:200]}")
        context_lines.append("")

    return "\n".join(context_lines)


def build_search_context(routing: dict, entities: dict) -> str:
    """
    Build a search context from routing decision and extracted entities.

    Args:
        routing: Routing decision dict with primary_source, secondary_source, legal_focus, pgvector_results
        entities: Extracted entity dict

    Returns:
        Search context string for LLM consumption
    """
    context_parts = []

    # Determine what to search based on routing
    legal_focus = routing.get("legal_focus", [])
    local_context = routing.get("local_context", "")

    # Include pgvector retrieval results if available
    pgvector_results = routing.get("pgvector_results", [])
    if pgvector_results:
        context_parts.append("【法律数据库检索结果】：")
        for chunk in pgvector_results:
            context_parts.append(f"\n【相关法规】{chunk.get('chunk_text', '')}")
        context_parts.append("")

    # Always include base legal references
    context_parts.append("""
【基础法律依据】：
1. 《民法典》第五百八十四条：当事人一方不履行合同义务或者履行合同义务不符合约定的，应当承担继续履行、采取补救措施或者赔偿损失等违约责任。
2. 《民法典》第五百八十五条：当事人可以约定一方违约时应当根据违约情况向对方支付一定数额的违约金，也可以约定因违约产生的损失赔偿额的计算方法。
   约定的违约金低于造成的损失的，人民法院或者仲裁机构可以根据当事人的请求予以增加；
   约定的违约金过分高于造成的损失的，人民法院或者仲裁机构可以根据当事人的请求予以适当减少。
   （判断标准：超过实际损失30%的，一般认定为"过分高于"）
3. 《民法典》第五百八十七条：债务人按照约定履行债务的，债权人应当返还定金。
4. 《城市房屋租赁管理办法》第九条：承租人应当按照约定的方法使用租赁房屋。
5. 《最高人民法院关于审理民间借贷案件适用法律若干问题的规定》第二十五条：借贷双方约定的利率超过合同成立时一年期贷款市场报价利率四倍的，超出部分人民法院不予支持。
""")

    # If secondary source is duckduckgo, perform real searches (best-effort, skip on failure)
    if routing.get("secondary_source") == "duckduckgo":
        import concurrent.futures
        search_queries = []

        # Add queries based on legal focus
        for focus in legal_focus[:2]:
            if "押金" in focus:
                search_queries.append("租房押金上限 法律规定 2024")
            elif "违约金" in focus:
                search_queries.append("租房违约金上限 民法典 司法解释")
            elif "提前解约" in focus:
                search_queries.append("租房提前解约违约金 法律规定")

        # Add local regulations if mentioned
        if local_context and "北京" in local_context:
            search_queries.append("北京市房屋租赁管理规定 押金")
        elif local_context and "上海" in local_context:
            search_queries.append("上海市房屋租赁管理规定 押金")

        # Perform searches with a hard outer timeout to avoid hanging
        for q in search_queries[:2]:
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(search_legal, q)
                    result = future.result(timeout=10)
                context_parts.append(f"\n{result}\n")
            except Exception as e:
                print(f"[DuckDuckGo] Skipping search '{q}': {e}")
                continue

    return "\n".join(context_parts)
