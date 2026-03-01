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
import re
import boto3

dynamodb = boto3.resource("dynamodb")
sqs = boto3.client("sqs")

TABLE_NAME = os.environ["DYNAMODB_TABLE"]
QUEUE_URL = os.environ["SQS_QUEUE_URL"]
ARTIFACT_TTL_HOURS = int(os.environ.get("ARTIFACT_TTL_HOURS", "24"))

VALID_PYTHON_VERSIONS = ["3.10", "3.11", "3.12", "3.13", "3.14"]
VALID_ARCHITECTURES = ["x86_64", "arm64"]
MAX_REQUIREMENTS_LENGTH = 10000  # 10KB max
MAX_ACTIVE_BUILDS = int(os.environ.get("MAX_ACTIVE_BUILDS", "10"))


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

    req_error = _validate_requirements(requirements)
    if req_error:
        return _response(400, {"error": req_error})

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

    # --- Enforce concurrent-build cap ---
    # Sum approximate queued + in-flight messages to estimate active builds.
    # This prevents a single caller from queueing unbounded EC2 Spot launches.
    try:
        attrs = sqs.get_queue_attributes(
            QueueUrl=QUEUE_URL,
            AttributeNames=[
                "ApproximateNumberOfMessages",
                "ApproximateNumberOfMessagesNotVisible",
            ],
        )["Attributes"]
        active = (
            int(attrs.get("ApproximateNumberOfMessages", 0))
            + int(attrs.get("ApproximateNumberOfMessagesNotVisible", 0))
        )
        if active >= MAX_ACTIVE_BUILDS:
            return _response(
                429,
                {
                    "error": (
                        f"Build queue is at capacity ({MAX_ACTIVE_BUILDS} concurrent builds). "
                        "Please retry later."
                    )
                },
            )
    except Exception as e:
        print(f"WARNING: could not check queue depth: {e}")
        # Fail open — allow the build rather than blocking on a transient error.

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
        # Tracks how many per-arch EC2 instances must complete before COMPLETED
        "pending_arches": len(architectures),
    })

    # --- Queue for processing ---
    send_kwargs = {
        "QueueUrl": QUEUE_URL,
        "MessageBody": json.dumps({
            "build_id": build_id,
            "python_version": python_version,
            "architectures": architectures,
            "requirements": requirements,
            "single_file": single_file,
        }),
    }
    if QUEUE_URL.endswith(".fifo"):
        send_kwargs["MessageGroupId"] = build_id[:8]

    sqs.send_message(**send_kwargs)

    return _response(200, {
        "build_id": build_id,
        "status": "QUEUED",
        "python_version": python_version,
        "architectures": architectures,
        "single_file": single_file,
        "expires_at": expires_at,
    })


def _validate_requirements(requirements: str):
    """
    Validate requirements.txt content.

    Returns an error string if invalid, or None if the content is acceptable.

    Rules:
    - URL-based installs (git+, http://, https://, file://, vcs+...) are rejected.
      They bypass PyPI and allow arbitrary code to be pulled from any host.
    - Recursive includes (-r / --requirement) and constraint files
      (-c / --constraint) are rejected to prevent file-system reads on the
      builder instance.
    - Lines with obvious shell metacharacters (;, |, &, $, `) are rejected
      as a defence-in-depth measure against injection in downstream tools.
    """
    URL_PREFIXES = ("git+", "http://", "https://", "file://", "svn+", "hg+", "bzr+")
    BLOCKED_FLAGS = ("-r ", "-r\t", "--requirement", "-c ", "-c\t", "--constraint")
    SHELL_META = re.compile(r'[;|&$`]')

    for lineno, raw_line in enumerate(requirements.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if any(line.startswith(p) for p in URL_PREFIXES):
            return (
                f"Line {lineno}: URL-based requirements are not allowed. "
                "Specify packages by name and version (e.g., requests==2.32.4)."
            )
        if any(line.startswith(f) for f in BLOCKED_FLAGS):
            return (
                f"Line {lineno}: recursive includes (-r) and constraint files (-c) "
                "are not allowed."
            )
        if SHELL_META.search(line):
            return (
                f"Line {lineno}: shell metacharacters (;, |, &, $, `) are not "
                "allowed in requirements."
            )
    return None


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
