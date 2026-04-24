from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    DIMENSIONS,
    DIMENSION_LABELS,
    DIMENSION_WEIGHTS,
    SEVERITY_WEIGHTS,
    AuditDimensionScore,
    AuditFinding,
    AuditReport,
)


SEVERITY_ORDER = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3}
ALLOWED_SIGNAL_SUFFIXES = {'.py', '.ts', '.tsx', '.js', '.jsx', '.json', '.toml', '.yaml', '.yml', '.cfg', '.conf'}
ANTI_BOT_MARKERS = ('captcha', 'turnstile', 'hcaptcha', 'recaptcha')
DEVICE_RISK_MARKERS = ('device fingerprint', 'fingerprintjs', 'browser fingerprint', 'visitorid', 'bot score', 'risk engine')
RETRY_MARKERS = ('retry', 'backoff', 'dead_letter', 'dead-letter', 'max_attempt', 'attempt_count')
OBJECT_STORAGE_MARKERS = ('boto3', 'minio', 's3', 'oss2', 'azure.storage.blob', 'presigned')
UPLOAD_LIMIT_MARKERS = (
    'content-length',
    'max_upload',
    'max_file',
    'max_pages',
    'max_page',
    'max_pixels',
    'pixel_limit',
    'page_limit',
    'file.size',
)


@dataclass(slots=True)
class ProjectSnapshot:
    repo_root: Path
    file_texts: dict[str, str]
    route_list: list[str]
    source_index: str
    signal_index: str


def scan_project(repo_root: Path) -> AuditReport:
    repo_root = repo_root.resolve()
    snapshot = _build_snapshot(repo_root)
    findings = _build_findings(snapshot)
    dimension_scores = _score_dimensions(findings)
    overall_score = _compute_overall_score(dimension_scores)
    release_decision = _release_decision(overall_score, dimension_scores)
    metrics = _collect_metrics(snapshot)
    strengths = _collect_strengths(snapshot, metrics)
    summary = _build_summary(dimension_scores, findings)
    return AuditReport(
        project_name=repo_root.name,
        generated_at=datetime.now(timezone.utc).isoformat(),
        overall_score=overall_score,
        release_decision=release_decision,
        summary=summary,
        metrics=metrics,
        strengths=strengths,
        dimension_scores=dimension_scores,
        findings=sorted(findings, key=_finding_sort_key),
    )


def write_report_files(report: AuditReport, output_dir: Path, base_name: str) -> tuple[Path, Path]:
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    json_path = output_dir / f'{base_name}.json'
    md_path = output_dir / f'{base_name}.md'

    json_path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    md_path.write_text(render_markdown(report), encoding='utf-8')
    return json_path, md_path


def render_markdown(report: AuditReport) -> str:
    lines: list[str] = [
        f'# {report.project_name} ??????????',
        '',
        f'- ?????{report.generated_at}',
        f'- ?????{report.overall_score}',
        f'- ?????{report.release_decision}',
        '',
        '## ??',
        '',
    ]

    for item in report.summary:
        lines.append(f'- {item}')

    if report.strengths:
        lines.extend(['', '## ????', ''])
        for item in report.strengths:
            lines.append(f'- {item}')

    lines.extend(['', '## ????', '', '| ?? | ?? | ?? | ??? |', '| --- | ---: | ---: | ---: |'])
    for score in report.dimension_scores:
        lines.append(f'| {score.label} | {score.score} | {score.weight} | {score.finding_count} |')

    lines.extend(['', '## ????', ''])
    for key, value in report.metrics.items():
        lines.append(f'- `{key}`: {value}')

    lines.extend(['', '## ????', ''])
    if not report.findings:
        lines.append('- ???????????????')
        return '\n'.join(lines)

    for finding in report.findings:
        lines.extend(
            [
                f'### [{finding.severity}] {finding.title}',
                '',
                f'- ???{_label_for_dimension(finding.dimension)}',
                f'- ???{finding.impact}',
                f'- ???{finding.recommendation}',
                f'- ???{finding.acceptance_criteria}',
                f'- ?????{finding.owner_hint}',
                '- ???',
            ]
        )
        for evidence in finding.evidence:
            lines.append(f'  - `{evidence}`')
        lines.append('')

    return '\n'.join(lines).rstrip() + '\n'


def _build_snapshot(repo_root: Path) -> ProjectSnapshot:
    key_files = [
        'backend/src/main.py',
        'backend/src/auth.py',
        'backend/src/rate_limit.py',
        'backend/src/llm_client.py',
        'backend/src/ocr/ingest_service.py',
        'backend/src/services/queue_service.py',
        'backend/src/workers/review_worker.py',
        'frontend/src/lib/reviewHistory.ts',
        'frontend/src/hooks/useStreamingReview.ts',
        'frontend/src/components/DocPanel.tsx',
        'frontend/src/pages/RegisterPage.tsx',
        'frontend/src/contexts/AuthContext.tsx',
        'backend/.env.example',
        '.env.docker',
        'frontend/nginx.conf',
    ]
    file_texts = {
        relative_path: _read_text(repo_root / relative_path)
        for relative_path in key_files
        if (repo_root / relative_path).exists()
    }

    signal_chunks: list[str] = []
    for path in _iter_signal_files(repo_root):
        text = _read_text(path)
        if text:
            signal_chunks.append(text)
    signal_index = '\n'.join(signal_chunks).lower()

    main_text = file_texts.get('backend/src/main.py', '')
    route_list = re.findall(r'@app\.(?:get|post|put|patch|delete)\("([^"]+)"', main_text)

    return ProjectSnapshot(
        repo_root=repo_root,
        file_texts=file_texts,
        route_list=route_list,
        source_index='\n'.join(file_texts.values()),
        signal_index=signal_index,
    )


def _iter_signal_files(repo_root: Path) -> list[Path]:
    base_dirs = [repo_root / 'backend' / 'src', repo_root / 'frontend' / 'src']
    extra_files = [
        repo_root / 'backend' / '.env.example',
        repo_root / '.env.docker',
        repo_root / 'frontend' / 'nginx.conf',
    ]
    excluded_parts = {
        '__pycache__',
        'audit',
        'tests',
        'dist',
        'node_modules',
        '.venv',
        'contract_review_copilot_backend.egg-info',
    }

    collected: list[Path] = []
    for base_dir in base_dirs:
        if not base_dir.exists():
            continue
        for path in base_dir.rglob('*'):
            if not path.is_file():
                continue
            relative_parts = set(path.relative_to(repo_root).parts)
            if relative_parts & excluded_parts:
                continue
            if path.suffix.lower() in ALLOWED_SIGNAL_SUFFIXES:
                collected.append(path)

    for path in extra_files:
        if path.exists() and path.is_file():
            collected.append(path)

    return sorted(set(collected))


def _collect_metrics(snapshot: ProjectSnapshot) -> dict[str, object]:
    route_list = snapshot.route_list
    review_history = snapshot.file_texts.get('frontend/src/lib/reviewHistory.ts', '')
    use_streaming = snapshot.file_texts.get('frontend/src/hooks/useStreamingReview.ts', '')
    ingest_service = snapshot.file_texts.get('backend/src/ocr/ingest_service.py', '')
    signal_index = snapshot.signal_index

    return {
        'routeCount': len(route_list),
        'authRouteCount': sum(route.startswith('/api/auth') for route in route_list),
        'reviewRouteCount': sum(route.startswith('/api/review') for route in route_list),
        'chatRouteCount': sum(route.startswith('/api/chat') for route in route_list),
        'uploadRouteCount': sum('/ocr' in route or 'upload' in route for route in route_list),
        'hasQueueEndpoint': '/api/review/queue' in route_list,
        'hasQueueStreamEndpoint': '/api/review/queue/{task_id}/stream' in route_list,
        'hasReviewWorker': 'backend/src/workers/review_worker.py' in snapshot.file_texts,
        'hasQueueService': 'backend/src/services/queue_service.py' in snapshot.file_texts,
        'hasRateLimitModule': 'backend/src/rate_limit.py' in snapshot.file_texts,
        'hasRegistrationRateLimit': '_enforce_auth_rate_limits' in snapshot.file_texts.get('backend/src/main.py', ''),
        'usesLocalStorageHistory': 'localStorage' in review_history,
        'usesSessionStorageHistory': 'sessionStorage' in review_history or 'sessionStorage' in use_streaming,
        'hasPdfPaging': '_render_pdf_to_images' in ingest_service and 'for page_index in range(len(pdf))' in ingest_service,
        'hasRedisCache': (snapshot.repo_root / 'backend/src/cache/redis_cache.py').exists(),
        'hasVectorStore': (snapshot.repo_root / 'backend/src/vectorstore/store.py').exists(),
        'hasDeepReviewRetry': 'retryDeepReview' in use_streaming,
        'hasCaptchaChallenge': any(marker in signal_index for marker in ANTI_BOT_MARKERS),
        'hasDeviceFingerprint': any(marker in signal_index for marker in DEVICE_RISK_MARKERS),
        'hasObjectStorageLayer': any(marker in signal_index for marker in OBJECT_STORAGE_MARKERS),
    }


def _collect_strengths(snapshot: ProjectSnapshot, metrics: dict[str, object]) -> list[str]:
    strengths: list[str] = []
    doc_panel = snapshot.file_texts.get('frontend/src/components/DocPanel.tsx', '')

    if metrics.get('hasQueueEndpoint') and metrics.get('hasReviewWorker'):
        strengths.append('????????????? worker??????????????')
    if metrics.get('hasRateLimitModule'):
        strengths.append('????????????????? Redis ??????')
    if metrics.get('hasRedisCache'):
        strengths.append('Redis ???????????????????????????')
    if metrics.get('hasVectorStore'):
        strengths.append('??? PostgreSQL + pgvector?????????????????')
    if metrics.get('hasPdfPaging'):
        strengths.append('PDF ???????? OCR????????????????')
    if 'accept=".txt,.docx,.pdf,.jpg,.jpeg,.png,.webp"' in doc_panel:
        strengths.append('???????????????????????')
    return strengths[:6]


def _build_findings(snapshot: ProjectSnapshot) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    route_list = snapshot.route_list
    signal_index = snapshot.signal_index
    main_text = snapshot.file_texts.get('backend/src/main.py', '')
    ingest_service = snapshot.file_texts.get('backend/src/ocr/ingest_service.py', '')
    queue_service = snapshot.file_texts.get('backend/src/services/queue_service.py', '')
    review_worker = snapshot.file_texts.get('backend/src/workers/review_worker.py', '')
    review_history = snapshot.file_texts.get('frontend/src/lib/reviewHistory.ts', '')
    use_streaming = snapshot.file_texts.get('frontend/src/hooks/useStreamingReview.ts', '')

    def add(
        finding_id: str,
        dimension: str,
        severity: str,
        title: str,
        evidence: list[str],
        impact: str,
        recommendation: str,
        acceptance_criteria: str,
        owner_hint: str,
    ) -> None:
        findings.append(
            AuditFinding(
                id=finding_id,
                dimension=dimension,
                severity=severity,
                title=title,
                evidence=evidence,
                impact=impact,
                recommendation=recommendation,
                acceptance_criteria=acceptance_criteria,
                owner_hint=owner_hint,
            )
        )

    if '/api/ocr/ingest' in route_list and '_extract_text_from_uploaded_image' in ingest_service:
        add(
            'concurrency-sync-ocr-ingest',
            'concurrency_performance',
            'P1',
            'OCR ?????????????',
            [
                _line_ref(snapshot, 'backend/src/main.py', '@app.post("/api/ocr/ingest")'),
                _line_ref(snapshot, 'backend/src/ocr/ingest_service.py', '_extract_text_from_uploaded_image'),
            ],
            '?? PDF ?????????????????????????????',
            '? OCR ?????????????? task_id???? SSE ??????????',
            '?????? 1 ???? task_id?OCR ? worker ???????????',
            'backend',
        )

    if '/api/review/export-docx' in route_list and '/api/review/queue' in route_list:
        add(
            'concurrency-sync-export',
            'concurrency_performance',
            'P3',
            '????????????',
            [
                _line_ref(snapshot, 'backend/src/main.py', '@app.post("/api/review/export-docx")'),
                _line_ref(snapshot, 'backend/src/services/queue_service.py', 'def create_task('),
            ],
            '????????????? CPU ? IO????????',
            '??????????????????????????????',
            '????????????????????????????',
            'backend',
        )

    if '/api/review' in route_list and '/api/review/deepen' in route_list and '/api/review/queue' in route_list:
        add(
            'async-partial-decoupling-review',
            'async_decoupling',
            'P2',
            '?????????????????',
            [
                _line_ref(snapshot, 'backend/src/main.py', '@app.post("/api/review")'),
                _line_ref(snapshot, 'backend/src/main.py', '@app.post("/api/review/deepen")'),
                _line_ref(snapshot, 'backend/src/main.py', '@app.post("/api/review/queue")'),
            ],
            '??????????????????????????????????',
            '?? review ? deepen ??????????????????/?????',
            'review ? deepen ???????????????????????????',
            'backend',
        )

    if queue_service and review_worker and not any(marker in queue_service.lower() for marker in RETRY_MARKERS):
        add(
            'async-missing-retry-policy',
            'async_decoupling',
            'P2',
            '??????????????????',
            [
                _line_ref(snapshot, 'backend/src/services/queue_service.py', 'def create_task('),
                _line_ref(snapshot, 'backend/src/workers/review_worker.py', 'async def run_queued_review('),
            ],
            '????????????????????????????',
            '????????????????????????????',
            '?????? retry_count?last_error ? dead_letter ???????????',
            'backend',
        )

    unsafe_main_exception_leak = 'str(exc)' in main_text and 'INGEST_VALIDATION_ERROR' not in main_text
    unsafe_worker_exception_leak = 'error_msg = str(exc)' in review_worker or 'push_event(task_id, "error", {"message": error_msg})' in review_worker
    if unsafe_main_exception_leak or unsafe_worker_exception_leak:
        add(
            'content-raw-exception-leak',
            'content_safety',
            'P1',
            '??? worker ????????????',
            [
                _line_ref(snapshot, 'backend/src/main.py', 'str(exc)'),
                _line_ref(snapshot, 'backend/src/workers/review_worker.py', 'error_msg = str(exc)'),
            ],
            '?? OCR???????????????????????????????',
            '???????????????????????????????????',
            '???????????????? str(exc) ???????????',
            'backend',
        )

    if 'localStorage' in review_history or 'sessionStorage' in review_history or 'sessionStorage' in use_streaming:
        add(
            'storage-browser-history',
            'storage_architecture',
            'P2',
            '????????????????????',
            [
                _line_ref(snapshot, 'frontend/src/lib/reviewHistory.ts', 'localStorage'),
                _line_ref(snapshot, 'frontend/src/hooks/useStreamingReview.ts', 'sessionStorage.setItem'),
            ],
            '?????????????????????????????????????',
            '?????????????????????????????????',
            '??????????????????????????????',
            'frontend+backend',
        )

    if '/api/ocr/ingest' in route_list and not any(marker in signal_index for marker in UPLOAD_LIMIT_MARKERS):
        add(
            'large-file-missing-limits',
            'large_file_handling',
            'P1',
            '??????????????????',
            [
                _line_ref(snapshot, 'backend/src/main.py', '@app.post("/api/ocr/ingest")'),
                _line_ref(snapshot, 'backend/src/ocr/ingest_service.py', '_render_pdf_to_images'),
                _line_ref(snapshot, 'frontend/src/components/DocPanel.tsx', 'accept=".txt,.docx,.pdf,.jpg,.jpeg,.png,.webp"'),
            ],
            '?? PDF ?????? OCR ???????????????',
            '?????????????????????????????',
            '???????????? PDF ????????????/???????',
            'backend+frontend',
        )

    if '/api/auth/register' in route_list and not any(marker in signal_index for marker in ANTI_BOT_MARKERS):
        add(
            'anti-bot-missing-challenge',
            'anti_bot_registration',
            'P2',
            '??????????? CAPTCHA ???????',
            [
                _line_ref(snapshot, 'backend/src/main.py', '@app.post("/api/auth/register")'),
                _line_ref(snapshot, 'backend/src/main.py', '_enforce_auth_rate_limits'),
                _line_ref(snapshot, 'frontend/src/pages/RegisterPage.tsx', 'handleSendCode'),
            ],
            '????????????????????????????????',
            '? send-code ? register ?? CAPTCHA???????????????????????????',
            '???????????????????????????',
            'backend+frontend',
        )

    return findings


def _score_dimensions(findings: list[AuditFinding]) -> list[AuditDimensionScore]:
    findings_by_dimension: dict[str, list[AuditFinding]] = defaultdict(list)
    for finding in findings:
        findings_by_dimension[finding.dimension].append(finding)

    scores: list[AuditDimensionScore] = []
    for dimension in DIMENSIONS:
        dimension_findings = findings_by_dimension.get(dimension, [])
        score = 100
        for finding in dimension_findings:
            score -= SEVERITY_WEIGHTS.get(finding.severity, 0)
        score = max(0, score)
        scores.append(
            AuditDimensionScore(
                key=dimension,
                label=_label_for_dimension(dimension),
                score=score,
                weight=DIMENSION_WEIGHTS[dimension],
                finding_count=len(dimension_findings),
            )
        )
    return scores


def _compute_overall_score(scores: list[AuditDimensionScore]) -> int:
    weighted_total = 0.0
    weight_sum = 0
    for score in scores:
        weighted_total += score.score * score.weight
        weight_sum += score.weight
    return round(weighted_total / weight_sum) if weight_sum else 0


def _release_decision(overall_score: int, scores: list[AuditDimensionScore]) -> str:
    if any(score.score < 60 for score in scores) or overall_score < 75:
        return 'block'
    if overall_score < 85:
        return 'warning'
    return 'pass'


def _build_summary(scores: list[AuditDimensionScore], findings: list[AuditFinding]) -> list[str]:
    severe_counts = Counter(finding.severity for finding in findings)
    weakest = sorted(scores, key=lambda item: item.score)[:2]
    return [
        f'??? {len(findings)} ???????? P1 {severe_counts.get("P1", 0)} ??P2 {severe_counts.get("P2", 0)} ??P3 {severe_counts.get("P3", 0)} ??',
        f'???????????{weakest[0].label}?{weakest[0].score} ??? {weakest[1].label}?{weakest[1].score} ???',
        '?????? OCR ??????????????????????????????',
    ]


def _finding_sort_key(finding: AuditFinding) -> tuple[int, str, str]:
    return (SEVERITY_ORDER.get(finding.severity, 99), finding.dimension, finding.id)


def _line_ref(snapshot: ProjectSnapshot, relative_path: str, marker: str) -> str:
    text = snapshot.file_texts.get(relative_path, '')
    if not text:
        return f'{relative_path}:1'
    index = text.find(marker)
    if index < 0:
        return f'{relative_path}:1'
    line_number = text[:index].count('\n') + 1
    return f'{relative_path}:{line_number}'


def _label_for_dimension(dimension: str) -> str:
    return DIMENSION_LABELS.get(dimension, dimension)


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        return path.read_text(encoding='utf-8-sig')
    except FileNotFoundError:
        return ''

