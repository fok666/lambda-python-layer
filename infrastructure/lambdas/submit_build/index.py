"""
Submit Build Lambda
Validates the build request, creates a DynamoDB record, and sends
the message to SQS for processing.

API: POST /builds
Body: {
    "requirements": "numpy==1.26.4\nrequests==2.32.4",
    "python_version": "3.13",
    "architectures": ["x86_64", "arm64"],
    "single_file": true
}
"""

import json
import uuid
import time
import os
import boto3

dynamodb = boto3.resource("dynamodb")
sqs = boto3.client("sqs")

TABLE_NAME = os.environ["DYNAMODB_TABLE"]
QUEUE_URL = os.environ["SQS_QUEUE_URL"]
ARTIFACT_TTL_HOURS = int(os.environ.get("ARTIFACT_TTL_HOURS", "24"))

VALID_PYTHON_VERSIONS = ["3.10", "3.11", "3.12", "3.13", "3.14"]
VALID_ARCHITECTURES = ["x86_64", "arm64"]
MAX_REQUIREMENTS_LENGTH = 10000  # 10KB max


def handler(event, context):
    """Handle POST /builds requests."""
    try:
        body = json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return _response(400, {"error": "Invalid JSON body"})

    # --- Validate input ---
    requirements = body.get("requirements", "").strip()
    if not requirements:
        return _response(400, {"error": "requirements is required"})

    if len(requirements) > MAX_REQUIREMENTS_LENGTH:
        return _response(400, {
            "error": f"requirements too large (max {MAX_REQUIREMENTS_LENGTH} chars)"
        })

    python_version = body.get("python_version", "3.13")
    if python_version not in VALID_PYTHON_VERSIONS:
        return _response(400, {
            "error": f"Invalid python_version. Must be one of: {VALID_PYTHON_VERSIONS}"
        })

    architectures = body.get("architectures", ["x86_64"])
    if not isinstance(architectures, list) or len(architectures) == 0:
        return _response(400, {"error": "architectures must be a non-empty list"})

    for arch in architectures:
        if arch not in VALID_ARCHITECTURES:
            return _response(400, {
                "error": f"Invalid architecture: {arch}. Must be one of: {VALID_ARCHITECTURES}"
            })

    single_file = body.get("single_file", True)
    if not isinstance(single_file, bool):
        return _response(400, {"error": "single_file must be a boolean"})

    # --- Create build record ---
    build_id = str(uuid.uuid4())
    now = int(time.time())
    expires_at = now + (ARTIFACT_TTL_HOURS * 3600)

    table = dynamodb.Table(TABLE_NAME)
    table.put_item(Item={
        "buildId": build_id,
        "status": "QUEUED",
        "python_version": python_version,
        "architectures": architectures,
        "requirements": requirements,
        "single_file": single_file,
        "created_at": now,
        "expires_at": expires_at,
        "ttl": expires_at + 86400,  # DynamoDB TTL: 1 day after artifact expiry
    })

    # --- Queue for processing ---
    sqs.send_message(
        QueueUrl=QUEUE_URL,
        MessageBody=json.dumps({
            "build_id": build_id,
            "python_version": python_version,
            "architectures": architectures,
            "requirements": requirements,
            "single_file": single_file,
        }),
        MessageGroupId=build_id[:8] if QUEUE_URL.endswith(".fifo") else None,
    )

    return _response(200, {
        "build_id": build_id,
        "status": "QUEUED",
        "python_version": python_version,
        "architectures": architectures,
        "single_file": single_file,
        "expires_at": expires_at,
    })


def _response(status_code, body):
    """Create API Gateway response with CORS headers."""
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "POST,GET,OPTIONS",
        },
        "body": json.dumps(body),
    }
