output "bucket_name" { value = aws_s3_bucket.backups.id }
output "role_arn" { value = var.enable_github_oidc ? aws_iam_role.recovery[0].arn : null }
output "oidc_subject" { value = local.oidc_subject }
output "backup_prefix" { value = local.backup_prefix }
output "evidence_prefix" { value = local.evidence_prefix }
output "aws_region" { value = var.aws_region }
