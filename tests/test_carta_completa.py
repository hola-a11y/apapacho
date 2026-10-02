"""Tests de POST /carta/completa y del cálculo de la carta completa."""

import pytest

from app import service

MADRID = {"lat": 40.4168, "lng": -3.7038}
CON_HORA = {"year": 1990, "month": 7, "day": 15, "hour": 14, "minute": 30, **MADRID}
SIN_HORA = {"year": 1990, "month": 7, "day": 11, **MADRID}
CLAVES = ["sol", "luna", "mercurio", "venus", "marte", "jupiter", "saturno",
          "urano", "neptuno", "pluton", "nodo_norte", "quiron"]


def _post(client, auth_headers, datos):
    r = client.post("/carta/completa", json=datos, headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_requiere_api_key(client):
    assert client.post("/carta/completa", json=CON_HORA).status_code == 401


def test_valida_igual_que_carta(client, auth_headers):
    r = client.post("/carta/completa", json={**CON_HORA, "lat": 91}, headers=auth_headers)
    assert r.status_code == 422


def test_incluye_los_campos_de_carta(client, auth_headers):
    completa = _post(client, auth_headers, CON_HORA)
    basica = client.post("/carta", json=CON_HORA, headers=auth_headers).json()
    for campo in ("sol", "luna", "ascendente", "hora_exacta", "luna_puede_variar"):
        assert completa[campo] == basica[campo]


def test_con_hora_estructura_completa(client, auth_headers):
    d = _post(client, auth_headers, CON_HORA)
    assert [p["clave"] for p in d["planetas"]] == CLAVES
    for p in d["planetas"]:
        assert p["signo"] in service.SIGNOS_ES
        assert 0 <= p["grado"] < 30
        assert 1 <= p["casa"] <= 12
        assert p["puede_variar"] is False
    assert [c["numero"] for c in d["casas"]] == list(range(1, 13))
    assert d["angulos"]["ascendente"]["signo"] == d["ascendente"]
    # Con hora cuentan 10 planetas + ascendente.
    assert sum(d["elementos"].values()) == 11
    assert sum(d["modalidades"].values()) == 11


def test_con_hora_valores_conocidos(client, auth_headers):
    """15/07/1990 14:30 Madrid. Valores contrastables con cualquier efeméride."""
    d = _post(client, auth_headers, CON_HORA)
    p = {x["clave"]: x for x in d["planetas"]}
    assert p["sol"]["signo"] == "Cáncer"
    assert p["marte"]["signo"] == "Tauro"  # Marte entró en Tauro el 12/07/1990
    for lento in ("saturno", "urano", "neptuno"):
        assert p[lento]["signo"] == "Capricornio"
        assert p[lento]["retrogrado"] is True
    assert p["pluton"]["signo"] == "Escorpio"
    assert p["sol"]["retrogrado"] is False
    assert d["angulos"]["medio_cielo"]["signo"] == "Cáncer"
    assert d["casas"][0]["signo"] == d["ascendente"]  # cúspide de la casa 1 = ascendente
    assert d["casas"][9]["signo"] == d["angulos"]["medio_cielo"]["signo"]  # casa 10 = MC
    assert d["fase_lunar"]["nombre"] == "Cuarto menguante"  # cuarto menguante el 15/07/1990


def test_sin_hora(client, auth_headers):
    d = _post(client, auth_headers, SIN_HORA)
    assert d["hora_exacta"] is False
    assert d["ascendente"] is None
    assert d["angulos"] is None
    assert d["casas"] is None
    assert all(p["casa"] is None for p in d["planetas"])
    # Sin hora cuentan solo los 10 planetas.
    assert sum(d["elementos"].values()) == 10
    luna = next(p for p in d["planetas"] if p["clave"] == "luna")
    assert luna["puede_variar"] is True
    assert d["luna_puede_variar"] is True


def test_latitud_polar_no_falla(client, auth_headers):
    d = _post(client, auth_headers, {"year": 1990, "month": 12, "day": 21, "hour": 12, "minute": 0,
                                     "lat": 78.22, "lng": 15.65})  # Longyearbyen
    assert len(d["casas"]) == 12


@pytest.mark.parametrize(
    "sol_abs,luna_abs,esperado",
    [
        (100, 100, "Luna nueva"),
        (100, 145, "Luna creciente"),
        (100, 190, "Cuarto creciente"),
        (100, 280, "Luna llena"),
        (100, 10, "Cuarto menguante"),
        (350, 5, "Luna nueva"),
    ],
)
def test_fase_lunar(sol_abs, luna_abs, esperado):
    assert service.fase_lunar(sol_abs, luna_abs)["nombre"] == esperado


def test_fase_lunar_iluminacion():
    assert service.fase_lunar(0, 0)["iluminacion"] == 0
    assert service.fase_lunar(0, 180)["iluminacion"] == 100


@pytest.mark.parametrize("grado,texto", [(0, "0°00′"), (22.75, "22°45′"), (29.9999, "29°59′"), (12.5, "12°30′")])
def test_grado_texto(grado, texto):
    assert service.grado_texto(grado) == texto
