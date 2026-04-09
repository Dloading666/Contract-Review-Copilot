from src.agents.breakpoint import check_breakpoint


def test_check_breakpoint_ignores_no_risk_placeholder_issue():
    result = check_breakpoint(
        [
            {
                "clause": "整体评估",
                "level": "low",
                "risk_level": 1,
                "issue": "未发现明显不公平条款。",
                "suggestion": "签约前仍建议逐条核对押金、违约责任和证据留存要求。",
                "legal_reference": "《民法典》合同编",
            }
        ]
    )

    assert result["issues_count"] == 0
    assert result["critical_count"] == 0
    assert result["high_count"] == 0
    assert result["medium_count"] == 0
    assert result["low_count"] == 0
    assert "未发现明显不公平条款" in result["question"]


def test_check_breakpoint_counts_only_substantive_issues():
    result = check_breakpoint(
        [
            {
                "clause": "整体评估",
                "level": "low",
                "risk_level": 1,
                "issue": "未发现明显不公平条款。",
                "suggestion": "签约前仍建议逐条核对押金、违约责任和证据留存要求。",
                "legal_reference": "《民法典》合同编",
            },
            {
                "clause": "押金条款",
                "level": "high",
                "risk_level": 4,
                "issue": "押金金额偏高。",
                "suggestion": "建议协商降低押金。",
                "legal_reference": "《民法典》第585条",
            },
        ]
    )

    assert result["issues_count"] == 1
    assert result["critical_count"] == 0
    assert result["high_count"] == 1
    assert result["medium_count"] == 0
    assert result["low_count"] == 0
