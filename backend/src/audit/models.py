from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


DIMENSIONS = (
    'concurrency_performance',
    'async_decoupling',
    'content_safety',
    'storage_architecture',
    'large_file_handling',
    'anti_bot_registration',
)

DIMENSION_LABELS = {
    'concurrency_performance': '????',
    'async_decoupling': '????',
    'content_safety': '????',
    'storage_architecture': '????',
    'large_file_handling': '?????',
    'anti_bot_registration': '?????',
}

DIMENSION_WEIGHTS = {
    'concurrency_performance': 20,
    'async_decoupling': 20,
    'content_safety': 20,
    'storage_architecture': 15,
    'large_file_handling': 15,
    'anti_bot_registration': 10,
}

SEVERITY_WEIGHTS = {
    'P0': 25,
    'P1': 15,
    'P2': 8,
    'P3': 3,
}


@dataclass(slots=True)
class AuditFinding:
    id: str
    dimension: str
    severity: str
    title: str
    evidence: list[str]
    impact: str
    recommendation: str
    acceptance_criteria: str
    owner_hint: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AuditDimensionScore:
    key: str
    label: str
    score: int
    weight: int
    finding_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AuditReport:
    project_name: str
    generated_at: str
    overall_score: int
    release_decision: str
    summary: list[str]
    metrics: dict[str, Any]
    strengths: list[str] = field(default_factory=list)
    dimension_scores: list[AuditDimensionScore] = field(default_factory=list)
    findings: list[AuditFinding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            'projectName': self.project_name,
            'generatedAt': self.generated_at,
            'overallScore': self.overall_score,
            'releaseDecision': self.release_decision,
            'summary': self.summary,
            'metrics': self.metrics,
            'strengths': self.strengths,
            'dimensionScores': [item.to_dict() for item in self.dimension_scores],
            'findings': [item.to_dict() for item in self.findings],
        }
