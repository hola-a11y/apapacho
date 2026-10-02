# Build en dos fases:
# 1) "builder" usa la imagen completa python:3.12, que ya trae gcc, para compilar las
#    dependencias sin wheel para Python 3.12 (pyswisseph, el motor de Swiss Ephemeris).
#    Misma versión de Debian que la slim, así que las wheels son compatibles.
# 2) La imagen final es slim, sin compilador, con usuario no root y sin secretos:
#    API_KEY se inyecta por entorno en tiempo de ejecución.

FROM python:3.12 AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY requirements.txt .
RUN pip wheel --wheel-dir /wheels -r requirements.txt


FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/apapacho

# Instala solo desde las wheels ya compiladas, sin acceso al índice.
COPY requirements.txt .
COPY --from=builder /wheels /wheels
RUN pip install --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels

# Usuario sin privilegios.
RUN groupadd --system --gid 1001 app \
    && useradd --system --uid 1001 --gid app --home-dir /srv/apapacho --shell /usr/sbin/nologin app

COPY --chown=app:app app ./app

USER app
EXPOSE 8000

# Sin curl en la imagen slim: el healthcheck usa la propia stdlib de Python.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200 else 1)"

# --no-access-log: el access log de uvicorn incluye la IP del cliente; el servicio registra
# por su cuenta solo método, ruta y status. --proxy-headers para leer X-Forwarded-* del
# reverse proxy (controlado por FORWARDED_ALLOW_IPS).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers"]
