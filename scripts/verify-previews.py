#!/usr/bin/env python3
"""Read-only runner acceptance using the documented environment interface."""
import json
import os
import re
import subprocess
import sys
import tempfile

from preview_evidence import create, observe, save


class VerificationError(Exception):
    pass


def command(args, env, stage, json_output=True, timeout=60):
    try:
        result = subprocess.run(args, env=env, capture_output=True, text=True,
                                timeout=timeout)
        if result.returncode:
            raise VerificationError(stage)
        return json.loads(result.stdout) if json_output else result.stdout
    except (OSError, subprocess.TimeoutExpired, ValueError):
        raise VerificationError(stage) from None


def verify():
    prs = [os.getenv('PR_A', ''), os.getenv('PR_B', '')]
    # Never use unchecked input in the evidence filename or Azure query.
    safe = [pr if re.fullmatch(r'[1-9][0-9]{0,9}', pr) else 'unknown'
            for pr in prs]
    path, data = create('verify', safe)
    current = None
    try:
        if safe != prs or prs[0] == prs[1]:
            raise VerificationError(
                'Two distinct positive PR numbers of at most 10 digits '
                'are required.')
        expectation = os.getenv('EXPECTATION', '')
        if expectation not in ('inventory', 'both-present',
                               'a-present-b-absent', 'both-absent'):
            raise VerificationError('Invalid verification expectation.')
        prefix = os.getenv('PREVIEW_DNS_PREFIX', '')
        group = os.getenv('AZURE_RESOURCE_GROUP', '')
        if not re.fullmatch(r'[a-z]([a-z0-9-]{0,28}[a-z0-9])?', prefix):
            raise VerificationError('Invalid preview DNS prefix.')
        if not re.fullmatch(r'[a-zA-Z0-9_.()-]{1,90}', group):
            raise VerificationError('Invalid preview resource group.')
        try:
            creds = json.loads(os.environ['AZURE_CREDENTIALS'])
            fields = [creds[k] for k in (
                'clientId', 'clientSecret', 'tenantId', 'subscriptionId')]
            if any(not isinstance(v, str) or not v.strip() or
                   any(ord(c) < 32 or ord(c) == 127 for c in v)
                   for v in fields):
                raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise VerificationError(
                'Valid Azure service principal credentials are required.'
            ) from None
        with tempfile.TemporaryDirectory(
                prefix='cdd-verify-cli-') as temporary:
            env = dict(os.environ, AZURE_CONFIG_DIR=temporary)
            command(['az', 'login', '--service-principal',
                     '--username', fields[0], '--password=' + fields[1],
                     '--tenant', fields[2], '--output', 'none'],
                    env, 'Azure authentication failed.', False, 120)
            command(['az', 'account', 'set', '--subscription', fields[3]], env,
                    'Azure subscription selection failed.', False)
            location = command(
                ['az', 'group', 'show', '--name', group,
                 '--query', 'location', '--output', 'tsv'],
                env, 'Preview resource group lookup failed.', False).strip()
            if not re.fullmatch(r'[a-z0-9]+', location):
                raise VerificationError(
                    'Invalid preview resource group location.')
            try:
                quota = command(
                    ['az', 'container', 'list-usage', '--location', location,
                     '--output', 'json'],
                    env, 'Quota observation unavailable.')
                if not isinstance(quota, list):
                    raise VerificationError('Quota observation unavailable.')
                data['quota'] = {'status': 'observed', 'limits': [
                    {'current': q.get('currentValue'), 'limit': q.get('limit')}
                    for q in quota if isinstance(q, dict)
                    and isinstance(q.get('currentValue'), (int, float))
                    and isinstance(q.get('limit'), (int, float))]}
            except VerificationError:
                data['quota'] = {'status': 'unavailable', 'limits': None}
            save(path, data)
            for index, pr in enumerate(prs):
                current = data['records'][index]
                groups = command(
                    ['az', 'container', 'list', '--resource-group', group,
                     '--query', f"[?name=='preview-pr-{pr}']",
                     '--output', 'json'],
                    env, 'Preview lookup failed or returned malformed JSON.')
                if not isinstance(groups, list) or len(groups) > 1:
                    raise VerificationError(
                        'Invalid exact-name preview lookup.')
                required = (
                    expectation == 'both-present' or
                    (expectation == 'a-present-b-absent' and index == 0))
                absent = (
                    expectation == 'both-absent' or
                    (expectation == 'a-present-b-absent' and index == 1))
                current['present'] = bool(groups)
                if groups:
                    try:
                        observe(current, groups[0], pr, prefix)
                    except (ValueError, TypeError, AttributeError):
                        raise VerificationError(
                            'Preview exact name or ownership tags '
                            'do not match.') from None
                else:
                    current['verified_absent'] = True
                save(path, data)
                if required and not groups or absent and groups:
                    raise VerificationError(
                        'Preview presence does not match expectation.')
                if groups and required:
                    expected = os.getenv(
                        'EXPECTED_IMAGE_' + ('A' if index == 0 else 'B'), '')
                    if not expected or current['image'] != expected:
                        raise VerificationError(
                            'Preview image does not match current '
                            'expected revision.')
                    if current['provisioning_state'] != 'Succeeded':
                        raise VerificationError(
                            'Preview provisioning has not succeeded.')
                if groups:
                    if not current['fqdn']:
                        raise VerificationError(
                            'Preview has no valid public FQDN.')
                    ports = (
                        (groups[0].get('ipAddress') or {}).get('ports') or [])
                    if (not isinstance(ports, list) or
                            any(not isinstance(item, dict) for item in ports)):
                        raise VerificationError(
                            'Malformed preview public HTTP ports.')
                    port = ports[0].get('port') if len(ports) == 1 else None
                    if not isinstance(port, int) or not 1 <= port <= 65535:
                        raise VerificationError(
                            'Preview has no valid public HTTP port.')
                    try:
                        result = subprocess.run(
                            ['curl', '--silent', '--show-error', '--fail',
                             '--noproxy', '*', '--connect-timeout', '5',
                             '--max-time', '15', '--output', '/dev/null',
                             '--write-out', '%{http_code}',
                             f"http://{current['fqdn']}:{port}/"],
                            env=env, capture_output=True, text=True,
                            timeout=20)
                        code = result.stdout.strip()
                        current['http'] = {'success': result.returncode == 0,
                                           'curl_exit': result.returncode,
                                           'status_code': (
                                               int(code) if re.fullmatch(
                                                   r'[0-9]{3}', code)
                                               else None),
                                           'method': 'public-dns'}
                    except (OSError, subprocess.TimeoutExpired):
                        current['http'] = {
                            'success': False, 'method': 'public-dns',
                            'status_code': None, 'curl_exit': None}
                    save(path, data)
                    if not current['http']['success']:
                        raise VerificationError(
                            'Public preview HTTP probe failed.')
                current['status'] = 'success'
                save(path, data)
        data['status'] = 'success'
        save(path, data)
        return 0
    except (VerificationError, TypeError, AttributeError) as error:
        message = (str(error) if isinstance(error, VerificationError)
                   else 'Malformed preview observation.')
        data['status'], data['error'] = 'failure', message
        if current is not None:
            current['status'], current['error'] = 'failure', message
        save(path, data)
        print(message, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(verify())
