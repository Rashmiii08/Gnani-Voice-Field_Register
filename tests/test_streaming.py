from fastapi.testclient import TestClient
from backend.main import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "running"


def test_homepage_loads():
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Gnani Voice Field Register" in response.text
