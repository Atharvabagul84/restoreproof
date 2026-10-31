# Free-only project policy

The user's persistent requirement is free tools/services. On 2026-10-25 the owner approved publishing this repository as an MIT-licensed portfolio project; visibility changes still need the owner's explicit go-ahead. No paid plan, paid API, account upgrade or paid overage is authorized.

## Defaults

Use the existing local container engine, loopback Moto with explicit dummy credentials, local JSON/JUnit and reviewed small files in the repository. No AWS credentials are required for the local showcase. Hosted artifacts contain curated reports only and expire after one day. No paid monitoring or LLM API dependency is present.

Terraform cloud apply defaults off. Weekly AWS recovery is defined but disabled. These defaults concern additional service/tool charges, not existing hardware, electricity or internet expenses. Emulator tests do not prove cloud IAM/OIDC behavior.

v0.5 adds a separate opt-in weekly **synthetic** GitHub lab. It uses the existing standard Ubuntu runner and loopback Moto; it requires no cloud credentials. The user authorized enabling this timer after a successful hosted run and renewed account checks. Its schedule flag is independent of the blocked AWS schedule. See [the report/schedule guide](../guides/offline-report.md).

The synthetic lab flag was enabled on October 7 after [run 37596871490 passed](../history/validation-v05.md). The first timer execution is due October 12 at 04:17 UTC; actual scheduled execution was still pending at handoff. The account's existing $0 Actions budget and Stop usage control were preserved.

## Verified account state on 2026-10-07

- GitHub Free: **80 / 2,000 included Actions minutes**, **0 / 0.5 GB artifact storage**, and an existing **$0 Actions budget with Stop usage enabled**. This permits the small private validation in this session. Usage is shared across repositories, so these observations are not permanent guarantees.
- Before the v0.5 work, GitHub was checked again: **84 / 2,000 included minutes**, **0 / 0.5 GB storage**, **$0 billable usage**, and the existing Actions **$0 budget / Stop usage Yes**. No billing setting was changed. The weekly lab uses one runner with a 25-minute timeout, one-day artifact retention and a non-cancelling concurrency group. Shared allowance and account policies still determine whether a future run can start.
- AWS: **Free plan**, **no charges while on the plan**, **$140 credits**, expiry **April 6, 2027**. No upgrade was selected. An organization policy denied `iam:ListOpenIDConnectProviders`.
- The user initially paused browser transfer, then explicitly resumed live validation on this date. A normal AWS CLI browser sign-in provided a task-specific temporary session without changing extension permissions. The reviewed storage-only Terraform plan created eight RestoreProof resources; the live S3 recovery/failure suite passed. The local session cache was cleared with `aws logout` after verification.
- This managed-project account denies `iam:*Provider*`. Taking control of those restrictions requires an account upgrade and advanced features; neither is authorized or selected. No OIDC provider or recovery role was created. See [the account finding](../history/aws-account-compatibility.md).

## Gates and retention

`RESTOREPROOF_FREE_CI_VERIFIED=true` is the explicit standard Linux runner gate. All original integration jobs depend on the gated unit job; the manual S3 lab and issuer-identity job require the same gate. Disable it when verified allowance/spending conditions change. A budget email alone is insufficient: actual prevention of paid overage is required.

The AWS job additionally requires the exact repository/main identity (`RESTOREPROOF_REPOSITORY_ID` must equal `github.repository_id`; the S3 lab and issuer-identity jobs check it too), AWS free-use flag, real deployed role ARN, and either manual AWS mode or the enabled schedule flag. Keep the **repository variables** `RESTOREPROOF_AWS_FREE_VERIFIED`, `RESTOREPROOF_ROLE_ARN` and `RESTOREPROOF_SCHEDULE_ENABLED` unset while GitHub AWS authentication is blocked. The one-time local live test used the free-use environment gate only in its process. A cron definition with false job gates does not run the recovery workload. A skipped job means **not run**, not passed.

One-day Actions artifact retention reduces storage growth but is not a billing cap; it does not modify older artifacts or undo accrued usage. S3 lifecycle is also a retention policy, not a cost control. Do not add larger runners, KMS keys, NAT gateways, hosted databases or paid APIs to work around limits. Do not upgrade an account or weaken an organization policy.

Before future AWS work, recheck plan eligibility, expiry and organization-approved permissions, then follow [the deployment runbook](../../infra/aws/README.md). Continue locally if a no-charge authorized path is unavailable.

## Delivered scope

v0.4 implements exact-version retrieval, bounded transport, all five requested storage failures, real Chisel recovery, cleanup evidence, bounded last-success history, Terraform and gated OIDC/schedule definitions. Real S3 retrieval, applied bucket controls, remote evidence and local target cleanup passed; live enforcement of the proposed scoped recovery role and GitHub role assumption remain unvalidated. See [the S3 runbook](../guides/s3-recovery.md), [implementation validation](../history/validation-v04.md), and [live S3 record](../history/validation-aws-live.md).

The private bucket and its small synthetic backup/evidence objects are intentionally retained. Current objects expire after 30 days and noncurrent versions after 7 days; expiration is asynchronous, may leave delete markers, and does not remove the bucket. No compute was deployed in AWS. Recheck the Free plan before any future access; an old successful run does not establish future cost eligibility.

Primary references: [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [budget controls](https://docs.github.com/en/billing/concepts/budgets-and-alerts), [AWS Free Tier](https://aws.amazon.com/free/), [Moto server mode](https://docs.getmoto.org/en/latest/docs/server_mode.html).
