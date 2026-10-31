import json
import subprocess
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import feed, main
from app.feed_bridge import fetch_page
from app.twitter_cli import CliExecutionError, CliNotFoundError, CliTimeoutError, InvalidCliOutputError


def test_bridge_passes_real_cursor_and_returns_next_page():
    captured = {}

    class Client:
        def _graphql_get(self, operation, variables, features):
            captured.update(operation=operation, variables=variables)
            return {"data": {"home": {"home_timeline_urt": {"instructions": []}}}}

    def parse(payload, get_instructions):
        assert get_instructions(payload) == []
        return [SimpleNamespace(id="1"), SimpleNamespace(id="1"), SimpleNamespace(id="2")], "next"

    page = fetch_page(Client(), "previous", 20, parse_timeline=parse, serialize=lambda item: {"id": item.id}, features={})
    assert captured["operation"] == "HomeTimeline"
    assert captured["variables"]["cursor"] == "previous"
    assert page == {"tweets": [{"id": "1"}, {"id": "2"}], "next_cursor": "next", "has_more": True}


def test_bridge_rejects_changed_upstream_shape():
    client = SimpleNamespace(_graphql_get=lambda *args: {"data": {}})
    with pytest.raises(ValueError, match="unrecognized"):
        fetch_page(client, None, 20, parse_timeline=None, serialize=None, features={})


def test_feed_runner_sends_cursor_over_stdin(monkeypatch):
    monkeypatch.setattr(feed, "cli_python_command", lambda: ["/cli/python"])

    def run(command, **kwargs):
        assert command[0] == "/cli/python"
        assert command[-1].endswith("feed_bridge.py")
        assert json.loads(kwargs["input"]) == {"cursor": "opaque cursor +/=", "limit": 20}
        assert kwargs["timeout"] == 45
        return subprocess.CompletedProcess(command, 0, json.dumps({"tweets": [{"id": "1"}], "next_cursor": "next", "has_more": True}), "")

    monkeypatch.setattr(subprocess, "run", run)
    assert feed.fetch_feed_page("opaque cursor +/=")["next_cursor"] == "next"


@pytest.mark.parametrize("payload", ["invalid json", "[]", '{"tweets":[],"has_more":"yes"}', '{"tweets":[null],"has_more":false}'])
def test_feed_runner_rejects_bad_pages(monkeypatch, payload):
    monkeypatch.setattr(feed, "cli_python_command", lambda: ["python"])
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess([], 0, payload, ""))
    with pytest.raises(InvalidCliOutputError):
        feed.fetch_feed_page()


def test_repeated_cursor_ends_pagination(monkeypatch):
    monkeypatch.setattr(feed, "cli_python_command", lambda: ["python"])
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: subprocess.CompletedProcess([], 0, '{"tweets":[],"next_cursor":"same","has_more":true}', ""))
    assert feed.fetch_feed_page("same") == {"tweets": [], "next_cursor": None, "has_more": False}


def test_feed_api_passes_cursor_and_limits(monkeypatch):
    def fetch(cursor, limit):
        assert cursor == "opaque+/="
        assert limit == 30
        return {"tweets": [{"id": "1"}], "next_cursor": "next", "has_more": True}

    monkeypatch.setattr(main, "fetch_feed_page", fetch)
    client = TestClient(main.app)
    response = client.get("/api/feed", params={"cursor": "opaque+/=", "limit": 30})
    assert response.status_code == 200
    assert response.json()["next_cursor"] == "next"
    assert client.get("/api/feed?limit=0").status_code == 422
    assert client.get("/api/feed?limit=41").status_code == 422


@pytest.mark.parametrize("error,status", [(CliExecutionError, 502), (CliNotFoundError, 503), (CliTimeoutError, 504)])
def test_feed_api_shows_recoverable_upstream_errors(monkeypatch, error, status):
    def fetch(**kwargs):
        raise error("Try again")

    monkeypatch.setattr(main, "fetch_feed_page", fetch)
    response = TestClient(main.app).get("/api/feed")
    assert response.status_code == status
    assert response.json()["detail"] == "Try again"
