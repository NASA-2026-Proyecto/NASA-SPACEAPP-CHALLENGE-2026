"""Parámetros de consulta compartidos entre rutas."""

from typing import Annotated

from fastapi import Query

Lat = Annotated[float, Query(ge=-90, le=90, description="Latitud en grados (WGS84)")]
Lon = Annotated[float, Query(ge=-180, le=180, description="Longitud en grados (WGS84), de -180 a 180")]
