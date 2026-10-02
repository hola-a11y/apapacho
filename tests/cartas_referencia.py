"""Cartas de referencia calculadas en astro.com.

Rellena `esperado` con los signos en español tal y como los devuelve la API:
Aries, Tauro, Géminis, Cáncer, Leo, Virgo, Libra, Escorpio, Sagitario, Capricornio,
Acuario, Piscis.

Mientras `esperado` tenga valores None, el test correspondiente se marca como SKIPPED.
Las coordenadas y la hora son las que introdujiste en astro.com (hora local del lugar,
sin convertir a UTC: la API resuelve la zona horaria y el horario de verano histórico).
"""

CARTAS_REFERENCIA = [
    {
        "id": "carta_1",
        "entrada": {
            "year": None,
            "month": None,
            "day": None,
            "hour": None,
            "minute": None,
            "lat": None,
            "lng": None,
        },
        "esperado": {"sol": None, "luna": None, "ascendente": None},
    },
    {
        "id": "carta_2",
        "entrada": {
            "year": None,
            "month": None,
            "day": None,
            "hour": None,
            "minute": None,
            "lat": None,
            "lng": None,
        },
        "esperado": {"sol": None, "luna": None, "ascendente": None},
    },
    {
        "id": "carta_3",
        "entrada": {
            "year": None,
            "month": None,
            "day": None,
            "hour": None,
            "minute": None,
            "lat": None,
            "lng": None,
        },
        "esperado": {"sol": None, "luna": None, "ascendente": None},
    },
    {
        "id": "carta_4",
        "entrada": {
            "year": None,
            "month": None,
            "day": None,
            "hour": None,
            "minute": None,
            "lat": None,
            "lng": None,
        },
        "esperado": {"sol": None, "luna": None, "ascendente": None},
    },
    {
        "id": "carta_5",
        "entrada": {
            "year": None,
            "month": None,
            "day": None,
            "hour": None,
            "minute": None,
            "lat": None,
            "lng": None,
        },
        "esperado": {"sol": None, "luna": None, "ascendente": None},
    },
]
