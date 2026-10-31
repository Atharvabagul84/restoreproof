variable "allow_aws_resources" {
  type        = bool
  default     = false
  description = "Opt in only after account-specific no-charge controls have been verified."
}

variable "enable_github_oidc" {
  type        = bool
  default     = true
  description = "Disable for storage-only validation when organization policy prohibits IAM/OIDC. This does not enable GitHub AWS recovery."
}

variable "aws_account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "Use the exact 12-digit AWS account ID."
  }
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
  validation {
    condition     = can(regex("^[a-z]{2}-[a-z]+-[1-9]$", var.aws_region))
    error_message = "Use a commercial AWS region."
  }
}

variable "bucket_name" {
  type = string
  validation {
    condition     = can(regex("^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$", var.bucket_name))
    error_message = "Use a globally unique 3-63 character lowercase bucket name without dots."
  }
}

variable "retention_days" {
  type    = number
  default = 30
  validation {
    condition     = var.retention_days >= 1 && var.retention_days <= 90 && floor(var.retention_days) == var.retention_days
    error_message = "Current objects must expire within 1-90 whole days."
  }
}

variable "noncurrent_retention_days" {
  type    = number
  default = 7
  validation {
    condition     = var.noncurrent_retention_days >= 1 && var.noncurrent_retention_days <= 30 && floor(var.noncurrent_retention_days) == var.noncurrent_retention_days
    error_message = "Noncurrent versions must expire within 1-30 whole days."
  }
}

variable "github_owner" {
  type    = string
  default = "Atharvabagul84"
  validation {
    condition     = can(regex("^[A-Za-z0-9-]+$", var.github_owner))
    error_message = "An exact GitHub owner is required."
  }
}

variable "github_repository" {
  type    = string
  default = "restoreproof"
  validation {
    condition     = can(regex("^[A-Za-z0-9_.-]+$", var.github_repository))
    error_message = "An exact repository name without wildcards is required."
  }
}

variable "github_owner_id" {
  type    = string
  default = "64049571"
  validation {
    condition     = can(regex("^[0-9]+$", var.github_owner_id))
    error_message = "Use the immutable numeric GitHub owner ID."
  }
}

variable "github_repository_id" {
  type        = string
  default     = null
  description = "Immutable numeric ID of the one repository allowed to assume the recovery role (gh api repos/OWNER/REPO --jq .id). Required with enable_github_oidc."
  validation {
    condition     = var.github_repository_id == null ? !var.enable_github_oidc : can(regex("^[0-9]+$", var.github_repository_id))
    error_message = "Set the immutable numeric GitHub repository ID; it is required when enable_github_oidc is true."
  }
}

variable "github_branch" {
  type    = string
  default = "main"
  validation {
    condition     = can(regex("^[A-Za-z0-9][A-Za-z0-9._/-]{0,99}$", var.github_branch))
    error_message = "Use one exact branch without wildcard or subject delimiters."
  }
}

variable "immutable_subject" {
  type        = bool
  default     = true
  description = "This repository was created after 2026-07-15. Older repositories must verify their actual subject format."
}

variable "github_oidc_provider_arn" {
  type        = string
  default     = null
  description = "Use an existing account OIDC provider if present; otherwise create one."
  validation {
    condition     = var.github_oidc_provider_arn == null ? true : var.github_oidc_provider_arn == "arn:aws:iam::${var.aws_account_id}:oidc-provider/token.actions.githubusercontent.com"
    error_message = "The existing GitHub provider must belong to the selected account."
  }
}
