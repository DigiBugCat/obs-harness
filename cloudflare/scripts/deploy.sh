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

echo -e "${GREEN}=== OBS Harness Cloudflare Tunnel Deployment ===${NC}"
echo ""

# Check for required tools
for tool in docker terraform; do
    if ! command -v $tool &> /dev/null; then
        # Try tofu as terraform alternative
        if [ "$tool" = "terraform" ] && command -v tofu &> /dev/null; then
            TF_CMD="tofu"
            continue
        fi
        echo -e "${RED}Error: $tool is not installed${NC}"
        exit 1
    fi
done
TF_CMD="${TF_CMD:-terraform}"

# Check for docker compose
if ! docker compose version &> /dev/null; then
    echo -e "${RED}Error: docker compose is not available${NC}"
    exit 1
fi

# Load environment variables
ENV_FILE="$PROJECT_ROOT/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}Error: .env file not found at $ENV_FILE${NC}"
    echo "Please create it from .env.example"
    exit 1
fi

source "$ENV_FILE"

# Validate required variables
REQUIRED_VARS=(
    "CLOUDFLARE_API_KEY"
    "CLOUDFLARE_EMAIL"
    "CLOUDFLARE_ACCOUNT_ID"
    "CLOUDFLARE_ZONE_ID"
    "TUNNEL_NAME"
    "DOMAIN"
    "SERVICE_PORT"
    "AUTH_EMAILS"
    "AUTH_IP_RANGES"
)

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        echo -e "${RED}Error: $var is not set in .env${NC}"
        exit 1
    fi
done

# Create cloudflared directory if it doesn't exist
mkdir -p "$CF_DIR/cloudflared"

# Convert comma-separated lists to Terraform list format
IFS=',' read -ra EMAIL_ARRAY <<< "$AUTH_EMAILS"
EMAILS_TF=$(printf '"%s",' "${EMAIL_ARRAY[@]}" | sed 's/,$//')

IFS=',' read -ra IP_ARRAY <<< "$AUTH_IP_RANGES"
IPS_TF=$(printf '"%s",' "${IP_ARRAY[@]}" | sed 's/,$//')

echo -e "${YELLOW}Initializing Terraform...${NC}"
cd "$CF_DIR/terraform"
$TF_CMD init

echo -e "${YELLOW}Applying Terraform configuration...${NC}"
$TF_CMD apply -auto-approve \
    -var="cloudflare_api_key=$CLOUDFLARE_API_KEY" \
    -var="cloudflare_email=$CLOUDFLARE_EMAIL" \
    -var="cloudflare_account_id=$CLOUDFLARE_ACCOUNT_ID" \
    -var="cloudflare_zone_id=$CLOUDFLARE_ZONE_ID" \
    -var="tunnel_name=$TUNNEL_NAME" \
    -var="domain=$DOMAIN" \
    -var="subdomain=${SUBDOMAIN:-}" \
    -var="service_port=$SERVICE_PORT" \
    -var="auth_emails=[$EMAILS_TF]" \
    -var="auth_ip_ranges=[$IPS_TF]" \
    -var="session_duration=${SESSION_DURATION:-24h}" \
    -var="config_output_path=$CF_DIR/cloudflared"

# Set permissions readable by cloudflared container (runs as nonroot user)
chmod 644 "$CF_DIR/cloudflared/credentials.json"

echo ""
echo -e "${YELLOW}Building and starting Docker containers...${NC}"
cd "$PROJECT_ROOT"
docker compose up -d --build

echo ""
echo -e "${GREEN}=== Deployment Complete ===${NC}"
echo ""
TUNNEL_URL=$($TF_CMD -chdir="$CF_DIR/terraform" output -raw tunnel_url 2>/dev/null || echo "https://${SUBDOMAIN:-}${SUBDOMAIN:+.}$DOMAIN")
echo -e "Service URL: ${GREEN}$TUNNEL_URL${NC}"
echo ""
echo "To view logs: docker compose logs -f"
echo "To stop: docker compose down"
