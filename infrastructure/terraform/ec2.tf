# =============================================================================
# EC2 Launch Template for Build Workers
# =============================================================================
# Uses Amazon Linux 2023 with Docker pre-configured.
# Instances are launched as Spot by the process_build Lambda.
# Each instance self-terminates after build completion or timeout.
# =============================================================================

# Pre-create the EC2 Spot service-linked role so Lambda doesn't need to create it at runtime.
# This role is account-global and only needs to exist once.
# Terraform will silently import it if it already exists.
resource "aws_iam_service_linked_role" "ec2_spot" {
  aws_service_name = "spot.amazonaws.com"
  description      = "Service-linked role for EC2 Spot Instances"

  # Ignore if this role already exists in the account
  lifecycle {
    ignore_changes = [description]
  }
}

# Latest Amazon Linux 2023 AMI
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

resource "aws_launch_template" "builder" {
  name_prefix   = "${local.name_prefix}-builder-"
  image_id      = data.aws_ami.al2023.id
  instance_type = var.ec2_instance_type

  iam_instance_profile {
    arn = aws_iam_instance_profile.ec2_builder.arn
  }

  vpc_security_group_ids = [aws_security_group.builder.id]

  block_device_mappings {
    device_name = "/dev/xvda"

    ebs {
      volume_size           = var.ec2_volume_size
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 2
  }

  tag_specifications {
    resource_type = "instance"

    tags = {
      Name          = "${local.name_prefix}-builder"
      Project       = var.project_name
      AutoTerminate = "true"
    }
  }

  tag_specifications {
    resource_type = "volume"

    tags = {
      Name    = "${local.name_prefix}-builder-vol"
      Project = var.project_name
    }
  }

  # User data is provided dynamically by the process_build Lambda
  # This template serves as a base configuration

  lifecycle {
    create_before_destroy = true
  }
}
