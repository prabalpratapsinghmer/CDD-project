# CDD Project Demo Application

## Interactive project dashboard

The Flask root route serves `templates/dashboard.html`: a self-contained project
overview, not live GitHub or Azure monitoring. Explore the six-stage pipeline,
architecture, preview lifecycle and safety constraints, or search the six resource
cards for commands and configuration names. Copy controls use the Clipboard API
when available and select command text for manual copying otherwise.

Install dependencies and start the application directly:

```bash
python -m pip install -r requirements.txt
python app.py
```

Open `http://localhost:8080` (or set `PORT` to an available port). No frontend build,
external assets, credentials, or sibling reference files are needed. JavaScript
enhances navigation, disclosures, search, and copy; without it, all project details
and commands remain readable. The decorative WebGL hero falls back to CSS artwork
when unavailable and respects reduced-motion preferences.

## Local Run Instructions

### 1. Build the Docker Image
```bash
docker build -t cdd-demo-app .
```

### 2. Run the Container
```bash
docker run -p 8080:8080 cdd-demo-app
```
Access the application at `http://localhost:8080`.

The production base is pinned to the Python 3.11 slim manifest digest in
`Dockerfile`. `requirements.txt` freezes the resolved application, test and lint
distributions; local, container and CI installation use that same file without
separate unlocked tool installations. To override the container port:

```bash
docker run -e PORT=8090 -p 8080:8090 cdd-demo-app
```

### What the page shows
The server-rendered **Preview revision** panel shows the supplied PR number, full
commit SHA, branch and image tag, with links to the PR, commit and CI run when
provided. Metadata is escaped as text, not rendered as HTML. `ci.yml` supplies the
seven Docker build args (`PR_NUMBER`, `COMMIT_SHA`, `BRANCH`, `BUILD_TIME`,
`RUN_URL`, `REPO_URL`, `IMAGE_TAG`); the Dockerfile exposes them as environment
variables and `app.py` passes their real values to the dashboard. Without both a
PR number and commit SHA, the panel says “Local development — CI revision metadata
unavailable.” Partial metadata is still shown when supplied; no revision values
are invented.

`/api/info` preserves all seven build fields plus the actual hostname,
process start time and uptime in JSON. The dashboard does not display uptime,
health widgets or live-monitoring claims. A plain local build has empty CI
metadata; to simulate a PR:
```bash
docker build -t cdd-demo-app --build-arg PR_NUMBER=7 --build-arg COMMIT_SHA=$(git rev-parse HEAD) --build-arg BRANCH=demo .
```

---

## CI Pipeline & PR Status Automation (Member 2)

This repository includes an automated continuous integration (CI) pipeline implemented in `.github/workflows/ci.yml`.

### Workflow Triggers
- **Pull Requests**: Automatically triggers on `opened`, `synchronize` (new pushes to an open PR), and `reopened` against the `main` branch.
- **Manual Dispatch**: Requires an existing same-repository `pr_number`; `operation` selects `preview` (default), read-only `verify`, or `cleanup`. See the [candidate dispatch commands](docs/CI_SECRETS_SETUP.md#candidate-dispatch-without-merging-main).

### Pipeline Stages

1. **Trusted Context & Validation**:
   - Resolves the PR through GitHub's API before scheduling credentials: main base, same-repository head, current SHA/ref and lifecycle state.
   - Uses `control/` for orchestration and helpers, and `application/` at the resolved PR head for application checks and Docker context. On pull-request events `control/` is checked out from the base branch (`refs/heads/main`), not the PR's merge commit, so a PR's edits to `.github/scripts/` or `scripts/` take effect only after they are merged; on manual dispatch it is the dispatched ref's `github.workflow_sha`. Manual dispatch builds that PR's current head, not the workflow branch's application revision.
   - Locked `requirements.txt` is installed and tested in a digest-pinned `python:3.11-slim` container that receives only a read-only mount of the application.
   - Syntax compilation check (`python -m py_compile app.py`).
   - Linting check (`flake8 app.py tests`).
   - Full automated test suite (`pytest -v`), including deployment-contract tests.

2. **Docker Image Build & Publish**:
   - Uses Docker Buildx with GitHub Container Registry (`ghcr.io`).
   - Authenticates seamlessly using `GITHUB_TOKEN`.
   - Pushes multi-tagged images following strict tagging conventions:
     - `ghcr.io/<owner>/<repo>:pr-<pr_number>` (floating tag for latest PR revision)
     - `ghcr.io/<owner>/<repo>:<commit_sha>` (immutable commit SHA tag)
     - `ghcr.io/<owner>/<repo>:pr-<pr_number>-<short_sha>` (revision-pinned tag used for deployment)
   - Builds a locally loaded production image and requires a bounded 60-second HTTP smoke before publication; metadata and OCI revision labels identify the resolved PR head.

3. **Real PR Preview Hosting (Member 3 — Pratham)**:
   - Invokes `scripts/deploy-preview.sh` after Member 2 publishes the revision-tagged GHCR image.
   - Required inputs: `PR_NUMBER`, registry-qualified `IMAGE_REF`, `AZURE_CREDENTIALS` JSON (`clientId`, `clientSecret`, `tenantId`, `subscriptionId`), and stable repository variable `PREVIEW_DNS_PREFIX`. The GHCR package used here is public, so ACI pulls anonymously and no registry secrets are required; set `REGISTRY_USERNAME` / `REGISTRY_PASSWORD` only if the package is made private.
   - Preserves the optional `AZURE_RESOURCE_GROUP` secret (default `cdd-preview-rg`) and `CONTAINER_PORT` (default `8080`). `RESOURCE_NAME`, if provided, must equal `preview-pr-${PR_NUMBER}`.
   - Creates or updates only the PR's tagged ACI container group in a dedicated nonproduction resource group. Uses Linux, 1 vCPU/1 GiB, public TCP, `Always` restart, and the application `PORT` setting. Reads the group's region from Azure; protected DNS reuse and a stable prefix keep same-PR update addressing consistent.
   - Emits `status=success` and a URL only after verifying Azure provisioning, the requested image, the actual Azure FQDN, and HTTP GET `/` readiness. The URL is public HTTP, not HTTPS; use no sensitive data or application secrets.
   - Missing secrets or any deployment/readiness failure produce a nonzero exit, `status=failure`, an empty `url`, and a fixed non-secret `error_message`. Image publication is not preview success; no placeholder URL or successful cloud-setup fallback exists.

4. **PR Status & In-Place Commenting**:
   - Updates commit-status context `PR Preview Deployment` and a shared PR comment with marker `<!-- cdd-pr-preview-status -->`.
   - Paginates comments and updates only matching `github-actions[bot]` comments, never contributor-authored marker comments.
   - Attempts both status and comment publication; either channel's failure fails reporting visibly. Failed builds/deployments have no success URL.
   - Same-PR mutations serialize under `cdd-preview-pr-<number>` with `cancel-in-progress: false`; this is **not a durable ordered queue**. Different PRs can deploy independently.
   - Rechecks state/head inside the lock and before image publication, deployment and shared reporting. Stale open revisions skip mutations; a run observing a closed PR reconciles cleanup. Close cleanup skips a reopened PR.

5. **PR-Close Cleanup (Member 4)**:
   - `.github/workflows/pr-cleanup.yml` handles closed PRs (merged or not) using trusted base-main cleanup code, never PR-head scripts.
   - Deletes only `preview-pr-<pr_number>` after all three ownership tags match, then verifies absence. Outputs are `status=success,result=deleted|not-found`; failures have `status=failure` and empty result.
   - Cleanup publication failures fail visibly; the bot-owned marker is `<!-- cdd-pr-cleanup-status -->`.
   - Shares the PR mutation lock with CI. Candidate CI also supports permission-checked `cleanup`: `reconcile` skips open PRs; explicit `manual-cleanup` may remove an open PR's owned preview for cost control.
   - Deployment, cleanup and read-only two-PR verification publish only persistent sanitized evidence paths as artifacts/summaries, including observed partial-failure state without inventing success.

Only run previews for **controlled, trusted same-repository PR code**. Separate trusted control checkout does not sandbox application dependencies, tests or Dockerfiles on a credential-bearing runner, and on pull-request events the workflow file itself comes from the PR's merge commit, so anyone who can push a branch to this repository can change what runs with credentials: write access is the trust boundary. Fork previews are rejected; never bypass this using `pull_request_target`. Use only nonproduction resources; ACI previews incur charges. Historical orphan previews require explicit ownership-verified cleanup.

### Secrets and Permissions Configuration
See [Member 3 hosting setup and Member 4 handoff](docs/CI_SECRETS_SETUP.md) for provisioning, least-privilege permissions, script contracts, candidate dispatch, safe diagnostics and two-PR verification. Dated historical live observations are retained there; they do not prove current candidate acceptance or resource presence. Repository secret names exist, but their presence alone does not prove valid Azure access.

The completion candidate (PRs #8 and #10) has since been merged to `main`, so the installed automatic workflows are now the candidate's. To exercise a future change before merging, use the registered CI workflow with an explicit candidate `--ref`; on pull-request events, changes to helpers and scripts take effect only after merge.

See the [completion acceptance record and repeatable demo](docs/ACCEPTANCE_EVIDENCE.md) for full revisions, simultaneous-preview/update isolation, manual-target proof, real failure captures, cleanup evidence, screenshots and run/artifact links. Terminal cleanup is recorded separately in the linked reserved acceptance comment after the pre-cleanup documentation commit; do not infer present resource availability from dated screenshots.
