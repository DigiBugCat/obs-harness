#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CF_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$CF_DIR")"

echo -e "${RED}=== OBS Harness Cloudflare Tunnel Destruction ===${NC}"
echo ""
echo -e "${YELLOW}This will:${NC}"
echo "  - Stop and remove Docker containers"
echo "  - Delete Cloudflare tunnel and DNS records"
echo "  - Delete Access application and policies"
echo "  - Remove local configuration files"
echo ""
read -p "Are you sure you want to continue? (y/N) " -n 1 -r
echo ""

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 0
fi

# Check for terraform/tofu
TF_CMD="terraform"
if ! command -v terraform &> /dev/null; then
    if command -v tofu &> /dev/null; then
        TF_CMD="tofu"
    else
        echo -e "${RED}Error: terraform or tofu is not installed${NC}"
        exit 1
    fi
fi

# Load environment variables
ENV_FILE="$PROJECT_ROOT/.env"
if [ -f "$ENV_FILE" ]; then
    source "$ENV_FILE"
fi

echo -e "${YELLOW}Stopping Docker containers...${NC}"
cd "$PROJECT_ROOT"
docker compose down 2>/dev/null || true

echo -e "${YELLOW}Destroying Terraform resources...${NC}"
cd "$CF_DIR/terraform"

if [ -f "terraform.tfstate" ]; then
    # Convert comma-separated lists to Terraform list format
    IFS=',' read -ra EMAIL_ARRAY <<< "${AUTH_EMAILS:-}"
    EMAILS_TF=$(printf '"%s",' "${EMAIL_ARRAY[@]}" | sed 's/,$//')

    IFS=',' read -ra IP_ARRAY <<< "${AUTH_IP_RANGES:-}"
    IPS_TF=$(printf '"%s",' "${IP_ARRAY[@]}" | sed 's/,$//')

    $TF_CMD destroy -auto-approve \
        -var="cloudflare_api_key=${CLOUDFLARE_API_KEY:-dummy}" \
        -var="cloudflare_email=${CLOUDFLARE_EMAIL:-dummy@example.com}" \
        -var="cloudflare_account_id=${CLOUDFLARE_ACCOUNT_ID:-dummy}" \
        -var="cloudflare_zone_id=${CLOUDFLARE_ZONE_ID:-dummy}" \
        -var="tunnel_name=${TUNNEL_NAME:-dummy}" \
        -var="domain=${DOMAIN:-example.com}" \
        -var="subdomain=${SUBDOMAIN:-}" \
        -var="service_port=${SERVICE_PORT:-8080}" \
        -var="auth_emails=[$EMAILS_TF]" \
        -var="auth_ip_ranges=[$IPS_TF]" \
        -var="config_output_path=$CF_DIR/cloudflared"
else
    echo "No Terraform state found, skipping..."
fi

echo -e "${YELLOW}Cleaning up local files...${NC}"
rm -rf "$CF_DIR/cloudflared/"*.json "$CF_DIR/cloudflared/"*.yml
rm -rf "$CF_DIR/terraform/.terraform"
rm -f "$CF_DIR/terraform/terraform.tfstate"*
rm -f "$CF_DIR/terraform/.terraform.lock.hcl"

echo ""
echo -e "${GREEN}=== Destruction Complete ===${NC}"
