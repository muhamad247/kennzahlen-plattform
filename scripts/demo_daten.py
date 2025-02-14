"""Buchungen und Budget einer erfundenen Tischlerei für ein Jahr, und Upload über die API.

python -m scripts.demo_daten --url http://localhost:8080 --schluessel kz_...
"""

import argparse
import json
import random
import urllib.request
from datetime import date

# Monatliches Budget je Kostenstelle und Kontoart in Euro
BUDGET = {
    ("Werkstatt", "erloes"): 62_000,
    ("Werkstatt", "material"): 21_000,
    ("Werkstatt", "personal"): 24_000,
    ("Montage", "erloes"): 28_000,
    ("Montage", "fremdleistung"): 6_000,
    ("Montage", "personal"): 13_000,
    ("Verwaltung", "personal"): 9_500,
    ("Verwaltung", "miete"): 4_200,
    ("Verwaltung", "sonstiges"): 2_800,
}
# Saison: im Frühjahr und Herbst mehr Aufträge, im August Betriebsurlaub
SAISON = [0.85, 0.9, 1.05, 1.1, 1.1, 1.0, 0.95, 0.6, 1.05, 1.15, 1.1, 1.0]


def erzeugen(jahr: int = 2025, seed: int = 3) -> tuple[list[dict], list[dict]]:
    rng = random.Random(seed)
    buchungen, budget = [], []
    for monat in range(1, 13):
        for (kostenstelle, art), betrag in BUDGET.items():
            budget.append(
                {
                    "jahr": jahr,
                    "monat": monat,
                    "kostenstelle": kostenstelle,
                    "art": art,
                    "betrag": f"{betrag:.2f}",
                }
            )
            # Ist weicht vom Plan ab: Mengen schwanken mit der Saison, Material wird teurer
            faktor = SAISON[monat - 1] if art in ("erloes", "material", "fremdleistung") else 1.0
            if art == "material":
                faktor *= 1.06
            ist = betrag * faktor * rng.uniform(0.93, 1.07)
            # in einzelne Belege aufteilen
            belege = rng.randint(3, 12)
            anteile = [rng.random() for _ in range(belege)]
            for a in anteile:
                buchungen.append(
                    {
                        "datum": date(jahr, monat, rng.randint(1, 28)).isoformat(),
                        "kostenstelle": kostenstelle,
                        "art": art,
                        "betrag": f"{ist * a / sum(anteile):.2f}",
                    }
                )
    return buchungen, budget


def senden(url: str, schluessel: str, methode: str, pfad: str, daten: list[dict]) -> dict:
    anfrage = urllib.request.Request(
        url.rstrip("/") + pfad,
        data=json.dumps(daten).encode(),
        method=methode,
        headers={"Content-Type": "application/json", "X-API-Key": schluessel},
    )
    with urllib.request.urlopen(anfrage, timeout=30) as antwort:
        return json.load(antwort)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:8080")
    parser.add_argument("--schluessel", required=True)
    parser.add_argument("--jahr", type=int, default=2025)
    args = parser.parse_args()
    buchungen, budget = erzeugen(args.jahr)
    print(senden(args.url, args.schluessel, "POST", "/v1/buchungen", buchungen))
    print(senden(args.url, args.schluessel, "PUT", "/v1/budget", budget))


if __name__ == "__main__":
    main()
