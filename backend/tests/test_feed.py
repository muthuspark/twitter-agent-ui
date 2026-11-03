import json
import subprocess
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import feed, main
from app.feed_bridge import fetch_page, serialize_feed_tweet


def test_feed_serialization_preserves_quote_language_for_filtering():
    tweet = SimpleNamespace(quoted_tweet=SimpleNamespace(lang="hi"))
    serialized = serialize_feed_tweet(tweet, lambda _: {"lang": "en", "quotedTweet": {"text": "नमस्ते"}})
    assert serialized["quotedTweet"]["lang"] == "hi"
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


def test_bridge_preserves_author_media_descriptions():
    url = "https://pbs.twimg.com/media/example.jpg"
    payload = {"data": {"home": {"home_timeline_urt": {"instructions": [
        {"media": [{"media_url_https": url, "ext_alt_text": "  A revenue chart  "},
                   {"media_url_https": "other", "ext_alt_text": None}]}
    ]}}}}
    client = SimpleNamespace(_graphql_get=lambda *args: payload)
    page = fetch_page(
        client, None, 20,
        parse_timeline=lambda *args: ([SimpleNamespace(id="1")], None),
        serialize=lambda tweet: {"id": tweet.id, "media": [{"url": url}, {"url": "other"}]},
        features={},
    )
    assert page["tweets"][0]["media"] == [
        {"url": url, "altText": "A revenue chart"}, {"url": "other"}
    ]


@pytest.mark.parametrize("shape", ["tweetResult", "threaded_conversation_with_injections_v2"])
def test_thread_bridge_requests_conversation_and_preserves_pagination(shape):
    captured = {}

    class Client:
        def _graphql_get(self, operation, variables, features, field_toggles):
            captured.update(operation=operation, variables=variables, toggles=field_toggles)
            data = {"tweetResult": {"result": {"timeline": {"instructions": []}}}} if shape == "tweetResult" else {shape: {"instructions": []}}
            return {"data": data}

    def parse(payload, get_instructions):
        assert get_instructions(payload) == []
        return [SimpleNamespace(id="123"), SimpleNamespace(id="456")], "next-thread-page"

    page = fetch_page(Client(), "thread-cursor", 20, tweet_id="123", parse_timeline=parse, serialize=lambda tweet: {"id": tweet.id}, features={})
    assert captured["operation"] == "TweetDetail"
    assert captured["variables"]["focalTweetId"] == "123"
    assert captured["variables"]["cursor"] == "thread-cursor"
    assert "latestControlAvailable" not in captured["variables"]
    assert captured["toggles"]["withArticleRichContentState"] is True
    assert page["next_cursor"] == "next-thread-page"


def test_thread_api_passes_post_and_cursor_and_rejects_invalid_ids(monkeypatch):
    def fetch(cursor, limit, tweet_id):
        assert tweet_id == "123"
        assert cursor == "reply-cursor"
        return {"tweets": [{"id": "123"}, {"id": "456"}], "next_cursor": "next", "has_more": True}

    monkeypatch.setattr(main, "fetch_feed_page", fetch)
    client = TestClient(main.app)
    response = client.get("/api/feed/thread/123", params={"cursor": "reply-cursor"})
    assert response.status_code == 200
    assert len(response.json()["tweets"]) == 2
    assert client.get("/api/feed/thread/not-a-post").status_code == 422
    assert client.get("/api/feed/thread/123?limit=100").status_code == 422


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
