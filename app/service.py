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
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytz
import swisseph as swe
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


class DatosInsuficientes(ValueError):
    """Faltan datos para este cálculo (p. ej. la hora en una revolución solar)."""


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
    seconds: int = 0,
):
    """Crea el AstrologicalSubjectModel de Kerykeion para una fecha/hora local."""
    kwargs = dict(
        seconds=seconds,
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


# En sinastría los orbes se reducen 2°: 6° (4° en el sextil), 8° con Sol o Luna.
REDUCCION_ORBE_SINASTRIA = 2.0


def orbe_maximo(tipo: str, nombre_a: str, nombre_b: str, sinastria: bool = False) -> float:
    base = next(o for t, _, o, _ in TIPOS_ASPECTO if t == tipo)
    if sinastria:
        base -= REDUCCION_ORBE_SINASTRIA
    if nombre_a in LUMINARIAS or nombre_b in LUMINARIAS:
        base += EXTRA_ORBE_LUMINARIA
    return base


def aspecto_entre(nombre_a: str, lon_a: float, nombre_b: str, lon_b: float,
                  sinastria: bool = False) -> Optional[tuple[str, float, float, Optional[bool]]]:
    """Devuelve (tipo, ángulo exacto, orbe, armónico) si hay aspecto mayor dentro de orbe."""
    sep = separacion(lon_a, lon_b)
    for tipo, exacto, _, armonico in TIPOS_ASPECTO:
        orbe_max = orbe_maximo(tipo, nombre_a, nombre_b, sinastria)
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
    if hour is not None:
        principal = _sujeto(year, month, day, hour, minute or 0, lat, lng, tz, CLAVES_KERYKEION_CON_ANGULOS)
        return _carta_desde_sujetos(principal)
    principal = _sujeto(year, month, day, HORA_POR_DEFECTO, MINUTO_POR_DEFECTO, lat, lng, tz, CLAVES_KERYKEION)
    inicio = _sujeto(year, month, day, 0, 0, lat, lng, tz, CLAVES_KERYKEION)
    fin = _sujeto(year, month, day, 23, 59, lat, lng, tz, CLAVES_KERYKEION)
    return _carta_desde_sujetos(principal, inicio, fin)


CLAVES_KERYKEION = [p[2] for p in PUNTOS_CARTA]
CLAVES_KERYKEION_CON_ANGULOS = CLAVES_KERYKEION + ["Ascendant", "Medium_Coeli"]


def _carta_desde_sujetos(principal, inicio=None, fin=None) -> dict:
    """Construye la carta completa. Sin `inicio`/`fin`, la hora es exacta (hay ángulos y casas);
    con ellos, `principal` es el mediodía y se marcan los puntos que varían durante el día."""
    hora_exacta = inicio is None

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


# ---------------------------------------------------------------------------
# Revolución solar
# ---------------------------------------------------------------------------


def calcular_revolucion_solar(
    year: int,
    month: int,
    day: int,
    lat: float,
    lng: float,
    hour: Optional[int],
    minute: Optional[int],
    anio: int,
    lat_actual: Optional[float] = None,
    lng_actual: Optional[float] = None,
) -> dict:
    """Carta del instante en que el Sol vuelve a su longitud natal durante `anio` (en UTC).

    Necesita la hora de nacimiento: sin ella el Sol natal tiene ±0,5° de incertidumbre y el
    momento de la revolución, ±12 horas, lo que invalida ascendente y casas.
    La carta se levanta en (lat_actual, lng_actual), o en el lugar de nacimiento si se omiten.
    """
    if hour is None:
        raise DatosInsuficientes("La revolución solar necesita la hora de nacimiento")
    if anio < year:
        raise DatosInsuficientes("El año de la revolución no puede ser anterior al de nacimiento")

    tz_natal = zona_horaria(lat, lng)
    natal = _sujeto(year, month, day, hour, minute or 0, lat, lng, tz_natal, ["Sun"])
    lon_sol = natal.sun.abs_pos

    lat_r = lat if lat_actual is None else lat_actual
    lng_r = lng if lng_actual is None else lng_actual
    tz_r = zona_horaria(lat_r, lng_r)

    with _swe_lock:
        # _sujeto ya fijó la ruta de efemérides de Kerykeion; usamos las mismas opciones.
        jd = swe.solcross_ut(lon_sol, swe.julday(anio, 1, 1, 0.0), swe.FLG_SWIEPH)
    y, m, d, horas = swe.revjul(jd, swe.GREG_CAL)
    momento = datetime(y, m, d, tzinfo=timezone.utc) + timedelta(seconds=round(horas * 3600))

    # Se calcula en UTC: casas y planetas dependen solo del instante y del lugar, y así se
    # evitan las horas ambiguas de los cambios de horario.
    sujeto = _sujeto(momento.year, momento.month, momento.day, momento.hour, momento.minute,
                     lat_r, lng_r, "UTC", CLAVES_KERYKEION_CON_ANGULOS, seconds=momento.second)
    carta = _carta_desde_sujetos(sujeto)
    carta.update(
        anio=anio,
        momento_utc=momento.isoformat(),
        momento_local=momento.astimezone(pytz.timezone(tz_r)).isoformat(),
        zona_horaria=tz_r,
        sol_natal=_signo(natal.sun.sign_num, natal.sun.position),
    )
    return carta


# ---------------------------------------------------------------------------
# Sinastría
# ---------------------------------------------------------------------------

PESO_TIPO_SINASTRIA = {"trígono": 3.0, "sextil": 2.0, "cuadratura": -2.0, "oposición": -1.5}
CONJUNCION_ARMONICA = {"Sol", "Luna", "Venus", "Júpiter", "Ascendente"}
CONJUNCION_TENSA = {"Saturno", "Plutón"}
PESO_PUNTO_SINASTRIA = {
    "Sol": 1.5, "Luna": 1.5, "Venus": 1.5, "Marte": 1.5, "Ascendente": 1.5,
    "Mercurio": 1.0, "Júpiter": 1.0, "Saturno": 1.0,
    "Urano": 0.5, "Neptuno": 0.5, "Plutón": 0.5,
}
GENERACIONALES = {"Urano", "Neptuno", "Plutón"}
# Calibrado con 400 parejas aleatorias (1950-2005): la mediana del bruto es ~13,5 y el
# percentil 90, ~28. Así la pareja mediana obtiene 50, el p10 ~21 y el p90 ~80.
CENTRO_PUNTUACION = 13.5
ESCALA_PUNTUACION = 21.0


def _peso_tipo(tipo: str, a: str, b: str) -> float:
    if tipo != "conjunción":
        return PESO_TIPO_SINASTRIA[tipo]
    if a in CONJUNCION_ARMONICA and b in CONJUNCION_ARMONICA:
        return 2.5
    if a in CONJUNCION_TENSA or b in CONJUNCION_TENSA:
        return -1.5
    return 1.0


def peso_aspecto_sinastria(tipo: str, a: str, b: str, orbe: float, puede_variar: bool) -> float:
    """Contribución de un aspecto a la puntuación (documentada en el README)."""
    if a in GENERACIONALES and b in GENERACIONALES:
        return 0.0  # aspectos generacionales: los comparte toda la gente de edad parecida
    importancia = (PESO_PUNTO_SINASTRIA[a] + PESO_PUNTO_SINASTRIA[b]) / 2
    exactitud = 1 - orbe / orbe_maximo(tipo, a, b, sinastria=True)
    peso = _peso_tipo(tipo, a, b) * importancia * (0.5 + 0.5 * exactitud)
    if puede_variar:
        peso *= 0.5
    return peso


def _sujetos_persona(year, month, day, lat, lng, hour=None, minute=None):
    """(principal, inicio, fin) de una persona; inicio/fin son None si hay hora."""
    tz = zona_horaria(lat, lng)
    if hour is not None:
        return _sujeto(year, month, day, hour, minute or 0, lat, lng, tz, CLAVES_KERYKEION_CON_ANGULOS), None, None
    return (
        _sujeto(year, month, day, HORA_POR_DEFECTO, MINUTO_POR_DEFECTO, lat, lng, tz, CLAVES_KERYKEION),
        _sujeto(year, month, day, 0, 0, lat, lng, tz, CLAVES_KERYKEION),
        _sujeto(year, month, day, 23, 59, lat, lng, tz, CLAVES_KERYKEION),
    )


def _puntos_sinastria(sujeto, con_ascendente: bool) -> list[dict]:
    return [p for p in _puntos_aspecto(sujeto, con_ascendente) if p["nombre"] != "Medio Cielo"]


def calcular_sinastria(persona_a: dict, persona_b: dict) -> dict:
    """Aspectos entre los planetas (y ascendentes) de dos personas, con puntuación 0-100.

    Cada persona es un dict con year, month, day, lat, lng y opcionalmente hour, minute.
    En cada aspecto, `a` es el punto de la persona A y `b` el de la persona B.
    """
    sa = _sujetos_persona(**persona_a)
    sb = _sujetos_persona(**persona_b)
    hora_a, hora_b = sa[1] is None, sb[1] is None

    pa = _puntos_sinastria(sa[0], hora_a)
    pb = _puntos_sinastria(sb[0], hora_b)
    # Variantes del día para quien no tiene hora: (lista de A, lista de B) a comprobar.
    variantes = []
    if not hora_a:
        variantes += [(_puntos_sinastria(sa[1], False), pb), (_puntos_sinastria(sa[2], False), pb)]
    if not hora_b:
        variantes += [(pa, _puntos_sinastria(sb[1], False)), (pa, _puntos_sinastria(sb[2], False))]

    aspectos = []
    for i, a in enumerate(pa):
        for j, b in enumerate(pb):
            encontrado = aspecto_entre(a["nombre"], a["lon"], b["nombre"], b["lon"], sinastria=True)
            if encontrado is None:
                continue
            tipo, _, orbe, armonico = encontrado
            puede_variar = False
            for va, vb in variantes:
                otro = aspecto_entre(a["nombre"], va[i]["lon"], b["nombre"], vb[j]["lon"], sinastria=True)
                if otro is None or otro[0] != tipo:
                    puede_variar = True
            peso = peso_aspecto_sinastria(tipo, a["nombre"], b["nombre"], orbe, puede_variar)
            aspectos.append({
                "a": a["nombre"],
                "b": b["nombre"],
                "tipo": tipo,
                "armonico": armonico,
                "angulo": round(separacion(a["lon"], b["lon"]), 2),
                "orbe": round(orbe, 2),
                "orbe_texto": grado_texto(orbe),
                "puede_variar": puede_variar,
                "generacional": a["nombre"] in GENERACIONALES and b["nombre"] in GENERACIONALES,
                "peso": round(peso, 2),
            })
    aspectos.sort(key=lambda x: x["orbe"])

    bruto = sum(x["peso"] for x in aspectos)
    puntuacion = round(50 + 50 * math.tanh((bruto - CENTRO_PUNTUACION) / ESCALA_PUNTUACION))

    def resumen_persona(sujetos):
        carta = _carta_desde_sujetos(*[x for x in sujetos if x is not None])
        return {k: carta[k] for k in ("sol", "luna", "ascendente", "hora_exacta", "luna_puede_variar")}

    return {
        "persona_a": resumen_persona(sa),
        "persona_b": resumen_persona(sb),
        "aspectos": aspectos,
        "puntuacion": puntuacion,
        "resumen": {
            "armonicos": sum(1 for x in aspectos if x["armonico"] is True),
            "tensos": sum(1 for x in aspectos if x["armonico"] is False),
            "conjunciones": sum(1 for x in aspectos if x["tipo"] == "conjunción"),
            "puntuacion_bruta": round(bruto, 2),
        },
    }
