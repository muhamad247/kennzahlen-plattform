# 0002: API-Schlüssel statt OAuth, gespeichert nur als SHA-256-Hash

Status: angenommen

## Kontext

Die Clients sind Programme der Kunden (Export aus der Buchhaltung, Reporting-Tools), keine Menschen im Browser. Es braucht eine Anmeldung, die sich einfach in solche Skripte einbauen lässt, und eine Möglichkeit, Zugänge zu sperren.

## Entscheidung

Jeder Mandant bekommt einen oder mehrere API-Schlüssel (`kz_` + 32 zufällige Bytes). Der Client schickt ihn im Header `X-API-Key`. In der Datenbank liegt nur der SHA-256-Hash. Der Schlüssel im Klartext wird genau einmal beim Anlegen ausgegeben.

Warum SHA-256 und nicht bcrypt oder Argon2: Langsame Hashfunktionen schützen schwache Passwörter gegen Durchprobieren. Ein Schlüssel mit 256 Bit Zufall lässt sich nicht durchprobieren, auch nicht mit einem schnellen Hash. Außerdem muss der Hash deterministisch sein, damit die Datenbank den Mandanten mit einem einzigen Indexzugriff findet. Mit gesalzenen Hashes müsste man jeden gespeicherten Schlüssel einzeln prüfen.

Ein Mandant kann mehrere gültige Schlüssel haben. So lässt sich ein Schlüssel ohne Ausfall tauschen: neuen anlegen, Client umstellen, alten widerrufen (`python -m scripts.mandant`).

## Konsequenzen

- Gelangt die Datenbank in falsche Hände, sind die Schlüssel trotzdem nicht nutzbar.
- Schlüssel laufen nicht von selbst ab. Für den Anfang genügt der manuelle Tausch, ein Ablaufdatum ließe sich als Spalte ergänzen.
- Es gibt keine Rechte innerhalb eines Mandanten (z. B. nur lesen). Wenn das gebraucht wird, wäre OAuth 2.0 mit Client Credentials und Scopes der nächste Schritt, etwa über Microsoft Entra ID.
- Die Schlüssel müssen über HTTPS übertragen werden. In Azure erzwingt das der Ingress der Container Apps, lokal läuft alles über HTTP.
