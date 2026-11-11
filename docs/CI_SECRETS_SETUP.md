# CI Pipeline Secrets and Permissions Setup Guide

This document outlines the setup, configuration, and security practices for secrets and credentials required by the CI pipeline (`.github/workflows/ci.yml`) and PR preview deployment interface (`scripts/deploy-preview.sh`).

---

## 1. Overview of Pipeline Secrets

The CI/CD workflow uses a zero-trust credential model. Primary image publishing utilizes GitHub's native Open Container Initiative (OCI) registry (`ghcr.io`), which requires no external secrets. Cloud preview hosting integration requires Azure credentials provided by Member 3.

| Secret Name | Scope / Source | Required? | Purpose |
| :--- | :--- | :--- | :--- |
| `GITHUB_TOKEN` | Automatically provisioned by GitHub Actions | **Yes** (Built-in) | Publishes Docker images to `ghcr.io`, posts status comments to PRs, and updates commit check statuses. |
| `AZURE_CREDENTIALS` | Member 3 (Azure Preview Hosting) | Required for Live Cloud Previews | JSON containing Azure Service Principal credentials for Azure Container Instances (ACI). |
| `AZURE_RESOURCE_GROUP` | Member 3 (Azure Preview Hosting) | Optional (Default: `cdd-preview-rg`) | Target Azure Resource Group where preview containers are deployed. |
| `AZURE_SUBSCRIPTION_ID`| Member 3 (Azure Preview Hosting) | Optional | Azure Subscription ID containing the resource group. |
| `DOCKERHUB_USERNAME` | Repository Secret | Optional | Username if publishing to Docker Hub instead of GHCR. |
| `DOCKERHUB_TOKEN` | Repository Secret | Optional | Personal Access Token (PAT) if publishing to Docker Hub. |

---

## 2. GitHub Token Permissions Configuration

The pipeline requires specific repository-level permissions so `GITHUB_TOKEN` can push Docker packages to `ghcr.io` and write PR comments and status checks.

### Steps to Configure in GitHub:

1. Navigate to your GitHub repository: `https://github.com/<OWNER>/<REPO>`.
2. Click **Settings** (top navigation tab).
3. In the left sidebar, expand **Actions** and select **General**.
4. Scroll down to **Workflow permissions**.
5. Select **Read and write permissions**:
   - Allows GitHub Actions to push packages to GitHub Container Registry.
   - Allows workflows to create and update pull request comments and commit statuses.
6. Check the box **Allow GitHub Actions to approve pull request reviews** if applicable.
7. Click **Save**.

---

## 3. Azure Credentials Setup (Member 3 Hosting Contract)

Member 3 provisions the Azure Container Instances (ACI) environment. To allow CI to deploy preview containers to Azure, create an Azure Active Directory Service Principal with scoped `Contributor` rights over the preview resource group.

### Step 3.1: Azure CLI Creation Command

Run the following command in Azure CLI (replace `<SUBSCRIPTION_ID>` and `<RESOURCE_GROUP>`):

```bash
# Set your target subscription
az account set --subscription "<SUBSCRIPTION_ID>"

# Ensure the preview resource group exists
az group create --name "cdd-preview-rg" --location "eastus"

# Create a scoped Service Principal with Contributor access
az ad sp create-for-rbac \
  --name "cdd-ci-preview-sp" \
  --role "Contributor" \
  --scopes "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/cdd-preview-rg" \
  --json-auth
```

### Step 3.2: Expected JSON Output

The command above outputs a JSON structure similar to:

```json
{
  "clientId": "00000000-0000-0000-0000-000000000000",
  "clientSecret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
  "subscriptionId": "00000000-0000-0000-0000-000000000000",
  "tenantId": "00000000-0000-0000-0000-000000000000",
  "activeDirectoryEndpointUrl": "https://login.microsoftonline.com",
  "resourceManagerEndpointUrl": "https://management.azure.com/",
  "activeDirectoryGraphResourceId": "https://graph.windows.net/",
  "sqlManagementEndpointUrl": "https://management.core.windows.net:8443/",
  "galleryEndpointUrl": "https://gallery.azure.com/",
  "managementEndpointUrl": "https://management.core.windows.net/"
}
```

Copy the entire JSON block (including braces) as the value for the `AZURE_CREDENTIALS` secret.

---

## 4. How to Add Secrets to GitHub Repository

1. Open your GitHub repository in your browser.
2. Click on the **Settings** tab.
3. In the left sidebar under the **Security** section, click **Secrets and variables**, then choose **Actions**.
4. Under the **Repository secrets** section, click **New repository secret**.
5. Add each secret:
   - **Name**: `AZURE_CREDENTIALS`  
     **Secret**: Paste the full JSON output from Step 3.2.
   - **Name**: `AZURE_RESOURCE_GROUP` (optional)  
     **Secret**: `cdd-preview-rg`
6. Click **Add secret** to save.

---

## 5. Fallback Behavior Without Cloud Secrets

The deployment interface (`scripts/deploy-preview.sh`) is designed to handle staging gracefully:
- When `AZURE_CREDENTIALS` is **not set**:
  - The CI workflow still compiles, tests, and builds the container image.
  - The image is pushed to `ghcr.io`.
  - The deployment script detects the absence of Azure credentials and outputs:
    `status=pending_cloud_setup`
    `url=http://preview-pr-<PR_NUMBER>.eastus.azurecontainer.io:8080`
  - The PR comment displays `🟡 Image Published (Pending Cloud Setup)`.
  - The pipeline finishes with exit code `0` (clean pass), ensuring Member 2's validation does not block developers while Member 3 completes cloud provisioning.
- When `AZURE_CREDENTIALS` is **configured**:
  - The deployment script automatically performs service principal login, deploys to Azure Container Instances, retrieves the live FQDN, and updates the PR comment with `🟢 Ready` and the live link.

---

## 6. Security & Best Practices

1. **Zero Hardcoded Secrets**:
   - Never commit API keys, service principal passwords, or tokens into source control.
   - `.gitignore` must ignore `.env`, credentials files, and temporary authentication caches.
2. **Least Privilege Scope**:
   - The Azure Service Principal role is explicitly scoped to `/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/cdd-preview-rg` rather than subscription root.
3. **Log Sanitization**:
   - All deployment scripts mask credentials and capture standard error streams to temporary files.
   - On deployment failure, error outputs are sanitized so raw credentials are never echoed to GitHub Actions logs.
4. **Secret Rotation**:
   - Rotate `AZURE_CREDENTIALS` service principal secrets every 90 days.
   - When rotating, generate a new client secret via `az ad sp credential reset --id <CLIENT_ID>` and update the repository secret in GitHub.
