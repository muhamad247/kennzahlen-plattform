"""Mandanten und Schlüssel verwalten.

    python -m scripts.mandant anlegen "Muster GmbH"
    python -m scripts.mandant schluessel <mandant-id>
    python -m scripts.mandant widerrufen <schluessel>

Braucht DATABASE_ADMIN_URL. Der Schlüssel wird genau einmal ausgegeben.
"""

import argparse
import os
import sys

from app.verwaltung import mandant_anlegen, schluessel_hinzufuegen, schluessel_widerrufen


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    befehle = parser.add_subparsers(dest="befehl", required=True)
    anlegen = befehle.add_parser("anlegen", help="neuer Mandant mit erstem Schlüssel")
    anlegen.add_argument("name")
    anlegen.add_argument("--nur-schluessel", action="store_true", help="nur den Schlüssel ausgeben")
    befehle.add_parser("schluessel", help="weiterer Schlüssel").add_argument("mandant_id")
    befehle.add_parser("widerrufen", help="Schlüssel sperren").add_argument("schluessel")
    args = parser.parse_args()
    admin_url = os.environ["DATABASE_ADMIN_URL"]

    if args.befehl == "anlegen":
        mandant_id, schluessel = mandant_anlegen(admin_url, args.name)
        print(
            schluessel if args.nur_schluessel else f"Mandant {mandant_id}\nSchlüssel {schluessel}"
        )
    elif args.befehl == "schluessel":
        print(schluessel_hinzufuegen(admin_url, args.mandant_id))
    elif not schluessel_widerrufen(admin_url, args.schluessel):
        sys.exit("Schlüssel unbekannt oder schon widerrufen")


if __name__ == "__main__":
    main()
