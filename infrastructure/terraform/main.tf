# =============================================================================
# Lambda Python Layer Builder - Infrastructure
# =============================================================================
# Serverless build system that spins up EC2 Spot instances to build
# AWS Lambda Python layers using Docker, with GitHub Pages as the frontend.
# =============================================================================

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  # Credentials: export from the fok666 profile before running Terraform:
  #   eval "$(aws configure export-credentials --profile fok666 --format env)"
  #   terraform plan -var-file=prod.tfvars

  default_tags {
    tags = {
      Project     = var.project_name
      ManagedBy   = "Terraform"
      Environment = var.environment
    }
  }
}

# Unique suffix for globally unique resource names
resource "random_id" "suffix" {
  byte_length = 4
}

locals {
  name_prefix = "${var.project_name}-${var.environment}"
  suffix      = random_id.suffix.hex
}

# Current AWS account and region info
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
