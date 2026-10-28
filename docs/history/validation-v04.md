# v0.4 validation record

Recorded 2026-10-07. This record separates local implementation evidence, hosted emulator evidence and real AWS validation. Historical v0.3 results remain in their original record.

**Validated implementation:** `baeaaa24123fbddd84d35249611ec661720b86be`. The later evidence/documentation commit does not change runtime code. Source digest in the CI reports and the independently installed wheel: `9bbed984f634dbc1dad26dd6e457037a345aa941d4412da2dabb89b8467792c8`.

## Local implementation

- Unit plus actual loopback S3 HTTP suite: **223 discovered, 200 passed, 23 opt-in skips**, 20.497 seconds. The skipped tests require separate live Docker integration opt-ins; they are not counted as passes.
- The full S3-to-Chisel test passed one method covering six scenarios: healthy exact older-version recovery, missing version, denied access, hash mismatch, stale capture and interrupted transport. This initial run preceded two additional cleanup/history-bootstrap fixes, so it is development evidence rather than the final implementation benchmark.
- Cleanup regressions were reproduced before repair: an unexpected child exception must leave cleanup uncertain, and a failed partial-file removal must not become PASS.
- Evidence bootstrap was revised to conditionally create the index before reading it, avoiding the need for bucket-listing permission on AWS.
- Terraform 1.16.5 / AWS provider 6.67.0: validation passed; all **five mocked-provider plan tests** passed, including the IAM-free storage-only plan.
- `actionlint` 1.7.12 validates both workflow definitions. The wheel includes the pinned original Chisel source and source manifest.

## Hosted final-revision benchmark

The private, gated `Recover Chisel from S3` workflow runs the complete unit/HTTP suite and then the six-scenario real Chisel recovery against local Moto. Its separate issuer job requests a GitHub OIDC token and retains only the expected identity fields; the token itself is never logged or retained. An issuer PASS verifies the configured subject, not AWS role assumption.

GitHub run 37568837383 (pre-release CI run 37568837383) **passed** both `local-lab` and `oidc-identity`. The `aws` job was intentionally skipped and is not counted as validation.

| Test group | Passed methods | Scope |
|---|---:|---|
| Unit and actual loopback S3 HTTP | 200 | 223 discovered, 23 opt-in skips; 7.331 seconds |
| Separate full S3/Chisel integration | 1 | Six scenarios; 83.872 seconds including image preparation and source capture |
| **Distinct Python methods passed** | **201** | The 22 other existing live integration methods were not rerun in this workflow |
| Terraform mocked-provider plans | 5 | Separate local validation, no AWS calls |

The successful recovery retrieved a **139,123-byte** archive at original version `612f3cdf-9d28-48ef-956c-613e7a8df320` after a newer incorrect version was uploaded. The SHA-256 matched, all nine recorded retrieval/application/duration checks passed, stale writes returned HTTP 409, and source/target/download/local-bucket cleanup passed. The healthy attempt took **7.922736 seconds**, with images already prepared; this is a tiny synthetic observation, not production RTO.

All five negative cases produced their exact expected cause before allocating a target. After the interrupted-download case, `latest_attempt` was INCOMPLETE while `last_success` still pointed to healthy run `53c4d5f4cf004a9b8391cccf54ec602e`.

GitHub issued the exact expected immutable-ID subject: `repo:Atharvabagul84@64049571/restoreproof@1407771955:ref:refs/heads/main`. Only seven non-secret identity fields were retained. No AWS role was assumed.

Evidence is copied byte-for-byte; embedded original runner paths are historical provenance. Use these curated relative links:

- [Healthy recovery](../../evidence/s3/ci/healthy/report.json) and [nested Chisel report](../../evidence/s3/ci/healthy/application/report.json)
- [Six-scenario suite and history](../../evidence/s3/ci/suite.json)
- [Actual GitHub issuer identity](../../evidence/s3/oidc-identity.json)
- [Test names and summaries](../../evidence/s3/ci-tests.log)
- [Machine-readable accounting](../../evidence/s3/validation.json) and [SHA-256 manifest](../../evidence/s3/MANIFEST.json)

The wheel was installed outside the checkout and verified all 101 pinned Chisel source files. A final local Docker inventory contained no containers labeled `io.restoreproof.run_id`. No backup bytes, cookies, OTPs, private keys or AWS credentials are included in curated evidence.

## Real AWS status

The signed-in account's Free plan displayed a no-charge guarantee, $140 credits and expiry April 6, 2027. S3 bucket listing and STS account identity succeeded. The pre-existing EdgeOps bucket was not modified.

The initial session ended with cloud validation paused when browser transfer required a local-file extension permission. The user then explicitly resumed it on 2026-10-07. The subsequent **real S3/local Docker suite passed all six scenarios**, Terraform applied eight storage-only resources and its post-apply plan reported no changes. [Full live record](validation-aws-live.md). The earlier `evidence/s3/validation.json` remains an immutable historical record of the hosted emulator run and its then-pending AWS status.

The IAM denial was traced to `DenyIAMRestrictedActions`, matching the AWS-managed project policy's `iam:*Provider*` restriction. Advanced account features require upgrading the account; that route is incompatible with the user's free-only constraint. No policy was weakened, and no OIDC provider or recovery role was created. [Account compatibility finding](aws-account-compatibility.md).

Live enforcement of the proposed recovery role, GitHub-to-AWS role assumption and the weekly cloud schedule remain unvalidated and disabled. The final user benchmark is not claimed complete until a real GitHub AWS workflow run retains recovery evidence and confirms cleanup. The local live-S3 result is useful independent evidence, not a substitute for that authentication benchmark.

## Cost and scope

GitHub Free showed 80 of 2,000 included minutes used and zero of 0.5 GB artifact storage used before this validation. The existing Actions budget was $0 with Stop usage enabled. New artifacts retain only reviewed reports for one day. No paid plan, paid API or upgrade was selected. These observations are account-state checks from this date, not permanent guarantees; see [the cost policy](../reference/cost-policy.md).

Tests demonstrate a small synthetic backup and real application journey. They do not establish production RTO/RPO, AWS disaster recovery, replication correctness, long-term retention, or tamper-proof audit storage.
