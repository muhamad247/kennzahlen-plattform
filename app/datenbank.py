"""Zugriff auf PostgreSQL. Jede Anfrage läuft in einer Transaktion, in der der Mandant
gesetzt ist; die Row-Level Security der Datenbank übernimmt die Trennung."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.kennzahlen import Summe


@dataclass(frozen=True)
class Mandant:
    id: str
    name: str


class Datenbank:
    def __init__(self, url: str, max_verbindungen: int = 10) -> None:
        self.pool = ConnectionPool(
            url,
            min_size=1,
            max_size=max_verbindungen,
            open=False,
            timeout=5,
            kwargs={"autocommit": True, "row_factory": dict_row},
            # tote Verbindungen (z. B. nach Datenbank-Neustart) vor der Ausgabe aussortieren
            check=ConnectionPool.check_connection,
        )

    def oeffnen(self) -> None:
        # nicht auf die erste Verbindung warten: die App soll auch starten, wenn die
        # Datenbank kurz nicht erreichbar ist; /ready meldet das dann
        self.pool.open(wait=False)

    def schliessen(self) -> None:
        self.pool.close()

    def bereit(self) -> bool:
        try:
            with self.pool.connection(timeout=2) as conn:
                conn.execute("SELECT 1")
            return True
        except Exception:  # Pool-Timeout, Verbindungsfehler: in jedem Fall nicht bereit
            return False

    def mandant_zu_schluessel(self, schluessel_hash: str) -> Mandant | None:
        with self.pool.connection() as conn:
            zeile = conn.execute(
                "SELECT id, name FROM mandant_zu_schluessel(%s)", (schluessel_hash,)
            ).fetchone()
        return Mandant(str(zeile["id"]), zeile["name"]) if zeile else None

    @contextmanager
    def fuer_mandant(self, mandant_id: str) -> Iterator[psycopg.Connection]:
        """Verbindung mit gesetztem Mandanten. set_config(..., true) gilt nur bis zum Ende
        der Transaktion, die Verbindung geht also ohne Mandant zurück in den Pool."""
        with self.pool.connection() as conn, conn.transaction():
            conn.execute("SELECT set_config('app.mandant_id', %s, true)", (mandant_id,))
            yield conn

    # Die Abfragen enthalten bewusst keine Bedingung auf mandant_id: die Datenbank filtert.

    def buchungen_speichern(self, mandant_id: str, buchungen: list[dict]) -> int:
        # COPY wäre schneller, PostgreSQL erlaubt COPY FROM aber nicht auf Tabellen mit
        # Row-Level Security. executemany schickt die INSERTs gebündelt (Pipeline-Modus).
        with self.fuer_mandant(mandant_id) as conn, conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO buchungen (datum, kostenstelle, art, betrag)
                VALUES (%(datum)s, %(kostenstelle)s, %(art)s, %(betrag)s)
                """,
                buchungen,
            )
            return len(buchungen)

    def budget_speichern(self, mandant_id: str, positionen: list[dict]) -> int:
        with self.fuer_mandant(mandant_id) as conn, conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO budget (jahr, monat, kostenstelle, art, betrag)
                VALUES (%(jahr)s, %(monat)s, %(kostenstelle)s, %(art)s, %(betrag)s)
                ON CONFLICT (mandant_id, jahr, monat, kostenstelle, art)
                DO UPDATE SET betrag = EXCLUDED.betrag
                """,
                positionen,
            )
            return len(positionen)

    def ist_summen(self, mandant_id: str, von, bis) -> list[Summe]:
        with self.fuer_mandant(mandant_id) as conn:
            zeilen = conn.execute(
                """
                SELECT kostenstelle, art::text AS art, sum(betrag) AS betrag
                FROM buchungen WHERE datum >= %s AND datum < %s
                GROUP BY kostenstelle, art
                """,
                (von, bis),
            ).fetchall()
        return [Summe(**z) for z in zeilen]

    def budget_summen(self, mandant_id: str, jahr: int, monat: int | None) -> list[Summe]:
        with self.fuer_mandant(mandant_id) as conn:
            zeilen = conn.execute(
                """
                SELECT kostenstelle, art::text AS art, sum(betrag) AS betrag
                FROM budget WHERE jahr = %s AND (%s::int IS NULL OR monat = %s)
                GROUP BY kostenstelle, art
                """,
                (jahr, monat, monat),
            ).fetchall()
        return [Summe(**z) for z in zeilen]

    def buchungen_loeschen(self, mandant_id: str, von, bis) -> int:
        with self.fuer_mandant(mandant_id) as conn:
            cur = conn.execute("DELETE FROM buchungen WHERE datum >= %s AND datum < %s", (von, bis))
            return cur.rowcount
