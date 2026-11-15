"""GET con reintentos para los servicios públicos de la NASA (solo biblioteca estándar)."""

import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

USER_AGENT = "earth-jukebox-api"


def http_get(url: str, timeout: float = 60.0, attempts: int = 4) -> bytes:
    """GET con reintentos ante errores de servidor, cortes y tiempos de espera."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code < 500 or attempt == attempts:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == attempts:
                raise
        time.sleep(3.0 * attempt)
    raise AssertionError("inalcanzable")


def http_last_modified(url: str, timeout: float = 30.0) -> datetime:
    """Fecha de última modificación de un recurso (petición HEAD), en UTC."""
    request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        header = response.headers.get("Last-Modified")
    if not header:
        raise LookupError(f"{url} no indica su fecha de modificación.")
    return parsedate_to_datetime(header).astimezone(UTC)
