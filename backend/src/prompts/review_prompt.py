"""
Review prompts — centralised prompt templates for contract risk analysis.

Extracted from agents/logic_review.py so they can be versioned, tested,
and swapped independently of the agent logic.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Main review prompt (13 risk dimensions, JSON output)
# ---------------------------------------------------------------------------

REVIEW_PROMPT = """你是专业合同审查律师。严格依据合同原文逐条审查风险，不脱离原文臆测。

合同信息：{contract_info}
关键变量：月租金{monthly_rent}元 | 押金{deposit}元 | 押金退还：{deposit_conditions} | 违约金：{penalty_clause} | 滞纳金：{late_fee} | 解约：{termination_clause}

法规检索：{rag_context}

合同原文：
{contract_text}

审查维度（按合同类型「{contract_type}」侧重）：
1. 押金是否超2-3个月租金  2. 违约金是否超实际损失30%（民法典585条）
3. 滞纳金是否超年化LPR四倍  4. 押金退还条件是否明确
5. 提前解约违约金过高  6. 显失公平条款
7. 单方调整租金/费用  8. 自动续租是否对等
9. 维修责任转嫁承租人  10. 解约权不对等
11. 提前通知期不对等  12. 不合理禁止+高额罚款
13. 交付标准/设施状态不明确

要求：
- 优先依据原文，issue中点明具体条款内容
- clause写明条款编号/名称
- 没把握时设 confidence:"low"，不强行输出

直接返回JSON数组：
[{{{{
  "clause": "第X条",
  "level": "critical/high/medium/low",
  "risk_level": 1-5,
  "issue": "问题描述",
  "suggestion": "修正建议",
  "legal_reference": "法条",
  "confidence": "high/medium/low"
}}}}]"""


# ---------------------------------------------------------------------------
# Auto-fix prompt (clause revision)
# ---------------------------------------------------------------------------

AUTOFIX_PROMPT = """你是一个专业的合同修订专家。请根据以下风险信息，生成一条修正后的合同条款。

风险条款：{clause}
问题描述：{issue}
修正建议：{suggestion}
法律依据：{legal_ref}

请直接输出一段修正后的合同条款文本，用中括号【】标注关键修改处。
输出格式示例：
【建议将"押金不予退还"修改为"押金在扣除应由乙方承担的水电费及合理损耗费用后无息退还"】

直接输出修正文本，不要其他内容。
"""
