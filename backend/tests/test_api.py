import pytest
from fastapi.testclient import TestClient

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
