"""
Logic Review Agent — LLM-powered clause review with rule-based fallback.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime

from .entity_extraction import create_chat_completion, extract_entities
from .routing import decide_routing
from ..search import build_search_context
from ..llm_client import get_primary_model_key

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

REVIEW_PROMPT = """你是一个专业的合同审查律师。请严格依据合同原文逐条审查风险，不要脱离原文臆测。

合同信息：
{contract_info}

已提取的关键变量：
- 月租金：{monthly_rent} 元
- 押金：{deposit} 元
- 押金退还条件：{deposit_conditions}
- 违约金条款：{penalty_clause}
- 滞纳金条款：{late_fee}
- 解约条款：{termination_clause}

法规检索上下文：
{rag_context}

合同原文（重点逐条审查）：
{contract_text}

请审查以下风险点并返回 JSON 数组格式的风险列表：

审查维度：
1. 押金是否超过 2-3 个月租金（违反地方规定）
2. 违约金是否超过实际损失的 30%（民法典第585条）
3. 滞纳金是否超过年化 LPR 四倍（约 14.8%）
4. 押金退还条件是否明确（有无模糊地带）
5. 提前解约违约金是否过高
6. 合同是否存在其他显失公平的条款
7. 是否存在单方调整租金或服务费用的权利
8. 自动续租条款是否对等，是否存在“未通知即视为续租”
9. 维修责任是否被完全转嫁给承租人，尤其是主体结构、管道、家电大修
10. 解约权是否明显不对等，是否存在甲方可随时解约而乙方受限
11. 提前通知期是否明显不对等，是否只约束乙方
12. 是否存在不合理的禁止行为并配套高额违约金或罚款
13. 房屋交付标准、设施状态和损坏责任是否写明，是否存在模糊交付

输出要求：
- 必须优先依据合同原文识别问题，尽量在 issue 中点明具体条款内容
- clause 应写明条款编号、条款名称或可以定位的条款主题
- 没有把握时不要输出

对于每条发现的风险，返回：
- clause: 涉及的合同条款编号/名称
- level: critical/high/medium/low
- risk_level: 1-5 的数字
- issue: 问题描述
- suggestion: 修正建议
- legal_reference: 相关法条

直接返回 JSON 数组，不要其他文字：
[
  {{
    "clause": "第8.2条",
    "level": "critical",
    "risk_level": 5,
    "issue": "合同写明“押金不予退还”，明显加重承租人责任。",
    "suggestion": "改为在扣除实际欠费和合理损耗后退还押金，并明确退还时限。",
    "legal_reference": "《民法典》第497条"
  }}
]
"""

RISK_KEYWORDS = (
    "押金",
    "保证金",
    "违约金",
    "违约",
    "自动续租",
    "自动续约",
    "续租",
    "续约",
    "解约",
    "解除",
    "提前解除",
    "提前退租",
    "退租",
    "逾期",
    "滞纳金",
    "利息",
    "租金调整",
    "调整租金",
    "变更租金",
    "服务费",
    "管理费",
    "转租",
    "二房东",
    "租金贷",
    "贷款",
    "分期",
    "征信",
    "委托扣款",
    "维修",
    "修缮",
    "免责",
    "现状出租",
    "现有状态",
    "断水断电",
    "中介费",
    "水电",
    "返还",
    "通知",
    "原房东",
    "托管协议",
    "仲裁",
    "甲方所在地",
    "随时进入",
    "入户检查",
    "养宠",
    "宠物",
    "禁止转租",
    "口头承诺",
    "解释权",
    "交付",
    "设施清单",
)

CLAUSE_HEADER_PATTERN = re.compile(r"(?m)^(第[一二三四五六七八九十百零\d]+条|[0-9]+\.\s*|（\d+）)")
DATE_PATTERN = re.compile(r"(\d{4})[年/-](\d{1,2})[月/-](\d{1,2})日?")
LPR_4X_ANNUAL_RATE = 0.148

PATTERN_RULES = [
    {
        "clause": "租金调整条款",
        "pattern": re.compile(r"甲方.{0,10}(有权|可以).{0,20}(调整|变更|上调).{0,12}(租金|服务费|管理费)"),
        "level": "high",
        "risk_level": 4,
        "issue": "合同赋予甲方单方调整租金或相关费用的权利，缺少乙方同意机制，属于明显不对等约定。",
        "suggestion": "改为租金和服务费用调整须经双方协商一致并书面确认后生效。",
        "legal_reference": "《民法典》第496条、第497条",
    },
    {
        "clause": "自动续租条款",
        "pattern": re.compile(
            r"(到期前\d+日(?:内)?|期满前\d+日(?:内)?)"
            r".{0,40}(未.*通知|不.*书面)"
            r".{0,30}(视为|自动)(续租|续约)"
        ),
        "level": "medium",
        "risk_level": 3,
        "issue": "合同存在“未通知即自动续租/续约”的安排，若只约束承租人，容易形成续租陷阱。",
        "suggestion": "改为双方在到期前明确书面确认是否续租，不能以沉默视为同意。",
        "legal_reference": "《民法典》第730条",
    },
    {
        "clause": "维修责任条款",
        "pattern": re.compile(r"(房屋|设施|主体结构|管道|家电).{0,20}(维修|修缮).{0,20}(由乙方|承租方).{0,10}(承担|负责)"),
        "level": "medium",
        "risk_level": 3,
        "issue": "合同将房屋或主要设施维修责任转由乙方承担，可能免除了出租人的法定维修义务。",
        "suggestion": "明确主体结构、管道、家电大修等由出租方负责，乙方仅承担日常合理使用中的小额维护。",
        "legal_reference": "《民法典》第733条",
    },
    {
        "clause": "解约权条款",
        "pattern": re.compile(r"甲方.{0,10}(有权|可以).{0,10}(随时|任意|单方).{0,10}(解除合同|解约|收回房屋)"),
        "level": "high",
        "risk_level": 4,
        "issue": "合同赋予甲方随时单方解除或收回房屋的权利，解约权明显偏向一方。",
        "suggestion": "将解约条件限定为明确违约情形，并补充乙方对应的法定或约定解约权。",
        "legal_reference": "《民法典》第563条、第497条",
    },
    {
        "clause": "禁止转租违约条款",
        "pattern": re.compile(r"禁止.*转租.{0,100}(违约金|罚款|不予退还)"),
        "level": "medium",
        "risk_level": 3,
        "issue": "合同将禁止转租与高额违约责任绑定，可能超过合理损失范围。",
        "suggestion": "保留转租需经同意的要求，但违约责任应以实际损失为基础，不宜直接设置高额罚款。",
        "legal_reference": "《民法典》第716条、第585条",
    },
    {
        "clause": "禁止养宠违约条款",
        "pattern": re.compile(r"(禁止|不得).{0,15}(养宠|饲养宠物).{0,80}(违约金|罚款|押金不退)"),
        "level": "medium",
        "risk_level": 3,
        "issue": "合同对特定禁止行为直接配套较高违约金或押金不退，可能构成过度惩罚。",
        "suggestion": "如确需限制养宠，应明确管理要求和实际损害赔偿标准，避免直接设置高额罚款。",
        "legal_reference": "《民法典》第585条、第497条",
    },
    {
        "clause": "入户检查条款",
        "pattern": re.compile(r"甲方.{0,10}(有权|可以).{0,10}(随时|任意).{0,12}(进入|检查|查看|入户)"),
        "level": "medium",
        "risk_level": 3,
        "issue": "合同允许甲方随时入户检查，可能侵犯承租人的安宁居住与隐私权益。",
        "suggestion": "改为甲方需基于合理事由并提前通知后方可入户，紧急情况除外。",
        "legal_reference": "《民法典》第509条",
    },
    {
        "clause": "租金贷条款",
        "pattern": re.compile(r"(金融机构|贷款|分期|征信|委托扣款|租金贷|消费贷)"),
        "level": "high",
        "risk_level": 4,
        "issue": "合同中出现贷款、分期、征信或委托扣款安排，存在“租金贷”或隐性消费信贷风险。",
        "suggestion": "要求明确租金支付方式，不接受未经充分说明的贷款、分期或征信授权条款。",
        "legal_reference": "《民法典》第496条",
    },
    {
        "clause": "现状交付条款",
        "pattern": re.compile(r"(现状|现有状态).{0,20}(出租|交付).{0,40}(不.*维修|不.*负责)"),
        "level": "medium",
        "risk_level": 3,
        "issue": "合同以“现状出租/交付”为由排除甲方维修责任，可能导致后续维权困难。",
        "suggestion": "签约前补充房屋现状和设施清单，并明确交付后非乙方原因造成的问题由甲方负责维修。",
        "legal_reference": "《民法典》第733条",
    },
    {
        "clause": "提前退租赔偿条款",
        "pattern": re.compile(r"提前退租.{0,60}(全部|全额|剩余).{0,20}租金"),
        "level": "critical",
        "risk_level": 5,
        "issue": "合同要求提前退租时支付全部或剩余租期租金，明显超出合理损失范围。",
        "suggestion": "改为按照实际空置损失或不超过一个月租金的合理违约责任处理。",
        "legal_reference": "《民法典》第585条",
    },
    {
        "clause": "口头承诺条款",
        "pattern": re.compile(r"口头.*承诺.*无效|以本合同.*为准.*口头"),
        "level": "low",
        "risk_level": 2,
        "issue": "合同通过“口头承诺无效”兜底，可能掩盖签约前的重要口头说明或营销承诺。",
        "suggestion": "将关键口头承诺补充写入书面合同或附件，避免后续举证困难。",
        "legal_reference": "《民法典》第496条",
    },
    {
        "clause": "押金退还条款",
        "pattern": re.compile(r"押金不予退还|押金不退"),
        "level": "high",
        "risk_level": 4,
        "issue": "合同写明押金不予退还，属于明显加重承租人责任的格式条款。",
        "suggestion": "改为押金在扣除实际欠费和合理损失后退还，并明确退还时限与依据。",
        "legal_reference": "《民法典》第497条",
    },
    {
        "clause": "断水断电免责条款",
        "pattern": re.compile(r"断水断电.*不构成违约|可断水断电"),
        "level": "critical",
        "risk_level": 5,
        "issue": "合同允许甲方通过断水断电处理争议，并宣称不构成违约，涉嫌以自力救济限制乙方基本居住使用权。",
        "suggestion": "删除断水断电免责条款，改为通过催告、协商、仲裁或诉讼方式解决争议。",
        "legal_reference": "《民法典》第509条",
    },
    {
        "clause": "出租权限与房东身份条款",
        "pattern": re.compile(r"无需联系原房东|托管协议|原房东不再另行确认"),
        "level": "critical",
        "risk_level": 5,
        "issue": "合同中出现“无需联系原房东”或托管协议等表述，存在无权出租、二房东或授权不明风险。",
        "suggestion": "签约前核验房东身份、产权证明、授权委托书和托管协议原件，并确认原房东知情同意。",
        "legal_reference": "《民法典》第716条、第717条",
    },
    {
        "clause": "争议解决条款",
        "pattern": re.compile(r"甲方所在地.*仲裁委员会|提交甲方所在地"),
        "level": "medium",
        "risk_level": 2,
        "issue": "合同将争议解决地固定在甲方所在地，可能显著增加乙方维权成本。",
        "suggestion": "改为房屋所在地、合同履行地或双方另行协商确定的争议解决地。",
        "legal_reference": "《消费者权益保护法》第26条",
    },
    {
        "clause": "自动退租条款",
        "pattern": re.compile(r"逾期.{0,20}(视为|自动).{0,10}(退租|解除合同|收回房屋)"),
        "level": "high",
        "risk_level": 4,
        "issue": "合同约定逾期即自动退租或自动解除，容易导致乙方在未充分催告的情况下失去居住权。",
        "suggestion": "改为先书面催告并给予合理补救期限，再依据违约情形处理。",
        "legal_reference": "《民法典》第563条、第721条",
    },
    {
        "clause": "最终解释权条款",
        "pattern": re.compile(r"(最终解释权|解释权).{0,10}归甲方"),
        "level": "medium",
        "risk_level": 2,
        "issue": "合同将最终解释权单方归属于甲方，属于常见不公平格式条款。",
        "suggestion": "删除单方解释权条款，争议解释应以合同文义、补充协议和法律规定为准。",
        "legal_reference": "《民法典》第496条、第497条",
    },
    {
        "clause": "强制搭售条款",
        "pattern": re.compile(r"(必须|应当).{0,20}(接受|购买|使用).{0,30}(物业服务|保洁服务|网络服务|增值服务)"),
        "level": "medium",
        "risk_level": 3,
        "issue": "合同将租赁与其他服务捆绑，存在强制搭售风险。",
        "suggestion": "将附加服务改为可选项，并单独列明收费标准与是否同意。",
        "legal_reference": "《消费者权益保护法》第26条",
    },
]


def generate_clause_fix(clause: str, issue: str, suggestion: str, legal_ref: str) -> str:
    """Use LLM to generate a suggested clause revision."""
    try:
        response = create_chat_completion(
            model=get_primary_model_key(),
            messages=[
                {"role": "system", "content": "你是一个专业的合同修订专家，擅长将不公平条款修改为合法合理的表述。"},
                {
                    "role": "user",
                    "content": AUTOFIX_PROMPT.format(
                        clause=clause,
                        issue=issue,
                        suggestion=suggestion,
                        legal_ref=legal_ref,
                    ),
                },
            ],
            temperature=0.3,
            max_tokens=512,
            timeout=15.0,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        print(f"[AutoFix] LLM call failed: {exc}")
        return f"建议将「{clause}」条款修改为：{suggestion}（依据：{legal_ref}）"


def _normalize_issue(issue: dict) -> dict:
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


def _normalize_text(text: str) -> str:
    return re.sub(r"[\s\u3000，。、《》“”\"'：:；;（）()【】\[\]、\-]", "", text or "")


def _build_issue_keywords(issue: dict) -> list[str]:
    source_text = " ".join(
        [issue.get("clause", ""), issue.get("issue", ""), issue.get("suggestion", ""), issue.get("matched_text", "")]
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
    return [{**issue, "matched_text": _find_issue_excerpt(contract_text, issue)} for issue in issues]


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
            issue
            for issue in merged
            if not (issue.get("risk_level", 0) <= 1 and issue.get("clause") == "整体评估")
        ]

    return merged


def _split_contract_clauses(text: str) -> list[str]:
    matches = list(CLAUSE_HEADER_PATTERN.finditer(text))
    if not matches:
        return [block.strip() for block in re.split(r"\n\s*\n+", text) if block.strip()]

    clauses: list[str] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        chunk = text[start:end].strip()
        if chunk:
            clauses.append(chunk)
    return clauses


def _extract_suspicious_clauses(text: str) -> str:
    """提取含风险关键词的条款段落，用于长合同精简审查。"""
    clauses = _split_contract_clauses(text)
    suspicious = [
        clause.strip()
        for clause in clauses
        if len(clause.strip()) >= 8 and any(keyword in clause for keyword in RISK_KEYWORDS)
    ]
    if suspicious:
        return "\n\n".join(suspicious)
    return text[:4000]


def _parse_num(raw_value: str) -> float:
    sanitized = (raw_value or "").replace(",", "").replace("，", "").strip()
    if not sanitized:
        return 0
    amount = float(re.sub(r"[^\d.]", "", sanitized))
    if "万" in sanitized:
        return amount * 10000
    return amount


def _estimate_lease_months(text: str) -> int:
    year_match = re.search(r"(\d+)\s*年", text)
    month_match = re.search(r"(\d+)\s*个?月", text)

    if year_match:
        months = int(year_match.group(1)) * 12
        if month_match:
            months += int(month_match.group(1))
        return months

    if month_match:
        return int(month_match.group(1))

    dates = [
        datetime(int(year), int(month), int(day))
        for year, month, day in DATE_PATTERN.findall(text)[:2]
    ]
    if len(dates) == 2:
        delta_days = max((dates[1] - dates[0]).days, 0)
        return max(int(round(delta_days / 30.0)), 0)
    return 0


def _extract_daily_late_fee_rate(text: str) -> float | None:
    decimal_match = re.search(r"逾期.{0,40}(?:每日|每天|按日).{0,20}([0-9]+(?:\.[0-9]+)?)\s*%", text)
    if decimal_match:
        return float(decimal_match.group(1)) / 100

    permille_match = re.search(r"逾期.{0,40}(千分之([0-9]+(?:\.[0-9]+)?))", text)
    if permille_match:
        return float(permille_match.group(2)) / 1000

    permyriad_match = re.search(r"逾期.{0,40}(万分之([0-9]+(?:\.[0-9]+)?))", text)
    if permyriad_match:
        return float(permyriad_match.group(2)) / 10000

    return None


def _build_issue(
    clause: str,
    level: str,
    risk_level: int,
    issue: str,
    suggestion: str,
    legal_reference: str,
) -> dict:
    return {
        "clause": clause,
        "level": level,
        "risk_level": risk_level,
        "issue": issue,
        "suggestion": suggestion,
        "legal_reference": legal_reference,
    }


def review_clauses(
    contract_text: str,
    routing: dict | None = None,
    entities: dict | None = None,
    model_key: str | None = None,
) -> list[dict]:
    """Use LLM to analyze contract clauses for risks."""
    if os.getenv("SKIP_LLM_REVIEW", "").lower() in ("1", "true", "yes"):
        print("[LogicReview] SKIP_LLM_REVIEW is set, using rule-based fallback")
        return _rule_based_review(contract_text)

    try:
        if entities is None:
            entities = extract_entities(contract_text, model_key=model_key)

        if routing is None:
            routing = decide_routing(contract_text, entities, model_key=model_key)

        rent = entities.get("rent", {}).get("monthly", 0)
        deposit = entities.get("deposit", {}).get("amount", 0)
        review_text = _extract_suspicious_clauses(contract_text) if len(contract_text) > 4000 else contract_text
        search_context = build_search_context(routing, entities)
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
            late_fee=entities.get("late_fee") or "未约定",
            termination_clause=entities.get("termination_clause") or "未约定",
            rag_context=search_context or "未检索到额外法规上下文，请基于合同文本和通用法律原则审查。",
            contract_text=review_text[:5000],
        )

        response = create_chat_completion(
            model=model_key or get_primary_model_key(),
            messages=[
                {"role": "system", "content": "你是一个专业的合同审查律师，擅长发现合同中的不公平条款和法律风险。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=2048,
            timeout=15.0,
        )

        result_text = response.choices[0].message.content.strip()
        if "```json" in result_text:
            result_text = result_text.split("```json", 1)[1].split("```", 1)[0]
        elif "```" in result_text:
            result_text = result_text.split("```", 1)[1].split("```", 1)[0]

        issues = json.loads(result_text.strip())
        if isinstance(issues, dict):
            issues = [issues]
        issues = [_normalize_issue(issue) for issue in issues]
        issues = _attach_issue_context(issues, contract_text)
        issues = _merge_issue_lists(issues, _rule_based_review(contract_text))

        if not issues:
            issues.append(
                {
                    "clause": "整体评估",
                    "level": "low",
                    "risk_level": 1,
                    "issue": "未发现明显不公平条款，合同条款基本公平合理。",
                    "suggestion": "建议仔细阅读各项条款，确保自身权益。",
                    "legal_reference": "《民法典》合同编通则",
                }
            )

        return issues
    except Exception as exc:
        print(f"[LogicReview] LLM call failed: {exc}, using rule-based fallback")
        return _rule_based_review(contract_text)


def _rule_based_review(contract_text: str) -> list[dict]:
    """Fallback rule-based review when LLM is unavailable."""
    text = contract_text
    issues: list[dict] = []

    rent_match = re.search(r"(?:月租金|租金)(?:[：:]\s*|为\s*)?(?:人民币)?\s*(?:¥|￥)?\s*([0-9,，.]+)\s*(?:元|万)", text)
    deposit_match = re.search(r"(?:押金|保证金)(?:[：:]\s*|为\s*)?(?:人民币)?\s*(?:¥|￥)?\s*([0-9,，.]+)(?:（[^）]+）)?\s*(?:元|万)", text)
    rent = _parse_num(rent_match.group(1)) if rent_match else 0
    deposit = _parse_num(deposit_match.group(1)) if deposit_match else 0
    lease_months = _estimate_lease_months(text)

    if deposit > 3 * rent and rent > 0:
        issues.append(
            _build_issue(
                "押金条款",
                "critical",
                5,
                f"押金（{deposit:.0f}元）超过 3 个月租金，明显偏高，可能违反地方租赁管理规定。",
                "要求将押金下调至不超过 2 个月租金，并明确退还时限。",
                "地方住房租赁条例、 《民法典》第721条",
            )
        )
    elif deposit > 2 * rent and rent > 0:
        issues.append(
            _build_issue(
                "押金条款",
                "high",
                4,
                f"押金（{deposit:.0f}元）超过 2 个月租金，存在偏高风险。",
                "结合当地住房租赁规则核对押金上限，并补充退还条件与时限。",
                "地方住房租赁条例、 《民法典》第721条",
            )
        )

    if re.search(r"200%|两倍|双倍", text):
        issues.append(
            _build_issue(
                "违约责任条款",
                "critical",
                5,
                "合同出现 200%、双倍等明显过高违约金表达，远超合理损失赔偿范围。",
                "删除惩罚性倍率条款，改为以实际损失为基础或控制在合理比例内。",
                "《民法典》第585条",
            )
        )

    if re.search(r"提前退租.{0,40}(两个月|2个月|二个月).{0,10}租金.{0,10}违约金", text):
        issues.append(
            _build_issue(
                "提前退租违约金条款",
                "high",
                4,
                "合同要求提前退租支付两个月租金作为违约金，标准明显偏高。",
                "改为按实际损失或不超过一个月租金承担合理违约责任。",
                "《民法典》第585条",
            )
        )

    daily_rate = _extract_daily_late_fee_rate(text)
    if daily_rate is not None:
        annual_rate = daily_rate * 365
        level = "critical" if annual_rate > 0.36 else "high"
        risk_level = 5 if level == "critical" else 4
        issues.append(
            _build_issue(
                "逾期滞纳金条款",
                level,
                risk_level,
                f"合同约定的日滞纳金折算年化约为 {annual_rate * 100:.1f}%，高于 LPR 四倍的参考上限。",
                "将滞纳金调整为不高于 LPR 四倍的合理水平，或改按实际损失赔偿。",
                "《民法典》第585条、最高法关于民间借贷利率保护规则",
            )
        )

    if re.search(r"万分之(\d+(?:\.\d+)?)", text):
        permyriad_value = float(re.search(r"万分之(\d+(?:\.\d+)?)", text).group(1))
        annual_rate = permyriad_value / 10000 * 365
        if annual_rate > LPR_4X_ANNUAL_RATE:
            level = "critical" if annual_rate > 0.36 else "high"
            issues.append(
                _build_issue(
                    "滞纳金条款",
                    level,
                    5 if level == "critical" else 4,
                    f"合同使用“万分之{permyriad_value:g}”计算滞纳金，折算年化约为 {annual_rate * 100:.1f}%，明显偏高。",
                    "将滞纳金改为与 LPR 四倍相协调的合理比例。",
                    "《民法典》第585条",
                )
            )

    if re.search(r"乙方.{0,15}提前\d+(?:日|天|个月|月).{0,20}(通知|书面通知)", text) and not re.search(
        r"甲方.{0,15}提前\d+(?:日|天|个月|月).{0,20}(通知|书面通知)", text
    ):
        issues.append(
            _build_issue(
                "提前通知条款",
                "medium",
                3,
                "合同仅要求乙方提前通知解约或退租，但未对甲方设置对应通知义务，通知期明显不对等。",
                "补充甲方提前解约或收回房屋时的对应通知义务与违约责任。",
                "《民法典》第497条",
            )
        )

    if re.search(r"押金.{0,20}不计利息|押金.{0,20}无息", text) and deposit > 0 and lease_months > 12:
        issues.append(
            _build_issue(
                "押金利息条款",
                "low",
                2,
                "合同明确押金无息，且租期超过一年，长期占用押金对承租人不利。",
                "优先协商缩短押金占用周期、降低金额，或在条款中明确退还时限和扣减依据。",
                "《民法典》第509条",
            )
        )

    for rule in PATTERN_RULES:
        if rule["pattern"].search(text):
            issues.append(
                _build_issue(
                    rule["clause"],
                    rule["level"],
                    rule["risk_level"],
                    rule["issue"],
                    rule["suggestion"],
                    rule["legal_reference"],
                )
            )

    if not issues:
        issues.append(
            _build_issue(
                "整体评估",
                "low",
                1,
                "未发现明显不公平条款。",
                "签约前仍建议逐条核对押金、维修、解约、违约责任和证据留存要求。",
                "《民法典》合同编",
            )
        )

    normalized_issues = [_normalize_issue(issue) for issue in issues]
    return _attach_issue_context(normalized_issues, contract_text)
