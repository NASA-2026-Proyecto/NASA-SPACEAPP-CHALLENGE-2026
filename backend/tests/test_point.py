import pytest


def test_point_echoes_coordinates(client):
    response = client.get("/api/point", params={"lat": 40.4168, "lon": -3.7038})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["lat"] == 40.4168
    assert body["lon"] == -3.7038
    assert body["message"] == "Coordenadas recibidas: lat 40.4168, lon -3.7038"


@pytest.mark.parametrize(("lat", "lon"), [(90, 180), (-90, -180), (0, 0)])
def test_point_accepts_range_limits(client, lat, lon):
    assert client.get("/api/point", params={"lat": lat, "lon": lon}).status_code == 200


@pytest.mark.parametrize(
    "params",
    [
        {"lat": 90.01, "lon": 0},
        {"lat": -90.01, "lon": 0},
        {"lat": 0, "lon": 180.01},
        {"lat": 0, "lon": -180.01},
        {"lat": "nan", "lon": 0},
        {"lat": 0, "lon": "inf"},
        {"lat": "abc", "lon": 0},
        {"lat": 10},
        {"lon": 10},
        {},
    ],
)
def test_point_rejects_invalid_coordinates(client, params):
    assert client.get("/api/point", params=params).status_code == 422
