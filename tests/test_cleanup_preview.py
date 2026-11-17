import json
import os
from pathlib import Path
import re
import subprocess

import pytest


CLEANUP_SCRIPT = (
    Path(__file__).resolve().parents[1] / 'scripts' / 'cleanup-preview.sh'
)
CLIENT_SECRET = 'private-azure-client-secret'
OWNED_TAGS = {
    'managed-by': 'cdd-preview',
    'pr-number': '41',
    'preview-owner': 'test-preview',
}

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
    print('Azure rejected private-azure-client-secret', file=sys.stderr)
    sys.exit(1)


def value(flag):
    return args[args.index(flag) + 1] if flag in args else None


if command in ('login', 'account set'):
    print('{}')
elif command == 'container list':
    query = value('--query')
    match = re.fullmatch(
        r"\[\?name\s*==\s*'([^']+)'\](\.name)?", query)
    records = [
        record for record in state['containers'].values()
        if record['name'] == match.group(1)
    ]
    if match.group(2):
        print('\n'.join(record['name'] for record in records))
    else:
        print(json.dumps(records))
elif command == 'container delete':
    assert '--yes' in args
    name = value('--name')
    # FAKE_AZ_STICKY: Azure reports success but the group survives.
    if not os.environ.get('FAKE_AZ_STICKY'):
        del state['containers'][name]
        state_path.write_text(json.dumps(state))
else:
    raise SystemExit('Unexpected fake az command: ' + command)
'''


@pytest.fixture
def cleanup(tmp_path):
    bin_dir = tmp_path / 'bin'
    bin_dir.mkdir()
    az = bin_dir / 'az'
    az.write_text(FAKE_AZ)
    az.chmod(0o755)
    state_path = tmp_path / 'azure.json'
    groups = {
        f'preview-pr-{number}': {
            'name': f'preview-pr-{number}',
            'tags': dict(OWNED_TAGS, **{'pr-number': number}),
        }
        for number in ('41', '42')
    }
    state_path.write_text(json.dumps({'calls': [], 'containers': groups}))
    credentials = json.dumps({
        'clientId': 'test-client',
        'clientSecret': CLIENT_SECRET,
        'tenantId': 'test-tenant',
        'subscriptionId': 'test-subscription',
    })
    # Never inherit developer/cloud credentials.
    env = {
        'PATH': str(bin_dir) + os.pathsep + os.defpath,
        'HOME': str(tmp_path),
        'FAKE_AZ_STATE': str(state_path),
        'PR_NUMBER': '41',
        'AZURE_CREDENTIALS': credentials,
        'GITHUB_ACTIONS': 'true',
        'PREVIEW_DNS_PREFIX': 'test-preview',
    }
    output_path = tmp_path / 'github-output'

    class Cleanup:
        def run(self, **overrides):
            output_path.write_text('')
            run_env = dict(env, GITHUB_OUTPUT=str(output_path))
            for key, value in overrides.items():
                if value is None:
                    run_env.pop(key, None)
                else:
                    run_env[key] = value
            result = subprocess.run(
                ['bash', str(CLEANUP_SCRIPT)], env=run_env,
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
            return result, outputs

        def state(self):
            return json.loads(state_path.read_text())

        def set_groups(self, groups):
            state_path.write_text(
                json.dumps({'calls': [], 'containers': groups}))

    return Cleanup()


def assert_failure(result, outputs, reason):
    assert result.returncode != 0, result.stdout + result.stderr
    assert outputs.get('status') == 'failure'
    assert not outputs.get('result')
    assert '\n' not in outputs['error_message']
    assert re.search(reason, outputs['error_message'], re.IGNORECASE), outputs


def test_close_deletes_only_that_pr_and_repeat_is_safe(cleanup):
    result, outputs = cleanup.run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert outputs['status'] == 'success'
    assert outputs['result'] == 'deleted'
    assert set(cleanup.state()['containers']) == {'preview-pr-42'}

    # A repeated close event (or a PR that never deployed) is a clean no-op.
    result, outputs = cleanup.run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert outputs['status'] == 'success'
    assert outputs['result'] == 'not-found'
    assert cleanup.state()['calls'].count('container delete') == 1
    assert set(cleanup.state()['containers']) == {'preview-pr-42'}


@pytest.mark.parametrize('tag, value', [
    ('managed-by', 'someone-else'),
    ('pr-number', '42'),
    ('preview-owner', 'other-preview'),
    (None, None),
])
def test_unowned_container_is_never_deleted(cleanup, tag, value):
    tags = {} if tag is None else dict(OWNED_TAGS, **{tag: value})
    original = {'name': 'preview-pr-41', 'tags': tags}
    cleanup.set_groups({'preview-pr-41': original})
    result, outputs = cleanup.run()
    assert_failure(result, outputs, 'owner|tag')
    assert cleanup.state()['containers'] == {'preview-pr-41': original}
    assert 'container delete' not in cleanup.state()['calls']


@pytest.mark.parametrize('command, reason', [
    ('login', 'login|authentication'),
    ('account set', 'subscription'),
    ('container list', 'lookup|permission'),
    ('container delete', 'delete'),
])
def test_azure_errors_fail_visibly_and_redacted(cleanup, command, reason):
    result, outputs = cleanup.run(FAKE_AZ_FAILURE=command)
    assert_failure(result, outputs, reason)
    assert cleanup.state()['calls'][-1] == command
    assert set(cleanup.state()['containers']) == {
        'preview-pr-41', 'preview-pr-42',
    }


def test_delete_that_does_not_stick_is_a_failure(cleanup):
    result, outputs = cleanup.run(FAKE_AZ_STICKY='1')
    assert_failure(result, outputs, 'still exists')


@pytest.mark.parametrize('overrides, reason', [
    ({'AZURE_CREDENTIALS': None}, 'credential'),
    ({'AZURE_CREDENTIALS': '{}'}, 'credential'),
    ({'PR_NUMBER': '0'}, 'PR_NUMBER'),
    ({'PR_NUMBER': '41; rm -rf /'}, 'PR_NUMBER'),
    ({'PREVIEW_DNS_PREFIX': None}, 'prefix'),
])
def test_invalid_inputs_fail_before_azure(cleanup, overrides, reason):
    result, outputs = cleanup.run(**overrides)
    assert_failure(result, outputs, reason)
    assert cleanup.state()['calls'] == []
    assert set(cleanup.state()['containers']) == {
        'preview-pr-41', 'preview-pr-42',
    }
