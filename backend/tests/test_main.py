from fastapi.testclient import TestClient

from src import main


def test_protected_endpoints_require_auth():
    client = TestClient(main.app)

    autofix_response = client.post('/api/autofix', json={})
    review_response = client.post('/api/review', json={'contract_text': '合同文本'})

    assert autofix_response.status_code == 401
    assert review_response.status_code == 401


def test_review_accepts_valid_token_after_user_store_reset(monkeypatch):
    async def fake_run_review_stream(contract_text: str, session_id: str):
        yield {'event': 'review_complete', 'data': {'session_id': session_id}}

    monkeypatch.setattr(main, 'run_review_stream', fake_run_review_stream)

    main.paused_sessions.clear()
    main.auth._code_store.clear()
    main.auth._user_store.clear()

    email = 'restart@example.com'
    send_code_result = main.auth.send_verification_code(email)
    token = main.auth.verify_code(email, send_code_result['dev_code'])

    # Simulate a backend restart clearing in-memory users while the browser still
    # holds a valid JWT.
    main.auth._user_store.clear()

    client = TestClient(main.app)
    with client.stream(
        'POST',
        '/api/review',
        json={'contract_text': '合同文本', 'session_id': 'session-auth'},
        headers={'Authorization': f'Bearer {token}'},
    ) as response:
        assert response.status_code == 200
        stream_body = ''.join(response.iter_text())

    assert 'review_complete' in stream_body
    assert main.auth._user_store['restart']['email'] == email


def test_breakpoint_session_is_owned_and_preserves_issues(monkeypatch):
    async def fake_run_review_stream(contract_text: str, session_id: str):
        yield {
            'event': 'breakpoint',
            'data': {
                'session_id': session_id,
                'breakpoint': {
                    'needs_review': True,
                    'question': '继续吗？',
                    'issues_count': 1,
                    'critical_count': 0,
                    'high_count': 1,
                    'medium_count': 0,
                },
                'issues': [
                    {
                        'clause': '押金条款',
                        'level': 'high',
                        'risk_level': 3,
                        'issue': '押金过高',
                        'suggestion': '降低押金',
                        'legal_reference': '《民法典》第585条',
                    },
                ],
            },
        }

    async def fake_run_aggregation_stream(contract_text: str, session_id: str, issues: list[dict]):
        assert issues[0]['clause'] == '押金条款'
        yield {'event': 'stream_resume', 'data': {'session_id': session_id}}
        yield {'event': 'review_complete', 'data': {'session_id': session_id}}

    token_users = {
        'token-a': {'email': 'owner@example.com'},
        'token-b': {'email': 'other@example.com'},
    }

    monkeypatch.setattr(main, 'run_review_stream', fake_run_review_stream)
    monkeypatch.setattr(main, 'run_aggregation_stream', fake_run_aggregation_stream)
    monkeypatch.setattr(main.auth, 'get_user_from_token', lambda token: token_users.get(token))

    main.paused_sessions.clear()
    client = TestClient(main.app)

    with client.stream(
        'POST',
        '/api/review',
        json={'contract_text': '合同文本', 'session_id': 'session-1'},
        headers={'Authorization': 'Bearer token-a'},
    ) as response:
        assert response.status_code == 200
        list(response.iter_text())

    assert main.paused_sessions['session-1']['issues'][0]['clause'] == '押金条款'

    forbidden_response = client.post(
        '/api/review/confirm/session-1',
        json={'confirmed': True},
        headers={'Authorization': 'Bearer token-b'},
    )
    assert forbidden_response.status_code == 403

    with client.stream(
        'POST',
        '/api/review/confirm/session-1',
        json={'confirmed': True},
        headers={'Authorization': 'Bearer token-a'},
    ) as response:
        assert response.status_code == 200
        list(response.iter_text())

    assert 'session-1' not in main.paused_sessions
