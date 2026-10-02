# Prompt para el agente del formulario

Copia todo lo que hay debajo de la línea y pégaselo al agente que diseñó el formulario.
Sustituye antes los valores entre `<...>`.

---

Ya tienes la estructura y el diseño del formulario de Apapacho. El backend está terminado y
desplegado. Tu trabajo es conectar tu diseño a ese backend siguiendo este contrato, sin cambiar
el backend.

Hay tres funciones, cada una con su webhook de n8n:

| Función | Webhook |
|---|---|
| Carta natal | `https://<subdominio.midominio.com>/webhook/apapacho` |
| Compatibilidad (sinastría) | `https://<subdominio.midominio.com>/webhook/apapacho-compatibilidad` |
| Revolución solar | `https://<subdominio.midominio.com>/webhook/apapacho-revolucion` |

Las tres funcionan igual: el formulario envía JSON por POST, sin claves, y recibe JSON. Lo que
se explica abajo para la carta natal (campo trampa, errores, cómo mostrar la rueda,
accesibilidad) vale también para las otras dos.

## Cómo funciona por detrás

```
Navegador (tu formulario)
   │  POST JSON: ciudad, fecha, hora
   ▼
n8n  https://<subdominio.midominio.com>/webhook/apapacho
   │  1. valida los datos y descarta bots
   │  2. Nominatim: ciudad → latitud y longitud
   │  3. apapacho: calcula la carta (Swiss Ephemeris)
   ▼
Respuesta JSON con la carta completa
```

- El formulario **solo habla con el webhook de n8n**. Nunca llama a apapacho directamente:
  apapacho no es accesible desde Internet.
- **No hay API key en el frontend.** La clave de apapacho la guarda n8n. No añadas cabeceras
  de autenticación ni pidas ninguna clave.
- n8n solo acepta peticiones del origen configurado en su CORS (*Allowed Origins*). Si pruebas
  desde otro dominio o desde `localhost`, el navegador bloqueará la respuesta. Dímelo y
  ajustamos el origen.
- No se guarda nada: ni n8n ni apapacho almacenan los datos de nacimiento. Puedes decirlo en
  el formulario.

Hay una implementación de referencia, ya probada, en el repo `hola-a11y/apapacho`, archivo
`web/formulario.html`. Úsala para ver cómo se interpreta cada campo, pero el diseño es el tuyo.

## Petición

`POST https://<subdominio.midominio.com>/webhook/apapacho` con `Content-Type: application/json`:

```json
{ "ciudad": "Madrid", "fecha": "1990-07-15", "hora": "14:30", "website": "" }
```

| Campo | Formato | Notas |
|---|---|---|
| `ciudad` | texto | Obligatorio. Sugiere añadir el país si el nombre se repite ("Valencia, Venezuela"). |
| `fecha` | `AAAA-MM-DD` | Obligatorio. Lo que da `<input type="date">`. Entre 1900 y 2100. |
| `hora` | `HH:MM` en 24 h, o `null` | Lo que da `<input type="time">`. Hora local del lugar de nacimiento, sin convertir. Si la persona no la sabe, envía `null`, nunca `""` ni `"00:00"`. |
| `website` | texto vacío | **Campo trampa para bots.** Inclúyelo como input oculto (fuera de pantalla, `aria-hidden="true"`, `tabindex="-1"`, `autocomplete="off"`) y envíalo siempre. Si llega con texto, n8n rechaza la petición. |

Recomendación: además del campo de hora, pon una casilla "No sé mi hora de nacimiento" que
desactive el campo y envíe `hora: null`. Sin hora no hay ascendente, ni casas, ni ángulos.

## Respuesta correcta (200)

Ejemplo real para Madrid, 15/07/1990, 14:30, recortado donde indica `"..."`:

```json
{
  "sol": "Cáncer",
  "luna": "Aries",
  "ascendente": "Libra",
  "hora_exacta": true,
  "luna_puede_variar": false,
  "planetas": [
    {
      "longitud": 112.77,
      "signo": "Cáncer",
      "grado": 22.77,
      "grado_texto": "22°46′",
      "clave": "sol",
      "nombre": "Sol",
      "casa": 9,
      "retrogrado": false,
      "puede_variar": false
    },
    {
      "longitud": 23.55,
      "signo": "Aries",
      "grado": 23.55,
      "grado_texto": "23°33′",
      "clave": "luna",
      "nombre": "Luna",
      "casa": 7,
      "retrogrado": false,
      "puede_variar": false
    },
    {
      "...": "10 más: mercurio, venus, marte, jupiter, saturno, urano, neptuno, pluton, nodo_norte, quiron"
    }
  ],
  "angulos": {
    "ascendente": {
      "longitud": 201.36,
      "signo": "Libra",
      "grado": 21.36,
      "grado_texto": "21°21′"
    },
    "medio_cielo": {
      "longitud": 114.96,
      "signo": "Cáncer",
      "grado": 24.96,
      "grado_texto": "24°57′"
    }
  },
  "casas": [
    {
      "longitud": 201.36,
      "signo": "Libra",
      "grado": 21.36,
      "grado_texto": "21°21′",
      "numero": 1
    },
    {
      "...": "11 más, de la 2 a la 12"
    }
  ],
  "elementos": {
    "fuego": 2,
    "tierra": 4,
    "aire": 2,
    "agua": 3
  },
  "modalidades": {
    "cardinal": 7,
    "fijo": 3,
    "mutable": 1
  },
  "fase_lunar": {
    "nombre": "Cuarto menguante",
    "angulo": 270.78,
    "iluminacion": 49.3
  },
  "aspectos": [
    {
      "a": "Sol",
      "b": "Júpiter",
      "tipo": "conjunción",
      "armonico": null,
      "angulo": 0.21,
      "orbe": 0.21,
      "orbe_texto": "0°13′",
      "aplicativo": false,
      "puede_variar": false
    },
    {
      "a": "Júpiter",
      "b": "Saturno",
      "tipo": "oposición",
      "armonico": false,
      "angulo": 179.41,
      "orbe": 0.59,
      "orbe_texto": "0°36′",
      "aplicativo": false,
      "puede_variar": false
    },
    {
      "...": "24 más, ordenados por orbe"
    }
  ],
  "rueda_svg": "<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 600 600\" ...>...</svg>"
}
```

### Qué significa cada campo

**Los tres grandes** (siempre presentes):

- `sol`, `luna`, `ascendente`: nombre del signo en español con acentos (Aries, Tauro, Géminis,
  Cáncer, Leo, Virgo, Libra, Escorpio, Sagitario, Capricornio, Acuario, Piscis).
  `ascendente` es `null` sin hora.
- `hora_exacta`: `false` si se envió `hora: null`.
- `luna_puede_variar`: `true` si, sin hora, la Luna cambió de signo ese día. Muestra un aviso:
  "Sin la hora exacta, la Luna podría estar en el signo contiguo".

**Carta completa:**

- `planetas`: siempre 12, en este orden: sol, luna, mercurio, venus, marte, jupiter, saturno,
  urano, neptuno, pluton, nodo_norte, quiron. Usa `clave` para identificarlos y `nombre` para
  mostrarlos.
  - `signo`, `grado` (0-30 dentro del signo), `grado_texto` ("22°46′", listo para mostrar),
    `longitud` (0-360, por si lo necesitas para dibujar).
  - `casa`: 1-12, o `null` sin hora.
  - `retrogrado`: muéstralo con "℞" y explica el símbolo en una leyenda.
  - `puede_variar`: solo sin hora; `true` si ese punto cambió de signo ese día. Márcalo (por
    ejemplo con "*") y explica la marca.
- `angulos`: `ascendente` y `medio_cielo` con signo y grado. `null` sin hora.
- `casas`: 12 cúspides, `numero` 1-12. `null` sin hora. La 1 coincide con el ascendente y la 10
  con el medio cielo.
- `elementos`: recuento de fuego, tierra, aire y agua. `modalidades`: cardinal, fijo y mutable.
  Cuentan los 10 planetas (Sol a Plutón) más el ascendente si hay hora: suman 11 con hora y 10
  sin ella.
- `fase_lunar`: `nombre` (Luna nueva, Luna creciente, Cuarto creciente, Gibosa creciente, Luna
  llena, Gibosa menguante, Cuarto menguante, Luna menguante) e `iluminacion` en porcentaje (0-100).
- `aspectos`: ordenados del más exacto al menos exacto. Suelen ser entre 15 y 30.
  - `a`, `b`: nombres en español (también pueden ser "Ascendente" o "Medio Cielo").
  - `tipo`: conjunción, sextil, cuadratura, trígono u oposición.
  - `armonico`: `true` (trígono, sextil), `false` (cuadratura, oposición), `null` (conjunción).
  - `orbe_texto`: distancia al aspecto exacto, lista para mostrar ("0°13′").
  - `aplicativo`: `true` si se está formando, `false` si se deshace.
  - `puede_variar`: solo sin hora; `true` si ese aspecto podría no darse ese día.
  Recomendación: muestra los 8 primeros y el resto en un `<details>`.
- `rueda_svg`: la rueda zodiacal completa como texto SVG, de 600×600 y ya con la paleta
  Apapacho Astral (fondo `#0f1829`, líneas `#c9a15e`, texto `#f6f1e7`, fuego `#f0a07a`, tierra
  `#b8cf8f`, aire `#9fc6ef`, agua `#8fb3e8`). Ascendente a la izquierda; sin hora, sin casas y
  con 0° Aries a la izquierda.

### Cómo mostrar la rueda (obligatorio hacerlo así)

Muéstrala como imagen con una data URL. **No la insertes con `innerHTML`**: como `<img>`, el
navegador nunca ejecuta nada de dentro del SVG.

```js
if (typeof datos.rueda_svg === "string" && datos.rueda_svg.startsWith("<svg")) {
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(datos.rueda_svg);
  img.alt = "Rueda zodiacal de tu carta natal. Los mismos datos aparecen en las tablas siguientes.";
}
```

Ponle `width: 100%; height: auto`: es vectorial y escala sin perder calidad.

### Pinta los datos con `textContent`

Construye el HTML del resultado con `createElement` y `textContent`, nunca concatenando la
respuesta en `innerHTML`.

## Errores

| HTTP | Cuerpo | Qué mostrar |
|---|---|---|
| 400 | `{"error":"datos_incompletos"}` | "Faltan datos. Revisa la ciudad y la fecha." |
| 422 | `{"error":"ciudad_no_encontrada"}` | "No encontramos esa ciudad. Revisa cómo está escrita o añade el país." Lleva el foco al campo ciudad. |
| 502 | `{"error":"geocodificacion"}` | "No hemos podido localizar la ciudad ahora. Inténtalo en un minuto." |
| 502 | `{"error":"calculo"}` | "No hemos podido hacer el cálculo. Revisa la fecha y la hora." (p. ej. 30 de febrero). |
| 200 sin `sol` | vacío o inesperado | Mensaje genérico de "inténtalo de nuevo". |
| fallo de red | — | "No hay conexión con el servidor." |

Comprueba siempre que la respuesta 200 trae `sol` antes de pintar nada.

El servicio admite 30 cálculos por minuto en total. Desactiva el botón mientras se calcula
para evitar envíos dobles.

## Accesibilidad (el proyecto se llama hola-a11y: no es opcional)

- Cada campo con su `<label>`; ayudas con `aria-describedby`.
- Errores en un contenedor con `role="alert"`, y el foco al campo que falla con
  `aria-invalid="true"`.
- Al mostrar el resultado, mueve el foco a su encabezado o sección (`tabindex="-1"`).
- Botón con `aria-busy="true"` mientras calcula.
- Los símbolos de signos y planetas (♋, ☉...) son decorativos: `aria-hidden="true"` y el
  nombre siempre en texto. Añade el selector de variación `\uFE0E` tras el símbolo para que
  no se pinte como emoji.
- No transmitas información solo con color: armónico y tenso, también con texto.
- Contraste suficiente en modo claro y oscuro; foco visible; nada de scroll horizontal a 375 px.
- Respeta `prefers-reduced-motion` si animas algo.

## Compatibilidad (sinastría)

`POST https://<subdominio.midominio.com>/webhook/apapacho-compatibilidad`:

```json
{ "persona_a": { "ciudad": "Madrid", "fecha": "1990-07-15", "hora": "14:30" },
  "persona_b": { "ciudad": "Ciudad de México", "fecha": "1988-03-02", "hora": null },
  "website": "" }
```

Cada persona lleva ciudad, fecha y hora con las mismas reglas que la carta natal. La hora de
cada una es opcional por separado. Un solo campo trampa `website`, fuera de las personas.

Respuesta 200 (ejemplo real, recortado):

```json
{
  "persona_a": {
    "sol": "Cáncer",
    "luna": "Aries",
    "ascendente": "Libra",
    "hora_exacta": true,
    "luna_puede_variar": false
  },
  "persona_b": {
    "sol": "Piscis",
    "luna": "Virgo",
    "ascendente": "Aries",
    "hora_exacta": true,
    "luna_puede_variar": false
  },
  "aspectos": [
    {
      "a": "Marte",
      "b": "Saturno",
      "tipo": "trígono",
      "armonico": true,
      "angulo": 120.66,
      "orbe": 0.66,
      "orbe_texto": "0°40′",
      "puede_variar": false,
      "generacional": false,
      "peso": 3.54
    },
    {
      "a": "Plutón",
      "b": "Mercurio",
      "tipo": "cuadratura",
      "armonico": false,
      "angulo": 90.66,
      "orbe": 0.66,
      "orbe_texto": "0°40′",
      "puede_variar": false,
      "generacional": false,
      "peso": -1.42
    },
    {
      "...": "28 más, ordenados por orbe"
    }
  ],
  "puntuacion": 80,
  "resumen": {
    "armonicos": 15,
    "tensos": 8,
    "conjunciones": 8,
    "puntuacion_bruta": 28.03
  }
}
```

- `persona_a` y `persona_b`: los tres grandes de cada persona, como en la carta natal.
- `puntuacion`: afinidad de 0 a 100. **50 es una pareja típica**; el 10 % con más afinidad
  supera 80 y el 10 % con menos queda por debajo de 21. Es un indicador lúdico: dilo en la
  interfaz, por ejemplo "orientativo, para disfrutar".
- `aspectos`: entre un punto de A (`a`) y uno de B (`b`), ordenados del más exacto al menos
  exacto. Muéstralos como "Marte de A trígono Saturno de B". Si quieres poner nombres,
  pídelos en el formulario y úsalos solo en el navegador: **no los envíes**, el webhook no
  los necesita y rechaza campos que no conoce en cada persona.
  - `peso`: cuánto suma (positivo) o resta (negativo) a la puntuación. Útil para destacar los
    aspectos que más pesan.
  - `generacional: true`: aspecto entre Urano, Neptuno o Plutón de ambas personas. No cuenta
    en la puntuación; puedes ocultarlos o mostrarlos atenuados.
  - `puede_variar: true`: alguna de las dos no dio hora y el aspecto podría no darse.
- `resumen`: número de aspectos armónicos, tensos y conjunciones.
- No incluye rueda.

Errores: los mismos que en la carta natal, salvo que `ciudad_no_encontrada` indica de quién:

```json
{ "error": "ciudad_no_encontrada", "campo": "persona_a" }
```

`campo` es `persona_a` o `persona_b`: lleva el foco a la ciudad de esa persona.

## Revolución solar

`POST https://<subdominio.midominio.com>/webhook/apapacho-revolucion`:

```json
{ "ciudad": "Madrid", "fecha": "1990-07-15", "hora": "14:30",
  "anio": 2026, "ciudad_actual": "Ciudad de México", "website": "" }
```

| Campo | Notas |
|---|---|
| `ciudad`, `fecha` | De nacimiento, como en la carta natal. |
| `hora` | **Obligatoria** (`HH:MM`). Sin hora no se puede calcular: no ofrezcas la casilla "No sé mi hora" aquí; explica por qué. |
| `anio` | Año del cumpleaños, número o texto de 4 cifras. Entre el año de nacimiento y 2100. Por defecto, el año en curso. |
| `ciudad_actual` | Opcional. Dónde pasará (o pasó) ese cumpleaños. Vacío o ausente = la ciudad de nacimiento. Explícalo: la revolución cambia según el lugar. |

Respuesta 200 (ejemplo real, recortado): la **misma estructura que la carta natal completa**,
rueda incluida, más estos campos:

```json
{
  "sol": "Cáncer",
  "luna": "Leo",
  "ascendente": "Aries",
  "hora_exacta": true,
  "luna_puede_variar": false,
  "...": "planetas, angulos, casas, elementos, modalidades, fase_lunar, aspectos y rueda_svg: igual que en la carta natal",
  "anio": 2026,
  "momento_utc": "2026-07-15T05:19:55+00:00",
  "momento_local": "2026-07-14T23:19:55-06:00",
  "zona_horaria": "America/Mexico_City",
  "sol_natal": {
    "longitud": 112.77,
    "signo": "Cáncer",
    "grado": 22.77,
    "grado_texto": "22°46′"
  }
}
```

- `momento_local`: cuándo ocurre la revolución en la hora del lugar. Muéstralo en lenguaje
  natural ("14 de julio de 2026, 23:19"). Fíjate en que puede caer el día antes o después del
  cumpleaños.
- `sol_natal`: posición del Sol al nacer; el Sol de la revolución está en el mismo grado.
- Todo lo demás (planetas, casas, aspectos, rueda...) se pinta igual que en la carta natal:
  reutiliza los mismos componentes.

Errores: los mismos que en la carta natal, más:

- `400 datos_incompletos` también cuando falta la hora o el año es anterior al nacimiento o
  posterior a 2100. Valídalo antes de enviar para dar un mensaje concreto.
- `422 ciudad_no_encontrada` con `"campo": "ciudad"` o `"campo": "ciudad_actual"`.

## Pruebas antes de darlo por terminado

| Caso | Datos | Esperado |
|---|---|---|
| Con hora | Madrid, 1990-07-15, 14:30 | Sol Cáncer, Luna Aries, Asc Libra; rueda, 12 planetas, 12 casas, unos 26 aspectos; fase Cuarto menguante |
| Sin hora | Madrid, 1990-07-11, sin hora | Asc "sin hora"; aviso de Luna; sin casas ni columna de casa; algún "*" |
| Ciudad inexistente | Xqzwvlandia | Mensaje de ciudad no encontrada y foco en el campo |
| Fecha imposible | 1990-02-30 | Mensaje de cálculo (si el navegador deja enviarla) |
| Móvil | 375 px de ancho | Sin scroll horizontal; tabla y rueda legibles |
| Teclado y lector | Solo teclado | Se puede rellenar, enviar y leer el resultado |
| Compatibilidad | A: Madrid, 1990-07-15, 14:30. B: Ciudad de México, 1988-03-02, 08:10 | Puntuación 80, A Cáncer/Aries/Libra, B Piscis/Virgo/Aries |
| Compatibilidad sin hora | La misma, con B sin hora | Puntuación 72, B sin ascendente, algún aspecto marcado como variable |
| Compatibilidad, ciudad falsa | B en "Xqzwvlandia" | Mensaje de ciudad no encontrada y foco en la ciudad de B |
| Revolución solar | Madrid, 1990-07-15, 14:30, año 2026, sin ciudad actual | 15/07/2026 07:19 (Madrid), Asc Cáncer, con rueda |
| Revolución en otra ciudad | Igual, con ciudad actual "Ciudad de México" | 14/07/2026 23:19 (hora de México), Asc Aries |
| Revolución sin hora | Sin hora | El formulario no deja enviar y lo explica |

## Al terminar, dime

- Dónde está publicado el formulario (dominio exacto, para configurar CORS en los tres
  webhooks de n8n).
- El resultado de cada prueba.
- Cualquier dato que tu diseño necesite y la respuesta no traiga.
