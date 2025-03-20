# Prüft die Infrastruktur ohne Azure-Konto: der Provider wird durch Attrappen ersetzt.
#   terraform test

mock_provider "azurerm" {
  mock_data "azurerm_client_config" {
    defaults = {
      tenant_id = "00000000-0000-0000-0000-000000000001"
      object_id = "00000000-0000-0000-0000-000000000002"
    }
  }

  # Attrappen liefern sonst Zufallstexte; Azure-IDs müssen aber gültig aufgebaut sein
  mock_resource "azurerm_log_analytics_workspace" {
    defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/kennzahlen-rg/providers/Microsoft.OperationalInsights/workspaces/kennzahlen-logs" }
  }
  mock_resource "azurerm_container_app_environment" {
    defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/kennzahlen-rg/providers/Microsoft.App/managedEnvironments/kennzahlen-env" }
  }
  mock_resource "azurerm_postgresql_flexible_server" {
    defaults = {
      id   = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/kennzahlen-rg/providers/Microsoft.DBforPostgreSQL/flexibleServers/kennzahlen-db"
      fqdn = "kennzahlen-db.postgres.database.azure.com"
    }
  }
  mock_resource "azurerm_key_vault" {
    defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/kennzahlen-rg/providers/Microsoft.KeyVault/vaults/kennzahlen-kv" }
  }
  mock_resource "azurerm_user_assigned_identity" {
    defaults = {
      id           = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/kennzahlen-rg/providers/Microsoft.ManagedIdentity/userAssignedIdentities/kennzahlen-app-id"
      principal_id = "00000000-0000-0000-0000-000000000003"
    }
  }
  mock_resource "azurerm_key_vault_secret" {
    defaults = {
      id             = "https://kennzahlen-kv.vault.azure.net/secrets/geheimnis/0123456789abcdef0123456789abcdef"
      versionless_id = "https://kennzahlen-kv.vault.azure.net/secrets/geheimnis"
    }
  }
}

variables {
  subscription_id = "00000000-0000-0000-0000-000000000000"
  image           = "ghcr.io/beispiel/kennzahlen-plattform:1.0.0"
}

run "standard" {
  command = apply

  assert {
    condition     = azurerm_container_app.api.template[0].min_replicas == 2
    error_message = "Die API muss mit mindestens zwei Instanzen laufen."
  }

  assert {
    condition     = azurerm_container_app.api.template[0].container[0].readiness_probe[0].path == "/ready" && azurerm_container_app.api.template[0].container[0].liveness_probe[0].path == "/health"
    error_message = "Liveness muss /health prüfen, Readiness /ready."
  }

  assert {
    condition = alltrue([
      for e in azurerm_container_app.api.template[0].container[0].env :
      e.secret_name == "database-url" && e.value == null if e.name == "DATABASE_URL"
    ])
    error_message = "Die Datenbank-URL darf nur als Geheimnis aus dem Key Vault kommen, nie als Klartext."
  }

  assert {
    condition     = alltrue([for s in azurerm_container_app.api.secret : s.key_vault_secret_id != null && s.value == null])
    error_message = "Alle Geheimnisse der API müssen aus dem Key Vault kommen."
  }

  assert {
    condition     = azurerm_key_vault.kv.rbac_authorization_enabled
    error_message = "Key-Vault-Zugriff nur über Rollen."
  }

  assert {
    condition     = azurerm_postgresql_flexible_server.db.sku_name == "B_Standard_B1ms" && length(azurerm_postgresql_flexible_server.db.high_availability) == 0
    error_message = "Ohne db_hochverfuegbar: kleine SKU, kein Standby."
  }

  assert {
    condition     = startswith(azurerm_key_vault_secret.database_url.value, "postgresql://kennzahlen_app:") && endswith(azurerm_key_vault_secret.database_url.value, "sslmode=require")
    error_message = "Die API verbindet sich als eingeschränkte Rolle und nur verschlüsselt."
  }
}

run "hochverfuegbar" {
  command = apply

  variables {
    db_hochverfuegbar = true
    min_instanzen     = 3
  }

  assert {
    condition     = azurerm_postgresql_flexible_server.db.high_availability[0].mode == "ZoneRedundant" && startswith(azurerm_postgresql_flexible_server.db.sku_name, "GP_")
    error_message = "Hochverfügbare Datenbank braucht Standby in zweiter Zone und eine General-Purpose-SKU."
  }

  assert {
    condition     = azurerm_container_app.api.template[0].min_replicas == 3
    error_message = "min_instanzen wird nicht übernommen."
  }
}

run "ungueltiger_name" {
  command = plan

  variables {
    name = "Kennzahlen_Prod"
  }

  expect_failures = [var.name]
}
