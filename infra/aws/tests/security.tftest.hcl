mock_provider "aws" {}

variables {
  bucket_name          = "restoreproof-offline-test"
  aws_account_id       = "123456789012"
  github_owner         = "Atharvabagul84"
  github_repository    = "restoreproof"
  github_owner_id      = "64049571"
  github_repository_id = "1436708557"
}

run "cloud_disabled_by_default" {
  command         = plan
  expect_failures = [terraform_data.cost_guard]
}

run "private_versioned_encrypted_and_scoped" {
  command = plan
  variables { allow_aws_resources = true }

  assert {
    condition     = aws_s3_bucket_public_access_block.backups.block_public_acls && aws_s3_bucket_public_access_block.backups.block_public_policy && aws_s3_bucket_public_access_block.backups.ignore_public_acls && aws_s3_bucket_public_access_block.backups.restrict_public_buckets
    error_message = "All public access must be blocked."
  }
  assert {
    condition     = aws_s3_bucket_versioning.backups.versioning_configuration[0].status == "Enabled" && !aws_s3_bucket.backups.force_destroy
    error_message = "Backups must be versioned and not force-destroyed."
  }
  assert {
    condition     = one(aws_s3_bucket_server_side_encryption_configuration.backups.rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256"
    error_message = "SSE-S3 must avoid a paid KMS dependency."
  }
  assert {
    condition     = one(aws_s3_bucket_ownership_controls.backups.rule).object_ownership == "BucketOwnerEnforced"
    error_message = "Object ACLs must be disabled."
  }
  assert {
    condition     = jsondecode(aws_iam_role.recovery[0].assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == "repo:Atharvabagul84@64049571/restoreproof@1436708557:ref:refs/heads/main"
    error_message = "Only the exact immutable repository and main branch may assume the role."
  }
  assert {
    condition     = jsondecode(aws_iam_role.recovery[0].assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
    error_message = "OIDC audience must be STS."
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.recovery[0].policy).Statement[0].Action == "s3:GetObjectVersion" && jsondecode(aws_iam_role_policy.recovery[0].policy).Statement[0].Resource == "arn:aws:s3:::restoreproof-offline-test/backups/chisel/*"
    error_message = "Backup access must only read explicit versions in the approved prefix."
  }
  assert {
    condition     = jsondecode(aws_iam_role_policy.recovery[0].policy).Statement[1].Action == "s3:PutObject" && jsondecode(aws_iam_role_policy.recovery[0].policy).Statement[2].Action == "s3:GetObject"
    error_message = "Evidence permissions must not grant backup writes, deletes or bucket listing."
  }
  assert {
    condition     = jsondecode(aws_s3_bucket_policy.backups.policy).Statement[0].Condition.Bool["aws:SecureTransport"] == "false"
    error_message = "Unencrypted transport must be denied."
  }
  assert {
    condition     = one(aws_s3_bucket_lifecycle_configuration.backups.rule).expiration[0].days == 30 && one(aws_s3_bucket_lifecycle_configuration.backups.rule).noncurrent_version_expiration[0].noncurrent_days == 7
    error_message = "Current and noncurrent versions need bounded retention."
  }
}

run "reject_wildcard_repository" {
  command = plan
  variables {
    allow_aws_resources = true
    github_repository   = "*"
  }
  expect_failures = [var.github_repository]
}

run "reject_unbounded_retention" {
  command = plan
  variables {
    allow_aws_resources = true
    retention_days      = 365
  }
  expect_failures = [var.retention_days]
}

run "require_repository_id_for_oidc" {
  command = plan
  variables {
    allow_aws_resources  = true
    github_repository_id = null
  }
  expect_failures = [var.github_repository_id]
}

run "reject_non_numeric_repository_id" {
  command = plan
  variables {
    allow_aws_resources  = true
    github_repository_id = "restoreproof"
  }
  expect_failures = [var.github_repository_id]
}
