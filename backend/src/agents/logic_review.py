"""
Logic Review Agent — LLM-powered
Performs numerical validation and clause risk analysis.
"""
import os
import json
from openai import OpenAI
from .entity_extraction import get_llm_client, extract_entities
from .routing import decide_routing
from ..search import build_search_context


REVIEW_PROMPT = """你是一个专业的合同审查律师。请分析以下租赁合同中的风险条款。

合同信息：
{contract_info}

已提取的关键变量：
- 月租金：{monthly_rent} 元
- 押金：{deposit} 元
- 押金退还条件：{deposit_conditions}
- 违约金条款：{penalty_clause}

请审查以下风险点并返回JSON数组格式的风险列表：

审查维度：
1. 押金是否超过2-3个月租金（违反地方规定）
2. 违约金是否超过实际损失的30%（民法典585条）
3. 滞纳金是否超过年化LPR四倍（约14.8%）
4. 押金退还条件是否明确（有无模糊地带）
5. 提前解约违约金是否过高
6. 合同是否存在其他显失公平的条款

对于每条发现的风险，返回：
- clause: 涉及的合同条款编号/名称
- level: critical/high/medium/low
- risk_level: 1-5的数字
- issue: 问题描述
- suggestion: 修正建议
- legal_reference: 相关法条

直接返回JSON数组，不要其他文字：
[
  {{
    "clause": "第8.2条",
    "level": "critical",
    "risk_level": 5,
    "issue": "违约金为合同总额200%，远超法定上限",
    "suggestion": "调整为不超过合同总额的30%",
    "legal_reference": "《民法典》第585条"
  }}
]
"""


def review_clauses(contract_text: str, routing: dict | None = None) -> list[dict]:
    """Use LLM to analyze contract clauses for risks."""
    try:
        entities = extract_entities(contract_text)

        # If routing not provided, run it inline
        if routing is None:
            routing = decide_routing(contract_text, entities)

        rent = entities.get("rent", {}).get("monthly", 0)
        deposit = entities.get("deposit", {}).get("amount", 0)

        # Build real search context (pgvector + DuckDuckGo)
        search_context = build_search_context(routing, entities)

        # Build prompt with all required values
        contract_info = (
            f"合同类型：{entities.get('contract_type', '租赁合同')}，"
            f"出租方：{entities.get('parties', {}).get('lessor', '未知')}，"
            f"承租方：{entities.get('parties', {}).get('lessee', '未知')}，"
            f"标的物：{entities.get('property', {}).get('address', '未知')}，"
            f"租赁期限：{entities.get('lease_term', {}).get('duration_text', '未知')}。"
        )

        prompt = REVIEW_PROMPT.format(
            contract_info=contract_info,
            monthly_rent=rent,
            deposit=deposit,
            deposit_conditions=entities.get("deposit", {}).get("conditions", "未明确"),
            penalty_clause=entities.get("penalty_clause", "未约定"),
            rag_context=search_context,
        )

        response = get_llm_client().chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "glm-5"),
            messages=[
                {"role": "system", "content": "你是一个专业的合同审查律师，擅长发现合同中的不公平条款和法律风险。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=2048,
        )

        result_text = response.choices[0].message.content.strip()

        # Parse JSON
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0]
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0]

        issues = json.loads(result_text.strip())

        # Ensure we have at least one issue
        if not issues:
            issues.append({
                "clause": "整体评估",
                "level": "low",
                "risk_level": 1,
                "issue": "未发现明显不公平条款，合同条款基本公平合理。",
                "suggestion": "建议仔细阅读各项条款，确保自身权益。",
                "legal_reference": "《民法典》合同编通则",
            })

        return issues
    except Exception as e:
        print(f"[LogicReview] LLM call failed: {e}, using rule-based fallback")
        return _rule_based_review(contract_text)


def _rule_based_review(contract_text: str) -> list[dict]:
    """Fallback rule-based review when LLM is unavailable."""
    import re

    issues = []
    text = contract_text

    def parse_num(s):
        s = s.replace(",", "").replace("，", "")
        if "万" in s:
            return float(re.sub(r"[^\d.]", "", s)) * 10000
        return float(re.sub(r"[^\d.]", "", s))

    rent_match = re.search(r'(?:月租金|租金)[为]?\s*(?:¥|￥)?\s*([0-9,，.]+)\s*(?:元|万)', text)
    deposit_match = re.search(r'(?:押金|保证金)[为]?\s*(?:¥|￥)?\s*([0-9,，.]+)\s*(?:元|万)', text)

    rent = parse_num(rent_match.group(1)) if rent_match else 0
    deposit = parse_num(deposit_match.group(1)) if deposit_match else 0

    # Check deposit ratio
    if deposit > 3 * rent and rent > 0:
        issues.append({
            "clause": "押金条款",
            "level": "critical",
            "risk_level": 5,
            "issue": f"押金（{deposit:.0f}元）超过3个月租金，可能违反住建部相关规定。",
            "suggestion": "要求将押金降至不超过2个月租金。",
            "legal_reference": "《城市房屋租赁管理办法》第9条",
        })
    elif deposit > 2 * rent and rent > 0:
        issues.append({
            "clause": "押金条款",
            "level": "high",
            "risk_level": 3,
            "issue": f"押金（{deposit:.0f}元）超过2个月租金，建议核实地方规定。",
            "suggestion": "明确押金退还条件和时限。",
            "legal_reference": "《民法典》第721条",
        })

    # Check penalty
    if "200%" in text or "两倍" in text or "双倍" in text:
        issues.append({
            "clause": "违约责任条款",
            "level": "critical",
            "risk_level": 5,
            "issue": "违约金规定为合同总额200%，远超法定上限（损失30%），可能被认定为无效条款。",
            "suggestion": "删除200%条款或调整为不超过合同总额30%。",
            "legal_reference": "《民法典》第585条",
        })

    # Check late fee
    late_match = re.search(r'逾期.*?(\d+(?:\.\d+)?)\s*%?\s*(?:滞纳金|利息)', text)
    if late_match:
        rate = float(late_match.group(1))
        if rate > 0.1:
            issues.append({
                "clause": "逾期滞纳金",
                "level": "critical",
                "risk_level": 5,
                "issue": f"日滞纳金{rate}%，年化约{rate*365:.0f}%，远超法定上限（LPR四倍约14.8%），条款无效。",
                "suggestion": "删除滞纳金条款或改为参照LPR利率。",
                "legal_reference": "《民法典》第585条",
            })

    if not issues:
        issues.append({
            "clause": "整体评估",
            "level": "low",
            "risk_level": 1,
            "issue": "未发现明显不公平条款。",
            "suggestion": "仔细阅读条款后再签约。",
            "legal_reference": "《民法典》合同编",
        })

    return issues
