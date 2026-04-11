"""
Search module — DuckDuckGo removed; returns empty results.
"""


def search_web(query: str, max_results: int = 5) -> list[dict]:
    return []


def search_legal(query: str, max_results: int = 3) -> str:
    return ""


def build_search_context(routing: dict, entities: dict) -> str:
    """Return static legal references only (no live web search)."""
    return """
【基础法律依据】：
1. 《民法典》第五百八十四条：当事人一方不履行合同义务或者履行合同义务不符合约定的，应当承担继续履行、采取补救措施或者赔偿损失等违约责任。
2. 《民法典》第五百八十五条：约定的违约金过分高于造成的损失的，人民法院或者仲裁机构可以根据当事人的请求予以适当减少。（判断标准：超过实际损失30%的，一般认定为"过分高于"）
3. 《民法典》第五百八十七条：债务人按照约定履行债务的，债权人应当返还定金。
4. 《城市房屋租赁管理办法》第九条：承租人应当按照约定的方法使用租赁房屋。
5. 《最高人民法院关于审理民间借贷案件适用法律若干问题的规定》第二十五条：借贷双方约定的利率超过合同成立时一年期贷款市场报价利率四倍的，超出部分人民法院不予支持。
"""
