from src.agents.breakpoint import check_breakpoint


def test_check_breakpoint_skips_pause_for_no_risk_placeholder_issue():
    result = check_breakpoint(
        [
            {
                "clause": "整体评估",
                "level": "low",
                "risk_level": 1,
                "issue": "未发现明显不公平条款",
                "suggestion": "Keep checking the contract before signing.",
                "legal_reference": "Civil Code Contract Book",
            }
        ]
    )

    assert result["needs_review"] is False
    assert result["issues_count"] == 0
    assert result["critical_count"] == 0
    assert result["high_count"] == 0
    assert result["medium_count"] == 0
    assert result["low_count"] == 0


def test_check_breakpoint_counts_only_substantive_issues():
    result = check_breakpoint(
        [
            {
                "clause": "整体评估",
                "level": "low",
                "risk_level": 1,
                "issue": "未发现明显不公平条款",
                "suggestion": "Keep checking the contract before signing.",
                "legal_reference": "Civil Code Contract Book",
            },
            {
                "clause": "Deposit clause",
                "level": "high",
                "risk_level": 4,
                "issue": "The deposit amount is too high.",
                "suggestion": "Renegotiate the deposit amount.",
                "legal_reference": "Civil Code Art. 585",
            },
        ]
    )

    assert result["needs_review"] is True
    assert result["issues_count"] == 1
    assert result["critical_count"] == 0
    assert result["high_count"] == 1
    assert result["medium_count"] == 0
    assert result["low_count"] == 0
