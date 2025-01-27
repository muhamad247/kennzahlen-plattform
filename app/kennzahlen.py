"""Controlling-Kennzahlen aus summierten Buchungen. Reine Funktionen ohne Datenbank,
damit sie sich exakt testen lassen."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

ERLOES = "erloes"
VARIABEL = ("material", "fremdleistung")
FIX = ("personal", "miete", "sonstiges")
ARTEN = (ERLOES, *VARIABEL, *FIX)
NULL = Decimal("0")


@dataclass(frozen=True)
class Summe:
    """Summe der Buchungen einer Kostenstelle und Kontoart im Zeitraum."""

    kostenstelle: str
    art: str
    betrag: Decimal


def zeitraum(jahr: int, monat: int | None = None) -> tuple[date, date]:
    """Beginn (inklusiv) und Ende (exklusiv) eines Monats oder ganzen Jahres."""
    if monat is None:
        return date(jahr, 1, 1), date(jahr + 1, 1, 1)
    ende = date(jahr + 1, 1, 1) if monat == 12 else date(jahr, monat + 1, 1)
    return date(jahr, monat, 1), ende


def _quote(zaehler: Decimal, nenner: Decimal) -> float | None:
    return None if nenner == 0 else round(float(zaehler / nenner), 4)


def ergebnisrechnung(summen: list[Summe]) -> dict:
    """Deckungsbeitragsrechnung: Umsatz, variable Kosten, DB, Fixkosten, Betriebsergebnis."""
    nach_art: dict[str, Decimal] = defaultdict(lambda: NULL)
    for s in summen:
        nach_art[s.art] += s.betrag
    umsatz = nach_art[ERLOES]
    variabel = sum((nach_art[a] for a in VARIABEL), NULL)
    fix = sum((nach_art[a] for a in FIX), NULL)
    deckungsbeitrag = umsatz - variabel
    ergebnis = deckungsbeitrag - fix
    return {
        "umsatz": float(umsatz),
        "variable_kosten": float(variabel),
        "deckungsbeitrag": float(deckungsbeitrag),
        "db_quote": _quote(deckungsbeitrag, umsatz),
        "fixkosten": float(fix),
        "betriebsergebnis": float(ergebnis),
        "umsatzrendite": _quote(ergebnis, umsatz),
        "kosten_nach_art": {a: float(nach_art[a]) for a in (*VARIABEL, *FIX)},
    }


def kostenstellen(summen: list[Summe]) -> list[dict]:
    """Ergebnisrechnung je Kostenstelle, nach Betriebsergebnis absteigend."""
    gruppen: dict[str, list[Summe]] = defaultdict(list)
    for s in summen:
        gruppen[s.kostenstelle].append(s)
    zeilen = [{"kostenstelle": k, **ergebnisrechnung(g)} for k, g in gruppen.items()]
    for z in zeilen:
        del z["kosten_nach_art"]
    return sorted(zeilen, key=lambda z: (-z["betriebsergebnis"], z["kostenstelle"]))


def abweichungen(ist: list[Summe], budget: list[Summe]) -> list[dict]:
    """Ist gegen Budget je Kostenstelle und Kontoart, größte Abweichung zuerst.

    Mehr Erlös als geplant ist günstig, mehr Kosten als geplant ungünstig."""
    werte: dict[tuple[str, str], list[Decimal]] = defaultdict(lambda: [NULL, NULL])
    for s in ist:
        werte[(s.kostenstelle, s.art)][0] += s.betrag
    for s in budget:
        werte[(s.kostenstelle, s.art)][1] += s.betrag
    zeilen = []
    for (kostenstelle, art), (i, b) in werte.items():
        abw = i - b
        zeilen.append(
            {
                "kostenstelle": kostenstelle,
                "art": art,
                "ist": float(i),
                "budget": float(b),
                "abweichung": float(abw),
                "abweichung_prozent": _quote(abw, b),
                "guenstig": abw >= 0 if art == ERLOES else abw <= 0,
            }
        )
    return sorted(zeilen, key=lambda z: (-abs(z["abweichung"]), z["kostenstelle"], z["art"]))
