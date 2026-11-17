"""Acceptance-only fault: never merge this disposable PR."""
from app import app


def test_only_aci_runtime_configuration_activates_fault(monkeypatch):
    client = app.test_client()
    monkeypatch.delenv('GUNICORN_CMD_ARGS', raising=False)
    assert client.get('/').status_code == 200
    monkeypatch.setenv('GUNICORN_CMD_ARGS', '')
    assert client.get('/').status_code == 200
    monkeypatch.setenv('GUNICORN_CMD_ARGS', '--workers 2 --threads 8')
    response = client.get('/')
    assert response.status_code == 503
    assert b'deliberate ACI-only readiness fault' in response.data
    assert client.get('/api/info').status_code == 200
