from pathlib import Path

from src.evals.golden_runner import evaluate_samples, load_samples


def test_golden_eval_harness_passes_current_samples():
    samples_path = Path(__file__).resolve().parents[1] / "evals" / "golden_contracts.json"
    summary = evaluate_samples(load_samples(samples_path))

    assert summary["total"] >= 4
    assert summary["failed"] == 0
    assert summary["passed"] == summary["total"]
