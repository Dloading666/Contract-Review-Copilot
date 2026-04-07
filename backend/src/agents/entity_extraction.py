"""
Entity Extraction Agent — ZhipuAI GLM-5 Implementation
Uses LLM to extract key variables from contract text.
"""
import os
import json
from openai import OpenAI


def get_llm_client() -> OpenAI:
    return OpenAI(
        api_key=os.getenv("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY")),
        base_url=os.getenv("OPENAI_BASE_URL", "https://coding.dashscope.aliyuncs.com/v1"),
    )


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

def extract_entities(contract_text: str) -> dict:
    """
    Use GLM-5 to extract structured entities from contract text.
    Falls back to regex-based extraction on error.
    """
    try:
        client = get_llm_client()
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "glm-5"),
            messages=[
                {"role": "system", "content": "你是一个专业的法律文档分析助手。"},
                {"role": "user", "content": EXTRACTION_PROMPT.format(contract_text=contract_text)},
            ],
            temperature=0.1,
            max_tokens=1024,
        )
        result_text = response.choices[0].message.content.strip()

        # Parse JSON from response
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
    """Fallback regex-based extraction when LLM is unavailable."""
    import re

    def parse_num(s):
        s = s.replace(",", "").replace("，", "")
        if "万" in s:
            return float(re.sub(r"[^\d.]", "", s)) * 10000
        return float(re.sub(r"[^\d.]", "", s))

    text = contract_text

    lessor = re.search(r'出租方[（(]甲方[）)][：:]\s*(.+?)(?:\n|$)', text)
    lessee = re.search(r'承租方[（(]乙方[）)][：:]\s*(.+?)(?:\n|$)', text)
    prop = re.search(r'(?:租赁|出租).*?(?:位于|坐落于)[：:]?\s*(.+?)(?:，|,|\n)', text, re.DOTALL)
    rent = re.search(r'(?:月租金|租金)[为]?\s*(?:人民币)?\s*(?:[¥￥])?\s*([0-9,，.]+)\s*(?:元|万)', text)
    deposit = re.search(r'(?:押金|保证金)[为]?\s*(?:人民币)?\s*(?:[¥￥])?\s*([0-9,，.]+)\s*(?:元|万)', text)
    penalty = re.search(r'(?:违约|违约金)[：:]?\s*(.+?)(?:\n|$)', text)
    area = re.search(r'(\d+)\s*(?:平方米|平米|m2)', text, re.IGNORECASE)
    dates = re.findall(r'(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}日?)', text)

    return {
        "contract_type": "租赁合同",
        "parties": {
            "lessor": lessor.group(1).strip() if lessor else "未知",
            "lessee": lessee.group(1).strip() if lessee else "未知",
        },
        "property": {
            "address": prop.group(1).strip() if prop else "未明确",
            "area": area.group(1) if area else "未明确",
        },
        "rent": {
            "monthly": parse_num(rent.group(1)) if rent else 0,
            "total": 0,
            "currency": "人民币",
            "payment_cycle": "月付" if "月付" in text else "约定支付",
        },
        "deposit": {
            "amount": parse_num(deposit.group(1)) if deposit else 0,
            "conditions": "租期届满且无损坏时全额退还" if "无损坏" in text or "正常" in text else "未明确条件",
        },
        "lease_term": {
            "start": dates[0] if dates else "未明确",
            "end": dates[1] if len(dates) > 1 else "未明确",
            "duration_text": f"{dates[0] if dates else ''} 至 {dates[1] if len(dates) > 1 else ''}",
        },
        "penalty_clause": penalty.group(1).strip() if penalty else "未约定",
    }
