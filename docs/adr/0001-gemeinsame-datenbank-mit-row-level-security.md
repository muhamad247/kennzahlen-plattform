# 0001: Gemeinsame Datenbank, Trennung der Mandanten über Row-Level Security

Status: angenommen

## Kontext

Mehrere Firmen nutzen dieselbe Plattform. Keine darf die Daten einer anderen sehen, auch nicht durch einen Programmierfehler. Erwartet werden einige Dutzend bis wenige Hundert Mandanten mit überschaubaren Datenmengen (Buchungen eines Jahres: Tausende, nicht Milliarden Zeilen).

Drei übliche Varianten:

| | Datenbank je Mandant | Schema je Mandant | gemeinsame Tabellen |
|---|---|---|---|
| Trennung | physisch, am stärksten | stark | nur logisch |
| Kosten | eine Instanz je Kunde | eine Instanz | eine Instanz |
| Schemaänderung | n-mal ausrollen | n-mal ausrollen | einmal |
| neuer Mandant | Datenbank anlegen | Schema anlegen | eine Zeile |

## Entscheidung

Gemeinsame Tabellen mit einer Spalte `mandant_id` und Row-Level Security (RLS) in PostgreSQL. Die Anwendung setzt zu Beginn jeder Transaktion `app.mandant_id`. Eine Policy lässt nur Zeilen dieses Mandanten durch, beim Lesen (`USING`) wie beim Schreiben (`WITH CHECK`).

Damit das hält:

- Die Anwendung verbindet sich als eigene Rolle `kennzahlen_app`, die weder Eigentümerin der Tabellen ist noch RLS umgehen darf (`NOBYPASSRLS`). Zusätzlich `FORCE ROW LEVEL SECURITY`, falls doch einmal als Eigentümer verbunden wird.
- Der Mandant wird mit `set_config(..., true)` nur für die laufende Transaktion gesetzt. Eine Verbindung kommt also ohne Mandant in den Pool zurück und sieht dann gar nichts.
- Die Abfragen im Code enthalten bewusst keinen Filter auf `mandant_id`. Die Tests beweisen so, dass die Datenbank allein die Trennung durchsetzt.
- Die Tabelle mit den API-Schlüsseln kann die Anwendung nicht lesen. Sie fragt nur über eine Funktion nach, zu welchem Mandanten ein Hash gehört.

## Konsequenzen

- Ein vergessener `WHERE`-Filter führt nicht zu einem Datenleck. `tests/test_mandantentrennung.py` prüft das direkt in der Datenbank, inklusive Versuchen, fremde Zeilen zu ändern oder RLS abzuschalten.
- `COPY FROM` funktioniert auf Tabellen mit RLS nicht. Uploads laufen deshalb über gebündelte `INSERT`s (10.000 Buchungen brauchen lokal etwa 0,2 s, das reicht).
- Ein großer Mandant kann die anderen ausbremsen (Noisy Neighbour). Abhilfe: Anfragebegrenzung je Mandant (ADR 0004). Wächst ein Mandant stark, lässt er sich später in eine eigene Datenbank verschieben, ohne das Schema zu ändern.
- Backups und Wiederherstellung gelten für alle Mandanten gemeinsam. Die Daten eines einzelnen Mandanten wiederherzustellen, ist aufwendiger als bei getrennten Datenbanken.
