"""Der wichtigste Teil: Kein Mandant sieht oder verändert Daten eines anderen.

Die Tests greifen teils direkt mit der Rolle der Anwendung auf die Datenbank zu. Sie zeigen,
dass die Trennung auch dann hält, wenn in der API eine Abfrage ohne Mandantenfilter landet.
"""

import psycopg
import pytest

from app.datenbank import Datenbank

BUCHUNG = {"datum": "2025-03-10", "kostenstelle": "Vertrieb", "art": "erloes", "betrag": "500.00"}


def _als_app(app_url, mandant_id=None):
    conn = psycopg.connect(app_url)
    if mandant_id:
        conn.execute("SELECT set_config('app.mandant_id', %s, true)", (mandant_id,))
    return conn


@pytest.fixture
def zwei_mandanten(client, neuer_mandant):
    a_id, a = neuer_mandant("A")
    b_id, b = neuer_mandant("B")
    client.post("/v1/buchungen", headers=a, json=[BUCHUNG])
    client.post("/v1/buchungen", headers=b, json=[{**BUCHUNG, "betrag": "7.00"}] * 3)
    return a_id, a, b_id, b


def test_mandant_sieht_ueber_die_api_nur_eigene_daten(client, zwei_mandanten):
    _, a, _, b = zwei_mandanten
    assert client.get("/v1/kennzahlen?jahr=2025", headers=a).json()["gesamt"]["umsatz"] == 500
    assert client.get("/v1/kennzahlen?jahr=2025", headers=b).json()["gesamt"]["umsatz"] == 21


def test_ohne_mandant_sieht_die_anwendung_nichts(app_url, admin_url, zwei_mandanten):
    with psycopg.connect(admin_url) as admin:
        assert admin.execute("SELECT count(*) FROM buchungen").fetchone()[0] >= 4
    with _als_app(app_url) as conn:
        assert conn.execute("SELECT count(*) FROM buchungen").fetchone()[0] == 0


def test_abfrage_ohne_mandantenfilter_liefert_nur_eigene_zeilen(app_url, zwei_mandanten):
    a_id, _, b_id, _ = zwei_mandanten
    with _als_app(app_url, b_id) as conn:
        zeilen = conn.execute("SELECT DISTINCT mandant_id::text FROM buchungen").fetchall()
    assert zeilen == [(b_id,)]


def test_schreiben_mit_fremder_mandant_id_wird_abgelehnt(app_url, zwei_mandanten):
    a_id, _, b_id, _ = zwei_mandanten
    with _als_app(app_url, a_id) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(
            "INSERT INTO buchungen (mandant_id, datum, kostenstelle, art, betrag) "
            "VALUES (%s, '2025-01-01', 'X', 'erloes', 1)",
            (b_id,),
        )


def test_update_und_delete_erreichen_fremde_zeilen_nicht(client, app_url, zwei_mandanten):
    a_id, a, _, b = zwei_mandanten
    with _als_app(app_url, a_id) as conn:
        conn.execute("UPDATE buchungen SET betrag = 0")
        conn.execute("DELETE FROM buchungen")
    assert client.get("/v1/kennzahlen?jahr=2025", headers=a).json()["gesamt"]["umsatz"] == 0
    assert client.get("/v1/kennzahlen?jahr=2025", headers=b).json()["gesamt"]["umsatz"] == 21


def test_eigene_zeilen_koennen_nicht_einem_anderen_mandanten_zugeschoben_werden(
    app_url, zwei_mandanten
):
    a_id, _, b_id, _ = zwei_mandanten
    with _als_app(app_url, a_id) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("UPDATE buchungen SET mandant_id = %s", (b_id,))


@pytest.mark.parametrize("tabelle", ["api_schluessel", "mandanten"])
def test_anwendung_kann_schluessel_und_mandanten_nicht_lesen(app_url, tabelle):
    with _als_app(app_url) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute(f"SELECT * FROM {tabelle}")


def test_anwendung_kann_die_trennung_nicht_abschalten(app_url, zwei_mandanten):
    with _als_app(app_url) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("ALTER TABLE buchungen DISABLE ROW LEVEL SECURITY")
    with _als_app(app_url) as conn, pytest.raises(psycopg.errors.InsufficientPrivilege):
        conn.execute("SET row_security = off")
        conn.execute("SELECT count(*) FROM buchungen")


def test_mandant_gilt_nur_bis_zum_ende_der_transaktion(app_url, zwei_mandanten):
    """Nur eine Verbindung im Pool: Nach der Transaktion von A ist kein Mandant mehr gesetzt."""
    a_id, _, _, _ = zwei_mandanten
    db = Datenbank(app_url, max_verbindungen=1)
    db.oeffnen()
    try:
        with db.fuer_mandant(a_id) as conn:
            assert conn.execute("SELECT count(*) FROM buchungen").fetchone()["count"] == 1
        with db.pool.connection() as conn:
            assert conn.execute("SELECT aktueller_mandant() AS m").fetchone()["m"] is None
            assert conn.execute("SELECT count(*) FROM buchungen").fetchone()["count"] == 0
    finally:
        db.schliessen()


def test_schluessel_liegt_nur_als_hash_in_der_datenbank(admin_url, neuer_mandant):
    _, kopf = neuer_mandant()
    schluessel = kopf["X-API-Key"]
    with psycopg.connect(admin_url) as conn:
        inhalt = conn.execute("SELECT string_agg(hash, ',') FROM api_schluessel").fetchone()[0]
    assert schluessel not in inhalt
    assert schluessel.removeprefix("kz_") not in inhalt
