import pytest
from src.graph.state import (
    ReviewState, FindingCandidate, compute_finding_id, validate_finding,
    VALID_SEVERITIES, _normalize_for_hash,
)


def test_finding_id_stable_across_agents():
    fid1 = compute_finding_id("deposit", "押金条款", "押金不予退还", "押金偏高")
    fid2 = compute_finding_id("deposit", "押金条款", "押金不予退还", "押金偏高")
    assert fid1 == fid2


def test_finding_id_excludes_agent_id():
    fid_financial = compute_finding_id("deposit", "押金", "test", "test")
    fid_rights = compute_finding_id("deposit", "押金", "test", "test")
    assert fid_financial == fid_rights


def test_finding_id_differs_on_different_content():
    fid1 = compute_finding_id("deposit", "押金", "text1", "issue1")
    fid2 = compute_finding_id("penalty", "违约金", "text2", "issue2")
    assert fid1 != fid2


def test_finding_candidate_auto_generates_id():
    fc = FindingCandidate(
        agent_id="financial_performance", dimension="deposit",
        clause="押金条款", matched_text="test", issue="偏高",
    )
    assert fc.finding_id
    assert len(fc.finding_id) == 16


def test_finding_candidate_validates_risk_level():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        FindingCandidate(
            agent_id="test", dimension="test", clause="test",
            issue="test", risk_level=6,
        )


def test_finding_candidate_validates_confidence():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        FindingCandidate(
            agent_id="test", dimension="test", clause="test",
            issue="test", confidence=1.5,
        )


def test_validate_finding_valid():
    assert validate_finding({
        "clause": "test", "issue": "test", "severity": "high",
        "risk_level": 4, "confidence": 0.8,
    })


def test_validate_finding_empty_clause():
    assert not validate_finding({
        "clause": "", "issue": "test", "severity": "high",
        "risk_level": 4, "confidence": 0.8,
    })


def test_validate_finding_invalid_severity():
    assert not validate_finding({
        "clause": "test", "issue": "test", "severity": "extreme",
        "risk_level": 4, "confidence": 0.8,
    })


def test_validate_finding_risk_level_out_of_range():
    assert not validate_finding({
        "clause": "test", "issue": "test", "severity": "high",
        "risk_level": 0, "confidence": 0.8,
    })
    assert not validate_finding({
        "clause": "test", "issue": "test", "severity": "high",
        "risk_level": 6, "confidence": 0.8,
    })


def test_validate_finding_confidence_out_of_range():
    assert not validate_finding({
        "clause": "test", "issue": "test", "severity": "high",
        "risk_level": 4, "confidence": -0.1,
    })


def test_normalize_for_hash():
    assert _normalize_for_hash("  押 金 条 款  ") == "押金条款"
    assert _normalize_for_hash("押金：20,000元") == "押金：20000元"


def test_review_state_has_required_fields():
    import typing
    hints = typing.get_type_hints(ReviewState, include_extras=True)
    assert "candidate_findings" in hints
    assert "verified_findings" in hints
    assert "final_findings" in hints
    assert "overall_risk" in hints
    assert "persisted" in hints
    assert "used_rule_fallback" in hints
