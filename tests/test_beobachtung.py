import json
import logging

from prometheus_client.parser import text_string_to_metric_families

from app.beobachtung import JsonFormat


def _werte(client, name):
    """{labels als frozenset: wert} für eine Metrik aus /metrics."""
    for familie in text_string_to_metric_families(client.get("/metrics").text):
        for probe in familie.samples:
            if probe.name == name:
                yield probe.labels, probe.value


def test_anfragen_werden_je_mandant_und_routenvorlage_gezaehlt(client, neuer_mandant):
    _, kopf = neuer_mandant("Zaehl")
    name = client.get("/v1/mandant", headers=kopf).json()["name"]
    for monat in (1, 2, 3):
        client.get(f"/v1/kennzahlen?jahr=2025&monat={monat}", headers=kopf)
    werte = {
        (m["mandant"], m["route"], m["status"]): v for m, v in _werte(client, "http_anfragen_total")
    }
    # drei verschiedene URLs, aber eine Zeitreihe: sonst wüchse die Zahl der Reihen unbegrenzt
    assert werte[(name, "/v1/kennzahlen", "200")] == 3
    assert werte[(name, "/v1/mandant", "200")] == 1


def test_unbekannte_pfade_und_fehlende_anmeldung(client):
    client.get("/gibt/es/nicht")
    client.get("/v1/mandant")
    werte = {
        (m["mandant"], m["route"], m["status"]): v for m, v in _werte(client, "http_anfragen_total")
    }
    assert werte[("-", "unbekannt", "404")] == 1
    assert werte[("-", "/v1/mandant", "401")] == 1


def test_metrics_zaehlt_sich_nicht_selbst(client):
    client.get("/metrics")
    routen = {m["route"] for m, _ in _werte(client, "http_anfragen_total")}
    assert "/metrics" not in routen


def test_antwortzeiten_und_importierte_buchungen(client, neuer_mandant):
    _, kopf = neuer_mandant("Import")
    buchung = {"datum": "2025-01-02", "kostenstelle": "A", "art": "erloes", "betrag": "1.00"}
    client.post("/v1/buchungen", headers=kopf, json=[buchung] * 5)
    importiert = [
        v for m, v in _werte(client, "buchungen_importiert_total") if "Import" in m["mandant"]
    ]
    assert importiert == [5]
    anzahl = [
        v
        for m, v in _werte(client, "http_antwortzeit_sekunden_count")
        if m["route"] == "/v1/buchungen" and "Import" in m["mandant"]
    ]
    assert anzahl == [1]


def test_log_ist_eine_json_zeile_mit_kontext():
    eintrag = logging.LogRecord("kennzahlen", logging.INFO, __file__, 1, "Anfrage", None, None)
    eintrag.mandant, eintrag.status, eintrag.request_id = "Muster GmbH", 200, "abc"
    daten = json.loads(JsonFormat().format(eintrag))
    assert daten["nachricht"] == "Anfrage"
    assert daten["mandant"] == "Muster GmbH"
    assert daten["status"] == 200
    assert daten["zeit"].endswith("+00:00")
    assert "dauer_ms" not in daten
