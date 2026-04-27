from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from ..agents.logic_review import rule_review_clauses


LEVEL_RANK = {
    "low": 1,
    "medium": 2,
    "high": 3,
    "critical": 4,
}


def load_samples(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Golden eval samples must be a JSON array")
    return data


def evaluate_sample(sample: dict[str, Any]) -> dict[str, Any]:
    sample_id = str(sample.get("id") or "")
    issues = rule_review_clauses(str(sample.get("contract_text") or ""))
    effective_issues = [
        issue for issue in issues
        if not (
            str(issue.get("clause") or "") == "整体评估"
            and LEVEL_RANK.get(str(issue.get("level")), 0) <= LEVEL_RANK["low"]
        )
    ]
    clause_names = {str(issue.get("clause") or "") for issue in effective_issues}

    failures: list[str] = []
    for clause in sample.get("expected_clauses", []):
        if clause not in clause_names:
            failures.append(f"missing expected clause: {clause}")

    minimum_level = sample.get("minimum_level")
    if minimum_level and effective_issues:
        required_rank = LEVEL_RANK.get(str(minimum_level), 0)
        observed_rank = max(LEVEL_RANK.get(str(issue.get("level")), 0) for issue in effective_issues)
        if observed_rank < required_rank:
            failures.append(f"expected minimum level {minimum_level}, observed {observed_rank}")

    maximum_findings = sample.get("maximum_findings")
    if isinstance(maximum_findings, int) and len(effective_issues) > maximum_findings:
        failures.append(f"expected at most {maximum_findings} findings, observed {len(effective_issues)}")

    return {
        "id": sample_id,
        "name": sample.get("name") or sample_id,
        "passed": not failures,
        "failures": failures,
        "observed_clauses": sorted(clause_names),
        "observed_levels": sorted({str(issue.get("level") or "") for issue in effective_issues}),
        "finding_count": len(effective_issues),
        "raw_finding_count": len(issues),
    }


def evaluate_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    results = [evaluate_sample(sample) for sample in samples]
    passed = sum(1 for result in results if result["passed"])
    return {
        "passed": passed,
        "failed": len(results) - passed,
        "total": len(results),
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run deterministic golden contract review evals.")
    parser.add_argument(
        "--samples",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "evals" / "golden_contracts.json",
        help="Path to golden sample JSON file.",
    )
    parser.add_argument("--output", type=Path, help="Optional path for JSON result output.")
    args = parser.parse_args()

    summary = evaluate_samples(load_samples(args.samples))
    output = json.dumps(summary, ensure_ascii=False, indent=2)
    print(output)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")

    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
