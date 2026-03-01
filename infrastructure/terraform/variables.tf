# =============================================================================
# General Configuration
# =============================================================================

variable "aws_region" {
  description = "AWS region for all resources."
  type        = string
  default     = "eu-central-1"
}

variable "environment" {
  description = "Environment name (e.g., dev, staging, prod)."
  type        = string
  default     = "prod"
}

variable "project_name" {
  description = "Project name used as prefix for all resource names."
  type        = string
  default     = "lambda-layer-builder"
}

# =============================================================================
# Build Configuration
# =============================================================================

variable "artifact_ttl_hours" {
  description = <<-EOT
    Number of hours to retain build artifacts in S3 before automatic deletion.
    Also controls the DynamoDB TTL for build records (artifacts TTL + 24h).

    **Cost Impact:**
    - Longer TTL = more S3 storage costs
    - Shorter TTL = users must download promptly

    Default: 24 hours
  EOT
  type        = number
  default     = 24

  validation {
    condition     = var.artifact_ttl_hours >= 1 && var.artifact_ttl_hours <= 168
    error_message = "artifact_ttl_hours must be between 1 and 168 (1 week)."
  }
}

variable "docker_image_prefix" {
  description = <<-EOT
    Docker image prefix for pre-built Lambda layer builder images.
    The system will try to pull pre-built images before falling back to local builds.

    Format: registry/repository (without tag)
    Tags are auto-generated: python{version}-{arch}-latest
  EOT
  type        = string
  default     = "ghcr.io/fok666/lambda-python-layer"
}

variable "github_repo_url" {
  description = "GitHub repository URL for cloning Dockerfiles (fallback when pre-built images unavailable)."
  type        = string
  default     = "https://github.com/fok666/lambda-python-layer.git"
}

# =============================================================================
# EC2 Spot Instance Configuration
# =============================================================================

variable "ec2_instance_type" {
  description = <<-EOT
    EC2 instance type for x86_64 build workers.

    **Recommended types:**
    - c5.xlarge:  4 vCPU,  8 GB RAM (~$0.04/hr spot) - Good default
    - c5.2xlarge: 8 vCPU, 16 GB RAM (~$0.08/hr spot) - Heavy builds
    - m5.large:   2 vCPU,  8 GB RAM (~$0.02/hr spot) - Light builds

    Default: c5.xlarge
  EOT
  type        = string
  default     = "c5.xlarge"
}

variable "ec2_arm64_instance_type" {
  description = <<-EOT
    EC2 Graviton instance type for arm64 build workers.
    arm64 packages are always built on native Graviton hardware;
    QEMU cross-compilation is unreliable for C extension packages.

    **Recommended types:**
    - c7g.xlarge:  4 vCPU,  8 GB RAM (~$0.03/hr spot) - Good default
    - c7g.2xlarge: 8 vCPU, 16 GB RAM (~$0.06/hr spot) - Heavy builds
    - m7g.large:   2 vCPU,  8 GB RAM (~$0.02/hr spot) - Light builds

    Default: c7g.xlarge
  EOT
  type        = string
  default     = "c7g.xlarge"
}

variable "ec2_volume_size" {
  description = <<-EOT
    Root EBS volume size in GB for build instances.
    Needs space for Docker images, build artifacts, and OS.

    **Sizing guide:**
    - 30 GB: Minimal (1 Python version, small packages)
    - 50 GB: Recommended (multiple versions, large packages)
    - 100 GB: Heavy builds (many large packages like PyTorch)

    Default: 50 GB
  EOT
  type        = number
  default     = 50

  validation {
    condition     = var.ec2_volume_size >= 20 && var.ec2_volume_size <= 200
    error_message = "ec2_volume_size must be between 20 and 200 GB."
  }
}

variable "ec2_max_build_time_minutes" {
  description = <<-EOT
    Maximum time in minutes before a build instance self-terminates.
    Safety net to prevent runaway costs from stuck instances.

    Default: 30 minutes (most builds complete in 5-15 minutes)
  EOT
  type        = number
  default     = 30

  validation {
    condition     = var.ec2_max_build_time_minutes >= 10 && var.ec2_max_build_time_minutes <= 120
    error_message = "ec2_max_build_time_minutes must be between 10 and 120."
  }
}

# =============================================================================
# Networking
# =============================================================================

variable "vpc_cidr" {
  description = "CIDR block for the VPC. Default: 10.0.0.0/16"
  type        = string
  default     = "10.0.0.0/16"
}

variable "availability_zones" {
  description = <<-EOT
    List of availability zones for subnet placement.
    At least 1 required. Using 2 improves spot instance availability.

    Leave empty to auto-select the first 2 AZs in the region.
  EOT
  type        = list(string)
  default     = []
}

# =============================================================================
# API & CORS
# =============================================================================

variable "allowed_origins" {
  description = <<-EOT
    List of allowed CORS origins for the API.
    Use ["*"] during development, restrict to your GitHub Pages URL in production.

    Example: ["https://yourusername.github.io"]
  EOT
  type        = list(string)
  default     = ["*"]
}

variable "api_throttle_rate" {
  description = "API Gateway throttle rate (requests per second)."
  type        = number
  default     = 10
}

variable "api_throttle_burst" {
  description = "API Gateway throttle burst limit."
  type        = number
  default     = 20
}

# =============================================================================
# SQS Configuration
# =============================================================================

variable "sqs_visibility_timeout" {
  description = <<-EOT
    SQS message visibility timeout in seconds.
    Should be longer than the time it takes to launch an EC2 instance.

    Default: 300 seconds (5 minutes)
  EOT
  type        = number
  default     = 300
}

variable "sqs_max_receive_count" {
  description = "Number of times a message can be received before going to DLQ."
  type        = number
  default     = 3
}

variable "max_active_builds" {
  description = <<-EOT
    Maximum number of concurrently active builds (queued + in-flight).
    Requests that would exceed this limit receive HTTP 429.
    Each active build may launch up to 2 EC2 Spot instances (one per architecture),
    so this cap directly bounds worst-case concurrent EC2 costs.

    Default: 10 (= up to 20 simultaneous Spot instances)
  EOT
  type        = number
  default     = 10

  validation {
    condition     = var.max_active_builds >= 1 && var.max_active_builds <= 100
    error_message = "max_active_builds must be between 1 and 100."
  }
}
