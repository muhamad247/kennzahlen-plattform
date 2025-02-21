# 0003: Zustandslose Instanzen, mindestens zwei, mit getrennter Health- und Readiness-Prüfung

Status: angenommen

## Kontext

Die API soll weiterlaufen, wenn eine Instanz abstürzt oder bei einem Update neu startet. Eine einzelne Instanz ist bei jedem Deployment kurz weg.

## Entscheidung

- Die Instanzen speichern keinen Zustand, der für die Antwort nötig ist. Alles Wichtige liegt in PostgreSQL. Jede Instanz kann jede Anfrage beantworten.
- Es laufen immer mindestens zwei Instanzen hinter einem Load Balancer: lokal nginx, in Azure der Ingress der Container Apps mit `min_replicas = 2`.
- Zwei getrennte Prüfungen:
  - `/health` (Liveness) prüft nur, ob der Prozess antwortet. Schlägt sie fehl, wird die Instanz neu gestartet. Sie prüft bewusst nicht die Datenbank. Sonst würden bei einem Datenbankproblem alle Instanzen gleichzeitig neu starten, was nichts hilft.
  - `/ready` (Readiness) prüft die Datenbankverbindung. Schlägt sie fehl, bekommt die Instanz keinen Verkehr mehr, läuft aber weiter.
- nginx schickt eine Anfrage an die andere Instanz weiter, wenn die erste nicht erreichbar ist oder mit 502/503 antwortet. Das gilt nur für Verbindungsfehler, damit kein Upload doppelt geschrieben wird.

## Konsequenzen

- `scripts/ausfalltest.py` beendet während laufender Anfragen eine Instanz hart und startet sie später neu. Erwartet wird keine einzige fehlgeschlagene Anfrage. Der Test läuft in GitHub Actions bei jedem Push.
- Die Datenbank bleibt ein Single Point of Failure. In Azure lässt sich dafür ein Standby in einer zweiten Verfügbarkeitszone einschalten (`db_hochverfuegbar = true`). Das braucht eine teurere SKU, weil die Burstable-Klasse keine Hochverfügbarkeit unterstützt.
- Die Anfragebegrenzung liegt im Speicher der Instanz und ist damit die einzige Ausnahme vom zustandslosen Prinzip, siehe ADR 0004.
