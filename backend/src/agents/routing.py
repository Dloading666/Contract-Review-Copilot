"""
Routing Agent — LLM-powered
Decides search strategy: pgvector RAG vs DuckDuckGo web search.
"""
import os
import json
from .entity_extraction import create_chat_completion
from ..config import get_settings
from ..llm_client import get_primary_model_key

# pgvector imports
try:
    from ..vectorstore.store import retrieve_similar_chunks
    from ..vectorstore.connection import DATABASE_URL
    PGVECTOR_AVAILABLE = bool(DATABASE_URL)
except Exception:
    PGVECTOR_AVAILABLE = False
    retrieve_similar_chunks = None


ROUTING_PROMPT = """你是一个智能法律检索系统。请分析以下合同的关键特征，决定检索策略。

合同基本信息：
- 合同类型：{contract_type}
- 标的金额：月租 {monthly_rent} 元，押金 {deposit} 元
- 合同性质：{property_type}

请决定检索策略：

1. primary_source: 固定为 "pgvector"（法律数据库）

2. reason: 解释选择理由（1-2句话）

3. confidence: 置信度 0.0-1.0

4. local_context: 本合同适用的地方性规定说明

5. legal_focus: 本合同最需要关注的3个法律领域（如：违约金上限、押金退还、租赁期限）

直接返回JSON，不要其他文字：
{{
  "primary_source": "pgvector",
  "secondary_source": null,
  "reason": "这是标准住宅租赁合同，适用全国性法律为主...",
  "confidence": 0.92,
  "local_context": "住宅租赁以全国性法律为准。",
  "legal_focus": ["违约金上限", "押金退还条件", "提前解约通知"]
}}
"""


def decide_routing(contract_text: str, entities: dict, model_key: str | None = None) -> dict:
    """Use LLM to decide retrieval strategy."""
    # Skip LLM if environment variable is set
    if os.getenv("SKIP_LLM_ROUTING", "").lower() in ("1", "true", "yes"):
        return _default_routing(contract_text, entities)

    try:
        settings = get_settings()
        rent = entities.get("rent", {}).get("monthly", 0)
        deposit = entities.get("deposit", {}).get("amount", 0)
        prop_type = "住宅租赁" if any(w in contract_text for w in ["住宅", "公寓", "住房"]) else "商业租赁"

        response = create_chat_completion(
            model=model_key or get_primary_model_key(),
            messages=[
                {"role": "system", "content": "你是一个智能法律检索系统。"},
                {"role": "user", "content": ROUTING_PROMPT.format(
                    contract_type=entities.get("contract_type", "租赁合同"),
                    monthly_rent=rent,
                    deposit=deposit,
                    property_type=prop_type,
                )},
            ],
            temperature=settings.review_temperature,
            max_tokens=512,
            timeout=settings.review_routing_timeout_seconds,
            allow_fallback=False,
        )
        print(f"[Routing] LLM response received", flush=True)

        result_text = response.choices[0].message.content.strip()

        # Parse JSON
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0]
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0]

        data = json.loads(result_text.strip())

        routing = {
            "primary_source": data.get("primary_source", "pgvector"),
            "secondary_source": data.get("secondary_source", "duckduckgo"),
            "reason": data.get("reason", ""),
            "confidence": float(data.get("confidence", 0.9)),
            "local_context": data.get("local_context", ""),
            "legal_focus": data.get("legal_focus", []),
        }

        # Perform actual pgvector retrieval if primary source is pgvector
        if routing["primary_source"] == "pgvector" and PGVECTOR_AVAILABLE:
            try:
                # Build query from legal focus areas
                focus_areas = routing.get("legal_focus", [])
                query = contract_text[:500] if not focus_areas else "、".join(focus_areas[:3])
                chunks = retrieve_similar_chunks(query, top_k=5, min_similarity=0.3)
                routing["pgvector_results"] = chunks
            except Exception as e:
                print(f"[Routing] pgvector retrieval failed: {e}", flush=True)
                routing["pgvector_results"] = []

        return routing
    except Exception as e:
        return _default_routing(contract_text, entities)


def _default_routing(contract_text: str, entities: dict) -> dict:
    rent = entities.get("rent", {}).get("monthly", 0)
    prop_type = "住宅" if any(w in contract_text for w in ["住宅", "公寓"]) else "商业"

    return {
        "primary_source": "pgvector",
        "secondary_source": None,
        "reason": f"这是{prop_type}租赁合同，建议优先检索《民法典》和相关司法解释。",
        "confidence": 0.85,
        "local_context": "如为北京地区商业租赁，建议同时检索《北京市房地产租赁管理办法》。" if prop_type == "商业" else "住宅租赁以全国性法律为准。",
        "legal_focus": ["违约金上限", "押金退还", "合同解除权"],
    }
