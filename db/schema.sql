-- Schema der Kennzahlen-Plattform. Wird als Datenbank-Eigentümer ausgeführt
-- (scripts/einrichten.py); die Anwendung selbst verbindet sich als kennzahlen_app.
--
-- Mandantentrennung: Alle Tabellen mit Kundendaten haben Row-Level Security.
-- Die Anwendung setzt pro Transaktion app.mandant_id; die Datenbank zeigt und
-- akzeptiert dann nur Zeilen dieses Mandanten. Fehlt die Einstellung, sieht man nichts.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS mandanten (
    id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name     text NOT NULL UNIQUE,
    angelegt timestamptz NOT NULL DEFAULT now()
);

-- Nur der SHA-256-Hash des Schlüssels wird gespeichert, nie der Schlüssel selbst.
CREATE TABLE IF NOT EXISTS api_schluessel (
    hash       text PRIMARY KEY CHECK (hash ~ '^[0-9a-f]{64}$'),
    mandant_id uuid NOT NULL REFERENCES mandanten (id) ON DELETE CASCADE,
    angelegt   timestamptz NOT NULL DEFAULT now(),
    widerrufen timestamptz
);

DO $$ BEGIN
    CREATE TYPE kontoart AS ENUM
        ('erloes', 'material', 'fremdleistung', 'personal', 'miete', 'sonstiges');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Mandant der laufenden Transaktion; NULL, wenn keiner gesetzt ist.
-- NULLIF, weil eine einmal benutzte, dann zurückgesetzte Einstellung '' statt NULL liefert.
CREATE OR REPLACE FUNCTION aktueller_mandant() RETURNS uuid
    LANGUAGE sql STABLE
    AS $$ SELECT NULLIF(current_setting('app.mandant_id', true), '')::uuid $$;

CREATE TABLE IF NOT EXISTS buchungen (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mandant_id   uuid NOT NULL DEFAULT aktueller_mandant() REFERENCES mandanten (id),
    datum        date NOT NULL,
    kostenstelle text NOT NULL CHECK (length(kostenstelle) BETWEEN 1 AND 50),
    art          kontoart NOT NULL,
    betrag       numeric(14, 2) NOT NULL CHECK (betrag >= 0)
);
CREATE INDEX IF NOT EXISTS buchungen_mandant_datum ON buchungen (mandant_id, datum);

CREATE TABLE IF NOT EXISTS budget (
    mandant_id   uuid NOT NULL DEFAULT aktueller_mandant() REFERENCES mandanten (id),
    jahr         integer NOT NULL CHECK (jahr BETWEEN 2000 AND 2100),
    monat        integer NOT NULL CHECK (monat BETWEEN 1 AND 12),
    kostenstelle text NOT NULL CHECK (length(kostenstelle) BETWEEN 1 AND 50),
    art          kontoart NOT NULL,
    betrag       numeric(14, 2) NOT NULL CHECK (betrag >= 0),
    PRIMARY KEY (mandant_id, jahr, monat, kostenstelle, art)
);

ALTER TABLE buchungen ENABLE ROW LEVEL SECURITY;
ALTER TABLE buchungen FORCE ROW LEVEL SECURITY;
ALTER TABLE budget ENABLE ROW LEVEL SECURITY;
ALTER TABLE budget FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS mandantentrennung ON buchungen;
CREATE POLICY mandantentrennung ON buchungen
    USING (mandant_id = aktueller_mandant())
    WITH CHECK (mandant_id = aktueller_mandant());

DROP POLICY IF EXISTS mandantentrennung ON budget;
CREATE POLICY mandantentrennung ON budget
    USING (mandant_id = aktueller_mandant())
    WITH CHECK (mandant_id = aktueller_mandant());

-- Die Anwendung darf die Schlüsseltabelle nicht lesen. Sie fragt nur über diese
-- Funktion nach, zu welchem Mandanten ein Hash gehört.
CREATE OR REPLACE FUNCTION mandant_zu_schluessel(schluessel_hash text)
    RETURNS TABLE (id uuid, name text)
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path = public, pg_temp
    AS $$
        SELECT m.id, m.name
        FROM api_schluessel s JOIN mandanten m ON m.id = s.mandant_id
        WHERE s.hash = schluessel_hash AND s.widerrufen IS NULL
    $$;

REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC;
REVOKE ALL ON FUNCTION mandant_zu_schluessel(text) FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO kennzahlen_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON buchungen, budget TO kennzahlen_app;
GRANT EXECUTE ON FUNCTION mandant_zu_schluessel(text), aktueller_mandant() TO kennzahlen_app;
