"""Ausfalltest gegen den laufenden docker-compose-Stack.

Schickt 40 Sekunden lang Anfragen über den Load Balancer. Nach 10 Sekunden wird
Instanz app1 hart beendet (wie bei einem Absturz), nach 25 Sekunden wieder gestartet.
Erwartung: keine einzige fehlgeschlagene Anfrage.

    docker compose up -d --build
    python -m scripts.ausfalltest
"""

import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

from scripts.demo_daten import erzeugen, senden

URL = "http://localhost:8080"
DAUER_S, AUSFALL_S, NEUSTART_S = 40, 10, 25


def compose(*args: str) -> str:
    return subprocess.run(
        ["docker", "compose", *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def warten_bis_bereit(timeout_s: int = 180) -> None:
    ende = time.monotonic() + timeout_s
    while time.monotonic() < ende:
        try:
            with urllib.request.urlopen(URL + "/ready", timeout=2) as antwort:
                if antwort.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(2)
    sys.exit("Stack wurde nicht bereit")


def _instanz(kopf: str | None) -> str:
    # nach einem Wechsel listet nginx alle versuchten Instanzen; geantwortet hat die letzte
    return (kopf or "?").split(",")[-1].strip()


def anfrage(schluessel: str) -> tuple[str, str]:
    req = urllib.request.Request(
        URL + "/v1/kennzahlen?jahr=2025", headers={"X-API-Key": schluessel}
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as antwort:
            return str(antwort.status), _instanz(antwort.headers.get("X-Instanz"))
    except urllib.error.HTTPError as fehler:
        return str(fehler.code), _instanz(fehler.headers.get("X-Instanz"))
    except (urllib.error.URLError, OSError) as fehler:
        return f"Verbindungsfehler: {fehler}", "-"


def main() -> None:
    warten_bis_bereit()
    ausgabe = compose(
        "run",
        "--rm",
        "-T",
        "einrichten",
        "python",
        "-m",
        "scripts.mandant",
        "anlegen",
        f"Ausfalltest {int(time.time())}",
        "--nur-schluessel",
    )
    schluessel = ausgabe.splitlines()[-1]
    buchungen, budget = erzeugen()
    senden(URL, schluessel, "POST", "/v1/buchungen", buchungen)
    senden(URL, schluessel, "PUT", "/v1/budget", budget)

    phasen = {"vorher": Counter(), "ausfall": Counter(), "danach": Counter()}
    instanzen = {name: set() for name in phasen}
    start = time.monotonic()
    gestoppt = gestartet = False
    while (t := time.monotonic() - start) < DAUER_S:
        if not gestoppt and t >= AUSFALL_S:
            compose("kill", "app1")
            print(f"{t:5.1f} s: app1 beendet")
            gestoppt = True
        if not gestartet and t >= NEUSTART_S:
            compose("start", "app1")
            print(f"{t:5.1f} s: app1 neu gestartet")
            gestartet = True
        phase = "vorher" if not gestoppt else "ausfall" if not gestartet else "danach"
        status, instanz = anfrage(schluessel)
        phasen[phase][status] += 1
        instanzen[phase].add(instanz)
        time.sleep(0.05)

    fehler = 0
    for phase, zaehler in phasen.items():
        print(f"{phase:8} {dict(zaehler)}  Instanzen: {sorted(instanzen[phase])}")
        fehler += sum(n for status, n in zaehler.items() if status != "200")
    if fehler:
        sys.exit(f"{fehler} Anfragen fehlgeschlagen")
    if len(instanzen["ausfall"]) != 1:
        sys.exit("Während des Ausfalls hätte nur eine Instanz antworten dürfen")
    print("Keine fehlgeschlagene Anfrage während des Ausfalls")


if __name__ == "__main__":
    main()
