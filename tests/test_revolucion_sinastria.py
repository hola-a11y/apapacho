"""Tests de POST /revolucion-solar y POST /sinastria."""

from datetime import datetime

import pytest

from app import service

MADRID = {"lat": 40.4168, "lng": -3.7038}
CDMX = {"lat": 19.4326, "lng": -99.1332}
NATAL = {"year": 1990, "month": 7, "day": 15, "hour": 14, "minute": 30, **MADRID}
OTRA = {"year": 1988, "month": 3, "day": 2, "hour": 8, "minute": 10, **CDMX}
PLANETAS_10 = {"Sol", "Luna", "Mercurio", "Venus", "Marte", "Júpiter", "Saturno", "Urano", "Neptuno", "Plutón"}


# --- revolución solar ----------------------------------------------------------


def _rs(client, auth_headers, **extra):
    return client.post("/revolucion-solar", json={**NATAL, **extra}, headers=auth_headers)


def test_rs_del_anio_de_nacimiento_es_el_nacimiento(client, auth_headers):
    r = _rs(client, auth_headers, anio=1990)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["momento_utc"] == "1990-07-15T12:30:00+00:00"  # 14:30 en Madrid, horario de verano
    assert d["ascendente"] == "Libra"


def test_rs_sol_vuelve_a_su_posicion(client, auth_headers):
    d = _rs(client, auth_headers, anio=2026).json()
    momento = datetime.fromisoformat(d["momento_utc"])
    assert momento.year == 2026 and momento.month == 7 and momento.day in (14, 15, 16)
    sol = next(p for p in d["planetas"] if p["clave"] == "sol")
    assert abs(sol["longitud"] - d["sol_natal"]["longitud"]) < 0.01
    assert d["momento_local"].endswith("+02:00")
    assert d["zona_horaria"] == "Europe/Madrid"
    assert len(d["casas"]) == 12
    assert d["rueda_svg"].startswith("<svg")
    assert d["anio"] == 2026


def test_rs_en_otro_lugar(client, auth_headers):
    en_madrid = _rs(client, auth_headers, anio=2026).json()
    en_cdmx = _rs(client, auth_headers, anio=2026, lat_actual=CDMX["lat"], lng_actual=CDMX["lng"]).json()
    assert en_cdmx["momento_utc"] == en_madrid["momento_utc"]  # el instante no depende del lugar
    assert en_cdmx["zona_horaria"] == "America/Mexico_City"
    assert en_cdmx["momento_local"].endswith("-06:00")
    assert en_cdmx["angulos"] != en_madrid["angulos"]  # las casas sí


def test_rs_nacido_un_29_de_febrero(client, auth_headers):
    datos = {"year": 1992, "month": 2, "day": 29, "hour": 10, "minute": 0, **MADRID, "anio": 2023}
    d = client.post("/revolucion-solar", json=datos, headers=auth_headers).json()
    sol = next(p for p in d["planetas"] if p["clave"] == "sol")
    assert abs(sol["longitud"] - d["sol_natal"]["longitud"]) < 0.01
    assert d["momento_utc"].startswith(("2023-02-28", "2023-03-01"))


def test_rs_sin_hora_es_422(client, auth_headers):
    datos = {k: v for k, v in NATAL.items() if k not in ("hour", "minute")}
    r = client.post("/revolucion-solar", json={**datos, "anio": 2026}, headers=auth_headers)
    assert r.status_code == 422
    assert "hora" in r.json()["detail"]


def test_rs_anio_anterior_al_nacimiento_es_422(client, auth_headers):
    assert _rs(client, auth_headers, anio=1980).status_code == 422


@pytest.mark.parametrize(
    "extra",
    [{"anio": 2026, "lat_actual": 19.4}, {"anio": 2026, "lng_actual": -99.1}, {"anio": 2101},
     {"anio": 2026, "lat_actual": 95, "lng_actual": 0}, {}],
)
def test_rs_validacion(client, auth_headers, extra):
    assert _rs(client, auth_headers, **extra).status_code == 422


def test_rs_requiere_api_key(client):
    assert client.post("/revolucion-solar", json={**NATAL, "anio": 2026}).status_code == 401


# --- sinastría -----------------------------------------------------------------


def _sin(client, auth_headers, a, b):
    r = client.post("/sinastria", json={"persona_a": a, "persona_b": b}, headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_sinastria_estructura(client, auth_headers):
    d = _sin(client, auth_headers, NATAL, OTRA)
    basica = client.post("/carta", json=NATAL, headers=auth_headers).json()
    for campo in ("sol", "luna", "ascendente", "hora_exacta", "luna_puede_variar"):
        assert d["persona_a"][campo] == basica[campo]
    assert 0 <= d["puntuacion"] <= 100
    asp = d["aspectos"]
    assert asp
    assert [x["orbe"] for x in asp] == sorted(x["orbe"] for x in asp)
    permitidos = PLANETAS_10 | {"Ascendente"}
    for x in asp:
        assert x["a"] in permitidos and x["b"] in permitidos
        assert x["orbe"] <= service.orbe_maximo(x["tipo"], x["a"], x["b"], sinastria=True)
        if x["generacional"]:
            assert x["peso"] == 0
    r = d["resumen"]
    assert r["armonicos"] == sum(1 for x in asp if x["armonico"] is True)
    assert r["tensos"] == sum(1 for x in asp if x["armonico"] is False)
    assert r["conjunciones"] == sum(1 for x in asp if x["tipo"] == "conjunción")


def test_sinastria_simetrica(client, auth_headers):
    ab = _sin(client, auth_headers, NATAL, OTRA)
    ba = _sin(client, auth_headers, OTRA, NATAL)
    assert ab["puntuacion"] == ba["puntuacion"]
    assert len(ab["aspectos"]) == len(ba["aspectos"])


def test_sinastria_sin_hora(client, auth_headers):
    sin_hora = {k: v for k, v in OTRA.items() if k not in ("hour", "minute")}
    d = _sin(client, auth_headers, NATAL, sin_hora)
    assert d["persona_b"]["ascendente"] is None
    assert all(x["b"] != "Ascendente" for x in d["aspectos"])
    assert any(x["a"] == "Ascendente" for x in d["aspectos"])  # A sí tiene hora y ascendente
    # El 02/03/1988 la Luna de B recorre unos 13°: un trígono casi exacto aguanta todo el día,
    # uno a 4,5° de orbe no.
    por_par = {(x["a"], x["tipo"], x["b"]): x for x in d["aspectos"]}
    assert por_par[("Marte", "trígono", "Luna")]["puede_variar"] is False
    assert por_par[("Urano", "trígono", "Luna")]["puede_variar"] is True


def test_sinastria_validacion(client, auth_headers):
    r = client.post("/sinastria", json={"persona_a": NATAL, "persona_b": {**OTRA, "lat": 100}}, headers=auth_headers)
    assert r.status_code == 422
    r = client.post("/sinastria", json={"persona_a": NATAL}, headers=auth_headers)
    assert r.status_code == 422


def test_sinastria_requiere_api_key(client):
    assert client.post("/sinastria", json={"persona_a": NATAL, "persona_b": OTRA}).status_code == 401


def test_peso_aspecto():
    assert service.peso_aspecto_sinastria("trígono", "Sol", "Luna", 0, False) == pytest.approx(4.5)
    assert service.peso_aspecto_sinastria("cuadratura", "Marte", "Venus", 0, False) == pytest.approx(-3.0)
    assert service.peso_aspecto_sinastria("conjunción", "Venus", "Júpiter", 0, False) == pytest.approx(2.5 * 1.25)
    assert service.peso_aspecto_sinastria("conjunción", "Saturno", "Sol", 0, False) == pytest.approx(-1.5 * 1.25)
    assert service.peso_aspecto_sinastria("trígono", "Urano", "Neptuno", 0, False) == 0
    # En el límite del orbe cuenta la mitad; si puede variar, otra mitad menos.
    limite = service.orbe_maximo("trígono", "Sol", "Luna", sinastria=True)
    assert service.peso_aspecto_sinastria("trígono", "Sol", "Luna", limite, False) == pytest.approx(2.25)
    assert service.peso_aspecto_sinastria("trígono", "Sol", "Luna", 0, True) == pytest.approx(2.25)
