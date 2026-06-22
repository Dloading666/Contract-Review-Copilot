from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import json
from .entity_extraction import create_chat_completion
from ..config import get_settings
from ..llm_client import get_primary_model_key
from ..graph.state import FindingCandidate

AGENT_ID = "financial_performance"
ROLE_NAME = "财务履约审查"
DIMENSIONS = ("deposit", "penalty", "payment", "late_fee", "performance", "general")

SYSTEM_PROMPT = """你是专业的合同财务履约审查律师。专注于以下维度：
- 押金金额、退还条件、扣除规则
- 违约金比例、上限、触发条件
- 滞纳金计算方式、年化利率
- 租金支付方式、调整机制
- 费用分担、保证金、服务费
- 履行条件、交付标准

只输出JSON数组，不要其他文字。"""


def _build_prompt(contract_text: str, entities: dict, evidence: list[dict]) -> str:
    rent = entities.get("rent", {}).get("monthly", 0)
    deposit = entities.get("deposit", {}).get("amount", 0)
    evidence_lines = []
    for e in evidence[:5]:
        eid = e.get("id", "")
        title = e.get("title", "")
        econtent = e.get("content", "")[:200]
        evidence_lines.append(f"[{eid}] {title}: {econtent}")
    evidence_text = "\n".join(evidence_lines) or "无额外检索依据"
    lessor = entities.get("parties", {}).get("lessor", "未知")
    lessee = entities.get("parties", {}).get("lessee", "未知")
    dims = list(DIMENSIONS)

    return f"""合同信息：月租金{rent}元，押金{deposit}元
出租方：{lessor}
承租方：{lessee}

检索依据：
{evidence_text}

合同原文：
{contract_text[:6000]}

请以JSON数组返回每条风险，每条包含：
clause, dimension(从{dims}中选), issue, severity(critical/high/medium/low),
risk_level(1-5), confidence(0-1), legal_references(数组), evidence_ids(数组),
suggestion, matched_text(原文引用)"""


def _parse_findings(raw: str) -> list[dict]:
    text = raw.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0]
    start = text.find("[")
    if start == -1:
        start = text.find("{")
        if start == -1:
            return []
        try:
            obj = json.loads(text[start:])
            return [obj] if isinstance(obj, dict) else []
        except json.JSONDecodeError:
            return []
    try:
        parsed = json.loads(text[start:])
        return parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        return []


def run_financial_agent(
    contract_text: str,
    entities: dict,
    evidence: list[dict],
    model_key: str | None = None,
) -> list[dict]:
    settings = get_settings()
    model = settings.review_specialist_model or model_key or get_primary_model_key()
    try:
        response = create_chat_completion(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _build_prompt(contract_text, entities, evidence)},
            ],
            temperature=settings.review_temperature,
            max_tokens=4096,
            timeout=settings.review_model_timeout_seconds,
            allow_fallback=False,
        )
        raw = response.choices[0].message.content.strip()
    except Exception as exc:
        logger.exception("[%s] LLM call failed: %s", AGENT_ID, exc)
        return []

    parsed = _parse_findings(raw)
    if not parsed:
        logger.error("[%s] JSON parse failed, raw=%s", AGENT_ID, raw[:200])
        return []

    results = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        dimension = item.get("dimension", "general")
        if dimension not in DIMENSIONS:
            dimension = "general"
        try:
            fc = FindingCandidate(
                agent_id=AGENT_ID,
                dimension=dimension,
                clause=item.get("clause", "未知条款"),
                matched_text=item.get("matched_text", ""),
                issue=item.get("issue", ""),
                severity=item.get("severity", "medium"),
                risk_level=int(item.get("risk_level", 3)),
                confidence=float(item.get("confidence", 0.5)),
                legal_references=item.get("legal_references", []),
                evidence_ids=item.get("evidence_ids", []),
                suggestion=item.get("suggestion", ""),
            )
            results.append(fc.model_dump())
        except Exception as exc:
            logger.warning("[%s] Skipping invalid finding: %s", AGENT_ID, exc)
    return results
