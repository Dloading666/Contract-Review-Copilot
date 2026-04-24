from __future__ import annotations

import argparse
from pathlib import Path

from .scanner import scan_project, write_report_files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Run the six-dimension project audit.')
    parser.add_argument(
        '--repo-root',
        type=Path,
        default=Path(__file__).resolve().parents[3],
        help='Repository root to scan.',
    )
    parser.add_argument(
        '--output-dir',
        type=Path,
        default=Path(__file__).resolve().parents[3] / 'docs' / 'audits',
        help='Directory for generated markdown and json reports.',
    )
    parser.add_argument(
        '--base-name',
        default='current-baseline',
        help='Base filename for generated reports.',
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    report = scan_project(args.repo_root)
    json_path, md_path = write_report_files(report, args.output_dir, args.base_name)
    print(f'overall_score={report.overall_score}')
    print(f'release_decision={report.release_decision}')
    print(f'json_report={json_path}')
    print(f'markdown_report={md_path}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
