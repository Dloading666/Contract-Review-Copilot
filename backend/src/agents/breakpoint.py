"""
Breakpoint agent.

Determines whether the review should pause for confirmation before the final
report is generated.
"""

from __future__ import annotations

from typing import Any


PLACEHOLDER_CLAUSES = {"整体评估", "风险评估"}


def _is_placeholder_issue(issue: dict[str, Any]) -> bool:
    clause = str(issue.get("clause", "")).strip()
    risk_level = int(issue.get("risk_level", 0) or 0)
    return clause in PLACEHOLDER_CLAUSES and risk_level <= 1


def _build_question(total: int, critical_count: int, high_count: int) -> str:
    if total == 0:
        return (
            "本次审查未发现明显不公平条款，合同整体风险较低。"
            "是否继续生成完整的避坑指南报告？"
        )

    if critical_count > 0:
        return (
            f"已检测到 {total} 处潜在风险条款，其中 {critical_count} 处属于高危/严重级别。"
            "这些条款可能明显加重消费者责任或排除主要权利，建议重点核查。"
            "是否继续生成完整的避坑指南报告？"
        )

    if high_count > 0:
        return (
            f"已检测到 {total} 处潜在风险条款，主要涉及押金、违约责任或解除条件。"
            "建议在签约前优先协商相关条款。"
            "是否继续生成完整的避坑指南报告？"
        )

    return (
        f"已完成合同审查，共发现 {total} 处提示性风险。"
        "合同整体相对公平，但仍建议留意押金返还、违约责任和证据留存。"
        "是否继续生成完整的避坑指南报告？"
    )


def check_breakpoint(issues: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Decide whether to pause for human review.

    Placeholder "no-risk" summary issues should not be counted as actual risks,
    otherwise the UI may show contradictory states such as "no unfair clauses"
    and "1 risk clause" at the same time.
    """

    substantive_issues = [issue for issue in issues if not _is_placeholder_issue(issue)]

    critical_count = sum(1 for issue in substantive_issues if int(issue.get("risk_level", 0) or 0) >= 5)
    high_count = sum(1 for issue in substantive_issues if 3 <= int(issue.get("risk_level", 0) or 0) < 5)
    medium_count = sum(1 for issue in substantive_issues if 2 <= int(issue.get("risk_level", 0) or 0) < 3)
    low_count = sum(1 for issue in substantive_issues if int(issue.get("risk_level", 0) or 0) < 2)
    total = len(substantive_issues)

    return {
        "needs_review": total > 0,
        "question": _build_question(total, critical_count, high_count),
        "issues_count": total,
        "critical_count": critical_count,
        "high_count": high_count,
        "medium_count": medium_count,
        "low_count": low_count,
    }
