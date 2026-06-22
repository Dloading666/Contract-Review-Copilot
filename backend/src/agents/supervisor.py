from __future__ import annotations

import json
from .entity_extraction import create_chat_completion
from ..config import get_settings
from ..llm_client import get_primary_model_key

AGENT_ID = "supervisor"
ROLE_NAME = "主管裁决"

SYSTEM_PROMPT = """你是合同审查主管。你的任务是合并已通过复核的审查结论，生成最终结果。

规则：
1. 只处理已通过复核的finding，不创造新的条款、事实或法律依据
2. 确定每条的最终严重程度
3. 合并同一条款的相关发现
4. 输出整体风险评估和简要总结

输出JSON对象：
{
  "final_findings": [{"finding_id":"...", "final_severity":"...", "final_risk_level":1-5, "summary":"..."}],
  "overall_risk": "critical/high/medium/low",
  "summary": "总体评估"
}

只输出JSON，不要其他文字。"""


def run_supervisor_agent(
    contract_text: str,
    verified_findings: list[dict],
    model_key: str | None = None,
) -> dict:
    if not verified_findings:
        return {
            "final_findings": [],
            "overall_risk": "low",
            "summary": "未发现明显风险条款。",
        }

    settings = get_settings()
    model = settings.review_supervisor_model or model_key or get_primary_model_key()

    findings_summary = json.dumps([
        {
            "finding_id": f.get("finding_id", ""),
            "agent_id": f.get("agent_id", ""),
            "clause": f.get("clause", ""),
            "issue": f.get("issue", ""),
            "severity": f.get("severity", ""),
            "risk_level": f.get("risk_level", 0),
            "confidence": f.get("confidence", 0),
            "legal_references": f.get("legal_references", []),
            "suggestion": f.get("suggestion", ""),
        }
        for f in verified_findings
    ], ensure_ascii=False)

    prompt = f"""合同原文（前2000字）：
{contract_text[:2000]}

已通过复核的审查结论：
{findings_summary}

请合并输出最终审查结果。"""

    try:
        response = create_chat_completion(
            model=model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=2048,
            timeout=settings.review_report_timeout_seconds,
            allow_fallback=False,
        )
        raw = response.choices[0].message.content.strip()
    except Exception as exc:
        print(f"[{AGENT_ID}] LLM call failed: {exc}, using fallback merge", flush=True)
        return _fallback_merge(verified_findings)

    return _parse_supervisor_result(raw, verified_findings)


def _parse_supervisor_result(raw: str, verified_findings: list[dict]) -> dict:
    text = raw.strip()
    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0]
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0]
    start = text.find("{")
    if start == -1:
        return _fallback_merge(verified_findings)
    try:
        data = json.loads(text[start:])
    except json.JSONDecodeError:
        return _fallback_merge(verified_findings)

    final_findings_raw = data.get("final_findings", [])
    if not isinstance(final_findings_raw, list):
        final_findings_raw = []

    # Only keep findings that exist in verified_findings
    finding_map = {f["finding_id"]: f for f in verified_findings if "finding_id" in f}
    enriched = []
    for ff in final_findings_raw:
        fid = ff.get("finding_id", "")
        original = finding_map.get(fid)
        if not original:
            continue
        merged = dict(original)
        # Map final_severity -> severity
        if "final_severity" in ff:
            sv = ff["final_severity"]
            if sv in ("critical", "high", "medium", "low"):
                merged["severity"] = sv
        # Map final_risk_level -> risk_level
        if "final_risk_level" in ff:
            rl = ff["final_risk_level"]
            if isinstance(rl, int) and 1 <= rl <= 5:
                merged["risk_level"] = rl
        if "summary" in ff:
            merged["supervisor_summary"] = ff["summary"]
        enriched.append(merged)

    overall_risk = data.get("overall_risk", "medium")
    if overall_risk not in ("critical", "high", "medium", "low"):
        overall_risk = "medium"

    return {
        "final_findings": enriched if enriched else verified_findings,
        "overall_risk": overall_risk,
        "summary": data.get("summary", "审查完成"),
    }


def _fallback_merge(findings: list[dict]) -> dict:
    max_risk = max((f.get("risk_level", 0) for f in findings), default=0)
    if max_risk >= 5:
        overall = "critical"
    elif max_risk >= 4:
        overall = "high"
    elif max_risk >= 3:
        overall = "medium"
    else:
        overall = "low"
    return {
        "final_findings": findings,
        "overall_risk": overall,
        "summary": f"审查完成，共发现 {len(findings)} 条风险。",
    }
