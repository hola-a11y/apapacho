"""Cálculo astrológico: Sol, Luna y Ascendente con Kerykeion (Swiss Ephemeris).

Escrito contra la API de kerykeion 5.12.x:
    AstrologicalSubjectFactory.from_birth_data(..., lng=, lat=, tz_str=, online=False)
devuelve un AstrologicalSubjectModel con atributos `sun`, `moon` y `ascendant`,
cada uno con `sign` (abreviatura de 3 letras) y `sign_num` (0 = Aries ... 11 = Piscis).
"""

from __future__ import annotations

import logging
import math
import threading
from dataclasses import dataclass
from typing import Optional

from kerykeion import AstrologicalSubjectFactory, KerykeionException
from timezonefinder import TimezoneFinder

# Kerykeion registra avisos por el logger raíz; no contienen datos de nacimiento,
# pero bajamos el nivel para no ensuciar los logs del servicio.
logging.getLogger("kerykeion").setLevel(logging.ERROR)

SIGNOS_ES: tuple[str, ...] = (
    "Aries",
    "Tauro",
    "Géminis",
    "Cáncer",
    "Leo",
    "Virgo",
    "Libra",
    "Escorpio",
    "Sagitario",
    "Capricornio",
    "Acuario",
    "Piscis",
)

# Hora que se asume para Sol y Luna cuando no se conoce la hora de nacimiento.
HORA_POR_DEFECTO = 12
MINUTO_POR_DEFECTO = 0

# timezonefinder carga sus datos una sola vez; in_memory acelera las consultas.
_tf = TimezoneFinder(in_memory=True)

# pyswisseph mantiene estado global en C; serializamos el acceso para que los
# workers del threadpool de FastAPI no se pisen.
_swe_lock = threading.Lock()


class ZonaHorariaNoEncontrada(ValueError):
    """No se pudo determinar la zona horaria IANA para las coordenadas dadas."""


class HoraInvalida(ValueError):
    """La hora local no se puede convertir a UTC (p. ej. errores internos de DST)."""


@dataclass(frozen=True)
class Posiciones:
    sol_num: int
    luna_num: int
    asc_num: Optional[int]
    utc_iso: str
    local_iso: str
    tz_str: str


@dataclass(frozen=True)
class Carta:
    sol: str
    luna: str
    ascendente: Optional[str]
    hora_exacta: bool
    luna_puede_variar: bool
    zona_horaria: str  # informativo; no se expone en la respuesta HTTP


def zona_horaria(lat: float, lng: float) -> str:
    """Devuelve el nombre IANA (p. ej. 'Europe/Madrid') de la zona horaria de unas coordenadas.

    Para puntos en el mar devuelve zonas 'Etc/GMT±N'. Si no se puede resolver, lanza
    ZonaHorariaNoEncontrada.
    """
    tz = _tf.timezone_at(lat=lat, lng=lng)
    if tz is None:
        raise ZonaHorariaNoEncontrada("No se pudo determinar la zona horaria para esas coordenadas")
    return tz


def _sujeto(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    lat: float,
    lng: float,
    tz_str: str,
    puntos: list[str],
):
    """Crea el AstrologicalSubjectModel de Kerykeion para una fecha/hora local."""
    kwargs = dict(
        name="-",  # Nunca pasamos datos identificativos a la librería.
        year=year,
        month=month,
        day=day,
        hour=hour,
        minute=minute,
        lat=lat,
        lng=lng,
        tz_str=tz_str,
        online=False,  # Sin llamadas a GeoNames: lat/lng y tz vienen dados.
        active_points=puntos,
        calculate_lunar_phase=False,
        suppress_geonames_warning=True,
    )

    with _swe_lock:
        try:
            return AstrologicalSubjectFactory.from_birth_data(**kwargs)
        except KerykeionException as exc:
            # pytz lanza error si la hora local es ambigua (cambio a horario de invierno:
            # la hora ocurre dos veces) o inexistente (cambio a horario de verano: la hora
            # se salta). Resolvemos ambos casos asumiendo horario estándar (is_dst=False),
            # que es el criterio habitual de los programas de astrología.
            texto = str(exc)
            if "Ambiguous" in texto or "Non-existent" in texto:
                return AstrologicalSubjectFactory.from_birth_data(is_dst=False, **kwargs)
            raise HoraInvalida("No se pudo interpretar la hora local") from exc


def _calcular(
    year: int,
    month: int,
    day: int,
    hour: int,
    minute: int,
    lat: float,
    lng: float,
    tz_str: str,
    con_ascendente: bool,
) -> Posiciones:
    puntos = ["Sun", "Moon", "Ascendant"] if con_ascendente else ["Sun", "Moon"]
    subject = _sujeto(year, month, day, hour, minute, lat, lng, tz_str, puntos)

    asc_num = None
    if con_ascendente:
        if subject.ascendant is None:
            raise HoraInvalida("No se pudo calcular el ascendente")
        asc_num = subject.ascendant.sign_num

    return Posiciones(
        sol_num=subject.sun.sign_num,
        luna_num=subject.moon.sign_num,
        asc_num=asc_num,
        utc_iso=subject.iso_formatted_utc_datetime,
        local_iso=subject.iso_formatted_local_datetime,
        tz_str=tz_str,
    )


def calcular_carta(
    year: int,
    month: int,
    day: int,
    lat: float,
    lng: float,
    hour: Optional[int] = None,
    minute: Optional[int] = None,
) -> Carta:
    """Calcula Sol, Luna y Ascendente para unos datos de nacimiento.

    Si `hour` es None: Sol y Luna se calculan a las 12:00 locales, el ascendente es None,
    `hora_exacta` es False y `luna_puede_variar` indica si la Luna cambia de signo entre
    las 00:00 y las 23:59 de ese día.
    """
    tz = zona_horaria(lat, lng)

    if hour is None:
        mediodia = _calcular(year, month, day, HORA_POR_DEFECTO, MINUTO_POR_DEFECTO, lat, lng, tz, False)
        inicio = _calcular(year, month, day, 0, 0, lat, lng, tz, False)
        fin = _calcular(year, month, day, 23, 59, lat, lng, tz, False)
        return Carta(
            sol=SIGNOS_ES[mediodia.sol_num],
            luna=SIGNOS_ES[mediodia.luna_num],
            ascendente=None,
            hora_exacta=False,
            luna_puede_variar=inicio.luna_num != fin.luna_num,
            zona_horaria=tz,
        )

    pos = _calcular(year, month, day, hour, minute or 0, lat, lng, tz, True)
    assert pos.asc_num is not None
    return Carta(
        sol=SIGNOS_ES[pos.sol_num],
        luna=SIGNOS_ES[pos.luna_num],
        ascendente=SIGNOS_ES[pos.asc_num],
        hora_exacta=True,
        luna_puede_variar=False,
        zona_horaria=tz,
    )


# ---------------------------------------------------------------------------
# Carta completa
# ---------------------------------------------------------------------------

# (clave en la API, nombre en español, nombre en Kerykeion, atributo del modelo)
PUNTOS_CARTA: tuple[tuple[str, str, str, str], ...] = (
    ("sol", "Sol", "Sun", "sun"),
    ("luna", "Luna", "Moon", "moon"),
    ("mercurio", "Mercurio", "Mercury", "mercury"),
    ("venus", "Venus", "Venus", "venus"),
    ("marte", "Marte", "Mars", "mars"),
    ("jupiter", "Júpiter", "Jupiter", "jupiter"),
    ("saturno", "Saturno", "Saturn", "saturn"),
    ("urano", "Urano", "Uranus", "uranus"),
    ("neptuno", "Neptuno", "Neptune", "neptune"),
    ("pluton", "Plutón", "Pluto", "pluto"),
    ("nodo_norte", "Nodo Norte", "True_North_Lunar_Node", "true_north_lunar_node"),
    ("quiron", "Quirón", "Chiron", "chiron"),
)

# Solo los diez planetas clásicos (y el ascendente, si hay hora) cuentan para el reparto
# de elementos y modalidades. Nodo Norte y Quirón no.
CLAVES_REPARTO = ("sol", "luna", "mercurio", "venus", "marte", "jupiter", "saturno", "urano", "neptuno", "pluton")

ELEMENTOS = ("fuego", "tierra", "aire", "agua")  # Aries=fuego, Tauro=tierra, Géminis=aire, Cáncer=agua...
MODALIDADES = ("cardinal", "fijo", "mutable")  # Aries=cardinal, Tauro=fijo, Géminis=mutable...

ATRIBUTOS_CASAS = (
    "first_house", "second_house", "third_house", "fourth_house", "fifth_house", "sixth_house",
    "seventh_house", "eighth_house", "ninth_house", "tenth_house", "eleventh_house", "twelfth_house",
)
_NUMERO_CASA = {
    "First_House": 1, "Second_House": 2, "Third_House": 3, "Fourth_House": 4,
    "Fifth_House": 5, "Sixth_House": 6, "Seventh_House": 7, "Eighth_House": 8,
    "Ninth_House": 9, "Tenth_House": 10, "Eleventh_House": 11, "Twelfth_House": 12,
}

FASES_LUNARES = (
    "Luna nueva",
    "Luna creciente",
    "Cuarto creciente",
    "Gibosa creciente",
    "Luna llena",
    "Gibosa menguante",
    "Cuarto menguante",
    "Luna menguante",
)


def grado_texto(grado: float) -> str:
    """22.75 -> "22°45′" (grados y minutos dentro del signo)."""
    total_minutos = int(round(grado * 60))
    g, m = divmod(total_minutos, 60)
    if g >= 30:  # redondeo en el límite del signo
        g, m = 29, 59
    return f"{g}°{m:02d}′"


def fase_lunar(sol_abs: float, luna_abs: float) -> dict:
    """Fase lunar a partir de la elongación Luna-Sol (0° = nueva, 180° = llena)."""
    angulo = (luna_abs - sol_abs) % 360
    indice = int(((angulo + 22.5) % 360) // 45)
    iluminacion = (1 - math.cos(math.radians(angulo))) / 2 * 100
    return {
        "nombre": FASES_LUNARES[indice],
        "angulo": round(angulo, 2),
        "iluminacion": round(iluminacion, 1),
    }


def _signo(sign_num: int, grado: float) -> dict:
    return {
        "longitud": round(sign_num * 30 + grado, 2),
        "signo": SIGNOS_ES[sign_num],
        "grado": round(grado, 2),
        "grado_texto": grado_texto(grado),
    }


# ---------------------------------------------------------------------------
# Aspectos
# ---------------------------------------------------------------------------

# (nombre, ángulo exacto, orbe base, armónico)
TIPOS_ASPECTO: tuple[tuple[str, float, float, Optional[bool]], ...] = (
    ("conjunción", 0.0, 8.0, None),
    ("sextil", 60.0, 6.0, True),
    ("cuadratura", 90.0, 8.0, False),
    ("trígono", 120.0, 8.0, True),
    ("oposición", 180.0, 8.0, False),
)
# Si interviene el Sol o la Luna, el orbe se amplía 2°: 10° (8° en el sextil).
EXTRA_ORBE_LUMINARIA = 2.0
LUMINARIAS = ("Sol", "Luna")
ANGULOS_NOMBRES = ("Ascendente", "Medio Cielo")


def separacion(lon_a: float, lon_b: float) -> float:
    """Distancia angular más corta entre dos longitudes, 0-180."""
    d = (lon_b - lon_a) % 360
    return min(d, 360 - d)


def aspecto_entre(nombre_a: str, lon_a: float, nombre_b: str, lon_b: float) -> Optional[tuple[str, float, float, Optional[bool]]]:
    """Devuelve (tipo, ángulo exacto, orbe, armónico) si hay aspecto mayor dentro de orbe."""
    sep = separacion(lon_a, lon_b)
    luminaria = nombre_a in LUMINARIAS or nombre_b in LUMINARIAS
    for tipo, exacto, orbe_base, armonico in TIPOS_ASPECTO:
        orbe_max = orbe_base + (EXTRA_ORBE_LUMINARIA if luminaria else 0.0)
        orbe = abs(sep - exacto)
        if orbe <= orbe_max:
            return tipo, exacto, orbe, armonico
    return None


def calcular_aspectos(puntos: list[dict], puntos_inicio: Optional[list[dict]] = None,
                      puntos_fin: Optional[list[dict]] = None) -> list[dict]:
    """Aspectos mayores entre los puntos dados, ordenados por orbe.

    Cada punto es {"nombre", "lon", "vel"} (velocidad en grados/día).
    Sin hora, `puntos_inicio` y `puntos_fin` son las posiciones a las 00:00 y 23:59: un aspecto
    `puede_variar` si no se mantiene con el mismo tipo en ambos extremos del día.
    """
    aspectos = []
    for i in range(len(puntos)):
        for j in range(i + 1, len(puntos)):
            a, b = puntos[i], puntos[j]
            if a["nombre"] in ANGULOS_NOMBRES and b["nombre"] in ANGULOS_NOMBRES:
                continue  # Ascendente-Medio Cielo no se considera aspecto
            encontrado = aspecto_entre(a["nombre"], a["lon"], b["nombre"], b["lon"])
            if encontrado is None:
                continue
            tipo, exacto, orbe, armonico = encontrado

            # Aplicativo: el orbe se reduce un instante después (dt = 0,01 días).
            dt = 0.01
            orbe_despues = abs(separacion(a["lon"] + a["vel"] * dt, b["lon"] + b["vel"] * dt) - exacto)

            puede_variar = False
            if puntos_inicio is not None and puntos_fin is not None:
                for extremo in (puntos_inicio, puntos_fin):
                    otro = aspecto_entre(a["nombre"], extremo[i]["lon"], b["nombre"], extremo[j]["lon"])
                    if otro is None or otro[0] != tipo:
                        puede_variar = True

            aspectos.append({
                "a": a["nombre"],
                "b": b["nombre"],
                "tipo": tipo,
                "armonico": armonico,
                "angulo": round(separacion(a["lon"], b["lon"]), 2),
                "orbe": round(orbe, 2),
                "orbe_texto": grado_texto(orbe),
                "aplicativo": orbe_despues < orbe,
                "puede_variar": puede_variar,
            })
    aspectos.sort(key=lambda x: x["orbe"])
    return aspectos


def _puntos_aspecto(sujeto, con_angulos: bool) -> list[dict]:
    puntos = []
    for clave, nombre, _, atributo in PUNTOS_CARTA:
        if clave in CLAVES_REPARTO:  # solo los diez planetas
            p = getattr(sujeto, atributo)
            puntos.append({"nombre": nombre, "lon": p.abs_pos, "vel": p.speed or 0.0})
    if con_angulos:
        puntos.append({"nombre": "Ascendente", "lon": sujeto.ascendant.abs_pos, "vel": sujeto.ascendant.speed or 0.0})
        puntos.append({"nombre": "Medio Cielo", "lon": sujeto.medium_coeli.abs_pos, "vel": sujeto.medium_coeli.speed or 0.0})
    return puntos


def calcular_carta_completa(
    year: int,
    month: int,
    day: int,
    lat: float,
    lng: float,
    hour: Optional[int] = None,
    minute: Optional[int] = None,
) -> dict:
    """Carta natal completa: planetas, nodo norte, Quirón, ángulos, casas, elementos,
    modalidades y fase lunar.

    Sin hora: todo se calcula a las 12:00 locales; ascendente, medio cielo, casas y la casa de
    cada planeta son None, y cada planeta indica `puede_variar` si cambia de signo ese día.
    """
    tz = zona_horaria(lat, lng)
    hora_exacta = hour is not None
    claves_kerykeion = [p[2] for p in PUNTOS_CARTA]

    if hora_exacta:
        principal = _sujeto(year, month, day, hour, minute or 0, lat, lng, tz,
                            claves_kerykeion + ["Ascendant", "Medium_Coeli"])
        inicio = fin = None
    else:
        principal = _sujeto(year, month, day, HORA_POR_DEFECTO, MINUTO_POR_DEFECTO, lat, lng, tz, claves_kerykeion)
        inicio = _sujeto(year, month, day, 0, 0, lat, lng, tz, claves_kerykeion)
        fin = _sujeto(year, month, day, 23, 59, lat, lng, tz, claves_kerykeion)

    planetas = []
    for clave, nombre, _, atributo in PUNTOS_CARTA:
        punto = getattr(principal, atributo)
        if punto is None:
            raise HoraInvalida(f"No se pudo calcular {nombre}")
        puede_variar = False
        if not hora_exacta:
            puede_variar = getattr(inicio, atributo).sign_num != getattr(fin, atributo).sign_num
        planetas.append({
            "clave": clave,
            "nombre": nombre,
            **_signo(punto.sign_num, punto.position),
            "casa": _NUMERO_CASA.get(punto.house) if hora_exacta else None,
            "retrogrado": bool(punto.retrograde),
            "puede_variar": puede_variar,
        })

    angulos = None
    casas = None
    if hora_exacta:
        if principal.ascendant is None or principal.medium_coeli is None:
            raise HoraInvalida("No se pudieron calcular los ángulos")
        angulos = {
            "ascendente": _signo(principal.ascendant.sign_num, principal.ascendant.position),
            "medio_cielo": _signo(principal.medium_coeli.sign_num, principal.medium_coeli.position),
        }
        casas = []
        for numero, atributo in enumerate(ATRIBUTOS_CASAS, start=1):
            cuspide = getattr(principal, atributo)
            casas.append({"numero": numero, **_signo(cuspide.sign_num, cuspide.position)})

    signos_reparto = [p.sign_num for p in (getattr(principal, a) for c, _, _, a in PUNTOS_CARTA if c in CLAVES_REPARTO)]
    if hora_exacta:
        signos_reparto.append(principal.ascendant.sign_num)
    elementos = {e: 0 for e in ELEMENTOS}
    modalidades = {m: 0 for m in MODALIDADES}
    for n in signos_reparto:
        elementos[ELEMENTOS[n % 4]] += 1
        modalidades[MODALIDADES[n % 3]] += 1

    if hora_exacta:
        aspectos = calcular_aspectos(_puntos_aspecto(principal, True))
    else:
        aspectos = calcular_aspectos(
            _puntos_aspecto(principal, False), _puntos_aspecto(inicio, False), _puntos_aspecto(fin, False)
        )

    por_clave = {p["clave"]: p for p in planetas}
    return {
        "sol": por_clave["sol"]["signo"],
        "luna": por_clave["luna"]["signo"],
        "ascendente": angulos["ascendente"]["signo"] if angulos else None,
        "hora_exacta": hora_exacta,
        "luna_puede_variar": por_clave["luna"]["puede_variar"],
        "planetas": planetas,
        "angulos": angulos,
        "casas": casas,
        "elementos": elementos,
        "modalidades": modalidades,
        "fase_lunar": fase_lunar(principal.sun.abs_pos, principal.moon.abs_pos),
        "aspectos": aspectos,
    }
