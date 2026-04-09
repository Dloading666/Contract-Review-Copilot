from fastapi.testclient import TestClient

from src import main


def test_protected_endpoints_require_auth():
    client = TestClient(main.app)

    autofix_response = client.post('/api/autofix', json={})
    chat_response = client.post('/api/chat', json={'message': 'hello'})
    export_response = client.post('/api/review/export-docx', json={'report_paragraphs': ['报告内容']})
    review_response = client.post('/api/review', json={'contract_text': '合同文本'})

    assert autofix_response.status_code == 401
    assert chat_response.status_code == 401
    assert export_response.status_code == 401
    assert review_response.status_code == 401


def test_models_endpoint_returns_available_models():
    client = TestClient(main.app)
    response = client.get('/api/models')

    assert response.status_code == 200
    payload = response.json()
    assert payload['default_model'] == 'gemma4'
    assert any(model['key'] == 'gemma4' for model in payload['models'])


def test_register_rejects_invalid_email_without_top_level_domain(monkeypatch):
    monkeypatch.setattr(main.auth, 'register_user', lambda *_args, **_kwargs: {'success': True})

    client = TestClient(main.app)
    response = client.post(
        '/api/auth/register',
        json={
            'email': 'user@domaincom',
            'code': '123456',
            'password': 'secret123',
        },
    )

    assert response.status_code == 400


def test_review_generates_uuid_session_id_when_client_omits_one(monkeypatch):
    captured: list[str] = []

    async def fake_run_review_stream(contract_text: str, session_id: str, model_key: str | None = None):
        captured.append(session_id)
        yield {'event': 'review_complete', 'data': {'session_id': session_id}}

    monkeypatch.setattr(main, 'run_review_stream', fake_run_review_stream)
    monkeypatch.setattr(
        main.auth,
        'get_user_from_token',
        lambda token: {'email': 'owner@example.com'} if token == 'token-a' else None,
    )

    client = TestClient(main.app)
    for _ in range(2):
        with client.stream(
            'POST',
            '/api/review',
            json={'contract_text': '合同文本', 'model': 'gemma4'},
            headers={'Authorization': 'Bearer token-a'},
        ) as response:
            assert response.status_code == 200
            list(response.iter_text())

    assert len(captured) == 2
    assert captured[0] != captured[1]
    assert all(session_id.startswith('session-') for session_id in captured)
    assert all(len(session_id) == len('session-') + 32 for session_id in captured)


def test_chat_endpoint_uses_selected_model(monkeypatch):
    monkeypatch.setattr(
        main.auth,
        'get_user_from_token',
        lambda token: {'email': 'owner@example.com'} if token == 'token-a' else None,
    )

    capture: dict[str, object] = {}

    class _FakeResponse:
        model = 'gemma3'
        choices = [type('Choice', (), {'message': type('Message', (), {'content': '这是模型回复。'})()})()]

    monkeypatch.setattr(
        main,
        'create_chat_completion',
        lambda **kwargs: capture.update(kwargs) or _FakeResponse(),
    )

    client = TestClient(main.app)
    response = client.post(
        '/api/chat',
        json={
            'message': '这份合同的押金条款有什么问题？',
            'model': 'gemma4',
            'contract_text': '押金不予退还。',
            'risk_summary': '[high] 押金条款：押金不予退还',
        },
        headers={'Authorization': 'Bearer token-a'},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload['reply'] == '这是模型回复。'
    assert payload['model'] == 'gemma3'
    assert capture['model'] == 'gemma4'
    assert '押金不予退还' in capture['messages'][0]['content']


def test_review_accepts_valid_token_after_user_store_reset(monkeypatch):
    capture: dict[str, str | None] = {}

    async def fake_run_review_stream(contract_text: str, session_id: str, model_key: str | None = None):
        capture['model_key'] = model_key
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
        json={'contract_text': '合同文本', 'session_id': 'session-auth', 'model': 'gemma4'},
        headers={'Authorization': f'Bearer {token}'},
    ) as response:
        assert response.status_code == 200
        stream_body = ''.join(response.iter_text())

    assert 'review_complete' in stream_body
    assert capture['model_key'] == 'gemma4'
    assert main.auth._user_store['restart']['email'] == email


def test_breakpoint_session_is_owned_and_preserves_issues(monkeypatch):
    capture: dict[str, str | None] = {}

    async def fake_run_review_stream(contract_text: str, session_id: str, model_key: str | None = None):
        capture['review_model_key'] = model_key
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

    async def fake_run_aggregation_stream(
        contract_text: str,
        session_id: str,
        issues: list[dict],
        model_key: str | None = None,
    ):
        capture['aggregation_model_key'] = model_key
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
        json={'contract_text': '合同文本', 'session_id': 'session-1', 'model': 'gemma4'},
        headers={'Authorization': 'Bearer token-a'},
    ) as response:
        assert response.status_code == 200
        list(response.iter_text())

    assert main.paused_sessions['session-1']['issues'][0]['clause'] == '押金条款'
    assert main.paused_sessions['session-1']['model_key'] == 'gemma4'
    assert capture['review_model_key'] == 'gemma4'

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

    assert capture['aggregation_model_key'] == 'gemma4'
    assert 'session-1' not in main.paused_sessions


def test_export_report_docx_returns_word_document(monkeypatch):
    monkeypatch.setattr(
        main.auth,
        'get_user_from_token',
        lambda token: {'email': 'owner@example.com'} if token == 'token-a' else None,
    )

    client = TestClient(main.app)
    response = client.post(
        '/api/review/export-docx',
        json={
            'filename': '租房合同.docx',
            'report_paragraphs': ['## 审查结论', '存在 1 处高危条款。'],
        },
        headers={'Authorization': 'Bearer token-a'},
    )

    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    assert 'filename*=UTF-8' in response.headers['content-disposition']
    assert response.content.startswith(b'PK')
