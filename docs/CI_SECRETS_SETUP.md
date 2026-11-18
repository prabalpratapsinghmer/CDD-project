# Member 3 — Pratham: ACI preview hosting

Member 2 publishes revision-tagged images to GHCR; `scripts/deploy-preview.sh` creates or updates one Azure Container Instances (ACI) container group per PR. Deployment is fail-closed: missing credentials, failed provisioning, or failed HTTP readiness fail the workflow. No URL is guessed and image publication alone is not deployment success.

## Trust, isolation, and cost

- Use a **dedicated nonproduction subscription/resource group**, never a production group, credentials, data, or application secrets. This public demo exposes unauthenticated **HTTP**, not HTTPS; do not send sensitive data or treat it as a production service.
- Run only controlled, trusted **same-repository** PRs targeting `main`. The candidate resolves the current PR head through the API and rejects forks before scheduling credentials. It checks out orchestration/helpers into `control/` from the base branch (`refs/heads/main`) on pull-request events, and at `github.workflow_sha` for manual dispatch (which requires write access), separately from `application/` at the resolved PR SHA; a PR's edits to helpers and scripts therefore take effect on pull-request runs only after they are merged. This does **not** sandbox application dependencies, tests or Dockerfiles running on a secret-bearing runner, and on pull-request events the workflow file itself comes from the PR's merge commit, so anyone able to push a branch to this repository can change what runs with credentials: write access is the trust boundary. Never use `pull_request_target` or automatic approval to bypass fork restrictions.
- Every active PR uses a Linux container group with **1 vCPU and 1 GiB memory**, public TCP, and restart policy `Always`. ACI charges for allocated resources while running; check regional capacity, subscription quotas, budget alerts, and current [ACI pricing](https://azure.microsoft.com/en-us/pricing/details/container-instances/). Two concurrent previews need at least 2 vCPU/2 GiB available. There is no automatic expiry: a preview is removed by the PR-close cleanup (section 5) or manually.
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

HTTP readiness uses the ACI public IP with the FQDN Host header (`curl --resolve`) and bounded retries (60 retries, 5-second retry delay, 5-second connection timeout, 10-second per-attempt limit, 900 seconds in total) to cover ACI cold starts and flaky runner DNS; a revision that never answers is therefore reported as failed only after up to 15 minutes. It does not prove application revision content; validate that separately below. The script uses an isolated temporary Azure CLI configuration and removes it on exit, leaving the workstation's active Azure login/subscription unchanged. Raw Azure stderr is suppressed rather than published because it may expose credentials.

The preview job tests/builds from `application/`, uses only `control/` helpers, loads and HTTP-smokes the production image before pushing its three tags, and deploys the revision-pinned tag. State/head are re-fetched after acquiring the mutation lock and immediately before publication, deployment and shared PR reporting. Current build/deploy failures publish no success URL. Reporting paginates marker comments and updates only `github-actions[bot]` comments; contributor-authored markers are never edited. Both commit status and deployment comment publication are attempted, and either channel's failure fails reporting visibly. Cleanup comment publication failures likewise fail the job.

### Candidate dispatch without merging main

The registered **CI** workflow accepts required `pr_number` (positive integer, at most 10 digits), `operation=preview|verify|cleanup` (default `preview`), optional `peer_pr_number` (required and distinct for `verify`), `expectation=inventory|both-present|a-present-b-absent|both-absent` (default `both-present`), and `cleanup_mode=reconcile|manual-cleanup` (default `reconcile`). PR events always select preview. Manual preview and cleanup require repository write/admin permission. All target PRs must exist in this repository with base `main` and same-repository heads.

Select the reviewed candidate branch explicitly. These commands use the integration branch, not `main`; replace `A`/`B` with actual distinct PR numbers before use. The candidate control SHA can differ from either PR's head: application/image metadata always follows the API-resolved target PR head, not the workflow ref.

```bash
REPOSITORY=prabalpratapsinghmer/CDD-project
CANDIDATE=completion/cdd-acceptance-20261117T161744Z
A=123  # replace with actual trusted PR
B=124  # replace with actual trusted peer PR

gh workflow run ci.yml --repo "$REPOSITORY" --ref "$CANDIDATE" \
  -f operation=preview -f pr_number="$A"
gh workflow run ci.yml --repo "$REPOSITORY" --ref "$CANDIDATE" \
  -f operation=verify -f pr_number="$A" -f peer_pr_number="$B" \
  -f expectation=both-present
gh workflow run ci.yml --repo "$REPOSITORY" --ref "$CANDIDATE" \
  -f operation=cleanup -f pr_number="$B" -f cleanup_mode=reconcile
# Explicit cost-control deletion, even if A is open:
gh workflow run ci.yml --repo "$REPOSITORY" --ref "$CANDIDATE" \
  -f operation=cleanup -f pr_number="$A" -f cleanup_mode=manual-cleanup
gh workflow run ci.yml --repo "$REPOSITORY" --ref "$CANDIDATE" \
  -f operation=verify -f pr_number="$A" -f peer_pr_number="$B" \
  -f expectation=both-absent
```

For historical inventory only, use `operation=verify`, `pr_number=6`, `peer_pr_number=4`, `expectation=inventory`; this observes presence without changing resources or assuming old previews still exist. For isolation after B cleanup use `expectation=a-present-b-absent`.

The completion candidate has since been merged to `main` (PRs #8 and #10), so main's installed automatic workflows are now the candidate's. Explicit-ref dispatch remains the way to exercise a future change before it is merged. Acceptance-record rows that describe "installed main" refer to `main` as it was when they were captured (`b60a1cec`).

### Read-only public verifier and sanitized evidence

`scripts/verify-previews.py` receives `PR_A`, `PR_B`, `EXPECTED_IMAGE_A`, `EXPECTED_IMAGE_B`, `EXPECTATION`, `AZURE_CREDENTIALS`, `AZURE_RESOURCE_GROUP`, and `PREVIEW_DNS_PREFIX`. The workflow derives expected revision-tagged images from both API-resolved current PR heads; do not substitute floating tags. Verification has only `contents: read` GitHub token permission, no mutation concurrency group, and does not build, publish, deploy, delete, comment or set commit status.

It targets only exact `preview-pr-N` resources, checks all three ownership tags before exposing image/network details, and probes actual public HTTP URLs **without `--resolve`**. `both-present` requires both current images, successful provisioning and reachable public HTTP; `a-present-b-absent` requires A healthy/current and B absent; `both-absent` requires both absent. `inventory` records observed presence without requiring one of these arrangements. Ownership, image, provisioning, authentication, malformed response or reachability mismatches fail verification. Quota-read permission limits are separate observations; two successful concurrent provisions are the capacity proof.

Cloud helpers publish `evidence_path` before cloud operations, pointing outside disposable CLI directories to `${RUNNER_TEMP:-/tmp}/cdd-preview-<operation>-<PR_NUMBER>-<unique>.json`. Records allowlist observed PR/resource/image/tags/provisioning/FQDN/IP, readiness HTTP result, final status/error and verified post-delete absence; unobserved fields remain null. A readiness failure retains already observed cloud state and actual HTTP failure, but success `url` remains empty. Cleanup failures retain observed targeting/deletion state without claiming absence. CLI temporary credentials/configuration are removed on exit; sanitized evidence persists for `if: always()` artifact and summary publication using only the declared path. Never upload raw Azure responses, credential files, environment dumps or raw login/errors.

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

## 5. Member 4 cleanup and recovery

`.github/workflows/pr-cleanup.yml` handles `pull_request: closed` (merged or not) with trusted base-main code, never PR-head scripts. It rechecks state inside the shared mutation lock and skips a reopened PR. Candidate CI `operation=cleanup` instead selects helpers at the reviewed dispatch workflow SHA after write/admin actor validation: `reconcile` cleans only a currently closed PR; `manual-cleanup` deliberately permits deletion of an open PR's owned preview. Inputs are `PR_NUMBER`, `AZURE_CREDENTIALS`, `AZURE_RESOURCE_GROUP` (default `cdd-preview-rg`) and `PREVIEW_DNS_PREFIX`, which must match `preview-owner`.

| Situation | Outcome (`GITHUB_OUTPUT`: `status`, `result`, `error_message`) |
| --- | --- |
| `preview-pr-N` exists with all three ownership tags | Deleted, then re-listed to prove it is gone: `status=success`, `result=deleted`. |
| No `preview-pr-N` (build failed, repeated close event) | `status=success`, `result=not-found`; no delete is attempted. |
| Group exists but any ownership tag differs | Refused, nothing deleted, `status=failure`, empty `result`. |
| Missing/invalid credentials, login or permission error, delete that does not stick | `status=failure`, empty `result`; the job goes red. Nothing is reported as cleaned unless it verifiably is. |

The cleanup script uses exact-name `az container list` lookup and `az container delete --name preview-pr-N`, then re-lists to verify absence. It never deletes by prefix or deletes the resource group. Reporting uses the bot-owned `<!-- cdd-pr-cleanup-status -->` comment, validates `status=success,result=deleted|not-found` (unknown results fail), and fails visibly if publication fails.

**Serialization, not ordered delivery.** Both mutation workflows use `cdd-preview-pr-<N>` with `cancel-in-progress: false`. GitHub concurrency retains at most one pending job and may replace it; it is not a durable ordered queue. Safety comes from re-fetching lifecycle/head under the lock and before mutations: open/stale CI skips, current open CI deploys, closed CI reconciles ownership-verified cleanup, and automatic/reconcile close cleanup skips if reopened. A close after the final deploy gate is handled by serialized cleanup; manual preview of a closed PR reconciles cleanup rather than recreating it. Explicit `manual-cleanup` remains available for open-PR cost control.

**Previews that predate this workflow** (for example `preview-pr-3`, whose PR closed before cleanup existed) are never cleaned automatically. Delete them with the manual procedure below.

### Historical observed live validation (2026-11-11; later cleanup observation dated separately)

Environment: Azure for Students. The subscription's region policy allowed only `malaysiawest`, `koreacentral`, `eastasia`, `uaenorth`, and `polandcentral`, so previews use `cdd-preview-rg-koreacentral`. The deployer service principal has **Azure Container Instances Contributor** only at that group's scope. The GHCR package is public, so ACI pulls anonymously.

| Check | Observed result |
| --- | --- |
| PR #3 preview | `preview-pr-3` at `http://pratham-cdd-preview-preview-pr-3.fnh7fkg5g4fjf2ba.koreacentral.azurecontainer.io:8080`; HTTP 200; content `Version: Base Setup...`; ACI `Succeeded`; ownership tags matched. |
| Concurrent PR #4 preview | `preview-pr-4` at `http://pratham-cdd-preview-preview-pr-4.f2f6hzbsevddhhc7.koreacentral.azurecontainer.io:8080`; HTTP 200; content `Version: Isolation Test B2...`; ACI `Succeeded`; ownership tags matched. Both groups were listed at the same time. |
| Update isolation | PR #4 was updated from `pr-4-7a84fdb` to `pr-4-8ff6cdb`. Its FQDN stayed the same and its content changed. PR #3's URL and content stayed unchanged. |
| Cleanup | Temporary PR #4 was closed; its ownership tags were verified; only `preview-pr-4` was deleted. `preview-pr-3` remained and served its content. This was manual because close automation is Member 4's deliverable. |
| Failure reporting | Missing/empty credentials and readiness failures produced a nonzero exit, `status=failure`, empty URL, and a fixed diagnostic. An initial cold-start readiness timeout left a running group; the next run recovered it. |
| Automated cleanup script (2026-11-17) | `scripts/cleanup-preview.sh` ran unmodified against real Azure in `cdd-preview-rg-koreacentral` with throwaway groups `preview-pr-9990` (correct tags) and `preview-pr-9991` (foreign `preview-owner`). Closing 9990: `result=deleted`, issued only `container list`/`container delete --name preview-pr-9990`/`container list`. Repeating 9990 and closing never-deployed 9992: `result=not-found`, no delete issued. 9991: refused (`status=failure`), still present. Nonexistent resource group: `status=failure`. `preview-pr-3` was untouched throughout; throwaway groups were removed afterwards. Limits of that local run: service-principal login and the GitHub workflow trigger were not exercised (a pass-through `az` shim skipped only `login` and `account set`). Both were exercised afterwards on GitHub: merging PR #6 (run 44119488568) and closing PR #7 unmerged (run 44229137269) each logged in as the service principal, reported `result=deleted`, posted the 🧹 PR comment and left Azure with no container groups. |

A **first** ACI creation in `koreacentral` took more than 15 minutes before the FQDN was reliably reachable; warm updates took about 2.5–3 minutes. Readiness now connects to the ACI IP with the FQDN Host header and retries up to 60 times (900 seconds in total). Pre-warm a preview before a demo. Runner DNS/public-network reachability was intermittent; the IP probe removes DNS from the readiness path. Azure CLI calls now have timeouts and the preview job has a 40-minute cap.

Public HTTP demo only; do not send sensitive data. ACI groups bill while running. A preview whose PR closed before the cleanup workflow existed (such as `preview-pr-3`) keeps running until you delete it manually.

These are dated historical observations, not a present-time resource inventory or candidate acceptance claim. Repository secret names `AZURE_CREDENTIALS` and `AZURE_RESOURCE_GROUP` and variable `PREVIEW_DNS_PREFIX` were observed during completion discovery; values were not extracted, and names alone do not establish valid credentials or current cloud access. Historical merged PR #6 cleanup run [44119488568](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44119488568) and its [bot deletion report](https://github.com/prabalpratapsinghmer/CDD-project/pull/6#issuecomment-6953200670) are installed-main evidence only, not current Azure absence proof.

### Repeat procedure for future live validation

1. Confirm scoped secrets and quota; inventory historical PRs first using candidate `verify/inventory`. Open two controlled PRs A/B with distinct visible content. Record PR numbers, full SHAs, revision images, tags, run/comment links, actual URLs and screenshots.
2. Dispatch candidate previews as needed; use `verify/both-present` to prove owned/current images, provisioning and actual public HTTP. Open both URLs and verify revision/content; a green build alone is insufficient.
3. Update A and record its new SHA/image, exact stable URL and unchanged bot comment ID. Recheck B's image/content/URL unchanged. Dispatch preview from A's candidate workflow ref targeting B and distinguish workflow SHA from B's resolved head using checkout, OCI labels, page/API, deployed image and status evidence.
4. On disposable B only, exercise the approved cloud-only HTTP failure while leaving local image smoke successful. Record exact failing revision, provisioning/readiness evidence, red status and no success URL; never alter credentials or A for the fault. Close B unmerged, prove automatic B deletion with A healthy, repeat candidate reconcile for `success/not-found`, then use `verify/a-present-b-absent`. Do not move B's failure code into A.
5. Preserve sanitized records/screenshots before deletion. Exercise reconcile against open A to demonstrate it skips; after final documentation commits settle, use candidate `cleanup/manual-cleanup` on A and `verify/both-absent`. Leave A open/unmerged and explain its preview was removed for cost control. Do not push after terminal cleanup because a push can recreate its preview. If dispatched cleanup is unavailable, the trusted administrator recovery below requires exact ownership verification:

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

### Historical additional local verification
- `bash -n scripts/deploy-preview.sh`, `flake8 app.py tests`, and `actionlint .github/workflows/ci.yml` passed.
- `pytest -v`: **33 passed**, covering isolation/update behavior, public and private registry paths, ownership refusal, validation, credential-safe errors, invalid provisioning/image/FQDN/IP results, and HTTP failure.
- A separate smoke run executed the deployment shell with Azure CLI **2.92.0**'s real JSON-file loader, intercepted Azure requests, and real local HTTP responses. Two simulated groups coexisted; updating PR 31 kept its URL and left PR 32's response unchanged. Failure-reporting shell execution also removed a stale URL while retaining the failure reason.

These local checks complement, but do not replace, the live evidence above.
