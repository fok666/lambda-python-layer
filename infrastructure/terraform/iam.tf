# =============================================================================
# IAM Roles & Policies
# =============================================================================

# -----------------------------------------------------------------------------
# Lambda Execution Role - Submit Build
# -----------------------------------------------------------------------------

resource "aws_iam_role" "lambda_submit" {
  name = "${local.name_prefix}-lambda-submit"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "lambda_submit" {
  name = "${local.name_prefix}-lambda-submit-policy"
  role = aws_iam_role.lambda_submit.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
        ]
        Resource = aws_dynamodb_table.builds.arn
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
          "sqs:GetQueueAttributes",
        ]
        Resource = aws_sqs_queue.build_queue.arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Lambda Execution Role - Process Build (SQS consumer, launches EC2)
# -----------------------------------------------------------------------------

resource "aws_iam_role" "lambda_process" {
  name = "${local.name_prefix}-lambda-process"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "lambda_process" {
  name = "${local.name_prefix}-lambda-process-policy"
  role = aws_iam_role.lambda_process.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:UpdateItem",
        ]
        Resource = aws_dynamodb_table.builds.arn
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
        ]
        Resource = aws_sqs_queue.build_queue.arn
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:RunInstances",
          "ec2:CreateTags",
        ]
        Resource = "*"
      },
      {
        # Required to create AWSServiceRoleForEC2Spot on first Spot usage
        Effect = "Allow"
        Action = "iam:CreateServiceLinkedRole"
        Resource = "arn:aws:iam::*:role/aws-service-role/spot.amazonaws.com/AWSServiceRoleForEC2Spot"
        Condition = {
          StringLike = {
            "iam:AWSServiceName" = "spot.amazonaws.com"
          }
        }
      },
      {
        Effect   = "Allow"
        Action   = "iam:PassRole"
        Resource = aws_iam_role.ec2_builder.arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# Lambda Execution Role - Check Status
# -----------------------------------------------------------------------------

resource "aws_iam_role" "lambda_status" {
  name = "${local.name_prefix}-lambda-status"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "lambda_status" {
  name = "${local.name_prefix}-lambda-status-policy"
  role = aws_iam_role.lambda_status.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
        ]
        Resource = aws_dynamodb_table.builds.arn
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
        ]
        Resource = "${aws_s3_bucket.artifacts.arn}/builds/*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# -----------------------------------------------------------------------------
# EC2 Builder Instance Role
# -----------------------------------------------------------------------------

resource "aws_iam_role" "ec2_builder" {
  name = "${local.name_prefix}-ec2-builder"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "ec2.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "ec2_builder" {
  name = "${local.name_prefix}-ec2-builder-policy"
  role = aws_iam_role.ec2_builder.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:PutObjectAcl",
        ]
        Resource = "${aws_s3_bucket.artifacts.arn}/builds/*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:UpdateItem",
        ]
        Resource = aws_dynamodb_table.builds.arn
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:TerminateInstances",
        ]
        Resource = "*"
        Condition = {
          StringEquals = {
            "ec2:ResourceTag/Project" = var.project_name
          }
        }
      },
      {
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances",
        ]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:DescribeLogStreams",
        ]
        Resource = "${aws_cloudwatch_log_group.ec2_builds.arn}:*"
      }
    ]
  })
}

resource "aws_iam_instance_profile" "ec2_builder" {
  name = "${local.name_prefix}-ec2-builder"
  role = aws_iam_role.ec2_builder.name
}
