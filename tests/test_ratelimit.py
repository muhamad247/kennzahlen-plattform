from app.ratelimit import Ratelimit


class Uhr:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def test_burst_dann_gesperrt_dann_wieder_frei():
    uhr = Uhr()
    limit = Ratelimit(pro_minute=60, burst=3, uhr=uhr)  # 1 Anfrage pro Sekunde
    assert [limit.erlauben("a")[0] for _ in range(4)] == [True, True, True, False]
    assert limit.erlauben("a") == (False, 1)
    uhr.t = 1.0
    assert limit.erlauben("a")[0] is True
    assert limit.erlauben("a")[0] is False


def test_wartezeit_wird_aufgerundet():
    uhr = Uhr()
    limit = Ratelimit(pro_minute=6, burst=1, uhr=uhr)  # alle 10 Sekunden ein Token
    assert limit.erlauben("a")[0]
    uhr.t = 2.5
    assert limit.erlauben("a") == (False, 8)


def test_mandanten_haben_getrennte_kontingente():
    limit = Ratelimit(pro_minute=60, burst=1, uhr=Uhr())
    assert limit.erlauben("a")[0] and not limit.erlauben("a")[0]
    assert limit.erlauben("b")[0]


def test_nie_mehr_als_burst_angespart():
    uhr = Uhr()
    limit = Ratelimit(pro_minute=60, burst=2, uhr=uhr)
    limit.erlauben("a")
    uhr.t = 3600
    assert [limit.erlauben("a")[0] for _ in range(3)] == [True, True, False]


def test_api_antwortet_429_mit_retry_after(client_fuer, neuer_mandant):
    client = client_fuer(ratelimit=Ratelimit(pro_minute=1, burst=2))
    _, laut = neuer_mandant("Laut")
    _, leise = neuer_mandant("Leise")
    codes = [client.get("/v1/mandant", headers=laut).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    antwort = client.get("/v1/mandant", headers=laut)
    assert antwort.status_code == 429
    assert int(antwort.headers["Retry-After"]) >= 1
    # der andere Mandant merkt nichts davon
    assert client.get("/v1/mandant", headers=leise).status_code == 200
    metriken = client.get("/metrics").text
    assert 'ratelimit_abgelehnt_total{mandant="Laut' in metriken
