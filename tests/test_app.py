import pytest
from app import STARTED_AT, accent_hue, app

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
    response = client.get('/')
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    for key in ('COMMIT_SHA', 'BRANCH', 'IMAGE_TAG', 'BUILD_TIME'):
        assert BUILD_ENV[key] in page
    repo = BUILD_ENV['REPO_URL']
    assert f'{repo}/pull/7' in page
    assert f"{repo}/commit/{BUILD_ENV['COMMIT_SHA']}" in page
    assert BUILD_ENV['RUN_URL'] in page
    assert 'Local development — CI revision metadata unavailable.' not in page


@pytest.mark.parametrize('field', [
    'PR_NUMBER', 'COMMIT_SHA', 'BRANCH', 'IMAGE_TAG', 'BUILD_TIME',
])
def test_revision_metadata_cannot_inject_html(client, monkeypatch, field):
    payload = '<script>alert("revision")</script>'
    set_build_env(monkeypatch, **{field: payload})
    page = client.get('/').get_data(as_text=True)
    assert payload not in page
    assert '&lt;script&gt;alert(&#34;revision&#34;)&lt;/script&gt;' in page
    data = client.get('/api/info').get_json()
    assert data[field.lower()] == payload


def test_page_title_names_the_pr_only_for_ci_builds(client, monkeypatch):
    local = client.get('/').get_data(as_text=True)
    assert '<title>CDD Project' in local
    set_build_env(monkeypatch)
    ci = client.get('/').get_data(as_text=True)
    assert '<title>PR #7 · CDD Project' in ci


def test_local_run_renders_without_ci_metadata(client):
    response = client.get('/')
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'Local development — CI revision metadata unavailable.' in page
    assert '/pull/' not in page
    data = client.get('/api/info').get_json()
    for key in BUILD_ENV:
        assert data[key.lower()] == ''


@pytest.mark.parametrize('missing_field', ['PR_NUMBER', 'COMMIT_SHA'])
def test_partial_revision_is_not_presented_as_ci_build(
        client, monkeypatch, missing_field):
    set_build_env(monkeypatch, **{missing_field: ''})
    page = client.get('/').get_data(as_text=True)
    assert 'Local development — CI revision metadata unavailable.' in page
    # Not a CI build, but whatever was supplied is still shown, not hidden.
    assert BUILD_ENV['BRANCH'] in page
    assert BUILD_ENV['IMAGE_TAG'] in page
    supplied_field = (
        'COMMIT_SHA' if missing_field == 'PR_NUMBER' else 'PR_NUMBER')
    data = client.get('/api/info').get_json()
    assert data[missing_field.lower()] == ''
    assert data[supplied_field.lower()] == BUILD_ENV[supplied_field]


def test_api_info_reports_build_and_uptime(client, monkeypatch):
    set_build_env(monkeypatch)
    response = client.get('/api/info')
    assert response.status_code == 200
    data = response.get_json()
    for key, value in BUILD_ENV.items():
        assert data[key.lower()] == value
    assert data['hostname']
    assert data['started_at'] == STARTED_AT.isoformat()
    assert isinstance(data['uptime_seconds'], int)
    assert data['uptime_seconds'] >= 0


def test_consecutive_prs_get_clearly_different_tints():
    for number in range(1, 200):
        a, b = accent_hue(str(number)), accent_hue(str(number + 1))
        assert 0 <= a < 360
        assert min((a - b) % 360, (b - a) % 360) > 90


@pytest.mark.parametrize('pr_number', [
    '', 'abc', '²', '٣', '1' * 11, '9' * 5000])
def test_malformed_pr_number_gets_default_tint_and_page_still_renders(
        client, monkeypatch, pr_number):
    assert accent_hue(pr_number) == accent_hue('')
    set_build_env(monkeypatch, PR_NUMBER=pr_number)
    assert client.get('/').status_code == 200
