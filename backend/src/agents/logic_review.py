"""
Logic Review Agent — LLM-powered
Performs numerical validation and clause risk analysis.
"""
import os
import json
import re
from .entity_extraction import create_chat_completion, extract_entities
from .routing import decide_routing
from .legal_skill import _is_claude_enabled, REVIEW_CONTRACT_SKILL
from ..search import build_search_context


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


def generate_clause_fix(clause: str, issue: str, suggestion: str, legal_ref: str) -> str:
    """Use LLM to generate a suggested clause revision."""
    try:
        response = create_chat_completion(
            model=os.getenv("OPENAI_MODEL", "glm-5"),
            messages=[
                {"role": "system", "content": "你是一个专业的合同修订专家，擅长将不公平条款修改为合法合理的表述。"},
                {"role": "user", "content": AUTOFIX_PROMPT.format(
                    clause=clause,
                    issue=issue,
                    suggestion=suggestion,
                    legal_ref=legal_ref,
                )},
            ],
            temperature=0.3,
            max_tokens=512,
            timeout=15.0,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[AutoFix] LLM call failed: {e}")
        return f"建议将「{clause}」条款修改为：{suggestion}（依据：{legal_ref}）"


REVIEW_PROMPT = """你是一个专业的合同审查律师。请分析以下租赁合同中的风险条款。

合同信息：
{contract_info}

已提取的关键变量：
- 月租金：{monthly_rent} 元
- 押金：{deposit} 元
- 押金退还条件：{deposit_conditions}
- 违约金条款：{penalty_clause}

法规检索上下文：
{rag_context}

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


def _normalize_issue(issue: dict) -> dict:
    """Normalize model output so the frontend and aggregation use a stable shape."""
    level = issue.get("level") or issue.get("severity") or "low"
    return {
        "clause": issue.get("clause", "整体评估"),
        "level": level,
        "severity": level,
        "risk_level": int(issue.get("risk_level", 1)),
        "issue": issue.get("issue", "未提供问题描述。"),
        "suggestion": issue.get("suggestion", "建议进一步核对原合同条款。"),
        "legal_reference": issue.get("legal_reference") or issue.get("legalRef") or "《民法典》合同编",
    }


RISK_KEYWORDS = (
    "押金",
    "保证金",
    "违约金",
    "违约",
    "自动退租",
    "解约",
    "解除",
    "提前解除",
    "提前退租",
    "退租",
    "逾期",
    "滞纳金",
    "利息",
    "转租",
    "二房东",
    "租金贷",
    "服务费",
    "管理费",
    "维修",
    "免责",
    "断水断电",
    "中介费",
    "水电",
    "返还",
    "续租",
    "通知",
    "原房东",
    "托管协议",
    "仲裁",
    "甲方所在地",
)


def _normalize_text(text: str) -> str:
    return re.sub(r"[\s\u3000，。、《》“”\"'：:；;（）()【】\[\]、\-]", "", text or "")


def _build_issue_keywords(issue: dict) -> list[str]:
    source_text = " ".join(
        [
            issue.get("clause", ""),
            issue.get("issue", ""),
            issue.get("suggestion", ""),
        ]
    )
    keywords: list[str] = []

    for keyword in RISK_KEYWORDS:
        if keyword in source_text:
            keywords.append(keyword)

    clause_text = issue.get("clause", "")
    if clause_text and clause_text not in ("整体评估", "风险评估"):
        keywords.append(clause_text)

    return list(dict.fromkeys(keyword for keyword in keywords if len(keyword) >= 2))


def _find_issue_excerpt(contract_text: str, issue: dict) -> str:
    keywords = _build_issue_keywords(issue)
    if not keywords:
        return ""

    best_line = ""
    best_score = 0

    for raw_line in contract_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        normalized_line = _normalize_text(line)
        score = 0
        for keyword in keywords:
            normalized_keyword = _normalize_text(keyword)
            if normalized_keyword and normalized_keyword in normalized_line:
                score += max(len(normalized_keyword), 2)

        if score > best_score:
            best_score = score
            best_line = line

    return best_line if best_score >= 2 else ""


def _attach_issue_context(issues: list[dict], contract_text: str) -> list[dict]:
    enriched_issues = []
    for issue in issues:
        enriched_issues.append({
            **issue,
            "matched_text": _find_issue_excerpt(contract_text, issue),
        })
    return enriched_issues


def _merge_issue_lists(*issue_groups: list[dict]) -> list[dict]:
    merged: list[dict] = []
    seen: set[str] = set()

    for issues in issue_groups:
        for issue in issues:
            key = f"{_normalize_text(issue.get('clause', ''))}|{_normalize_text(issue.get('issue', ''))}"
            if key in seen:
                continue
            seen.add(key)
            merged.append(issue)

    has_substantive_issue = any(issue.get("risk_level", 0) > 1 for issue in merged)
    if has_substantive_issue:
        merged = [
            issue for issue in merged
            if not (
                issue.get("risk_level", 0) <= 1
                and issue.get("clause") == "整体评估"
            )
        ]

    return merged


def review_clauses(contract_text: str, routing: dict | None = None, entities: dict | None = None) -> list[dict]:
    """Use LLM to analyze contract clauses for risks."""
    # Skip LLM if environment variable is set (for slow API environments)
    if os.getenv("SKIP_LLM_REVIEW", "").lower() in ("1", "true", "yes"):
        print("[LogicReview] SKIP_LLM_REVIEW is set, using rule-based fallback")
        return _rule_based_review(contract_text)

    try:
        # Use pre-extracted entities if provided, otherwise extract
        if entities is None:
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
            rag_context=search_context or "未检索到额外法规上下文，请基于合同文本和通用法律原则审查。",
        )

        system_content = REVIEW_CONTRACT_SKILL
        response = create_chat_completion(
            model=os.getenv("OPENAI_MODEL", "glm-5"),
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=2048,
            timeout=15.0,
        )

        result_text = response.choices[0].message.content.strip()

        # Parse JSON
        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0]
        elif "```" in result_text:
            result_text = result_text.split("```")[1].split("```")[0]

        issues = json.loads(result_text.strip())
        if isinstance(issues, dict):
            issues = [issues]
        issues = [_normalize_issue(issue) for issue in issues]
        issues = _attach_issue_context(issues, contract_text)
        issues = _merge_issue_lists(issues, _rule_based_review(contract_text))

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

    rent_match = re.search(r'(?:月租金|租金)(?:[：:]\s*|为\s*)?(?:人民币)?\s*(?:¥|￥)?\s*([0-9,，.]+)\s*(?:元|万)', text)
    deposit_match = re.search(r'(?:押金|保证金)(?:[：:]\s*|为\s*)?(?:人民币)?\s*(?:¥|￥)?\s*([0-9,，.]+)(?:（[^）]+）)?\s*(?:元|万)', text)

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

    # Check obviously excessive liquidated damages
    if "200%" in text or "两倍" in text or "双倍" in text:
        issues.append({
            "clause": "违约责任条款",
            "level": "critical",
            "risk_level": 5,
            "issue": "违约金规定为合同总额200%，远超法定上限（损失30%），可能被认定为无效条款。",
            "suggestion": "删除200%条款或调整为不超过合同总额30%。",
            "legal_reference": "《民法典》第585条",
        })

    if re.search(r'提前退租.+?两个月租金.+?违约金', text):
        issues.append({
            "clause": "提前退租违约金条款",
            "level": "high",
            "risk_level": 4,
            "issue": "提前退租需支付两个月租金作为违约金，标准明显偏高，可能被认定为过分加重承租人责任。",
            "suggestion": "将违约责任调整为以实际损失为基础，或降为不超过一个月租金。",
            "legal_reference": "《民法典》第585条",
        })

    if "押金不予退还" in text:
        issues.append({
            "clause": "押金退还条款",
            "level": "high",
            "risk_level": 4,
            "issue": "合同约定逾期后押金不予退还，属于对承租人明显不利的格式条款。",
            "suggestion": "改为在扣除实际欠费和合理损失后返还剩余押金，并明确结算依据。",
            "legal_reference": "《民法典》第497条",
        })

    if "断水断电且不构成违约" in text:
        issues.append({
            "clause": "断水断电免责条款",
            "level": "critical",
            "risk_level": 5,
            "issue": "甲方单方断水断电且主张不构成违约，涉嫌以自力救济方式限制承租人基本使用权益。",
            "suggestion": "删除断水断电免责约定，争议应通过催告、协商或司法途径处理。",
            "legal_reference": "《民法典》第509条",
        })

    if "无需联系原房东" in text or "托管协议" in text:
        issues.append({
            "clause": "出租权限与房东身份条款",
            "level": "critical",
            "risk_level": 5,
            "issue": "合同显示出租方仅称已与房东签署托管协议，并要求承租人无需联系原房东，存在无权出租、冒充房东或转委托不明的重大风险。",
            "suggestion": "签约前要求出示房产证、房东身份证明、授权委托书及托管协议原件，并核验房东联系方式。",
            "legal_reference": "《民法典》第716条",
        })

    if re.search(r'甲方所在地.*仲裁委员会仲裁', text):
        issues.append({
            "clause": "争议解决条款",
            "level": "medium",
            "risk_level": 2,
            "issue": "争议解决固定为甲方所在地仲裁，可能明显增加承租人维权成本。",
            "suggestion": "改为合同签订地、房屋所在地有管辖权的法院，或约定双方协商确定争议解决地。",
            "legal_reference": "《仲裁法》第16条",
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

    normalized_issues = [_normalize_issue(issue) for issue in issues]
    return _attach_issue_context(normalized_issues, contract_text)
