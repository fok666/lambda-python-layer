# =============================================================================
# SQS Queue for Build Requests
# =============================================================================
# Build requests are queued for decoupled, reliable processing.
# Failed messages go to a dead letter queue for investigation.
# =============================================================================

resource "aws_sqs_queue" "build_queue" {
  name                       = "${local.name_prefix}-build-queue"
  visibility_timeout_seconds = var.sqs_visibility_timeout
  message_retention_seconds  = 86400 # 24 hours
  receive_wait_time_seconds  = 10    # Long polling

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.build_dlq.arn
    maxReceiveCount     = var.sqs_max_receive_count
  })

  tags = {
    Name = "${local.name_prefix}-build-queue"
  }
}

resource "aws_sqs_queue" "build_dlq" {
  name                      = "${local.name_prefix}-build-dlq"
  message_retention_seconds = 604800 # 7 days

  tags = {
    Name = "${local.name_prefix}-build-dlq"
  }
}
