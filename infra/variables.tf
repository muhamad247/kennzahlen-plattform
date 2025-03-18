variable "subscription_id" {
  description = "Azure-Subscription, in der alles angelegt wird"
  type        = string
}

variable "name" {
  description = "Präfix für alle Ressourcen"
  type        = string
  default     = "kennzahlen"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,15}$", var.name))
    error_message = "3 bis 16 Zeichen: Kleinbuchstaben, Ziffern, Bindestrich."
  }
}

variable "standort" {
  description = "Azure-Region"
  type        = string
  default     = "germanywestcentral"
}

variable "image" {
  description = "Container-Image der API, z. B. ghcr.io/<benutzer>/kennzahlen-plattform:1.0.0"
  type        = string
}

variable "min_instanzen" {
  description = "Mindestzahl laufender Instanzen; ab 2 übersteht die API den Ausfall einer Instanz"
  type        = number
  default     = 2

  validation {
    condition     = var.min_instanzen >= 1 && var.min_instanzen <= 10
    error_message = "Zwischen 1 und 10."
  }
}

variable "max_instanzen" {
  description = "Obergrenze beim automatischen Hochskalieren"
  type        = number
  default     = 5
}

variable "db_hochverfuegbar" {
  description = "Datenbank mit Standby in einer zweiten Verfügbarkeitszone (teurere SKU nötig)"
  type        = bool
  default     = false
}
