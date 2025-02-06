from collections import defaultdict
from decimal import Decimal

import pytest

from app.verwaltung import schluessel_hinzufuegen, schluessel_widerrufen
from scripts.demo_daten import erzeugen

BUCHUNG = {"datum": "2025-03-10", "kostenstelle": "Vertrieb", "art": "erloes", "betrag": "500.00"}


@pytest.fixture
def demo(client, neuer_mandant):
    _, kopf = neuer_mandant("Tischlerei")
    buchungen, budget = erzeugen()
    assert client.post("/v1/buchungen", headers=kopf, json=buchungen).status_code == 201
    assert client.put("/v1/budget", headers=kopf, json=budget).status_code == 200
    return kopf, buchungen, budget


def _summe(posten, **filter_):
    werte = defaultdict(Decimal)
    for p in posten:
        if all(str(p[k]).startswith(str(v)) for k, v in filter_.items()):
            werte[p["art"]] += Decimal(p["betrag"])
    return werte


# --- Anmeldung ---------------------------------------------------------------


def test_ohne_schluessel_401(client):
    antwort = client.get("/v1/mandant")
    assert antwort.status_code == 401
    assert "X-API-Key" in antwort.json()["detail"]


def test_falscher_schluessel_401(client):
    assert client.get("/v1/mandant", headers={"X-API-Key": "kz_falsch"}).status_code == 401


def test_schluessel_tauschen_ohne_ausfall(client, admin_url, neuer_mandant):
    """Zweiten Schlüssel anlegen, Kunde stellt um, alten widerrufen."""
    mandant_id, alt = neuer_mandant()
    neu = {"X-API-Key": schluessel_hinzufuegen(admin_url, mandant_id)}
    assert client.get("/v1/mandant", headers=alt).json()["id"] == mandant_id
    assert client.get("/v1/mandant", headers=neu).json()["id"] == mandant_id
    assert schluessel_widerrufen(admin_url, alt["X-API-Key"])
    assert client.get("/v1/mandant", headers=alt).status_code == 401
    assert client.get("/v1/mandant", headers=neu).status_code == 200
    assert not schluessel_widerrufen(admin_url, alt["X-API-Key"])


# --- Eingaben prüfen ---------------------------------------------------------


@pytest.mark.parametrize(
    "aenderung",
    [
        {"betrag": "-1.00"},
        {"betrag": "1.001"},
        {"art": "provision"},
        {"datum": "2025-02-30"},
        {"kostenstelle": ""},
        {"kostenstelle": "x" * 51},
    ],
)
def test_ungueltige_buchung_422(client, neuer_mandant, aenderung):
    _, kopf = neuer_mandant()
    antwort = client.post("/v1/buchungen", headers=kopf, json=[{**BUCHUNG, **aenderung}])
    assert antwort.status_code == 422


def test_leere_und_zu_grosse_uploads_422(client, neuer_mandant):
    _, kopf = neuer_mandant()
    assert client.post("/v1/buchungen", headers=kopf, json=[]).status_code == 422
    assert client.post("/v1/buchungen", headers=kopf, json=[BUCHUNG] * 10_001).status_code == 422
    assert client.post("/v1/buchungen", headers=kopf, json=[BUCHUNG] * 10_000).status_code == 201


def test_ungueltige_abfrageparameter_422(client, neuer_mandant):
    _, kopf = neuer_mandant()
    assert client.get("/v1/kennzahlen?jahr=2025&monat=13", headers=kopf).status_code == 422
    assert client.get("/v1/kennzahlen", headers=kopf).status_code == 422


# --- Auswertungen ------------------------------------------------------------


def test_kennzahlen_stimmen_mit_den_hochgeladenen_daten(client, demo):
    kopf, buchungen, _ = demo
    erwartet = _summe(buchungen)
    g = client.get("/v1/kennzahlen?jahr=2025", headers=kopf).json()["gesamt"]
    umsatz = erwartet["erloes"]
    variabel = erwartet["material"] + erwartet["fremdleistung"]
    fix = erwartet["personal"] + erwartet["miete"] + erwartet["sonstiges"]
    assert g["umsatz"] == float(umsatz)
    assert g["deckungsbeitrag"] == float(umsatz - variabel)
    assert g["betriebsergebnis"] == float(umsatz - variabel - fix)


def test_monat_filtert_richtig(client, demo):
    kopf, buchungen, _ = demo
    maerz = client.get("/v1/kennzahlen?jahr=2025&monat=3", headers=kopf).json()
    assert maerz["gesamt"]["umsatz"] == float(_summe(buchungen, datum="2025-03")["erloes"])
    assert {k["kostenstelle"] for k in maerz["kostenstellen"]} == {
        "Werkstatt",
        "Montage",
        "Verwaltung",
    }


def test_abweichungen_gegen_budget(client, demo):
    kopf, buchungen, budget = demo
    positionen = client.get("/v1/abweichungen?jahr=2025", headers=kopf).json()["positionen"]
    betraege = [abs(p["abweichung"]) for p in positionen]
    assert betraege == sorted(betraege, reverse=True)
    material = next(p for p in positionen if p["art"] == "material")
    assert material["budget"] == float(_summe(budget)["material"])
    assert material["ist"] == float(_summe(buchungen)["material"])
    assert material["guenstig"] is False  # Material ist in den Demodaten teurer als geplant


def test_budget_mehrfach_senden_aendert_nichts(client, demo):
    kopf, _, budget = demo
    vorher = client.get("/v1/abweichungen?jahr=2025", headers=kopf).json()
    assert client.put("/v1/budget", headers=kopf, json=budget).json() == {"gespeichert": 108}
    assert client.get("/v1/abweichungen?jahr=2025", headers=kopf).json() == vorher


def test_zeitraum_loeschen_und_neu_laden(client, demo):
    kopf, buchungen, _ = demo
    maerz = [b for b in buchungen if b["datum"].startswith("2025-03")]
    assert client.delete("/v1/buchungen?jahr=2025&monat=3", headers=kopf).json() == {
        "geloescht": len(maerz)
    }
    assert (
        client.get("/v1/kennzahlen?jahr=2025&monat=3", headers=kopf).json()["gesamt"]["umsatz"] == 0
    )
    assert (
        client.get("/v1/kennzahlen?jahr=2025&monat=4", headers=kopf).json()["gesamt"]["umsatz"] > 0
    )
    client.post("/v1/buchungen", headers=kopf, json=maerz)
    jahr = client.get("/v1/kennzahlen?jahr=2025", headers=kopf).json()["gesamt"]["umsatz"]
    assert jahr == float(_summe(buchungen)["erloes"])


# --- Betrieb -----------------------------------------------------------------


def test_health_und_ready(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").status_code == 200
    # ohne vorherigen /ready-Aufruf: die Metrik wird beim Abruf selbst geprüft
    assert "datenbank_bereit 1.0" in client.get("/metrics").text


def test_ohne_datenbank_lebt_die_instanz_ist_aber_nicht_bereit(client_fuer):
    client = client_fuer(url="postgresql://kennzahlen_app:x@127.0.0.1:1/nichts?connect_timeout=1")
    assert client.get("/health").status_code == 200
    antwort = client.get("/ready")
    assert antwort.status_code == 503
    assert "datenbank_bereit 0.0" in client.get("/metrics").text


def test_request_id_wird_durchgereicht_oder_erzeugt(client):
    assert (
        client.get("/health", headers={"X-Request-ID": "abc-123"}).headers["X-Request-ID"]
        == "abc-123"
    )
    assert len(client.get("/health").headers["X-Request-ID"]) == 32


def test_openapi_beschreibt_alle_endpunkte(client):
    pfade = client.get("/openapi.json").json()["paths"]
    assert {"/v1/buchungen", "/v1/budget", "/v1/kennzahlen", "/v1/abweichungen"} <= set(pfade)
    assert "/metrics" not in pfade
