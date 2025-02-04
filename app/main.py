"""HTTP-API der Kennzahlen-Plattform."""

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, Field

from app import kennzahlen
from app.beobachtung import OHNE_MANDANT, Metriken, logging_einrichten
from app.datenbank import Datenbank, Mandant
from app.ratelimit import Ratelimit
from app.verwaltung import hash_schluessel

log = logging.getLogger("kennzahlen")

Art = Literal["erloes", "material", "fremdleistung", "personal", "miete", "sonstiges"]
Kostenstelle = Annotated[str, Field(min_length=1, max_length=50)]
Betrag = Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
MAX_POSTEN = int(os.environ.get("MAX_POSTEN_PRO_ANFRAGE", "10000"))


class Buchung(BaseModel):
    datum: date
    kostenstelle: Kostenstelle
    art: Art
    betrag: Betrag


class Budgetposition(BaseModel):
    jahr: int = Field(ge=2000, le=2100)
    monat: int = Field(ge=1, le=12)
    kostenstelle: Kostenstelle
    art: Art
    betrag: Betrag


Jahr = Annotated[int, Query(ge=2000, le=2100)]
Monat = Annotated[int | None, Query(ge=1, le=12)]


def erstelle_app(datenbank_url: str | None = None, ratelimit: Ratelimit | None = None) -> FastAPI:
    url = datenbank_url or os.environ["DATABASE_URL"]
    db = Datenbank(url, max_verbindungen=int(os.environ.get("DB_MAX_VERBINDUNGEN", "10")))
    limit = ratelimit or Ratelimit(
        pro_minute=float(os.environ.get("RATELIMIT_PRO_MINUTE", "600")),
        burst=int(os.environ.get("RATELIMIT_BURST", "100")),
    )
    metriken = Metriken()

    @asynccontextmanager
    async def lebenszyklus(app: FastAPI):
        db.oeffnen()
        yield
        db.schliessen()

    app = FastAPI(
        title="Kennzahlen-Plattform",
        version="1.0.0",
        description="Controlling-Kennzahlen für mehrere Mandanten, sauber getrennt.",
        lifespan=lebenszyklus,
    )
    app.state.db = db
    app.state.metriken = metriken

    @app.middleware("http")
    async def messen(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.mandant = OHNE_MANDANT
        start = time.perf_counter()
        try:
            antwort = await call_next(request)
            status = antwort.status_code
        except Exception:
            status = 500
            log.exception("Unbehandelter Fehler", extra={"request_id": request_id})
            antwort = JSONResponse({"detail": "Interner Fehler"}, status_code=500)
        dauer = time.perf_counter() - start
        # Routenvorlage statt echtem Pfad, sonst wächst die Zahl der Zeitreihen unbegrenzt
        route = getattr(request.scope.get("route"), "path", "unbekannt")
        mandant = request.state.mandant
        if route != "/metrics":
            metriken.anfragen.labels(mandant, route, str(status)).inc()
            metriken.antwortzeit.labels(mandant, route).observe(dauer)
            log.info(
                "Anfrage",
                extra={
                    "request_id": request_id,
                    "mandant": mandant,
                    "methode": request.method,
                    "pfad": request.url.path,
                    "route": route,
                    "status": status,
                    "dauer_ms": round(dauer * 1000, 1),
                },
            )
        antwort.headers["X-Request-ID"] = request_id
        return antwort

    def aktueller_mandant(
        request: Request, x_api_key: Annotated[str | None, Header()] = None
    ) -> Mandant:
        if not x_api_key:
            raise HTTPException(401, "API-Schlüssel fehlt (Header X-API-Key)")
        mandant = db.mandant_zu_schluessel(hash_schluessel(x_api_key))
        if mandant is None:
            raise HTTPException(401, "Unbekannter oder widerrufener API-Schlüssel")
        request.state.mandant = mandant.name
        erlaubt, warten = limit.erlauben(mandant.id)
        if not erlaubt:
            metriken.abgelehnt.labels(mandant.name).inc()
            raise HTTPException(429, "Zu viele Anfragen", headers={"Retry-After": str(warten)})
        return mandant

    MandantDep = Annotated[Mandant, Depends(aktueller_mandant)]

    @app.get("/health", tags=["Betrieb"])
    def health() -> dict:
        """Lebt der Prozess? Prüft bewusst nicht die Datenbank, sonst würden bei einem
        Datenbankausfall alle Instanzen neu gestartet."""
        return {"status": "ok"}

    @app.get("/ready", tags=["Betrieb"])
    def ready(response: Response) -> dict:
        """Kann die Instanz Anfragen bedienen? Der Load Balancer schickt sonst nichts hin."""
        ok = db.bereit()
        if not ok:
            response.status_code = 503
        return {"status": "bereit" if ok else "datenbank nicht erreichbar"}

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        # bei jeder Abfrage durch Prometheus frisch prüfen, nicht nur wenn /ready aufgerufen wurde
        metriken.db_bereit.set(1 if db.bereit() else 0)
        return Response(generate_latest(metriken.registry), media_type=CONTENT_TYPE_LATEST)

    @app.get("/v1/mandant", tags=["Mandant"])
    def mandant(m: MandantDep) -> dict:
        return {"id": m.id, "name": m.name}

    @app.post("/v1/buchungen", status_code=201, tags=["Daten"])
    def buchungen_hochladen(
        buchungen: Annotated[list[Buchung], Field(min_length=1, max_length=MAX_POSTEN)],
        m: MandantDep,
    ) -> dict:
        n = db.buchungen_speichern(m.id, [b.model_dump() for b in buchungen])
        metriken.buchungen.labels(m.name).inc(n)
        return {"gespeichert": n}

    @app.delete("/v1/buchungen", tags=["Daten"])
    def buchungen_loeschen(m: MandantDep, jahr: Jahr, monat: Monat = None) -> dict:
        """Zum Neuladen eines Zeitraums, z. B. nach Korrekturen in der Buchhaltung."""
        von, bis = kennzahlen.zeitraum(jahr, monat)
        return {"geloescht": db.buchungen_loeschen(m.id, von, bis)}

    @app.put("/v1/budget", tags=["Daten"])
    def budget_speichern(
        positionen: Annotated[list[Budgetposition], Field(min_length=1, max_length=MAX_POSTEN)],
        m: MandantDep,
    ) -> dict:
        """Legt Budgetpositionen an oder überschreibt sie; mehrfaches Senden ändert nichts."""
        return {"gespeichert": db.budget_speichern(m.id, [p.model_dump() for p in positionen])}

    @app.get("/v1/kennzahlen", tags=["Auswertung"])
    def ergebnis(m: MandantDep, jahr: Jahr, monat: Monat = None) -> dict:
        von, bis = kennzahlen.zeitraum(jahr, monat)
        summen = db.ist_summen(m.id, von, bis)
        return {
            "jahr": jahr,
            "monat": monat,
            "gesamt": kennzahlen.ergebnisrechnung(summen),
            "kostenstellen": kennzahlen.kostenstellen(summen),
        }

    @app.get("/v1/abweichungen", tags=["Auswertung"])
    def abweichungen(m: MandantDep, jahr: Jahr, monat: Monat = None) -> dict:
        von, bis = kennzahlen.zeitraum(jahr, monat)
        return {
            "jahr": jahr,
            "monat": monat,
            "positionen": kennzahlen.abweichungen(
                db.ist_summen(m.id, von, bis), db.budget_summen(m.id, jahr, monat)
            ),
        }

    return app


def app_aus_umgebung() -> FastAPI:
    """Einstieg für uvicorn: `uvicorn app.main:app_aus_umgebung --factory`."""
    logging_einrichten(os.environ.get("LOG_LEVEL", "INFO"))
    return erstelle_app()
