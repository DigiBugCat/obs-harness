output "tunnel_id" {
  description = "The ID of the created tunnel"
  value       = cloudflare_tunnel.main.id
}

output "tunnel_url" {
  description = "The public URL for accessing the service"
  value       = "https://${local.full_domain}"
}

output "tunnel_cname" {
  description = "The CNAME target for the tunnel"
  value       = "${cloudflare_tunnel.main.id}.cfargotunnel.com"
}

output "access_application_id" {
  description = "The ID of the Access application (null if access protection disabled)"
  value       = var.enable_access_protection ? cloudflare_access_application.main[0].id : null
}
