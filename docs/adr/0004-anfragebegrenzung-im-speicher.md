# 0004: Anfragebegrenzung je Mandant im Speicher jeder Instanz

Status: angenommen

## Kontext

Alle Mandanten teilen sich Instanzen und Datenbank. Ein Mandant mit einem fehlerhaften Skript in einer Endlosschleife soll die anderen nicht ausbremsen.

## Entscheidung

Token Bucket je Mandant: standardmäßig 600 Anfragen pro Minute, kurzfristig bis zu 100 auf einmal (`RATELIMIT_PRO_MINUTE`, `RATELIMIT_BURST`). Ist der Eimer leer, antwortet die API mit 429 und sagt im Header `Retry-After`, wann es wieder geht. Der Zähler liegt im Speicher der jeweiligen Instanz.

Die Alternative wäre ein gemeinsamer Zähler in Redis. Das wäre genau, brächte aber einen weiteren Dienst, der betrieben und überwacht werden muss und selbst ausfallen kann.

## Konsequenzen

- Bei zwei Instanzen ist das tatsächliche Limit bis zu doppelt so hoch. Ziel ist hier Schutz vor Ausreißern, nicht Abrechnung nach Anfragen. Die Ungenauigkeit ist deshalb vertretbar. Das Limit je Instanz lässt sich als gewünschtes Gesamtlimit geteilt durch die Zahl der Instanzen einstellen.
- Nach einem Neustart beginnt der Zähler voll. Auch das ist für den Zweck unkritisch.
- Wird das Limit später Teil des Vertrags (z. B. Tarife mit unterschiedlichen Kontingenten), ist ein gemeinsamer Zähler nötig. Dann wird Redis oder ein Gateway wie Azure API Management eingeführt.
- Im Lasttest mit zwei Mandanten und 30 parallelen Nutzern wurden 87 % der Anfragen mit 429 abgelehnt. Das Limit greift also. Eine abgelehnte Anfrage kostet nur die Prüfung des Schlüssels (ein Indexzugriff), keine Auswertung.
