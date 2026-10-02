# apapacho

Microservicio HTTP, libre y gratuito (AGPL-3.0), que calcula **Sol, Luna y Ascendente** a partir
de los datos de nacimiento. Pensado para consumirse desde un workflow de **n8n** detrás de un
formulario. No hace geocoding: la ciudad se convierte a coordenadas fuera (por ejemplo en n8n
con Nominatim) y aquí solo entran latitud y longitud.

- Python 3.12 · FastAPI · [Kerykeion](https://github.com/g-battaglia/kerykeion) (Swiss Ephemeris) ·
  timezonefinder · pydantic v2 · slowapi.
- Cálculo 100 % offline: no llama a ningún servicio externo.
- Zona horaria resuelta a partir de lat/lng como nombre IANA (`Europe/Madrid`,
  `America/Mexico_City`...), así se respetan los horarios de verano **históricos**.
- Signos devueltos en español. Casas Placidus, zodiaco tropical (como astro.com por defecto).

## Qué devuelve

`POST /carta` con:

```json
{ "year": 1990, "month": 7, "day": 15, "hour": 14, "minute": 30, "lat": 40.4168, "lng": -3.7038 }
```

responde:

```json
{ "sol": "Cáncer", "luna": "Aries", "ascendente": "Libra", "hora_exacta": true, "luna_puede_variar": false }
```

| Campo de entrada | Tipo | Rango | Obligatorio |
|---|---|---|---|
| `year` | int | 1900 – 2100 | sí |
| `month` | int | 1 – 12 | sí |
| `day` | int | 1 – 31 (y fecha válida) | sí |
| `hour` | int o null | 0 – 23 | no |
| `minute` | int o null | 0 – 59 | no (0 si hay hora) |
| `lat` | float | -90 – 90 | sí |
| `lng` | float | -180 – 180 | sí |

La hora es la **hora local del lugar de nacimiento**, tal como figura en el certificado. No la
conviertas a UTC: el servicio lo hace con la zona horaria del punto geográfico.

**Si `hour` es null o se omite**: Sol y Luna se calculan a las 12:00 locales, `ascendente` es
`null`, `hora_exacta` es `false` y `luna_puede_variar` es `true` cuando la Luna cambia de signo
entre las 00:00 y las 23:59 de ese día (ocurre aproximadamente uno de cada dos o tres días).

Horas que no existen o se repiten por un cambio de hora (madrugada del cambio al horario de
verano / invierno) se resuelven asumiendo horario estándar, en lugar de devolver error.

Otros endpoints:

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/` | no | Nombre, licencia y enlace al código fuente (oferta AGPL) |
| GET | `/health` | no | `{"status": "ok"}` |
| GET | `/docs` | no | OpenAPI / Swagger |
| POST | `/carta` | `X-API-Key` | Cálculo |

Errores: `401` API key ausente o incorrecta · `422` validación · `429` rate limit.

## Cómo correrlo

### Con Docker Compose (recomendado)

```bash
git clone https://github.com/hola-a11y/apapacho.git
cd apapacho
cp .env.example .env
# Genera una clave y pégala en .env como API_KEY=...
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
docker compose up -d --build
```

Por defecto el contenedor **no publica ningún puerto**: vive en la red interna `apapacho_net`
(sin salida a Internet) y solo es alcanzable por otros contenedores de esa red, normalmente el
reverse proxy. Para probarlo en local sin proxy, entra desde otro contenedor de la misma red:

```bash
docker run --rm --network apapacho_net curlimages/curl -s http://apapacho:8000/health
```

o publica temporalmente el puerto con un override (no lo subas a producción):

```bash
cat > docker-compose.override.yml <<'YAML'
services:
  apapacho:
    ports: ["127.0.0.1:8000:8000"]
YAML
docker compose up -d
```

### En local, sin Docker

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export API_KEY="una-clave-larga"
uvicorn app.main:app --reload --no-access-log
```

### Ejemplo con curl

```bash
curl -s -X POST http://localhost:8000/carta \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"year":1990,"month":7,"day":15,"hour":14,"minute":30,"lat":40.4168,"lng":-3.7038}'
```

Sin hora de nacimiento:

```bash
curl -s -X POST http://localhost:8000/carta \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $API_KEY" \
  -d '{"year":1990,"month":7,"day":11,"lat":40.4168,"lng":-3.7038}'
# {"sol":"Cáncer","luna":"Acuario","ascendente":null,"hora_exacta":false,"luna_puede_variar":true}
```

## Configuración (variables de entorno)

| Variable | Por defecto | Descripción |
|---|---|---|
| `API_KEY` | — | **Obligatoria.** Sin ella el proceso no arranca. Comparación en tiempo constante. |
| `RATE_LIMIT` | `30/minute` | Límite por IP en `POST /carta` (sintaxis de [limits](https://limits.readthedocs.io/)). |
| `CORS_ORIGINS` | vacío | Orígenes permitidos, separados por comas. Vacío = CORS cerrado. |
| `SOURCE_URL` | este repo | URL devuelta en `GET /`. Cámbiala si publicas un fork modificado. |
| `FORWARDED_ALLOW_IPS` | `*` | Proxies de confianza para `X-Forwarded-For` (uvicorn). |

## Seguridad y privacidad

- Autenticación por header `X-API-Key` comparada con `secrets.compare_digest`.
- Rate limit por IP (slowapi). Detrás de un reverse proxy la IP real llega por
  `X-Forwarded-For`; por eso el contenedor arranca con `--proxy-headers`.
- **Los logs solo contienen método, ruta y código de estado.** Nunca el cuerpo, la query ni la IP.
  El access log de uvicorn está desactivado y los errores 422 no reflejan la entrada recibida.
- CORS cerrado por defecto. Sin endpoints de depuración. El esquema rechaza campos desconocidos.
- Imagen `python:3.12-slim`, usuario no root, sistema de archivos de solo lectura, sin
  capabilities, sin secretos en la imagen (la clave entra por `.env`, que está en `.gitignore`).
- No se persiste nada: cada petición se calcula y se olvida.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

Cubre: hora ausente (y detección de cambio de signo lunar), validación de rangos y fechas,
auth faltante/incorrecta, rate limit, CORS cerrado, zona horaria con horario de verano
histórico (Ciudad de México 2010 vs 2024, Madrid 1950 vs 1990) y que los logs no contienen
datos de nacimiento.

### Cartas de referencia (astro.com)

`tests/cartas_referencia.py` tiene 5 fixtures con los datos de entrada y los resultados
esperados vacíos. Rellénalos con cartas calculadas en astro.com y los tests dejarán de marcarse
como `skipped`. Introduce la hora local y las coordenadas que usaste en astro.com, y los signos
con el nombre en español exacto (`Géminis`, `Cáncer`, `Escorpio`...).

## Despliegue en un VPS detrás de un reverse proxy con HTTPS

Esquema: Internet → proxy (443, TLS) → red Docker interna → `apapacho:8000`.
El servicio nunca se expone directamente.

### Opción A: Caddy (TLS automático con Let's Encrypt)

1. Apunta un DNS `A` (por ejemplo `carta.tudominio.com`) a la IP del VPS y abre solo 80/443 en
   el firewall (`ufw allow 80,443/tcp`).
2. Levanta apapacho: `docker compose up -d --build` (crea la red `apapacho_net`).
3. Crea en otra carpeta un `docker-compose.yml` para Caddy que se una a esa red:

```yaml
services:
  caddy:
    image: caddy:2
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    networks:
      - default        # salida a Internet para pedir certificados
      - apapacho_net   # acceso al servicio

volumes:
  caddy_data:
  caddy_config:

networks:
  apapacho_net:
    external: true
```

y un `Caddyfile`:

```
carta.tudominio.com {
    encode gzip
    reverse_proxy apapacho:8000
}
```

4. `docker compose up -d` en la carpeta de Caddy. Caddy obtiene y renueva el certificado solo y
   reenvía `X-Forwarded-For`, que apapacho usa para el rate limit.
5. Comprueba: `curl https://carta.tudominio.com/health`.

Si ya tienes **Traefik** o **nginx-proxy** en el VPS, basta con conectar ese contenedor a
`apapacho_net` (`docker network connect apapacho_net <proxy>`) y añadir una ruta hacia
`http://apapacho:8000`. Con nginx fuera de Docker, publica el puerto solo en loopback
(`127.0.0.1:8000:8000`, ver override arriba) y usa `proxy_pass http://127.0.0.1:8000;` con
`proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;` y certificados de certbot.

Actualizar: `git pull && docker compose up -d --build`. Logs: `docker compose logs -f apapacho`.

## Conectarlo desde n8n (nodo HTTP Request)

Antes del nodo necesitas `lat` y `lng` (por ejemplo, otro HTTP Request a Nominatim:
`https://nominatim.openstreetmap.org/search?q={{ $json.ciudad }}&format=json&limit=1`, con un
header `User-Agent` identificativo, y toma `[0].lat` y `[0].lon`).

1. **Credencial**: Credentials → New → *Header Auth*. Name: `X-API-Key`, Value: tu `API_KEY`.
   Así la clave no queda escrita en el workflow.
2. **Nodo HTTP Request**:
   - Method: `POST`
   - URL: `https://carta.tudominio.com/carta`
   - Authentication: *Generic Credential Type* → *Header Auth* → la credencial anterior.
   - Send Body: ON · Body Content Type: `JSON` · Specify Body: *Using JSON*:

   ```json
   {
     "year": {{ $json.year }},
     "month": {{ $json.month }},
     "day": {{ $json.day }},
     "hour": {{ $json.hour ?? null }},
     "minute": {{ $json.minute ?? null }},
     "lat": {{ Number($json.lat) }},
     "lng": {{ Number($json.lon) }}
   }
   ```

   Si el formulario trae la fecha como texto (`1990-07-15`), descompónla antes:
   `{{ Number($json.fecha.split('-')[0]) }}`, etc. Si la hora viene vacía, debe llegar `null`,
   no `""` ni `0`.
   - Options → *Response* → Response Format: `JSON`.
   - Options → *Batching* o un nodo *Wait* si el formulario puede generar ráfagas: el límite es
     30 peticiones por minuto por IP (ajustable con `RATE_LIMIT`).
3. Usa la salida en los nodos siguientes: `{{ $json.sol }}`, `{{ $json.luna }}`,
   `{{ $json.ascendente }}`, `{{ $json.hora_exacta }}`, `{{ $json.luna_puede_variar }}`.
   Por ejemplo, un nodo *IF* sobre `luna_puede_variar` para avisar de que, sin hora exacta,
   la Luna podría ser del signo contiguo.

Si n8n corre en el mismo VPS con Docker, puedes saltarte el proxy y llamar a
`http://apapacho:8000/carta` directamente. Para ello, en el `docker-compose.yml` de n8n añade
al servicio `n8n` las dos redes y declara `apapacho_net` como externa:

```yaml
services:
  n8n:
    # ...
    networks:
      - default        # la red de siempre: Postgres, Traefik
      - apapacho_net
    labels:
      # Imprescindible si n8n se publica con Traefik: con dos redes, Traefik podría
      # intentar llegar a n8n por apapacho_net (interna) y la web de n8n daría error.
      - traefik.docker.network=<proyecto>_default   # p. ej. n8n_default
      # ...resto de labels

networks:
  apapacho_net:
    external: true
```

Aplica con `docker compose up -d n8n`. Como `apapacho_net` la crea el compose de apapacho,
levanta apapacho antes que n8n y no hagas `docker compose down` en apapacho sin parar n8n.
Todas las peticiones llegarán desde la IP de n8n, así que `RATE_LIMIT` es el total del
formulario: súbelo si esperas más de 30 envíos por minuto.

## Formulario web de ejemplo

`web/formulario.html` es un formulario accesible, sin dependencias externas, que envía ciudad,
fecha y hora a un webhook de n8n y muestra Sol, Luna y Ascendente. Cambia `WEBHOOK_URL` dentro
del archivo y súbelo a cualquier hosting estático. La API key nunca va en el HTML: la guarda n8n.

`n8n/workflow-apapacho.json` es el workflow de n8n que hay detrás, listo para importar
(probado en n8n 2.21.7): webhook, validación con campo trampa para bots, Nominatim, apapacho y
respuestas de error con los códigos que espera el formulario. Para usarlo:

1. En n8n: *Create workflow* → menú `...` → *Import from File* → elige el archivo.
2. Abre el nodo **apapacho** y, si avisa de credencial, elige tu credencial Header Auth.
3. En el nodo **Nominatim**, cambia el correo del header `User-Agent` por el tuyo.
4. En el nodo **Webhook**, cambia *Allowed Origins (CORS)* de `*` al dominio del formulario.
5. Publica el workflow. La URL de producción es `https://<tu-n8n>/webhook/apapacho`.

El workflow no guarda ejecuciones (`Do not save`). n8n marca cada ejecución como borrada al
terminar y su limpieza automática (`EXECUTIONS_DATA_PRUNE=true`) la elimina después.

`docs/prompt-agente-n8n.md` contiene un prompt para que un agente construya ese mismo workflow
desde cero, si prefieres no importarlo.

## Licencia y aviso sobre Swiss Ephemeris

Este proyecto se distribuye bajo la **GNU Affero General Public License v3.0** (`LICENSE`).
Los cálculos los realiza [Kerykeion](https://github.com/g-battaglia/kerykeion) (AGPL-3.0),
que usa [Swiss Ephemeris](https://www.astro.com/swisseph/) de Astrodienst a través de
[pyswisseph](https://github.com/astrorigin/pyswisseph). Swiss Ephemeris se licencia bajo
AGPL-3.0 (o licencia comercial de Astrodienst); por eso este servicio también es AGPL y, al
ofrecerse como servicio en red, debe facilitar su código fuente a los usuarios. `GET /`
devuelve el enlace al repositorio: <https://github.com/hola-a11y/apapacho>.

Si modificas el servicio y lo despliegas, publica tus cambios y apunta `SOURCE_URL` a tu fork.
