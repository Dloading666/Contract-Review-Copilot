"""
Aggregation Agent — LLM-powered
Generates the streamed final report.
"""
import os
import json
from datetime import datetime
from .entity_extraction import create_chat_completion, extract_entities
from .routing import decide_routing
from .logic_review import review_clauses
from ..llm_client import get_primary_model_key
from .legal_skill import LEGAL_RISK_ASSESSMENT_SKILL


REPORT_PROMPT = """你是一个专业的法律文档撰写助手。请根据以下合同审查结果，生成一份结构化的《避坑指南》报告。

合同基本信息：
- 出租方（甲方）：{lessor}
- 承租方（乙方）：{lessee}
- 租赁标的：{property_address}
- 建筑面积：约{property_area}平方米
- 月租金：人民币{monthly_rent:,}元
- 押金：人民币{deposit:,}元
- 租赁期限：{lease_term}

风险审查结果：
{risk_summary}

检索依据：
{legal_basis}

请生成一份专业、清晰的《避坑指南》，包含以下部分：

1. 合同基本信息（整理后）
2. 风险条款摘要（用emoji标注严重程度）
3. 每条风险的详细分析（条款内容、问题分析、处置建议、法律依据）
4. 综合评分（满分100）和审查结论

要求：
- 使用中文
- 语言严谨但易懂
- 处置建议要具体可操作
- 在最后加上免责声明

直接返回报告内容，不需要JSON格式。
"""


def generate_report(
    contract_text: str,
    issues: list[dict] | None = None,
    model_key: str | None = None,
) -> list[str]:
    """Use LLM to generate the final report, returned as paragraphs."""
    # Skip LLM if environment variable is set
    if os.getenv("SKIP_LLM_REPORT", "").lower() in ("1", "true", "yes"):
        return _template_report(contract_text, issues)

    try:
        entities = extract_entities(contract_text, model_key=model_key)
        # Issues are passed from the review phase – do not re-call review agents
        if issues is None:
            routing = decide_routing(contract_text, entities, model_key=model_key)
            issues = review_clauses(contract_text, routing, entities, model_key=model_key)

        lessor = entities.get("parties", {}).get("lessor", "未知")
        lessee = entities.get("parties", {}).get("lessee", "未知")
        prop = entities.get("property", {}).get("address", "未知")
        area = entities.get("property", {}).get("area", "未知")
        rent = entities.get("rent", {}).get("monthly", 0)
        deposit = entities.get("deposit", {}).get("amount", 0)
        lease_term = entities.get("lease_term", {}).get("duration_text", "未知")

        # Build risk summary
        critical = [i for i in issues if i.get("risk_level", 0) >= 5]
        high = [i for i in issues if 3 <= i.get("risk_level", 0) < 5]
        medium = [i for i in issues if 2 <= i.get("risk_level", 0) < 3]
        low = [i for i in issues if i.get("risk_level", 0) < 2]

        risk_lines = []
        if critical:
            risk_lines.append(f"🔴 高危风险 {len(critical)} 项：")
            for i in critical:
                risk_lines.append(f"  - [{i['clause']}] {i['issue'][:50]}...")
        if high:
            risk_lines.append(f"🟠 高风险 {len(high)} 项：")
            for i in high:
                risk_lines.append(f"  - [{i['clause']}] {i['issue'][:50]}...")
        if medium:
            risk_lines.append(f"🟡 中风险 {len(medium)} 项：")
            for i in medium:
                risk_lines.append(f"  - [{i['clause']}] {i['issue'][:50]}...")
        if low:
            risk_lines.append(f"🟢 提示 {len(low)} 项")
        risk_summary = "\n".join(risk_lines) if risk_lines else "未发现明显风险"

        # Legal basis summary
        legal_refs = list(set([i.get("legal_reference", "") for i in issues if i.get("legal_reference")]))
        legal_basis = "\n".join([f"- {ref}" for ref in legal_refs[:5]]) if legal_refs else "《民法典》合同编通则"

        system_content = LEGAL_RISK_ASSESSMENT_SKILL
        response = create_chat_completion(
            model=model_key or get_primary_model_key(),
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": REPORT_PROMPT.format(
                    lessor=lessor,
                    lessee=lessee,
                    property_address=prop,
                    property_area=area,
                    monthly_rent=rent,
                    deposit=deposit,
                    lease_term=lease_term,
                    risk_summary=risk_summary,
                    legal_basis=legal_basis,
                )},
            ],
            temperature=0.3,
            max_tokens=3072,
            timeout=60.0,
        )

        report_text = response.choices[0].message.content.strip()

        # Split into paragraphs by double newlines or section headers
        paragraphs = []
        current = ""
        for line in report_text.split("\n"):
            if line.startswith("## ") or line.startswith("### "):
                if current.strip():
                    paragraphs.append(current.strip())
                current = line
            elif line.strip() == "" and current.strip():
                if len(current) > 50:
                    paragraphs.append(current.strip())
                current = ""
            else:
                current += "\n" + line

        if current.strip():
            paragraphs.append(current.strip())

        # Add metadata paragraph if not present
        if not any("免责声明" in p for p in paragraphs):
            paragraphs.append(
                f"---\n⚠️ *本报告由 AI 自动生成，仅供参考。具体法律问题请咨询专业律师。*\n"
                f"📋 *报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
            )

        return paragraphs if paragraphs else [report_text]

    except Exception as e:
        print(f"[Aggregation] LLM call failed: {e}, using template fallback")
        return _template_report(contract_text, issues, model_key=model_key)


def _template_report(
    contract_text: str,
    issues: list[dict] | None = None,
    model_key: str | None = None,
) -> list[str]:
    """Fallback template-based report when LLM is unavailable."""
    entities = extract_entities(contract_text, model_key=model_key)
    if issues is None:
        issues = review_clauses(contract_text, model_key=model_key)

    lessor = entities.get("parties", {}).get("lessor", "未知")
    lessee = entities.get("parties", {}).get("lessee", "未知")
    prop = entities.get("property", {}).get("address", "未知")
    area = entities.get("property", {}).get("area", "未知")
    rent = entities.get("rent", {}).get("monthly", 0)
    deposit = entities.get("deposit", {}).get("amount", 0)

    paragraphs = [
        f"## 合同避坑指南\n\n尊敬的用户您好，以下是基于您提交的租赁合同进行的智能审查报告。",
        f"### 一、合同基本信息\n\n• 出租方（甲方）：{lessor}\n• 承租方（乙方）：{lessee}\n• 租赁标的：{prop}\n• 建筑面积：约{area}平方米\n• 月租金：人民币{rent:,.0f}元\n• 押金：人民币{deposit:,.0f}元",
        f"### 二、风险条款摘要\n\n共发现 {len(issues)} 条风险条款",
    ]

    for i, issue in enumerate(issues, 1):
        level_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(issue.get("level", "low"), "⚪")
        paragraphs.append(
            f"{level_emoji} **{issue['clause']}**（{issue.get('level', 'low').upper()}）\n\n"
            f"问题：{issue['issue']}\n\n"
            f"建议：{issue['suggestion']}\n\n"
            f"依据：{issue['legal_reference']}"
        )

    # Calculate score
    if any(i.get("risk_level", 0) >= 5 for i in issues):
        score = max(30, 100 - sum(5 for i in issues if i.get("risk_level", 0) >= 5) * 15)
        verdict = "存在高危条款，建议暂缓签约，优先协商修改。"
    elif any(i.get("risk_level", 0) >= 3 for i in issues):
        score = max(55, 100 - sum(3 for i in issues if i.get("risk_level", 0) >= 3) * 10)
        verdict = "存在风险条款，建议签约前与对方协商修改。"
    else:
        score = 80
        verdict = "条款基本合理，可放心签约。"

    paragraphs.append(
        f"### 三、综合评估\n\n**综合评分**：{score}/100\n\n**结论**：{verdict}\n\n"
        f"---\n⚠️ *本报告由 AI 自动生成，仅供参考。具体法律问题请咨询专业律师。*\n"
        f"📋 *报告生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*"
    )

    return paragraphs
