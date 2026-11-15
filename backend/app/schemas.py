"""Contrato de la API con el front."""

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: str
    version: str


class PointResponse(BaseModel):
    ok: bool
    lat: float = Field(description="Latitud recibida, en grados")
    lon: float = Field(description="Longitud recibida, en grados")
    message: str = Field(description="Confirmación legible para mostrar en la interfaz")
