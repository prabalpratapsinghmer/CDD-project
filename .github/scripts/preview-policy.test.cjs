'use strict';

const test = require('node:test');
const assert = require('node:assert/strict');
const { decidePreviewAction } = require('./preview-policy.cjs');
const sha = 'a'.repeat(40);
const other = 'b'.repeat(40);
const input = { state: 'open', currentSha: sha, expectedSha: sha, trigger: 'ci' };

for (const [name, changes, expected] of [
  ['current open revision deploys', {}, 'deploy'],
  ['superseded open revision skips', { currentSha: other }, 'skip'],
  ['closed current revision reconciles cleanup', { state: 'closed' }, 'cleanup'],
  ['stale after close reconciles cleanup', { state: 'closed', currentSha: other }, 'cleanup'],
  ['close removes a closed preview', { state: 'closed', trigger: 'close' }, 'cleanup'],
  ['reopened close skips cleanup', { trigger: 'close' }, 'skip'],
  ['reopened updated close skips cleanup', { trigger: 'close', currentSha: other }, 'skip'],
  ['manual cleanup removes an open preview', { trigger: 'manual-cleanup' }, 'cleanup'],
  ['manual cleanup removes a closed preview', { state: 'closed', trigger: 'manual-cleanup' }, 'cleanup'],
]) {
  test(name, () => assert.equal(decidePreviewAction({ ...input, ...changes }), expected));
}

for (const [name, changes] of [
  ['unknown state', { state: 'merged' }],
  ['missing state', { state: undefined }],
  ['unknown trigger', { trigger: 'deploy' }],
  ['missing trigger', { trigger: undefined }],
  ['short current SHA', { currentSha: 'abc' }],
  ['missing expected SHA', { expectedSha: undefined }],
  ['uppercase SHA', { expectedSha: 'A'.repeat(40) }],
  ['non-string SHA', { currentSha: 42 }],
  ['extra SHA newline', { expectedSha: `${sha}\n` }],
]) {
  test(`rejects ${name} safely`, () => assert.throws(
    () => decidePreviewAction({ ...input, ...changes }),
    { message: 'Invalid preview policy input.' },
  ));
}
test('rejects omitted input safely', () => assert.throws(
  () => decidePreviewAction(), { message: 'Invalid preview policy input.' },
));
for (const value of [null, false, 7, 'private input', []]) {
  test(`rejects non-object input ${JSON.stringify(value)} safely`, () => assert.throws(
    () => decidePreviewAction(value), { message: 'Invalid preview policy input.' },
  ));
}
