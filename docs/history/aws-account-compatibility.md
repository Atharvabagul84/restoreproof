# AWS account compatibility finding

Investigation resumed on 2026-10-07 after the user explicitly requested the live validation to continue.

## Observed account state

The selected account is `123456789012`, region `ap-southeast-2`. AWS Settings again showed the Free plan, $0 due, $140 remaining credits and expiry April 6, 2027. Existing project resources must remain untouched.

The signed-in managed role could call STS and list S3 buckets. Its `iam:ListOpenIDConnectProviders` request was explicitly denied. AWS's authorization-details API identified the matching statement as `DenyIAMRestrictedActions` in service control policy `p-0opyu1yf`, attached through the AWS-managed organization. No access policy was modified.

## Root cause

This is the new AWS managed-project account experience. Its documented policy denies `iam:*Provider*`, covering creation, inspection and modification of IAM identity providers. That matches the observed statement name and denied action. This is broader than the single failed list request; retrying OIDC creation is not a supported solution. The same provider restriction is documented for managed projects on both Free and Paid plans. [AWS managed policies for projects](https://docs.aws.amazon.com/accounts/latest/reference/scps-and-rcps-for-projects.html).

AWS documents advanced account features as the way to take control of these organizational restrictions, and requires upgrading the account first. Advanced features also remove managed spend limits. That path conflicts with this project's free-only requirement and is not selected. [Advanced-feature prerequisites and effects](https://docs.aws.amazon.com/accounts/latest/reference/activate-advanced-features.html).

## Permitted validation boundary

Use the existing authorized project session for the independent S3 storage/recovery test, with `enable_github_oidc=false`. This does not grant new identities access or replace the intended GitHub OIDC benchmark. The S3 configuration, exact-version recovery, application behavior, evidence and cleanup can be evaluated separately from AWS role federation.

AWS supports obtaining temporary local-development credentials through browser sign-in using `aws login`. A dedicated task profile/cache can avoid transferring keys through chat or uploading project files through the browser extension. End the task's session when validation finishes. [AWS CLI console sign-in](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html).

Keep the GitHub AWS role and schedule gates unset until an account with an approved, free-only OIDC path is actually available and tested. Issuer identity checks and storage-only runs do not establish AWS role assumption or least-privilege enforcement by the proposed recovery role.

## Result of the permitted test

The storage-only Terraform apply and all six real-S3/local-Chisel scenarios subsequently passed. The post-apply plan contained no changes; remote reports/history were read back; source/target/download cleanup passed. The task-specific AWS CLI login cache was cleared after the test. No IAM resources, paid upgrade or policy change was made. See [the live validation record](validation-aws-live.md) for exact object versions, measurements and failure-injection boundaries.
