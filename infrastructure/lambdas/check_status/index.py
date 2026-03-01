"""
Check Status Lambda
Returns the build status and generates presigned download URLs
for completed builds.

API: GET /builds/{buildId}
Response: {
    "build_id": "uuid",
    "status": "COMPLETED",
    "python_version": "3.13",
    "architectures": ["x86_64", "arm64"],
    "created_at": 1709312400,
    "expires_at": 1709398800,
    "files": [
        {
            "filename": "combined-python3.13-x86_64.zip",
            "download_url": "https://...",
            "architecture": "x86_64"
        }
    ]
}
"""

import json
import os
import re
import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
# Region must be explicit when generating presigned URLs with STS credentials.
# Without it boto3 defaults to us-east-1, causing a signature mismatch for
# buckets in other regions.
s3_client = boto3.client("s3", region_name=os.environ.get("AWS_REGION"))

TABLE_NAME = os.environ["DYNAMODB_TABLE"]
S3_BUCKET = os.environ["S3_BUCKET"]
ARTIFACT_TTL_HOURS = int(os.environ.get("ARTIFACT_TTL_HOURS", "24"))

# Presigned URL expiry matches artifact TTL (capped at 7 days for S3 limit)
PRESIGN_EXPIRY = min(ARTIFACT_TTL_HOURS * 3600, 604800)


def handler(event, context):
    """Handle GET /builds/{buildId} requests."""
    # Extract buildId from path parameters
    build_id = (event.get("pathParameters") or {}).get("buildId")

    if not build_id:
        return _response(400, {"error": "buildId is required"})

    # Validate UUID format
    uuid_pattern = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
    )
    if not uuid_pattern.match(build_id):
        return _response(400, {"error": "Invalid buildId format"})

    # Fetch build record
    table = dynamodb.Table(TABLE_NAME)
    try:
        result = table.get_item(Key={"buildId": build_id})
    except ClientError as e:
        print(f"DynamoDB error: {e}")
        return _response(500, {"error": "Failed to retrieve build status"})

    item = result.get("Item")
    if not item:
        return _response(404, {"error": "Build not found"})

    # Build base response
    response_body = {
        "build_id": item["buildId"],
        "status": item["status"],
        "python_version": item.get("python_version", "unknown"),
        "architectures": item.get("architectures", []),
        "single_file": item.get("single_file", True),
        "created_at": int(item.get("created_at", 0)),
        "expires_at": int(item.get("expires_at", 0)),
    }

    # Add error message if failed
    if item.get("error_message"):
        response_body["error_message"] = item["error_message"]

    # Add completed timestamp
    if item.get("completed_at"):
        response_body["completed_at"] = int(item["completed_at"])

    # Generate presigned download URLs for completed builds
    if item["status"] == "COMPLETED" and item.get("s3_keys"):
        s3_keys = item["s3_keys"].split(",")
        files = []

        for s3_key in s3_keys:
            s3_key = s3_key.strip()
            if not s3_key:
                continue

            filename = s3_key.split("/")[-1]
            architecture = _detect_architecture(filename)

            try:
                download_url = s3_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": S3_BUCKET, "Key": s3_key},
                    ExpiresIn=PRESIGN_EXPIRY,
                )
                files.append({
                    "filename": filename,
                    "download_url": download_url,
                    "architecture": architecture,
                    # s3_key intentionally omitted — callers only need the presigned URL
                })
            except ClientError as e:
                print(f"Failed to generate presigned URL for {s3_key}: {e}")
                files.append({
                    "filename": filename,
                    "architecture": architecture,
                    "error": "Failed to generate download URL",
                })

        response_body["files"] = files
        response_body["file_count"] = len(files)

    return _response(200, response_body)


def _detect_architecture(filename):
    """Detect architecture from filename."""
    filename_lower = filename.lower()
    if "x86_64" in filename_lower or "amd64" in filename_lower:
        return "x86_64"
    elif "aarch64" in filename_lower or "arm64" in filename_lower:
        return "arm64"
    return "unknown"


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
