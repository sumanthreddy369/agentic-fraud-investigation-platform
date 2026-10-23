# Temporary portfolio infrastructure. Do not apply until the account, credit
# eligibility, access plan, cost estimate and teardown window are reviewed.
terraform {
  required_version = ">= 1.8, < 2.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

variable "account_id" {
  type = string
  validation {
    condition     = can(regex("^[0-9]{12}$", var.account_id))
    error_message = "Provide the reviewed AWS account ID."
  }
}
variable "expires_at" {
  type        = string
  description = "Reviewed UTC teardown deadline; this tag does not automate deletion."
  validation {
    condition     = can(formatdate("YYYY-MM-DD", var.expires_at))
    error_message = "Provide an RFC3339 teardown deadline."
  }
}
variable "operator_role_arn" {
  type        = string
  description = "Existing, explicitly approved IAM role for cluster administration. Never root."
  validation {
    condition     = can(regex("^arn:aws:iam::[0-9]{12}:role/.+$", var.operator_role_arn))
    error_message = "An existing IAM role ARN is required."
  }
}
variable "kubernetes_version" {
  type        = string
  description = "Pin a version confirmed in STANDARD_SUPPORT immediately before apply."
}
variable "name" {
  type    = string
  default = "risk-portfolio-demo"
}
variable "worker_instance_type" {
  type        = string
  description = "Explicit x86_64 worker type checked for account eligibility, quota and cost before apply."
  validation {
    condition     = can(regex("^[a-z0-9-]+[.][a-z0-9]+$", var.worker_instance_type))
    error_message = "Provide a reviewed EC2 instance type."
  }
}
provider "aws" {
  region              = "us-east-1"
  allowed_account_ids = [var.account_id]
  default_tags {
    tags = {
      Project   = var.name
      Purpose   = "DisposablePortfolio"
      ManagedBy = "Terraform"
      ExpiresAt = var.expires_at
    }
  }
}
data "aws_availability_zones" "available" { state = "available" }

resource "aws_vpc" "demo" {
  cidr_block           = "10.87.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true
}
resource "aws_subnet" "private" {
  count             = 2
  vpc_id            = aws_vpc.demo.id
  cidr_block        = cidrsubnet(aws_vpc.demo.cidr_block, 8, count.index)
  availability_zone = data.aws_availability_zones.available.names[count.index]
}
resource "aws_subnet" "egress" {
  vpc_id            = aws_vpc.demo.id
  cidr_block        = "10.87.10.0/24"
  availability_zone = data.aws_availability_zones.available.names[0]
}
resource "aws_internet_gateway" "demo" { vpc_id = aws_vpc.demo.id }
resource "aws_eip" "nat" { domain = "vpc" }
resource "aws_nat_gateway" "demo" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.egress.id
  depends_on    = [aws_internet_gateway.demo]
}
resource "aws_route_table" "egress" {
  vpc_id = aws_vpc.demo.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.demo.id
  }
}
resource "aws_route_table_association" "egress" {
  subnet_id      = aws_subnet.egress.id
  route_table_id = aws_route_table.egress.id
}
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.demo.id
  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.demo.id
  }
}
resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.demo.id
  service_name      = "com.amazonaws.us-east-1.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]
}

resource "aws_iam_role" "cluster" {
  name = "${var.name}-cluster"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "eks.amazonaws.com" } }]
  })
}
resource "aws_iam_role_policy_attachment" "cluster" {
  role       = aws_iam_role.cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}
resource "aws_cloudwatch_log_group" "eks" {
  name              = "/aws/eks/${var.name}/cluster"
  retention_in_days = 1
}
resource "aws_eks_cluster" "demo" {
  name                      = var.name
  role_arn                  = aws_iam_role.cluster.arn
  version                   = var.kubernetes_version
  enabled_cluster_log_types = ["api", "audit", "authenticator"]
  access_config {
    authentication_mode                         = "API"
    bootstrap_cluster_creator_admin_permissions = false
  }
  upgrade_policy { support_type = "STANDARD" }
  vpc_config {
    subnet_ids              = aws_subnet.private[*].id
    endpoint_private_access = true
    endpoint_public_access  = false
  }
  depends_on = [aws_iam_role_policy_attachment.cluster, aws_cloudwatch_log_group.eks]
}
resource "aws_eks_access_entry" "operator" {
  cluster_name  = aws_eks_cluster.demo.name
  principal_arn = var.operator_role_arn
}
resource "aws_eks_access_policy_association" "operator" {
  cluster_name  = aws_eks_cluster.demo.name
  principal_arn = aws_eks_access_entry.operator.principal_arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  access_scope { type = "cluster" }
}
resource "aws_security_group" "operator" {
  name        = "${var.name}-operator"
  description = "For a reviewed CloudShell VPC environment; no inbound access"
  vpc_id      = aws_vpc.demo.id
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}
resource "aws_vpc_security_group_ingress_rule" "operator_api" {
  security_group_id            = aws_eks_cluster.demo.vpc_config[0].cluster_security_group_id
  referenced_security_group_id = aws_security_group.operator.id
  from_port                    = 443
  to_port                      = 443
  ip_protocol                  = "tcp"
}
resource "aws_iam_role" "node" {
  name = "${var.name}-node"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "sts:AssumeRole", Principal = { Service = "ec2.amazonaws.com" } }]
  })
}
# Initial demo CNI permissions on the node role. Separate pod identity is a
# production-hardening gate; workload pods must not receive node credentials.
resource "aws_iam_role_policy_attachment" "node" {
  for_each   = toset(["AmazonEKSWorkerNodePolicy", "AmazonEC2ContainerRegistryPullOnly", "AmazonEKS_CNI_Policy"])
  role       = aws_iam_role.node.name
  policy_arn = "arn:aws:iam::aws:policy/${each.value}"
}
resource "aws_launch_template" "node" {
  name_prefix = "${var.name}-"
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }
  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 30
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }
  tag_specifications {
    resource_type = "instance"
    tags          = { Project = var.name, Purpose = "DisposablePortfolio", ExpiresAt = var.expires_at }
  }
  tag_specifications {
    resource_type = "volume"
    tags          = { Project = var.name, Purpose = "DisposablePortfolio", ExpiresAt = var.expires_at }
  }
}
resource "aws_eks_node_group" "demo" {
  cluster_name    = aws_eks_cluster.demo.name
  node_group_name = "demo"
  node_role_arn   = aws_iam_role.node.arn
  subnet_ids      = aws_subnet.private[*].id
  instance_types  = [var.worker_instance_type]
  capacity_type   = "ON_DEMAND"
  ami_type        = "AL2023_x86_64_STANDARD"
  launch_template {
    id      = aws_launch_template.node.id
    version = aws_launch_template.node.latest_version
  }
  scaling_config {
    desired_size = 2
    min_size     = 1
    max_size     = 2
  }
  update_config { max_unavailable = 1 }
  depends_on = [aws_iam_role_policy_attachment.node, aws_route_table_association.private]
}
resource "aws_ecr_repository" "api" {
  name                 = var.name
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  image_scanning_configuration { scan_on_push = true }
  encryption_configuration { encryption_type = "AES256" }
}
output "cluster_name" { value = aws_eks_cluster.demo.name }
output "private_subnets" { value = aws_subnet.private[*].id }
output "operator_security_group" { value = aws_security_group.operator.id }
output "repository_url" { value = aws_ecr_repository.api.repository_url }
