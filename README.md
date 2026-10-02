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

### Carta completa

`POST /carta/completa` recibe exactamente la misma entrada y devuelve los mismos cinco campos
que `/carta`, más la carta natal completa:

| Campo | Contenido |
|---|---|
| `planetas` | Sol a Plutón, Nodo Norte verdadero y Quirón. Cada uno con `clave`, `nombre`, `signo`, `grado` (0-30 dentro del signo), `grado_texto` (`"22°46′"`), `casa` (1-12), `retrogrado` y `puede_variar`. |
| `angulos` | `ascendente` y `medio_cielo`, con signo y grado. |
| `casas` | Las 12 cúspides Placidus, con signo y grado. |
| `elementos` | Recuento de fuego, tierra, aire y agua. |
| `modalidades` | Recuento de cardinal, fijo y mutable. |
| `fase_lunar` | `nombre` (Luna nueva ... Luna menguante), `angulo` Luna-Sol e `iluminacion` en %. |
| `aspectos` | Aspectos mayores, ordenados por orbe: `a`, `b`, `tipo`, `armonico`, `angulo`, `orbe`, `orbe_texto`, `aplicativo` y `puede_variar`. |
| `rueda_svg` | La rueda zodiacal en SVG, como texto. La misma que devuelve `/carta/rueda.svg`. |

Cada planeta, ángulo y casa trae además `longitud`, de 0 a 360 (0 = 0° Aries).

Elementos y modalidades cuentan los diez planetas de Sol a Plutón, más el ascendente si hay
hora. Nodo Norte y Quirón no cuentan.

**Aspectos**: conjunción (0°), sextil (60°), cuadratura (90°), trígono (120°) y oposición
(180°), entre los diez planetas, más Ascendente y Medio Cielo si hay hora. Orbe de 8°, o 6° en
el sextil, ampliado 2° si interviene el Sol o la Luna. `aplicativo` indica si el aspecto se está
formando, según la velocidad de cada punto. Ascendente con Medio Cielo no cuenta como aspecto.

**Sin hora**: todo se calcula a las 12:00 locales. `angulos`, `casas` y la `casa` de cada
planeta son `null`, y cada planeta marca `puede_variar: true` si cambia de signo ese día. Un
aspecto marca `puede_variar: true` si no se mantiene, con el mismo tipo, a las 00:00 y a las 23:59.

### Rueda zodiacal

`POST /carta/rueda.svg` recibe la misma entrada y devuelve `image/svg+xml`: la rueda con signos,
casas, planetas, grados, retrogradaciones y líneas de aspecto. El Ascendente queda a la
izquierda. Sin hora, la rueda no tiene casas y 0° Aries queda a la izquierda.

El SVG no lleva scripts, fuentes externas, imágenes ni enlaces, así que se puede incrustar en un
correo. Incluye `<title>` y `<desc>` con la carta en texto, para lectores de pantalla. Los
símbolos usan las fuentes del sistema de quien lo abre.

Colores: fondo `#0f1829`, líneas `#c9a15e`, texto `#f6f1e7`, fuego `#f0a07a`, tierra `#b8cf8f`,
aire `#9fc6ef` y agua `#8fb3e8`. Aspectos armónicos en azul, tensos en naranja, sextiles con
línea discontinua. Las conjunciones no se dibujan porque los puntos coinciden.

### Revolución solar

`POST /revolucion-solar` recibe los datos de nacimiento, **con hora obligatoria**, más:

```json
{ "anio": 2026, "lat_actual": 19.4326, "lng_actual": -99.1332 }
```

`lat_actual` y `lng_actual` son el lugar donde se pasa el cumpleaños. Son opcionales, pero van
juntas; si se omiten se usa el lugar de nacimiento. Calcula el instante exacto en que el Sol
vuelve a su longitud natal durante `anio` (en UTC) y devuelve la carta completa de ese
instante, con rueda incluida, más `anio`, `momento_utc`, `momento_local`, `zona_horaria` y
`sol_natal`.

Sin hora de nacimiento responde 422: el Sol natal tendría medio grado de incertidumbre y el
momento de la revolución, doce horas, así que ascendente y casas no servirían.

### Sinastría

`POST /sinastria` recibe dos personas con el mismo formato que `/carta`:

```json
{ "persona_a": { "year": 1990, "month": 7, "day": 15, "hour": 14, "minute": 30, "lat": 40.4168, "lng": -3.7038 },
  "persona_b": { "year": 1988, "month": 3, "day": 2, "lat": 19.4326, "lng": -99.1332 } }
```

Devuelve el resumen de cada persona (`sol`, `luna`, `ascendente`...), los `aspectos` entre las
dos cartas ordenados por orbe, una `puntuacion` de 0 a 100 y un `resumen` con el número de
aspectos armónicos, tensos y conjunciones. En cada aspecto, `a` es el punto de la persona A y
`b` el de la persona B.

Puntos: los diez planetas de cada persona, más su Ascendente si tiene hora. Orbes 2° más
estrechos que en la carta natal: 6°, o 4° en el sextil, y 8° si interviene el Sol o la Luna.

**Cómo se calcula la puntuación.** Cada aspecto suma o resta:

```
peso = tipo × importancia × (0,5 + 0,5 × exactitud) × (0,5 si puede_variar)
```

- **tipo**: trígono +3, sextil +2, cuadratura −2, oposición −1,5. Conjunción +2,5 si une dos
  puntos de {Sol, Luna, Venus, Júpiter, Ascendente}, −1,5 si interviene Saturno o Plutón, y +1
  en el resto.
- **importancia**: media de los dos puntos. Sol, Luna, Venus, Marte y Ascendente valen 1,5.
  Mercurio, Júpiter y Saturno, 1. Urano, Neptuno y Plutón, 0,5.
- **exactitud**: 1 con el aspecto exacto y 0 en el límite del orbe.
- **Aspectos generacionales**, entre Urano, Neptuno y Plutón de ambas personas, pesan 0: los
  comparte toda la gente de edad parecida.

La suma bruta se convierte a 0-100 con `50 + 50 × tanh((bruto − 13,5) / 21)`. Las constantes se
calibraron con 400 parejas aleatorias nacidas entre 1950 y 2005: la pareja mediana obtiene 50,
el 10 % con menos afinidad unos 21 y el 10 % con más, unos 80. Es un indicador orientativo para
un uso lúdico. Cada aspecto trae su `peso`, así que la puntuación se puede auditar.

Otros endpoints:

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/` | no | Nombre, licencia y enlace al código fuente (oferta AGPL) |
| GET | `/health` | no | `{"status": "ok"}` |
| GET | `/docs` | no | OpenAPI / Swagger |
| POST | `/carta` | `X-API-Key` | Sol, Luna y Ascendente |
| POST | `/carta/completa` | `X-API-Key` | Carta natal completa |
| POST | `/carta/rueda.svg` | `X-API-Key` | Rueda zodiacal en SVG |
| POST | `/revolucion-solar` | `X-API-Key` | Carta del cumpleaños de un año |
| POST | `/sinastria` | `X-API-Key` | Aspectos y afinidad entre dos cartas |

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
histórico (Ciudad de México 2010 vs 2024, Madrid 1950 vs 1990), que los logs no contienen
datos de nacimiento, la carta completa con valores conocidos de julio de 1990, los aspectos y
sus orbes, que la rueda SVG es válida y no contiene scripts ni recursos externos, la revolución
solar (incluido quien nació un 29 de febrero) y la sinastría (simetría, pesos y caso sin hora).

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
fecha y hora a un webhook de n8n y muestra Sol, Luna y Ascendente con sus símbolos. Si la
respuesta trae la carta completa, muestra también la rueda, planetas, aspectos, ángulos,
elementos, modalidades y fase lunar. Cambia `WEBHOOK_URL` dentro
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
