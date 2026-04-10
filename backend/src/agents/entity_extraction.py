"""
Entity Extraction Agent.
Uses the shared LLM router with Redis-backed response caching.
"""
import hashlib
import json
import os
from types import SimpleNamespace

from ..cache import build_cache_key, get_json, get_ttl_seconds, set_json
from ..llm_client import (
    create_chat_completion as _core_create_chat_completion,
    get_primary_model_key,
)


def _cached_chat_completion(content: str, model: str):
    return SimpleNamespace(
        model=model,
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    role="assistant",
                    content=content,
                )
            )
        ],
    )


def create_chat_completion(**kwargs):
    """
    统一的 LLM 调用入口，增加 Redis 缓存层。
    当设置 ANTHROPIC_API_KEY 时，路由至 Claude。
    """
    from .legal_skill import _is_claude_enabled, create_claude_completion, _get_claude_model
    if _is_claude_enabled():
        model = kwargs.pop("model", _get_claude_model())
        messages = kwargs.pop("messages", [])
        return create_claude_completion(messages, model, **kwargs)

    primary_model = kwargs.get("model", get_primary_model_key())

    cache_data = {
        "model": primary_model,
        "messages": kwargs.get("messages", []),
        "temperature": kwargs.get("temperature", 0.1),
        "max_tokens": kwargs.get("max_tokens", 1024),
    }
    cache_key = build_cache_key("llm", {
        "model": primary_model,
        "hash": hashlib.md5(json.dumps(cache_data, ensure_ascii=False).encode()).hexdigest(),
    })

    cached = get_json(cache_key)
    if cached and cached.get("content"):
        print(f"[LLM] 使用缓存: {primary_model}", flush=True)
        return _cached_chat_completion(cached["content"], cached.get("model", primary_model))

    response = _core_create_chat_completion(**kwargs)

    content = getattr(response.choices[0].message, "content", None)
    if content:
        set_json(
            cache_key,
            {"content": content, "model": getattr(response, "model", primary_model)},
            get_ttl_seconds("llm"),
        )

    return response


EXTRACTION_PROMPT = """你是一个专业的法律文档分析助手。请从以下合同文本中提取关键信息，以JSON格式返回。

要求提取的字段：
- contract_type: 合同类型（如：租赁合同、买卖合同）
- lessor: 出租方/卖方名称
- lessee: 承租方/买方名称
- property_address: 标的物地址或位置
- property_area: 建筑面积（数字，单位平方米）
- monthly_rent: 月租金（数字，单位元）
- total_rent: 合同总租金（数字，单位元）
- deposit: 押金金额（数字，单位元）
- deposit_conditions: 押金退还条件描述
- lease_start: 租赁开始日期
- lease_end: 租赁结束日期
- penalty_clause: 违约金条款原文
- late_fee: 滞纳金条款（如有）
- termination_clause: 解约条款（如有）

合同文本：
{contract_text}

请直接返回JSON，不要包含其他文字。确保所有数字字段返回实际数字而非文字。
"""

def extract_entities(contract_text: str, model_key: str | None = None) -> dict:
    """
    使用 LLM 从合同文本中提取结构化实体，失败时回退到正则匹配。
    """
    if os.getenv("SKIP_LLM_EXTRACTION", "").lower() in ("1", "true", "yes"):
        return _regex_fallback(contract_text)

    try:
        response = create_chat_completion(
            model=model_key or get_primary_model_key(),
            messages=[
                {"role": "system", "content": "你是一个专业的法律文档分析助手。"},
                {"role": "user", "content": EXTRACTION_PROMPT.format(contract_text=contract_text)},
            ],
            temperature=0.1,
            max_tokens=1024,
            timeout=15.0,
        )
        result_text = response.choices[0].message.content.strip()

        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0]
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0]

        data = json.loads(result_text.strip())

        return {
            "contract_type": data.get("contract_type", "租赁合同"),
            "parties": {
                "lessor": data.get("lessor", "未知"),
                "lessee": data.get("lessee", "未知"),
            },
            "property": {
                "address": data.get("property_address", "未明确"),
                "area": str(data.get("property_area", "未明确")),
            },
            "rent": {
                "monthly": float(data.get("monthly_rent", 0)),
                "total": float(data.get("total_rent", 0)),
                "currency": "人民币",
                "payment_cycle": "月付",
            },
            "deposit": {
                "amount": float(data.get("deposit", 0)),
                "conditions": data.get("deposit_conditions", "未明确"),
            },
            "lease_term": {
                "start": data.get("lease_start", "未明确"),
                "end": data.get("lease_end", "未明确"),
                "duration_text": f"{data.get('lease_start', '')} 至 {data.get('lease_end', '')}",
            },
            "penalty_clause": data.get("penalty_clause", "未约定"),
            "late_fee": data.get("late_fee"),
            "termination_clause": data.get("termination_clause"),
        }
    except Exception as e:
        print(f"[EntityExtraction] LLM call failed: {e}, falling back to regex")
        return _regex_fallback(contract_text)


def _regex_fallback(contract_text: str) -> dict:
    """LLM 不可用时的正则回退提取。"""
    import re

    def parse_num(s):
        s = s.replace(",", "").replace("，", "")
        if "万" in s:
            return float(re.sub(r"[^\d.]", "", s)) * 10000
        return float(re.sub(r"[^\d.]", "", s))

    text = contract_text

    def clean_party(value: str) -> str:
        return re.sub(r'（身份证[:：].*?）', '', value).strip()

    lessor = (
        re.search(r'(?:甲方[（(]出租方[）)]|出租方[（(]甲方[）)])[：:]\s*(.+?)(?:\n|$)', text)
        or re.search(r'甲方[：:]\s*(.+?)(?:\n|$)', text)
        or re.search(r'出租方[：:]\s*(.+?)(?:\n|$)', text)
    )
    lessee = (
        re.search(r'(?:乙方[（(]承租方[）)]|承租方[（(]乙方[）)])[：:]\s*(.+?)(?:\n|$)', text)
        or re.search(r'乙方[：:]\s*(.+?)(?:\n|$)', text)
        or re.search(r'承租方[：:]\s*(.+?)(?:\n|$)', text)
    )
    prop = (
        re.search(r'房屋地址[：:]\s*(.+?)(?:\n|$)', text)
        or re.search(r'(?:租赁|出租).*?(?:位于|坐落于)[：:]?\s*(.+?)(?:，|,|\n)', text, re.DOTALL)
    )
    rent = re.search(r'(?:月租金|租金)(?:[：:]\s*|为\s*)?(?:人民币)?\s*(?:[¥￥])?\s*([0-9,，.]+)\s*(?:元|万)', text)
    deposit = re.search(r'(?:押金|保证金)(?:[：:]\s*|为\s*)?(?:人民币)?\s*(?:[¥￥])?\s*([0-9,，.]+)(?:（[^）]+）)?\s*(?:元|万)', text)
    penalty = (
        re.search(r'(?:违约金条款|违约金)[：:]?\s*(.+?)(?:\n|$)', text)
        or re.search(r'(.{0,80}支付.+?作为违约金)(?:\n|$)', text)
        or re.search(r'(.{0,80}押金不予退还)(?:\n|$)', text)
    )
    area = re.search(r'(\d+)\s*(?:平方米|平米|m2)', text, re.IGNORECASE)
    dates = re.findall(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?)', text)
    deposit_conditions = re.search(r'押金退还条件[：:]\s*(.+?)(?:\n|$)', text)
    payment_cycle = re.search(r'(押一付一|押一付三|押二付一|押二付三|月付|季付|半年付|年付)', text)

    return {
        "contract_type": "租赁合同",
        "parties": {
            "lessor": clean_party(lessor.group(1)) if lessor else "未知",
            "lessee": clean_party(lessee.group(1)) if lessee else "未知",
        },
        "property": {
            "address": prop.group(1).strip() if prop else "未明确",
            "area": area.group(1) if area else "未明确",
        },
        "rent": {
            "monthly": parse_num(rent.group(1)) if rent else 0,
            "total": 0,
            "currency": "人民币",
            "payment_cycle": payment_cycle.group(1) if payment_cycle else ("月付" if "月付" in text else "约定支付"),
        },
        "deposit": {
            "amount": parse_num(deposit.group(1)) if deposit else 0,
            "conditions": deposit_conditions.group(1).strip() if deposit_conditions else (
                "租期届满且无损坏时全额退还" if "无损坏" in text or "正常" in text else "未明确条件"
            ),
        },
        "lease_term": {
            "start": dates[0] if dates else "未明确",
            "end": dates[1] if len(dates) > 1 else "未明确",
            "duration_text": f"{dates[0] if dates else ''} 至 {dates[1] if len(dates) > 1 else ''}",
        },
        "penalty_clause": penalty.group(1).strip() if penalty else "未约定",
    }
