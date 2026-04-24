from pathlib import Path

from src.audit.scanner import render_markdown, scan_project


def test_scan_project_returns_six_dimension_report():
    repo_root = Path(__file__).resolve().parents[2]
    report = scan_project(repo_root)

    assert report.project_name == 'Contract-Review-Copilot'
    assert len(report.dimension_scores) == 6
    assert report.findings
    assert report.overall_score >= 0
    assert report.release_decision in {'block', 'warning', 'pass'}
    assert all(dimension.score >= 0 for dimension in report.dimension_scores)
    assert not any(finding.dimension == 'anti_bot_registration' for finding in report.findings)


def test_render_markdown_includes_summary_sections():
    repo_root = Path(__file__).resolve().parents[2]
    report = scan_project(repo_root)
    markdown = render_markdown(report)

    assert markdown.startswith('# Contract-Review-Copilot')
    assert markdown.count('## ') >= 3
    assert 'P1' in markdown or 'P2' in markdown or 'P3' in markdown
