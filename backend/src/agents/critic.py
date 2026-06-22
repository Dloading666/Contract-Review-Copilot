from __future__ import annotations

import json
from .entity_extraction import create_chat_completion
from ..config import get_settings
from ..llm_client import get_primary_model_key

AGENT_ID = "critic"
ROLE_NAME = "交叉复核"

SYSTEM_PROMPT = """你是合同审查复核专家。你的任务是核验其他Agent的审查结果：

1. 确认 matched_text 能在合同原文中定位到
2. 确认 evidence_ids 指向实际存在的检索结果
3. 合并同条款同问题的重复发现
4. 冲突意见保留置信度高且证据充分的
5. 检查风险等级是否合理

对每个finding输出：finding_id, accepted(true/false), rejection_reason, severity_adjustment(可选), conflict_group(可选用于去重分组)

只输出JSON数组。"""


def run_critic_agent(
    contract_text: str,
    candidate_findings: list[dict],
    evidence: list[dict],
    model_key: str | None = None,
) -> dict:
    settings = get_settings()
    model = settings.review_critic_model or model_key or get_primary_model_key()

    evidence_lines = []
    for e in evidence[:10]:
        eid = e.get("id", "")
        title = e.get("title", "")
        content = e.get("content", "")[:150]
        evidence_lines.append(f"[{eid}] {title}: {content}")
    evidence_text = "\n".join(evidence_lines) or "无检索依据"

    findings_summary = json.dumps([
        {
            "finding_id": f.get("finding_id", ""),
            "agent_id": f.get("agent_id", ""),
            "clause": f.get("clause", ""),
            "matched_text": f.get("matched_text", "")[:100],
            "issue": f.get("issue", ""),
            "severity": f.get("severity", ""),
            "risk_level": f.get("risk_level", 0),
            "confidence": f.get("confidence", 0),
            "evidence_ids": f.get("evidence_ids", []),
        }
        for f in candidate_findings
    ], ensure_ascii=False)

    prompt = f"""合同原文（前3000字）：
{contract_text[:3000]}

检索依据：
{evidence_text}

待复核发现：
{findings_summary}

请逐条核验，返回JSON数组，每条包含：
finding_id, accepted(bool), rejection_reason(null if accepted),
severity_adjustment(null or "up"/"down"), conflict_group(null or string)"""

    try:
        response = create_chat_completion(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=2048,
            timeout=settings.review_model_timeout_seconds,
            allow_fallback=False,
        )
        raw = response.choices[0].message.content.strip()
    except Exception as exc:
        print(f"[{AGENT_ID}] LLM call failed: {exc}, accepting all findings", flush=True)
        return {"verified": candidate_findings, "rejected": [], "degraded": True}

    parsed = _parse_verdicts(raw)
    finding_map = {f["finding_id"]: f for f in candidate_findings}
    verified = []
    rejected = []

    for verdict in parsed:
        fid = verdict.get("finding_id", "")
        finding = finding_map.get(fid)
        if not finding:
            continue
        if verdict.get("accepted", False):
            adjusted = dict(finding)
            adj = verdict.get("severity_adjustment")
            if adj == "up" and adjusted.get("risk_level", 0) < 5:
                adjusted["risk_level"] = min(5, adjusted.get("risk_level", 3) + 1)
            elif adj == "down" and adjusted.get("risk_level", 0) > 1:
                adjusted["risk_level"] = max(1, adjusted.get("risk_level", 3) - 1)
            adjusted["critic_conflict_group"] = verdict.get("conflict_group")
            verified.append(adjusted)
        else:
            rejected.append({
                **finding,
                "rejection_reason": verdict.get("rejection_reason", "未通过复核"),
            })

    verified = _deduplicate_by_conflict_group(verified)

    mentioned_ids = {v.get("finding_id") for v in parsed}
    for f in candidate_findings:
        if f["finding_id"] not in mentioned_ids:
            verified.append(f)

    return {"verified": verified, "rejected": rejected, "degraded": False}


def _parse_verdicts(raw: str) -> list[dict]:
    text = raw.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0]
    start = text.find("[")
    if start == -1:
        return []
    try:
        parsed = json.loads(text[start:])
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def _deduplicate_by_conflict_group(findings: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    ungrouped = []
    for f in findings:
        group = f.pop("critic_conflict_group", None)
        if group:
            groups.setdefault(group, []).append(f)
        else:
            ungrouped.append(f)
    result = list(ungrouped)
    for group_findings in groups.values():
        best = max(group_findings, key=lambda x: (x.get("confidence", 0), x.get("risk_level", 0)))
        result.append(best)
    return result
