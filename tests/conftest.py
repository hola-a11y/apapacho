"""Configuración común de los tests.

API_KEY se fija ANTES de importar app.main, porque el módulo se niega a arrancar sin ella.
"""

import os

import pytest

TEST_API_KEY = "clave-de-pruebas"
os.environ.setdefault("API_KEY", TEST_API_KEY)
os.environ.setdefault("RATE_LIMIT", "30/minute")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app, limiter  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    """Cada test parte con el contador de rate limit a cero."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    return {"X-API-Key": os.environ["API_KEY"]}
