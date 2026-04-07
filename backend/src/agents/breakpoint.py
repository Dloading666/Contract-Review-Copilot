"""
Breakpoint Agent — Mock Implementation
Determines if human confirmation is needed before generating final report.
"""


def check_breakpoint(issues: list[dict]) -> dict:
    """
    Decide whether to pause for human review.
    Returns breakpoint decision.
    """
    critical_count = sum(1 for i in issues if i.get("risk_level", 0) >= 5)
    high_count = sum(1 for i in issues if 3 <= i.get("risk_level", 0) < 5)
    medium_count = sum(1 for i in issues if 2 <= i.get("risk_level", 0) < 3)
    low_count = sum(1 for i in issues if i.get("risk_level", 0) < 2)

    total = len(issues)

    if critical_count > 0:
        question = (
            f"已检测到 {total} 条潜在风险条款，其中 {critical_count} 条为高危/严重级别。 "
            "这些条款可能违反《民法典》相关规定，存在显著法律风险。\n"
            "是否继续生成完整的避坑指南报告？"
        )
    elif high_count > 0:
        question = (
            f"已检测到 {total} 条潜在风险条款，主要涉及违约金和押金退还条件。 "
            "建议在签约前与对方协商修改相关条款。\n"
            "是否继续生成完整的避坑指南报告？"
        )
    else:
        question = (
            f"已完成合同审查，共发现 {total} 条提示性风险。 "
            "合同整体条款相对公平，建议留意押金退还和违约金计算方式。\n"
            "是否生成完整的避坑指南报告？"
        )

    return {
        "needs_review": True,
        "question": question,
        "issues_count": total,
        "critical_count": critical_count,
        "high_count": high_count,
        "medium_count": medium_count,
        "low_count": low_count,
    }
