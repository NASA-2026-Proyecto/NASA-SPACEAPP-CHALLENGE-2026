"""Peticiones HTTP a los servicios públicos de la NASA (solo biblioteca estándar).

Las URLs que se piden salen en parte de respuestas de la propia NASA (listados, JSON),
así que antes de pedir nada, y también antes de seguir una redirección, se comprueba
que la dirección sea https y de un servidor conocido.
"""

import http.client
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import IO
from urllib.parse import urlsplit

USER_AGENT = "earth-jukebox-api"
ALLOWED_HOSTS = frozenset({"svs.gsfc.nasa.gov", "opendap.nccs.nasa.gov"})
HTTPS_PORT = 443
RETRY_PAUSE_SECONDS = 3.0  # se multiplica por el número de intento


def check_url(url: str) -> None:
    """Comprueba que una URL es https, de un servidor conocido y sin rarezas.

    Se rechazan también las direcciones con usuario o contraseña, con un puerto distinto
    del de https y con barras invertidas, espacios o caracteres de control: son las
    formas habituales de hacer pasar un servidor por otro.

    Raises:
        ValueError: Si la URL no está permitida.
    """
    problem = ValueError(f"URL no permitida: {url!r}")
    if "\\" in url or any(character.isspace() or not character.isprintable() for character in url):
        raise problem
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise problem from None
    allowed = (
        parts.scheme == "https"
        and parts.hostname in ALLOWED_HOSTS
        and parts.username is None
        and parts.password is None
        and port in (None, HTTPS_PORT)
    )
    if not allowed:
        raise problem


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    """Sigue las redirecciones solo si el destino también está permitido."""

    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: http.client.HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        """Rechaza (con ValueError) una redirección a una dirección no permitida."""
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_CheckedRedirects)


def _open(request: urllib.request.Request, timeout: float) -> http.client.HTTPResponse:
    """Abre la conexión. Es el único punto del backend que sale a la red."""
    response: http.client.HTTPResponse = _opener.open(request, timeout=timeout)
    return response


def _request(url: str, method: str = "GET") -> urllib.request.Request:
    """Prepara la petición, o falla si la URL no está permitida."""
    check_url(url)
    return urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})


def _with_retries[T](
    request: urllib.request.Request,
    read: Callable[[http.client.HTTPResponse], T],
    timeout: float,
    attempts: int,
    sleep: Callable[[float], None],
) -> T:
    """Hace la petición y devuelve `read(respuesta)`, reintentando los fallos pasajeros.

    Se reintentan los errores de servidor (5xx), los tiempos de espera y los cortes de
    conexión, también a mitad de la descarga. Un 4xx no se reintenta: no va a cambiar.
    """
    if attempts < 1:
        raise ValueError("Hace falta al menos un intento.")
    for attempt in range(1, attempts):
        try:
            with _open(request, timeout) as response:
                return read(response)
        except urllib.error.HTTPError as error:
            if error.code < 500:
                raise
        except (http.client.HTTPException, OSError):
            pass
        sleep(RETRY_PAUSE_SECONDS * attempt)
    # Último intento: si falla, el error llega tal cual a quien llama
    with _open(request, timeout) as response:
        return read(response)


def http_get(
    url: str,
    timeout: float = 60.0,
    attempts: int = 4,
    sleep: Callable[[float], None] = time.sleep,
) -> bytes:
    """Descarga el contenido de una URL (GET).

    Args:
        url: Dirección https de uno de los servidores de `ALLOWED_HOSTS`.
        timeout: Segundos de espera por intento.
        attempts: Intentos en total antes de dejar pasar el error.
        sleep: Función de pausa entre intentos (se sustituye en los tests).

    Raises:
        ValueError: Si la URL, o una redirección, no está permitida.
        OSError: Si todos los intentos fallan (incluye `urllib.error.URLError`).
    """
    return _with_retries(_request(url), lambda response: response.read(), timeout, attempts, sleep)


def http_last_modified(
    url: str,
    timeout: float = 30.0,
    attempts: int = 3,
    sleep: Callable[[float], None] = time.sleep,
) -> datetime:
    """Fecha de última modificación de un recurso (petición HEAD), en UTC.

    Raises:
        ValueError: Si la URL, o una redirección, no está permitida.
        LookupError: Si el servidor no indica la fecha.
    """
    header = _with_retries(
        _request(url, method="HEAD"),
        lambda response: response.headers.get("Last-Modified"),
        timeout,
        attempts,
        sleep,
    )
    if not header:
        raise LookupError(f"{url} no indica su fecha de modificación.")
    return parsedate_to_datetime(header).astimezone(UTC)
