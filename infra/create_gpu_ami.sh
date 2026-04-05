#!/bin/bash
##############################################################################
# create_gpu_ami.sh – creates a custom AMI with Ollama + model pre-installed
#
# This AMI is used by ec2_gpu_manager.py to launch spot GPU instances.
# Having the model pre-baked means cold start is ~2 min (boot only),
# not ~10 min (boot + download 9GB model).
#
# Steps:
#   1. Launch a temporary g4dn.xlarge (on-demand, ~$0.53/hr)
#   2. Install Ollama + pull qwen2.5:14b
#   3. Create an AMI from the instance
#   4. Terminate the temporary instance
#
# Total cost: ~$0.50 (one-time, takes ~30 min)
#
# Usage:
#   chmod +x infra/create_gpu_ami.sh
#   ./infra/create_gpu_ami.sh
##############################################################################

set -e

REGION="us-east-1"
INSTANCE_TYPE="g4dn.xlarge"
MODEL="qwen2.5:14b"
APP_NAME="med-llm-rag"
KEY_NAME="$APP_NAME-key"

# Get the security group
SG_ID=$(aws ec2 describe-security-groups \
  --region $REGION \
  --filters "Name=group-name,Values=$APP_NAME-sg" \
  --query 'SecurityGroups[0].GroupId' --output text)

# Allow Ollama port (11434) in security group
aws ec2 authorize-security-group-ingress \
  --region $REGION \
  --group-id $SG_ID \
  --protocol tcp \
  --port 11434 \
  --cidr 0.0.0.0/0 2>/dev/null || echo "Port 11434 already open"

echo "=========================================="
echo "Creating GPU AMI with Ollama + $MODEL"
echo "=========================================="

# Ubuntu 22.04 Deep Learning AMI (has NVIDIA drivers pre-installed)
AMI_ID=$(aws ec2 describe-images \
  --region $REGION \
  --owners 898082745236 \
  --filters "Name=name,Values=Deep Learning AMI GPU PyTorch*Ubuntu 22.04*" \
            "Name=state,Values=available" \
            "Name=architecture,Values=x86_64" \
  --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
  --output text 2>/dev/null)

# Fallback to standard Ubuntu if DL AMI not found
if [ -z "$AMI_ID" ] || [ "$AMI_ID" = "None" ]; then
  echo "Deep Learning AMI not found, using standard Ubuntu + installing NVIDIA drivers"
  AMI_ID=$(aws ec2 describe-images \
    --region $REGION \
    --owners 099720109477 \
    --filters "Name=name,Values=ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*" \
              "Name=state,Values=available" \
    --query 'sort_by(Images, &CreationDate)[-1].ImageId' \
    --output text)
fi

echo "[1/5] Using base AMI: $AMI_ID"

# Launch temporary instance
echo "[2/5] Launching temporary $INSTANCE_TYPE..."
INSTANCE_ID=$(aws ec2 run-instances \
  --region $REGION \
  --image-id $AMI_ID \
  --instance-type $INSTANCE_TYPE \
  --key-name $KEY_NAME \
  --security-group-ids $SG_ID \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":50,"VolumeType":"gp3"}}]' \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$APP_NAME-ami-builder}]" \
  --query 'Instances[0].InstanceId' \
  --output text)

echo "  Instance: $INSTANCE_ID"
echo "  Waiting for instance to be running..."
aws ec2 wait instance-running --region $REGION --instance-ids $INSTANCE_ID

# Get public IP
TEMP_IP=$(aws ec2 describe-instances \
  --region $REGION \
  --instance-ids $INSTANCE_ID \
  --query 'Reservations[0].Instances[0].PublicIpAddress' \
  --output text)
echo "  IP: $TEMP_IP"

# Wait for SSH to be ready
echo "  Waiting for SSH..."
for i in $(seq 1 30); do
  ssh -i ~/.ssh/$KEY_NAME.pem -o StrictHostKeyChecking=no -o ConnectTimeout=5 \
    ubuntu@$TEMP_IP "echo ready" 2>/dev/null && break
  sleep 10
done

# Install Ollama and pull model
echo "[3/5] Installing Ollama and pulling $MODEL (this takes ~15 min)..."
ssh -i ~/.ssh/$KEY_NAME.pem -o StrictHostKeyChecking=no ubuntu@$TEMP_IP << 'REMOTE'
set -e

# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama in background
ollama serve &
sleep 10

# Pull the model (this is the slow part — ~9GB download)
echo "Pulling model..."
ollama pull qwen2.5:14b

# Verify model is there
ollama list

# Create a systemd service so Ollama starts on boot
sudo tee /etc/systemd/system/ollama-autostart.service > /dev/null << 'EOF'
[Unit]
Description=Ollama LLM Server
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/ollama serve
Restart=always
RestartSec=3
Environment="OLLAMA_HOST=0.0.0.0"
Environment="OLLAMA_KEEP_ALIVE=-1"

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable ollama-autostart

# Stop the manual ollama process
pkill ollama || true
sleep 2

echo "Setup complete!"
REMOTE

# Replace MODELNAME placeholder
ssh -i ~/.ssh/$KEY_NAME.pem -o StrictHostKeyChecking=no ubuntu@$TEMP_IP \
  "sudo sed -i 's/MODELNAME/$MODEL/g' /etc/systemd/system/ollama-autostart.service" 2>/dev/null || true

# Create AMI
echo "[4/5] Creating AMI (takes 5-10 min)..."
AMI_NAME="$APP_NAME-gpu-ollama-$(date +%Y%m%d)"

NEW_AMI=$(aws ec2 create-image \
  --region $REGION \
  --instance-id $INSTANCE_ID \
  --name "$AMI_NAME" \
  --description "Ollama + $MODEL pre-installed for medical RAG" \
  --no-reboot \
  --query 'ImageId' \
  --output text)

echo "  AMI ID: $NEW_AMI"
echo "  Waiting for AMI to be available..."
aws ec2 wait image-available --region $REGION --image-ids $NEW_AMI

# Terminate temporary instance
echo "[5/5] Terminating temporary instance..."
aws ec2 terminate-instances --region $REGION --instance-ids $INSTANCE_ID > /dev/null

echo ""
echo "=========================================="
echo "GPU AMI READY"
echo "=========================================="
echo ""
echo "AMI ID: $NEW_AMI"
echo "AMI Name: $AMI_NAME"
echo ""
echo "Next steps:"
echo "  1. Add to .env on EC2:"
echo "     GPU_AMI_ID=$NEW_AMI"
echo "     GPU_SECURITY_GROUP=$SG_ID"
echo ""
echo "  2. Add to GitHub Secrets:"
echo "     GPU_AMI_ID=$NEW_AMI"
echo ""
echo "  3. Redeploy: git push origin main"
