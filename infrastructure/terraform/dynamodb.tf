# =============================================================================
# DynamoDB Table for Build Tracking
# =============================================================================
# Tracks build state: QUEUED → PROCESSING → COMPLETED | FAILED
# TTL automatically cleans up old records.
# =============================================================================

resource "aws_dynamodb_table" "builds" {
  name         = "${local.name_prefix}-builds"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "buildId"

  attribute {
    name = "buildId"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = {
    Name = "${local.name_prefix}-builds"
  }
}
