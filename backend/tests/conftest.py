import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


@pytest.fixture
def client() -> TestClient:
    # Configuración explícita: los tests no dependen del entorno de quien los ejecuta
    return TestClient(create_app(Settings(cors_origins=[])))
