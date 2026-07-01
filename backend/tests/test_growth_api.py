from fastapi.testclient import TestClient

from app.twitter_cli import CliResult


def test_growth_discover_returns_candidates(monkeypatch):
    from app import main

    def fake_run(preset, options):
        assert preset == "search"
        assert options["query"] == "AI agents startups"
        return CliResult(
            command=["twitter", "search", "AI agents startups", "--max", "2", "--json"],
            data={
                "ok": True,
                "data": [
                    {
                        "id": "123",
                        "text": "AI agents need product taste",
                        "author": {"screenName": "founder"},
                        "metrics": {"likes": 3, "replies": 0},
                    }
                ],
            },
        )

    monkeypatch.setattr(main, "run_twitter_command", fake_run)
    client = TestClient(main.app)

    response = client.post("/api/growth/discover", json={"query": "AI agents startups", "max": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["command"] == ["twitter", "search", "AI agents startups", "--max", "2", "--json"]
    assert body["candidates"][0]["id"] == "123"


def test_growth_discover_excludes_already_commented_posts(monkeypatch, tmp_path):
    from app import main

    store = main.GrowthStore(tmp_path / "growth.sqlite3")
    store.record_action(
        recommendation_id=1,
        action="comment",
        tweet_id="already-commented",
        comment_text="I replied here already",
        status="approved",
        command=["twitter", "reply", "already-commented", "I replied here already", "--json"],
        result={"ok": True},
    )

    def fake_run(preset, options):
        return CliResult(
            command=["twitter", "search", "AI agents", "--max", "2", "--json"],
            data={
                "ok": True,
                "data": [
                    {
                        "id": "already-commented",
                        "text": "Do not show me",
                        "author": {"screenName": "one"},
                        "metrics": {},
                    },
                    {
                        "id": "fresh",
                        "text": "Show me",
                        "author": {"screenName": "two"},
                        "metrics": {},
                    },
                ],
            },
        )

    monkeypatch.setattr(main, "run_twitter_command", fake_run)
    monkeypatch.setattr(main, "get_growth_store", lambda: store)
    client = TestClient(main.app)

    response = client.post("/api/growth/discover", json={"query": "AI agents", "max": 2})

    assert response.status_code == 200
    assert [candidate["id"] for candidate in response.json()["candidates"]] == ["fresh"]


def test_growth_analyze_saves_recommendations(monkeypatch, tmp_path):
    from app import main

    def fake_store():
        return main.GrowthStore(tmp_path / "growth.sqlite3")

    def fake_analyze(candidates, profile_focus, preference_memory=None):
        assert candidates[0]["id"] == "123"
        assert "AI" in profile_focus
        assert preference_memory["summary"] == "No preference memory recorded yet."
        return [
            {
                "tweet_id": "123",
                "action": "like",
                "confidence": 81,
                "reason": "Relevant low-reply AI post.",
                "comment": "",
                "risk": "low",
            }
        ]

    monkeypatch.setattr(main, "get_growth_store", fake_store)
    monkeypatch.setattr(main, "analyze_candidates", fake_analyze)
    client = TestClient(main.app)

    response = client.post(
        "/api/growth/analyze",
        json={
            "profile_focus": "AI, startups, software engineering, personal brand",
            "candidates": [{"id": "123", "text": "AI agents", "author": {}, "metrics": {}}],
        },
    )

    assert response.status_code == 200
    recommendation = response.json()["recommendations"][0]
    assert recommendation["id"] == 1
    assert recommendation["action"] == "like"


def test_growth_approve_executes_single_action(monkeypatch, tmp_path):
    from app import main

    def fake_store():
        return main.GrowthStore(tmp_path / "growth.sqlite3")

    def fake_run(action, tweet_id, comment_text=None):
        assert action == "comment"
        assert tweet_id == "123"
        assert comment_text == "Useful point"
        return CliResult(
            command=["twitter", "reply", "123", "Useful point", "--json"],
            data={"ok": True},
        )

    monkeypatch.setattr(main, "get_growth_store", fake_store)
    monkeypatch.setattr(main, "run_growth_action", fake_run)
    client = TestClient(main.app)

    response = client.post(
        "/api/growth/approve",
        json={
            "recommendation_id": 7,
            "action": "comment",
            "tweet_id": "123",
            "comment_text": "Useful point",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["record"]["status"] == "approved"
    assert body["record"]["command"] == ["twitter", "reply", "123", "Useful point", "--json"]


def test_growth_approve_records_source_metadata(monkeypatch, tmp_path):
    from app import main

    store = main.GrowthStore(tmp_path / "growth.sqlite3")

    def fake_run(action, tweet_id, comment_text=None):
        return CliResult(command=["twitter", "reply", tweet_id, comment_text, "--json"], data={"ok": True})

    monkeypatch.setattr(main, "get_growth_store", lambda: store)
    monkeypatch.setattr(main, "run_growth_action", fake_run)
    client = TestClient(main.app)

    response = client.post(
        "/api/growth/approve",
        json={
            "recommendation_id": 7,
            "action": "comment",
            "tweet_id": "123",
            "comment_text": "Useful point",
            "metadata": {
                "source_tweet": {"text": "AI agent question", "author": {"screenName": "ada"}},
                "recommendation_reason": "Relevant technical question.",
                "comment_drafts": ["Useful point", "Alternative", "Third"],
            },
        },
    )

    assert response.status_code == 200
    history = store.history()
    assert history[0]["metadata"]["source_tweet"]["author"]["screenName"] == "ada"
    assert history[0]["metadata"]["comment_drafts"] == ["Useful point", "Alternative", "Third"]


def test_growth_analyze_receives_preference_memory(monkeypatch, tmp_path):
    from app import main

    store = main.GrowthStore(tmp_path / "growth.sqlite3")
    store.record_action(
        recommendation_id=1,
        action="comment",
        tweet_id="old",
        comment_text="Evals are the bottleneck.",
        status="approved",
        command=["twitter", "reply", "old", "Evals are the bottleneck.", "--json"],
        result={"ok": True},
        metadata={"source_tweet": {"text": "AI agents"}, "recommendation_reason": "Technical"},
    )
    captured = {}

    def fake_analyze(candidates, profile_focus, preference_memory=None):
        captured["memory"] = preference_memory
        return [
            {
                "tweet_id": "123",
                "action": "like",
                "confidence": 81,
                "reason": "Relevant low-reply AI post.",
                "comment": "",
                "risk": "low",
            }
        ]

    monkeypatch.setattr(main, "get_growth_store", lambda: store)
    monkeypatch.setattr(main, "analyze_candidates", fake_analyze)
    client = TestClient(main.app)

    response = client.post(
        "/api/growth/analyze",
        json={
            "profile_focus": "AI, startups, software engineering, personal brand",
            "candidates": [{"id": "123", "text": "AI agents", "author": {}, "metrics": {}}],
        },
    )

    assert response.status_code == 200
    assert "Evals are the bottleneck" in captured["memory"]["summary"]


def test_growth_approve_skip_records_without_cli_execution(monkeypatch, tmp_path):
    from app import main

    def fake_store():
        return main.GrowthStore(tmp_path / "growth.sqlite3")

    def fail_run(action, tweet_id, comment_text=None):
        raise AssertionError("skip approval must not execute twitter CLI")

    monkeypatch.setattr(main, "get_growth_store", fake_store)
    monkeypatch.setattr(main, "run_growth_action", fail_run)
    client = TestClient(main.app)

    response = client.post(
        "/api/growth/approve",
        json={"recommendation_id": 9, "action": "skip", "tweet_id": "123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["record"]["status"] == "approved"
    assert body["record"]["command"] == []
    assert body["record"]["result"] == {"ok": True, "skipped": True}


def test_growth_reject_records_without_cli_execution(monkeypatch, tmp_path):
    from app import main

    def fake_store():
        return main.GrowthStore(tmp_path / "growth.sqlite3")

    monkeypatch.setattr(main, "get_growth_store", fake_store)
    client = TestClient(main.app)

    response = client.post(
        "/api/growth/reject",
        json={
            "recommendation_id": 3,
            "action": "like",
            "tweet_id": "123",
            "metadata": {"source_tweet": {"text": "Rejected source"}},
        },
    )

    assert response.status_code == 200
    assert response.json()["record"]["status"] == "rejected"
    assert fake_store().history()[0]["metadata"]["source_tweet"]["text"] == "Rejected source"


def test_growth_history_returns_records(monkeypatch, tmp_path):
    from app import main

    store = main.GrowthStore(tmp_path / "growth.sqlite3")
    store.record_action(
        recommendation_id=1,
        action="like",
        tweet_id="123",
        comment_text="",
        status="approved",
        command=["twitter", "like", "123", "--json"],
        result={"ok": True},
    )

    monkeypatch.setattr(main, "get_growth_store", lambda: store)
    client = TestClient(main.app)

    response = client.get("/api/growth/history")

    assert response.status_code == 200
    assert response.json()["history"][0]["tweet_id"] == "123"
