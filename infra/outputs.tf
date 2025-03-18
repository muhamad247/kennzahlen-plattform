output "api_url" {
  description = "Öffentliche Adresse der API"
  value       = "https://${azurerm_container_app.api.ingress[0].fqdn}"
}

output "datenbank_server" {
  value = azurerm_postgresql_flexible_server.db.fqdn
}

output "key_vault" {
  value = azurerm_key_vault.kv.name
}

output "einrichten_starten" {
  description = "Befehl, der das Schema einspielt"
  value       = "az containerapp job start -n ${azurerm_container_app_job.einrichten.name} -g ${azurerm_resource_group.rg.name}"
}
