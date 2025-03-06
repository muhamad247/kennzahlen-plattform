"""Metriken für Prometheus und Logs als JSON, beides mit Mandant und Route."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

OHNE_MANDANT = "-"


class Metriken:
    """Eigene Registry je App, damit Tests mehrere Apps nebeneinander starten können."""

    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.anfragen = Counter(
            "http_anfragen",
            "HTTP-Anfragen nach Mandant, Route und Statuscode",
            ["mandant", "route", "status"],
            registry=self.registry,
        )
        self.antwortzeit = Histogram(
            "http_antwortzeit_sekunden",
            "Antwortzeit nach Mandant und Route",
            ["mandant", "route"],
            buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
            registry=self.registry,
        )
        self.buchungen = Counter(
            "buchungen_importiert",
            "Importierte Buchungen nach Mandant",
            ["mandant"],
            registry=self.registry,
        )
        self.abgelehnt = Counter(
            "ratelimit_abgelehnt",
            "Wegen Anfragebegrenzung abgelehnte Anfragen",
            ["mandant"],
            registry=self.registry,
        )
        self.db_bereit = Gauge(
            "datenbank_bereit",
            "1, wenn die letzte Bereitschaftsprüfung die Datenbank erreicht hat",
            registry=self.registry,
        )


class JsonFormat(logging.Formatter):
    """Eine JSON-Zeile je Ereignis; Zusatzfelder kommen über extra={...}."""

    FELDER = ("request_id", "mandant", "methode", "pfad", "route", "status", "dauer_ms")

    def format(self, record: logging.LogRecord) -> str:
        eintrag = {
            "zeit": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "nachricht": record.getMessage(),
        }
        for feld in self.FELDER:
            if hasattr(record, feld):
                eintrag[feld] = getattr(record, feld)
        if record.exc_info:
            eintrag["fehler"] = self.formatException(record.exc_info)
        return json.dumps(eintrag, ensure_ascii=False)


def logging_einrichten(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormat())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # Uvicorns eigene Zugriffslogs doppeln unsere Anfragelogs
    logging.getLogger("uvicorn.access").disabled = True
