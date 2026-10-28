locals {
  repository_subject = var.immutable_subject ? "${var.github_owner}@${var.github_owner_id}/${var.github_repository}@${var.github_repository_id}" : "${var.github_owner}/${var.github_repository}"
  oidc_subject       = "repo:${local.repository_subject}:ref:refs/heads/${var.github_branch}"
  oidc_provider_arn  = "arn:aws:iam::${var.aws_account_id}:oidc-provider/token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github" {
  count          = var.enable_github_oidc && var.github_oidc_provider_arn == null ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  depends_on     = [terraform_data.cost_guard]
}

resource "aws_iam_role" "recovery" {
  count                = var.enable_github_oidc ? 1 : 0
  name                 = "restoreproof-recovery-${var.github_repository_id}"
  max_session_duration = 3600
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.oidc_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = { StringEquals = {
        "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        "token.actions.githubusercontent.com:sub" = local.oidc_subject
      } }
    }]
  })
  depends_on = [terraform_data.cost_guard, aws_iam_openid_connect_provider.github]
}

resource "aws_iam_role_policy" "recovery" {
  count = var.enable_github_oidc ? 1 : 0
  name  = "read-versioned-backups-and-write-recovery-evidence"
  role  = aws_iam_role.recovery[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Sid = "ReadExactBackupVersion", Effect = "Allow", Action = "s3:GetObjectVersion", Resource = "${local.bucket_arn}/${local.backup_prefix}*" },
      { Sid = "WriteEvidenceOnly", Effect = "Allow", Action = "s3:PutObject", Resource = "${local.bucket_arn}/${local.evidence_prefix}*" },
      { Sid = "ReadHistoryOnly", Effect = "Allow", Action = "s3:GetObject", Resource = "${local.bucket_arn}/${local.evidence_prefix}history.json" }
    ]
  })
}
