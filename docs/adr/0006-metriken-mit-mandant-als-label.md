# 0006: Metriken mit Prometheus, Mandant und Routenvorlage als Labels

Status: angenommen

## Kontext

Im Betrieb ist die erste Frage meist: Betrifft ein Problem alle Mandanten oder nur einen? Dafür müssen Anfragen, Fehler und Antwortzeiten je Mandant sichtbar sein.

## Entscheidung

- Die API stellt unter `/metrics` Zähler und Histogramme im Prometheus-Format bereit, mit den Labels `mandant`, `route` und `status`.
- Als Route zählt die Vorlage (`/v1/kennzahlen`), nicht der tatsächliche Pfad mit Parametern. Unbekannte Pfade landen gesammelt unter `unbekannt`. Sonst entstünde für jeden Aufruf von außen eine neue Zeitreihe.
- Als Mandant steht der Name im Label, damit das Dashboard ohne Nachschlagen lesbar ist.
- Jede Anfrage erzeugt außerdem eine Logzeile als JSON mit Request-ID, Mandant, Route, Status und Dauer. Die Request-ID wird vom Load Balancer gesetzt und in der Antwort zurückgegeben, so lässt sich ein Fehler eines Kunden im Log finden.
- `/metrics` ist von außen gesperrt (nginx), Prometheus fragt die Instanzen direkt ab.
- Die Alarmregeln (`monitoring/alarme.yml`) haben eigene Unit-Tests (`promtool test rules`).

## Konsequenzen

- Die Zahl der Zeitreihen wächst mit Mandanten × Routen × Statuscodes. Bei einigen Hundert Mandanten ist das unproblematisch, bei Zehntausenden nicht mehr. Dann würde man den Mandanten aus den Metriken nehmen und Auswertungen je Mandant aus den Logs machen.
- Wird ein Mandant umbenannt, beginnt seine Zeitreihe neu. Das ist selten und wird in Kauf genommen. Mit der Mandanten-ID wäre es stabil, aber schlechter lesbar.
- Der Datenbankstatus (`datenbank_bereit`) wird bei jeder Abfrage durch Prometheus frisch geprüft. Ein erster Entwurf hat den Wert nur bei Aufrufen von `/ready` gesetzt. Instanzen ohne solche Aufrufe meldeten dadurch dauerhaft „Datenbank nicht erreichbar“. Aufgefallen ist das beim Test mit einem echten Prometheus.
