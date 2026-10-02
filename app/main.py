"""API HTTP: GET /, GET /health y POST /carta.

Seguridad:
- Autenticación por header X-API-Key contra la variable de entorno API_KEY (comparación en
  tiempo constante). Si API_KEY no está definida, el módulo falla al importarse y el
  servicio no arranca.
- Rate limit por IP con slowapi (RATE_LIMIT, por defecto 30/minute).
- Los logs solo registran método, ruta y código de estado. Nunca el cuerpo ni la query.
- CORS cerrado salvo que CORS_ORIGINS tenga valores.
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app import service
from app.schemas import CartaRequest, CartaResponse, HealthResponse, RootResponse

# ---------------------------------------------------------------------------
# Configuración (solo variables de entorno; sin secretos en el código ni en la imagen)
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("API_KEY", "").strip()
if not API_KEY:
    raise RuntimeError(
        "La variable de entorno API_KEY es obligatoria y no está definida. "
        "El servicio no arranca sin ella."
    )
_API_KEY_BYTES = API_KEY.encode("utf-8")

RATE_LIMIT = os.environ.get("RATE_LIMIT", "30/minute").strip() or "30/minute"
SOURCE_URL = os.environ.get("SOURCE_URL", "https://github.com/hola-a11y/apapacho").strip()
CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]

# ---------------------------------------------------------------------------
# Logging: formato mínimo. El access log de uvicorn se desactiva (--no-access-log)
# y se sustituye por el middleware de abajo, que no registra IP, query ni cuerpo.
# ---------------------------------------------------------------------------

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("apapacho")

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address, default_limits=[RATE_LIMIT])

app = FastAPI(
    title="apapacho",
    description=(
        "Calcula Sol, Luna y Ascendente a partir de datos de nacimiento. "
        "Software libre bajo AGPL-3.0; usa Swiss Ephemeris a través de Kerykeion."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url=None,
    openapi_url="/openapi.json",
)
app.state.limiter = limiter

if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-API-Key"],
        allow_credentials=False,
    )


@app.middleware("http")
async def _log_request(request: Request, call_next):
    """Registra únicamente método, ruta y status. Sin IP, sin query, sin cuerpo."""
    try:
        response = await call_next(request)
    except Exception:
        log.info("%s %s 500", request.method, request.url.path)
        raise
    log.info("%s %s %s", request.method, request.url.path, response.status_code)
    return response


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={"detail": "Demasiadas peticiones. Inténtalo de nuevo en un momento."},
        headers={"Retry-After": "60"},
    )


@app.exception_handler(RequestValidationError)
async def _validation_handler(request: Request, exc: RequestValidationError):
    # Devolvemos los errores sin el campo "input" para no reflejar los datos enviados.
    errores = [
        {"loc": e.get("loc", ()), "msg": e.get("msg", ""), "type": e.get("type", "")}
        for e in exc.errors()
    ]
    return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, content={"detail": errores})


@app.exception_handler(Exception)
async def _unhandled_handler(request: Request, exc: Exception):
    # Solo el tipo de excepción: el mensaje podría contener datos de entrada.
    log.error("Error no controlado: %s", type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "Error interno"})


# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------


def requiere_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> None:
    if x_api_key is None or not secrets.compare_digest(x_api_key.encode("utf-8"), _API_KEY_BYTES):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key ausente o incorrecta",
            headers={"WWW-Authenticate": "X-API-Key"},
        )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/", response_model=RootResponse, tags=["meta"])
@limiter.exempt
def root(request: Request) -> RootResponse:
    """Oferta de código fuente (AGPL-3.0 §13): enlace al repositorio."""
    return RootResponse(
        name="apapacho",
        license="AGPL-3.0-or-later",
        source=SOURCE_URL,
        docs="/docs",
    )


@app.get("/health", response_model=HealthResponse, tags=["meta"])
@limiter.exempt
def health(request: Request) -> HealthResponse:
    return HealthResponse(status="ok")


@app.post(
    "/carta",
    response_model=CartaResponse,
    dependencies=[Depends(requiere_api_key)],
    tags=["carta"],
    responses={401: {"description": "API key ausente o incorrecta"}, 429: {"description": "Rate limit"}},
)
@limiter.limit(RATE_LIMIT)
def carta(request: Request, datos: CartaRequest) -> CartaResponse:
    """Calcula Sol, Luna y Ascendente (signos en español)."""
    try:
        resultado = service.calcular_carta(
            year=datos.year,
            month=datos.month,
            day=datos.day,
            hour=datos.hour,
            minute=datos.minute,
            lat=datos.lat,
            lng=datos.lng,
        )
    except service.ZonaHorariaNoEncontrada as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    except service.HoraInvalida as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    return CartaResponse(
        sol=resultado.sol,
        luna=resultado.luna,
        ascendente=resultado.ascendente,
        hora_exacta=resultado.hora_exacta,
        luna_puede_variar=resultado.luna_puede_variar,
    )
