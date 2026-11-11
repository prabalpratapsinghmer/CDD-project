# Member 3 — Pratham: ACI preview hosting

Member 2 publishes revision-tagged images to GHCR; `scripts/deploy-preview.sh` creates or updates one Azure Container Instances (ACI) container group per PR. Deployment is fail-closed: missing credentials, failed provisioning, or failed HTTP readiness fail the workflow. No URL is guessed and image publication alone is not deployment success.

## Trust, isolation, and cost

- Use a **dedicated nonproduction subscription/resource group**, never a production group, credentials, data, or application secrets. This public demo exposes unauthenticated **HTTP**, not HTTPS; do not send sensitive data or treat it as a production service.
- Run only controlled, trusted PRs. The existing workflow checks out PR code, installs its dependencies, runs tests, builds its Dockerfile, and executes its deployment script with secrets. Anyone able to change that code can steal credentials. Do not enable untrusted/fork PR secret access, switch to `pull_request_target` to bypass restrictions, or automatically approve untrusted runs. Fork PRs without secrets cannot deploy and must not be reported as successful previews.
- Every active PR uses a Linux container group with **1 vCPU and 1 GiB memory**, public TCP, and restart policy `Always`. ACI charges for allocated resources while running; check regional capacity, subscription quotas, budget alerts, and current [ACI pricing](https://azure.microsoft.com/en-us/pricing/details/container-instances/). Two concurrent previews need at least 2 vCPU/2 GiB available. This work does not implement automatic expiry or close cleanup; remove recorded demo resources manually until Member 4 delivers cleanup.
- Keep registry tokens read-only and Azure rights resource-group scoped. Never enable broad repository write defaults or PR-review approval permissions merely to deploy: the workflow declares the GitHub token permissions it needs.

## 1. Administrator provisioning

Prerequisites on a trusted workstation: Bash, Python 3, current Azure CLI supporting ACI JSON file deployment, GitHub CLI authenticated to administer repository secrets/variables, and permission to create a service principal, register providers, create the group, and assign roles. Do not enable shell tracing, CLI debug logging, or terminal recording while handling secrets.

```bash
set +x
set -euo pipefail
REPOSITORY="OWNER/REPO"                    # replace
SUBSCRIPTION_ID="YOUR-NONPRODUCTION-SUBSCRIPTION-ID"
RESOURCE_GROUP="cdd-preview-rg"
LOCATION="koreacentral"                   # must be allowed by subscription policy and support ACI
PREVIEW_DNS_PREFIX="yourrepo-preview"      # choose a stable, repository-specific value

az login --output none                    # administrator interactive login
az account set --subscription "$SUBSCRIPTION_ID"

# Student subscriptions can restrict deployment regions. Pick an ACI-supported
# region from this policy (or omit the flag if no such policy exists).
az policy assignment list --scope "/subscriptions/${SUBSCRIPTION_ID}" \
  --disable-scope-strict-match \
  --query "[?displayName=='Allowed resource deployment regions'].parameters.listOfAllowedLocations.value" \
  --output tsv

az provider register --namespace Microsoft.ContainerInstance --wait --output none
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none
SCOPE="/subscriptions/${SUBSCRIPTION_ID}/resourceGroups/${RESOURCE_GROUP}"
```

The deployer needs the built-in **Azure Container Instances Contributor Role**, **not** general `Contributor`, scoped only to this dedicated group. Microsoft's [role definition](https://learn.microsoft.com/en-us/azure/role-based-access-control/built-in-roles/containers#azure-container-instances-contributor-role) explicitly includes:

- `Microsoft.ContainerInstance/containerGroups/*`: group-scoped container list/read/create/update/delete.
- `Microsoft.Resources/subscriptions/resourceGroups/read`: resource-group lookup (including its region); no separate broad Reader/Contributor assignment is needed for `az group show`.

The role does not make the deployer an administrator: provider registration and resource-group creation are administrator setup steps. RBAC assignment propagation can take time.

Create the service principal and stream its credential JSON **directly into the GitHub secret**, never a file or terminal. `subscriptionId` is explicitly inserted so differences in Azure CLI JSON output cannot omit it. The four required credential fields are nonempty single-line strings.

```bash
az ad sp create-for-rbac \
  --name "cdd-preview-deployer" \
  --role "Azure Container Instances Contributor Role" \
  --scopes "$SCOPE" \
  --json-auth --only-show-errors \
| PREVIEW_SUBSCRIPTION_ID="$SUBSCRIPTION_ID" python3 -c '
import json, os, sys
credentials = json.load(sys.stdin)
credentials["subscriptionId"] = os.environ["PREVIEW_SUBSCRIPTION_ID"]
for key in ("clientId", "clientSecret", "tenantId", "subscriptionId"):
    value = credentials[key]
    assert isinstance(value, str) and value.strip()
    assert not any(ord(char) < 32 or ord(char) == 127 for char in value)
json.dump(credentials, sys.stdout)
' | gh secret set AZURE_CREDENTIALS --repo "$REPOSITORY"

printf '%s' "$RESOURCE_GROUP" | gh secret set AZURE_RESOURCE_GROUP --repo "$REPOSITORY"
gh variable set PREVIEW_DNS_PREFIX --body "$PREVIEW_DNS_PREFIX" --repo "$REPOSITORY"

# `create-for-rbac --role` normally assigns this; verify and repair if it did not.
SP_OBJECT_ID=$(az ad sp list --display-name "cdd-preview-deployer" \
  --query "[0].id" --output tsv)
az role assignment create \
  --assignee-object-id "$SP_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Azure Container Instances Contributor Role" \
  --scope "$SCOPE" --output none
az role assignment list --assignee "$SP_OBJECT_ID" --scope "$SCOPE" \
  --include-inherited \
  --query "[?roleDefinitionName=='Azure Container Instances Contributor Role'].scope" \
  --output tsv
```

See the [Azure CLI service-principal reference](https://learn.microsoft.com/en-us/cli/azure/ad/sp#az-ad-sp-create-for-rbac). Do not blindly repeat creation to rotate credentials or leave orphan principals after a failed secret upload: inspect the application/role assignment in the administrator session and rotate its credential through your approved secret-management process. Record principal ID, group scope, credential expiry, and rotation owner, **not** the password. Rotate before expiry and update the GitHub secret through stdin again; revoke old credentials after verification.

`PREVIEW_DNS_PREFIX` is a repository **variable**, not a secret: 1–30 lowercase letters/digits/hyphens, starts with a letter and ends with a letter/digit. Keep it unchanged throughout each PR's lifetime. Use a distinct group/prefix per repository to prevent ownership/name collisions.

## 2. GHCR image access

Member 2 publishes revision-tagged images to GHCR. This repository's `cdd-project` container package is **public**, so ACI pulls the image anonymously. No `REGISTRY_USERNAME`/`REGISTRY_PASSWORD` secrets are needed; the deployment omits `imageRegistryCredentials` when both are empty.

Public images are pullable by anyone. Keep secrets out of the image and build context; the included `.dockerignore` excludes local environments, Git metadata, and test/docs files.

If the package is made private, ACI needs a durable read-only credential because it can restart after the Actions job ends:

1. Use a dedicated bot account with **Read** access to only the intended GHCR package.
2. Create a personal access token **(classic)** with only `read:packages`; authorize organization SSO if required. GitHub Packages does not support fine-grained PATs. See [GitHub's GHCR authentication guidance](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry#authenticating-with-a-personal-access-token-classic).
3. Store the bot login and token without placing the PAT in shell history or command arguments:

```bash
printf '%s' 'YOUR-GHCR-BOT-LOGIN' | gh secret set REGISTRY_USERNAME --repo "$REPOSITORY"
read -rsp 'GHCR read:packages PAT: ' REGISTRY_PASSWORD
printf '\n'
printf '%s' "$REGISTRY_PASSWORD" | gh secret set REGISTRY_PASSWORD --repo "$REPOSITORY"
unset REGISTRY_PASSWORD
```

Set both secrets or neither. Do not use `GITHUB_TOKEN` as the durable registry password; it expires after the job. ACI retains pull credentials in its container-group configuration, so keep resource-group access restricted. Rotate the PAT before expiry or after compromise, update the secret, and redeploy active previews.

## 3. Workflow and script interface

| Input | Source / contract |
| --- | --- |
| `PR_NUMBER` | Required positive integer, at most 10 digits. |
| `IMAGE_REF` | Required registry-qualified image with explicit tag or SHA256 digest, normally `ghcr.io/<owner>/<repo>:pr-<number>-<short_sha>` from Member 2. No embedded credentials, control characters, or whitespace. Do not update previews using the floating PR tag. |
| `AZURE_CREDENTIALS` | Required repository secret JSON containing `clientId`, `clientSecret`, `tenantId`, `subscriptionId` as nonempty single-line strings. No separate `AZURE_SUBSCRIPTION_ID` secret is used. |
| `AZURE_RESOURCE_GROUP` | Existing repository secret interface, optional; defaults to `cdd-preview-rg`. Region is read from this existing group, not hardcoded in the script. |
| `PREVIEW_DNS_PREFIX` | Required repository variable `vars.PREVIEW_DNS_PREFIX`, stable per repository. |
| `REGISTRY_USERNAME`, `REGISTRY_PASSWORD` | Optional repository secrets for durable private image pulls; set both or neither. Omit for the public GHCR package used here. |
| `CONTAINER_PORT` | Optional integer 1–65535, default `8080`; workflow uses `8080`. Exposed TCP port and application `PORT` environment variable. |
| `RESOURCE_NAME` | Optional; if supplied, must equal `preview-pr-${PR_NUMBER}`. No arbitrary deployment target override. |
| `GITHUB_OUTPUT` | Actions-provided output file; set a temporary file path to inspect outputs locally. |

Resource name is always `preview-pr-N`. The DNS label is `${PREVIEW_DNS_PREFIX}-preview-pr-N`, with `ResourceGroupReuse` DNS reuse policy set through `properties.ipAddress.autoGeneratedDomainNameLabelScope` in the ACI JSON definition supplied to `az container create --file` (not an unsupported CLI reuse-policy flag). The actual FQDN is queried from Azure, never constructed from the label/region. The resource is tagged `managed-by=cdd-preview`, `pr-number=N`, `preview-owner=PREFIX`. Existing resources without all three matching tags are refused before mutation. Updates call ACI create/update on the same group/name with the requested revision image: no delete/recreate path. Keep name, region, prefix, port, and resource configuration stable for same-PR updates; an ACI configuration-change rejection is a failure, not permission to delete the group.

| Result | Process / `GITHUB_OUTPUT` behavior |
| --- | --- |
| Success | Exit 0, `status=success`, `url=http://<actual-Azure-FQDN>:<port>`, empty `error_message`; only after Azure reports `Succeeded`, the requested image matches, the FQDN is valid, and HTTP GET `/` passes. |
| Failure | Nonzero exit, `status=failure`, empty `url`, fixed single-line non-secret `error_message`. No success URL or cloud-setup success fallback. A failed update may leave the old or partially updated resource: inspect it before retrying/cleanup. |

HTTP readiness uses bounded curl retries (24 retries, 5-second retry delay, 5-second connection timeout, 10-second per-attempt limit). It does not prove application revision content; validate that separately below. The script uses an isolated temporary Azure CLI configuration and removes it on exit, leaving the workstation's active Azure login/subscription unchanged. Raw Azure stderr is suppressed rather than published because it may expose credentials.

The workflow runs the full `pytest -v` suite and `flake8 app.py tests`, preserves Member 2's GHCR tags and status/comment integration, and runs aggregate reporting plus final failure enforcement even after deployment failure. Output values enter the aggregate shell through environment variables, not interpolated shell source.

### Local invocation

Use a trusted checkout and trusted workstation with Bash, Python 3, Azure CLI and curl. Load `AZURE_CREDENTIALS` and the registry credentials into the environment from an approved secret manager; GitHub repository secrets cannot be downloaded back with `gh`. Never paste secrets into a command, commit a `.env`, or use `set -x`.

```bash
set +x
: "${AZURE_CREDENTIALS:?Load service-principal JSON securely first}"
: "${REGISTRY_USERNAME:?Load the bot login first}"
: "${REGISTRY_PASSWORD:?Load its read-only PAT securely first}"
export AZURE_CREDENTIALS REGISTRY_USERNAME REGISTRY_PASSWORD
export PR_NUMBER=123                       # an actual trusted demo PR
export IMAGE_REF="ghcr.io/OWNER/REPO:pr-123-COMMITSHORT" # lowercase owner/repo; actual published tag
export PREVIEW_DNS_PREFIX="yourrepo-preview"
export AZURE_RESOURCE_GROUP="cdd-preview-rg"
export CONTAINER_PORT=8080
export GITHUB_OUTPUT="$(mktemp)"           # outputs contain no credentials
bash scripts/deploy-preview.sh
cat "$GITHUB_OUTPUT"
rm -f "$GITHUB_OUTPUT"
unset AZURE_CREDENTIALS REGISTRY_USERNAME REGISTRY_PASSWORD
```

## 4. Failure diagnosis (trusted administrator session only)

Fixed diagnostics identify the failed stage without printing cloud responses:

| Stage / diagnostic | Administrator action |
| --- | --- |
| Input validation, missing credentials, or unavailable `python3`/`az`/`curl` | Correct the named input/secret or install the dependency; no cloud success is claimed. |
| `Unable to prepare temporary Azure CLI configuration.` | Check temporary-directory permissions/space. |
| `Azure login failed; verify the service principal credentials and tenant.` | Check principal/tenant, expiry, and secret rotation. |
| `Azure subscription selection failed; verify subscriptionId and the scoped role.` | Check the JSON subscription and group-scoped assignment/propagation. |
| `Preview resource group lookup failed; verify its existence and read permission.` / invalid group location | Confirm the dedicated group exists and its region is supported; check role assignment. |
| `Preview ownership lookup failed; verify container group read permission.` | Check scoped container read/list access. |
| `Refusing to overwrite an existing container group without matching preview ownership tags.` | Stop and investigate the collision. Do not retag/delete an unrelated resource to force deployment. |
| `ACI create/update failed; check registry pull access, image existence, regional quota and group configuration.` | Check private package Read access/PAT, published tag, provider registration, regional capacity/quota, and ACI update restrictions. |
| `ACI deployment inspection failed; verify container group read permission.` / deployment did not report requested image with valid FQDN | Inspect provisioning state and events; do not advertise a URL until verification passes. |
| `Preview HTTP readiness failed; check application startup, PORT binding and ACI container logs.` | Check app startup, `0.0.0.0` binding, port, and logs. |

On a **safe local administrator terminal**, select the nonproduction subscription, then inspect only non-secret fields. Do not run these diagnostics on untrusted PR runners, dump full container definitions (registry credentials may be present), use `--debug`, or post raw responses/logs to PR comments:

```bash
az login --output none
az account set --subscription "$SUBSCRIPTION_ID"
az group show --name "$RESOURCE_GROUP" --query '{name:name,location:location}' --output json
az container show --resource-group "$RESOURCE_GROUP" --name "preview-pr-${PR_NUMBER}" \
  --query '{name:name,tags:tags,state:provisioningState,fqdn:ipAddress.fqdn,images:containers[].image,events:containers[].instanceView.events}' \
  --output json
az container logs --resource-group "$RESOURCE_GROUP" --name "preview-pr-${PR_NUMBER}"
```

Application/event logs themselves can contain sensitive data: inspect privately and redact before sharing. Keep raw deploy stderr suppressed in CI rather than attempting unreliable secret redaction.

## 5. Member 4 cleanup handoff and live validation

**Close cleanup is not implemented by Member 3.** Member 4 must use the same subscription, dedicated group, `preview-pr-N` name, and all three ownership tags. Never delete by broad prefix, delete the resource group, or target production. Missing groups should be handled idempotently; ownership/permission failures must remain visible.

The current workflow serializes same-PR runs with workflow-level concurrency:

```yaml
concurrency:
  group: cdd-preview-pr-${{ github.event.pull_request.number || inputs.pr_number || '1' }}
  cancel-in-progress: false
```

Member 4's future close workflow must use **exactly the same group expression**, not a workflow-name-prefixed key, and `cancel-in-progress: false` so cleanup cannot race an active update. GitHub concurrency is not FIFO and keeps at most one pending run, so Member 4 must also guard against stale deployment after PR closure; shared serialization alone is not a closed-PR lifecycle implementation. Different PRs remain independent.

### Two-PR live validation procedure (not observed evidence)

1. Complete provisioning/secrets and confirm quota for two previews. Open two trusted demo PRs A and B with visibly distinct page content. Record both PR numbers, commit SHAs, image references, resource names/tags, Actions run links, actual reported URLs, and HTTP response content/screenshots.
2. Confirm each run is green only after readiness; use the reported URLs to verify A and B display their own content. Record actual Azure `Succeeded` state and requested image for each. URLs must differ between PRs.
3. Push visibly changed content to A. Record its new commit/image and run. Confirm A's **exact URL is unchanged**, its response reflects the new content, and its PR comment/status updates in place. Recheck B's URL, image and content are unchanged. A `200` alone is insufficient revision proof.
4. Record a controlled failure (for example, a nonexistent image via a trusted local invocation) and confirm nonzero exit, failure output, empty URL, and, for workflow failures, red status/no success link. Do not corrupt real credentials or another PR's resource for this exercise.
5. Preserve the non-secret records before cleanup. Stop/finish all runs for each demo PR and ensure no update can be queued. Verify exact ownership before deleting only that PR's container group in a trusted admin session:

```bash
[[ "$PR_NUMBER" =~ ^[1-9][0-9]{0,9}$ ]] || { printf '%s\n' 'Invalid PR number; refusing cleanup.' >&2; exit 1; }
export PR_NUMBER PREVIEW_DNS_PREFIX
set -o pipefail
az container show --resource-group "$RESOURCE_GROUP" --name "preview-pr-${PR_NUMBER}" \
  --query '{name:name,tags:tags}' --output json \
| python3 -c '
import json, os, sys
resource = json.load(sys.stdin)
pr = os.environ["PR_NUMBER"]
expected = {"managed-by": "cdd-preview", "pr-number": pr,
            "preview-owner": os.environ["PREVIEW_DNS_PREFIX"]}
assert resource["name"] == "preview-pr-" + pr
assert all((resource.get("tags") or {}).get(k) == v for k, v in expected.items())
' && az container delete --resource-group "$RESOURCE_GROUP" \
       --name "preview-pr-${PR_NUMBER}" --yes --output none
```

Run separately for A and B; verify their absence and record cleanup outcomes. Do not delete if lookup/tag verification fails. This manual recovery procedure is not close-event automation.

### Current evidence and blockers

No live Azure create/update, private GHCR pull, stable-URL/two-PR validation, or cleanup evidence has been produced in this environment. No cloud credentials/subscription or repository deployment secrets are available; live Azure provisioning and concurrent verification have not been performed. An authorized administrator must provision/configure the cloud, registry credentials, repository secrets, and DNS-prefix variable and execute the procedure above; do not present the procedure, offline tests, or example names as observed cloud proof.

Local verification completed:
- `bash -n scripts/deploy-preview.sh`, `flake8 app.py tests`, and `actionlint .github/workflows/ci.yml` passed.
- `pytest -v`: **31 passed**, covering isolation/update behavior, ownership refusal, validation, credential-safe errors, invalid provisioning/image/FQDN results, and HTTP failure.
- A separate smoke run executed the deployment shell with Azure CLI **2.92.0**'s real JSON-file loader, intercepted Azure requests, and real local HTTP responses. Two simulated groups coexisted; updating PR 31 kept its URL and left PR 32's response unchanged. Failure-reporting shell execution also removed a stale URL while retaining the failure reason.

These checks prove local script/interface behavior only; they do not establish reachable Azure previews, private image pulls, or cloud isolation.
