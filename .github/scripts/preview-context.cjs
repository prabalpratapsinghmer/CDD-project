'use strict';

const { decidePreviewAction } = require('./preview-policy.cjs');
const INVALID = 'Preview context validation failed.';

function prNumber(value) {
  const text = String(value ?? '');
  if (text.length > 10 || text.trim() !== text || !/^[1-9][0-9]{0,9}$/.test(text)) throw new Error(INVALID);
  return Number(text);
}

function validatePr(pr, repository) {
  if (!pr || pr.base?.repo?.full_name?.toLowerCase() !== repository.toLowerCase()
      || pr.head?.repo?.full_name?.toLowerCase() !== repository.toLowerCase()
      || pr.base?.ref !== 'main' || !['open', 'closed'].includes(pr.state)
      || typeof pr.head?.sha !== 'string' || pr.head.sha.length !== 40
      || !/^[a-f0-9]{40}$/.test(pr.head.sha)
      || typeof pr.head.ref !== 'string' || !pr.head.ref
      || /[\r\n\x00]/.test(pr.head.ref)) throw new Error(INVALID);
  return pr;
}

async function readPr(github, context, number) {
  const { data } = await github.rest.pulls.get({ ...context.repo, pull_number: prNumber(number) });
  return validatePr(data, `${context.repo.owner}/${context.repo.repo}`);
}

function image(context, number, sha) {
  return `ghcr.io/${context.repo.owner}/${context.repo.repo}:pr-${number}-${sha.slice(0, 7)}`.toLowerCase();
}

async function resolve({ github, context, core }) {
  const manual = context.eventName === 'workflow_dispatch';
  const inputs = manual ? context.payload.inputs || {} : {};
  const operation = manual ? inputs.operation || 'preview' : 'preview';
  const cleanupMode = inputs.cleanup_mode || 'reconcile';
  const expectation = inputs.expectation || 'both-present';
  if (!['preview', 'verify', 'cleanup'].includes(operation)
      || !['reconcile', 'manual-cleanup'].includes(cleanupMode)
      || !['inventory', 'both-present', 'a-present-b-absent', 'both-absent'].includes(expectation)) {
    throw new Error(INVALID);
  }
  if (manual && operation !== 'verify') {
    const { data } = await github.rest.repos.getCollaboratorPermissionLevel({
      ...context.repo, username: context.actor,
    });
    if (!['write', 'admin'].includes(data.permission)) throw new Error(INVALID);
  }
  const number = prNumber(manual ? inputs.pr_number : context.payload.pull_request?.number);
  const pr = await readPr(github, context, number);
  const expectedSha = manual ? pr.head.sha : context.payload.pull_request?.head?.sha;
  const close = context.payload.action === 'closed';
  const trigger = close || (operation === 'cleanup' && cleanupMode === 'reconcile')
    ? 'close' : operation === 'cleanup' ? 'manual-cleanup' : 'ci';
  let disposition = decidePreviewAction({
    state: pr.state, currentSha: pr.head.sha, expectedSha, trigger,
  });
  // An obsolete PR event must not schedule any credential-bearing job, even if closed.
  if (!manual && expectedSha !== pr.head.sha && !close) disposition = 'skip';
  const values = {
    operation, cleanup_mode: cleanupMode, expectation, trigger,
    pr_number: String(number), commit_sha: pr.head.sha, head_ref: pr.head.ref,
    repository: pr.head.repo.full_name, image: image(context, number, pr.head.sha), disposition,
  };
  if (operation === 'verify') {
    const peerNumber = prNumber(inputs.peer_pr_number);
    if (peerNumber === number) throw new Error(INVALID);
    const peer = await readPr(github, context, peerNumber);
    Object.assign(values, {
      peer_pr_number: String(peerNumber), peer_sha: peer.head.sha,
      peer_image: image(context, peerNumber, peer.head.sha), disposition: 'verify',
    });
  }
  for (const [key, value] of Object.entries(values)) core.setOutput(key, value);
  await core.summary.addHeading('Resolved preview intent')
    .addRaw(`PR #${number}; operation ${operation}; disposition ${values.disposition}.\n`)
    .addRaw(values.disposition === 'skip' ? 'Superseded revision or reopened PR: no preview mutations scheduled.\n' : '')
    .write();
}

async function guard({ github, context, core, trigger = process.env.POLICY_TRIGGER || 'ci' }) {
  const pr = await readPr(github, context, process.env.PR_NUMBER);
  const action = decidePreviewAction({
    state: pr.state, currentSha: pr.head.sha,
    expectedSha: process.env.COMMIT_SHA, trigger,
  });
  core.setOutput('action', action);
  if (action === 'skip') {
    await core.summary.addRaw('Preview mutation skipped: superseded revision or reopened PR.\n').write();
  }
  return action;
}

module.exports = { resolve, guard, readPr, prNumber };
