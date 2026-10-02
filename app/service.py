"""Cálculo astrológico: Sol, Luna y Ascendente con Kerykeion (Swiss Ephemeris).

Escrito contra la API de kerykeion 5.12.x:
    AstrologicalSubjectFactory.from_birth_data(..., lng=, lat=, tz_str=, online=False)
devuelve un AstrologicalSubjectModel con atributos `sun`, `moon` y `ascendant`,
cada uno con `sign` (abreviatura de 3 letras) y `sign_num` (0 = Aries ... 11 = Piscis).
"""

from __future__ import annotations

import logging
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
            subject = AstrologicalSubjectFactory.from_birth_data(**kwargs)
        except KerykeionException as exc:
            # pytz lanza error si la hora local es ambigua (cambio a horario de invierno:
            # la hora ocurre dos veces) o inexistente (cambio a horario de verano: la hora
            # se salta). Resolvemos ambos casos asumiendo horario estándar (is_dst=False),
            # que es el criterio habitual de los programas de astrología.
            texto = str(exc)
            if "Ambiguous" in texto or "Non-existent" in texto:
                subject = AstrologicalSubjectFactory.from_birth_data(is_dst=False, **kwargs)
            else:
                raise HoraInvalida("No se pudo interpretar la hora local") from exc

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
