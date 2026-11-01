# Every Change Gets Its Own Live Link

## Project overview

**Goal:** Let a team safely review each website change before it reaches production. Every pull request (PR) automatically builds and deploys an isolated preview website at a shareable URL. When the PR is merged or closed, its preview is removed.

**Demo promise:** Open a PR, wait about two minutes for the CI/CD pipeline, then share its live preview link with the professor. The link shows that PR's version—not the production site or another PR's build.

**Repository status:** This repository was empty when this guide was created. The team still needs to choose and implement the website, hosting target, and CI/CD provider. The plan below recommends a straightforward Docker + Azure Container Instances (ACI) path; adapt it if course constraints or available credentials require another target. Keep the preview lifecycle and PR behavior the same.

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

### Member 3 — Preview hosting and URL

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

**First team meeting:** assign names; choose the application stack, CI provider, registry, and hosting target; confirm access/credits; agree image name, port, resource naming, URL output, and secrets; split work by the five roles. The suggested Azure path is a recommendation, not a claim that cloud resources or credentials already exist.

**Integration order:** Member 1 establishes the build/container contract. Members 2 and 3 agree the image and deploy interface. Member 4 uses the same PR resource naming and event lifecycle. Member 5 runs the complete flow only after those interfaces are wired together.

## Demo checklist

- [ ] Create a branch with an obvious website change and open a PR.
- [ ] Show the CI build/deploy check running; wait for success and the preview URL (target: about two minutes, dependent on provider and cold-start time).
- [ ] Open the URL and show the PR's change live.
- [ ] Push a second visible change and show the same PR preview updates.
- [ ] Optionally open a second PR and show its distinct URL/content.
- [ ] Close the first PR and show its preview resource is removed while the second preview remains.
- [ ] Show the CI result and documented setup/cleanup path.

## Project completion

The project is complete when the acceptance criteria are demonstrated end to end, required setup is documented, and no preview resource remains for a closed PR. Record platform-specific costs/quotas and remove any test resources after the demo.