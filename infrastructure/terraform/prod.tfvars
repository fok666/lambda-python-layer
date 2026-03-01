# =============================================================================
# Lambda Python Layer Builder - Terraform Configuration
# =============================================================================
# Copy this file to terraform.tfvars and customize for your environment.
# =============================================================================

# AWS region for all resources
aws_region = "eu-central-1"

# Environment name
environment = "prod"

# Project name (used as prefix for all resources)
project_name = "lambda-layer-builder"

# Hours to keep build artifacts in S3 (1-168)
artifact_ttl_hours = 24

# Docker image prefix for pre-built images
# docker_image_prefix = "ghcr.io/fok666/lambda-python-layer"

# GitHub repo URL (fallback for local Docker builds)
# github_repo_url = "https://github.com/fok666/lambda-python-layer.git"

# EC2 Spot instance type for builds
# c5.xlarge  = 4 vCPU, 8GB  (~$0.04/hr spot) - Recommended
# c5.2xlarge = 8 vCPU, 16GB (~$0.08/hr spot) - Heavy builds
# m5.large   = 2 vCPU, 8GB  (~$0.02/hr spot) - Light builds
ec2_instance_type = "c5.xlarge"

# EBS volume size in GB (30-200)
ec2_volume_size = 50

# Max build time before instance self-terminates (safety net)
ec2_max_build_time_minutes = 30

# CORS origins - MUST be restricted to your GitHub Pages URL in production.
# Using ["*"] exposes the API to cross-origin requests from any website.
# Example: ["https://yourusername.github.io"]
# allowed_origins = ["https://yourusername.github.io"]
allowed_origins = ["https://fok666.github.io"]  # TODO: replace with your actual frontend origin

# API request limits (per-stage; tune down for tighter abuse prevention)
api_throttle_rate  = 5   # requests per second
api_throttle_burst = 10  # burst limit

# Maximum concurrent builds (each may launch up to 2 EC2 Spot instances)
max_active_builds = 10
