# Optional AWS infrastructure and GitHub recovery

Apply only under verified account-specific no-charge controls. This project keeps local execution fully functional. Do not upgrade an AWS plan or weaken an organization policy to run the demo.

## Infrastructure contract

- One private bucket: four public-access blocks, BucketOwnerEnforced ownership, versioning, SSE-S3 AES256 encryption and a deny for insecure transport.
- Current object expiration after 30 days; noncurrent versions after 7 days; incomplete multipart uploads aborted after one day. Values are bounded and configurable. Lifecycle is asynchronous, can leave delete markers, and does not delete the bucket itself.
- `force_destroy=false` and `prevent_destroy=true` protect backup storage from casual teardown. Do not remove those safeguards without a reviewed data-retention decision.
- Optional GitHub OIDC provider and one role. Trust requires `aud=sts.amazonaws.com` and the exact repository/main subject, with immutable numeric owner/repository IDs for this newly created repository.
- Recovery permissions: `GetObjectVersion` on `backups/chisel/*`, `PutObject` on `evidence/chisel/*`, and `GetObject` on the single history index. No backup writes, deletes, broad bucket listing, KMS keys or static GitHub AWS secrets.
- Account ID is constrained in the AWS provider. No compute, NAT gateway, database, paid monitoring, remote Terraform backend or other recurring service is provisioned by this configuration.

## Local checks, no credentials or cloud mutations

Use Terraform 1.16.5 (configuration supports 1.11+ below 2) and the committed AWS provider lock for 6.67.0:

```sh
terraform -chdir=infra/aws init -backend=false
terraform -chdir=infra/aws fmt -check -recursive
terraform -chdir=infra/aws validate
terraform -chdir=infra/aws test
```

The five mocked-provider tests check the free-use opt-in, private/versioned/encrypted storage, scoped OIDC/IAM configuration and storage-only isolation. They do not contact AWS or establish live permissions.

## Prepare a deployment

1. Verify the actual AWS plan, expiry and prevention of charges, and GitHub's included minutes/storage plus enforced $0 overage cap. Keep repository visibility PRIVATE.
2. Authenticate the authorized deployer through its normal temporary session. Never paste keys into chat or commit state/credentials. The deployer has broader infrastructure permissions than the recovery role; the workflow cannot create its own role.
3. Copy `terraform.tfvars.example` to a gitignored tfvars file. Set the exact account, region and a new globally unique bucket name. Set `allow_aws_resources=true` only after step 1.
4. Determine whether the account already has the GitHub OIDC provider; if so, set its exact ARN instead of creating a duplicate. Verify the actual issuer subject using the `oidc-identity` job in the manual local-lab workflow. Existing repositories may have a different subject format; do not widen trust to wildcards.
5. Run `terraform plan -var-file=<your-file> -out=<reviewed-plan>`. Inspect every resource and permission. Apply only that reviewed plan. Preserve the local state securely and outside Git.

For the account inspected on 2026-10-07, the denial was traced to AWS's managed-project `DenyIAMRestrictedActions` statement. Its documented `iam:*Provider*` restriction covers GitHub OIDC provider operations. Advanced features require a paid-plan upgrade; that route is not selected under the free-only constraint. This finding combines the observed denied list request with the published policy; it does not claim every IAM API was called. [Account compatibility evidence](../../docs/history/aws-account-compatibility.md).

`enable_github_oidc=false` plans only the bucket/configuration and makes `role_arn` null. It issues no IAM provider/role/policy operations. This storage-only plan was applied to `restoreproof-123456789012-ap-southeast-2` on 2026-10-07: **8 added, 0 changed, 0 destroyed**, followed by a no-change plan. Real S3 recovery used the existing project's temporary CLI browser session and local Docker. It does not complete GitHub-to-AWS authentication. [Live validation](../../docs/history/validation-aws-live.md).

## Prepare the first backup

Use the existing Chisel source capture to obtain a synthetic custom-format dump and independent expectations. With a separately authorized producer session, upload under `backups/chisel/` with AES256 encryption and ExpectedBucketOwner. Record the upload's **VersionId**, archive SHA-256 and original source capture time in a reviewed full [S3 recovery contract](../../docs/guides/s3-recovery.md). Do not use a guessed version ID or the object's upload time as a capture timestamp.

The checked-in `contracts/s3-chisel.json` records the actual successful synthetic upload from 2026-10-07. It is a historical, expiring contract: its 24-hour freshness window ends on 2026-10-08 at 05:32:56 UTC. Re-running it later must fail freshness. The adapter now pins Chisel v1.0.0 (`fdb206c`), so this contract (which names a pre-release commit) is now rejected as INVALID before freshness is checked; a new upload must record the current commit. Create a new capture/upload and review a new contract before a future live drill; do not edit the timestamp to disguise an old backup. The repository is private; do not commit real customer data, secrets or backup bytes.

## Enable manual GitHub AWS verification

Set repository variables only after their prerequisites are true:

| Variable | Required value / prerequisite |
|---|---|
| `RESTOREPROOF_FREE_CI_VERIFIED` | `true`; actual free allowance and enforced spending stop verified |
| `RESTOREPROOF_AWS_FREE_VERIFIED` | `true`; current no-charge AWS plan verified |
| `RESTOREPROOF_AWS_ACCOUNT_ID` | Exact account ID used by Terraform |
| `RESTOREPROOF_AWS_REGION` | Bucket region |
| `RESTOREPROOF_ROLE_ARN` | Actual successfully deployed scoped recovery role ARN |
| `RESTOREPROOF_SCHEDULE_ENABLED` | Keep unset until a complete manual AWS run passes |

Run **Recover Chisel from S3** with mode `aws`, ref `main` and the reviewed contract path. It prepares images, requests a 30-minute session using GitHub OIDC, restores Chisel, publishes evidence and prints the latest attempt/last success. The role permits at most one-hour sessions. Actions are pinned by commit. No pull-request event has this role path.

Review `runs/current.json`, the S3 parent report, nested application report, object version/hash, all required auth/application checks, local artifact, remote history and cleanup. A skipped job, an issuer-claims check, or an emulator PASS does not satisfy this benchmark.

Only after that benchmark passes, set `RESTOREPROOF_SCHEDULE_ENABLED=true` to opt into Monday 04:17 UTC (09:47 India time). Arrange a producer and reviewed contract refresh within `max_age_seconds`; the schedule never creates fresh backups by itself. A stale pinned backup must fail.

## Pause, retention and recovery

Unset the schedule variable to pause AWS drills, and disable either free-use gate if plan eligibility or spending controls change. This does not delete existing backups. Keep reviewed small evidence in the private repository if it must outlive the one-day Actions artifact retention. S3 object lifecycle and index windows are retention policies, not a spending cap.

Use the [owned cleanup procedure](../../docs/guides/s3-recovery.md#scheduling-and-interruption) after an interrupted drill. Archive Terraform state before ending a temporary deployment environment. Bucket destruction and deleting backup versions are separate, consequential data-management operations; they are not part of a recovery drill.

Primary references: [S3 versioning](https://docs.aws.amazon.com/AmazonS3/latest/userguide/Versioning.html), [GitHub OIDC with AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws), [S3 GetObject](https://docs.aws.amazon.com/boto3/latest/reference/services/s3/client/get_object.html).
