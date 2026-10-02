# Imagen slim, usuario no root, sin secretos: API_KEY se inyecta por entorno en runtime.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/apapacho

# Dependencias primero para aprovechar la caché de capas.
COPY requirements.txt .
RUN pip install -r requirements.txt

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
