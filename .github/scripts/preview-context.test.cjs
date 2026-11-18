'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { resolve, guard, prNumber } = require('./preview-context.cjs');
const sha = 'a'.repeat(40);
const other = 'b'.repeat(40);

function fixture({ manual = false, inputs = {}, permission = 'write', state = 'open', headSha = sha,
  headRepo = 'owner/repo', baseRepo = 'owner/repo', base = 'main', action = 'synchronize' } = {}) {
  const outputs = {};
  const pr = {
    state, head: { sha: headSha, ref: 'feature/current', repo: { full_name: headRepo } },
    base: { ref: base, repo: { full_name: baseRepo } },
  };
  const github = { rest: {
    pulls: { get: async () => ({ data: pr }) },
    repos: { getCollaboratorPermissionLevel: async () => ({ data: { permission } }) },
  } };
  const summary = { addHeading() { return this; }, addRaw() { return this; }, async write() {} };
  const core = { setOutput: (key, value) => { outputs[key] = value; }, summary };
  const context = {
    repo: { owner: 'owner', repo: 'repo' }, actor: 'contributor',
    eventName: manual ? 'workflow_dispatch' : 'pull_request',
    payload: manual ? { inputs: { pr_number: '42', ...inputs } }
      : { action, pull_request: { number: 42, head: { sha } } },
  };
  return { github, core, context, outputs };
}

for (const value of ['0', '-1', '1.5', '01', '10000000000', '1\n', 'x', '', null]) {
  test(`rejects invalid PR number ${JSON.stringify(value)}`, () => assert.throws(
    () => prNumber(value), { message: 'Preview context validation failed.' },
  ));
}
test('accepts the positive ten-digit boundary', () => assert.equal(prNumber('9999999999'), 9999999999));

test('manual preview resolves the requested PR head, not the workflow SHA', async () => {
  const f = fixture({ manual: true, headSha: other });
  f.context.sha = sha;
  await resolve(f);
  assert.equal(f.outputs.commit_sha, other);
  assert.equal(f.outputs.head_ref, 'feature/current');
  assert.equal(f.outputs.pr_number, '42');
  assert.equal(f.outputs.image, `ghcr.io/owner/repo:pr-42-${other.slice(0, 7)}`);
  assert.equal(f.outputs.disposition, 'deploy');
});

test('stale PR event skips before any mutation job can be scheduled', async () => {
  const f = fixture({ headSha: other });
  await resolve(f);
  assert.equal(f.outputs.disposition, 'skip');
});
test('stale closed CI event also skips at resolution', async () => {
  const f = fixture({ headSha: other, state: 'closed' });
  await resolve(f);
  assert.equal(f.outputs.disposition, 'skip');
});
test('current closed CI event reconciles cleanup', async () => {
  const f = fixture({ state: 'closed' });
  await resolve(f);
  assert.equal(f.outputs.disposition, 'cleanup');
});
test('a close event for a reopened PR skips', async () => {
  const f = fixture({ action: 'closed' });
  await resolve(f);
  assert.equal(f.outputs.disposition, 'skip');
});

for (const changes of [{ headRepo: 'outsider/fork' }, { baseRepo: 'elsewhere/repo' }, { base: 'develop' }]) {
  test(`rejects unsupported PR trust boundary ${JSON.stringify(changes)}`, async () => {
    await assert.rejects(resolve(fixture(changes)), { message: 'Preview context validation failed.' });
  });
}
for (const operation of ['preview', 'cleanup']) {
  for (const permission of ['read', 'triage', 'none']) {
    test(`rejects ${permission} actor manual ${operation}`, async () => {
      await assert.rejects(resolve(fixture({ manual: true, permission, inputs: { operation } })),
        { message: 'Preview context validation failed.' });
    });
  }
}
test('manual cleanup may explicitly remove an open preview', async () => {
  const f = fixture({ manual: true, inputs: { operation: 'cleanup', cleanup_mode: 'manual-cleanup' } });
  await resolve(f);
  assert.equal(f.outputs.disposition, 'cleanup');
  assert.equal(f.outputs.trigger, 'manual-cleanup');
});
test('reconcile does not delete an open preview', async () => {
  const f = fixture({ manual: true, inputs: { operation: 'cleanup' } });
  await resolve(f);
  assert.equal(f.outputs.disposition, 'skip');
});
test('verify resolves both current pinned images without requiring mutation permission', async () => {
  const f = fixture({ manual: true, permission: 'read', inputs: { operation: 'verify', peer_pr_number: '43' } });
  await resolve(f);
  assert.equal(f.outputs.disposition, 'verify');
  assert.equal(f.outputs.peer_image, 'ghcr.io/owner/repo:pr-43-aaaaaaa');
});
test('verify rejects identical PRs', async () => {
  await assert.rejects(resolve(fixture({ manual: true, inputs: { operation: 'verify', peer_pr_number: '42' } })),
    { message: 'Preview context validation failed.' });
});
test('locked guard reconciles a close that arrived after context resolution', async () => {
  const f = fixture({ state: 'closed', headSha: other });
  const saved = { PR_NUMBER: process.env.PR_NUMBER, COMMIT_SHA: process.env.COMMIT_SHA };
  process.env.PR_NUMBER = '42';
  process.env.COMMIT_SHA = sha;
  try {
    assert.equal(await guard({ ...f, trigger: 'ci' }), 'cleanup');
  } finally {
    for (const [key, value] of Object.entries(saved)) {
      if (value === undefined) delete process.env[key]; else process.env[key] = value;
    }
  }
});
