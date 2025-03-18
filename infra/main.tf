# Betrieb in Azure: Container Apps für die API, PostgreSQL Flexible Server als Datenbank,
# Key Vault für alle Zugangsdaten. Begründung der Wahl: docs/adr/0005.

data "azurerm_client_config" "aktuell" {}

resource "random_string" "suffix" {
  length  = 6
  upper   = false
  special = false
}

# Landen im Terraform-State. Der State gehört deshalb in ein verschlüsseltes Backend
# mit eingeschränktem Zugriff (siehe README, Abschnitt Grenzen).
resource "random_password" "db_admin" {
  length  = 32
  special = false
}

resource "random_password" "db_app" {
  length  = 32
  special = false
}

locals {
  suffix   = random_string.suffix.result
  tags     = { projekt = "kennzahlen-plattform", verwaltet_von = "terraform" }
  db_admin = "kennzahlen_admin"
  db_host  = azurerm_postgresql_flexible_server.db.fqdn
}

resource "azurerm_resource_group" "rg" {
  name     = "${var.name}-rg"
  location = var.standort
  tags     = local.tags
}

# ---------------------------------------------------------------- Datenbank

resource "azurerm_postgresql_flexible_server" "db" {
  name                          = "${var.name}-db-${local.suffix}"
  resource_group_name           = azurerm_resource_group.rg.name
  location                      = azurerm_resource_group.rg.location
  version                       = "16"
  administrator_login           = local.db_admin
  administrator_password        = random_password.db_admin.result
  sku_name                      = var.db_hochverfuegbar ? "GP_Standard_D2ds_v5" : "B_Standard_B1ms"
  storage_mb                    = 32768
  backup_retention_days         = 7
  zone                          = "1"
  public_network_access_enabled = true
  tags                          = local.tags

  dynamic "high_availability" {
    for_each = var.db_hochverfuegbar ? [1] : []
    content {
      mode                      = "ZoneRedundant"
      standby_availability_zone = "2"
    }
  }

  lifecycle {
    # Azure tauscht Primär- und Standby-Zone nach einem Failover; das ist kein Drift
    ignore_changes = [zone, high_availability[0].standby_availability_zone]
  }
}

resource "azurerm_postgresql_flexible_server_database" "kennzahlen" {
  name      = "kennzahlen"
  server_id = azurerm_postgresql_flexible_server.db.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# 0.0.0.0 bis 0.0.0.0 heißt bei Azure: Zugriff nur aus Azure-Diensten.
# Für Produktion besser ein eigenes VNet mit privatem Endpunkt (docs/adr/0005).
resource "azurerm_postgresql_flexible_server_firewall_rule" "azure_dienste" {
  name             = "azure-dienste"
  server_id        = azurerm_postgresql_flexible_server.db.id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# ---------------------------------------------------------------- Key Vault

resource "azurerm_key_vault" "kv" {
  name                       = "${var.name}-kv-${local.suffix}"
  resource_group_name        = azurerm_resource_group.rg.name
  location                   = azurerm_resource_group.rg.location
  tenant_id                  = data.azurerm_client_config.aktuell.tenant_id
  sku_name                   = "standard"
  rbac_authorization_enabled = true
  soft_delete_retention_days = 7
  purge_protection_enabled   = false
  tags                       = local.tags
}

# Wer Terraform ausführt, darf Geheimnisse schreiben
resource "azurerm_role_assignment" "deployer_secrets" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.aktuell.object_id
}

# Die Container lesen Geheimnisse über eine eigene Identität, nicht über Passwörter
resource "azurerm_user_assigned_identity" "app" {
  name                = "${var.name}-app-id"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  tags                = local.tags
}

resource "azurerm_role_assignment" "app_secrets" {
  scope                = azurerm_key_vault.kv.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

resource "azurerm_key_vault_secret" "database_url" {
  name         = "database-url"
  key_vault_id = azurerm_key_vault.kv.id
  value        = "postgresql://kennzahlen_app:${random_password.db_app.result}@${local.db_host}:5432/kennzahlen?sslmode=require"
  depends_on   = [azurerm_role_assignment.deployer_secrets]
}

resource "azurerm_key_vault_secret" "database_admin_url" {
  name         = "database-admin-url"
  key_vault_id = azurerm_key_vault.kv.id
  value        = "postgresql://${local.db_admin}:${random_password.db_admin.result}@${local.db_host}:5432/kennzahlen?sslmode=require"
  depends_on   = [azurerm_role_assignment.deployer_secrets]
}

resource "azurerm_key_vault_secret" "app_db_passwort" {
  name         = "app-db-passwort"
  key_vault_id = azurerm_key_vault.kv.id
  value        = random_password.db_app.result
  depends_on   = [azurerm_role_assignment.deployer_secrets]
}

# ---------------------------------------------------------------- Container Apps

resource "azurerm_log_analytics_workspace" "logs" {
  name                = "${var.name}-logs"
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "PerGB2018"
  retention_in_days   = 30
  tags                = local.tags
}

resource "azurerm_container_app_environment" "env" {
  name                       = "${var.name}-env"
  resource_group_name        = azurerm_resource_group.rg.name
  location                   = azurerm_resource_group.rg.location
  log_analytics_workspace_id = azurerm_log_analytics_workspace.logs.id
  tags                       = local.tags
}

# Einmalig nach dem ersten Deployment und nach Schemaänderungen starten:
#   az containerapp job start -n <name>-einrichten -g <name>-rg
resource "azurerm_container_app_job" "einrichten" {
  name                         = "${var.name}-einrichten"
  resource_group_name          = azurerm_resource_group.rg.name
  location                     = azurerm_resource_group.rg.location
  container_app_environment_id = azurerm_container_app_environment.env.id
  replica_timeout_in_seconds   = 300
  replica_retry_limit          = 1
  tags                         = local.tags

  manual_trigger_config {
    parallelism              = 1
    replica_completion_count = 1
  }

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  secret {
    name                = "database-admin-url"
    key_vault_secret_id = azurerm_key_vault_secret.database_admin_url.versionless_id
    identity            = azurerm_user_assigned_identity.app.id
  }

  secret {
    name                = "app-db-passwort"
    key_vault_secret_id = azurerm_key_vault_secret.app_db_passwort.versionless_id
    identity            = azurerm_user_assigned_identity.app.id
  }

  template {
    container {
      name    = "einrichten"
      image   = var.image
      cpu     = 0.25
      memory  = "0.5Gi"
      command = ["python", "-m", "scripts.einrichten"]

      env {
        name        = "DATABASE_ADMIN_URL"
        secret_name = "database-admin-url"
      }
      env {
        name        = "APP_DB_PASSWORT"
        secret_name = "app-db-passwort"
      }
    }
  }

  depends_on = [azurerm_role_assignment.app_secrets]
}

resource "azurerm_container_app" "api" {
  name                         = "${var.name}-api"
  resource_group_name          = azurerm_resource_group.rg.name
  container_app_environment_id = azurerm_container_app_environment.env.id
  revision_mode                = "Single"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.app.id]
  }

  secret {
    name                = "database-url"
    key_vault_secret_id = azurerm_key_vault_secret.database_url.versionless_id
    identity            = azurerm_user_assigned_identity.app.id
  }

  ingress {
    external_enabled = true
    target_port      = 8000

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    # Mindestens zwei Instanzen, Azure verteilt sie auf verschiedene Hosts
    min_replicas = var.min_instanzen
    max_replicas = var.max_instanzen

    http_scale_rule {
      name                = "gleichzeitige-anfragen"
      concurrent_requests = "50"
    }

    container {
      name   = "api"
      image  = var.image
      cpu    = 0.5
      memory = "1Gi"

      env {
        name        = "DATABASE_URL"
        secret_name = "database-url"
      }
      env {
        name  = "LOG_LEVEL"
        value = "INFO"
      }

      # Lebt der Prozess? Sonst Neustart.
      liveness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/health"
      }

      # Erreicht die Instanz die Datenbank? Sonst bekommt sie keinen Verkehr.
      readiness_probe {
        transport = "HTTP"
        port      = 8000
        path      = "/ready"
      }
    }
  }

  depends_on = [azurerm_role_assignment.app_secrets]
}
