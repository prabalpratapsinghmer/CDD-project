import json
import os
from pathlib import Path
import re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest


DEPLOY_SCRIPT = (
    Path(__file__).resolve().parents[1] / 'scripts' / 'deploy-preview.sh'
)
CLIENT_SECRET = 'private-azure-client-secret'
REGISTRY_PASSWORD = 'private-ghcr-pull-token'

FAKE_AZ = r'''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import re
import sys

state_path = Path(os.environ['FAKE_AZ_STATE'])
state = json.loads(state_path.read_text())
args = sys.argv[1:]
command = ' '.join(args[:2]) if args[0] != 'login' else 'login'
state['calls'].append(command)
state_path.write_text(json.dumps(state))
if command == os.environ.get('FAKE_AZ_FAILURE'):
    print('Azure rejected private-azure-client-secret private-ghcr-pull-token',
          file=sys.stderr)
    sys.exit(1)

def value(flag):
    return args[args.index(flag) + 1] if flag in args else None

if command in ('login', 'account set'):
    print('{}')
elif command == 'group show':
    print('eastus')
elif command == 'container list':
    records = list(state['containers'].values())
    query = value('--query')
    if query:
        match = re.fullmatch(r"\[\?name\s*==\s*['\"]([^'\"]+)['\"]\]", query)
        if not match:
            raise SystemExit('Unsupported fake list query: ' + query)
        records = [
            record for record in records if record['name'] == match.group(1)
        ]
    print(json.dumps(records))
elif command == 'container create':
    name = value('--name')
    definition = json.loads(Path(value('--file')).read_text())
    record = definition['properties']
    record['containers'] = [
        dict(container['properties'], name=container['name'])
        for container in record['containers']
    ]
    record.update({
        'name': name,
        'resourceGroup': value('--resource-group'),
        'location': definition['location'],
        'tags': definition['tags'],
        'provisioningState': 'Succeeded',
    })
    record['ipAddress']['fqdn'] = (
        '127.0.0.1' if name == 'preview-pr-41' else 'localhost'
    )
    state['containers'][name] = record
    state_path.write_text(json.dumps(state))
    print(json.dumps(record))
elif command == 'container show':
    record = state['containers'][value('--name')]
    fault = os.environ.get('FAKE_AZ_SHOW_FAULT')
    if fault == 'missing-fqdn':
        record['ipAddress']['fqdn'] = None
    elif fault == 'wrong-image':
        record['containers'][0]['image'] = 'ghcr.io/example/app:unexpected'
    elif fault == 'failed-provisioning':
        record['provisioningState'] = 'Failed'
    print(json.dumps(record))
else:
    raise SystemExit('Unexpected fake az command: ' + command)
'''


@pytest.fixture
def deployment(tmp_path):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    az = bin_dir / 'az'
    az.write_text(FAKE_AZ)
    az.chmod(0o755)
    state_path = tmp_path / 'azure.json'
    state_path.write_text(json.dumps({'calls': [], 'containers': {}}))
    served = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state = json.loads(state_path.read_text())
            host = self.headers['Host'].rsplit(':', 1)[0]
            name = next(name for name, group in state['containers'].items()
                        if group['ipAddress']['fqdn'] == host)
            image = state['containers'][name]['containers'][0]['image']
            served.append((name, image, self.path))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(image.encode())

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    credentials = json.dumps({
        'clientId': 'test-client',
        'clientSecret': CLIENT_SECRET,
        'tenantId': 'test-tenant',
        'subscriptionId': 'test-subscription',
    })
    # Never inherit developer/cloud credentials or proxy settings.
    env = {
        'PATH': str(bin_dir) + os.pathsep + os.defpath,
        'HOME': str(tmp_path),
        'NO_PROXY': '*',
        'FAKE_AZ_STATE': str(state_path),
        'PR_NUMBER': '41',
        'IMAGE_REF': 'ghcr.io/example/app:revision-one',
        'AZURE_CREDENTIALS': credentials,
        'GITHUB_ACTIONS': 'true',
        'PREVIEW_DNS_PREFIX': 'test-preview',
        'REGISTRY_USERNAME': 'preview-reader',
        'REGISTRY_PASSWORD': REGISTRY_PASSWORD,
        'CONTAINER_PORT': str(server.server_port),
    }
    output_path = tmp_path / 'github-output'

    class Deployment:
        def run(self, **overrides):
            output_path.write_text('')
            run_env = dict(env, GITHUB_OUTPUT=str(output_path))
            for key, value in overrides.items():
                if value is None:
                    run_env.pop(key, None)
                else:
                    run_env[key] = value
            result = subprocess.run(
                ['bash', str(DEPLOY_SCRIPT)], env=run_env,
                text=True, capture_output=True, timeout=20,
            )
            output_text = output_path.read_text()
            outputs = dict(
                line.split('=', 1) for line in output_text.splitlines()
            )
            logs = result.stdout + result.stderr + output_text
            visible = '\n'.join(
                line for line in logs.splitlines()
                if not line.startswith('::add-mask::')
            )
            assert CLIENT_SECRET not in visible
            assert REGISTRY_PASSWORD not in visible
            return result, outputs

        def state(self):
            return json.loads(state_path.read_text())

        def fail_http(self):
            curl = bin_dir / 'curl'
            curl.write_text(
                '#!/bin/sh\n'
                'echo "private-azure-client-secret '
                'private-ghcr-pull-token" >&2\n'
                'exit 22\n'
            )
            curl.chmod(0o755)

    fixture = Deployment()
    fixture.served = served
    fixture.port = server.server_port
    fixture.state_path = state_path
    try:
        yield fixture
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def assert_failure(result, outputs, reason):
    assert result.returncode != 0, result.stdout + result.stderr
    assert outputs.get('status') == 'failure'
    assert not outputs.get('url')
    assert outputs.get('error_message')
    assert '\n' not in outputs['error_message']
    assert re.search(reason, outputs['error_message'], re.IGNORECASE), outputs


def test_create_two_prs_then_update_one_preserves_other(deployment):
    urls = {}
    for number, revision in [('41', 'one'), ('42', 'two'), ('41', 'three')]:
        image = f'ghcr.io/example/app:revision-{revision}'
        result, outputs = deployment.run(PR_NUMBER=number, IMAGE_REF=image)
        assert result.returncode == 0, result.stdout + result.stderr
        assert outputs['status'] == 'success'
        assert not outputs.get('error_message')
        if number in urls:
            assert outputs['url'] == urls[number]
        urls[number] = outputs['url']
        assert deployment.served[-1] == (f'preview-pr-{number}', image, '/')

    state = deployment.state()
    assert set(state['containers']) == {'preview-pr-41', 'preview-pr-42'}
    assert (
        state['containers']['preview-pr-41']['containers'][0]['image']
        == 'ghcr.io/example/app:revision-three'
    )
    assert (
        state['containers']['preview-pr-42']['containers'][0]['image']
        == 'ghcr.io/example/app:revision-two'
    )
    assert urls['41'] != urls['42']
    response = subprocess.run(
        ['curl', '--fail', '--silent', '--show-error', '--noproxy', '*',
         '--max-time', '5', urls['42'] + '/'],
        text=True, capture_output=True, timeout=10,
    )
    assert response.returncode == 0, response.stderr
    assert response.stdout == 'ghcr.io/example/app:revision-two'
    assert deployment.served[-1] == (
        'preview-pr-42', 'ghcr.io/example/app:revision-two', '/',
    )


def test_public_image_deploys_without_registry_credentials(deployment):
    result, outputs = deployment.run(
        REGISTRY_USERNAME=None, REGISTRY_PASSWORD=None,
        IMAGE_REF='ghcr.io/example/public:revision-one',
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert outputs['status'] == 'success'
    assert outputs['url'] == f'http://127.0.0.1:{deployment.port}'
    group = deployment.state()['containers']['preview-pr-41']
    assert 'imageRegistryCredentials' not in group
    assert (
        group['containers'][0]['image']
        == 'ghcr.io/example/public:revision-one'
    )


@pytest.mark.parametrize('overrides, reason', [
    ({'AZURE_CREDENTIALS': None}, 'credential'),
    ({'AZURE_CREDENTIALS': '{bad json'}, 'credential'),
    ({'AZURE_CREDENTIALS': '{}'}, 'credential'),
    ({'REGISTRY_USERNAME': None}, 'registry'),
    ({'REGISTRY_PASSWORD': None}, 'registry'),
    ({'PR_NUMBER': '0'}, 'PR_NUMBER|PR number'),
    ({'PR_NUMBER': '12345678901'}, 'PR_NUMBER|PR number'),
    ({'CONTAINER_PORT': '0'}, 'port'),
    ({'CONTAINER_PORT': '65536'}, 'port'),
    ({'RESOURCE_NAME': 'preview-pr-42'}, 'RESOURCE_NAME|resource name'),
    ({'PREVIEW_DNS_PREFIX': 'Invalid_prefix'}, 'DNS|prefix'),
    ({'IMAGE_REF': None}, 'image'),
    ({'IMAGE_REF': 'ghcr.io/user:secret@example/app:tag'}, 'image'),
    ({'IMAGE_REF': 'ghcr.io/example/app:tag\nother'}, 'image'),
])
def test_invalid_inputs_fail_before_azure(deployment, overrides, reason):
    result, outputs = deployment.run(**overrides)
    assert_failure(result, outputs, reason)
    assert deployment.state()['calls'] == []
    assert deployment.state()['containers'] == {}
    assert deployment.served == []


@pytest.mark.parametrize('command, reason', [
    ('login', 'login|authentication'),
    ('account set', 'subscription'),
    ('group show', 'resource.group|location'),
    ('container list', 'inspect|list|ownership'),
    ('container create', 'create|deploy'),
    ('container show', 'show|inspect|verif'),
])
def test_azure_errors_are_fail_closed_and_redacted(
    deployment, command, reason,
):
    result, outputs = deployment.run(FAKE_AZ_FAILURE=command)
    assert_failure(result, outputs, reason)
    assert deployment.state()['calls'][-1] == command
    assert deployment.served == []
    if command != 'container show':
        assert deployment.state()['containers'] == {}


@pytest.mark.parametrize('fault, reason', [
    ('missing-fqdn', 'FQDN|hostname|DNS'),
    ('wrong-image', 'image|verif'),
    ('failed-provisioning', 'provision|deploy|verif'),
])
def test_unverified_container_never_publishes_url(deployment, fault, reason):
    result, outputs = deployment.run(FAKE_AZ_SHOW_FAULT=fault)
    assert_failure(result, outputs, reason)
    assert deployment.served == []


@pytest.mark.parametrize('tag, value', [
    ('managed-by', 'someone-else'),
    ('pr-number', '42'),
    ('preview-owner', 'other-preview'),
    (None, None),
])
def test_unowned_existing_container_is_not_changed(deployment, tag, value):
    tags = {
        'managed-by': 'cdd-preview',
        'pr-number': '41',
        'preview-owner': 'test-preview',
    }
    if tag is None:
        tags = {}
    else:
        tags[tag] = value
    original = {
        'name': 'preview-pr-41',
        'tags': tags,
        'containers': [{'image': 'ghcr.io/other/app:untouched'}],
    }
    deployment.state_path.write_text(json.dumps({
        'calls': [], 'containers': {'preview-pr-41': original},
    }))
    result, outputs = deployment.run()
    assert_failure(result, outputs, 'owner|tag|managed|belong')
    assert deployment.state()['containers']['preview-pr-41'] == original
    assert 'container create' not in deployment.state()['calls']
    assert deployment.served == []


def test_http_failure_never_publishes_url(deployment):
    deployment.fail_http()
    result, outputs = deployment.run()
    assert_failure(result, outputs, 'HTTP|readiness|ready|health')
    assert deployment.state()['calls'][-1] == 'container show'
    assert deployment.served == []
