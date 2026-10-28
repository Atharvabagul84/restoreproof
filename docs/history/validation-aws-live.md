# Real S3 recovery validation — 2026-10-07

**Result: the real S3 storage/recovery suite passed. The GitHub-to-AWS benchmark remains incomplete.** AWS supplied the object storage and evidence history; the original Chisel application ran in disposable local Docker containers. Authentication used the existing project's temporary AWS CLI browser session, not a GitHub OIDC role.

The runtime is unchanged from implementation commit `baeaaa24123fbddd84d35249611ec661720b86be`. Its measured source digest remains `9bbed984f634dbc1dad26dd6e457037a345aa941d4412da2dabb89b8467792c8`, matching the earlier green GitHub and wheel evidence. The six operational live scenarios below are additional observations, not six newly counted Python unit tests.

## Applied infrastructure

Terraform 1.16.5 and AWS provider 6.67.0 applied the reviewed storage-only plan to account `123456789012`, region `ap-southeast-2`, bucket `restoreproof-123456789012-ap-southeast-2`:

- **8 added, 0 changed, 0 destroyed**: one cost guard and seven S3 bucket/configuration resources. No IAM resources or AWS compute.
- All four public-access blocks enabled; BucketOwnerEnforced ownership; versioning enabled; SSE-S3 AES256 encryption; a policy denying insecure transport.
- Current-object expiration: 30 days. Noncurrent versions: 7 days. Incomplete multipart uploads: 1 day. Lifecycle processing is asynchronous and may leave delete markers.
- A subsequent real refresh/plan returned **no changes**. The existing EdgeOps bucket was not targeted.

Evidence: [reviewed resource list](../../evidence/aws-live/terraform-plan-summary.json), [apply log](../../evidence/aws-live/terraform-apply.log), [post-apply plan](../../evidence/aws-live/terraform-post-apply-plan.log), [bucket settings read from AWS](../../evidence/aws-live/bucket-controls.json).

## Exact backup and application result

| Field | Observed value |
|---|---|
| Source capture | `2026-10-07T05:32:56.475736+00:00` |
| Archive size | 139,146 bytes |
| Original version recovered | `D8bX4tAGy_JUGkg2l1WNaSw726DOg1u2` |
| Newer incorrect version deliberately ignored | `PnOTzTyeAmHk_ujvg4hhRIMUOyW1Axdf` |
| SHA-256 | `d4453ac30e2764fe9c7421932245f9d3749294d7d005317ccc050a927eb79c43` |
| Healthy S3 parent run | `82152e40e3fc4bbaa63c75c6a12875ba` |
| Capture age when retrieval started | 178.289129 seconds |
| S3 retrieval phase | 1.313 seconds |
| Whole healthy attempt, including target cleanup | 21.656 seconds |

All nine required retrieval/application/duration checks passed: exact backup retrieval; unauthenticated HTTP 401; email OTP sign-in over verified TLS; restored identity; saved-brief content hash; create/read/update and stale-write HTTP 409 with unchanged content; cross-tenant HTTP 404; sign-out followed by HTTP 401; recovery-duration objective. Source, target and download cleanup were PASS.

This is one tiny synthetic backup with images already prepared, local application runtime and a real regional S3 connection. It is not production RTO, RPO, incident MTTR or a cloud-region failover measurement.

Evidence: [upload receipt](../../evidence/aws-live/upload-receipt.json), [trusted contract](../../contracts/s3-chisel.json), [healthy parent report](../../evidence/aws-live/healthy/report.json), [nested Chisel report](../../evidence/aws-live/healthy/application/report.json).

## Failure scenarios and exact boundaries

| Scenario | Observed outcome | What was actually exercised |
|---|---|---|
| Healthy older version | PASS | Real S3 GET of the pinned version, then complete Chisel recovery |
| Missing object | INCOMPLETE / `missing-object` | Real S3 request for a unique absent key; no target allocation |
| Denied access | INCOMPLETE / `access-denied` | Real S3 rejection of a deliberately wrong ExpectedBucketOwner; **not** a test of the proposed recovery-role IAM policy |
| Checksum mismatch | FAIL / `checksum-mismatch` | Real object download checked against an intentionally wrong trusted hash |
| Stale backup | FAIL / `stale-backup` | Intentionally stale capture timestamp rejected locally before S3 GET |
| Interrupted download | INCOMPLETE / `download-interrupted` | Real AWS HTTP 200 body returned 4,096 bytes; the test then closed that response locally, and the SDK detected the truncated stream |

The interruption harness wrapped the real client's `get_object` response. Its first `read` returned 4,096 actual bytes; on the next read it closed the underlying StreamingBody and invoked its normal `read` again. It did not fabricate S3 bytes or manually raise the expected error. This tests client-observed interruption, not an actual AWS service outage. The existing local HTTP tests separately exercise an upstream socket closing mid-body.

Every negative case matched its intended failure code, allocated no application target, and removed partial downloads. A suite PASS means expected failures were detected; it does not turn those failed recovery attempts into successful recoveries. [Full suite](../../evidence/aws-live/suite.json).

## Evidence, history and cleanup

All six reports were published to `evidence/chisel/runs/<run-id>.json` in the private bucket with AES256 encryption and create-only writes. Each report was read back and compared with its expected JSON payload. History was also read back and compared after conditional updates.

The latest attempt is interrupted run `9536aaa326fe4687b522502f47ee0bc7` with status INCOMPLETE. Last success correctly remains healthy run `82152e40e3fc4bbaa63c75c6a12875ba`. [History](../../evidence/aws-live/history.json) · [Remote evidence version/hash receipts](../../evidence/aws-live/remote-evidence-receipts.json).

The final Docker inventory had no containers labeled `io.restoreproof.run_id`; no target `backup.dump` or `.s3-download-*` files remained. The source fixture is intentionally retained locally, and the private S3 bucket/backups/evidence remain subject to their retention policy. Neither bucket destruction nor deletion of backup versions is part of a successful recovery drill. [Cleanup inventory](../../evidence/aws-live/cleanup.json).

`aws logout --profile restoreproof-live` cleared this task's isolated login cache. This is local credential-cache cleanup, not a claim that already issued access tokens were immediately revoked; all validation child processes had completed. The user's existing Console session was left intact. [Session cleanup](../../evidence/aws-live/session-cleanup.json).

Curated evidence preserves original bytes and historical runner paths. No backup bytes, temporary credentials, OTPs, cookies, private keys, Terraform state or plan binary are committed. [SHA-256 manifest](../../evidence/aws-live/MANIFEST.json). Local Terraform state must be preserved separately for future management of the retained bucket.

## Remaining benchmark and next run

The account is AWS's managed-project experience. Its organizational policy denies IAM identity-provider operations, and AWS requires a paid-plan upgrade before enabling the advanced controls that could change those restrictions. No upgrade, policy bypass, static CI key or alternate identity workaround was used. [Exact account finding and official references](aws-account-compatibility.md).

GitHub issuer claims were validated in the earlier CI run, but **AWS role assumption, scoped recovery-role enforcement and scheduled cloud recovery are still unvalidated**. Only `RESTOREPROOF_FREE_CI_VERIFIED=true` exists among repository variables; AWS role/free-use/schedule variables remain unset. The full requested GitHub workflow benchmark cannot be completed in this account mode under the current free-only constraint.

The retained contract expires after 24 hours, at **2026-10-08 05:32:56 UTC / 11:02:56 India time**. It must then fail freshness. For another live run, recheck Free-plan eligibility, capture fresh synthetic Chisel data, upload and record a new exact version/hash/capture time, and obtain a new temporary session. Do not refresh the timestamp on an old dump. For a repeatable showcase without account restrictions, `python -m restoreproof s3-demo --output runs/s3-demo` creates fresh local fixtures each time.

Enable cloud scheduling only after an OIDC-compatible account with verified prevention of charges is available, a manual GitHub AWS recovery passes, and a backup producer plus reviewed contract refresh satisfy the freshness window. Until then, the private CI lab and retained live-S3 evidence are the demonstrated portfolio scope.
