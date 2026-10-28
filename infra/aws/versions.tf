terraform {
  required_version = ">= 1.11, < 2.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.70.0"
    }
  }
}

provider "aws" {
  region              = var.aws_region
  allowed_account_ids = [var.aws_account_id]
  default_tags {
    tags = { Project = "RestoreProof", ManagedBy = "Terraform" }
  }
}

resource "terraform_data" "cost_guard" {
  input = var.allow_aws_resources
  lifecycle {
    precondition {
      condition     = var.allow_aws_resources
      error_message = "Cloud deployment is disabled. Verify the actual Free plan and prevention of charges before opting in."
    }
  }
}
