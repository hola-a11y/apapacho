"""Tests del módulo de cálculo: zona horaria, horario de verano histórico, logs."""

import logging

import pytest

from app import service

MADRID = (40.4168, -3.7038)
CDMX = (19.4326, -99.1332)


def test_zona_horaria_por_coordenadas():
    assert service.zona_horaria(*MADRID) == "Europe/Madrid"
    assert service.zona_horaria(*CDMX) == "America/Mexico_City"


def test_zona_horaria_en_el_mar_devuelve_etc_gmt():
    # Atlántico medio: timezonefinder devuelve una zona náutica Etc/GMT±N.
    assert service.zona_horaria(0.0, -30.0).startswith("Etc/GMT")


def test_horario_de_verano_historico_ciudad_de_mexico():
    """México aplicó horario de verano hasta 2022. La misma fecha/hora local tiene distinto
    offset UTC según el año: la zona horaria IANA debe respetar la historia, no el estado actual."""
    lat, lng = CDMX
    tz = service.zona_horaria(lat, lng)
    con_dst = service._calcular(2010, 7, 1, 12, 0, lat, lng, tz, True)
    sin_dst = service._calcular(2024, 7, 1, 12, 0, lat, lng, tz, True)
    assert con_dst.local_iso.endswith("-05:00")  # CDT
    assert sin_dst.local_iso.endswith("-06:00")  # CST
    assert con_dst.utc_iso == "2010-07-01T17:00:00+00:00"
    assert sin_dst.utc_iso == "2024-07-01T18:00:00+00:00"


def test_horario_de_verano_historico_madrid():
    """España no tenía horario de verano en 1950 (UTC+1); en 1990 sí (UTC+2)."""
    lat, lng = MADRID
    tz = service.zona_horaria(lat, lng)
    assert service._calcular(1950, 7, 1, 12, 0, lat, lng, tz, True).local_iso.endswith("+01:00")
    assert service._calcular(1990, 7, 1, 12, 0, lat, lng, tz, True).local_iso.endswith("+02:00")


def test_hora_inexistente_por_cambio_de_hora_no_falla():
    # 31/03/2024 02:30 no existe en Madrid (los relojes saltan de 02:00 a 03:00).
    carta = service.calcular_carta(2024, 3, 31, *MADRID, hour=2, minute=30)
    assert carta.ascendente is not None


def test_hora_ambigua_por_cambio_de_hora_no_falla():
    # 27/10/2024 02:30 ocurre dos veces en Madrid.
    carta = service.calcular_carta(2024, 10, 27, *MADRID, hour=2, minute=30)
    assert carta.ascendente is not None


def test_sin_hora_usa_mediodia_para_sol_y_luna():
    sin_hora = service.calcular_carta(1990, 7, 15, *MADRID)
    mediodia = service.calcular_carta(1990, 7, 15, *MADRID, hour=12, minute=0)
    assert sin_hora.sol == mediodia.sol
    assert sin_hora.luna == mediodia.luna
    assert sin_hora.ascendente is None
    assert sin_hora.hora_exacta is False


def test_signos_en_espanol():
    assert len(service.SIGNOS_ES) == 12
    assert service.SIGNOS_ES[0] == "Aries"
    assert service.SIGNOS_ES[11] == "Piscis"


def test_logs_no_contienen_datos_de_nacimiento(client, auth_headers, caplog):
    datos = {"year": 1987, "month": 3, "day": 21, "hour": 6, "minute": 45, "lat": 41.3874, "lng": 2.1686}
    with caplog.at_level(logging.DEBUG, logger="apapacho"):
        r = client.post("/carta", json=datos, headers=auth_headers)
    assert r.status_code == 200
    texto = " ".join(rec.getMessage() for rec in caplog.records if rec.name == "apapacho")
    assert "POST /carta 200" in texto
    for prohibido in ("1987", "41.38", "2.1686", "6:45", "testclient"):
        assert prohibido not in texto
