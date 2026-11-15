"""Cliente del Scientific Visualization Studio de la NASA (svs.gsfc.nasa.gov), sin clave.

Las visualizaciones del Earth Information Center (EIC) se publican aquí. SVS no permite
que un navegador de otro origen lea sus imágenes (CORS), así que se descargan desde el
backend.
"""

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from app.services.http import http_get, http_last_modified

API_URL = "https://svs.gsfc.nasa.gov/api/"


@dataclass(frozen=True)
class Media:
    """Un recurso descargable de una página: una imagen, un vídeo o un directorio de fotogramas."""

    kind: str  # "Image", "Frames", "Movie"...
    url: str


@dataclass(frozen=True)
class Page:
    """Lo que interesa de una página de visualización de SVS."""

    id: int
    title: str
    updated: datetime  # UTC
    media: tuple[Media, ...]

    @property
    def url(self) -> str:
        """Dirección de la página para personas."""
        return f"https://svs.gsfc.nasa.gov/{self.id}/"

    def find(self, kind: str, contains: str = "") -> Media:
        """Primer recurso de un tipo cuya URL contiene un texto (sin distinguir mayúsculas).

        Raises:
            LookupError: Si la página no tiene ninguno.
        """
        for item in self.media:
            if item.kind == kind and contains.lower() in item.url.lower():
                return item
        raise LookupError(f"La página {self.id} de SVS no tiene {kind} '{contains}'.")


def _https(url: str) -> str:
    """La API devuelve direcciones http://; el servidor atiende las mismas por https."""
    return url.replace("http://", "https://", 1)


def parse_page(raw: dict[str, Any]) -> Page:
    """Convierte la respuesta JSON de la API de SVS (`/api/<id>`) en una `Page`.

    La fecha de actualización se pasa a UTC; si viniera sin zona, se toma como UTC.
    """
    media = tuple(
        Media(kind=instance["media_type"], url=_https(instance["url"]))
        for group in raw.get("media_groups", [])
        for item in group.get("items", [])
        if (instance := item.get("instance") or {}).get("media_type") and instance.get("url")
    )
    updated = datetime.fromisoformat(raw.get("update_date") or raw["release_date"])
    updated = updated.replace(tzinfo=UTC) if updated.tzinfo is None else updated.astimezone(UTC)
    return Page(id=raw["id"], title=raw["title"], updated=updated, media=media)


def parse_frame_listing(html: str, base_url: str) -> list[str]:
    """URLs de los fotogramas de un directorio de SVS, del más antiguo al más reciente.

    Según la página, los enlaces son relativos ("0001.png") o rutas absolutas
    ("/vis/.../frame.001.exr"); se resuelven y se descartan los que no cuelgan del
    directorio (iconos y demás imágenes de la plantilla).
    """
    base = base_url.rstrip("/") + "/"
    links = re.findall(r'href="?([^"\s>]+\.(?:png|jpg|exr))', html)
    urls = dict.fromkeys(urljoin(base, link) for link in links)
    return sorted((url for url in urls if url.startswith(base)), key=_frame_order)


def _frame_order(url: str) -> tuple[int, ...]:
    """Orden por los números del nombre de archivo (".999" va antes que ".1000")."""
    return tuple(int(number) for number in re.findall(r"\d+", url.rsplit("/", 1)[-1]))


class SvsClient:
    """Acceso a las páginas de SVS y a sus archivos."""

    def __init__(
        self,
        get: Callable[[str], bytes] = http_get,
        last_modified: Callable[[str], datetime] = http_last_modified,
    ) -> None:
        """Prepara el cliente.

        Args:
            get: Función que descarga una URL (se sustituye en los tests).
            last_modified: Función que da la fecha de modificación de una URL.
        """
        self._get = get
        self._last_modified = last_modified

    def page(self, page_id: int) -> Page:
        """Datos de la página de visualización con ese número."""
        return parse_page(json.loads(self._get(f"{API_URL}{page_id}")))

    def frame_urls(self, frames: Media) -> list[str]:
        """URLs de los fotogramas de un directorio, del más antiguo al más reciente."""
        return parse_frame_listing(self._get(frames.url).decode("utf-8", errors="replace"), frames.url)

    def download(self, url: str) -> bytes:
        """Contenido de un archivo de SVS."""
        return self._get(url)

    def last_modified(self, url: str) -> datetime:
        """Cuándo cambió por última vez un archivo (UTC): sirve para detectar un render nuevo."""
        return self._last_modified(url)
