# v0.5 validation: offline reports and weekly synthetic recovery

Recorded **2026-10-07**. Runtime implementation: `c3899529c14508fc97001252c2b95feb4ad97a08`. Later documentation and evidence commits do not change the tested runtime. The CI journals and independently installed wheel agree on Python/source-manifest digest `31ef255cfffb21e738716d04cd61445baae1de1ac6d63374538a2e56f3c6d17f`. This digest does not cover stylesheet bytes; the wheel hash covers the packaged stylesheet too.

## Hosted result

Private GitHub run 37596871490 (pre-release CI run 37596871490) passed the manual `local-lab` and `oidc-identity` jobs. The AWS job was **skipped**, not validated. The lab job completed from 08:54:06 to 08:56:04 UTC, including setup, installation, tests and artifact upload.

| Check | Observed result |
|---|---|
| Unit and actual loopback S3 HTTP tests | 245 discovered; **222 passed**, 23 opt-in skips; 6.231 seconds |
| Separate S3/Chisel integration | **1 method passed**, exercising six scenarios; 78.081 seconds including preparation and capture |
| Distinct Python methods passed | **223**; the other 22 live integration methods were not rerun here |
| HTML export | PASS; six local-S3 attempts, correct latest attempt and last success |
| GitHub issuer identity | Exact expected repository/main subject; only seven non-secret fields retained; no AWS role assumed |

The healthy attempt retrieved the **139,140-byte** archive at original version `378b5257-795e-4d70-a6ef-3d7204df10c3` after a newer incorrect version existed. SHA-256 matched, all nine recorded checks passed, stale writes returned 409, tenant isolation returned 404, and source/target/download/emulator-storage cleanup passed. Its total was **7.170736 seconds**, including cleanup with images already prepared. This is a tiny synthetic observation, not production RTO or an improvement benchmark against the different AWS run.

Missing object, access denial, checksum mismatch, stale capture and interrupted HTTP body each produced its exact expected cause before target allocation. Latest attempt `44c62469be354c05a9a103a53781244f` remained INCOMPLETE; last success still referenced `1738c9642ec54e32956b70820b4b2dcc`. A passing scenario suite does not turn these failed attempts green.

## Implementation and artifact checks

- The 22 new report regression tests cover escaping and field selection, scope separation, invalid evidence, input limits, contradictory success/cleanup, receipt mismatches, duplicate IDs/keys and preservation of an existing output on rejection. Failures were observed before implementing the corresponding behavior.
- Local discovery: **218 passed / 27 opt-in skips** out of 245, in 38.662 seconds. The four HTTP tests skipped locally were enabled in the hosted result above.
- `actionlint` 1.7.12 passed both workflow definitions. Terraform was unchanged; its earlier five plan tests remain historical v0.4 evidence, not newly rerun checks.
- The v0.5 wheel was installed and invoked outside the checkout, exported six historical AWS journals and verified all 101 pinned Chisel source files. CSS was present in the wheel. Wheel SHA-256: `9d2d559324f7c75f0cc6f2c81d082185660622a381eb2d595741e20c61f9719f`.
- Browser review covered the desktop overview, expanded healthy checks and a 390 × 844 mobile viewport. Document width and scroll width were both 375 pixels: no page-level horizontal overflow. The narrow evidence table can scroll within its container. These checks do not constitute a full accessibility audit.
- HTML uses inline CSS and native disclosures, with no JavaScript or external assets. Rendering retained evidence requires neither Docker nor AWS credentials. It reports historical observations and selected journal history, not current service health.

## Weekly lab enabled

After the manual run passed, repository settings were read back at **09:02:02 UTC on October 7**: the repository was PRIVATE, the recovery workflow was active, and its only variables were `RESTOREPROOF_FREE_CI_VERIFIED=true` and `RESTOREPROOF_LAB_SCHEDULE_ENABLED=true`.

The synthetic lab is scheduled for **Monday 04:17 UTC / 09:47 India time**, first due **October 12, 2026**. No actual scheduled event had executed when this record was written. GitHub scheduling is best-effort. Each run creates fresh synthetic fixtures; its HTML history covers that run's six attempts. Actions artifacts expire after one day, while reviewed evidence below is retained in the private repository.

Before this work, the account displayed GitHub Free, 84 of 2,000 included minutes, zero of 0.5 GB artifact storage, $0 billable usage, and an existing $0 Actions budget with Stop usage enabled. No billing setting was changed. The lab uses a standard Ubuntu runner, a 25-minute job timeout and a non-cancelling concurrency group. The shared allowance and account controls determine whether future jobs can start; see the [cost policy](../reference/cost-policy.md).

The AWS free-use, role and schedule variables remain **unset**. The managed-account OIDC restriction is unchanged. No AWS session, cloud provisioning, paid API or upgrade was used for v0.5. Historical live S3 evidence remains separate in [the AWS validation record](validation-aws-live.md).

## Retained evidence

Captured reports are copied byte-for-byte; their embedded runner paths are historical and are not followed by the exporter.

- [Six-scenario suite](../../evidence/v05/ci/suite.json), [healthy recovery](../../evidence/v05/ci/healthy/report.json) and [Chisel application report](../../evidence/v05/ci/healthy/application/report.json)
- [Exact workflow HTML](../../evidence/v05/ci/report/restoreproof.html) and [export metadata](../../evidence/v05/ci/report/export.json)
- [Test names and summaries](../../evidence/v05/ci-tests.log), [run metadata](../../evidence/v05/ci-run.json), [issuer identity](../../evidence/v05/oidc-identity.json) and [schedule readback](../../evidence/v05/schedule-state.json)
- [Machine-readable validation](../../evidence/v05/validation.json), [wheel smoke](../../evidence/v05/wheel-smoke.json) and [SHA-256 manifest](../../evidence/v05/MANIFEST.json)

The manifest covers 26 evidence files. No backup archives, Terraform state, cookies, OTP values, private keys or AWS credentials are included. Checksums permit byte comparison; they do not sign or authenticate the evidence producer.
