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
   - Python 3.9 environment with pip caching.
   - Syntax compilation check (`python -m py_compile app.py`).
   - Linting check (`flake8 app.py tests/test_app.py`).
   - Automated unit test suite (`pytest -v tests/test_app.py`).

2. **Docker Image Build & Publish**:
   - Uses Docker Buildx with GitHub Container Registry (`ghcr.io`).
   - Authenticates seamlessly using `GITHUB_TOKEN`.
   - Pushes multi-tagged images following strict tagging conventions:
     - `ghcr.io/<owner>/<repo>:pr-<pr_number>` (floating tag for latest PR revision)
     - `ghcr.io/<owner>/<repo>:<commit_sha>` (immutable commit SHA tag)
     - `ghcr.io/<owner>/<repo>:pr-<pr_number>-<short_sha>` (revision-pinned tag)

3. **Preview Deployment Contract (Member 3 Interface)**:
   - Invokes `scripts/deploy-preview.sh` with standardized environment variables:
     - `PR_NUMBER`: Pull request number.
     - `IMAGE_REF`: Target published container image reference.
     - `CONTAINER_PORT`: Application port (`8080`).
     - `RESOURCE_NAME`: Deterministic preview resource name (`preview-pr-${PR_NUMBER}`).
     - `AZURE_CREDENTIALS`: Scoped Azure Service Principal credentials (configured by Member 3).
     - `AZURE_RESOURCE_GROUP`: Azure Resource Group (`cdd-preview-rg`).
   - Exports `status`, `url`, and `error_message` to GitHub Actions step outputs.
   - Fallback behavior: If `AZURE_CREDENTIALS` is not set, the pipeline marks preview status as `pending_cloud_setup`, publishes the image, and exits cleanly without failing the build.

4. **PR Status & In-Place Commenting**:
   - Updates GitHub Commit Status Check (`PR Preview Deployment`) with target preview URL.
   - Automatically posts or updates a single markdown table comment on the PR using marker `<!-- cdd-pr-preview-status -->`.
   - Subsequent pushes update the existing comment in-place, eliminating duplicate notification noise.

### Secrets and Permissions Configuration
For setup instructions on repository secrets (`AZURE_CREDENTIALS`, `AZURE_RESOURCE_GROUP`) and GitHub token permissions, see [docs/CI_SECRETS_SETUP.md](docs/CI_SECRETS_SETUP.md).
