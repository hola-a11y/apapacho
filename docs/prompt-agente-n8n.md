# Prompt para el agente que construye el workflow de n8n

Copia todo lo que hay debajo de la línea y pégaselo a un agente que tenga acceso a tu n8n
(por ejemplo Claude Code ejecutándose en el VPS, o un agente con el conector de n8n).
Antes de pegarlo, sustituye los valores entre `<...>`.

---

Necesito que construyas y publiques un workflow en mi n8n. Todo lo de abajo ya existe y
funciona; tu trabajo es solo el workflow y conectar el formulario HTML.

## Lo que ya existe (no lo cambies)

- n8n 2.21.7 autoalojado en Docker, detrás de Traefik, en `https://<subdominio.midominio.com>`.
  Su docker-compose está en `/docker/n8n/docker-compose.yml`. No lo modifiques.
- El microservicio **apapacho** corre en el mismo servidor y n8n lo alcanza por la red interna
  de Docker en `http://apapacho:8000`. No es accesible desde Internet y no debe serlo.
- En n8n ya hay una credencial de tipo **Header Auth** llamada `Apapachoapp`, con el header
  `X-API-Key`. Úsala; no crees otra ni copies la clave en ningún sitio.
- El formulario HTML está en el repo `hola-a11y/apapacho`, archivo `web/formulario.html`.

## API de apapacho

`POST http://apapacho:8000/carta/completa` con header `X-API-Key` (la credencial) y cuerpo JSON:

```json
{ "year": 1990, "month": 7, "day": 15, "hour": 14, "minute": 30, "lat": 40.4168, "lng": -3.7038 }
```

- `hour` y `minute` pueden ser `null` si no se conoce la hora. Nunca `""` ni `0` en su lugar.
- `lat` y `lng` deben ser números, no texto.
- Respuesta 200: `sol`, `luna`, `ascendente`, `hora_exacta`, `luna_puede_variar`, y además
  `planetas`, `angulos`, `casas`, `elementos`, `modalidades` y `fase_lunar`. El formulario usa
  todos esos campos: devuélvelos tal cual, sin filtrar.
- Errores: 401 clave incorrecta, 422 datos inválidos, 429 más de 30 peticiones por minuto.

## Lo que envía el formulario

`POST` con `Content-Type: application/json`:

```json
{ "ciudad": "Madrid", "fecha": "1990-07-15", "hora": "14:30", "website": "" }
```

- `hora` es `"HH:MM"` o `null`.
- `website` es un campo trampa para bots: si viene con texto, la petición es spam.

## El workflow que tienes que construir

Nombre: `Apapacho - Carta`.

1. **Webhook**: método `POST`, path `apapacho`, Respond = `Using 'Respond to Webhook' Node`.
   En Options, **Allowed Origins (CORS)** = `<https://dominio-donde-alojo-el-formulario>`.
2. **IF "Datos válidos"**: `body.ciudad` no vacío, `body.fecha` cumple `^\d{4}-\d{2}-\d{2}$`
   y `body.website` vacío.
   - Si no: **Respond to Webhook** con código **400** y JSON `{"error":"datos_incompletos"}`.
3. **HTTP Request "Nominatim"**: `GET https://nominatim.openstreetmap.org/search` con query
   `q` = la ciudad, `format` = `json`, `limit` = `1`, y header
   `User-Agent: apapacho/1.0 (<mi correo de contacto>)`. En Options → Response activa
   **Include Response Headers and Status** (respuesta completa), para que una ciudad
   inexistente llegue como `body: []` en un item en vez de cortar el flujo. No uses
   *Always Output Data*: haría que un fallo de conexión parezca una ciudad inexistente.
   En Settings, **On Error** = `Continue (using error output)`.
   - Salida de error: **Respond to Webhook** con código **502** y JSON `{"error":"geocodificacion"}`.
4. **IF "Ciudad encontrada"**: `$json.body[0].lat` existe y no está vacío.
   - Si no: **Respond to Webhook** con código **422** y JSON `{"error":"ciudad_no_encontrada"}`.
5. **HTTP Request "apapacho"**: `POST http://apapacho:8000/carta/completa`, autenticación Generic
   Credential Type, Header Auth, credencial `Apapachoapp`. Body JSON con esta expresión
   (ajusta el nombre del nodo Webhook si es distinto):

   ```
   {{ JSON.stringify({
     year: Number($('Webhook').item.json.body.fecha.split('-')[0]),
     month: Number($('Webhook').item.json.body.fecha.split('-')[1]),
     day: Number($('Webhook').item.json.body.fecha.split('-')[2]),
     hour: $('Webhook').item.json.body.hora ? Number($('Webhook').item.json.body.hora.split(':')[0]) : null,
     minute: $('Webhook').item.json.body.hora ? Number($('Webhook').item.json.body.hora.split(':')[1]) : null,
     lat: Number($json.body[0].lat),
     lng: Number($json.body[0].lon)
   }) }}
   ```

   Ojo: Nominatim devuelve `lon`, apapacho espera `lng`.
   En Settings, **On Error** = `Continue (using error output)`.
   - Salida de error: **Respond to Webhook** con código **502** y JSON `{"error":"calculo"}`.
   - Salida correcta: **Respond to Webhook** con código **200** y el JSON de apapacho tal cual
     (`First Incoming Item`).

## Privacidad (obligatorio)

- No guardes los datos de nacimiento en ningún sitio: nada de Google Sheets, bases de datos,
  correos ni logs, salvo que yo lo pida expresamente.
- En **Workflow Settings**, pon *Save successful production executions* y *Save failed
  production executions* en **Do not save**, para que n8n no almacene fechas ni ciudades.
- La clave de apapacho no puede aparecer nunca en el HTML ni en el workflow en texto plano.

## Pruebas antes de darlo por terminado

Publica o activa el workflow y prueba la URL de producción
(`https://<subdominio.midominio.com>/webhook/apapacho`):

| Caso | Cuerpo | Esperado |
|---|---|---|
| Con hora | `{"ciudad":"Madrid","fecha":"1990-07-15","hora":"14:30","website":""}` | 200, Cáncer, Aries, Libra |
| Sin hora | `{"ciudad":"Madrid","fecha":"1990-07-11","hora":null,"website":""}` | 200, `ascendente` null, `luna_puede_variar` true |
| Ciudad inexistente | `{"ciudad":"Xqzwvlandia","fecha":"1990-07-15","hora":null,"website":""}` | 422, `ciudad_no_encontrada` |
| Bot | `{"ciudad":"Madrid","fecha":"1990-07-15","hora":null,"website":"spam"}` | 400, `datos_incompletos` |
| Sin fecha | `{"ciudad":"Madrid","hora":null,"website":""}` | 400, `datos_incompletos` |

Comprueba también la cabecera CORS con una petición `OPTIONS` desde el origen del formulario.

## Formulario

En `web/formulario.html` cambia **solo** la constante `WEBHOOK_URL` por la URL de producción.
No cambies los nombres de los campos ni los códigos de error, porque el formulario depende de
ellos. Si cambias el diseño, mantén las etiquetas, el foco visible y los mensajes con
`role="alert"`: el formulario es accesible y debe seguir siéndolo.

## Al terminar, dime

- La URL de producción del webhook.
- El resultado de cada caso de prueba.
- Cualquier cosa que no hayas podido hacer y por qué.
