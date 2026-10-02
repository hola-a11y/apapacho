"""Esquemas de entrada y salida (pydantic v2)."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CartaRequest(BaseModel):
    """Datos de nacimiento. El geocoding (ciudad -> lat/lng) se hace fuera, en n8n."""

    model_config = ConfigDict(extra="forbid")

    year: int = Field(..., ge=1900, le=2100, description="Año de nacimiento (1900-2100)")
    month: int = Field(..., ge=1, le=12, description="Mes (1-12)")
    day: int = Field(..., ge=1, le=31, description="Día (1-31)")
    hour: Optional[int] = Field(
        None, ge=0, le=23, description="Hora local (0-23). Si se omite, no se calcula el ascendente."
    )
    minute: Optional[int] = Field(None, ge=0, le=59, description="Minuto (0-59)")
    lat: float = Field(..., ge=-90, le=90, description="Latitud en grados decimales")
    lng: float = Field(..., ge=-180, le=180, description="Longitud en grados decimales")

    @model_validator(mode="after")
    def _validar_fecha_y_hora(self) -> "CartaRequest":
        # Rechaza fechas inexistentes como 31/02 o 29/02 en años no bisiestos.
        try:
            date(self.year, self.month, self.day)
        except ValueError as exc:
            raise ValueError("La fecha no existe en el calendario") from exc

        if self.hour is None:
            # Sin hora no tiene sentido un minuto: se ignora.
            self.minute = None
        elif self.minute is None:
            self.minute = 0
        return self


class CartaResponse(BaseModel):
    sol: str = Field(..., description="Signo solar (nombre en español)")
    luna: str = Field(..., description="Signo lunar (nombre en español)")
    ascendente: Optional[str] = Field(
        None, description="Signo ascendente. null si no se indicó la hora de nacimiento."
    )
    hora_exacta: bool = Field(..., description="true si se usó la hora indicada; false si se asumió 12:00")
    luna_puede_variar: bool = Field(
        ...,
        description=(
            "true si no se indicó hora y la Luna cambia de signo durante ese día "
            "(entre 00:00 y 23:59 hora local)"
        ),
    )


class HealthResponse(BaseModel):
    status: str


class RootResponse(BaseModel):
    name: str
    license: str
    source: str
    docs: str
