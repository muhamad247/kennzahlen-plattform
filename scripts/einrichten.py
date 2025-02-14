"""Datenbank einrichten: Rolle der Anwendung anlegen und Schema einspielen.

    DATABASE_ADMIN_URL=... APP_DB_PASSWORT=... python -m scripts.einrichten

Kann beliebig oft laufen; vorhandene Tabellen und Daten bleiben erhalten.
"""

import os
import sys
import time

import psycopg

from app.verwaltung import einrichten


def main() -> None:
    admin_url = os.environ["DATABASE_ADMIN_URL"]
    passwort = os.environ["APP_DB_PASSWORT"]
    for versuch in range(30):
        try:
            einrichten(admin_url, passwort)
            print("Datenbank eingerichtet")
            return
        except psycopg.OperationalError as fehler:
            print(f"Datenbank noch nicht erreichbar ({versuch + 1}/30): {fehler}", file=sys.stderr)
            time.sleep(2)
    sys.exit("Datenbank nicht erreichbar")


if __name__ == "__main__":
    main()
