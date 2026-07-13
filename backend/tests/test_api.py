import pytest
from fastapi.testclient import TestClient

from app.analytics import AnalyticsSummary
from app.twitter_cli import CliResult, ValidationError


def test_health_endpoint_reports_ok():
    from app.main import app

    client = TestClient(app)

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_presets_endpoint_returns_supported_commands():
    from app.main import app

    client = TestClient(app)

    response = client.get("/api/presets")

    assert response.status_code == 200
    preset_ids = [preset["id"] for preset in response.json()["presets"]]
    assert preset_ids == ["feed", "search", "bookmarks", "status", "whoami"]


def test_run_endpoint_returns_cli_result(monkeypatch):
    from app import main

    def fake_runner(preset, options):
        assert preset == "feed"
        assert options == {"max": 2}
        return CliResult(command=["twitter", "feed", "--max", "2", "--json"], data={"ok": True, "data": []})

    monkeypatch.setattr(main, "run_twitter_command", fake_runner)
    client = TestClient(main.app)

    response = client.post("/api/run", json={"preset": "feed", "options": {"max": 2}})

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "command": ["twitter", "feed", "--max", "2", "--json"],
        "data": {"ok": True, "data": []},
    }


def test_run_endpoint_maps_validation_failure(monkeypatch):
    from app import main

    def fake_runner(preset, options):
        raise ValidationError("Search query is required")

    monkeypatch.setattr(main, "run_twitter_command", fake_runner)
    client = TestClient(main.app)

    response = client.post("/api/run", json={"preset": "search", "options": {"max": 2}})

    assert response.status_code == 422
    assert response.json()["detail"] == "Search query is required"


def test_analytics_summary_endpoint_returns_dashboard_data(monkeypatch):
    from app import main

    def fake_fetch(start_date="28daysAgo", end_date="yesterday"):
        return AnalyticsSummary(
            start_date=start_date,
            end_date=end_date,
            metrics={
                "activeUsers": 12,
                "sessions": 20,
                "screenPageViews": 42,
                "conversions": 3,
                "engagementRate": 0.61,
            },
            acquisition=[{"channel": "Organic Social", "sessions": 7, "activeUsers": 5, "conversions": 1}],
            pages=[{"path": "/", "views": 30, "activeUsers": 10, "conversions": 2}],
            campaigns=[
                {
                    "sourceMedium": "x.com / social",
                    "campaign": "founder-post",
                    "sessions": 7,
                    "activeUsers": 5,
                    "conversions": 1,
                    "engagementRate": 0.72,
                    "conversionRate": 0.1429,
                }
            ],
            landing_pages=[
                {
                    "landingPage": "/",
                    "sessions": 12,
                    "activeUsers": 10,
                    "conversions": 2,
                    "engagementRate": 0.5,
                    "conversionRate": 0.1667,
                }
            ],
            funnel_events=[{"eventName": "sign_up", "eventCount": 3, "activeUsers": 3, "conversions": 3}],
            recommendations=["Double down on x.com / social."],
        )

    monkeypatch.setenv("GA4_PROPERTY_ID", "123456")
    monkeypatch.setattr(main, "fetch_analytics_summary", fake_fetch)
    client = TestClient(main.app)

    response = client.get("/api/analytics/summary?start_date=7daysAgo&end_date=yesterday")

    assert response.status_code == 200
    body = response.json()
    assert body["property_id"] == "123456"
    assert body["metrics"]["activeUsers"] == 12
    assert body["acquisition"][0]["channel"] == "Organic Social"
    assert body["campaigns"][0]["campaign"] == "founder-post"
    assert body["landing_pages"][0]["landingPage"] == "/"
    assert body["funnel_events"][0]["eventName"] == "sign_up"
    assert body["recommendations"] == ["Double down on x.com / social."]
