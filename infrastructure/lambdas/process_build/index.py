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
ARM64_INSTANCE_TYPE = os.environ.get("EC2_ARM64_INSTANCE_TYPE", "c7g.xlarge")
LAUNCH_TEMPLATE_ID = os.environ.get("LAUNCH_TEMPLATE_ID")
LAUNCH_TEMPLATE_ID_ARM64 = os.environ.get("LAUNCH_TEMPLATE_ID_ARM64")
MAX_BUILD_MINUTES = int(os.environ.get("MAX_BUILD_MINUTES", "30"))
PROJECT_NAME = os.environ.get("PROJECT_NAME", "lambda-layer-builder")
LOG_GROUP_NAME = os.environ.get("EC2_BUILD_LOG_GROUP", "/lambda-layer-builder/prod/ec2-builds")


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
    """Launch one native EC2 Spot instance per requested architecture."""
    build_id = message["build_id"]
    python_version = message["python_version"]
    architectures = message["architectures"]
    requirements = message["requirements"]
    single_file = message.get("single_file", True)

    print(f"Processing build {build_id}: Python {python_version}, "
          f"arch={architectures}, single_file={single_file}")

    _update_status(build_id, "PROCESSING")

    subnet_id = random.choice(SUBNET_IDS)
    instance_ids = []

    for arch in architectures:
        instance_id = _launch_arch_instance(
            build_id=build_id,
            arch=arch,
            python_version=python_version,
            requirements=requirements,
            single_file=single_file,
            subnet_id=subnet_id,
        )
        instance_ids.append(f"{arch}:{instance_id}")

    # Record all launched instance IDs
    table = dynamodb.Table(TABLE_NAME)
    table.update_item(
        Key={"buildId": build_id},
        UpdateExpression="SET instance_ids = :ids",
        ExpressionAttributeValues={":ids": instance_ids},
    )


def _launch_arch_instance(build_id, arch, python_version, requirements, single_file, subnet_id):
    """Launch a native EC2 Spot instance for a single architecture."""
    if arch == "arm64":
        template_id = LAUNCH_TEMPLATE_ID_ARM64
        instance_type = ARM64_INSTANCE_TYPE
    else:
        template_id = LAUNCH_TEMPLATE_ID
        instance_type = EC2_INSTANCE_TYPE

    user_data = _generate_user_data(
        build_id=build_id,
        arch=arch,
        python_version=python_version,
        requirements=requirements,
        single_file=single_file,
        log_group_name=LOG_GROUP_NAME,
    )

    try:
        response = ec2.run_instances(
            LaunchTemplate={"LaunchTemplateId": template_id},
            InstanceType=instance_type,
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
                        {"Key": "Name", "Value": f"builder-{build_id[:8]}-{arch}"},
                        {"Key": "BuildId", "Value": build_id},
                        {"Key": "Architecture", "Value": arch},
                        {"Key": "Project", "Value": PROJECT_NAME},
                        {"Key": "AutoTerminate", "Value": "true"},
                    ],
                }
            ],
        )

        instance_id = response["Instances"][0]["InstanceId"]
        print(f"Launched {arch} Spot instance {instance_id} (type={instance_type}) for build {build_id}")
        return instance_id

    except Exception as e:
        error_msg = str(e)
        print(f"Failed to launch {arch} instance for build {build_id}: {error_msg}")
        if "InsufficientInstanceCapacity" in error_msg or "SpotMaxPriceTooLow" in error_msg:
            _update_status(build_id, "FAILED",
                           error=f"Spot capacity unavailable for {arch}. Please retry.")
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


def _generate_user_data(build_id, arch, python_version, requirements, single_file, log_group_name):
    """Generate the EC2 user-data bash script for a single-architecture build."""
    req_escaped = requirements.replace("\\", "\\\\").replace("'", "'\\''")
    if arch == "arm64":
        arch_label = "arm64"
        platform = "linux/arm64"
    else:
        arch_label = "amd64"
        platform = "linux/amd64"
    single_file_str = "true" if single_file else "false"

    return f"""#!/bin/bash
set -euo pipefail
exec > >(tee /var/log/build.log) 2>&1

echo "$(date): === Lambda Layer Builder ==="
echo "Build ID: {build_id}"
echo "Python: {python_version}"
echo "Architecture: {arch}"
echo "Single file: {single_file_str}"

# --- Instance metadata (IMDSv2) ---
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \\
  -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
REGION=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \\
  http://169.254.169.254/latest/meta-data/placement/region)
INSTANCE_ID=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \\
  http://169.254.169.254/latest/meta-data/instance-id)

export AWS_DEFAULT_REGION="$REGION"

# --- Safety: auto-terminate after {MAX_BUILD_MINUTES} minutes ---
(sleep {MAX_BUILD_MINUTES * 60} && \\
  echo "$(date): TIMEOUT - self-terminating" && \\
  python3 -c "
import boto3
from decimal import Decimal
table = boto3.resource('dynamodb', region_name='$REGION').Table('{TABLE_NAME}')
table.update_item(
    Key={{'buildId': '{build_id}'}},
    UpdateExpression='ADD pending_arches :n SET #s = :f, error_message = :e',
    ExpressionAttributeNames={{'#s': 'status'}},
    ExpressionAttributeValues={{':n': Decimal('-1'), ':f': 'FAILED', ':e': 'Build timed out after {MAX_BUILD_MINUTES} minutes ({arch})'}},
)
" && \\
  aws ec2 terminate-instances --instance-ids "$INSTANCE_ID") &
WATCHDOG_PID=$!

cleanup() {{
    echo "$(date): Cleanup initiated"
    kill $WATCHDOG_PID 2>/dev/null || true
    echo "$(date): Self-terminating instance $INSTANCE_ID"
    aws ec2 terminate-instances --instance-ids "$INSTANCE_ID" 2>/dev/null || true
}}
trap cleanup EXIT

# --- Install Docker and CloudWatch Agent ---
echo "$(date): Installing Docker and CloudWatch Agent..."
dnf install -y docker git aws-cli amazon-cloudwatch-agent 2>/dev/null || yum install -y docker git aws-cli
systemctl start docker
systemctl enable docker

# --- Configure CloudWatch Logs streaming ---
echo "$(date): Configuring CloudWatch Logs streaming..."
mkdir -p /opt/aws/amazon-cloudwatch-agent/etc
cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json << 'CWEOF'
{{
  "logs": {{
    "logs_collected": {{
      "files": {{
        "collect_list": [
          {{
            "file_path": "/var/log/build.log",
            "log_group_name": "{log_group_name}",
            "log_stream_name": "{build_id}",
            "timezone": "UTC",
            "timestamp_format": "%Y-%m-%dT%H:%M:%S"
          }}
        ]
      }}
    }}
  }}
}}
CWEOF

/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \\
    -a fetch-config -m ec2 \\
    -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json \\
    -s 2>/dev/null \\
  && echo "$(date): CloudWatch streaming active \u2192 {log_group_name}/{build_id}" \\
  || echo "$(date): WARNING: CloudWatch agent failed to start"

# --- Create requirements file ---
mkdir -p /build/input /build/output
cat > /build/input/requirements.txt << 'REQUIREMENTS_EOF'
{requirements}
REQUIREMENTS_EOF

echo "$(date): Requirements:"
cat /build/input/requirements.txt

# --- Build ---
DOCKER_IMAGE_PREFIX="{DOCKER_IMAGE_PREFIX}"
S3_BUCKET="{S3_BUCKET}"
BUILD_ID="{build_id}"
PYTHON_VERSION="{python_version}"
SINGLE_FILE="{single_file_str}"
ARCH="{arch}"
PLATFORM="{platform}"
ARCH_LABEL="{arch_label}"

echo ""
echo "$(date): =========================================="
echo "$(date): Building for $ARCH ($PLATFORM)"
echo "$(date): =========================================="

image_tag="${{DOCKER_IMAGE_PREFIX}}:python${{PYTHON_VERSION}}-${{ARCH_LABEL}}-latest"

if docker pull --platform "$PLATFORM" "$image_tag" 2>/dev/null; then
    echo "$(date): Using pre-built image: $image_tag"
else
    echo "$(date): Pre-built image unavailable, building locally..."
    git clone {GITHUB_REPO_URL} /build/repo
    dockerfile="/build/repo/Dockerfile.al2023"
    if [[ "$PYTHON_VERSION" == "3.10" || "$PYTHON_VERSION" == "3.11" ]]; then
        dockerfile="/build/repo/Dockerfile.al2"
    fi
    docker buildx create --use --name builder 2>/dev/null || true
    docker buildx build \\
        --platform "$PLATFORM" \\
        --build-arg PYTHON_VERSION=$PYTHON_VERSION \\
        -t "$image_tag" \\
        --load \\
        -f "$dockerfile" \\
        /build/repo/
fi

if [ "$SINGLE_FILE" = "true" ]; then
    docker run --rm \\
        --platform "$PLATFORM" \\
        -e SINGLE_FILE=true \\
        -v /build/input/requirements.txt:/input/requirements.txt \\
        -v /build/output:/package \\
        "$image_tag"
else
    docker run --rm \\
        --platform "$PLATFORM" \\
        -v /build/input/requirements.txt:/input/requirements.txt \\
        -v /build/output:/package \\
        "$image_tag"
fi

echo "$(date): Build complete for $ARCH"

# --- Upload artifacts to S3 ---
echo ""
echo "$(date): Uploading artifacts to S3..."
S3_KEYS=""

for zip_file in /build/output/*.zip; do
    if [ -f "$zip_file" ]; then
        filename=$(basename "$zip_file")
        s3_key="builds/$BUILD_ID/$filename"
        aws s3 cp "$zip_file" "s3://$S3_BUCKET/$s3_key"
        echo "$(date): Uploaded: s3://$S3_BUCKET/$s3_key"
        if [ -n "$S3_KEYS" ]; then
            S3_KEYS="$S3_KEYS,$s3_key"
        else
            S3_KEYS="$s3_key"
        fi
    fi
done

if [ -z "$S3_KEYS" ]; then
    echo "$(date): ERROR - No zip files produced!"
    python3 -c "
import boto3
from decimal import Decimal
table = boto3.resource('dynamodb', region_name='$REGION').Table('{TABLE_NAME}')
table.update_item(
    Key={{'buildId': '{build_id}'}},
    UpdateExpression='ADD pending_arches :n SET #s = :f, error_message = :e',
    ExpressionAttributeNames={{'#s': 'status'}},
    ExpressionAttributeValues={{':n': Decimal('-1'), ':f': 'FAILED', ':e': 'Build produced no output files ({arch})'}},
)
"
    exit 1
fi

# --- Atomically record completion in DynamoDB ---
# ADD arch_s3_keys (StringSet) and decrement pending_arches.
# The last architecture to complete (pending_arches reaches 0) sets COMPLETED.
# Errors here are caught inside the Python script so DynamoDB is always updated,
# even if the update itself fails (the build is then marked FAILED instead of
# being left stuck in PROCESSING with orphaned S3 files).
export _BUILD_S3_KEYS="$S3_KEYS"
export _BUILD_COMPLETED_AT="$(date +%s)"

python3 << 'PYEOF'
import boto3, os, time, sys
from decimal import Decimal

region = os.environ['AWS_DEFAULT_REGION']
table_name = "{TABLE_NAME}"
build_id = "{build_id}"
arch = "{arch}"

s3_keys_str = os.environ.get('_BUILD_S3_KEYS', '')
completed_at = int(os.environ.get('_BUILD_COMPLETED_AT', '0'))
key_list = [k.strip() for k in s3_keys_str.split(',') if k.strip()]

table = boto3.resource('dynamodb', region_name=region).Table(table_name)


def _mark_failed(reason):
    # Best-effort: mark the build FAILED in DynamoDB.
    for attempt in range(3):
        try:
            table.update_item(
                Key={{'buildId': build_id}},
                UpdateExpression='SET #s = :f, error_message = :e',
                ExpressionAttributeNames={{'#s': 'status'}},
                ExpressionAttributeValues={{':f': 'FAILED', ':e': reason}},
            )
            print('Marked build FAILED: ' + reason)
            return
        except Exception as ex:
            print('WARNING: _mark_failed attempt ' + str(attempt + 1) + ' failed: ' + str(ex))
            time.sleep(2 ** attempt)
    print('ERROR: could not update DynamoDB after repeated failures')


try:
    # Step 1: atomically add this arch's S3 keys and decrement the pending counter.
    resp = table.update_item(
        Key={{'buildId': build_id}},
        UpdateExpression='ADD arch_s3_keys :k, pending_arches :n',
        ExpressionAttributeValues={{
            ':k': set(key_list),
            ':n': Decimal('-1'),
        }},
        ReturnValues='ALL_NEW',
    )
except Exception as e:
    # S3 upload already succeeded; emit an error but mark the build FAILED so
    # it never stays stuck in PROCESSING.
    msg = arch + ' uploaded to S3 but DynamoDB key-registration failed: ' + str(e)
    print('ERROR: ' + msg)
    _mark_failed(msg)
    sys.exit(0)  # Exit cleanly so bash set -e doesn't re-trigger the cleanup trap

pending = int(resp['Attributes'].get('pending_arches', 1))
if pending <= 0:
    # Step 2: all architectures finished — set the final COMPLETED status.
    all_keys_set = resp['Attributes'].get('arch_s3_keys', set())
    all_keys = ','.join(sorted(all_keys_set))
    fc = len(all_keys_set)

    for attempt in range(3):
        try:
            table.update_item(
                Key={{'buildId': build_id}},
                UpdateExpression='SET #s = :s, s3_keys = :k, completed_at = :t, file_count = :fc',
                ExpressionAttributeNames={{'#s': 'status'}},
                ExpressionAttributeValues={{
                    ':s': 'COMPLETED',
                    ':k': all_keys,
                    ':t': completed_at,
                    ':fc': fc,
                }},
            )
            print('Build COMPLETED: ' + str(fc) + ' file(s), keys: ' + all_keys)
            break
        except Exception as e:
            if attempt < 2:
                print('WARNING: COMPLETED update attempt ' + str(attempt + 1) + ' failed, retrying: ' + str(e))
                time.sleep(2 ** attempt)
            else:
                # pending_arches is already 0 so no other instance will retry;
                # mark FAILED so the caller gets a definitive answer.
                msg = 'S3 upload succeeded but failed to set COMPLETED status: ' + str(e)
                print('ERROR: ' + msg)
                _mark_failed(msg)
else:
    print(arch + ' done, ' + str(pending) + ' arch(es) still pending')
PYEOF

echo ""
echo "$(date): =========================================="
echo "$(date): {arch} build finished successfully!"
echo "$(date): =========================================="

# Instance self-terminates via EXIT trap
"""
