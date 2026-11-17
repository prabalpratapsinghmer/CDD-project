import pytest
from app import accent_hue, app, fingerprint

BUILD_ENV = {
    'PR_NUMBER': '7',
    'COMMIT_SHA': 'a1b2c3d4e5f60718293a4b5c6d7e8f9012345678',
    'BRANCH': 'feature/blue-header',
    'BUILD_TIME': '2026-11-17T10:15:30Z',
    'RUN_URL': 'https://github.com/acme/demo/actions/runs/424242',
    'REPO_URL': 'https://github.com/acme/demo',
    'IMAGE_TAG': 'ghcr.io/acme/demo:pr-7-a1b2c3d',
}


@pytest.fixture
def client(monkeypatch):
    # Start from a clean "local run" so developer env never leaks in.
    for key in BUILD_ENV:
        monkeypatch.delenv(key, raising=False)
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def set_build_env(monkeypatch, **overrides):
    for key, value in dict(BUILD_ENV, **overrides).items():
        monkeypatch.setenv(key, value)


def test_ci_metadata_is_shown_and_linked(client, monkeypatch):
    set_build_env(monkeypatch)
    page = client.get('/').get_data(as_text=True)
    assert 'PR&nbsp;#7' in page
    assert BUILD_ENV['COMMIT_SHA'] in page
    assert 'feature/blue-header' in page
    assert 'https://github.com/acme/demo/pull/7' in page
    repo = BUILD_ENV['REPO_URL']
    assert f"{repo}/commit/{BUILD_ENV['COMMIT_SHA']}" in page
    assert BUILD_ENV['RUN_URL'] in page
    assert BUILD_ENV['IMAGE_TAG'] in page
    assert 'Local build' not in page


def test_branch_name_cannot_inject_html(client, monkeypatch):
    set_build_env(monkeypatch, BRANCH='<script>alert(1)</script>')
    page = client.get('/').get_data(as_text=True)
    assert '<script>alert(1)</script>' not in page
    assert '&lt;script&gt;alert(1)&lt;/script&gt;' in page


def test_local_run_renders_without_ci_metadata(client):
    response = client.get('/')
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'Local build' in page
    assert '/pull/' not in page


def test_fingerprint_is_stable_per_commit_and_differs_between_commits():
    bars = fingerprint('a' * 40)
    assert bars == fingerprint('a' * 40)
    assert bars != fingerprint('b' * 40)
    assert len(bars) == 20 and all(0 <= bar < 360 for bar in bars)


def test_consecutive_prs_get_clearly_different_accent_colours():
    for number in range(1, 200):
        a, b = accent_hue(str(number)), accent_hue(str(number + 1))
        assert 0 <= a < 360
        assert min((a - b) % 360, (b - a) % 360) > 90
    assert accent_hue('') == accent_hue('not-a-number')


def test_api_info_reports_build_and_uptime(client, monkeypatch):
    set_build_env(monkeypatch)
    data = client.get('/api/info').get_json()
    assert data['pr_number'] == '7'
    assert data['commit_sha'] == BUILD_ENV['COMMIT_SHA']
    assert data['image_tag'] == BUILD_ENV['IMAGE_TAG']
    assert data['hostname']
    assert data['uptime_seconds'] >= 0
