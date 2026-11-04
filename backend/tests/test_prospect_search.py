import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import prospect_search, prospects, reddit_cli

NOW = "2026-11-04T00:00:00+00:00"
URL = "https://www.reddit.com/r/SaaS/comments/abc123/decisions/"


def source(**changes):
    return {"url": URL, "title": "We lose decisions", "text": "I run a team. We lose decisions in Slack.",
            "author": "founder", "published_at": "2026-11-03T00:00:00Z", "evidence_kind": "snippet",
            "collection_source": "exa", "caveats": ["Indexed excerpt"], **changes}


def test_exa_uses_server_key_domain_date_and_bounded_text(monkeypatch):
    monkeypatch.setenv("EXA_WEB_SEARCH_API", "test-secret")
    def request(method, url, **kwargs):
        assert method == "POST" and url == "https://api.exa.ai/search"
        assert kwargs["headers"] == {"x-api-key": "test-secret"}
        assert "cookies" not in kwargs and kwargs["follow_redirects"] is False
        payload = kwargs["json"]
        assert payload["includeDomains"] == ["reddit.com"]
        assert payload["numResults"] == 10 and payload["startPublishedDate"].startswith("2026-11-02")
        assert payload["contents"]["text"]["maxCharacters"] == 12000
        return httpx.Response(200, json={"results": [
            {"url": URL, "title": "Lost decisions", "text": "A real excerpt", "publishedDate": "2026-11-03T00:00:00Z"},
            {"url": "https://linkedin.com/posts/123", "text": "Ignore"},
            {"url": "https://reddit.com/r/SaaS", "text": "Ignore"},
        ]}, request=httpx.Request(method, url))
    monkeypatch.setattr(prospect_search.httpx, "request", request)
    result = prospect_search.reddit("decisions", NOW)
    assert len(result) == 1 and result[0]["evidence_kind"] == "snippet"
    assert result[0]["collection_source"] == "exa"


def test_missing_key_never_accesses_network(monkeypatch):
    monkeypatch.delenv("EXA_WEB_SEARCH_API", raising=False)
    monkeypatch.setattr(prospect_search.httpx, "request", lambda *a, **k: pytest.fail("No request without key"))
    assert not prospect_search.status()["configured"]
    with pytest.raises(prospect_search.SearchError, match="EXA_WEB_SEARCH_API"):
        prospect_search.reddit("query", NOW)


@pytest.mark.parametrize("code", [401, 402, 429, 500])
def test_errors_never_expose_key_or_response_body(monkeypatch, code):
    monkeypatch.setenv("EXA_WEB_SEARCH_API", "test-secret")
    monkeypatch.setattr(prospect_search.httpx, "request", lambda method, url, **kwargs:
        httpx.Response(code, text="private diagnostic test-secret", request=httpx.Request(method, url)))
    with pytest.raises(prospect_search.SearchError) as error:
        prospect_search.reddit("query", NOW)
    assert "test-secret" not in str(error.value) and "private diagnostic" not in str(error.value)


def test_hn_uses_public_search_and_comment_author(monkeypatch):
    def request(method, url, **kwargs):
        assert method == "GET" and url.startswith("https://hn.algolia.com/")
        assert "headers" not in kwargs and "cookies" not in kwargs
        assert kwargs["params"]["hitsPerPage"] == 10
        return httpx.Response(200, json={"hits": [{"objectID": "123", "story_title": "Ask HN",
            "comment_text": "<p>I lose &amp; forget decisions.</p>", "author": "commenter", "created_at": NOW}]},
            request=httpx.Request(method, url))
    monkeypatch.setattr(prospect_search.httpx, "request", request)
    result = prospect_search.hackernews('"decisions"', NOW)
    assert result[0]["url"] == "https://news.ycombinator.com/item?id=123"
    assert result[0]["author"] == "commenter" and "I lose & forget decisions." in result[0]["text"]


@pytest.mark.parametrize("quote,personal", [("We lose decisions in Slack.", True), ("Invented pain", False)])
def test_classification_verifies_exact_quote_preserves_source_metadata(monkeypatch, quote, personal):
    monkeypatch.setattr(prospect_search, "reddit", lambda *args: [source()])
    def classify(system, payload, schema, **kwargs):
        assert not kwargs.get("web_search")
        return json.dumps({"posts": [{"id": "0", "quote": quote, "context": "Work problem",
            "lead_type": "buyer", "personal_pain": True, "buyer_role_evidence": "I run a team",
            "explicit_solution_request": False, "caveats": []}]})
    monkeypatch.setattr(prospects, "_run_codex", classify)
    seen = set()
    posts, coverage, _ = prospects.collect_public_query("reddit", "query", seen, NOW)
    assert posts[0]["personal_pain"] is personal
    assert posts[0]["author"] == "founder" and posts[0]["evidence_kind"] == "snippet"
    assert coverage["provider"] == "exa" and coverage["status"] == "searched"
    assert prospects.collect_public_query("reddit", "next query", seen, NOW)[0] == []


def test_public_source_failure_preserves_partial_coverage(monkeypatch):
    monkeypatch.setattr(prospect_search, "reddit", lambda *a: (_ for _ in ()).throw(prospect_search.SearchError("Exa unavailable")))
    posts, coverage, warnings = prospects.collect_public_query("reddit", "query", set(), NOW)
    assert not posts and coverage["status"] == "unavailable" and warnings


def test_research_and_status_never_access_browser(monkeypatch, tmp_path):
    monkeypatch.setenv("PROSPECTS_DB_PATH", str(tmp_path / "research.db"))
    for name in ("connection_status", "search", "read", "close_research"):
        monkeypatch.setattr(reddit_cli, name, lambda *a, **k: pytest.fail("Browser session must not be touched"))
    monkeypatch.setattr(prospects, "source_snapshot", lambda: {"evidence": [], "warnings": []})
    monkeypatch.setattr(prospect_search, "reddit", lambda *a: [])
    monkeypatch.setattr(prospect_search, "hackernews", lambda *a: [])
    monkeypatch.setattr(prospect_search, "communities", lambda *a: [])
    monkeypatch.setattr(prospects, "research_group", lambda group, now: {
        "posts": [{**source(url=f"https://x.com/founder/status/{index}", published_at=date),
                   "quote": "We lose decisions", "lead_type": "discussion", "personal_pain": False,
                   "buyer_role_evidence": "", "explicit_solution_request": False}
                  for index, date in enumerate(("2026-11-03T00:00:00Z", "2026-11-01T00:00:00Z", "", "2026-11-05T00:00:00Z"), 1)],
        "queries": [{"query": q["query"], "status": "searched", "finding": "Done"} for q in group], "warnings": []})
    monkeypatch.setattr(prospects, "search_product_code", lambda *a: [])
    monkeypatch.setattr(prospects, "assess_posts", lambda *a: [])
    run = {"id": "public", "status": "running", "started_at": NOW, "queries": [
        {**q, "status": "pending"} for q in prospects.QUERIES], "posts": [], "warnings": [], "error": ""}
    prospects.execute_run(run)
    assert run["status"] == "complete"
    assert [post["url"] for post in run["posts"]] == ["https://x.com/founder/status/1"]
    assert all(q["reddit"]["provider"] == "exa" and q["hackernews"]["provider"] == "hn_algolia" for q in run["queries"])
    from app.main import app
    response = TestClient(app).get("/api/prospects/sources/research/status")
    assert response.status_code == 200 and "username" not in response.json()


@pytest.mark.parametrize("date,expected", [
    ("2026-11-02T00:00:00Z", True),
    ("2026-11-01T23:59:59Z", False),
    ("2026-11-04T00:00:00Z", True),
    ("2026-11-04T00:00:01Z", False),
    ("2026-11-02T05:30:00+05:30", True),
    ("", False), (None, False), ("yesterday", False),
])
def test_discovery_window_is_strictly_last_48_hours(date, expected):
    assert prospect_search.within_window(date, NOW) is expected
