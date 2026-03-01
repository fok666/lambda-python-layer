"""
Process Build Lambda
Triggered by SQS. Launches an EC2 Spot instance with a user-data script
that builds the Lambda layer packages using Docker containers.

The EC2 instance:
1. Installs Docker
2. Pulls pre-built images from GHCR (or builds locally as fallback)
3. Runs the Docker container to build the Lambda layer zips
4. Uploads artifacts to S3
5. Updates DynamoDB with status and S3 keys
6. Self-terminates
"""

import json
import os
import base64
import random
import boto3

ec2 = boto3.client("ec2")
dynamodb = boto3.resource("dynamodb")

TABLE_NAME = os.environ["DYNAMODB_TABLE"]
S3_BUCKET = os.environ["S3_BUCKET"]
SUBNET_IDS = os.environ["SUBNET_IDS"].split(",")
SECURITY_GROUP_ID = os.environ["SECURITY_GROUP_ID"]
LAUNCH_TEMPLATE_ID = os.environ["LAUNCH_TEMPLATE_ID"]
INSTANCE_PROFILE_ARN = os.environ["INSTANCE_PROFILE_ARN"]
DOCKER_IMAGE_PREFIX = os.environ.get("DOCKER_IMAGE_PREFIX", "ghcr.io/fok666/lambda-python-layer")
GITHUB_REPO_URL = os.environ.get("GITHUB_REPO_URL", "https://github.com/fok666/lambda-python-layer.git")
EC2_INSTANCE_TYPE = os.environ.get("EC2_INSTANCE_TYPE", "c5.xlarge")
MAX_BUILD_MINUTES = int(os.environ.get("MAX_BUILD_MINUTES", "30"))
PROJECT_NAME = os.environ.get("PROJECT_NAME", "lambda-layer-builder")


def handler(event, context):
    """Process SQS messages containing build requests."""
    for record in event["Records"]:
        message = json.loads(record["body"])
        try:
            _process_build(message)
        except Exception as e:
            print(f"ERROR processing build {message.get('build_id', 'unknown')}: {e}")
            _update_status(message.get("build_id"), "FAILED", error=str(e))
            raise


def _process_build(message):
    """Launch EC2 Spot instance to perform the build."""
    build_id = message["build_id"]
    python_version = message["python_version"]
    architectures = message["architectures"]
    requirements = message["requirements"]
    single_file = message.get("single_file", True)

    print(f"Processing build {build_id}: Python {python_version}, "
          f"arch={architectures}, single_file={single_file}")

    # Update status to PROCESSING
    _update_status(build_id, "PROCESSING")

    # Generate user-data script
    user_data = _generate_user_data(
        build_id=build_id,
        python_version=python_version,
        architectures=architectures,
        requirements=requirements,
        single_file=single_file,
    )

    # Pick a random subnet for AZ diversity
    subnet_id = random.choice(SUBNET_IDS)

    # Launch Spot instance
    try:
        response = ec2.run_instances(
            LaunchTemplate={"LaunchTemplateId": LAUNCH_TEMPLATE_ID},
            InstanceType=EC2_INSTANCE_TYPE,
            MinCount=1,
            MaxCount=1,
            SubnetId=subnet_id,
            InstanceMarketOptions={
                "MarketType": "spot",
                "SpotOptions": {
                    "SpotInstanceType": "one-time",
                    "InstanceInterruptionBehavior": "terminate",
                },
            },
            UserData=base64.b64encode(user_data.encode()).decode(),
            TagSpecifications=[
                {
                    "ResourceType": "instance",
                    "Tags": [
                        {"Key": "Name", "Value": f"builder-{build_id[:8]}"},
                        {"Key": "BuildId", "Value": build_id},
                        {"Key": "Project", "Value": PROJECT_NAME},
                        {"Key": "AutoTerminate", "Value": "true"},
                    ],
                }
            ],
        )

        instance_id = response["Instances"][0]["InstanceId"]
        print(f"Launched Spot instance {instance_id} for build {build_id}")

        # Store instance ID in DynamoDB
        table = dynamodb.Table(TABLE_NAME)
        table.update_item(
            Key={"buildId": build_id},
            UpdateExpression="SET instance_id = :i",
            ExpressionAttributeValues={":i": instance_id},
        )

    except Exception as e:
        error_msg = str(e)
        print(f"Failed to launch instance for build {build_id}: {error_msg}")

        # If spot capacity unavailable, mark as failed with helpful message
        if "InsufficientInstanceCapacity" in error_msg or "SpotMaxPriceTooLow" in error_msg:
            _update_status(build_id, "FAILED",
                           error="Spot instance capacity unavailable. Please retry.")
        else:
            _update_status(build_id, "FAILED", error=error_msg)
        raise


def _update_status(build_id, status, error=None):
    """Update build status in DynamoDB."""
    if not build_id:
        return
    table = dynamodb.Table(TABLE_NAME)
    update_expr = "SET #s = :s"
    attr_names = {"#s": "status"}
    attr_values = {":s": status}

    if error:
        update_expr += ", error_message = :e"
        attr_values[":e"] = error

    try:
        table.update_item(
            Key={"buildId": build_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=attr_names,
            ExpressionAttributeValues=attr_values,
        )
    except Exception as e:
        print(f"Failed to update status for {build_id}: {e}")


def _generate_user_data(build_id, python_version, architectures, requirements, single_file):
    """Generate the EC2 user-data bash script for the build."""
    req_escaped = requirements.replace("\\", "\\\\").replace("'", "'\\''")
    arches_str = " ".join(architectures)
    single_file_str = "true" if single_file else "false"

    return f"""#!/bin/bash
set -euo pipefail
exec > >(tee /var/log/build.log) 2>&1

echo "$(date): === Lambda Layer Builder ==="
echo "Build ID: {build_id}"
echo "Python: {python_version}"
echo "Architectures: {arches_str}"
echo "Single file: {single_file_str}"

# --- Instance metadata (IMDSv2) ---
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/placement/region)
INSTANCE_ID=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/instance-id)

export AWS_DEFAULT_REGION="$REGION"

# --- Safety: auto-terminate after {MAX_BUILD_MINUTES} minutes ---
(sleep {MAX_BUILD_MINUTES * 60} && \
  echo "$(date): TIMEOUT - self-terminating" && \
  aws dynamodb update-item \
    --table-name "{TABLE_NAME}" \
    --key '{{"buildId": {{"S": "{build_id}"}}}}' \
    --update-expression "SET #s = :s, error_message = :e" \
    --expression-attribute-names '{{"#s": "status"}}' \
    --expression-attribute-values '{{":s": {{"S": "FAILED"}}, ":e": {{"S": "Build timed out after {MAX_BUILD_MINUTES} minutes"}}}}' && \
  aws ec2 terminate-instances --instance-ids "$INSTANCE_ID") &
WATCHDOG_PID=$!

# --- Helper functions ---
update_status() {{
    local status=$1
    local extra="${{2:-}}"
    aws dynamodb update-item \
        --table-name "{TABLE_NAME}" \
        --key '{{"buildId": {{"S": "{build_id}"}}}}' \
        --update-expression "SET #s = :s${{extra}}" \
        --expression-attribute-names '{{"#s": "status"}}' \
        --expression-attribute-values "$(echo '{{":s": {{"S": "'"$status"'"}}}}' )" \
        2>/dev/null || true
}}

cleanup() {{
    echo "$(date): Cleanup initiated"
    kill $WATCHDOG_PID 2>/dev/null || true
    echo "$(date): Self-terminating instance $INSTANCE_ID"
    aws ec2 terminate-instances --instance-ids "$INSTANCE_ID" 2>/dev/null || true
}}
trap cleanup EXIT

# --- Install Docker ---
echo "$(date): Installing Docker..."
dnf install -y docker git aws-cli 2>/dev/null || yum install -y docker git aws-cli
systemctl start docker
systemctl enable docker

# Enable QEMU for cross-architecture builds
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes 2>/dev/null || true

# --- Create requirements file ---
mkdir -p /build/input /build/output
cat > /build/input/requirements.txt << 'REQUIREMENTS_EOF'
{requirements}
REQUIREMENTS_EOF

echo "$(date): Requirements:"
cat /build/input/requirements.txt

# --- Configuration ---
DOCKER_IMAGE_PREFIX="{DOCKER_IMAGE_PREFIX}"
S3_BUCKET="{S3_BUCKET}"
BUILD_ID="{build_id}"
PYTHON_VERSION="{python_version}"
SINGLE_FILE="{single_file_str}"

# --- Build function ---
build_arch() {{
    local arch=$1
    local platform=""
    local arch_label=""

    if [ "$arch" = "x86_64" ]; then
        platform="linux/amd64"
        arch_label="amd64"
    else
        platform="linux/arm64"
        arch_label="arm64"
    fi

    echo ""
    echo "$(date): ========================================="
    echo "$(date): Building for $arch ($platform)"
    echo "$(date): ========================================="

    local image_tag="${{DOCKER_IMAGE_PREFIX}}:python${{PYTHON_VERSION}}-${{arch_label}}-latest"

    # Try pre-built image first, fall back to local build
    if docker pull --platform "$platform" "$image_tag" 2>/dev/null; then
        echo "$(date): Using pre-built image: $image_tag"
    else
        echo "$(date): Pre-built image unavailable, building locally..."

        if [ ! -d /build/repo ]; then
            git clone {GITHUB_REPO_URL} /build/repo
        fi

        # Select correct Dockerfile based on Python version
        local dockerfile="/build/repo/Dockerfile.al2023"
        if [[ "$PYTHON_VERSION" == "3.10" || "$PYTHON_VERSION" == "3.11" ]]; then
            dockerfile="/build/repo/Dockerfile.al2"
        fi

        docker buildx create --use --name builder 2>/dev/null || true
        docker buildx build \
            --platform "$platform" \
            --build-arg PYTHON_VERSION=$PYTHON_VERSION \
            -t "$image_tag" \
            --load \
            -f "$dockerfile" \
            /build/repo/
    fi

    # Run the build container
    if [ "$SINGLE_FILE" = "true" ]; then
        docker run --rm \
            --platform "$platform" \
            -e SINGLE_FILE=true \
            -v /build/input/requirements.txt:/input/requirements.txt \
            -v /build/output:/package \
            "$image_tag"
    else
        docker run --rm \
            --platform "$platform" \
            -v /build/input/requirements.txt:/input/requirements.txt \
            -v /build/output:/package \
            "$image_tag"
    fi

    echo "$(date): Build complete for $arch"
}}

# --- Execute builds ---
for arch in {arches_str}; do
    build_arch "$arch"
done

# --- Upload artifacts to S3 ---
echo ""
echo "$(date): Uploading artifacts to S3..."
S3_KEYS=""
FILE_COUNT=0

for zip_file in /build/output/*.zip; do
    if [ -f "$zip_file" ]; then
        filename=$(basename "$zip_file")
        s3_key="builds/$BUILD_ID/$filename"
        aws s3 cp "$zip_file" "s3://$S3_BUCKET/$s3_key"
        echo "$(date): Uploaded: s3://$S3_BUCKET/$s3_key ($(du -h "$zip_file" | cut -f1))"

        if [ -n "$S3_KEYS" ]; then
            S3_KEYS="$S3_KEYS,$s3_key"
        else
            S3_KEYS="$s3_key"
        fi
        FILE_COUNT=$((FILE_COUNT + 1))
    fi
done

if [ "$FILE_COUNT" -eq 0 ]; then
    echo "$(date): ERROR - No zip files produced!"
    aws dynamodb update-item \
        --table-name "{TABLE_NAME}" \
        --key '{{"buildId": {{"S": "{build_id}"}}}}' \
        --update-expression "SET #s = :s, error_message = :e" \
        --expression-attribute-names '{{"#s": "status"}}' \
        --expression-attribute-values '{{":s": {{"S": "FAILED"}}, ":e": {{"S": "Build produced no output files"}}}}'
    exit 1
fi

# --- Update DynamoDB with completion ---
COMPLETED_AT=$(date +%s)
aws dynamodb update-item \
    --table-name "{TABLE_NAME}" \
    --key '{{"buildId": {{"S": "{build_id}"}}}}' \
    --update-expression "SET #s = :s, s3_keys = :k, completed_at = :t, file_count = :fc" \
    --expression-attribute-names '{{"#s": "status"}}' \
    --expression-attribute-values '{{":s": {{"S": "COMPLETED"}}, ":k": {{"S": "'"$S3_KEYS"'"}}, ":t": {{"N": "'"$COMPLETED_AT"'"}}, ":fc": {{"N": "'"$FILE_COUNT"'"}}}}'

echo ""
echo "$(date): ========================================="
echo "$(date): Build completed successfully!"
echo "$(date): Files: $FILE_COUNT"
echo "$(date): S3 Keys: $S3_KEYS"
echo "$(date): ========================================="

# Instance will self-terminate via the EXIT trap
"""
