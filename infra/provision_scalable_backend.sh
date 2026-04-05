#!/bin/bash
##############################################################################
# provision_scalable_backend.sh – create the cheapest correct scalable backend
#
# Target architecture:
#   CloudFront /api -> ALB -> ASG backend instances -> RDS PostgreSQL
#
# Prereqs:
#   - AWS CLI configured
#   - jq installed
#   - required app secrets exported in the shell before running
##############################################################################

set -euo pipefail

REGION="${AWS_REGION:-us-east-1}"
APP_NAME="${APP_NAME:-med-llm-rag}"
DB_INSTANCE_CLASS="${DB_INSTANCE_CLASS:-db.t3.micro}"
DB_ALLOCATED_STORAGE="${DB_ALLOCATED_STORAGE:-20}"
BACKEND_INSTANCE_TYPE="${BACKEND_INSTANCE_TYPE:-t3.micro}"
BACKEND_VOLUME_SIZE="${BACKEND_VOLUME_SIZE:-30}"
DB_NAME="${POSTGRES_DB:-medlit}"
DB_USER="${POSTGRES_USER:-medlit}"
DB_PASSWORD="${POSTGRES_PASSWORD:-medlit}"
LLM_MODEL="${LLM_MODEL:-llama-3.3-70b-versatile}"
MAX_CAPACITY="${MAX_CAPACITY:-2}"
DESIRED_CAPACITY="${DESIRED_CAPACITY:-1}"
MIN_CAPACITY="${MIN_CAPACITY:-1}"

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
VPC_ID=$(aws ec2 describe-vpcs --region "$REGION" --filters "Name=isDefault,Values=true" --query 'Vpcs[0].VpcId' --output text)
SUBNET_IDS=$(aws ec2 describe-subnets --region "$REGION" --filters "Name=vpc-id,Values=$VPC_ID" --query 'Subnets[].SubnetId' --output text)
SUBNET_CSV=$(echo "$SUBNET_IDS" | tr '\t' ',')

REPO_URI=$(aws ecr describe-repositories --region "$REGION" --repository-names "$APP_NAME-backend" --query 'repositories[0].repositoryUri' --output text)
AMI_ID=$(aws ec2 describe-images \
  --region "$REGION" \
  --owners 099720109477 \
  --filters "Name=name,Values=ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*" "Name=state,Values=available" \
  --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
  --output text)

ALB_SG_NAME="$APP_NAME-alb-sg"
APP_SG_NAME="$APP_NAME-backend-app-sg"
RDS_SG_NAME="$APP_NAME-rds-sg"
ALB_NAME="$APP_NAME-backend-alb"
TG_NAME="$APP_NAME-backend-tg"
LT_NAME="$APP_NAME-backend-lt"
ASG_NAME="$APP_NAME-backend-asg"
DB_SUBNET_GROUP="$APP_NAME-db-subnets"
DB_IDENTIFIER="$APP_NAME-db"
PARAM_NAME="/$APP_NAME/backend-env"
INSTANCE_PROFILE_NAME="$APP_NAME-ec2-profile"
ROLE_NAME="$APP_NAME-ec2-role"

required_vars=(GROQ_API_KEY NCBI_API_KEY NCBI_EMAIL SECRET_KEY)
for var_name in "${required_vars[@]}"; do
if [ -z "${!var_name:-}" ]; then
    echo "Missing required environment variable: $var_name"
    exit 1
  fi
done

if [ "${#DB_PASSWORD}" -lt 8 ]; then
  EXISTING_DATABASE_URL=$(aws ssm get-parameter \
    --region "$REGION" \
    --name "$PARAM_NAME" \
    --with-decryption \
    --query 'Parameter.Value' \
    --output text 2>/dev/null | awk '/^DATABASE_URL=/{sub(/^DATABASE_URL=/, ""); print}')

  if [ -n "${EXISTING_DATABASE_URL:-}" ]; then
    DB_PASSWORD=$(printf '%s' "$EXISTING_DATABASE_URL" | sed -E 's#^[^:]+://[^:]+:([^@]+)@.*#\1#')
  else
    DB_PASSWORD=$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 20)
  fi
fi

ensure_sg() {
  local name="$1"
  local description="$2"
  local sg_id
  sg_id=$(aws ec2 describe-security-groups \
    --region "$REGION" \
    --filters "Name=group-name,Values=$name" "Name=vpc-id,Values=$VPC_ID" \
    --query 'SecurityGroups[0].GroupId' \
    --output text 2>/dev/null || true)

  if [ -z "$sg_id" ] || [ "$sg_id" = "None" ]; then
    sg_id=$(aws ec2 create-security-group \
      --region "$REGION" \
      --group-name "$name" \
      --description "$description" \
      --vpc-id "$VPC_ID" \
      --query 'GroupId' \
      --output text)
  fi

  echo "$sg_id"
}

ALB_SG_ID=$(ensure_sg "$ALB_SG_NAME" "ALB security group for $APP_NAME")
APP_SG_ID=$(ensure_sg "$APP_SG_NAME" "Backend app security group for $APP_NAME")
RDS_SG_ID=$(ensure_sg "$RDS_SG_NAME" "RDS security group for $APP_NAME")

aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$ALB_SG_ID" --protocol tcp --port 80 --cidr 0.0.0.0/0 2>/dev/null || true
aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$ALB_SG_ID" --protocol tcp --port 443 --cidr 0.0.0.0/0 2>/dev/null || true
aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$APP_SG_ID" --protocol tcp --port 8000 --source-group "$ALB_SG_ID" 2>/dev/null || true
aws ec2 authorize-security-group-ingress --region "$REGION" --group-id "$RDS_SG_ID" --protocol tcp --port 5432 --source-group "$APP_SG_ID" 2>/dev/null || true

ROLE_POLICY=$(cat <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ssm:GetParameter",
        "ssm:GetParameters"
      ],
      "Resource": "arn:aws:ssm:$REGION:$ACCOUNT_ID:parameter$PARAM_NAME"
    }
  ]
}
EOF
)

aws iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name "$ROLE_NAME-ssm" \
  --policy-document "$ROLE_POLICY"

aws iam attach-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore >/dev/null

if ! aws rds describe-db-subnet-groups --region "$REGION" --db-subnet-group-name "$DB_SUBNET_GROUP" >/dev/null 2>&1; then
  aws rds create-db-subnet-group \
    --region "$REGION" \
    --db-subnet-group-name "$DB_SUBNET_GROUP" \
    --db-subnet-group-description "$APP_NAME DB subnet group" \
    --subnet-ids $SUBNET_IDS >/dev/null
fi

if ! aws rds describe-db-instances --region "$REGION" --db-instance-identifier "$DB_IDENTIFIER" >/dev/null 2>&1; then
  aws rds create-db-instance \
    --region "$REGION" \
    --db-instance-identifier "$DB_IDENTIFIER" \
    --db-instance-class "$DB_INSTANCE_CLASS" \
    --engine postgres \
    --engine-version 16.3 \
    --allocated-storage "$DB_ALLOCATED_STORAGE" \
    --master-username "$DB_USER" \
    --master-user-password "$DB_PASSWORD" \
    --db-name "$DB_NAME" \
    --vpc-security-group-ids "$RDS_SG_ID" \
    --db-subnet-group-name "$DB_SUBNET_GROUP" \
    --backup-retention-period 1 \
    --storage-type gp3 \
    --no-publicly-accessible \
    --no-multi-az \
    >/dev/null
fi

echo "Waiting for RDS instance to become available..."
aws rds wait db-instance-available --region "$REGION" --db-instance-identifier "$DB_IDENTIFIER"

RDS_ENDPOINT=$(aws rds describe-db-instances \
  --region "$REGION" \
  --db-instance-identifier "$DB_IDENTIFIER" \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text)

BACKEND_ENV=$(cat <<EOF
ECR_IMAGE=$REPO_URI:latest
DATABASE_URL=postgresql+asyncpg://$DB_USER:$DB_PASSWORD@$RDS_ENDPOINT:5432/$DB_NAME?ssl=require
GROQ_API_KEY=$GROQ_API_KEY
LLM_MODEL=$LLM_MODEL
NCBI_API_KEY=$NCBI_API_KEY
NCBI_EMAIL=$NCBI_EMAIL
SECRET_KEY=$SECRET_KEY
DEBUG=false
LOG_LEVEL=INFO
AWS_REGION=$REGION
EOF
)

aws ssm put-parameter \
  --region "$REGION" \
  --name "$PARAM_NAME" \
  --type SecureString \
  --overwrite \
  --value "$BACKEND_ENV" >/dev/null

ALB_ARN=$(aws elbv2 describe-load-balancers --region "$REGION" --names "$ALB_NAME" --query 'LoadBalancers[0].LoadBalancerArn' --output text 2>/dev/null || true)
if [ -z "$ALB_ARN" ] || [ "$ALB_ARN" = "None" ]; then
  ALB_ARN=$(aws elbv2 create-load-balancer \
    --region "$REGION" \
    --name "$ALB_NAME" \
    --subnets $SUBNET_IDS \
    --security-groups "$ALB_SG_ID" \
    --type application \
    --scheme internet-facing \
    --query 'LoadBalancers[0].LoadBalancerArn' \
    --output text)
fi

TG_ARN=$(aws elbv2 describe-target-groups --region "$REGION" --names "$TG_NAME" --query 'TargetGroups[0].TargetGroupArn' --output text 2>/dev/null || true)
if [ -z "$TG_ARN" ] || [ "$TG_ARN" = "None" ]; then
  TG_ARN=$(aws elbv2 create-target-group \
    --region "$REGION" \
    --name "$TG_NAME" \
    --protocol HTTP \
    --port 8000 \
    --vpc-id "$VPC_ID" \
    --target-type instance \
    --health-check-path /health \
    --health-check-protocol HTTP \
    --query 'TargetGroups[0].TargetGroupArn' \
    --output text)
fi

LISTENER_ARN=$(aws elbv2 describe-listeners --region "$REGION" --load-balancer-arn "$ALB_ARN" --query 'Listeners[0].ListenerArn' --output text 2>/dev/null || true)
if [ -z "$LISTENER_ARN" ] || [ "$LISTENER_ARN" = "None" ]; then
  aws elbv2 create-listener \
    --region "$REGION" \
    --load-balancer-arn "$ALB_ARN" \
    --protocol HTTP \
    --port 80 \
    --default-actions Type=forward,TargetGroupArn="$TG_ARN" >/dev/null
fi

USER_DATA=$(cat <<EOF
#!/bin/bash
set -euxo pipefail
apt-get update -y
apt-get install -y docker.io curl unzip
curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
unzip -q /tmp/awscliv2.zip -d /tmp
/tmp/aws/install
systemctl enable docker
systemctl start docker
usermod -aG docker ubuntu
mkdir -p /home/ubuntu/app
chown -R ubuntu:ubuntu /home/ubuntu/app
aws ssm get-parameter --region $REGION --name "$PARAM_NAME" --with-decryption --query 'Parameter.Value' --output text > /home/ubuntu/app/.env
set -a
. /home/ubuntu/app/.env
set +a
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com
docker volume create hf_cache || true
docker pull "\$ECR_IMAGE"
docker rm -f medlit-backend || true
docker run -d \
  --name medlit-backend \
  --restart unless-stopped \
  --env-file /home/ubuntu/app/.env \
  -e DEBUG=false \
  -e LOG_LEVEL=INFO \
  -p 8000:8000 \
  -v hf_cache:/app/hf-cache \
  "\$ECR_IMAGE"
EOF
)

LT_DATA=$(cat <<EOF
{
  "ImageId": "$AMI_ID",
  "InstanceType": "$BACKEND_INSTANCE_TYPE",
  "BlockDeviceMappings": [
    {
      "DeviceName": "/dev/sda1",
      "Ebs": {
        "DeleteOnTermination": true,
        "VolumeSize": $BACKEND_VOLUME_SIZE,
        "VolumeType": "gp3"
      }
    }
  ],
  "IamInstanceProfile": {
    "Name": "$INSTANCE_PROFILE_NAME"
  },
  "SecurityGroupIds": ["$APP_SG_ID"],
  "UserData": "$(printf '%s' "$USER_DATA" | base64 | tr -d '\n')",
  "TagSpecifications": [
    {
      "ResourceType": "instance",
      "Tags": [
        {"Key": "Name", "Value": "$APP_NAME-backend-asg"}
      ]
    }
  ]
}
EOF
)

LT_ID=$(aws ec2 describe-launch-templates --region "$REGION" --launch-template-names "$LT_NAME" --query 'LaunchTemplates[0].LaunchTemplateId' --output text 2>/dev/null || true)
if [ -z "$LT_ID" ] || [ "$LT_ID" = "None" ]; then
  LT_ID=$(aws ec2 create-launch-template \
    --region "$REGION" \
    --launch-template-name "$LT_NAME" \
    --launch-template-data "$LT_DATA" \
    --query 'LaunchTemplate.LaunchTemplateId' \
    --output text)
else
  aws ec2 create-launch-template-version \
    --region "$REGION" \
    --launch-template-id "$LT_ID" \
    --source-version '$Latest' \
    --launch-template-data "$LT_DATA" >/dev/null
fi

LATEST_LT_VERSION=$(aws ec2 describe-launch-template-versions --region "$REGION" --launch-template-id "$LT_ID" --versions '$Latest' --query 'LaunchTemplateVersions[0].VersionNumber' --output text)
aws ec2 modify-launch-template --region "$REGION" --launch-template-id "$LT_ID" --default-version "$LATEST_LT_VERSION" >/dev/null

if ! aws autoscaling describe-auto-scaling-groups --region "$REGION" --auto-scaling-group-names "$ASG_NAME" --query 'AutoScalingGroups[0].AutoScalingGroupName' --output text 2>/dev/null | grep -q "$ASG_NAME"; then
  aws autoscaling create-auto-scaling-group \
    --region "$REGION" \
    --auto-scaling-group-name "$ASG_NAME" \
    --launch-template "LaunchTemplateId=$LT_ID,Version=$LATEST_LT_VERSION" \
    --min-size "$MIN_CAPACITY" \
    --max-size "$MAX_CAPACITY" \
    --desired-capacity "$DESIRED_CAPACITY" \
    --vpc-zone-identifier "$SUBNET_CSV" \
    --health-check-type ELB \
    --health-check-grace-period 300
else
  aws autoscaling update-auto-scaling-group \
    --region "$REGION" \
    --auto-scaling-group-name "$ASG_NAME" \
    --launch-template "LaunchTemplateId=$LT_ID,Version=$LATEST_LT_VERSION" \
    --min-size "$MIN_CAPACITY" \
    --max-size "$MAX_CAPACITY" \
    --desired-capacity "$DESIRED_CAPACITY" \
    --vpc-zone-identifier "$SUBNET_CSV" \
    --health-check-type ELB \
    --health-check-grace-period 300
fi

aws autoscaling attach-load-balancer-target-groups \
  --region "$REGION" \
  --auto-scaling-group-name "$ASG_NAME" \
  --target-group-arns "$TG_ARN" >/dev/null

aws autoscaling put-scaling-policy \
  --region "$REGION" \
  --auto-scaling-group-name "$ASG_NAME" \
  --policy-name "$APP_NAME-backend-cpu-tt" \
  --policy-type TargetTrackingScaling \
  --target-tracking-configuration '{
    "PredefinedMetricSpecification": {
      "PredefinedMetricType": "ASGAverageCPUUtilization"
    },
    "TargetValue": 60.0
  }' >/dev/null

ALB_DNS=$(aws elbv2 describe-load-balancers --region "$REGION" --load-balancer-arns "$ALB_ARN" --query 'LoadBalancers[0].DNSName' --output text)

echo "Provisioning complete."
echo "RDS endpoint: $RDS_ENDPOINT"
echo "ALB DNS: $ALB_DNS"
echo "ASG: $ASG_NAME"
