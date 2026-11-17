#!/usr/bin/env bash
set -euo pipefail
umask 077

# Member 4: pr-cleanup.yml calls this when a PR closes (merged or not).
# Deletes only preview-pr-<PR_NUMBER>, and only if all three ownership tags set by
# deploy-preview.sh match. Missing group = success (idempotent); everything else
# (bad credentials, no permission, foreign tags, delete that did not stick) = failure.
output_var() {
  if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    printf '%s=%s\n' "$1" "$2" >> "$GITHUB_OUTPUT"
  fi
}

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  if [[ -n "${evidence_path:-}" ]]; then
    python3 "$evidence_helper" finish "$evidence_path" failure "$1" || true
  fi
  output_var status failure
  output_var result ""
  output_var error_message "$1"
  exit 1
}

failure_reason="Preview cleanup failed."
trap 'fail "$failure_reason"' ERR

PR_NUMBER="${PR_NUMBER:-}"
AZURE_RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-cdd-preview-rg}"
PREVIEW_DNS_PREFIX="${PREVIEW_DNS_PREFIX:-}"

evidence_helper="$(dirname "${BASH_SOURCE[0]}")/preview_evidence.py"
evidence_path=$(python3 "$evidence_helper" init cleanup "${PR_NUMBER:-unknown}")
[[ "$PR_NUMBER" =~ ^[1-9][0-9]{0,9}$ ]] || fail "PR_NUMBER must be a positive integer of at most 10 digits."
RESOURCE_NAME="preview-pr-${PR_NUMBER}"
[[ "$PREVIEW_DNS_PREFIX" =~ ^[a-z]([a-z0-9-]{0,28}[a-z0-9])?$ ]] || fail "PREVIEW_DNS_PREFIX must be a lowercase DNS prefix of 1 to 30 characters."
resource_group_pattern='^[a-zA-Z0-9_.()-]{1,90}$'
[[ "$AZURE_RESOURCE_GROUP" =~ $resource_group_pattern ]] || fail "AZURE_RESOURCE_GROUP must be a valid preview resource group name."
[[ -n "${AZURE_CREDENTIALS:-}" ]] || fail "AZURE_CREDENTIALS is required; no preview was removed."

for dependency in python3 az; do
  command -v "$dependency" >/dev/null || fail "Required cleanup command is unavailable: ${dependency}."
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
fi

failure_reason="Unable to prepare temporary Azure CLI configuration."
work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT
# Never change a developer's active subscription or reuse a production login.
export AZURE_CONFIG_DIR="$work_dir/azure"

# Raw CLI errors are never printed; publish only fixed stage diagnostics.
failure_reason="Azure login failed; verify the service principal credentials and tenant."
timeout 120 az login --service-principal --username "$CLIENT_ID" --password="$CLIENT_SECRET" \
  --tenant "$TENANT_ID" --output none >/dev/null 2>"$work_dir/azure-error.log"
failure_reason="Azure subscription selection failed; verify subscriptionId and the scoped role."
timeout 60 az account set --subscription "$SUBSCRIPTION_ID" >/dev/null 2>"$work_dir/azure-error.log"

failure_reason="Preview lookup failed; verify the resource group exists and the role can read container groups."
timeout 60 az container list --resource-group "$AZURE_RESOURCE_GROUP" \
  --query "[?name=='${RESOURCE_NAME}']" --output json >"$work_dir/existing.json" 2>"$work_dir/azure-error.log"

failure_reason="Refusing to delete a container group without matching preview ownership tags."
python3 "$evidence_helper" observe "$evidence_path" "$work_dir/existing.json" "$PREVIEW_DNS_PREFIX"
state=$(python3 - "$work_dir/existing.json" "$PR_NUMBER" "$PREVIEW_DNS_PREFIX" <<'PY'
import json
import sys

with open(sys.argv[1]) as source:
    groups = json.load(source)
if not groups:
    print("none")
    sys.exit(0)
expected = {"managed-by": "cdd-preview", "pr-number": sys.argv[2], "preview-owner": sys.argv[3]}
if len(groups) > 1 or any((groups[0].get("tags") or {}).get(key) != value
                          for key, value in expected.items()):
    sys.exit(1)
print("owned")
PY
)

result=not-found
if [[ "$state" == owned ]]; then
  printf 'Deleting %s from preview resource group %s.\n' "$RESOURCE_NAME" "$AZURE_RESOURCE_GROUP"
  failure_reason="ACI delete failed; verify the scoped role may delete container groups."
  python3 "$evidence_helper" set "$evidence_path" deletion_requested true
  timeout 300 az container delete --resource-group "$AZURE_RESOURCE_GROUP" --name "$RESOURCE_NAME" \
    --yes --output none >/dev/null 2>"$work_dir/azure-error.log"
  failure_reason="Preview still exists after delete; remove it manually (see docs/CI_SECRETS_SETUP.md)."
  remaining=$(timeout 60 az container list --resource-group "$AZURE_RESOURCE_GROUP" \
    --query "[?name=='${RESOURCE_NAME}'].name" --output tsv 2>"$work_dir/azure-error.log")
  if [[ -n "$remaining" ]]; then
    python3 "$evidence_helper" set "$evidence_path" verified_absent false
  fi
  [[ -z "$remaining" ]] || fail "$failure_reason"
  result=deleted
fi

python3 "$evidence_helper" set "$evidence_path" verified_absent true result "\"${result}\""
python3 "$evidence_helper" finish "$evidence_path" success ""
output_var status success
output_var result "$result"
output_var error_message ""
printf 'Cleanup complete for PR #%s: %s.\n' "$PR_NUMBER" "$result"
