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


def test_continuous_loss_backtest_endpoint() -> None:
    client = TestClient(app)
    response = client.get("/backtests/one-year-continuous-loss")
    assert response.status_code == 200
    payload = response.json()
    assert "equal_capital_start_value" in payload
    assert "hold_equal_capital_end_value" in payload
    assert "diversified_equal_capital_end_value" in payload
    assert "mean_return_advantage_pp" in payload
    assert "median_return_advantage_pp" in payload
    assert "average_winner_pp" in payload
    assert "average_loser_pp" in payload
    assert "payoff_ratio" in payload
    assert "profit_factor" in payload
    assert "historical_capital_weighted_uplift_pct" in payload
    assert "episodes" in payload
