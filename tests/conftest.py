"""Tests laufen gegen ein echtes PostgreSQL, weil die Mandantentrennung in der Datenbank liegt.

TEST_ADMIN_URL zeigt auf einen Server, auf dem eine Testdatenbank angelegt werden darf.
"""

import os
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from app.main import erstelle_app
from app.verwaltung import APP_ROLLE, einrichten, mandant_anlegen

SERVER_URL = os.environ.get("TEST_ADMIN_URL", "postgresql://postgres@127.0.0.1:54329/postgres")
TEST_DB = "kennzahlen_test"
APP_PASSWORT = "test-passwort"


def _url(**aenderungen) -> str:
    return make_conninfo(**{**conninfo_to_dict(SERVER_URL), **aenderungen})


@pytest.fixture(scope="session")
def admin_url() -> str:
    with psycopg.connect(SERVER_URL, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {TEST_DB} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {TEST_DB}")
    url = _url(dbname=TEST_DB)
    einrichten(url, APP_PASSWORT)
    return url


@pytest.fixture(scope="session")
def app_url(admin_url) -> str:
    return _url(dbname=TEST_DB, user=APP_ROLLE, password=APP_PASSWORT)


@pytest.fixture
def neuer_mandant(admin_url):
    """Jeder Test bekommt eigene Mandanten; so stören sich Tests nicht gegenseitig."""

    def anlegen(name: str = "Mandant") -> tuple[str, dict]:
        mandant_id, schluessel = mandant_anlegen(admin_url, f"{name} {uuid.uuid4().hex[:8]}")
        return mandant_id, {"X-API-Key": schluessel}

    return anlegen


@pytest.fixture
def client_fuer(app_url):
    clients = []

    def starten(**kwargs) -> TestClient:
        client = TestClient(erstelle_app(kwargs.pop("url", app_url), **kwargs))
        client.__enter__()
        clients.append(client)
        return client

    yield starten
    for client in clients:
        client.__exit__(None, None, None)


@pytest.fixture
def client(client_fuer) -> TestClient:
    return client_fuer()
