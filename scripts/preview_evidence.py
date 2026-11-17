"""Persistent allowlisted observations; never serialize CLI responses."""
import json
import os
from pathlib import Path
import re
import sys
import tempfile


def record(pr):
    return dict(pr_number=pr, resource_name=f'preview-pr-{pr}', present=None,
                image=None, tags=None, provisioning_state=None, fqdn=None,
                ip=None, http=None, deletion_requested=None,
                verified_absent=None, status=None, result=None, error=None)


def create(operation, prs):
    prs = [pr if re.fullmatch(r'[1-9][0-9]{0,9}', pr) else 'unknown'
           for pr in prs]
    fd, path = tempfile.mkstemp(
        prefix=f'cdd-preview-{operation}-{prs[0]}-', suffix='.json',
        dir=os.getenv('RUNNER_TEMP', '/tmp'))
    os.close(fd)
    data = dict(operation=operation, records=[record(pr) for pr in prs],
                quota=None, status=None, error=None)
    save(path, data)
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as target:
            target.write(f'evidence_path={path}\n')
    return path, data


def save(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + '\n')


def observe(target, group, pr, prefix):
    if not isinstance(group, dict) or group.get('name') != f'preview-pr-{pr}':
        raise ValueError('Preview exact-name lookup failed.')
    target['present'] = True
    expected = {'managed-by': 'cdd-preview', 'pr-number': pr,
                'preview-owner': prefix}
    tags = group.get('tags')
    if (not isinstance(tags, dict) or
            any(tags.get(k) != v for k, v in expected.items())):
        raise ValueError('Preview ownership tags do not match.')
    target['tags'] = expected
    containers = group.get('containers', [])
    if (not isinstance(containers, list) or
            any(not isinstance(item, dict) for item in containers)):
        raise ValueError('Malformed preview containers observation.')
    image = containers[0].get('image') if len(containers) == 1 else None
    if (isinstance(image, str) and
            re.fullmatch(r'[A-Za-z0-9./_:@-]{1,512}', image)):
        target['image'] = image
    state = group.get('provisioningState')
    if state in ('Succeeded', 'Failed', 'Pending', 'Creating', 'Updating',
                 'Deleting', 'Canceled'):
        target['provisioning_state'] = state
    address = group.get('ipAddress') or {}
    if not isinstance(address, dict):
        raise ValueError('Malformed preview network observation.')
    fqdn = address.get('fqdn')
    if (isinstance(fqdn, str) and
            re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?', fqdn)):
        target['fqdn'] = fqdn
    import ipaddress
    try:
        target['ip'] = str(ipaddress.ip_address(address.get('ip')))
    except (ValueError, TypeError):
        pass


def main():
    action, *args = sys.argv[1:]
    if action == 'init':
        print(create(args[0], [args[1]])[0])
        return
    path = args.pop(0)
    data = json.loads(Path(path).read_text())
    target = data['records'][0]
    if action == 'observe':
        groups = json.loads(Path(args[0]).read_text())
        if isinstance(groups, dict):
            groups = [groups]
        if not isinstance(groups, list) or len(groups) > 1:
            raise ValueError('Invalid preview lookup.')
        if groups:
            try:
                observe(target, groups[0], target['pr_number'], args[1])
            finally:
                save(path, data)
        else:
            target['present'] = False
    elif action == 'set':
        for key, value in zip(args[::2], args[1::2]):
            if key not in target:
                raise ValueError('Invalid evidence field.')
            target[key] = json.loads(value)
    elif action == 'finish':
        target['status'], target['error'] = args
        data['status'], data['error'] = args
    save(path, data)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Unable to record sanitized preview evidence.', file=sys.stderr)
        sys.exit(1)
