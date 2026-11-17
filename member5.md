---

## 🛠️ CI/CD Project Runbook & Lifecycle (Member 5 Integration)

### 1. System Architecture & Setup
- **Web App & Container:** Python Flask, packaged via Docker (Member 1).
- **CI/CD Pipeline:** GitHub Actions triggering on PR open/synchronize (Member 2).
- **Preview Hosting:** Azure Container Instances (ACI) generating isolated URLs per PR (Member 3).
- **Automated Cleanup:** Idempotent GitHub Action deleting ACI resources on PR close (Member 4).

### 2. Prerequisites & Secrets Required
To successfully run this pipeline, the following GitHub Repository Secrets must be configured:
- `AZURE_CREDENTIALS`: JSON output containing Azure Service Principal (`clientId`, `clientSecret`, `tenantId`, `subscriptionId`).
- `AZURE_RESOURCE_GROUP`: Target resource group name (Default: `cdd-preview-rg`).

### 3. Local Development Commands
To test the application locally before opening a PR:

docker build -t cdd-demo-app .
docker run --rm -p 8080:8080 cdd-demo-app


### 4. Demo & Acceptance Testing Checklist
This checklist verifies end-to-end integration and concurrent environment isolation:
- [ ] **Trigger CI:** Open a test PR with a visible UI change. Verify GitHub Actions starts the build.
- [ ] **Verify Preview URL:** Once the `deploy-preview` script finishes, click the preview link generated in the PR comments to verify the live change.
- [ ] **Test Isolation (Concurrent PRs):** Open a second PR with a different change. Verify it deploys to a separate URL (`preview-pr-<number>`) without affecting the first PR.
- [ ] **Verify Cleanup:** Close one of the PRs. Wait for the `pr-cleanup.yml` workflow to finish, and confirm via Azure Portal (or CLI) that the specific container group was deleted, while the other active PR remains live.
