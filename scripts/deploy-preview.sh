#!/usr/bin/env bash
set -euo pipefail

# scripts/deploy-preview.sh
# Deployment interface contract between CI (Member 2) and Preview Hosting (Member 3).

output_var() {
  local key="$1"
  local val="$2"
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    echo "${key}=${val}" >> "$GITHUB_OUTPUT"
  fi
}

# Resolve input parameters
PR_NUMBER="${PR_NUMBER:-1}"
CONTAINER_PORT="${CONTAINER_PORT:-8080}"
RESOURCE_NAME="${RESOURCE_NAME:-preview-pr-${PR_NUMBER}}"
AZURE_RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-cdd-preview-rg}"
IMAGE_REF="${IMAGE_REF:-}"

echo "=== PR Preview Deployment Contract ==="
echo "PR Number:        ${PR_NUMBER}"
echo "Resource Name:    ${RESOURCE_NAME}"
echo "Container Port:   ${CONTAINER_PORT}"
echo "Target Image:     ${IMAGE_REF}"
echo "Resource Group:   ${AZURE_RESOURCE_GROUP}"

if [[ -z "${IMAGE_REF}" ]]; then
  echo "ERROR: IMAGE_REF environment variable is required." >&2
  output_var "status" "failure"
  output_var "url" ""
  output_var "error_message" "IMAGE_REF environment variable is required but was empty."
  exit 1
fi

# Check if Azure credentials are provided by Member 3
if [[ -z "${AZURE_CREDENTIALS:-}" ]]; then
  echo "AZURE_CREDENTIALS not set; image built and published. Cloud deployment awaits Member 3 secret configuration."
  PREVIEW_URL="http://${RESOURCE_NAME}.eastus.azurecontainer.io:${CONTAINER_PORT}"
  output_var "status" "pending_cloud_setup"
  output_var "url" "${PREVIEW_URL}"
  output_var "error_message" ""
  exit 0
fi

echo "AZURE_CREDENTIALS detected. Initiating deployment to Azure Container Instances..."

# Mask credentials if running in GitHub Actions
if command -v jq >/dev/null 2>&1; then
  CLIENT_ID=$(echo "${AZURE_CREDENTIALS}" | jq -r '.clientId // .appId // empty')
  CLIENT_SECRET=$(echo "${AZURE_CREDENTIALS}" | jq -r '.clientSecret // .password // empty')
  TENANT_ID=$(echo "${AZURE_CREDENTIALS}" | jq -r '.tenantId // .tenant // empty')
  SUBSCRIPTION_ID=$(echo "${AZURE_CREDENTIALS}" | jq -r '.subscriptionId // empty')
else
  CLIENT_ID=$(python3 -c "import json, os; d=json.loads(os.environ['AZURE_CREDENTIALS']); print(d.get('clientId') or d.get('appId') or '')")
  CLIENT_SECRET=$(python3 -c "import json, os; d=json.loads(os.environ['AZURE_CREDENTIALS']); print(d.get('clientSecret') or d.get('password') or '')")
  TENANT_ID=$(python3 -c "import json, os; d=json.loads(os.environ['AZURE_CREDENTIALS']); print(d.get('tenantId') or d.get('tenant') or '')")
  SUBSCRIPTION_ID=$(python3 -c "import json, os; d=json.loads(os.environ['AZURE_CREDENTIALS']); print(d.get('subscriptionId') or '')")
fi

if [[ -z "${CLIENT_ID}" || -z "${CLIENT_SECRET}" || -z "${TENANT_ID}" ]]; then
  echo "ERROR: AZURE_CREDENTIALS JSON missing required fields (clientId, clientSecret, tenantId)." >&2
  output_var "status" "failure"
  output_var "url" ""
  output_var "error_message" "Malformed AZURE_CREDENTIALS secret: missing required service principal keys."
  exit 1
fi

# Execute deployment and capture output safely
deploy_err_file=$(mktemp)
trap 'rm -f "${deploy_err_file}"' EXIT

if ! az login --service-principal -u "${CLIENT_ID}" -p "${CLIENT_SECRET}" --tenant "${TENANT_ID}" > /dev/null 2>"${deploy_err_file}"; then
  SANITIZED_ERR=$(head -n 5 "${deploy_err_file}" | tr '\n' ' ')
  echo "ERROR: Azure service principal authentication failed: ${SANITIZED_ERR}" >&2
  output_var "status" "failure"
  output_var "url" ""
  output_var "error_message" "Azure login failed: ${SANITIZED_ERR}"
  exit 1
fi

if [[ -n "${SUBSCRIPTION_ID}" ]]; then
  az account set --subscription "${SUBSCRIPTION_ID}" > /dev/null 2>&1 || true
fi

echo "Deploying container group ${RESOURCE_NAME} with image ${IMAGE_REF}..."
if ! az container create \
  --resource-group "${AZURE_RESOURCE_GROUP}" \
  --name "${RESOURCE_NAME}" \
  --image "${IMAGE_REF}" \
  --dns-name-label "${RESOURCE_NAME}" \
  --ports "${CONTAINER_PORT}" \
  --environment-variables PORT="${CONTAINER_PORT}" \
  --output json > /dev/null 2>"${deploy_err_file}"; then
  SANITIZED_ERR=$(head -n 5 "${deploy_err_file}" | tr '\n' ' ')
  echo "ERROR: az container create failed: ${SANITIZED_ERR}" >&2
  output_var "status" "failure"
  output_var "url" ""
  output_var "error_message" "ACI deployment failed: ${SANITIZED_ERR}"
  exit 1
fi

FQDN=$(az container show --resource-group "${AZURE_RESOURCE_GROUP}" --name "${RESOURCE_NAME}" --query "ipAddress.fqdn" -o tsv 2>/dev/null || true)
if [[ -z "${FQDN}" || "${FQDN}" == "null" ]]; then
  FQDN="${RESOURCE_NAME}.eastus.azurecontainer.io"
fi

PREVIEW_URL="http://${FQDN}:${CONTAINER_PORT}"
echo "Deployment successful: ${PREVIEW_URL}"
output_var "status" "success"
output_var "url" "${PREVIEW_URL}"
output_var "error_message" ""
