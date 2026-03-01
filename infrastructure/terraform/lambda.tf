# =============================================================================
# Lambda Functions
# =============================================================================

# Package Lambda source code into zip archives
data "archive_file" "submit_build" {
  type        = "zip"
  source_file = "${path.module}/../lambdas/submit_build/index.py"
  output_path = "${path.module}/.build/submit_build.zip"
}

data "archive_file" "process_build" {
  type        = "zip"
  source_file = "${path.module}/../lambdas/process_build/index.py"
  output_path = "${path.module}/.build/process_build.zip"
}

data "archive_file" "check_status" {
  type        = "zip"
  source_file = "${path.module}/../lambdas/check_status/index.py"
  output_path = "${path.module}/.build/check_status.zip"
}

# -----------------------------------------------------------------------------
# Submit Build Lambda
# Validates request, creates DynamoDB record, sends message to SQS
# -----------------------------------------------------------------------------

resource "aws_lambda_function" "submit_build" {
  function_name    = "${local.name_prefix}-submit-build"
  filename         = data.archive_file.submit_build.output_path
  source_code_hash = data.archive_file.submit_build.output_base64sha256
  handler          = "index.handler"
  runtime          = "python3.13"
  timeout          = 30
  memory_size      = 128
  role             = aws_iam_role.lambda_submit.arn

  environment {
    variables = {
      DYNAMODB_TABLE     = aws_dynamodb_table.builds.name
      SQS_QUEUE_URL      = aws_sqs_queue.build_queue.url
      ARTIFACT_TTL_HOURS = tostring(var.artifact_ttl_hours)
    }
  }

  tags = {
    Name = "${local.name_prefix}-submit-build"
  }
}

resource "aws_cloudwatch_log_group" "submit_build" {
  name              = "/aws/lambda/${aws_lambda_function.submit_build.function_name}"
  retention_in_days = 14
}

# -----------------------------------------------------------------------------
# Process Build Lambda
# Triggered by SQS, launches EC2 Spot instance with build user-data
# -----------------------------------------------------------------------------

resource "aws_lambda_function" "process_build" {
  function_name    = "${local.name_prefix}-process-build"
  filename         = data.archive_file.process_build.output_path
  source_code_hash = data.archive_file.process_build.output_base64sha256
  handler          = "index.handler"
  runtime          = "python3.13"
  timeout          = 60
  memory_size      = 256
  role             = aws_iam_role.lambda_process.arn

  environment {
    variables = {
      DYNAMODB_TABLE       = aws_dynamodb_table.builds.name
      S3_BUCKET            = aws_s3_bucket.artifacts.id
      SUBNET_IDS           = join(",", aws_subnet.public[*].id)
      SECURITY_GROUP_ID    = aws_security_group.builder.id
      LAUNCH_TEMPLATE_ID   = aws_launch_template.builder.id
      INSTANCE_PROFILE_ARN = aws_iam_instance_profile.ec2_builder.arn
      DOCKER_IMAGE_PREFIX  = var.docker_image_prefix
      GITHUB_REPO_URL      = var.github_repo_url
      EC2_INSTANCE_TYPE    = var.ec2_instance_type
      MAX_BUILD_MINUTES    = tostring(var.ec2_max_build_time_minutes)
      PROJECT_NAME         = var.project_name
      EC2_BUILD_LOG_GROUP  = aws_cloudwatch_log_group.ec2_builds.name
    }
  }

  tags = {
    Name = "${local.name_prefix}-process-build"
  }
}

resource "aws_cloudwatch_log_group" "process_build" {
  name              = "/aws/lambda/${aws_lambda_function.process_build.function_name}"
  retention_in_days = 14
}

# SQS trigger for process_build Lambda
resource "aws_lambda_event_source_mapping" "sqs_trigger" {
  event_source_arn                   = aws_sqs_queue.build_queue.arn
  function_name                      = aws_lambda_function.process_build.arn
  batch_size                         = 1
  maximum_batching_window_in_seconds = 0
  enabled                            = true
}

# -----------------------------------------------------------------------------
# Check Status Lambda
# Returns build status and generates presigned download URLs
# -----------------------------------------------------------------------------

resource "aws_lambda_function" "check_status" {
  function_name    = "${local.name_prefix}-check-status"
  filename         = data.archive_file.check_status.output_path
  source_code_hash = data.archive_file.check_status.output_base64sha256
  handler          = "index.handler"
  runtime          = "python3.13"
  timeout          = 15
  memory_size      = 128
  role             = aws_iam_role.lambda_status.arn

  environment {
    variables = {
      DYNAMODB_TABLE     = aws_dynamodb_table.builds.name
      S3_BUCKET          = aws_s3_bucket.artifacts.id
      ARTIFACT_TTL_HOURS = tostring(var.artifact_ttl_hours)
    }
  }

  tags = {
    Name = "${local.name_prefix}-check-status"
  }
}

resource "aws_cloudwatch_log_group" "check_status" {
  name              = "/aws/lambda/${aws_lambda_function.check_status.function_name}"
  retention_in_days = 14
}
