from __future__ import annotations

import hashlib
import re
import operator
from typing import Annotated, NotRequired, TypedDict

from pydantic import BaseModel, Field, model_validator


VALID_SEVERITIES = ("critical", "high", "medium", "low")


def _normalize_for_hash(text: str) -> str:
    return re.sub(r"[\s\u3000,.\u3001\u3002\u201c\u201d\"':;()\-]", "", text or "").strip().lower()


def compute_finding_id(
    dimension: str, clause: str, matched_text: str, issue: str
) -> str:
    normalized = f"{_normalize_for_hash(dimension)}|{_normalize_for_hash(clause)}|{_normalize_for_hash(matched_text)}|{_normalize_for_hash(issue)}"
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def validate_finding(finding: dict) -> bool:
    if not finding.get("clause") or not finding.get("issue"):
        return False
    severity = finding.get("severity", "medium")
    if severity not in VALID_SEVERITIES:
        return False
    risk_level = finding.get("risk_level", 3)
    if not (1 <= risk_level <= 5):
        return False
    confidence = finding.get("confidence", 0.5)
    if not (0.0 <= confidence <= 1.0):
        return False
    return True


class FindingCandidate(BaseModel):
    finding_id: str = ""
    agent_id: str
    dimension: str
    clause: str
    matched_text: str = ""
    issue: str
    severity: str = "medium"
    risk_level: int = Field(default=3, ge=1, le=5)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    legal_references: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    suggestion: str = ""

    @model_validator(mode="after")
    def _compute_finding_id(self) -> FindingCandidate:
        if not self.finding_id:
            self.finding_id = compute_finding_id(
                self.dimension, self.clause, self.matched_text, self.issue
            )
        return self


class ReviewState(TypedDict, total=False):
    session_id: str
    user_id: NotRequired[str | None]
    filename: NotRequired[str]
    contract_text: str
    model_key: NotRequired[str | None]

    entities: NotRequired[dict]
    routing: NotRequired[dict]
    evidence: NotRequired[list[dict]]

    rule_issues: NotRequired[list[dict]]
    collaboration_mode: NotRequired[str]
    specialist_tasks: NotRequired[list[str]]
    used_rule_fallback: NotRequired[bool]

    candidate_findings: Annotated[list[dict], operator.add]
    verified_findings: NotRequired[list[dict]]
    rejected_findings: NotRequired[list[dict]]
    final_findings: NotRequired[list[dict]]
    overall_risk: NotRequired[str]
    supervisor_summary: NotRequired[str]

    finding_changes: NotRequired[list[dict]]
    report_paragraphs: NotRequired[list[str]]

    current_stage: NotRequired[str]
    degraded_agents: Annotated[list[str], operator.add]
    errors: Annotated[list[str], operator.add]
    completed: NotRequired[bool]
    persisted: NotRequired[bool]
