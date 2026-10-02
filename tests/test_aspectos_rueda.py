"""Tests de los aspectos y de la rueda SVG."""

import re
import xml.etree.ElementTree as ET

import pytest

from app import rueda, service

MADRID = {"lat": 40.4168, "lng": -3.7038}
CON_HORA = {"year": 1990, "month": 7, "day": 15, "hour": 14, "minute": 30, **MADRID}
SIN_HORA = {"year": 1990, "month": 7, "day": 11, **MADRID}
PLANETAS_10 = {"Sol", "Luna", "Mercurio", "Venus", "Marte", "Júpiter", "Saturno", "Urano", "Neptuno", "Plutón"}
SVG_NS = "{http://www.w3.org/2000/svg}"


def _completa(client, auth_headers, datos):
    r = client.post("/carta/completa", json=datos, headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()


def _buscar(aspectos, a, b):
    for x in aspectos:
        if {x["a"], x["b"]} == {a, b}:
            return x
    return None


# --- aspectos -----------------------------------------------------------------


def test_aspectos_conocidos(client, auth_headers):
    """15/07/1990 14:30 Madrid: Sol 22°46′ Cáncer, Júpiter 22°33′ Cáncer, Saturno 21°58′ Capricornio,
    Luna 23°33′ Aries."""
    asp = _completa(client, auth_headers, CON_HORA)["aspectos"]
    sol_jup = _buscar(asp, "Sol", "Júpiter")
    assert sol_jup["tipo"] == "conjunción" and sol_jup["orbe"] < 0.5
    assert sol_jup["armonico"] is None
    assert sol_jup["aplicativo"] is False  # el Sol, más rápido, ya ha pasado a Júpiter
    assert _buscar(asp, "Sol", "Saturno")["tipo"] == "oposición"
    sol_luna = _buscar(asp, "Sol", "Luna")
    assert sol_luna["tipo"] == "cuadratura" and sol_luna["armonico"] is False
    assert sol_luna["aplicativo"] is False  # la Luna ya pasó la cuadratura exacta


def test_aspectos_reglas(client, auth_headers):
    d = _completa(client, auth_headers, CON_HORA)
    asp = d["aspectos"]
    assert asp, "debería haber aspectos"
    assert [a["orbe"] for a in asp] == sorted(a["orbe"] for a in asp)
    permitidos = PLANETAS_10 | {"Ascendente", "Medio Cielo"}
    exactos = {"conjunción": 0, "sextil": 60, "cuadratura": 90, "trígono": 120, "oposición": 180}
    for a in asp:
        assert a["a"] in permitidos and a["b"] in permitidos
        assert {a["a"], a["b"]} != {"Ascendente", "Medio Cielo"}
        base = 6 if a["tipo"] == "sextil" else 8
        maximo = base + (2 if {"Sol", "Luna"} & {a["a"], a["b"]} else 0)
        assert a["orbe"] <= maximo
        assert abs(abs(a["angulo"] - exactos[a["tipo"]]) - a["orbe"]) < 0.02
        assert a["puede_variar"] is False


def test_aspectos_sin_hora(client, auth_headers):
    asp = _completa(client, auth_headers, SIN_HORA)["aspectos"]
    for a in asp:
        assert a["a"] in PLANETAS_10 and a["b"] in PLANETAS_10
    # El 11/07/1990 la Luna recorre unos 13°: alguno de sus aspectos no dura todo el día.
    assert any(a["puede_variar"] for a in asp if "Luna" in (a["a"], a["b"]))


@pytest.mark.parametrize(
    "lon_a,lon_b,tipo",
    [(10, 12, "conjunción"), (10, 70, "sextil"), (10, 100, "cuadratura"), (10, 130, "trígono"),
     (10, 190, "oposición"), (358, 3, "conjunción"), (10, 40, None)],
)
def test_aspecto_entre(lon_a, lon_b, tipo):
    r = service.aspecto_entre("Marte", lon_a, "Venus", lon_b)
    assert (r[0] if r else None) == tipo


def test_orbe_ampliado_con_luminarias():
    # 9° de orbe: vale con el Sol, no entre dos planetas.
    assert service.aspecto_entre("Sol", 0, "Marte", 99) is not None
    assert service.aspecto_entre("Venus", 0, "Marte", 99) is None


# --- rueda SVG ----------------------------------------------------------------


def _validar_svg(svg: str) -> ET.Element:
    raiz = ET.fromstring(svg)
    assert raiz.tag == SVG_NS + "svg"
    assert raiz.get("role") == "img"
    assert raiz.find(SVG_NS + "title").text
    assert raiz.find(SVG_NS + "desc").text
    bajo = svg.lower()
    assert "<script" not in bajo
    assert "href" not in bajo
    assert "@import" not in bajo and "url(" not in bajo
    assert not re.search(r"\son\w+=", bajo), "sin atributos de evento"
    # La única URL permitida es el espacio de nombres SVG.
    assert re.findall(r"https?://[^\"']+", svg) == ["http://www.w3.org/2000/svg"]
    return raiz


def test_rueda_endpoint(client, auth_headers):
    r = client.post("/carta/rueda.svg", json=CON_HORA, headers=auth_headers)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/svg+xml")
    raiz = _validar_svg(r.text)
    assert "Libra" in raiz.find(SVG_NS + "title").text


def test_rueda_requiere_api_key(client):
    assert client.post("/carta/rueda.svg", json=CON_HORA).status_code == 401


def test_rueda_valida_entrada(client, auth_headers):
    r = client.post("/carta/rueda.svg", json={**CON_HORA, "year": 1800}, headers=auth_headers)
    assert r.status_code == 422


def test_rueda_sin_hora(client, auth_headers):
    r = client.post("/carta/rueda.svg", json=SIN_HORA, headers=auth_headers)
    assert r.status_code == 200
    raiz = _validar_svg(r.text)
    assert "Sin hora" in raiz.find(SVG_NS + "desc").text


def test_rueda_incluida_en_carta_completa(client, auth_headers):
    d = _completa(client, auth_headers, CON_HORA)
    _validar_svg(d["rueda_svg"])


def test_ascendente_a_la_izquierda():
    lienzo = rueda._Lienzo(referencia=201.36)
    x, y = lienzo.xy(201.36, 100)
    assert x == pytest.approx(rueda.C - 100) and y == pytest.approx(rueda.C)
    # 90° más en el zodiaco = abajo en pantalla (sentido antihorario).
    x, y = lienzo.xy(291.36, 100)
    assert x == pytest.approx(rueda.C) and y == pytest.approx(rueda.C + 100)


def test_repartir_separa_y_conserva_orden():
    longitudes = [112.77, 112.55, 109.23, 126.81, 300.0]
    vis = rueda._repartir(longitudes, 0)
    rel = sorted(vis)
    huecos = [b - a for a, b in zip(rel, rel[1:])] + [rel[0] + 360 - rel[-1]]
    assert min(huecos) >= rueda.SEPARACION_MIN - 1e-6
    orden_real = sorted(range(5), key=lambda i: longitudes[i])
    orden_vis = sorted(range(5), key=lambda i: vis[i])
    assert orden_real == orden_vis


def test_rueda_latitud_polar():
    d = service.calcular_carta_completa(1990, 12, 21, 78.22, 15.65, 12, 0)
    _validar_svg(rueda.generar_rueda(d))
