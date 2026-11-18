# Every Change Gets Its Own Live Link

## Project overview

**Goal:** Let a team safely review each website change before it reaches production. Every pull request (PR) automatically builds and deploys an isolated preview website at a shareable URL. When the PR is merged or closed, its preview is removed.

**Demo approach:** Open a controlled PR, wait for observed readiness, then share its reported preview link. There is no two-minute guarantee: historical first ACI creation took over 15 minutes before reliable FQDN reachability, with warm updates around 2.5–3 minutes. Pre-warm for the presentation and keep workflow, screenshot and cleanup evidence available.

**Historical starting point:** The repository was empty when this guide was first created; that statement is not current status. The integrated implementation now uses Flask, a pinned Python 3.11 Docker base/dependency set, GitHub Actions, GHCR and ACI. See `Readme.md` for the existing container/PORT contract and `docs/CI_SECRETS_SETUP.md` for the current runbook and dated observations. Candidate implementation is reviewed without merging main: main's installed automatic workflows are unchanged until review/merge, and candidate control logic must be exercised using the CI workflow's explicit candidate ref dispatch.

## What the finished system does

1. A contributor opens or updates a PR.
2. CI checks out that PR's exact commit, installs dependencies, runs the project's build/checks, and creates a Docker image tagged with a stable PR identifier and commit SHA.
3. CI pushes the image to a container registry and deploys (or updates) an isolated ACI container group for that PR.
4. The pipeline publishes a stable URL for that PR in the PR's checks/status or comment. The URL should remain the same across updates to that PR, while serving the latest successful commit.
5. A reviewer opens the URL and reviews the change. The PR must show deployment status and a useful failure reason when the build/deploy fails.
6. On PR close, whether merged or not, an automated cleanup job deletes that PR's container group and associated temporary resources. Cleanup must not affect another PR's preview or production.
7. Production deployment, if included, is separate from preview deployment and occurs only through the agreed merge/release workflow.

**Suggested naming:** `preview-pr-<number>` for the ACI group and a URL keyed by PR number. Use a commit SHA for immutable image tags. Do not put credentials in source code, image layers, PR comments, or logs.

## Scope and acceptance criteria

- A new PR gets its own reachable preview without a manual deployment step.
- A second PR gets a distinct preview; deploying it does not replace the first.
- Pushing another commit to a PR updates only that PR's preview.
- The PR exposes the preview URL and a clear deployment result.
- Closing a PR triggers cleanup for both merged and unmerged PRs; repeated cleanup is safe.
- A failed build/deploy is reported as failed and does not publish a misleading successful link.
- No secret values appear in repository files or logs; credentials are configured in the CI provider's secret store.
- The team demonstrates the full open/update/close lifecycle and records the live URL and cleanup result.

## Five team roles

Assign these roles to the five teammates. Replace the labels with names. Agree on interfaces early: the app's build command, Docker image name/port, registry, preview naming convention, and required CI secrets.

### Member 1 — Application and container image

**Owns:** The website that reviewers will see and its Docker packaging.

**Tasks:**
- Choose and implement the small demo website using the team's agreed stack. Include enough visible content to make a PR change easy to recognize during review.
- Provide a reproducible dependency install and production build/start command; document the container's listening port.
- Write a Dockerfile that builds and runs the application with a small, production-appropriate image. Ensure the app binds to `0.0.0.0` and uses the platform-provided port where applicable.
- Test the built image locally: build it, run it, and open the page through its mapped port.
- Coordinate the image/port/build contract with Members 2 and 3. Avoid adding deployment credentials or environment-specific secrets to the app.

**Deliverables:** Working website, Dockerfile, and concise local run instructions. A reviewer can tell which PR change is being previewed.

### Member 2 — CI pipeline and PR status

**Owns:** Automation that builds and validates each PR revision.

**Tasks:**
- Configure the repository's CI workflow to run for PR open, synchronize/update, and reopen events (and any other required lifecycle event).
- Check out the PR's correct commit; install dependencies; run the agreed build and checks; build the Docker image with PR-number and commit-SHA tags.
- Publish the image to the chosen registry using CI-managed credentials, not committed secrets.
- Ensure each PR update targets that PR's preview, and expose deployment outcome and URL as a check/status or PR comment. Avoid duplicate noisy comments; update an existing comment when practical.
- Make failed checks/deployments visible as failures and preserve diagnostic logs without leaking secrets.
- Document required repository secrets and how to configure them.

**Deliverables:** PR workflow, image publishing, visible status/URL integration, and secret setup notes. Member 3 owns the deployment action/interface; agree on inputs and outputs before wiring them together.

### Member 3 — Pratham

**Owns:** Isolated temporary environments and how reviewers reach them.

**Tasks:**
- Set up the selected hosting target. Recommended baseline: Azure Container Instances (ACI), with a container registry accessible to ACI and CI.
- Define deterministic, PR-scoped resource names (for example `preview-pr-<number>`), an externally reachable URL, and the image/port configuration.
- Implement or configure deployment so a new PR creates its environment and a later commit updates only that environment. Keep the preview URL stable for the PR if the platform allows it.
- Provide the deployment interface to Member 2: required inputs (PR number, image reference, port/configuration) and outputs (URL, success/failure). Ensure deployment failure is reported accurately.
- Restrict access to cloud resources and credentials to the minimum needed. Do not use production resources or credentials for previews unless explicitly approved.
- Verify two PRs can run at the same time without overwriting one another.

**Deliverables:** Repeatable preview deployment mechanism, reachable URL, cloud/registry setup instructions, and evidence of concurrent isolated previews.

### Member 4 — PR-close cleanup and lifecycle safety

**Owns:** Reliable deletion of temporary resources and lifecycle edge cases.

**Tasks:**
- Add automation for PR close events, including both merged and unmerged PRs. Ensure it runs when a PR is closed and is not limited to the merge path.
- Delete only resources whose names/metadata identify the closing PR. Never delete another PR's preview or shared registry resources.
- Make cleanup idempotent: a missing resource or repeated close event should finish safely and clearly, not break unrelated jobs.
- Handle permission failures and report cleanup outcome in CI; document any manual recovery procedure for orphaned previews.
- Coordinate resource naming and cloud permissions with Member 3, and workflow event/credential setup with Member 2.
- Exercise close-after-success, close-after-failure/partial-deploy, and repeated cleanup scenarios.

**Deliverables:** Automated cleanup workflow/action, safe resource targeting, and lifecycle test evidence. The preview is gone after the PR closes.

### Member 5 — Integration, documentation, and demo verification

**Owns:** End-to-end acceptance, onboarding documentation, and the presentation flow.

**Tasks:**
- Maintain the shared setup/runbook: architecture, prerequisites, required CI secrets, local app/Docker commands, deployment flow, preview URL behavior, cleanup behavior, and troubleshooting.
- Coordinate contract decisions across Members 1–4 and raise mismatches early; do not independently create a second deployment convention.
- Verify each acceptance criterion using a test PR: create a visible website change, open PR, wait for workflow, open the link, push an update, and close the PR.
- Verify isolation with two simultaneous PRs and confirm closing one does not affect the other. Confirm cleanup removes the closed PR's resource.
- Prepare a short demo checklist with a known-good change and backup evidence (workflow run, URL, and cleanup result) in case cloud provisioning is slow during presentation.
- Record observed failures accurately and help the relevant owner fix them; do not mark the lifecycle complete based only on a green build.

**Deliverables:** Maintained project documentation, acceptance evidence, and a repeatable demo. This role verifies integration; implementation ownership remains with Members 1–4.

## Shared workflow and handoffs

| Stage | Owner | Output / handoff |
| --- | --- | --- |
| Website build and container contract | Member 1 | App build/start commands, Dockerfile, port, locally runnable image |
| PR validation and image publication | Member 2 | CI-built image reference and build result |
| Isolated deployment | Member 3 | PR-specific live URL and deployment result |
| PR close cleanup | Member 4 | PR-specific resource deletion result |
| End-to-end verification and guide | Member 5 | Acceptance evidence and demo checklist |

**Original first-meeting guidance (historical):** assign names; choose the stack, CI, registry and hosting; confirm access/credits and agree interfaces. Those initial selections are now Flask, GitHub Actions, GHCR and ACI. Keep Member 3 identified as Pratham; do not infer other teammates' names. Secret names have been observed, but presence does not establish valid Azure access.

**Integration order:** Member 1 establishes the build/container contract. Members 2 and 3 agree the image and deploy interface. Member 4 uses the same PR resource naming and event lifecycle. Member 5 runs the complete flow only after those interfaces are wired together.

## Demo checklist

- [x] Open implementation A #8 and disposable B #9 with visibly distinct content.
- [x] Demonstrate actual simultaneous owned/current/healthy previews, not just green builds.
- [x] Push a visible A update; prove the exact URL and bot comment ID stay stable while B remains unchanged.
- [x] Select A's candidate workflow but explicitly target B; verify B's full application head across revision surfaces.
- [x] Provision B's deliberate failing image, show real HTTP 503 and fail-visible reporting without a success URL.
- [x] Close B unmerged, distinguish installed-main automatic deletion from candidate behavior, and repeat candidate cleanup with `not-found`.
- [x] Verify A healthy/current and B absent; preserve actual captures and artifact links.
- [ ] Finish the pre-cleanup commit/push and let its final A deployment settle.
- [ ] Intentionally clean A, strictly verify both previews absent, leave A open/unmerged, and publish terminal evidence in the reserved comment; do not push afterward.

For completion-candidate verification, use the exact `preview`, read-only `verify`, and guarded `cleanup` dispatch examples in `docs/CI_SECRETS_SETUP.md`. Verify two current owned images and public URLs, stable same-PR addressing, sibling isolation, fail-visible reporting and repeated deletion. Preserve evidence before removing only the test PR resources. Leave the implementation PR open/unmerged and intentionally remove its billable preview at the end.

The dated [acceptance evidence and repeatable demo](docs/ACCEPTANCE_EVIDENCE.md) records full SHAs, live runs, screenshots, observed failures/recovery, local-versus-cloud proof, and candidate-versus-installed-main limitations. The final terminal addendum belongs in [reserved acceptance comment 6954553166](https://github.com/prabalpratapsinghmer/CDD-project/pull/8#issuecomment-6954553166), updated only after cleanup and strict absence verification are observed. The unchecked terminal items above are deliberately not claimed by this pre-cleanup document.


## Project completion

The project is complete when the acceptance criteria are demonstrated end to end, required setup is documented, and no preview resource remains for a closed PR. Record platform-specific costs/quotas and remove any test resources after the demo.