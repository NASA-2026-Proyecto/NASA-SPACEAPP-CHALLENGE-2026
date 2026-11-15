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
from urllib.parse import urljoin

from app.services.http import http_get, http_last_modified

API_URL = "https://svs.gsfc.nasa.gov/api/"


@dataclass(frozen=True)
class Media:
    kind: str  # "Image", "Frames", "Movie"...
    url: str


@dataclass(frozen=True)
class Page:
    id: int
    title: str
    updated: datetime  # UTC
    media: tuple[Media, ...]

    @property
    def url(self) -> str:
        return f"https://svs.gsfc.nasa.gov/{self.id}/"

    def find(self, kind: str, contains: str = "") -> Media:
        for item in self.media:
            if item.kind == kind and contains.lower() in item.url.lower():
                return item
        raise LookupError(f"La página {self.id} de SVS no tiene {kind} '{contains}'.")


def _https(url: str) -> str:
    return url.replace("http://", "https://", 1)


def parse_page(raw: dict) -> Page:
    media = tuple(
        Media(kind=instance["media_type"], url=_https(instance["url"]))
        for group in raw.get("media_groups", [])
        for item in group.get("items", [])
        if (instance := item.get("instance") or {}).get("media_type") and instance.get("url")
    )
    updated = datetime.fromisoformat(raw.get("update_date") or raw["release_date"])
    return Page(id=raw["id"], title=raw["title"], updated=updated.astimezone(UTC), media=media)


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
    def __init__(
        self,
        get: Callable[[str], bytes] = http_get,
        last_modified: Callable[[str], datetime] = http_last_modified,
    ) -> None:
        self._get = get
        self._last_modified = last_modified

    def page(self, page_id: int) -> Page:
        return parse_page(json.loads(self._get(f"{API_URL}{page_id}")))

    def frame_urls(self, frames: Media) -> list[str]:
        return parse_frame_listing(self._get(frames.url).decode("utf-8", errors="replace"), frames.url)

    def download(self, url: str) -> bytes:
        return self._get(url)

    def last_modified(self, url: str) -> datetime:
        """Cuándo cambió por última vez un archivo (UTC): sirve para detectar un render nuevo."""
        return self._last_modified(url)
