# 0004: Anfragebegrenzung je Mandant im Speicher jeder Instanz

Status: angenommen

## Kontext

Alle Mandanten teilen sich Instanzen und Datenbank. Ein Mandant mit einem fehlerhaften Skript in einer Endlosschleife soll die anderen nicht ausbremsen.

## Entscheidung

Token Bucket je Mandant: standardmäßig 600 Anfragen pro Minute, kurzfristig bis zu 100 auf einmal (`RATELIMIT_PRO_MINUTE`, `RATELIMIT_BURST`). Ist der Eimer leer, antwortet die API mit 429 und sagt im Header `Retry-After`, wann es wieder geht. Der Zähler liegt im Speicher der jeweiligen Instanz.

Die Alternative wäre ein gemeinsamer Zähler in Redis. Das wäre genau, brächte aber einen weiteren Dienst, der betrieben und überwacht werden muss und selbst ausfallen kann.

## Konsequenzen

- Bei zwei Instanzen ist das tatsächliche Limit bis zu doppelt so hoch. Ziel ist hier Schutz vor Ausreißern, nicht Abrechnung nach Anfragen. Die Ungenauigkeit ist deshalb vertretbar. Das Limit je Instanz lässt sich als gewünschtes Gesamtlimit geteilt durch die Zahl der Instanzen einstellen.
- Fällt eine Instanz aus, gilt das Umgekehrte: Die verbleibende Instanz bekommt den ganzen Verkehr, hat aber nur ihr eigenes Kontingent. Das wirksame Limit je Mandant halbiert sich. Der erste Lauf des Ausfalltests in GitHub Actions hat das gezeigt: Ein Mandant mit rund 20 Anfragen pro Sekunde bekam während des Ausfalls 12 und kurz nach dem Neustart weitere 71 Antworten mit 429. Kein Fehler der Ausfallsicherheit, aber ein spürbarer Effekt für Mandanten nahe am Limit. Abhilfe wäre ein gemeinsamer Zähler (siehe unten) oder ein Limit je Instanz mit Reserve für den Ausfall.
- Nach einem Neustart beginnt der Zähler voll. Auch das ist für den Zweck unkritisch.
- Wird das Limit später Teil des Vertrags (z. B. Tarife mit unterschiedlichen Kontingenten), ist ein gemeinsamer Zähler nötig. Dann wird Redis oder ein Gateway wie Azure API Management eingeführt.
- Im Lasttest mit zwei Mandanten und 30 parallelen Nutzern wurden 87 % der Anfragen mit 429 abgelehnt. Das Limit greift also. Eine abgelehnte Anfrage kostet nur die Prüfung des Schlüssels (ein Indexzugriff), keine Auswertung.
