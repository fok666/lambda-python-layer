# =============================================================================
# S3 Bucket for Build Artifacts
# =============================================================================
# Stores built Lambda layer zip files. Objects expire automatically
# after the configured TTL. Access is via presigned URLs only.
# =============================================================================

resource "aws_s3_bucket" "artifacts" {
  bucket = "${local.name_prefix}-artifacts-${local.suffix}"

  tags = {
    Name = "${local.name_prefix}-artifacts"
  }
}

resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  versioning_configuration {
    status = "Disabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    id     = "expire-build-artifacts"
    status = "Enabled"

    filter {
      prefix = "builds/"
    }

    expiration {
      days = ceil(var.artifact_ttl_hours / 24)
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_cors_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = var.allowed_origins
    expose_headers  = ["Content-Length", "Content-Type"]
    max_age_seconds = 3600
  }
}
