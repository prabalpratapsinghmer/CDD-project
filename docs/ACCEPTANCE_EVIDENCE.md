# CDD completion acceptance evidence

> **Status (2026-11-18):** PRs #8 and #10 have since been merged to `main`, so passages below that call the candidate "unmerged" or name `b60a1cec` as installed main describe the situation when they were captured. The terminal cleanup and strict both-absent evidence for PRs #8/#9 is in the reserved acceptance comment linked below (cleanup run 44213089612, verification run 44213211514). Independent post-merge observations on 2026-11-18: closing PR #7 unmerged deleted `preview-pr-7` and commented on the PR ([cleanup run 44229137269](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44229137269)), and a read-only `verify` with `expectation=both-absent` for PRs #6 and #7 succeeded ([run 44229364852](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44229364852); sanitized record `docs/evidence/post-merge-both-absent-pr6-pr7.json`). The preview page was later simplified in PR #11; the screenshots and browser checks recorded here show the earlier, denser dashboard.

## Scope and evidence boundary

This record covers the unmerged completion candidate in [implementation PR A #8](https://github.com/prabalpratapsinghmer/CDD-project/pull/8), branch `completion/cdd-acceptance-20261117T161744Z`, and disposable [PR B #9](https://github.com/prabalpratapsinghmer/CDD-project/pull/9), closed unmerged. The original `CDD-project` worktree is preserved; integration uses `CDD-completion`.

The live acceptance below was observed on 2026-11-17; resumed observations are identified separately. Historical local checks are reported from the recovered session, not rerun for this document. Candidate PR-event/manual runs do **not** establish that the proposed automation is installed on `main`. Local tests and simulations do not establish Azure behavior. Screenshots and URLs are dated captures, not promises of present availability.

**Terminal evidence location:** the single reserved [acceptance comment 6954553166](https://github.com/prabalpratapsinghmer/CDD-project/pull/8#issuecomment-6954553166). This file is committed **before** terminal cleanup. Final deployment, intentional A cleanup, strict both-absent verification, artifact links and final PR state must be recorded in that comment after they are observed. This pre-cleanup record does not claim terminal cleanup is complete. No push is permitted after terminal cleanup because it could recreate A.

## Immutable revisions

| Revision | Full SHA | Meaning |
| --- | --- | --- |
| Initial candidate | `a800048db22cb75d5a268da027d9ab43a25db591` | Application, workflow, lifecycle and evidence implementation |
| Reporting correction / A baseline | `92eeadc7acf3ad152331eda3ea8999927d303cd5` | Scoped report permissions and safe channel diagnostics |
| Visible A update | `823f9530c3aca285edb3320944fbd44dfddb6bc9` | “One change. Its own preview.” and initial committed captures |
| Healthy B | `72f9a97506354ab0f12feca857a53e8faceb6270` | Distinct B heading and target-head proof |
| B-only fault | `c697202582939c2e0c14172d774436b34b715890` | Root fails only with nonempty existing runtime `GUNICORN_CMD_ARGS` |
| Final failing B | `7e7e869b985ee23c25ecf202cde79ee60e5ed39e` | Fault plus installed-main close workflow restored for truthful close acceptance |
| Installed main used by automatic close | `b60a1cec07c6b6ca012949970782e689565f0358` | Existing main automation, not the candidate |

The final documentation commit cannot name its own SHA; use PR A's final head and run links in the reserved comment for that immutable revision.

## Run ledger: live candidate versus installed main

All run links belong to `prabalpratapsinghmer/CDD-project`.

| Evidence class | Run | Observed outcome |
| --- | --- | --- |
| Candidate inventory of historical resources | [44128862258](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44128862258) | PR6/PR4 absent; quota lookup separately unavailable. [Artifact 14349047113](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44128862258/artifacts/14349047113), [capture](evidence/historical-pr6-pr4-inventory.json). |
| Candidate B PR event | [44129113807](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44129113807) | Image smoke, publication and cloud readiness passed, but PR-comment publication failed: run red, not end-to-end success. |
| Candidate A events | [44129102904](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44129102904), [44130257165](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44130257165) | A create/update timeout and subsequent failure while owned resource was still Creating. Stale first run skipped shared report mutation. |
| Candidate failed inventory | [44130330206](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44130330206) | A not publicly reachable; B unobserved because verification stopped at A. [Capture](evidence/pr8-incomplete-provisioning-observation.json). |
| Candidate owned partial-A cleanup | [44131738215](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44131738215) | Targeted recovery cleanup succeeded; unrelated resources untouched. |
| Candidate recovered A manual preview | [44131896844](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44131896844) | A provisioned and ready at baseline revision. |
| Candidate strict simultaneous previews | [44133875094](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44133875094) | Both current owned images, Succeeded, actual public-DNS HTTP 200. [Capture](evidence/both-present-baseline.json). |
| Candidate visible A PR update | [44134165854](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44134165854) | New A heading and revision; exact URL and bot comment stable. |
| Candidate strict post-update verification | [44135092275](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44135092275) | Both previews healthy/current; B unchanged. [Capture](evidence/both-present-updated.json). |
| Candidate manual A-selected workflow targeting B | [44130263626](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44130263626), [44135130869](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44135130869) | Application head was B, not orchestration head A; details below. |
| Candidate open-A reconciliation | [44136117556](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44136117556) | Open A deliberately skipped mutation jobs. |
| Candidate deliberate B failure | [44135962036](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44135962036) | Exact failing image provisioned; HTTP 503 made readiness/report red, no success URL. |
| **Installed-main automatic close** | [44137839134](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44137839134) | Closed-unmerged B deletion logged and workflow succeeded. This is not candidate automatic-close proof. |
| Candidate repeated closed-B cleanup; outcome recovered 2026-11-18 | [44137982933](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44137982933) | Success, `result=not-found`, `present=false`, `verified_absent=true`. [Sanitized capture](evidence/pr9-idempotent-cleanup.json). |

Historical merged-close [run 44119488568](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44119488568) for PR6 is prior installed-main evidence only. Installed-main B cleanup logs identify trusted main SHA above, deletion of `preview-pr-9` at `2026-11-17T17:31:11Z`, and `Cleanup complete: deleted` at `17:31:15Z`. That older workflow provided neither a sanitized artifact nor post-delete absence verification. Absence is established separately by candidate repeated cleanup, not retroactively attributed to the older run. [B cleanup report](https://github.com/prabalpratapsinghmer/CDD-project/pull/9#issuecomment-6955765990).

## Simultaneous isolation and visible update

Observed exact addresses:

- A: `http://pratham-cdd-preview-preview-pr-8.bfaqbqdjgwbnbad4.koreacentral.azurecontainer.io:8080`
- B: `http://pratham-cdd-preview-preview-pr-9.d8gefzhjbnffg4h7.koreacentral.azurecontainer.io:8080`

Both strict verifier captures require ownership tags `managed-by=cdd-preview`, `pr-number=8|9`, and `preview-owner=pratham-cdd-preview`; exact current revision image; successful provisioning; and HTTP 200 through public DNS (not a forced DNS mapping). Quota-read access was unavailable independently; successful simultaneous provisioning is the observed capacity proof, not an invented quota limit.

A changed from full SHA `92eeadc7acf3ad152331eda3ea8999927d303cd5` / image `ghcr.io/prabalpratapsinghmer/cdd-project:pr-8-92eeadc` to `823f9530c3aca285edb3320944fbd44dfddb6bc9` / `ghcr.io/prabalpratapsinghmer/cdd-project:pr-8-823f953`. The exact URL remained unchanged and the same [bot deployment comment 6954885487](https://github.com/prabalpratapsinghmer/CDD-project/pull/8#issuecomment-6954885487) was edited. B retained its URL, heading, image `ghcr.io/prabalpratapsinghmer/cdd-project:pr-9-72f9a97`, and full SHA. [Combined isolation proof](evidence/update-isolation-proof.json), [A baseline API](evidence/pr8-baseline-api.json), [A updated API](evidence/pr8-updated-api.json), [B after A update](evidence/pr9-after-a-update-api.json).

## Manual target-head proof

[Combined first proof](evidence/manual-workflow-versus-pr-head.json) records separate trusted-control checkout `92eeadc7acf3ad152331eda3ea8999927d303cd5` and application checkout `72f9a97506354ab0f12feca857a53e8faceb6270`. The repeated run used control `823f9530c3aca285edb3320944fbd44dfddb6bc9` and the same B application SHA ([checkout record](evidence/manual-after-update-checkouts.json)). Pulled OCI revision label, revision-pinned ACI image, rendered preview metadata, API SHA, and B commit status identify B. [B deployment comment 6954742092](https://github.com/prabalpratapsinghmer/CDD-project/pull/9#issuecomment-6954742092), [initial API](evidence/pr9-initial-api.json), [manual API](evidence/pr9-manual-api.json).

**Same-tag caveat:** the existing B ACI instance retained original build/run metadata. Its API/page `run_url` remained initial B run `44129113807`; it did not change to the manual run. Target-head correctness is proved by the revision surfaces, not by claiming every metadata value was regenerated.

## Failure must stay visibly failed

B alone contained the deliberate fault. Normal application/image behavior without a nonempty `GUNICORN_CMD_ARGS` remained HTTP 200; recovered local evidence reports eleven application/fault tests passing. A never received B's fault or test scaffolding.

Live run `44135962036` provisioned `ghcr.io/prabalpratapsinghmer/cdd-project:pr-9-7e7e869` at exact full SHA `7e7e869b985ee23c25ecf202cde79ee60e5ed39e`. Azure reported `Succeeded`, yet root returned actual HTTP **503**. [Readiness evidence](evidence/pr9-readiness-failure.json) preserves image, all ownership tags, network, provisioning state, curl exit **22** and HTTP **503**. Its readiness probe used `ip-resolve`; this is not the strict verifier's public-DNS method. [API capture](evidence/pr9-failing-revision-api.json) retained exact provenance while [root body](evidence/pr9-http503-body.txt) failed. B commit status was `failure`, `target_url=null`, and existing bot comment `6954742092` was updated with failure and no success URL. A remained reachable with its updated heading.

The earlier B comment-publication failure was corrected with scoped `pull-requests: write` and safe diagnostics. Exact original HTTP cause was discarded by the older generic diagnostic, so permission causation is **inference**, not proven root cause.

## Screenshots and local verification provenance

Actual PNG captures, not mockups:

- A before/after: [baseline desktop](evidence/pr8-baseline-desktop.png), [updated desktop](evidence/pr8-updated-desktop.png).
- Responsive A: [390×844](evidence/pr8-baseline-390.png), [768×1024](evidence/pr8-baseline-768.png), [1440×1000](evidence/pr8-baseline-1440.png). Recovered Chromium observations found no horizontal overflow at these widths.
- B: [initial dashboard](evidence/pr9-initial-dashboard.png), [manual-target dashboard](evidence/pr9-manual-dashboard.png), [real deliberate HTTP 503](evidence/pr9-deliberate-http503.png).
- Local production-image [escaped metadata / fallback capture](evidence/docker-metadata-escaping-fallback.png).

Recovered local verification: 81 Python tests, 73 native Node tests, Python compilation/lint and shell syntax checks, and actionlint v1.7.12 passed. Actual production Docker root/API checks passed default 8080 and runtime `PORT=8090` earlier in the session. These are historical local checks, not a claim that the two containers left running at the old session boundary were probed then. Resumed final smoke evidence belongs in the final comment.

Chromium exercised escaped script-like metadata without execution, mobile menu, disclosures, search, clipboard-unavailable manual-copy fallback, readable no-JS panels, reduced motion and WebGL-unavailable CSS fallback. Local missing-credential deploy/cleanup/verifier invocations produced persistent safe failure evidence. Policy/helper tests cover open/reopened/stale decisions; the live stale-A event and open-A reconcile runs above are separate evidence. No live reopen experiment is claimed.


### Resumed local runtime observation (2026-11-18)

The existing final production-image containers were actually probed: root and `/api/info` returned HTTP 200 at `127.0.0.1:32770` → container 8080 and `127.0.0.1:32771` → runtime override 8090. Both identified full SHA `823f9530c3aca285edb3320944fbd44dfddb6bc9`, image tag `pr-8-823f953`, branch `completion/cdd-acceptance-20261117T161744Z`, build time `2026-11-17T17:12:18Z` and run `44134165854`. Seven lowercase build metadata fields plus `hostname`, `started_at`, and `uptime_seconds` were present. Root was 44,394 bytes, SHA-256 `d229c11ca9b7e406ebcafcc45a0f51a2a8b11f8e6f1bc796eea994696d079853`. All three named temporary local verification containers were removed. This is local runtime proof, not cloud terminal-cleanup proof.

The machine-readable [final local container smoke record](evidence/final-local-container-smoke.json) preserves this resumed observation.

Recovered candidate B idempotent-cleanup [artifact 14352553021](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44137982933/artifacts/14352553021) supplies the sanitized `not-found` record linked above.

### Resumed cloud isolation observation (2026-11-18)

Candidate read-only [run 44211103972](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44211103972) succeeded with `expectation=a-present-b-absent`. [Sanitized capture](evidence/a-present-b-absent.json) and [verification artifact 14386590708](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44211103972/artifacts/14386590708) show A owned, exact image `ghcr.io/prabalpratapsinghmer/cdd-project:pr-8-823f953`, provisioning `Succeeded`, public-DNS HTTP 200; B `present=false`, `verified_absent=true`. Quota lookup remained separately unavailable. [Capture bundle artifact 14385149944](https://github.com/prabalpratapsinghmer/CDD-project/actions/runs/44211103972/artifacts/14385149944) preserves the dated acceptance captures. This proves A survived B cleanup; it is not a both-absent result.

Production base pin: `python:3.11-slim@sha256:07d4824036af339fa1b6ef769cc99d9c10a141769538b52b3b597c84f7a7b535`. The final historical application-only image build produced manifest-list digest `sha256:0496eb8a2a52f072933ee66dcfd978d80b6ec49de7dcc130e8d316a82dfdbfee`. Existing shell-form Docker CMD emitted `JSONArgsRecommended`; no claim that warning was removed.

## Repeatable demo and terminal sequence

Use the guarded dispatch examples and credentials/ownership contract in [the runbook](CI_SECRETS_SETUP.md); do not merge A to demonstrate it, expose runner secrets, broaden Azure roles, or create unrelated resources.

1. Pick two authorized same-repository PRs targeting `main`; show each full current head and distinct visible content. Dispatch candidate `preview` with explicit PR numbers; wait for image smoke, readiness and truthful status/comment publication.
2. Run strict `verify` with `expectation=both-present`. Show both actual public URLs, current revision panels, exact images and ownership evidence; use the dated captures above if provisioning is slow.
3. Push one visible A change. Wait for its deployment, then show same URL, same bot comment ID, new full SHA, and unchanged B via another strict verification.
4. Select A's workflow ref but target B explicitly. Compare trusted-control and application checkout SHAs, OCI revision, ACI image, page/API SHA and B status; preserve the same-tag metadata caveat.
5. On disposable B only, exercise the conditional cloud runtime fault; show real 503 readiness evidence, failed status and no success link. Close B unmerged. Distinguish installed-main automatic deletion from candidate manual behavior, then repeat candidate cleanup to prove `not-found` and verify A healthy/B absent.
6. Commit and push **all** intended implementation, documentation and captures while A remains open; let the resulting A deployment settle. Preserve final SHA/run/artifact references before cleanup.
7. Dispatch candidate `cleanup`, `cleanup_mode=manual-cleanup`, `pr_number=8`; require ownership-verified deletion/absence evidence. Run strict `verify`, PR8/PR9, `expectation=both-absent`. Leave A open/unmerged, B closed/unmerged.
8. Update only reserved [comment 6954553166](https://github.com/prabalpratapsinghmer/CDD-project/pull/8#issuecomment-6954553166) with observed terminal run/artifact links, full final head, local smoke, both-absent evidence and intentional cost-control explanation. **Do not push afterward.**

Terminal cleanup is intentionally not checked off in this pre-cleanup commit. The reserved comment is the authoritative final addendum, including any new failures rather than an assumed success.
