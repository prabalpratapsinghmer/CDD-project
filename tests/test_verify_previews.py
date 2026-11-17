import json
import os
from pathlib import Path
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'verify-previews.py'
FAKE_AZ = '''#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
command = ' '.join(args[:2]) if args[0] != 'login' else 'login'
if command == os.getenv('FAIL_COMMAND'):
    print('private-secret', file=sys.stderr)
    sys.exit(1)
if command == 'group show':
    print('eastus')
elif command == 'container list-usage':
    print('[{"currentValue":2,"limit":10,"secret":"private-secret"}]')
elif command == 'container list':
    if os.getenv('MALFORMED'):
        print('not json')
    else:
        groups = json.load(open(os.environ['STATE']))
        query = args[args.index('--query') + 1]
        print(json.dumps([g for g in groups if g['name'] in query]))
else:
    print('{}')
'''


@pytest.fixture
def verifier(tmp_path):
    class Handler(BaseHTTPRequestHandler):
        status = 200

        def do_GET(self):
            self.send_response(self.status)
            self.end_headers()

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    binary = tmp_path / 'az'
    binary.write_text(FAKE_AZ)
    binary.chmod(0o755)
    state = tmp_path / 'state.json'
    output = tmp_path / 'output'
    groups = [dict(name=f'preview-pr-{pr}', tags={
        'managed-by': 'cdd-preview', 'pr-number': pr,
        'preview-owner': 'test-preview'},
        containers=[{'image': f'ghcr.io/example/app:{pr}'}],
        provisioningState='Succeeded', ipAddress={
            'fqdn': 'localhost', 'ip': '127.0.0.1',
            'ports': [{'port': server.server_port}]}) for pr in ('41', '42')]
    env = dict(PATH=str(tmp_path) + os.pathsep + os.defpath,
               RUNNER_TEMP=str(tmp_path), GITHUB_OUTPUT=str(output),
               STATE=str(state), PR_A='41', PR_B='42',
               EXPECTED_IMAGE_A='ghcr.io/example/app:41',
               EXPECTED_IMAGE_B='ghcr.io/example/app:42',
               EXPECTATION='both-present', PREVIEW_DNS_PREFIX='test-preview',
               AZURE_RESOURCE_GROUP='preview-rg',
               AZURE_CREDENTIALS=json.dumps(dict(
                   clientId='client', clientSecret='private-secret',
                   tenantId='tenant', subscriptionId='subscription')))

    def run(records=None, http_status=200, **overrides):
        Handler.status = http_status
        state.write_text(json.dumps(groups if records is None else records))
        output.write_text('')
        result = subprocess.run(
            ['python3', str(SCRIPT)], env=dict(env, **overrides),
            capture_output=True, text=True, timeout=30)
        outputs = dict(line.split('=', 1)
                       for line in output.read_text().splitlines())
        path = Path(outputs['evidence_path'])
        evidence = json.loads(path.read_text())
        visible = result.stdout + result.stderr + path.read_text()
        assert 'private-secret' not in visible
        assert path.parent == tmp_path
        assert not list(tmp_path.glob('cdd-verify-cli-*'))
        return result, evidence

    yield run, groups
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.mark.parametrize('expectation, count', [
    ('both-present', 2), ('a-present-b-absent', 1),
    ('both-absent', 0), ('inventory', 2)])
def test_presence_transitions(verifier, expectation, count):
    run, groups = verifier
    result, evidence = run(groups[:count], EXPECTATION=expectation)
    assert result.returncode == 0, result.stderr
    assert evidence['status'] == 'success'
    observed = [r['present'] for r in evidence['records']]
    assert observed == [count > 0, count > 1]
    assert evidence['quota']['status'] == 'observed'


@pytest.mark.parametrize('change, expected', [
    ('image', 'image'), ('owner', 'ownership'),
    ('http', 'HTTP'), ('provision', 'provisioning')])
def test_observation_mismatches_persist(verifier, change, expected):
    run, groups = verifier
    if change == 'image':
        groups[0]['containers'][0]['image'] = 'ghcr.io/example/app:stale'
    elif change == 'owner':
        groups[0]['tags']['preview-owner'] = 'other'
    elif change == 'http':
        groups[0]['ipAddress']['ports'][0]['port'] = 1
    else:
        groups[0]['provisioningState'] = 'Failed'
    result, evidence = run(groups)
    assert result.returncode != 0
    assert expected in evidence['error']
    record = evidence['records'][0]
    assert record['present'] is True
    if change == 'owner':
        assert record['fqdn'] is None and record['image'] is None
    if change == 'http':
        assert record['http']['success'] is False
        assert record['image'] == 'ghcr.io/example/app:41'


@pytest.mark.parametrize('override', [
    {'MALFORMED': '1'}, {'FAIL_COMMAND': 'login'},
    {'PR_B': '41'}, {'PR_A': '../unsafe'}, {'AZURE_CREDENTIALS': '{}'}])
def test_invalid_inputs_and_cloud_errors_persist(verifier, override):
    run, _ = verifier
    result, evidence = run(**override)
    assert result.returncode != 0
    assert evidence['status'] == 'failure'
    assert evidence['records'][0]['verified_absent'] is None


def test_quota_permission_is_separate(verifier):
    run, _ = verifier
    result, evidence = run(FAIL_COMMAND='container list-usage')
    assert result.returncode == 0
    assert evidence['quota'] == {'status': 'unavailable', 'limits': None}


def test_unexpected_presence_fails(verifier):
    run, _ = verifier
    result, evidence = run(EXPECTATION='both-absent')
    assert result.returncode != 0
    assert 'presence' in evidence['error']


def test_public_http_503_is_retained(verifier):
    run, _ = verifier
    result, evidence = run(http_status=503)
    assert result.returncode != 0
    http = evidence['records'][0]['http']
    assert http['status_code'] == 503
    assert http['success'] is False


@pytest.mark.parametrize('field, value', [
    ('containers', {'private-secret': {}}),
    ('containers', ['private-secret']),
    ('containers', 'private-secret'),
    ('containers', None),
    ('ports', {'private-secret': {}}),
    ('ports', ['private-secret']),
    ('ports', 'private-secret'),
    ('ipAddress', 'private-secret'),
    ('tags', ['private-secret']),
])
def test_malformed_nested_shapes_fail_safely(verifier, field, value):
    run, groups = verifier
    if field == 'ports':
        groups[0]['ipAddress']['ports'] = value
    else:
        groups[0][field] = value
    result, evidence = run(groups)
    assert result.returncode != 0
    assert 'Traceback' not in result.stderr
    assert evidence['status'] == 'failure'
    assert evidence['error']
    record = evidence['records'][0]
    assert record['status'] == 'failure'
    assert record['present'] is True
    assert record['verified_absent'] is None
    if field != 'tags':
        assert record['tags']['pr-number'] == '41'
    if field == 'ports':
        assert record['image'] == 'ghcr.io/example/app:41'
        assert record['fqdn'] == 'localhost'
