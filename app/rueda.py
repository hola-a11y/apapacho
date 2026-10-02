"""Rueda zodiacal en SVG, generada a mano a partir de la carta completa.

- Sin scripts, sin fuentes externas, sin imágenes ni enlaces: apta para incrustar en un correo.
- Ascendente a la izquierda. Sin hora: 0° Aries a la izquierda y sin casas.
- Accesible: role="img" con <title> y <desc> que resumen la carta en texto.
"""

from __future__ import annotations

import math
from xml.sax.saxutils import escape

from app.service import SIGNOS_ES

# Paleta "Apapacho Astral"
FONDO = "#0f1829"
LINEAS = "#c9a15e"
TEXTO = "#f6f1e7"
COLOR_ELEMENTO = ("#f0a07a", "#b8cf8f", "#9fc6ef", "#8fb3e8")  # fuego, tierra, aire, agua
COLOR_ARMONICO = "#9fc6ef"
COLOR_TENSO = "#f0a07a"

VS_TEXTO = "︎"  # fuerza el glifo como texto, no como emoji
GLIFOS_SIGNO = tuple(chr(0x2648 + i) + VS_TEXTO for i in range(12))
GLIFOS_PLANETA = {
    "sol": "☉", "luna": "☽", "mercurio": "☿", "venus": "♀", "marte": "♂",
    "jupiter": "♃", "saturno": "♄", "urano": "♅", "neptuno": "♆", "pluton": "♇",
    "nodo_norte": "☊", "quiron": "⚷",
}

TAM = 600
C = TAM / 2
R_EXT = 292      # borde exterior del anillo zodiacal
R_ZOD = 250      # borde interior del anillo zodiacal
R_CASAS = 216    # borde interior del anillo de casas
R_PLANETA = 186  # radio de los glifos de planetas
R_GRADO = 163    # radio del texto de grado
R_ASP = 128      # círculo de aspectos
SEPARACION_MIN = 8.5  # grados mínimos entre glifos de planetas en pantalla

FUENTE = "'DejaVu Sans','Segoe UI Symbol','Noto Sans Symbols 2','Apple Symbols',Arial,sans-serif"


def _f(x: float) -> str:
    return f"{x:.2f}".rstrip("0").rstrip(".")


class _Lienzo:
    def __init__(self, referencia: float) -> None:
        self.referencia = referencia  # longitud que queda a la izquierda (Ascendente)

    def angulo(self, lon: float) -> float:
        """Ángulo en pantalla (radianes, antihorario desde la derecha)."""
        return math.radians(180 + lon - self.referencia)

    def xy(self, lon: float, r: float) -> tuple[float, float]:
        a = self.angulo(lon)
        return C + r * math.cos(a), C - r * math.sin(a)


def _sector(l: _Lienzo, lon0: float, lon1: float, r_ext: float, r_int: float) -> str:
    x0, y0 = l.xy(lon0, r_ext)
    x1, y1 = l.xy(lon1, r_ext)
    x2, y2 = l.xy(lon1, r_int)
    x3, y3 = l.xy(lon0, r_int)
    grande = 1 if (lon1 - lon0) % 360 > 180 else 0
    # Longitud creciente = sentido antihorario en pantalla = sweep 0 en SVG.
    return (f"M{_f(x0)} {_f(y0)}A{r_ext} {r_ext} 0 {grande} 0 {_f(x1)} {_f(y1)}"
            f"L{_f(x2)} {_f(y2)}A{r_int} {r_int} 0 {grande} 1 {_f(x3)} {_f(y3)}Z")


def _linea(l: _Lienzo, lon: float, r0: float, r1: float, color: str, ancho: float, opacidad: float = 1) -> str:
    x0, y0 = l.xy(lon, r0)
    x1, y1 = l.xy(lon, r1)
    op = "" if opacidad >= 1 else f' stroke-opacity="{_f(opacidad)}"'
    return f'<line x1="{_f(x0)}" y1="{_f(y0)}" x2="{_f(x1)}" y2="{_f(y1)}" stroke="{color}" stroke-width="{_f(ancho)}"{op}/>'


def _texto(x: float, y: float, contenido: str, tam: float, color: str, extra: str = "") -> str:
    return (f'<text x="{_f(x)}" y="{_f(y)}" font-size="{_f(tam)}" fill="{color}" text-anchor="middle" '
            f'dominant-baseline="central"{extra}>{escape(contenido)}</text>')


def _repartir(longitudes: list[float], referencia: float) -> list[float]:
    """Separa en pantalla los planetas demasiado juntos, conservando su orden zodiacal."""
    n = len(longitudes)
    if n < 2:
        return list(longitudes)
    # Posiciones relativas a la referencia (0-360) y ordenadas: así no hay salto 360->0.
    orden = sorted(range(n), key=lambda i: (longitudes[i] - referencia) % 360)
    pos = [(longitudes[i] - referencia) % 360 for i in orden]
    for _ in range(500):
        movido = False
        for k in range(n - 1):
            if pos[k + 1] - pos[k] < SEPARACION_MIN - 1e-6:
                medio = (pos[k] + pos[k + 1]) / 2
                pos[k], pos[k + 1] = medio - SEPARACION_MIN / 2, medio + SEPARACION_MIN / 2
                movido = True
        # Par que cruza el punto de referencia (último y primero).
        if pos[0] + 360 - pos[-1] < SEPARACION_MIN - 1e-6:
            medio = (pos[-1] + pos[0] + 360) / 2
            pos[-1], pos[0] = medio - SEPARACION_MIN / 2, medio + SEPARACION_MIN / 2 - 360
            movido = True
        if not movido:
            break
    resultado = [0.0] * n
    for i, p in zip(orden, pos):
        resultado[i] = (p + referencia) % 360
    return resultado


def descripcion(carta: dict) -> str:
    partes = []
    if carta.get("angulos"):
        asc = carta["angulos"]["ascendente"]
        mc = carta["angulos"]["medio_cielo"]
        partes.append(f"Ascendente en {asc['signo']} {asc['grado_texto']}, a la izquierda; "
                      f"Medio Cielo en {mc['signo']} {mc['grado_texto']}.")
    else:
        partes.append("Sin hora de nacimiento: rueda sin casas, con 0° de Aries a la izquierda.")
    planetas = []
    for p in carta["planetas"]:
        texto = f"{p['nombre']} en {p['signo']} {p['grado_texto']}"
        if p.get("casa"):
            texto += f", casa {p['casa']}"
        if p.get("retrogrado"):
            texto += ", retrógrado"
        planetas.append(texto)
    partes.append("; ".join(planetas) + ".")
    dibujados = [a for a in carta.get("aspectos", []) if a["tipo"] != "conjunción"]
    if dibujados:
        partes.append(f"{len(dibujados)} líneas de aspecto: azules las armónicas, naranjas las tensas.")
    return " ".join(partes)


def generar_rueda(carta: dict) -> str:
    """Devuelve el SVG (texto) de la rueda para un resultado de calcular_carta_completa."""
    angulos = carta.get("angulos")
    referencia = angulos["ascendente"]["longitud"] if angulos else 0.0
    l = _Lienzo(referencia)
    p = []  # piezas del SVG

    titulo = (f"Carta natal: Sol en {carta['sol']}, Luna en {carta['luna']}"
              + (f", Ascendente en {carta['ascendente']}" if carta.get("ascendente") else ""))
    p.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {TAM} {TAM}" width="{TAM}" height="{TAM}" '
             f'role="img" aria-labelledby="rueda-titulo rueda-desc" font-family="{FUENTE}">')
    p.append(f'<title id="rueda-titulo">{escape(titulo)}</title>')
    p.append(f'<desc id="rueda-desc">{escape(descripcion(carta))}</desc>')
    p.append(f'<rect width="{TAM}" height="{TAM}" fill="{FONDO}"/>')

    # Anillo zodiacal
    for s in range(12):
        color = COLOR_ELEMENTO[s % 4]
        p.append(f'<path d="{_sector(l, s * 30, s * 30 + 30, R_EXT, R_ZOD)}" fill="{color}" fill-opacity=".14" '
                 f'stroke="{LINEAS}" stroke-width=".8"/>')
        x, y = l.xy(s * 30 + 15, (R_EXT + R_ZOD) / 2)
        p.append(_texto(x, y, GLIFOS_SIGNO[s], 22, color))
    for g in range(0, 360, 5):
        if g % 30:
            largo = 7 if g % 10 == 0 else 4
            p.append(_linea(l, g, R_ZOD, R_ZOD + largo, LINEAS, .6, .8))

    for r in (R_EXT, R_ZOD, R_CASAS, R_ASP):
        p.append(f'<circle cx="{_f(C)}" cy="{_f(C)}" r="{r}" fill="none" stroke="{LINEAS}" stroke-width="1"/>')

    # Casas
    if carta.get("casas"):
        cuspides = [c["longitud"] for c in carta["casas"]]
        for i, lon in enumerate(cuspides):
            eje = i in (0, 3, 6, 9)  # AC, IC, DC, MC
            p.append(_linea(l, lon, R_ASP, R_ZOD, LINEAS, 2.2 if eje else .7, 1 if eje else .55))
            siguiente = cuspides[(i + 1) % 12]
            medio = lon + ((siguiente - lon) % 360) / 2
            x, y = l.xy(medio, (R_ZOD + R_CASAS) / 2)
            p.append(_texto(x, y, str(i + 1), 11, TEXTO, ' fill-opacity=".7"'))
        for nombre, lon in (("AC", cuspides[0]), ("MC", cuspides[9])):
            x, y = l.xy(lon - 4.5, (R_ZOD + R_CASAS) / 2)
            p.append(_texto(x, y, nombre, 10.5, LINEAS, ' font-weight="bold"'))

    # Aspectos (bajo los planetas). La conjunción no se dibuja: los puntos coinciden.
    lon_por_nombre = {pl["nombre"]: pl["longitud"] for pl in carta["planetas"]}
    if angulos:
        lon_por_nombre["Ascendente"] = angulos["ascendente"]["longitud"]
        lon_por_nombre["Medio Cielo"] = angulos["medio_cielo"]["longitud"]
    for a in reversed(carta.get("aspectos", [])):  # los más exactos, encima
        if a["tipo"] == "conjunción":
            continue
        x0, y0 = l.xy(lon_por_nombre[a["a"]], R_ASP)
        x1, y1 = l.xy(lon_por_nombre[a["b"]], R_ASP)
        color = COLOR_ARMONICO if a["armonico"] else COLOR_TENSO
        opacidad = max(.3, 1 - a["orbe"] / 10)
        guion = ' stroke-dasharray="4 3"' if a["tipo"] == "sextil" else ""
        p.append(f'<line x1="{_f(x0)}" y1="{_f(y0)}" x2="{_f(x1)}" y2="{_f(y1)}" stroke="{color}" '
                 f'stroke-width="1.3" stroke-opacity="{_f(opacidad)}"{guion}/>')

    # Planetas
    planetas = carta["planetas"]
    reales = [pl["longitud"] for pl in planetas]
    pantalla = _repartir(reales, referencia)
    for pl, lon, lon_vis in zip(planetas, reales, pantalla):
        p.append(_linea(l, lon, R_CASAS, R_CASAS - 7, TEXTO, 1.4))
        x, y = l.xy(lon, R_ASP)
        p.append(f'<circle cx="{_f(x)}" cy="{_f(y)}" r="2.2" fill="{TEXTO}"/>')
        if abs(((lon_vis - lon + 180) % 360) - 180) > .5:
            x0, y0 = l.xy(lon, R_CASAS - 7)
            x1, y1 = l.xy(lon_vis, R_PLANETA + 13)
            p.append(f'<line x1="{_f(x0)}" y1="{_f(y0)}" x2="{_f(x1)}" y2="{_f(y1)}" stroke="{TEXTO}" '
                     f'stroke-width=".6" stroke-opacity=".6"/>')
        x, y = l.xy(lon_vis, R_PLANETA)
        color = COLOR_ELEMENTO[SIGNOS_ES.index(pl["signo"]) % 4]
        p.append(_texto(x, y, GLIFOS_PLANETA[pl["clave"]] + VS_TEXTO, 20, TEXTO))
        x, y = l.xy(lon_vis, R_GRADO)
        p.append(_texto(x, y, f"{int(pl['grado'])}°", 9.5, color))
        if pl["retrogrado"]:
            x, y = l.xy(lon_vis, R_GRADO - 12)
            p.append(_texto(x, y, "℞", 9.5, color))

    p.append("</svg>")
    return "".join(p)
