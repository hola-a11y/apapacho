"""Tests de los endpoints: auth, validación, hora ausente, rate limit, meta."""

import pytest

MADRID = {"lat": 40.4168, "lng": -3.7038}
CARTA_COMPLETA = {"year": 1990, "month": 7, "day": 15, "hour": 14, "minute": 30, **MADRID}
SIGNOS = {
    "Aries", "Tauro", "Géminis", "Cáncer", "Leo", "Virgo",
    "Libra", "Escorpio", "Sagitario", "Capricornio", "Acuario", "Piscis",
}


# --- meta -------------------------------------------------------------------


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_root_ofrece_codigo_fuente(client):
    r = client.get("/")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["license"].startswith("AGPL-3.0")
    assert cuerpo["source"].startswith("http")


def test_sin_cors_por_defecto(client):
    r = client.options(
        "/carta",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in {k.lower() for k in r.headers}


# --- autenticación -----------------------------------------------------------


def test_carta_sin_api_key(client):
    r = client.post("/carta", json=CARTA_COMPLETA)
    assert r.status_code == 401


def test_carta_api_key_incorrecta(client):
    r = client.post("/carta", json=CARTA_COMPLETA, headers={"X-API-Key": "incorrecta"})
    assert r.status_code == 401


def test_carta_api_key_vacia(client):
    r = client.post("/carta", json=CARTA_COMPLETA, headers={"X-API-Key": ""})
    assert r.status_code == 401


def test_health_no_requiere_api_key(client):
    assert client.get("/health").status_code == 200


# --- cálculo -----------------------------------------------------------------


def test_carta_con_hora(client, auth_headers):
    r = client.post("/carta", json=CARTA_COMPLETA, headers=auth_headers)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert set(cuerpo) == {"sol", "luna", "ascendente", "hora_exacta", "luna_puede_variar"}
    assert cuerpo["sol"] == "Cáncer"  # 15 de julio es Cáncer en cualquier año
    assert cuerpo["luna"] in SIGNOS
    assert cuerpo["ascendente"] in SIGNOS
    assert cuerpo["hora_exacta"] is True
    assert cuerpo["luna_puede_variar"] is False


def test_carta_sin_hora(client, auth_headers):
    datos = {"year": 1990, "month": 7, "day": 15, **MADRID}
    r = client.post("/carta", json=datos, headers=auth_headers)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["sol"] == "Cáncer"
    assert cuerpo["luna"] in SIGNOS
    assert cuerpo["ascendente"] is None
    assert cuerpo["hora_exacta"] is False
    assert isinstance(cuerpo["luna_puede_variar"], bool)


def test_carta_hour_null_explicito(client, auth_headers):
    datos = {"year": 1990, "month": 7, "day": 15, "hour": None, "minute": None, **MADRID}
    r = client.post("/carta", json=datos, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["ascendente"] is None


def test_sin_hora_luna_cambia_de_signo_ese_dia(client, auth_headers):
    # 11/07/1990 en Madrid: la Luna pasa de Acuario a Piscis durante el día.
    datos = {"year": 1990, "month": 7, "day": 11, **MADRID}
    r = client.post("/carta", json=datos, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["luna_puede_variar"] is True


def test_sin_hora_luna_no_cambia_de_signo_ese_dia(client, auth_headers):
    # 15/07/1990 en Madrid: la Luna está en Aries todo el día.
    datos = {"year": 1990, "month": 7, "day": 15, **MADRID}
    r = client.post("/carta", json=datos, headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["luna"] == "Aries"
    assert r.json()["luna_puede_variar"] is False


def test_hora_sin_minuto_asume_cero(client, auth_headers):
    con_minuto = client.post("/carta", json={**CARTA_COMPLETA, "minute": 0}, headers=auth_headers).json()
    sin_minuto = client.post(
        "/carta", json={k: v for k, v in CARTA_COMPLETA.items() if k != "minute"}, headers=auth_headers
    ).json()
    assert con_minuto == sin_minuto


# --- validación --------------------------------------------------------------


@pytest.mark.parametrize(
    "campo,valor",
    [
        ("year", 1899),
        ("year", 2101),
        ("month", 0),
        ("month", 13),
        ("day", 0),
        ("day", 32),
        ("hour", -1),
        ("hour", 24),
        ("minute", -1),
        ("minute", 60),
        ("lat", -90.1),
        ("lat", 90.1),
        ("lng", -180.1),
        ("lng", 180.1),
        ("year", "mil novecientos"),
        ("lat", None),
    ],
)
def test_validacion_de_rangos(client, auth_headers, campo, valor):
    datos = {**CARTA_COMPLETA, campo: valor}
    r = client.post("/carta", json=datos, headers=auth_headers)
    assert r.status_code == 422, r.text


def test_validacion_fecha_inexistente(client, auth_headers):
    r = client.post("/carta", json={**CARTA_COMPLETA, "month": 2, "day": 30}, headers=auth_headers)
    assert r.status_code == 422


def test_validacion_campo_obligatorio_ausente(client, auth_headers):
    datos = {k: v for k, v in CARTA_COMPLETA.items() if k != "lat"}
    r = client.post("/carta", json=datos, headers=auth_headers)
    assert r.status_code == 422


def test_validacion_campo_desconocido(client, auth_headers):
    r = client.post("/carta", json={**CARTA_COMPLETA, "ciudad": "Madrid"}, headers=auth_headers)
    assert r.status_code == 422


def test_validacion_no_refleja_la_entrada(client, auth_headers):
    """El error 422 no debe devolver el campo 'input' con los datos enviados."""
    r = client.post("/carta", json={**CARTA_COMPLETA, "year": 1800}, headers=auth_headers)
    assert r.status_code == 422
    for error in r.json()["detail"]:
        assert "input" not in error


# --- rate limit --------------------------------------------------------------


def test_rate_limit_por_ip(client, auth_headers):
    from app.main import RATE_LIMIT

    limite = int(RATE_LIMIT.split("/")[0])
    datos = {"year": 1990, "month": 7, "day": 15, "hour": 14, "minute": 30, **MADRID}
    for _ in range(limite):
        assert client.post("/carta", json=datos, headers=auth_headers).status_code == 200
    r = client.post("/carta", json=datos, headers=auth_headers)
    assert r.status_code == 429
    assert "Retry-After" in r.headers
