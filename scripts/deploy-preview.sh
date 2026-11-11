#!/usr/bin/env bash
set -euo pipefail
umask 077

# Member 3 (Pratham): Member 2 calls this after publishing a revision-pinned image.
output_var() {
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    printf '%s=%s\n' "$1" "$2" >> "$GITHUB_OUTPUT"
  fi
}

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  output_var status failure
  output_var url ""
  output_var error_message "$1"
  exit 1
}

failure_reason="Preview deployment failed."
trap 'fail "$failure_reason"' ERR

PR_NUMBER="${PR_NUMBER:-}"
CONTAINER_PORT="${CONTAINER_PORT:-8080}"
AZURE_RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-cdd-preview-rg}"
PREVIEW_DNS_PREFIX="${PREVIEW_DNS_PREFIX:-}"
IMAGE_REF="${IMAGE_REF:-}"

[[ "$PR_NUMBER" =~ ^[1-9][0-9]{0,9}$ ]] || fail "PR_NUMBER must be a positive integer of at most 10 digits."
[[ "$CONTAINER_PORT" =~ ^[1-9][0-9]{0,4}$ ]] && (( CONTAINER_PORT <= 65535 )) || fail "CONTAINER_PORT must be between 1 and 65535."
[[ "${RESOURCE_NAME:-preview-pr-${PR_NUMBER}}" == "preview-pr-${PR_NUMBER}" ]] || fail "RESOURCE_NAME must equal preview-pr-PR_NUMBER."
RESOURCE_NAME="preview-pr-${PR_NUMBER}"
[[ "$PREVIEW_DNS_PREFIX" =~ ^[a-z]([a-z0-9-]{0,28}[a-z0-9])?$ ]] || fail "PREVIEW_DNS_PREFIX must be a lowercase DNS prefix of 1 to 30 characters."
resource_group_pattern='^[a-zA-Z0-9_.()-]{1,90}$'
[[ "$AZURE_RESOURCE_GROUP" =~ $resource_group_pattern ]] || fail "AZURE_RESOURCE_GROUP must be a valid preview resource group name."
image_pattern='^[a-z0-9.-]+(:[0-9]+)?/[a-z0-9._/-]+(:[A-Za-z0-9_][A-Za-z0-9_.-]*|@sha256:[a-f0-9]{64})$'
[[ "$IMAGE_REF" =~ $image_pattern ]] || fail "IMAGE_REF must be a registry-qualified image with a tag or SHA256 digest."
[[ -n "${AZURE_CREDENTIALS:-}" ]] || fail "AZURE_CREDENTIALS is required; no cloud preview has been deployed."
if [[ -n "${REGISTRY_USERNAME:-}" || -n "${REGISTRY_PASSWORD:-}" ]]; then
  [[ -n "${REGISTRY_USERNAME:-}" && -n "${REGISTRY_PASSWORD:-}" ]] || fail "REGISTRY_USERNAME and REGISTRY_PASSWORD must be provided together."
  [[ "$REGISTRY_USERNAME$REGISTRY_PASSWORD" != *[[:cntrl:]]* ]] || fail "Registry credentials must not contain control characters."
fi

for dependency in python3 az curl; do
  command -v "$dependency" >/dev/null || fail "Required deployment command is unavailable: ${dependency}."
done

failure_reason="AZURE_CREDENTIALS must contain clientId, clientSecret, tenantId and subscriptionId as nonempty single-line strings."
credential_fields=$(python3 - <<'PY'
import json
import os
import sys

try:
    credentials = json.loads(os.environ["AZURE_CREDENTIALS"])
    fields = [credentials[key] for key in ("clientId", "clientSecret", "tenantId", "subscriptionId")]
    if any(not isinstance(value, str) or not value.strip() or
           any(ord(char) < 32 or ord(char) == 127 for char in value) for value in fields):
        sys.exit(1)
except (ValueError, KeyError, TypeError):
    sys.exit(1)
print("\n".join(fields))
PY
)
mapfile -t credentials <<< "$credential_fields"
CLIENT_ID="${credentials[0]}"
CLIENT_SECRET="${credentials[1]}"
TENANT_ID="${credentials[2]}"
SUBSCRIPTION_ID="${credentials[3]}"
if [[ "${GITHUB_ACTIONS:-}" == true ]]; then
  printf '::add-mask::%s\n' "$CLIENT_SECRET"
  if [[ -n "${REGISTRY_PASSWORD:-}" ]]; then
    printf '::add-mask::%s\n' "$REGISTRY_PASSWORD"
  fi
fi

failure_reason="Unable to prepare temporary Azure CLI configuration."
work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT
# Never change a developer's active subscription or reuse a production login.
export AZURE_CONFIG_DIR="$work_dir/azure"

# Raw CLI errors can contain registry credentials; publish only fixed stage diagnostics.
failure_reason="Azure login failed; verify the service principal credentials and tenant."
timeout 120 az login --service-principal --username "$CLIENT_ID" --password="$CLIENT_SECRET" \
  --tenant "$TENANT_ID" --output none >/dev/null 2>"$work_dir/azure-error.log"
failure_reason="Azure subscription selection failed; verify subscriptionId and the scoped role."
timeout 60 az account set --subscription "$SUBSCRIPTION_ID" >/dev/null 2>"$work_dir/azure-error.log"
failure_reason="Preview resource group lookup failed; verify its existence and read permission."
LOCATION=$(timeout 60 az group show --name "$AZURE_RESOURCE_GROUP" --query location --output tsv 2>"$work_dir/azure-error.log")
[[ "$LOCATION" =~ ^[a-z0-9]+$ ]] || fail "Azure returned no valid location for the preview resource group."

failure_reason="Preview ownership lookup failed; verify container group read permission."
timeout 60 az container list --resource-group "$AZURE_RESOURCE_GROUP" \
  --query "[?name=='${RESOURCE_NAME}']" --output json >"$work_dir/existing.json" 2>"$work_dir/azure-error.log"
failure_reason="Refusing to overwrite an existing container group without matching preview ownership tags."
python3 - "$work_dir/existing.json" "$PR_NUMBER" "$PREVIEW_DNS_PREFIX" <<'PY'
import json
import sys

with open(sys.argv[1]) as source:
    groups = json.load(source)
expected = {"managed-by": "cdd-preview", "pr-number": sys.argv[2], "preview-owner": sys.argv[3]}
if len(groups) > 1 or any(any((group.get("tags") or {}).get(key) != value
                            for key, value in expected.items()) for group in groups):
    sys.exit(1)
PY

failure_reason="Unable to prepare the ACI deployment definition."
# The CLI has no DNS reuse-policy flag; its JSON file interface supports the ARM property.
python3 - "$work_dir/group.json" "$RESOURCE_NAME" "$LOCATION" "$IMAGE_REF" "$CONTAINER_PORT" "$PR_NUMBER" "$PREVIEW_DNS_PREFIX" <<'PY'
import json
import os
import sys

path, name, location, image, port, pr_number, prefix = sys.argv[1:]
port = int(port)
definition = {
    "apiVersion": "2021-10-01",
    "type": "Microsoft.ContainerInstance/containerGroups",
    "name": name,
    "location": location,
    "tags": {"managed-by": "cdd-preview", "pr-number": pr_number, "preview-owner": prefix},
    "properties": {
        "osType": "Linux",
        "restartPolicy": "Always",
        "containers": [{
            "name": name,
            "properties": {
                "image": image,
                "ports": [{"port": port, "protocol": "TCP"}],
                "environmentVariables": [{"name": "PORT", "value": str(port)}],
                "resources": {"requests": {"cpu": 1, "memoryInGB": 1}},
            },
        }],
        "ipAddress": {
            "type": "Public",
            "ports": [{"port": port, "protocol": "TCP"}],
            "dnsNameLabel": f"{prefix}-{name}",
            "autoGeneratedDomainNameLabelScope": "ResourceGroupReuse",
        },
    },
}
registry_username = os.environ.get("REGISTRY_USERNAME")
if registry_username:
    definition["properties"]["imageRegistryCredentials"] = [{
        "server": image.split("/")[0],
        "username": registry_username,
        "password": os.environ["REGISTRY_PASSWORD"],
    }]
with open(path, "w") as target:
    json.dump(definition, target)
PY

printf 'Deploying %s in preview resource group %s.\n' "$RESOURCE_NAME" "$AZURE_RESOURCE_GROUP"
failure_reason="ACI create/update failed; check registry pull access, image existence, regional quota and group configuration."
timeout 600 az container create --resource-group "$AZURE_RESOURCE_GROUP" --name "$RESOURCE_NAME" \
  --file "$work_dir/group.json" --output none >/dev/null 2>"$work_dir/azure-error.log"

failure_reason="ACI deployment inspection failed; verify container group read permission."
timeout 60 az container show --resource-group "$AZURE_RESOURCE_GROUP" --name "$RESOURCE_NAME" \
  --output json >"$work_dir/deployed.json" 2>"$work_dir/azure-error.log"
failure_reason="ACI did not report a successful deployment of the requested image with a valid FQDN/IP."
mapfile -t network < <(python3 - "$work_dir/deployed.json" "$IMAGE_REF" <<'PY'
import ipaddress
import json
import re
import sys

with open(sys.argv[1]) as source:
    group = json.load(source)
address = group.get("ipAddress") or {}
fqdn = address.get("fqdn")
ip = address.get("ip")
containers = group.get("containers") or []
if (group.get("provisioningState") != "Succeeded" or len(containers) != 1 or
        containers[0].get("image") != sys.argv[2] or not isinstance(fqdn, str) or
        not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", fqdn)):
    sys.exit(1)
try:
    if ipaddress.ip_address(ip).version != 4:
        sys.exit(1)
except (TypeError, ValueError):
    sys.exit(1)
print(fqdn)
print(ip)
PY
)
[[ "${#network[@]}" -eq 2 ]] || fail "ACI did not report a successful deployment of the requested image with a valid FQDN/IP."
FQDN="${network[0]}"
CONTAINER_IP="${network[1]}"
PREVIEW_URL="http://${FQDN}:${CONTAINER_PORT}"
failure_reason="Preview HTTP readiness failed; check application startup, PORT binding, ACI container logs and public network reachability."
# Runners can have flaky ACI DNS; connect to the known IP while preserving the FQDN Host header.
curl --fail --silent --show-error --noproxy '*' --connect-timeout 5 --max-time 10 \
  --retry 60 --retry-delay 5 --retry-all-errors --output /dev/null \
  --resolve "${FQDN}:${CONTAINER_PORT}:${CONTAINER_IP}" \
  "$PREVIEW_URL/" 2>"$work_dir/http-error.log"

output_var status success
output_var url "$PREVIEW_URL"
output_var error_message ""
printf 'Preview is reachable: %s\n' "$PREVIEW_URL"
