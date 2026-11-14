from fastapi.testclient import TestClient

from app import __version__
from app.config import Settings
from app.main import create_app


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_docs_live_under_api_prefix(client):
    # nginx solo reenvía /api/*: la documentación tiene que estar ahí
    assert client.get("/api/docs").status_code == 200
    paths = client.get("/api/openapi.json").json()["paths"]
    assert {"/api/health", "/api/point"} <= paths.keys()


def test_no_cors_by_default(client):
    response = client.get("/api/health", headers={"Origin": "http://example.org"})
    assert "access-control-allow-origin" not in response.headers


def test_cors_when_configured():
    origin = "http://localhost:5500"
    client = TestClient(create_app(Settings(cors_origins=[origin])))
    response = client.get("/api/health", headers={"Origin": origin})
    assert response.headers["access-control-allow-origin"] == origin
