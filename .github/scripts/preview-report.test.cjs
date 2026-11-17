'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { preview, cleanup } = require('./preview-report.cjs');
const sha = 'a'.repeat(40);

async function scenario(options, run) {
  const changes = {
    PR_NUMBER: '42', COMMIT_SHA: sha, IMAGE_REF: 'ghcr.io/owner/repo:pr-42-aaaaaaa',
    POLICY_TRIGGER: 'ci', IMAGE_READY: 'true', DEPLOY_STATUS: 'success',
    DEPLOY_OUTCOME: 'success', PREVIEW_URL: 'http://preview.example:8080',
    CLEANUP_STATUS: 'success', CLEANUP_RESULT: 'deleted', CLEANUP_OUTCOME: 'success',
    ...options.env,
  };
  const saved = Object.fromEntries(Object.keys(changes).map(key => [key, process.env[key]]));
  Object.assign(process.env, changes);
  const calls = { statuses: [], created: [], updated: [], failures: [], outputs: {}, reads: 0, paginations: 0 };
  const summary = { addRaw() { return this; }, async write() { if (options.summaryFails) throw new Error('private API error'); } };
  const core = {
    summary, setOutput: (key, value) => { calls.outputs[key] = value; },
    error() {}, setFailed: message => calls.failures.push(message),
  };
  const requestError = () => Object.assign(new Error('private API error'), {
    status: options.requestStatus ?? 403,
    response: { data: 'private response', headers: { authorization: 'private token' } },
  });
  const github = { rest: {
    pulls: { get: async () => {
      calls.reads += 1;
      return { data: {
        state: options.closeBeforeComment && calls.reads > 1 ? 'closed' : options.state || 'open',
        base: { ref: 'main', repo: { full_name: 'owner/repo' } },
        head: { sha: options.currentSha || sha, ref: 'feature', repo: { full_name: 'owner/repo' } },
      } };
    } },
    repos: { createCommitStatus: async value => {
      calls.statuses.push(value);
      if (options.statusFails) throw requestError();
    } },
    issues: {
      listComments() {},
      createComment: async value => { calls.created.push(value); if (options.commentFails) throw requestError(); },
      updateComment: async value => { calls.updated.push(value); if (options.commentFails) throw requestError(); },
    },
  }, paginate: async () => {
    calls.paginations += 1;
    if (options.listFails) throw requestError();
    return options.comments || [];
  } };
  const context = { repo: { owner: 'owner', repo: 'repo' }, runId: 123, serverUrl: 'https://github.com' };
  try { await run({ github, context, core }); return calls; } finally {
    for (const [key, value] of Object.entries(saved)) {
      if (value === undefined) delete process.env[key]; else process.env[key] = value;
    }
  }
}

test('ready report includes resolved revision, image and real URL', async () => {
  const calls = await scenario({}, preview);
  assert.equal(calls.statuses[0].sha, sha);
  assert.equal(calls.statuses[0].context, 'PR Preview Deployment');
  assert.equal(calls.statuses[0].target_url, 'http://preview.example:8080');
  assert.match(calls.created[0].body, new RegExp(sha));
  assert.match(calls.created[0].body, /ghcr.io\/owner\/repo:pr-42-aaaaaaa/);
});
test('build/smoke failure clears every success URL', async () => {
  const calls = await scenario({ env: { IMAGE_READY: 'false' } }, preview);
  assert.equal(calls.statuses[0].state, 'failure');
  assert.equal('target_url' in calls.statuses[0], false);
  assert.doesNotMatch(calls.created[0].body, /http:\/\/preview.example/);
});
test('status failure still attempts the comment and visibly fails', async () => {
  const calls = await scenario({ statusFails: true }, preview);
  assert.equal(calls.created.length, 1);
  assert.match(calls.failures[0], /commit-status/);
  assert.doesNotMatch(calls.failures.join(' '), /private API error/);
});
test('comment failure still attempts the status and visibly fails', async () => {
  const calls = await scenario({ commentFails: true }, preview);
  assert.equal(calls.statuses.length, 1);
  assert.match(calls.failures[0], /PR-comment/);
});
test('failure in both delivery channels is recorded separately', async () => {
  const calls = await scenario({ statusFails: true, commentFails: true }, preview);
  assert.equal(calls.statuses.length, 1);
  assert.equal(calls.created.length, 1);
  assert.equal(calls.failures.length, 2);
});
test('reporting summary failure does not suppress the second delivery channel', async () => {
  const calls = await scenario({ statusFails: true, summaryFails: true }, preview);
  assert.equal(calls.created.length, 1);
});
test('paginated marker discovery ignores contributor comments and updates only the Actions bot', async () => {
  const marker = '<!-- cdd-pr-preview-status -->';
  const calls = await scenario({ comments: [
    { id: 1, user: { login: 'contributor', type: 'User' }, body: marker },
    { id: 2, user: { login: 'github-actions[bot]', type: 'Bot' }, body: marker },
  ] }, preview);
  assert.equal(calls.paginations, 1);
  assert.equal(calls.created.length, 0);
  assert.equal(calls.updated[0].comment_id, 2);
});
test('superseded work publishes neither status nor comment', async () => {
  const calls = await scenario({ currentSha: 'b'.repeat(40) }, preview);
  assert.equal(calls.statuses.length, 0);
  assert.equal(calls.created.length, 0);
  assert.equal(calls.outputs.action, 'skip');
});
test('close discovered just before shared comment requests reconciliation instead of overwriting it', async () => {
  const calls = await scenario({ closeBeforeComment: true }, preview);
  assert.equal(calls.created.length, 0);
  assert.equal(calls.outputs.action, 'cleanup');
});
test('unknown successful cleanup result is a failure, never described as absent', async () => {
  const calls = await scenario({ state: 'closed', env: { POLICY_TRIGGER: 'close', CLEANUP_RESULT: 'unknown' } }, cleanup);
  assert.equal(calls.failures.length, 1);
  assert.match(calls.created[0].body, /cleanup failed/);
  assert.doesNotMatch(calls.created[0].body, /absence verified/);
});
test('idempotent not-found result reports verified absence', async () => {
  const calls = await scenario({ state: 'closed', env: { POLICY_TRIGGER: 'close', CLEANUP_RESULT: 'not-found' } }, cleanup);
  assert.equal(calls.failures.length, 0);
  assert.match(calls.created[0].body, /resource absence verified/);
});
test('cleanup comment publication failure fails visibly', async () => {
  const calls = await scenario({ state: 'closed', commentFails: true, env: { POLICY_TRIGGER: 'close' } }, cleanup);
  assert.match(calls.failures[0], /cleanup-comment/);
});
test('reopened close cannot mutate the cleanup comment', async () => {
  const calls = await scenario({ env: { POLICY_TRIGGER: 'close' } }, cleanup);
  assert.equal(calls.created.length, 0);
  assert.equal(calls.statuses.length, 0);
});
test('reopened PR does not hide an invalid cleanup result', async () => {
  const calls = await scenario({ env: { POLICY_TRIGGER: 'close', CLEANUP_RESULT: 'unknown' } }, cleanup);
  assert.equal(calls.failures.length, 1);
  assert.equal(calls.created.length, 0);
});
for (const [stage, options, status] of [
  ['list', { listFails: true }, 403],
  ['create', { commentFails: true }, 422],
  ['update', { commentFails: true, comments: [
    { id: 2, user: { login: 'github-actions[bot]', type: 'Bot' }, body: '<!-- cdd-pr-preview-status -->' },
  ] }, 500],
]) {
  test(`comment ${stage} failure exposes only safe stage and HTTP status`, async () => {
    const calls = await scenario({ ...options, requestStatus: status }, preview);
    assert.equal(calls.statuses.length, 1);
    assert.match(calls.failures[0], new RegExp(`stage=${stage}, HTTP status=${status}`));
    assert.doesNotMatch(calls.failures.join(' '), /private API error|private response|private token/);
  });
}
test('status failure includes a safe channel-specific stage and numerical status', async () => {
  const calls = await scenario({ statusFails: true, requestStatus: 403 }, preview);
  assert.match(calls.failures[0], /stage=create-status, HTTP status=403/);
  assert.equal(calls.created.length, 1);
});
test('non-numerical error status is not exposed', async () => {
  const calls = await scenario({ commentFails: true, requestStatus: 'private status' }, preview);
  assert.match(calls.failures[0], /stage=create, HTTP status=unavailable/);
  assert.doesNotMatch(calls.failures[0], /private status/);
});
test('cleanup comment failure includes safe stage and numerical status', async () => {
  const calls = await scenario({
    state: 'closed', commentFails: true, requestStatus: 403, env: { POLICY_TRIGGER: 'close' },
  }, cleanup);
  assert.match(calls.failures[0], /cleanup-comment.*stage=create, HTTP status=403/);
});
