import http.client
import urllib.error
from datetime import UTC, datetime
from email.message import Message

import pytest

from app.services import http as http_module
from app.services.http import http_get, http_last_modified

URL = "https://svs.gsfc.nasa.gov/api/5151"
MODIFIED = {"Last-Modified": "Sat, 14 Nov 2026 11:29:21 GMT"}


class FakeResponse:
    def __init__(self, body: bytes = b"", headers: dict[str, str] | None = None, read_error=None):
        self._body = body
        self._read_error = read_error
        self.headers = Message()
        for name, value in (headers or {}).items():
            self.headers[name] = value

    def read(self) -> bytes:
        if self._read_error:
            raise self._read_error
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def server_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(URL, code, "error", Message(), None)


@pytest.fixture
def network(monkeypatch):
    """Sustituye la red: cada llamada consume el siguiente resultado de la lista."""

    class Network:
        def __init__(self):
            self.outcomes: list = []
            self.requests: list = []
            self.pauses: list[float] = []
            self.timeouts: list[float] = []

        def open(self, request, timeout):
            self.requests.append(request)
            self.timeouts.append(timeout)
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

    fake = Network()
    monkeypatch.setattr(http_module, "_open", fake.open)
    return fake


def test_get_returns_the_body_and_identifies_itself(network):
    network.outcomes = [FakeResponse(b"datos")]
    assert http_get(URL, sleep=network.pauses.append) == b"datos"
    (request,) = network.requests
    assert request.full_url == URL
    assert request.get_method() == "GET"
    assert request.get_header("User-agent") == "earth-jukebox-api"
    assert network.pauses == []


@pytest.mark.parametrize(
    "failure",
    [
        server_error(500),
        server_error(502),
        server_error(504),
        urllib.error.URLError("sin conexión"),
        TimeoutError("tiempo agotado"),
        ConnectionResetError("conexión cortada"),
        FakeResponse(read_error=http.client.IncompleteRead(b"medio")),  # corte a mitad de descarga
    ],
)
def test_transient_failures_are_retried(network, failure):
    network.outcomes = [failure, failure, FakeResponse(b"al fin")]
    assert http_get(URL, sleep=network.pauses.append) == b"al fin"
    assert len(network.requests) == 3
    assert network.pauses == [3.0, 6.0]  # la pausa crece con cada intento


def test_every_attempt_uses_the_timeout(network):
    network.outcomes = [server_error(503), FakeResponse(b"ok")]
    http_get(URL, timeout=7.5, sleep=network.pauses.append)
    assert network.timeouts == [7.5, 7.5]


def test_client_errors_are_not_retried(network):
    network.outcomes = [server_error(404), FakeResponse(b"no se debe pedir")]
    with pytest.raises(urllib.error.HTTPError) as caught:
        http_get(URL, sleep=network.pauses.append)
    assert caught.value.code == 404
    assert len(network.requests) == 1
    assert network.pauses == []


def test_the_last_failure_is_raised_when_attempts_run_out(network):
    network.outcomes = [server_error(502), server_error(503), TimeoutError("agotado")]
    with pytest.raises(TimeoutError, match="agotado"):
        http_get(URL, attempts=3, sleep=network.pauses.append)
    assert len(network.requests) == 3
    assert network.pauses == [3.0, 6.0]  # tras el último intento ya no se espera


def test_at_least_one_attempt_is_required(network):
    with pytest.raises(ValueError, match="al menos un intento"):
        http_get(URL, attempts=0)
    assert network.requests == []


@pytest.mark.parametrize(
    "url",
    [
        "http://svs.gsfc.nasa.gov/api/5151",  # sin cifrar
        "https://example.org/api/5151",  # otro servidor
        "https://svs.gsfc.nasa.gov.example.org/x",  # se parece, pero no es
        "file:///etc/passwd",
        "ftp://svs.gsfc.nasa.gov/x",
        "https://evil.example@svs.gsfc.nasa.gov/",  # usuario delante del servidor
        "https://user:secret@svs.gsfc.nasa.gov/x",
        "https://svs.gsfc.nasa.gov:8443/x",  # otro puerto
        "https://svs.gsfc.nasa.gov:puerto/x",
        "https://evil.example\\@svs.gsfc.nasa.gov/",  # barra invertida
        " https://svs.gsfc.nasa.gov/x",
        "https://svs.gsfc.nasa.gov/x y",
        "https://svs.gsfc.nasa.gov/x\r\nHost: evil.example",
    ],
)
def test_only_https_urls_of_known_hosts_are_requested(network, url):
    with pytest.raises(ValueError, match="URL no permitida"):
        http_get(url)
    with pytest.raises(ValueError, match="URL no permitida"):
        http_last_modified(url)
    assert network.requests == []


def test_last_modified_uses_head_and_returns_utc(network):
    network.outcomes = [FakeResponse(headers=MODIFIED)]
    modified = http_last_modified(URL, sleep=network.pauses.append)
    assert modified == datetime(2026, 11, 14, 11, 29, 21, tzinfo=UTC)
    assert network.requests[0].get_method() == "HEAD"


def test_last_modified_is_retried_too(network):
    network.outcomes = [server_error(503), FakeResponse(headers=MODIFIED)]
    assert http_last_modified(URL, sleep=network.pauses.append).day == 14
    assert network.pauses == [3.0]


def test_missing_last_modified_header_is_an_error(network):
    network.outcomes = [FakeResponse()]
    with pytest.raises(LookupError, match="fecha de modificación"):
        http_last_modified(URL, sleep=network.pauses.append)


def test_last_modified_in_another_time_zone_is_converted_to_utc(network):
    network.outcomes = [FakeResponse(headers={"Last-Modified": "Sat, 14 Nov 2026 06:29:21 -0500"})]
    modified = http_last_modified(URL, sleep=network.pauses.append)
    assert modified == datetime(2026, 11, 14, 11, 29, 21, tzinfo=UTC)
    assert modified.utcoffset().total_seconds() == 0
    assert modified.hour == 11


# --- Redirecciones -----------------------------------------------------------------


def test_known_hosts_and_the_https_port_are_accepted():
    for url in (URL, "https://opendap.nccs.nasa.gov/dods/x.das", "https://svs.gsfc.nasa.gov:443/x"):
        http_module.check_url(url)  # no lanza


@pytest.mark.parametrize(
    "target",
    [
        "http://localhost:8000/internal",
        "https://example.org/x",
        "http://svs.gsfc.nasa.gov/x",
        "file:///etc/passwd",
    ],
)
def test_redirects_to_other_places_are_refused(target):
    handler = http_module._CheckedRedirects()
    request = http_module._request(URL)
    with pytest.raises(ValueError, match="URL no permitida"):
        handler.redirect_request(request, None, 302, "Found", Message(), target)


def test_redirects_between_known_hosts_are_followed():
    handler = http_module._CheckedRedirects()
    target = "https://svs.gsfc.nasa.gov/api/5113"
    redirected = handler.redirect_request(http_module._request(URL), None, 302, "Found", Message(), target)
    assert redirected.full_url == target


def test_a_refused_redirect_is_not_retried(network):
    network.outcomes = [ValueError("URL no permitida: 'http://localhost/'"), FakeResponse(b"no")]
    with pytest.raises(ValueError, match="URL no permitida"):
        http_get(URL, sleep=network.pauses.append)
    assert len(network.requests) == 1


def test_the_opener_checks_redirects():
    # La pieza que sale a la red de verdad lleva puesto el filtro de redirecciones
    assert any(isinstance(h, http_module._CheckedRedirects) for h in http_module._opener.handlers)


def test_requests_go_out_through_the_checked_opener(monkeypatch):
    seen = []

    def fake_open(request, timeout):
        seen.append((request.full_url, timeout))
        return FakeResponse(b"ok")

    monkeypatch.setattr(http_module._opener, "open", fake_open)
    assert http_get(URL, timeout=12.0) == b"ok"
    assert seen == [(URL, 12.0)]
