#!/bin/bash
##############################################################################
# create_iam_user.sh – creates a limited IAM user for GitHub Actions
#
# This user only has permissions it actually needs:
#   - ECR: push/pull images
#   - S3: upload frontend files
#   - CloudFront: update distribution config + create invalidations
#   - Auto Scaling / ELB: refresh scaled backend fleet and discover ALB
#   - EC2: manage spot GPU instance
#
# Usage:
#   chmod +x infra/create_iam_user.sh
#   ./infra/create_iam_user.sh
##############################################################################

set -e

REGION="us-east-1"
USER_NAME="med-llm-rag-cicd"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "Creating IAM user: $USER_NAME"

# Create user
aws iam create-user --user-name $USER_NAME 2>/dev/null || echo "User already exists"

# Create policy
POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECRAccess",
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:GetDownloadUrlForLayer",
        "ecr:BatchGetImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:PutImage"
      ],
      "Resource": "*"
    },
    {
      "Sid": "S3Access",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::med-llm-rag-frontend-$ACCOUNT_ID",
        "arn:aws:s3:::med-llm-rag-frontend-$ACCOUNT_ID/*"
      ]
    },
    {
      "Sid": "CloudFrontAccess",
      "Effect": "Allow",
      "Action": [
        "cloudfront:GetDistribution",
        "cloudfront:GetDistributionConfig",
        "cloudfront:UpdateDistribution",
        "cloudfront:CreateInvalidation"
      ],
      "Resource": "*"
    },
    {
      "Sid": "ScalingAccess",
      "Effect": "Allow",
      "Action": [
        "autoscaling:DescribeAutoScalingGroups",
        "autoscaling:StartInstanceRefresh",
        "elasticloadbalancing:DescribeLoadBalancers"
      ],
      "Resource": "*"
    },
    {
      "Sid": "EC2SpotGPUAccess",
      "Effect": "Allow",
      "Action": [
        "ec2:RunInstances",
        "ec2:TerminateInstances",
        "ec2:DescribeInstances",
        "ec2:DescribeInstanceStatus",
        "ec2:DescribeSpotInstanceRequests",
        "ec2:RequestSpotInstances",
        "ec2:CancelSpotInstanceRequests",
        "ec2:CreateTags"
      ],
      "Resource": "*"
    }
  ]
}
EOF
)

# Create and attach policy
aws iam put-user-policy \
  --user-name $USER_NAME \
  --policy-name "$USER_NAME-policy" \
  --policy-document "$POLICY"

# Create access keys
echo ""
echo "Creating access keys..."
KEYS=$(aws iam create-access-key --user-name $USER_NAME)

ACCESS_KEY=$(echo $KEYS | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['AccessKey']['AccessKeyId'])")
SECRET_KEY=$(echo $KEYS | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['AccessKey']['SecretAccessKey'])")

echo ""
echo "=========================================="
echo "Add these to GitHub Secrets:"
echo "=========================================="
echo "AWS_ACCESS_KEY_ID:     $ACCESS_KEY"
echo "AWS_SECRET_ACCESS_KEY: $SECRET_KEY"
echo ""
echo "IMPORTANT: Save these now — secret key shown only once!"
