"""API smoke tests."""

from fastapi.testclient import TestClient

from pms_platform.api.main import app


def test_health_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_dashboard_summary_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
    assert "total_episodes" in payload
    assert "assessment_counts" in payload
