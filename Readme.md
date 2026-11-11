# CDD Project Demo Application

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

---

## CI Pipeline & PR Status Automation (Member 2)

This repository includes an automated continuous integration (CI) pipeline implemented in `.github/workflows/ci.yml`.

### Workflow Triggers
- **Pull Requests**: Automatically triggers on `opened`, `synchronize` (new pushes to an open PR), and `reopened` against the `main` branch.
- **Manual Dispatch**: Can be triggered manually from the GitHub Actions tab via `workflow_dispatch` with an optional `pr_number` parameter.

### Pipeline Stages

1. **Validation & Testing**:
   - Python 3.11 environment with pip caching.
   - Syntax compilation check (`python -m py_compile app.py`).
   - Linting check (`flake8 app.py tests`).
   - Full automated test suite (`pytest -v`), including deployment-contract tests.

2. **Docker Image Build & Publish**:
   - Uses Docker Buildx with GitHub Container Registry (`ghcr.io`).
   - Authenticates seamlessly using `GITHUB_TOKEN`.
   - Pushes multi-tagged images following strict tagging conventions:
     - `ghcr.io/<owner>/<repo>:pr-<pr_number>` (floating tag for latest PR revision)
     - `ghcr.io/<owner>/<repo>:<commit_sha>` (immutable commit SHA tag)
     - `ghcr.io/<owner>/<repo>:pr-<pr_number>-<short_sha>` (revision-pinned tag)

3. **Real PR Preview Hosting (Member 3 — Pratham)**:
   - Invokes `scripts/deploy-preview.sh` after Member 2 publishes the revision-tagged GHCR image.
   - Required inputs: `PR_NUMBER`, registry-qualified `IMAGE_REF`, `AZURE_CREDENTIALS` JSON (`clientId`, `clientSecret`, `tenantId`, `subscriptionId`), stable repository variable `PREVIEW_DNS_PREFIX`, and repository secrets `REGISTRY_USERNAME` / `REGISTRY_PASSWORD` for durable, read-only private GHCR pulls.
   - Preserves the optional `AZURE_RESOURCE_GROUP` secret (default `cdd-preview-rg`) and `CONTAINER_PORT` (default `8080`). `RESOURCE_NAME`, if provided, must equal `preview-pr-${PR_NUMBER}`.
   - Creates or updates only the PR's tagged ACI container group in a dedicated nonproduction resource group. Uses Linux, 1 vCPU/1 GiB, public TCP, `Always` restart, and the application `PORT` setting. Reads the group's region from Azure; protected DNS reuse and a stable prefix keep same-PR update addressing consistent.
   - Emits `status=success` and a URL only after verifying Azure provisioning, the requested image, the actual Azure FQDN, and HTTP GET `/` readiness. The URL is public HTTP, not HTTPS; use no sensitive data or application secrets.
   - Missing secrets or any deployment/readiness failure produce a nonzero exit, `status=failure`, an empty `url`, and a fixed non-secret `error_message`. Image publication is not preview success; no placeholder URL or successful cloud-setup fallback exists.

4. **PR Status & In-Place Commenting**:
   - Updates GitHub Commit Status Check (`PR Preview Deployment`) with target preview URL.
   - Automatically posts or updates a single markdown table comment on the PR using marker `<!-- cdd-pr-preview-status -->`.
   - Subsequent pushes update the existing comment in-place, eliminating duplicate notification noise.
   - Aggregate reporting and final failure enforcement run even if deployment fails; failed previews have no success URL.
   - Same-PR workflows serialize under `cdd-preview-pr-<number>` with `cancel-in-progress: false`; different PRs can deploy independently.

Only run this secret-bearing workflow for controlled, trusted PR code. Do not expose secrets to untrusted PRs or use production resources. Running previews incur ACI charges. **PR-close cleanup is Member 4's responsibility and is not implemented here**; manually remove verified demo resources until that integration exists.

### Secrets and Permissions Configuration
See [Member 3 hosting setup and Member 4 handoff](docs/CI_SECRETS_SETUP.md) for administrator provisioning, least-privilege Azure permissions, durable private GHCR authentication, the complete script contract, local deployment, safe diagnostics/cleanup, and the two-PR live validation procedure. No cloud credentials/subscription or repository deployment secrets are available here; live Azure provisioning and concurrent verification have not been performed.
