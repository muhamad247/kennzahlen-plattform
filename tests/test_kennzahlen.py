from datetime import date
from decimal import Decimal

import pytest

from app.kennzahlen import Summe, abweichungen, ergebnisrechnung, kostenstellen, zeitraum


def s(kostenstelle, art, betrag):
    return Summe(kostenstelle, art, Decimal(str(betrag)))


SUMMEN = [
    s("Werkstatt", "erloes", 1000),
    s("Werkstatt", "material", 300),
    s("Werkstatt", "personal", 250),
    s("Montage", "erloes", 400),
    s("Montage", "fremdleistung", 100),
    s("Verwaltung", "miete", 200),
    s("Verwaltung", "sonstiges", 50.5),
]


def test_deckungsbeitragsrechnung():
    e = ergebnisrechnung(SUMMEN)
    assert e["umsatz"] == 1400
    assert e["variable_kosten"] == 400
    assert e["deckungsbeitrag"] == 1000
    assert e["db_quote"] == pytest.approx(0.7143)
    assert e["fixkosten"] == 500.5
    assert e["betriebsergebnis"] == 499.5
    assert e["umsatzrendite"] == pytest.approx(0.3568)
    assert e["kosten_nach_art"]["sonstiges"] == 50.5


def test_ohne_umsatz_gibt_es_keine_quoten():
    e = ergebnisrechnung([s("Verwaltung", "miete", 200)])
    assert e["db_quote"] is None and e["umsatzrendite"] is None
    assert e["betriebsergebnis"] == -200


def test_kostenstellen_nach_ergebnis_sortiert():
    zeilen = kostenstellen(SUMMEN)
    assert [z["kostenstelle"] for z in zeilen] == ["Werkstatt", "Montage", "Verwaltung"]
    assert [z["betriebsergebnis"] for z in zeilen] == [450, 300, -250.5]
    assert "kosten_nach_art" not in zeilen[0]


def test_abweichungen_bewerten_erloese_und_kosten_richtig():
    ist = [
        s("Werkstatt", "erloes", 1100),
        s("Werkstatt", "material", 350),
        s("Montage", "erloes", 380),
    ]
    plan = [
        s("Werkstatt", "erloes", 1000),
        s("Werkstatt", "material", 300),
        s("Montage", "erloes", 400),
        s("Verwaltung", "miete", 200),
    ]
    zeilen = {(z["kostenstelle"], z["art"]): z for z in abweichungen(ist, plan)}
    assert zeilen[("Werkstatt", "erloes")]["guenstig"] is True  # mehr Umsatz als geplant
    assert zeilen[("Werkstatt", "material")]["guenstig"] is False  # mehr Kosten als geplant
    assert zeilen[("Montage", "erloes")]["guenstig"] is False
    assert zeilen[("Werkstatt", "material")]["abweichung_prozent"] == pytest.approx(0.1667)
    assert zeilen[("Verwaltung", "miete")]["ist"] == 0  # geplant, aber nichts gebucht
    assert zeilen[("Verwaltung", "miete")]["guenstig"] is True


def test_abweichungen_groesste_zuerst_und_ohne_budget_keine_prozent():
    zeilen = abweichungen([s("A", "erloes", 10), s("B", "material", 500)], [s("A", "erloes", 30)])
    assert [z["kostenstelle"] for z in zeilen] == ["B", "A"]
    assert zeilen[0]["abweichung_prozent"] is None


@pytest.mark.parametrize(
    ("jahr", "monat", "von", "bis"),
    [
        (2025, None, date(2025, 1, 1), date(2026, 1, 1)),
        (2025, 2, date(2025, 2, 1), date(2025, 3, 1)),
        (2025, 12, date(2025, 12, 1), date(2026, 1, 1)),
    ],
)
def test_zeitraum(jahr, monat, von, bis):
    assert zeitraum(jahr, monat) == (von, bis)
