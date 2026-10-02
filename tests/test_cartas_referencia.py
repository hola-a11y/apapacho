"""Compara la API con las 5 cartas de referencia de astro.com (tests/cartas_referencia.py)."""

import pytest

from tests.cartas_referencia import CARTAS_REFERENCIA

CAMPOS_ENTRADA_OBLIGATORIOS = ("year", "month", "day", "lat", "lng")


def _lista_para_rellenar(carta: dict) -> bool:
    entrada, esperado = carta["entrada"], carta["esperado"]
    if any(entrada.get(k) is None for k in CAMPOS_ENTRADA_OBLIGATORIOS):
        return False
    if esperado.get("sol") is None or esperado.get("luna") is None:
        return False
    # Si se indicó hora, también hace falta el ascendente esperado.
    if entrada.get("hour") is not None and esperado.get("ascendente") is None:
        return False
    return True


@pytest.mark.parametrize("carta", CARTAS_REFERENCIA, ids=[c["id"] for c in CARTAS_REFERENCIA])
def test_carta_de_referencia(client, auth_headers, carta):
    if not _lista_para_rellenar(carta):
        pytest.skip(f"{carta['id']}: rellena entrada y esperado en tests/cartas_referencia.py")

    entrada = {k: v for k, v in carta["entrada"].items() if v is not None}
    esperado = carta["esperado"]

    r = client.post("/carta", json=entrada, headers=auth_headers)
    assert r.status_code == 200, r.text
    cuerpo = r.json()

    assert cuerpo["sol"] == esperado["sol"]
    assert cuerpo["luna"] == esperado["luna"]
    if entrada.get("hour") is not None:
        assert cuerpo["ascendente"] == esperado["ascendente"]
        assert cuerpo["hora_exacta"] is True
    else:
        assert cuerpo["ascendente"] is None
        assert cuerpo["hora_exacta"] is False
