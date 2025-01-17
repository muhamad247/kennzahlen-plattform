"""Einrichten der Datenbank und Verwalten von Mandanten. Läuft mit Admin-Rechten,
nie im Anfragepfad der API."""

from __future__ import annotations

import hashlib
import secrets
from pathlib import Path

import psycopg
from psycopg import sql

SCHEMA = Path(__file__).resolve().parent.parent / "db" / "schema.sql"
APP_ROLLE = "kennzahlen_app"
PRAEFIX = "kz_"


def hash_schluessel(schluessel: str) -> str:
    """SHA-256 genügt hier: Die Schlüssel sind lange Zufallswerte, keine Passwörter."""
    return hashlib.sha256(schluessel.encode()).hexdigest()


def neuer_schluessel() -> str:
    return PRAEFIX + secrets.token_urlsafe(32)


def einrichten(admin_url: str, app_passwort: str) -> None:
    """Legt die Rolle der Anwendung an (oder setzt ihr Passwort neu) und spielt das Schema ein."""
    with psycopg.connect(admin_url, autocommit=True) as conn:
        vorhanden = conn.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", (APP_ROLLE,)
        ).fetchone()
        befehl = (
            "ALTER ROLE {} WITH LOGIN PASSWORD {}"
            if vorhanden
            else ("CREATE ROLE {} WITH LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD {}")
        )
        conn.execute(sql.SQL(befehl).format(sql.Identifier(APP_ROLLE), sql.Literal(app_passwort)))
        with conn.transaction():
            conn.execute(SCHEMA.read_text(encoding="utf-8"))


def mandant_anlegen(admin_url: str, name: str) -> tuple[str, str]:
    """Neuer Mandant mit erstem API-Schlüssel. Der Schlüssel wird nur hier im Klartext
    zurückgegeben und danach nirgends gespeichert."""
    schluessel = neuer_schluessel()
    with psycopg.connect(admin_url) as conn:
        mandant_id = conn.execute(
            "INSERT INTO mandanten (name) VALUES (%s) RETURNING id", (name,)
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO api_schluessel (hash, mandant_id) VALUES (%s, %s)",
            (hash_schluessel(schluessel), mandant_id),
        )
    return str(mandant_id), schluessel


def schluessel_hinzufuegen(admin_url: str, mandant_id: str) -> str:
    """Zweiter Schlüssel für einen Mandanten, z. B. um einen alten ohne Ausfall abzulösen."""
    schluessel = neuer_schluessel()
    with psycopg.connect(admin_url) as conn:
        conn.execute(
            "INSERT INTO api_schluessel (hash, mandant_id) VALUES (%s, %s)",
            (hash_schluessel(schluessel), mandant_id),
        )
    return schluessel


def schluessel_widerrufen(admin_url: str, schluessel: str) -> bool:
    with psycopg.connect(admin_url) as conn:
        cur = conn.execute(
            "UPDATE api_schluessel SET widerrufen = now() WHERE hash = %s AND widerrufen IS NULL",
            (hash_schluessel(schluessel),),
        )
        return cur.rowcount == 1
