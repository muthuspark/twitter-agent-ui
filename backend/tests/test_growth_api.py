from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
import json
import subprocess

from app.twitter_cli import CliResult


def essay_draft(kwargs):
    return {"post_text": "A solo operator can test this business activity.",
            "essay_connection": "Tests the essay's claim about individual execution capacity.",
            "source_ids": [kwargs["research_sources"][0]["id"]]}


def test_bookmark_executes_cli_and_records_history(monkeypatch, tmp_path):
    from app import main

    store = main.GrowthStore(tmp_path / "growth.sqlite3")
    monkeypatch.setattr(main, "get_growth_store", lambda: store)

    def fake_run(command, **kwargs):
        assert command == ["twitter", "bookmark", "123", "--json"]
        return subprocess.CompletedProcess(command, 0, json.dumps({"ok": True}), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = TestClient(main.app)
    response = client.post("/api/growth/approve", json={"action": "bookmark", "tweet_id": "123"})

    assert response.status_code == 200
    assert response.json()["record"]["action"] == "bookmark"
    assert store.history()[0]["command"] == ["twitter", "bookmark", "123", "--json"]
    assert store.history()[0]["status"] == "approved"

    response = client.post("/api/growth/approve", json={"action": "bookmark", "tweet_id": " "})
    assert response.status_code == 422
    assert len(store.history()) == 1


def test_growth_discover_returns_candidates(monkeypatch):
    from app import main

    def fake_run(query, limit):
        assert query == "AI agents startups"
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

    monkeypatch.setattr(main, "search_tweets", fake_run)
    client = TestClient(main.app)

    response = client.post("/api/growth/discover", json={"query": "AI agents startups", "max": 2})

    assert response.status_code == 200
    body = response.json()
    assert body["command"] == ["twitter", "search", "AI agents startups", "--max", "2", "--json"]
    assert body["candidates"][0]["id"] == "123"


def test_growth_discover_uses_random_jovis_query_when_query_is_empty(monkeypatch):
    from app import main

    monkeypatch.setattr(main, "resolve_search_query", lambda query: "data team bottleneck")

    def fake_run(query, limit):
        assert query == "data team bottleneck"
        return CliResult(
            command=["twitter", "search", "data team bottleneck", "--max", "2", "--json"],
            data={"ok": True, "data": []},
        )

    monkeypatch.setattr(main, "search_tweets", fake_run)
    client = TestClient(main.app)

    response = client.post("/api/growth/discover", json={"query": "", "max": 2})

    assert response.status_code == 200
    assert response.json()["command"] == ["twitter", "search", "data team bottleneck", "--max", "2", "--json"]


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

    def fake_run(query, limit):
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

    monkeypatch.setattr(main, "search_tweets", fake_run)
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


def test_post_ideas_returns_generated_ideas(monkeypatch, tmp_path):
    from app import main

    store = main.GrowthStore(tmp_path / "growth.sqlite3")

    def fake_generate(profile_focus, themes, preference_memory=None, count=5, recent_liked_posts=None, recent_bookmarked_posts=None, **kwargs):
        assert "Jovis" in profile_focus
        assert "CRM" in themes
        assert preference_memory["summary"] == "No preference memory recorded yet."
        assert count == 3
        assert recent_liked_posts[0]["id"] == "liked-1"
        assert recent_bookmarked_posts[0]["id"] == "saved-1"
        return [
            {
                "title": "CRM answers",
                "angle": "CRM data is trapped.",
                "audience": "RevOps",
                "rationale": "Relevant buyer pain.",
                "cta": "See Jovis",
                "post_text": "Your CRM already knows which deals are stuck.",
                "essay_connection": "Tests whether a solo operator can automate customer analysis.",
                "source_ids": [kwargs["research_sources"][0]["id"]],
            }
        ]

    monkeypatch.setattr(main, "get_growth_store", lambda: store)
    monkeypatch.setattr(main, "generate_post_ideas", fake_generate)
    monkeypatch.setattr(main, "fetch_recent_liked_posts", lambda **kwargs: [{"id": "liked-1", "text": "CRM answers should be instant", "createdAtISO": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}])
    monkeypatch.setattr(main, "fetch_recent_bookmarked_posts", lambda **kwargs: [{"id": "saved-1", "text": "A useful saved post", "createdAtISO": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}])
    client = TestClient(main.app)

    response = client.post(
        "/api/posts/ideas",
        json={"source_mode": "interests", "profile_focus": "Jovis buyers", "themes": "CRM analytics", "count": 3},
    )

    assert response.status_code == 200
    assert response.json()["ideas"][0]["title"] == "CRM answers"
    assert response.json()["liked_posts_used"] == 1
    assert response.json()["bookmarked_posts_used"] == 1
    assert "posts published" in response.json()["context_warning"]


def test_approve_post_executes_post_and_records_history(monkeypatch, tmp_path):
    from app import main

    store = main.GrowthStore(tmp_path / "growth.sqlite3")

    def fake_run(post_text):
        assert post_text == "Approved post"
        return CliResult(command=["twitter", "post", "Approved post", "--json"], data={"ok": True, "id": "post-1"})

    monkeypatch.setattr(main, "get_growth_store", lambda: store)
    monkeypatch.setattr(main, "run_post_action", fake_run)
    client = TestClient(main.app)

    response = client.post(
        "/api/posts/approve",
        json={
            "post_text": "Approved post",
            "metadata": {"post_idea": {"title": "CRM answers"}},
        },
    )

    assert response.status_code == 200
    record = response.json()["record"]
    assert record["action"] == "post"
    assert record["tweet_id"] == "post-1"
    assert record["comment_text"] == "Approved post"
    assert record["metadata"]["post_idea"]["title"] == "CRM answers"


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


def test_post_ideas_uses_local_likes_when_x_is_unavailable(monkeypatch, tmp_path):
    from app import main
    from app.twitter_cli import CliExecutionError

    store = main.GrowthStore(tmp_path / "growth.sqlite3")
    for action, status, tweet_id in [("like", "approved", "123"), ("like", "rejected", "456"), ("bookmark", "approved", "789"), ("like", "approved", "123")]:
        store.record_action(
            recommendation_id=None, action=action, tweet_id=tweet_id,
            comment_text="", status=status, command=[], result={},
            metadata={"source_tweet": {"text": "Useful local post"}},
        )

    def fail_fetch(**kwargs):
        raise CliExecutionError("Session expired")

    def fake_generate(*args, **kwargs):
        assert kwargs["recent_liked_posts"][0]["id"] == "123"
        assert kwargs["recent_liked_posts"][0]["timestamp_basis"] == "action_time"
        assert kwargs["recent_bookmarked_posts"][0]["id"] == "789"
        return [essay_draft(kwargs)]

    monkeypatch.setattr(main, "get_growth_store", lambda: store)
    monkeypatch.setattr(main, "fetch_recent_liked_posts", fail_fetch)
    monkeypatch.setattr(main, "fetch_recent_bookmarked_posts", fail_fetch)
    monkeypatch.setattr(main, "generate_post_ideas", fake_generate)
    response = TestClient(main.app).post("/api/posts/ideas", json={"source_mode": "interests"})
    assert response.status_code == 200
    assert response.json()["liked_posts_used"] == 1
    assert response.json()["likes_warning"]


def test_post_ideas_handles_empty_and_duplicate_likes(monkeypatch, tmp_path):
    from app import main

    store = main.GrowthStore(tmp_path / "growth.sqlite3")
    monkeypatch.setattr(main, "get_growth_store", lambda: store)
    monkeypatch.setattr(main, "generate_post_ideas", lambda *args, **kwargs: [essay_draft(kwargs)])
    monkeypatch.setattr(main, "fetch_recent_liked_posts", lambda **kwargs: [])
    monkeypatch.setattr(main, "fetch_recent_bookmarked_posts", lambda **kwargs: [])
    client = TestClient(main.app)
    assert client.post("/api/posts/ideas", json={"source_mode": "interests"}).status_code == 422
    monkeypatch.setattr(main, "fetch_recent_liked_posts", lambda **kwargs: [{"id": "123", "text": "Useful", "createdAtISO": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}] * 2)
    body = client.post("/api/posts/ideas", json={"source_mode": "interests"}).json()
    assert body["liked_posts_used"] == 1
    assert "posts published" in body["context_warning"]


def test_post_ideas_explicit_interests_counts_overlapping_sources_once(monkeypatch, tmp_path):
    from app import main

    source = {"id": "same", "text": "Automating work in a one-person workshop", "createdAtISO": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}
    monkeypatch.setattr(main, "get_growth_store", lambda: main.GrowthStore(tmp_path / "growth.sqlite3"))
    monkeypatch.setattr(main, "fetch_recent_liked_posts", lambda **kwargs: [source])
    monkeypatch.setattr(main, "fetch_recent_bookmarked_posts", lambda **kwargs: [source])

    def generate(profile_focus, themes, **kwargs):
        assert profile_focus == ""
        assert themes == ""
        assert kwargs["recent_liked_posts"][0]["id"] == "same"
        assert kwargs["recent_bookmarked_posts"][0]["id"] == "same"
        return [essay_draft(kwargs)]

    monkeypatch.setattr(main, "generate_post_ideas", generate)
    response = TestClient(main.app).post("/api/posts/ideas", json={"source_mode": "interests"})
    assert response.status_code == 200
    assert response.json()["liked_posts_used"] == 1
    assert response.json()["bookmarked_posts_used"] == 1
    assert response.json()["unique_posts_used"] == 1


def test_post_ideas_does_not_generate_without_recent_context(monkeypatch, tmp_path):
    from app import main

    monkeypatch.setattr(main, "get_growth_store", lambda: main.GrowthStore(tmp_path / "growth.sqlite3"))
    monkeypatch.setattr(main, "fetch_recent_liked_posts", lambda **kwargs: [])
    monkeypatch.setattr(main, "fetch_recent_bookmarked_posts", lambda **kwargs: [])

    def unexpected(*args, **kwargs):
        pytest.fail("Generation should not run without interest context")

    monkeypatch.setattr(main, "generate_post_ideas", unexpected)
    response = TestClient(main.app).post("/api/posts/ideas", json={"source_mode": "interests", "themes": "Generic AI content"})
    assert response.status_code == 422


def test_image_generation_routes_are_removed():
    from app import main
    client = TestClient(main.app)
    assert client.post('/api/posts/images', json={'post_text': 'Draft'}).status_code == 404
    assert client.get('/api/posts/images/' + 'a' * 32).status_code == 404
    assert client.get('/api/posts/images/' + 'a' * 32 + '/file').status_code == 404


def test_legacy_image_request_does_not_silently_publish_text(monkeypatch):
    from app import main
    def unexpected(*args, **kwargs):
        raise AssertionError('An obsolete attachment request must not publish a post')
    monkeypatch.setattr(main, 'run_post_action', unexpected)
    response = TestClient(main.app).post('/api/posts/approve', json={
        'post_text': 'Draft from an older browser tab', 'image_id': 'a' * 32,
    })
    assert response.status_code == 422
    assert 'no longer supported' in response.json()['detail']


def test_text_post_with_cookie_progress_records_success_once(monkeypatch, tmp_path):
    from app import main
    store = main.GrowthStore(tmp_path / 'growth.sqlite3')
    monkeypatch.setattr(main, 'get_growth_store', lambda: store)
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        assert command == ['twitter', 'post', 'Approved post', '--json']
        return subprocess.CompletedProcess(command, 0,
            'Getting Twitter cookies...\n' + json.dumps({'ok': True, 'data': {'id': '123', 'success': True}}), '')
    monkeypatch.setattr(subprocess, 'run', run)
    response = TestClient(main.app).post('/api/posts/approve', json={'post_text': 'Approved post'})
    assert response.status_code == 200
    assert response.json()['record']['tweet_id'] == '123'
    assert len(calls) == len(store.history()) == 1
