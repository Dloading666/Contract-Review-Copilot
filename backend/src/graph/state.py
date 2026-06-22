from __future__ import annotations

import hashlib
import operator
from typing import Annotated, NotRequired, TypedDict

from pydantic import BaseModel, Field, model_validator


class FindingCandidate(BaseModel):
    finding_id: str = ""
    agent_id: str
    dimension: str
    clause: str
    matched_text: str = ""
    issue: str
    severity: str = "medium"
    risk_level: int = 3
    confidence: float = 0.5
    legal_references: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    suggestion: str = ""

    @model_validator(mode="after")
    def _compute_finding_id(self) -> FindingCandidate:
        if not self.finding_id:
            self.finding_id = compute_finding_id(
                self.agent_id, self.dimension, self.clause, self.issue
            )
        return self


def compute_finding_id(
    agent_id: str, dimension: str, clause: str, issue: str
) -> str:
    normalized = f"{agent_id}|{dimension}|{clause.strip().lower()}|{issue.strip().lower()}"
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


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

    candidate_findings: Annotated[list[dict], operator.add]
    verified_findings: Annotated[list[dict], operator.add]
    rejected_findings: Annotated[list[dict], operator.add]

    finding_changes: NotRequired[list[dict]]
    report_paragraphs: NotRequired[list[str]]

    current_stage: NotRequired[str]
    degraded_agents: NotRequired[list[str]]
    errors: NotRequired[list[str]]
    completed: NotRequired[bool]
