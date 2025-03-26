"""Lasttest: Mandanten fragen Kennzahlen ab und laden ab und zu kleine Buchungspakete hoch.

    KENNZAHLEN_SCHLUESSEL=kz_a,kz_b locust -f lasttest/locustfile.py --host http://localhost:8080 \
        --headless -u 50 -r 10 -t 60s
"""

import os
import random

from locust import HttpUser, between, task

SCHLUESSEL = os.environ["KENNZAHLEN_SCHLUESSEL"].split(",")


class Mandant(HttpUser):
    wait_time = between(0.05, 0.2)

    def on_start(self) -> None:
        self.client.headers["X-API-Key"] = random.choice(SCHLUESSEL)

    @task(6)
    def kennzahlen_monat(self) -> None:
        self.client.get(
            f"/v1/kennzahlen?jahr=2025&monat={random.randint(1, 12)}", name="/v1/kennzahlen?monat"
        )

    @task(3)
    def kennzahlen_jahr(self) -> None:
        self.client.get("/v1/kennzahlen?jahr=2025", name="/v1/kennzahlen")

    @task(3)
    def abweichungen(self) -> None:
        self.client.get("/v1/abweichungen?jahr=2025", name="/v1/abweichungen")

    @task(1)
    def hochladen(self) -> None:
        posten = [
            {
                "datum": "2025-01-15",
                "kostenstelle": "Lasttest",
                "art": "sonstiges",
                "betrag": "1.00",
            }
        ] * 50
        self.client.post("/v1/buchungen", json=posten, name="/v1/buchungen")
