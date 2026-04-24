from __future__ import annotations

import re

RISK_TERMS = (
    "押金",
    "保证金",
    "违约金",
    "违约",
    "解约",
    "解除",
    "提前退租",
    "退租",
    "滞纳金",
    "利息",
    "租金调整",
    "服务费",
    "管理费",
    "转租",
    "二房东",
    "租金贷",
    "贷款",
    "分期",
    "征信",
    "维修",
    "免责",
    "断水断电",
    "仲裁",
    "解释权",
    "中介费",
)

CONTRACT_HINTS = (
    ("租房", "租房合同"),
    ("租赁", "租赁合同"),
    ("公寓", "公寓租赁"),
    ("商业", "商业租赁"),
    ("办公", "商业租赁"),
    ("消费", "消费合同"),
    ("培训", "消费合同"),
)

LEGAL_HINT_MAP = {
    "押金": "民法典 押金返还 格式条款",
    "保证金": "民法典 保证金 返还 条款",
    "违约金": "民法典 违约金 过高 约定",
    "解约": "民法典 租赁合同 解除 条件",
    "解除": "民法典 租赁合同 解除 条件",
    "提前退租": "民法典 提前退租 违约责任",
    "退租": "民法典 提前退租 押金返还",
    "滞纳金": "民法典 滞纳金 违约金 上限",
    "利息": "逾期 利息 上限 民法典",
    "租金调整": "租金调整 单方变更 民法典",
    "服务费": "服务费 强制收费 合同条款",
    "管理费": "管理费 强制收费 合同条款",
    "转租": "民法典 转租 同意 条款",
    "二房东": "二房东 转租 授权 风险",
    "租金贷": "租金贷 风险 征信 分期",
    "贷款": "租房 贷款 条款 风险",
    "分期": "租房 分期 征信 风险",
    "征信": "征信 授权 合同 风险",
    "维修": "民法典 房屋租赁 维修义务",
    "免责": "格式条款 免责 民法典 497",
    "断水断电": "断水断电 自力救济 合同 风险",
    "仲裁": "仲裁 条款 管辖地 消费者",
    "解释权": "最终解释权 格式条款 民法典",
    "中介费": "中介费 收费 条款 风险",
}

QUESTION_PATTERN = re.compile(r"[？?！!。,\s]+")


def _extract_primary_terms(question: str, risk_summary: str) -> list[str]:
    source_text = f"{question} {risk_summary}"
    found = [term for term in RISK_TERMS if term in source_text]
    if found:
        return found[:3]

    compact_question = QUESTION_PATTERN.sub(" ", question).strip()
    fragments = [fragment for fragment in compact_question.split(" ") if len(fragment) >= 2]
    return fragments[:3]


def _detect_contract_hint(question: str, contract_text: str, risk_summary: str) -> str:
    source_text = f"{question} {contract_text[:400]} {risk_summary}"
    for needle, label in CONTRACT_HINTS:
        if needle in source_text:
            return label
    return "合同条款"


def build_chat_search_queries(
    *,
    question: str,
    contract_text: str = "",
    risk_summary: str = "",
    rewrite_count: int = 3,
) -> list[dict[str, object]]:
    normalized_question = question.strip()
    if not normalized_question:
        return []

    primary_terms = _extract_primary_terms(normalized_question, risk_summary)
    contract_hint = _detect_contract_hint(normalized_question, contract_text, risk_summary)

    queries: list[dict[str, object]] = [
        {
            "text": normalized_question,
            "kind": "original",
            "priority": 1.0,
        }
    ]

    if primary_terms:
        clause_query = " ".join(dict.fromkeys([*primary_terms, contract_hint, "条款"]))
        queries.append(
            {
                "text": clause_query,
                "kind": "clause",
                "priority": 0.9,
            }
        )

        legal_fragments = [LEGAL_HINT_MAP.get(term) for term in primary_terms if LEGAL_HINT_MAP.get(term)]
        if legal_fragments:
            queries.append(
                {
                    "text": " ".join(legal_fragments[:2]),
                    "kind": "legal",
                    "priority": 0.86,
                }
            )

        remedy_query = " ".join(dict.fromkeys([*primary_terms, contract_hint, "修改建议", "维权"]))
        queries.append(
            {
                "text": remedy_query,
                "kind": "remedy",
                "priority": 0.76,
            }
        )
    else:
        queries.append(
            {
                "text": f"{normalized_question} {contract_hint} 法律依据",
                "kind": "legal",
                "priority": 0.82,
            }
        )

    deduped: list[dict[str, object]] = []
    seen_texts: set[str] = set()
    for item in queries:
        text = str(item.get("text", "")).strip()
        if not text or text in seen_texts:
            continue
        seen_texts.add(text)
        deduped.append(item)
        if len(deduped) >= max(1, rewrite_count + 1):
            break

    return deduped
