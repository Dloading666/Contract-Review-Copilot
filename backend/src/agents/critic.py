from __future__ import annotations

import json
import re
from .entity_extraction import create_chat_completion
from ..config import get_settings
from ..llm_client import get_primary_model_key
from ..graph.state import compute_finding_id, validate_finding

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


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _text_in_contract(matched_text: str, contract_text: str) -> bool:
    if not matched_text:
        return False
    norm_mt = _normalize_text(matched_text)
    norm_ct = _normalize_text(contract_text)
    return norm_mt in norm_ct


def _deterministic_validate(
    finding: dict,
    contract_text: str,
    evidence_ids: set[str],
) -> tuple[bool, str | None]:
    """Run deterministic checks before LLM critic."""
    if not finding.get("clause") or not finding.get("issue"):
        return False, "空clause或空issue"
    severity = finding.get("severity", "medium")
    if severity not in ("critical", "high", "medium", "low"):
        return False, f"非法severity: {severity}"
    risk_level = finding.get("risk_level", 3)
    if not (1 <= risk_level <= 5):
        return False, f"非法risk_level: {risk_level}"

    matched_text = finding.get("matched_text", "")
    if not matched_text:
        return False, "空matched_text"
    if not _text_in_contract(matched_text, contract_text):
        return False, f"matched_text未在合同原文中找到"

    ev_ids = finding.get("evidence_ids", [])
    agent_id = finding.get("agent_id", "")
    if agent_id != "rule_engine" and not ev_ids:
        return False, "模型Agent未提供evidence_ids"
    for eid in ev_ids:
        if eid and eid not in evidence_ids:
            return False, f"evidence_id不存在: {eid}"

    return True, None


def _deduplicate_by_id(findings: list[dict]) -> list[dict]:
    """Deduplicate by stable finding_id without modifying originals."""
    seen: dict[str, dict] = {}
    for f in findings:
        fid = f.get("finding_id", "")
        if fid not in seen:
            seen[fid] = dict(f)
    return list(seen.values())


def _cap_unverified(finding: dict) -> dict:
    """Cap risk level to medium for unverified model findings."""
    capped = dict(finding)
    if capped.get("risk_level", 3) > 3:
        capped["risk_level"] = 3
        capped["severity"] = "medium"
    capped["unverified"] = True
    return capped


def run_critic_agent(
    contract_text: str,
    candidate_findings: list[dict],
    evidence: list[dict],
    model_key: str | None = None,
) -> dict:
    settings = get_settings()
    model = settings.review_critic_model or model_key or get_primary_model_key()

    evidence_id_set = {e.get("id", "") for e in evidence}

    # Step 1: Deterministic validation
    passed_validation = []
    failed_validation = []
    for f in candidate_findings:
        ok, reason = _deterministic_validate(f, contract_text, evidence_id_set)
        if ok:
            passed_validation.append(f)
        else:
            failed_validation.append({**f, "rejection_reason": reason or "确定性校验失败"})

    if not passed_validation:
        return {"verified": [], "rejected": failed_validation, "degraded": True}

    # Step 2: Deduplicate by stable ID
    deduplicated = _deduplicate_by_id(passed_validation)

    # Step 3: LLM critic
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
        for f in deduplicated
    ], ensure_ascii=False)

    prompt = f"""合同原文：
{contract_text[:5000]}

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
        print(f"[{AGENT_ID}] LLM call failed: {exc}", flush=True)
        return _safe_degradation(deduplicated, failed_validation)

    parsed = _parse_verdicts(raw)
    if not parsed:
        print(f"[{AGENT_ID}] LLM returned no verdicts", flush=True)
        return _safe_degradation(deduplicated, failed_validation)

    # Step 4: Apply LLM verdicts
    finding_map = {f["finding_id"]: f for f in deduplicated}
    verified = []
    rejected = list(failed_validation)
    mentioned_ids = set()

    for verdict in parsed:
        fid = verdict.get("finding_id", "")
        mentioned_ids.add(fid)
        finding = finding_map.get(fid)
        if not finding:
            continue
        if verdict.get("accepted", False):
            adjusted = dict(finding)
            adj = verdict.get("severity_adjustment")
            if adj == "up" and adjusted.get("risk_level", 0) < 5:
                adjusted["risk_level"] = min(5, adjusted.get("risk_level", 3) + 1)
                adjusted["severity"] = _risk_to_severity(adjusted["risk_level"])
            elif adj == "down" and adjusted.get("risk_level", 0) > 1:
                adjusted["risk_level"] = max(1, adjusted.get("risk_level", 3) - 1)
                adjusted["severity"] = _risk_to_severity(adjusted["risk_level"])
            adjusted["critic_conflict_group"] = verdict.get("conflict_group")
            verified.append(adjusted)
        else:
            rejected.append({
                **finding,
                "rejection_reason": verdict.get("rejection_reason", "未通过复核"),
            })

    # Step 5: Handle unmentioned findings
    for f in deduplicated:
        if f["finding_id"] not in mentioned_ids:
            # Model finding not mentioned = unverified, cap to medium
            if f.get("agent_id") == "rule_engine":
                verified.append(f)
            else:
                verified.append(_cap_unverified(f))

    # Step 6: Deduplicate by conflict group
    verified = _deduplicate_by_conflict_group(verified)

    return {"verified": verified, "rejected": rejected, "degraded": False}


def _safe_degradation(
    deduplicated: list[dict],
    failed_validation: list[dict],
) -> dict:
    """Safe fallback when LLM critic fails completely."""
    verified = []
    for f in deduplicated:
        if f.get("agent_id") == "rule_engine":
            verified.append(f)
        elif validate_finding(f):
            verified.append(_cap_unverified(f))
    return {
        "verified": verified,
        "rejected": failed_validation,
        "degraded": True,
    }


def _risk_to_severity(risk_level: int) -> str:
    if risk_level >= 5:
        return "critical"
    if risk_level >= 4:
        return "high"
    if risk_level >= 3:
        return "medium"
    return "low"


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
        f_copy = dict(f)
        group = f_copy.pop("critic_conflict_group", None)
        if group:
            groups.setdefault(group, []).append(f_copy)
        else:
            ungrouped.append(f_copy)
    result = list(ungrouped)
    for group_findings in groups.values():
        best = max(group_findings, key=lambda x: (x.get("confidence", 0), x.get("risk_level", 0)))
        result.append(best)
    return result
