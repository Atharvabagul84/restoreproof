mock_provider "aws" {}

variables {
  bucket_name         = "restoreproof-storage-only-test"
  aws_account_id      = "123456789012"
  allow_aws_resources = true
  enable_github_oidc  = false
}

run "storage_only_does_not_attempt_restricted_iam" {
  command = plan
  assert {
    condition     = length(aws_iam_role.recovery) == 0 && length(aws_iam_role_policy.recovery) == 0 && length(aws_iam_openid_connect_provider.github) == 0
    error_message = "Storage-only mode must not attempt any IAM resources."
  }
  assert {
    condition     = output.role_arn == null
    error_message = "Storage-only mode cannot advertise a deployed OIDC role."
  }
}
