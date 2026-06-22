import pytest
from src.graph.langgraph_builder import decide_collaboration_mode, _validate_mode


def test_validate_mode_accepts_valid():
    assert _validate_mode("single") == "single"
    assert _validate_mode("auto") == "auto"
    assert _validate_mode("multi") == "multi"


def test_validate_mode_rejects_invalid():
    with pytest.raises(ValueError, match="Invalid"):
        _validate_mode("parallel")


def test_mode_single_override():
    mode = decide_collaboration_mode(
        rule_issues=[{"level": "high", "risk_level": 4}],
        contract_text="x" * 10000,
        entities={},
        routing={"confidence": 0.5},
        mode_override="single",
    )
    assert mode == "single"


def test_mode_multi_override():
    mode = decide_collaboration_mode(
        rule_issues=[],
        contract_text="short",
        entities={},
        routing={"confidence": 0.99},
        mode_override="multi",
    )
    assert mode == "multi"


def test_auto_by_length():
    mode = decide_collaboration_mode(
        rule_issues=[],
        contract_text="x" * 6000,
        entities={},
        routing={"confidence": 0.99},
        mode_override="auto",
    )
    assert mode == "multi"


def test_auto_by_length_boundary():
    """Exactly at threshold should trigger multi (>=)."""
    mode = decide_collaboration_mode(
        rule_issues=[],
        contract_text="x" * 6000,
        entities={},
        routing={"confidence": 0.99},
        mode_override="auto",
    )
    assert mode == "multi"


def test_auto_below_threshold():
    mode = decide_collaboration_mode(
        rule_issues=[{"level": "low", "risk_level": 1}],
        contract_text="x" * 5999,
        entities={},
        routing={"confidence": 0.99},
        mode_override="auto",
    )
    assert mode == "single"


def test_auto_by_risk_level():
    mode = decide_collaboration_mode(
        rule_issues=[{"level": "medium", "risk_level": 3}],
        contract_text="short",
        entities={},
        routing={"confidence": 0.99},
        mode_override="auto",
    )
    assert mode == "multi"


def test_auto_by_low_confidence():
    mode = decide_collaboration_mode(
        rule_issues=[],
        contract_text="short",
        entities={},
        routing={"confidence": 0.5},
        mode_override="auto",
    )
    assert mode == "multi"


def test_auto_confidence_boundary():
    """At exactly threshold should stay single (< not <=)."""
    mode = decide_collaboration_mode(
        rule_issues=[],
        contract_text="short",
        entities={},
        routing={"confidence": 0.75},
        mode_override="auto",
    )
    assert mode == "single"


def test_auto_by_unknown_contract_type():
    mode = decide_collaboration_mode(
        rule_issues=[],
        contract_text="short",
        entities={"contract_type": "劳动合同"},
        routing={"confidence": 0.99},
        mode_override="auto",
    )
    assert mode == "multi"


def test_auto_standard_rental():
    mode = decide_collaboration_mode(
        rule_issues=[{"level": "low", "risk_level": 1}],
        contract_text="short",
        entities={"contract_type": "租赁合同"},
        routing={"confidence": 0.99},
        mode_override="auto",
    )
    assert mode == "single"
