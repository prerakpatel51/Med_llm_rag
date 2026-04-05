#!/bin/bash
##############################################################################
# migrate_postgres_to_rds.sh – copy the current single-host Postgres data into
# the new RDS instance from the existing EC2 backend host.
##############################################################################

set -euo pipefail

if [ $# -lt 2 ]; then
  echo "Usage: $0 <ec2-host> <rds-endpoint>"
  exit 1
fi

EC2_HOST="$1"
RDS_ENDPOINT="$2"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/med-llm-rag-key.pem}"
DB_NAME="${POSTGRES_DB:-medlit}"
DB_USER="${POSTGRES_USER:-medlit}"
DB_PASSWORD="${POSTGRES_PASSWORD:-medlit}"

ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "ubuntu@$EC2_HOST" <<EOF
set -euo pipefail
cd ~/app
docker exec medlit-postgres pg_dump -U "$DB_USER" -d "$DB_NAME" -Fc -f /tmp/medlit.dump
docker run --rm --network host -v /tmp:/tmp -e PGPASSWORD="$DB_PASSWORD" -e PGSSLMODE=require postgres:16 \
  pg_restore --clean --if-exists --no-owner -h "$RDS_ENDPOINT" -U "$DB_USER" -d "$DB_NAME" /tmp/medlit.dump
rm -f /tmp/medlit.dump
EOF
