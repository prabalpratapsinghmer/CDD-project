'use strict';

const INVALID = 'Invalid preview policy input.';

function decidePreviewAction(input = {}) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error(INVALID);
  const { state, currentSha, expectedSha, trigger } = input;
  if (!['open', 'closed'].includes(state)
      || !['ci', 'close', 'manual-cleanup'].includes(trigger)
      || typeof currentSha !== 'string' || currentSha.length !== 40
      || typeof expectedSha !== 'string' || expectedSha.length !== 40
      || !/^[a-f0-9]{40}$/.test(currentSha)
      || !/^[a-f0-9]{40}$/.test(expectedSha)) {
    throw new Error(INVALID);
  }
  if (trigger === 'manual-cleanup') return 'cleanup';
  if (trigger === 'close') return state === 'closed' ? 'cleanup' : 'skip';
  if (state === 'closed') return 'cleanup';
  return currentSha === expectedSha ? 'deploy' : 'skip';
}

module.exports = { decidePreviewAction };
