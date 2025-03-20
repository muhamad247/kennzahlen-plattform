# 0005: Azure Container Apps und PostgreSQL Flexible Server, beschrieben mit Terraform

Status: angenommen

## Kontext

Die API läuft als Container. Gesucht ist eine Plattform, die mehrere Instanzen, automatisches Skalieren, HTTPS und Neustarts übernimmt, ohne dass ein eigenes Kubernetes-Cluster betrieben werden muss. Azure, weil es bei Unternehmen im DACH-Raum verbreitet ist.

| | Azure App Service | Azure Container Apps | Azure Kubernetes Service |
|---|---|---|---|
| Betriebsaufwand | gering | gering | hoch |
| Container | ja | ja | ja |
| Skalieren nach Last | ja | ja, auch auf Anfragen je Instanz | ja, frei konfigurierbar |
| Jobs (z. B. Migration) | eingeschränkt | ja | ja |

## Entscheidung

- **Azure Container Apps** für die API (mindestens 2, höchstens 5 Instanzen, skaliert ab 50 gleichzeitigen Anfragen je Instanz) und ein **Container App Job** für das Einspielen des Schemas.
- **PostgreSQL Flexible Server**, Version 16 wie lokal. Optional mit Standby in einer zweiten Zone (`db_hochverfuegbar`).
- **Key Vault** für alle Zugangsdaten. Die Container lesen sie über eine eigene verwaltete Identität. Im Container-Image und in den Umgebungsvariablen steht kein Passwort im Klartext.
- Alles in **Terraform** (`infra/`). `terraform test` prüft die Konfiguration mit Attrappen des Azure-Providers, also ohne Azure-Konto, z. B. dass die Datenbank-URL nur aus dem Key Vault kommt.

## Konsequenzen

- Die Datenbank erlaubt Zugriffe aus Azure-Diensten (Firewall-Regel 0.0.0.0). Das gilt für alle Azure-Dienste, auch die anderer Kunden. Dann schützt nur noch das Passwort. Für Produktion gehören API und Datenbank in ein eigenes virtuelles Netz mit privatem Endpunkt. Das ist hier weggelassen, weil es die Konfiguration deutlich größer macht.
- Die zufällig erzeugten Passwörter stehen im Terraform-State. Der State gehört deshalb in ein Backend mit Verschlüsselung und eingeschränktem Zugriff, z. B. ein Azure Storage Account. Neuere Terraform-Versionen können Passwörter auch als write-only übergeben, sodass sie nicht im State landen.
- Prometheus und Grafana laufen nur lokal. In Azure würde man die Metriken an Azure Monitor (Managed Prometheus) schicken. Die Alarmregeln bleiben dieselben.
- Ein echtes Deployment ist nicht Teil der CI, weil es ein Azure-Konto braucht und Geld kostet.
