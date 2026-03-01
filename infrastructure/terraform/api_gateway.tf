# =============================================================================
# API Gateway (HTTP API v2)
# =============================================================================
# HTTP API with CORS support. Routes:
#   POST /builds         → submit_build Lambda
#   GET  /builds/{buildId} → check_status Lambda
# =============================================================================

resource "aws_apigatewayv2_api" "api" {
  name          = "${local.name_prefix}-api"
  protocol_type = "HTTP"
  description   = "Lambda Python Layer Builder API"

  cors_configuration {
    allow_origins = var.allowed_origins
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization"]
    max_age       = 86400
  }
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.api.id
  name        = "$default"
  auto_deploy = true

  default_route_settings {
    throttling_rate_limit  = var.api_throttle_rate
    throttling_burst_limit = var.api_throttle_burst
  }

  access_log_settings {
    destination_arn = aws_cloudwatch_log_group.api_gateway.arn
    format = jsonencode({
      requestId      = "$context.requestId"
      ip             = "$context.identity.sourceIp"
      requestTime    = "$context.requestTime"
      httpMethod     = "$context.httpMethod"
      routeKey       = "$context.routeKey"
      status         = "$context.status"
      protocol       = "$context.protocol"
      responseLength = "$context.responseLength"
      errorMessage   = "$context.error.message"
    })
  }
}

resource "aws_cloudwatch_log_group" "api_gateway" {
  name              = "/aws/apigateway/${local.name_prefix}-api"
  retention_in_days = 14
}

# -----------------------------------------------------------------------------
# POST /builds - Submit Build
# -----------------------------------------------------------------------------

resource "aws_apigatewayv2_integration" "submit_build" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.submit_build.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "submit_build" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "POST /builds"
  target    = "integrations/${aws_apigatewayv2_integration.submit_build.id}"
}

resource "aws_lambda_permission" "submit_build_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.submit_build.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}

# -----------------------------------------------------------------------------
# GET /builds/{buildId} - Check Status
# -----------------------------------------------------------------------------

resource "aws_apigatewayv2_integration" "check_status" {
  api_id                 = aws_apigatewayv2_api.api.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.check_status.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "check_status" {
  api_id    = aws_apigatewayv2_api.api.id
  route_key = "GET /builds/{buildId}"
  target    = "integrations/${aws_apigatewayv2_integration.check_status.id}"
}

resource "aws_lambda_permission" "check_status_apigw" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.check_status.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.api.execution_arn}/*/*"
}
