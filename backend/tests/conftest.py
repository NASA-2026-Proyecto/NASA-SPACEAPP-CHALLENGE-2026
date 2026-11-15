import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services.scenes import SceneStore
from tests.fakes import FakeGeosFp


@pytest.fixture
def client() -> TestClient:
    # Configuración explícita: los tests no dependen del entorno de quien los ejecuta,
    # y la NASA es de mentira: ningún test sale a la red
    scenes = SceneStore(FakeGeosFp().client())
    return TestClient(create_app(Settings(cors_origins=[]), scenes=scenes))
