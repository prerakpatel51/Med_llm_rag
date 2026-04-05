#!/bin/bash
##############################################################################
# setup_aws.sh – one-time AWS infrastructure setup
#
# Run this ONCE to create all AWS resources.
# After this, GitHub Actions handles all deployments automatically.
#
# Prerequisites:
#   - AWS CLI configured (aws configure)
#   - jq installed (brew install jq)
#
# Usage:
#   chmod +x infra/setup_aws.sh
#   ./infra/setup_aws.sh
##############################################################################

set -e  # exit on any error

# ── Config ────────────────────────────────────────────────────────────────────
REGION="us-east-1"
APP_NAME="med-llm-rag"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "=========================================="
echo "Setting up AWS infrastructure for $APP_NAME"
echo "Account: $ACCOUNT_ID | Region: $REGION"
echo "=========================================="

# ── 1. ECR Repository ─────────────────────────────────────────────────────────
echo ""
echo "[1/6] Creating ECR repository..."
aws ecr create-repository \
  --repository-name "$APP_NAME-backend" \
  --region $REGION \
  --image-scanning-configuration scanOnPush=true \
  2>/dev/null || echo "  ECR repo already exists, skipping"

ECR_URI="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/$APP_NAME-backend"
echo "  ECR URI: $ECR_URI"

# ── 2. S3 Bucket for frontend ─────────────────────────────────────────────────
echo ""
echo "[2/6] Creating S3 bucket for frontend..."
BUCKET_NAME="$APP_NAME-frontend-$ACCOUNT_ID"

aws s3 mb s3://$BUCKET_NAME --region $REGION 2>/dev/null || echo "  Bucket already exists"

# Enable static website hosting
aws s3 website s3://$BUCKET_NAME \
  --index-document index.html \
  --error-document 404.html

# Disable block public access (needed for CloudFront OAC)
aws s3api put-public-access-block \
  --bucket $BUCKET_NAME \
  --public-access-block-configuration \
  "BlockPublicAcls=false,IgnorePublicAcls=false,BlockPublicPolicy=false,RestrictPublicBuckets=false"

echo "  S3 Bucket: $BUCKET_NAME"

# ── 3. CloudFront Distribution ────────────────────────────────────────────────
echo ""
echo "[3/6] Creating CloudFront distribution..."

CF_CONFIG=$(cat <<EOF
{
  "Origins": {
    "Quantity": 1,
    "Items": [{
      "Id": "S3-$BUCKET_NAME",
      "DomainName": "$BUCKET_NAME.s3-website-$REGION.amazonaws.com",
      "CustomOriginConfig": {
        "HTTPPort": 80,
        "HTTPSPort": 443,
        "OriginProtocolPolicy": "http-only"
      }
    }]
  },
  "DefaultCacheBehavior": {
    "TargetOriginId": "S3-$BUCKET_NAME",
    "ViewerProtocolPolicy": "redirect-to-https",
    "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6",
    "Compress": true
  },
  "DefaultRootObject": "index.html",
  "CustomErrorResponses": {
    "Quantity": 1,
    "Items": [{
      "ErrorCode": 404,
      "ResponseCode": "200",
      "ResponsePagePath": "/index.html"
    }]
  },
  "Comment": "$APP_NAME frontend",
  "Enabled": true,
  "PriceClass": "PriceClass_100"
}
EOF
)

CF_RESULT=$(aws cloudfront create-distribution \
  --distribution-config "$CF_CONFIG" \
  --query 'Distribution.{ID:Id,Domain:DomainName}' \
  --output json 2>/dev/null) || echo "  CloudFront may already exist"

if [ ! -z "$CF_RESULT" ]; then
  CF_ID=$(echo $CF_RESULT | jq -r '.ID')
  CF_DOMAIN=$(echo $CF_RESULT | jq -r '.Domain')
  echo "  CloudFront ID: $CF_ID"
  echo "  CloudFront URL: https://$CF_DOMAIN"
fi

# ── 4. Security Group for EC2 ─────────────────────────────────────────────────
echo ""
echo "[4/6] Creating security group for EC2..."
VPC_ID=$(aws ec2 describe-vpcs \
  --region $REGION \
  --filters "Name=isDefault,Values=true" \
  --query 'Vpcs[0].VpcId' --output text)

SG_ID=$(aws ec2 create-security-group \
  --region $REGION \
  --group-name "$APP_NAME-sg" \
  --description "Security group for $APP_NAME" \
  --vpc-id $VPC_ID \
  --query 'GroupId' --output text 2>/dev/null) || \
  SG_ID=$(aws ec2 describe-security-groups \
    --region $REGION \
    --filters "Name=group-name,Values=$APP_NAME-sg" \
    --query 'SecurityGroups[0].GroupId' --output text)

# Allow SSH, HTTP, HTTPS, backend port, Grafana
for PORT in 22 80 443 8000 3001 9090; do
  aws ec2 authorize-security-group-ingress \
    --region $REGION \
    --group-id $SG_ID \
    --protocol tcp \
    --port $PORT \
    --cidr 0.0.0.0/0 2>/dev/null || true
done

echo "  Security Group: $SG_ID"

# ── 5. EC2 Key Pair ───────────────────────────────────────────────────────────
echo ""
echo "[5/6] Creating EC2 key pair..."
KEY_NAME="$APP_NAME-key"

aws ec2 create-key-pair \
  --region $REGION \
  --key-name $KEY_NAME \
  --query 'KeyMaterial' \
  --output text > ~/.ssh/$KEY_NAME.pem 2>/dev/null || echo "  Key pair already exists"

chmod 600 ~/.ssh/$KEY_NAME.pem 2>/dev/null || true
echo "  Key saved to: ~/.ssh/$KEY_NAME.pem"
echo "  IMPORTANT: Add contents of this file to GitHub Secret EC2_SSH_KEY"

# ── 6. Launch t3.small EC2 instance ──────────────────────────────────────────
echo ""
echo "[6/6] Launching t3.small EC2 instance..."

# Ubuntu 22.04 LTS AMI (us-east-1)
AMI_ID=$(aws ec2 describe-images \
  --region $REGION \
  --owners 099720109477 \
  --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" \
            "Name=state,Values=available" \
  --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
  --output text)

USER_DATA=$(cat <<'USERDATA'
#!/bin/bash
# Install Docker
apt-get update -y
apt-get install -y docker.io docker-compose-plugin awscli curl

# Start Docker
systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu

# Create app directory
mkdir -p /home/ubuntu/app
chown ubuntu:ubuntu /home/ubuntu/app

echo "EC2 setup complete"
USERDATA
)

INSTANCE_ID=$(aws ec2 run-instances \
  --region $REGION \
  --image-id $AMI_ID \
  --instance-type t3.small \
  --key-name $KEY_NAME \
  --security-group-ids $SG_ID \
  --user-data "$USER_DATA" \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":30,"VolumeType":"gp3"}}]' \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$APP_NAME-backend}]" \
  --query 'Instances[0].InstanceId' \
  --output text 2>/dev/null) || echo "  Instance may already exist"

if [ ! -z "$INSTANCE_ID" ] && [ "$INSTANCE_ID" != "None" ]; then
  echo "  Waiting for instance to start..."
  aws ec2 wait instance-running --region $REGION --instance-ids $INSTANCE_ID

  EC2_IP=$(aws ec2 describe-instances \
    --region $REGION \
    --instance-ids $INSTANCE_ID \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

  echo "  Instance ID: $INSTANCE_ID"
  echo "  Public IP: $EC2_IP"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo "=========================================="
echo "SETUP COMPLETE — Add these to GitHub Secrets"
echo "=========================================="
echo ""
echo "AWS_ACCESS_KEY_ID:       (your IAM key)"
echo "AWS_SECRET_ACCESS_KEY:   (your IAM secret)"
echo "EC2_HOST:                $EC2_IP"
echo "EC2_USER:                ubuntu"
echo "EC2_SSH_KEY:             (contents of ~/.ssh/$KEY_NAME.pem)"
echo "S3_BUCKET:               $BUCKET_NAME"
echo "CLOUDFRONT_DISTRIBUTION: $CF_ID"
echo "DB_PASSWORD:             (choose a strong password)"
echo "SECRET_KEY:              (run: openssl rand -hex 32)"
echo "NCBI_API_KEY:            (your NCBI key)"
echo "NCBI_EMAIL:              (your email)"
echo "GF_ADMIN_PASSWORD:       (choose a password)"
echo ""
echo "Next: Copy docker-compose.prod.yml to EC2:"
echo "  scp -i ~/.ssh/$KEY_NAME.pem docker-compose.prod.yml ubuntu@$EC2_IP:~/app/"
echo "  scp -i ~/.ssh/$KEY_NAME.pem .env.prod ubuntu@$EC2_IP:~/app/.env"
