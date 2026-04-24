from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from src import main


def test_send_code_rejects_honeypot_submission(monkeypatch):
    def should_not_send(_email: str):
        raise AssertionError('verification code sender should not run for bot submissions')

    monkeypatch.setattr(main.auth, 'send_verification_code', should_not_send)

    client = TestClient(main.app)
    response = client.post('/api/auth/send-code', json={
        'email': 'demo@example.com',
        'website': 'spam.example',
        'client_elapsed_ms': 2500,
        'captcha_token': None,
    })

    assert response.status_code == 400
    payload = response.json()
    assert payload['code'] == 'AUTH_BOT_GUARD'


def test_register_rejects_submissions_that_are_too_fast(monkeypatch):
    def should_not_register(*_args, **_kwargs):
        raise AssertionError('register_user should not run for suspiciously fast submissions')

    monkeypatch.setattr(main.auth, 'register_user', should_not_register)

    client = TestClient(main.app)
    response = client.post('/api/auth/register', json={
        'email': 'demo@example.com',
        'code': '123456',
        'password': 'Secret123',
        'website': '',
        'client_elapsed_ms': 100,
        'captcha_token': None,
    })

    assert response.status_code == 429
    payload = response.json()
    assert payload['code'] == 'AUTH_BOT_TOO_FAST'


def test_send_code_requires_captcha_when_enabled(monkeypatch):
    monkeypatch.setattr(
        main,
        'get_settings',
        lambda: SimpleNamespace(
            captcha_enabled=True,
            captcha_secret_key='secret-key',
            captcha_verify_url='https://example.com/siteverify',
        ),
    )

    client = TestClient(main.app)
    response = client.post('/api/auth/send-code', json={
        'email': 'demo@example.com',
        'website': '',
        'client_elapsed_ms': 2400,
        'captcha_token': None,
    })

    assert response.status_code == 400
    payload = response.json()
    assert payload['code'] == 'AUTH_CAPTCHA_REQUIRED'
