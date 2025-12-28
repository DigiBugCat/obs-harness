terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.1"
    }
  }
}

# Provider configuration using Global API Key
provider "cloudflare" {
  api_key = var.cloudflare_api_key
  email   = var.cloudflare_email
}

# Generate a secret for the tunnel
resource "random_password" "tunnel_secret" {
  length  = 64
  special = false
}

# Create the tunnel
resource "cloudflare_tunnel" "main" {
  account_id = var.cloudflare_account_id
  name       = var.tunnel_name
  secret     = base64encode(random_password.tunnel_secret.result)
}

# Configure tunnel routing
resource "cloudflare_tunnel_config" "main" {
  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_tunnel.main.id

  config {
    ingress_rule {
      hostname = local.full_domain
      service  = "http://localhost:${var.service_port}"
    }

    # Catch-all rule
    ingress_rule {
      service = "http_status:404"
    }
  }
}

# DNS record for the tunnel
resource "cloudflare_record" "tunnel_dns" {
  zone_id = var.cloudflare_zone_id
  name    = var.subdomain != "" ? var.subdomain : "@"
  type    = "CNAME"
  content = "${cloudflare_tunnel.main.id}.cfargotunnel.com"
  proxied = true
  ttl     = 1
}

# Access application (protected endpoint)
resource "cloudflare_access_application" "main" {
  zone_id                   = var.cloudflare_zone_id
  name                      = "${var.tunnel_name}-access"
  domain                    = local.full_domain
  type                      = "self_hosted"
  session_duration          = var.session_duration
  auto_redirect_to_identity = false
}

# Bypass policy for allowed IPs (no auth required)
resource "cloudflare_access_policy" "ip_bypass_policy" {
  zone_id        = var.cloudflare_zone_id
  application_id = cloudflare_access_application.main.id
  name           = "${var.tunnel_name}-ip-bypass"
  decision       = "bypass"
  precedence     = 1

  include {
    ip = var.auth_ip_ranges
  }
}

# Allow policy for email auth (fallback for non-allowed IPs)
resource "cloudflare_access_policy" "email_policy" {
  zone_id        = var.cloudflare_zone_id
  application_id = cloudflare_access_application.main.id
  name           = "${var.tunnel_name}-email-allow"
  decision       = "allow"
  precedence     = 2

  include {
    email = var.auth_emails
  }
}

# Generate configuration files
resource "local_file" "tunnel_credentials" {
  content = jsonencode({
    AccountTag   = var.cloudflare_account_id
    TunnelID     = cloudflare_tunnel.main.id
    TunnelName   = var.tunnel_name
    TunnelSecret = base64encode(random_password.tunnel_secret.result)
  })

  filename        = "${var.config_output_path}/credentials.json"
  file_permission = "0644"
}

resource "local_file" "tunnel_config" {
  content = yamlencode({
    tunnel           = cloudflare_tunnel.main.id
    credentials-file = "/home/nonroot/.cloudflared/credentials.json"
    metrics          = "0.0.0.0:2000"
    no-autoupdate    = true
  })

  filename        = "${var.config_output_path}/config.yml"
  file_permission = "0644"
}

# Local values
locals {
  full_domain = var.subdomain != "" ? "${var.subdomain}.${var.domain}" : var.domain
}
