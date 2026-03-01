# =============================================================================
# Outputs
# =============================================================================

output "api_url" {
  description = "API Gateway URL. Configure this in the GitHub Pages frontend."
  value       = aws_apigatewayv2_api.api.api_endpoint
}

output "s3_bucket_name" {
  description = "S3 bucket name for build artifacts."
  value       = aws_s3_bucket.artifacts.id
}

output "dynamodb_table_name" {
  description = "DynamoDB table name for build tracking."
  value       = aws_dynamodb_table.builds.name
}

output "sqs_queue_url" {
  description = "SQS queue URL for build requests."
  value       = aws_sqs_queue.build_queue.url
}

output "vpc_id" {
  description = "VPC ID."
  value       = aws_vpc.main.id
}

output "submit_build_lambda" {
  description = "Submit build Lambda function name."
  value       = aws_lambda_function.submit_build.function_name
}

output "process_build_lambda" {
  description = "Process build Lambda function name."
  value       = aws_lambda_function.process_build.function_name
}

output "check_status_lambda" {
  description = "Check status Lambda function name."
  value       = aws_lambda_function.check_status.function_name
}

output "github_pages_config" {
  description = "Paste this API URL into the GitHub Pages settings panel."
  value       = "API URL: ${aws_apigatewayv2_api.api.api_endpoint}"
}
