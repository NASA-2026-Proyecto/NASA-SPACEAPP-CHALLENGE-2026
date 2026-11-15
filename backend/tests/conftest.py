from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.factory import create_app

FIXTURES = Path(__file__).parent / "fixtures"


class IsolatedSettings(Settings):
    """Los ajustes de la API, pero sin leer el entorno: solo valen los valores que se le pasan."""

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, **_other_sources):
        return (init_settings,)


def make_settings(**overrides) -> Settings:
    """Ajustes para los tests: el entorno de quien los ejecuta no influye (ni los rompe)."""
    values = {"cors_origins": [], "scene_steps": 8, "scene_warmup": False}
    return IsolatedSettings(**{**values, **overrides})


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def client(settings) -> TestClient:
    # Sin escenas: ningún test sale a la red (las escenas se prueban con NASA de mentira)
    return TestClient(create_app(settings, scenes={}))


@pytest.fixture
def fixture_text() -> Callable[[str], str]:
    """Lee una respuesta real de la NASA guardada en tests/fixtures/."""
    return lambda name: (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def fixture_bytes() -> Callable[[str], bytes]:
    """Lee un archivo binario real de la NASA guardado en tests/fixtures/."""
    return lambda name: (FIXTURES / name).read_bytes()
