'use strict';

const { guard, prNumber } = require('./preview-context.cjs');

async function comment(github, context, number, marker, body) {
  const comments = await github.paginate(github.rest.issues.listComments, {
    ...context.repo, issue_number: number, per_page: 100,
  });
  const existing = comments.find(item => item.user?.login === 'github-actions[bot]'
    && item.user?.type === 'Bot' && item.body?.includes(marker));
  if (existing) {
    await github.rest.issues.updateComment({ ...context.repo, comment_id: existing.id, body });
  } else {
    await github.rest.issues.createComment({ ...context.repo, issue_number: number, body });
  }
}

async function failed(core, channel) {
  const message = `Preview ${channel} publication failed; inspect repository token permissions and retry.`;
  core.error(message);
  core.setFailed(message);
  try {
    await core.summary.addRaw(`${message}\n`).write();
  } catch {
    core.error('Preview reporting summary publication also failed.');
  }
}

async function preview({ github, context, core }) {
  const args = { github, context, core, trigger: 'ci' };
  let action = await guard(args);
  if (action !== 'deploy') return;
  const number = prNumber(process.env.PR_NUMBER);
  const success = process.env.DEPLOY_STATUS === 'success'
    && process.env.DEPLOY_OUTCOME === 'success'
    && process.env.IMAGE_READY === 'true'
    && /^https?:\/\/[^\s]+$/.test(process.env.PREVIEW_URL || '');
  const url = success ? process.env.PREVIEW_URL : '';
  const marker = '<!-- cdd-pr-preview-status -->';
  const runUrl = `${context.serverUrl || 'https://github.com'}/${context.repo.owner}/${context.repo.repo}/actions/runs/${context.runId}`;
  const body = `${marker}\n## PR Preview Deployment Status\n\n`
    + `| Metric | Details |\n| :--- | :--- |\n`
    + `| PR revision | #${number}, commit \`${process.env.COMMIT_SHA}\` |\n`
    + `| Build and image smoke | ${process.env.IMAGE_READY === 'true' ? 'Passed' : 'Failed or incomplete'} |\n`
    + `| Docker image | \`${process.env.IMAGE_REF}\` |\n`
    + `| Preview | ${success ? `🟢 Ready — [${url}](${url})` : '🔴 Failed — no success URL'} |\n\n`
    + `[Workflow run](${runUrl})\n`
    + (success ? '' : '\nApplication checks, image publication or preview deployment failed; see the safe workflow diagnostics.\n');
  // A channel failure does not prevent attempting the other delivery channel.
  try {
    await github.rest.repos.createCommitStatus({
      ...context.repo, sha: process.env.COMMIT_SHA, state: success ? 'success' : 'failure',
      context: 'PR Preview Deployment', description: success ? 'Preview environment is live' : 'Preview build or deployment failed',
      ...(success ? { target_url: url } : {}),
    });
  } catch {
    await failed(core, 'commit-status');
  }
  // Recheck immediately before shared-comment mutation; never overwrite newer work.
  action = await guard(args);
  if (action !== 'deploy') return;
  try {
    await comment(github, context, number, marker, body);
  } catch {
    await failed(core, 'PR-comment');
  }
}

async function cleanup({ github, context, core }) {
  const number = prNumber(process.env.PR_NUMBER);
  const status = process.env.CLEANUP_STATUS;
  const result = process.env.CLEANUP_RESULT;
  const success = status === 'success' && ['deleted', 'not-found'].includes(result)
    && process.env.CLEANUP_OUTCOME === 'success';
  if (!success) core.setFailed('Preview cleanup failed or returned an invalid result.');
  const action = await guard({ github, context, core });
  if (action !== 'cleanup') return;
  const text = success
    ? result === 'deleted' ? 'Preview removed; post-delete absence verified.' : 'Nothing to clean up; resource absence verified.'
    : 'Preview cleanup failed; the owned resource may still be running and billing. See the safe workflow diagnostics.';
  try {
    await comment(github, context, number, '<!-- cdd-pr-cleanup-status -->',
      `<!-- cdd-pr-cleanup-status -->\n${text}\n\nResource: \`preview-pr-${number}\`.`);
  } catch {
    await failed(core, 'cleanup-comment');
  }
}

module.exports = { preview, cleanup };
