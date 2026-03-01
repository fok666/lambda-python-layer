# Lambda Python Layer Builder — Infrastructure

Serverless infrastructure that builds AWS Lambda Python layers on-demand using EC2 Spot instances and Docker, with a GitHub Pages frontend.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  GitHub Pages (docs/index.html)                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  requirements.txt │ Python version │ Architecture │ Submit │      │
│  └─────────────────────────┬──────────────────────────────────┘      │
└────────────────────────────┼─────────────────────────────────────────┘
                             │ POST /builds
                             ▼
┌──────────────────────────────────────────────────────────────────────┐
│  API Gateway (HTTP API)                                              │
│  POST /builds         → submit_build Lambda                          │
│  GET  /builds/{id}    → check_status Lambda                          │
└───────────┬──────────────────────────────────────┬───────────────────┘
            │                                      │
            ▼                                      ▼
┌───────────────────┐                  ┌───────────────────────┐
│  submit_build λ   │                  │  check_status λ       │
│  • Validates input│                  │  • Reads DynamoDB     │
│  • Creates record │                  │  • Generates presigned│
│  • Sends to SQS   │                  │    S3 download URLs   │
└─────────┬─────────┘                  └───────────┬───────────┘
          │                                        │
          ▼                                        ▼
┌───────────────────┐                  ┌───────────────────────┐
│  SQS Build Queue  │                  │  DynamoDB             │
│  (with DLQ)       │                  │  buildId | status     │
└─────────┬─────────┘                  │  s3_keys | TTL        │
          │                            └───────────────────────┘
          ▼                                        ▲
┌───────────────────┐                              │
│  process_build λ  │                              │
│  • Launches EC2   │                              │
│    Spot instance  │                              │
└─────────┬─────────┘                              │
          │                                        │
          ▼                                        │
┌──────────────────────────────────────────────────┼───────────────────┐
│  EC2 Spot Instance                               │                   │
│  ┌─────────────────────────────────┐             │                   │
│  │  1. Install Docker              │             │                   │
│  │  2. Pull/build Docker image     │             │                   │
│  │  3. Run container to build      │             │                   │
│  │     Lambda layer zip files      │             │                   │
│  │  4. Upload zips to S3  ─────────┼──┐          │                   │
│  │  5. Update DynamoDB status ─────┼──┼──────────┘                   │
│  │  6. Self-terminate              │  │                              │
│  └─────────────────────────────────┘  │                              │
└───────────────────────────────────────┼──────────────────────────────┘
                                        │
                                        ▼
                              ┌───────────────────┐
                              │  S3 Artifacts      │
                              │  builds/{id}/*.zip │
                              │  Lifecycle: 24h    │
                              └───────────────────┘
```

## Flow

1. **User** opens GitHub Pages, enters `requirements.txt`, selects Python version & architecture
2. **API Gateway** routes `POST /builds` to `submit_build` Lambda
3. **submit_build** validates input, creates DynamoDB record (QUEUED), sends SQS message
4. **SQS** triggers `process_build` Lambda
5. **process_build** launches an EC2 Spot instance with a user-data script
6. **EC2 instance** installs Docker, pulls pre-built images from GHCR (or builds from Dockerfile), runs the build, uploads zips to S3, updates DynamoDB (COMPLETED), self-terminates
7. **User** frontend polls `GET /builds/{id}` which returns status + presigned S3 download URLs
8. **Artifacts** auto-expire from S3 after configurable TTL (default 24h)

## Cost Estimate

| Component | Cost | Notes |
|-----------|------|-------|
| EC2 Spot (c5.xlarge) | ~$0.04/hr | ~$0.01 per build (15 min avg) |
| S3 | ~$0.023/GB/month | Artifacts auto-expire |
| Lambda | ~$0.20/1M requests | Minimal usage |
| API Gateway | $1.00/1M requests | HTTP API pricing |
| DynamoDB | Pay-per-request | ~$0.00 for low volume |
| SQS | $0.40/1M messages | Negligible |
| **Total (idle)** | **~$0/month** | No running infrastructure |
| **Per build** | **~$0.01-0.03** | Spot instance + S3 |

## Prerequisites

- AWS account with permissions to create VPC, EC2, Lambda, S3, SQS, DynamoDB, API Gateway, IAM
- [Terraform](https://www.terraform.io/downloads) >= 1.5.0
- AWS CLI configured (`aws configure`)

## Deployment

```bash
cd infrastructure/terraform

# Copy and customize configuration
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your preferences

# Initialize and deploy
terraform init
terraform plan
terraform apply
```

After deployment, note the `api_url` output:

```
Outputs:
  api_url = "https://xxxxxxxxxx.execute-api.eu-central-1.amazonaws.com"
```

### Configure GitHub Pages

1. In your GitHub repository: **Settings → Pages → Source: Deploy from a branch**
2. Select **Branch: main**, **Folder: /docs**
3. Open your GitHub Pages URL
4. Click **⚙ API Settings** and paste the `api_url` from Terraform output
5. Start building layers!

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `aws_region` | `eu-central-1` | AWS region |
| `environment` | `prod` | Environment name |
| `artifact_ttl_hours` | `24` | Hours to keep artifacts in S3 |
| `ec2_instance_type` | `c5.xlarge` | Spot instance type |
| `ec2_volume_size` | `50` | EBS volume size (GB) |
| `ec2_max_build_time_minutes` | `30` | Safety timeout per build |
| `allowed_origins` | `["*"]` | CORS origins |
| `docker_image_prefix` | `ghcr.io/fok666/lambda-python-layer` | Pre-built image registry |

## API Reference

### POST /builds

Submit a new build request.

```json
{
  "requirements": "numpy==1.26.4\nrequests==2.32.4",
  "python_version": "3.13",
  "architectures": ["x86_64", "arm64"],
  "single_file": true
}
```

**Response:**
```json
{
  "build_id": "a1b2c3d4-...",
  "status": "QUEUED",
  "expires_at": 1709398800
}
```

### GET /builds/{buildId}

Check build status. Returns presigned download URLs when completed.

**Response (completed):**
```json
{
  "build_id": "a1b2c3d4-...",
  "status": "COMPLETED",
  "python_version": "3.13",
  "architectures": ["x86_64", "arm64"],
  "files": [
    {
      "filename": "combined-python3.13-x86_64.zip",
      "download_url": "https://s3.amazonaws.com/...",
      "architecture": "x86_64"
    },
    {
      "filename": "combined-python3.13-aarch64.zip",
      "download_url": "https://s3.amazonaws.com/...",
      "architecture": "arm64"
    }
  ]
}
```

## Security

- **S3 bucket**: Private, no public access. Downloads via presigned URLs only
- **EC2 instances**: No SSH, no inbound ports. Egress-only security group
- **IMDSv2**: Enforced on all EC2 instances
- **EBS encryption**: Enabled by default
- **IAM**: Least-privilege policies per component
- **DynamoDB TTL**: Automatic cleanup of old records
- **S3 lifecycle**: Automatic deletion of old artifacts

## Teardown

```bash
cd infrastructure/terraform
terraform destroy
```

> **Note:** S3 bucket must be empty before destruction. Terraform will fail if artifacts exist. Wait for lifecycle expiration or manually empty the bucket.
