variable "cloudflare_api_key" {
  description = "Cloudflare Global API Key"
  type        = string
  sensitive   = true
}

variable "cloudflare_email" {
  description = "Cloudflare account email"
  type        = string
}

variable "cloudflare_account_id" {
  description = "Your Cloudflare account ID"
  type        = string
}

variable "cloudflare_zone_id" {
  description = "The zone ID for your domain in Cloudflare"
  type        = string
}

variable "tunnel_name" {
  description = "Name for the Cloudflare tunnel (must be unique)"
  type        = string
}

variable "domain" {
  description = "The domain name (e.g., example.com)"
  type        = string
}

variable "subdomain" {
  description = "Subdomain for the service (leave empty for root domain)"
  type        = string
  default     = ""
}

variable "service_port" {
  description = "The port your service runs on"
  type        = number
  default     = 8080
}

variable "enable_access_protection" {
  description = "Enable Cloudflare Access protection (edge-level auth). Set to false if using app-level auth only."
  type        = bool
  default     = false
}

variable "auth_emails" {
  description = "List of email addresses allowed to access (only used if enable_access_protection=true)"
  type        = list(string)
  default     = []
}

variable "auth_ip_ranges" {
  description = "List of IP addresses or CIDR ranges allowed to access"
  type        = list(string)
  default     = []
}

variable "session_duration" {
  description = "How long access sessions last (e.g., '24h', '7d')"
  type        = string
  default     = "24h"
}

variable "config_output_path" {
  description = "Path where tunnel config files will be written"
  type        = string
  default     = "../cloudflared"
}
