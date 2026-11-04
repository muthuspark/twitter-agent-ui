from datetime import datetime, timezone
import json
import subprocess
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import reddit_cli, prospects


@pytest.fixture(autouse=True)
def legacy_client(monkeypatch):
    monkeypatch.setenv("REDDIT_CLI_BACKEND", "rdt")


def raw_post(post_id="abc123", **changes):
    return {"id": post_id, "permalink": f"/r/SaaS/comments/{post_id}/lost_decisions/",
            "title": "We lose decisions", "author": "founder", "subreddit": "SaaS",
            "selftext": "I run a team. We cannot find our decisions. What tool helps?",
            "created_utc": 1793491200, "num_comments": 2, **changes}


def envelope(data):
    return {"ok": True, "schema_version": "1", "data": data}


@pytest.fixture
def cli(monkeypatch):
    calls = []
    response = {"stdout": json.dumps(envelope([])), "returncode": 0, "stderr": "private diagnostics"}
    monkeypatch.setattr(reddit_cli, "executable", lambda: "/tools/rdt")
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(**response)
    monkeypatch.setattr(reddit_cli.subprocess, "run", run)
    return response, calls


def test_search_uses_bounded_json_command_and_public_fields(cli):
    response, calls = cli
    response["stdout"] = json.dumps(envelope([raw_post(cookie="secret")]))
    result = reddit_cli.search('"decisions" "buried"')
    command, options = calls[0]
    assert command == ["/tools/rdt", "search", '"decisions" "buried"', "--sort", "relevance", "--time", "month", "--limit", "10", "--compact", "--json"]
    assert options["timeout"] == 60 and not options["check"]
    assert "shell" not in options
    assert result[0]["published_at"] == datetime.fromtimestamp(1793491200, timezone.utc).isoformat()
    assert "cookie" not in result[0]
    response["stdout"] = json.dumps(envelope([]))
    assert reddit_cli.search("no results") == []


@pytest.mark.parametrize("output,code", [
    ("not JSON: secret", "invalid_output"),
    (json.dumps({"ok": True, "schema_version": "2", "data": []}), "invalid_output"),
    (json.dumps({"ok": False, "schema_version": "1", "error": {"code": "not_authenticated", "message": "secret"}}), "not_authenticated"),
    (json.dumps({"ok": False, "schema_version": "1", "error": {"code": "rate_limited", "message": "secret"}}), "rate_limited"),
    (json.dumps({"ok": False, "schema_version": "1", "error": {"code": "forbidden", "message": "secret"}}), "forbidden"),
    (json.dumps(envelope({})), "invalid_output"),
])
def test_errors_are_safe_and_typed(cli, output, code):
    cli[0]["stdout"] = output
    with pytest.raises(reddit_cli.RedditCliError) as caught:
        reddit_cli.search("query")
    assert caught.value.code == code
    assert "secret" not in str(caught.value)
    assert "private diagnostics" not in str(caught.value)


def test_nonzero_exit_cannot_be_success(cli):
    cli[0]["returncode"] = 1
    with pytest.raises(reddit_cli.RedditCliError, match="could not complete"):
        reddit_cli.search("query")


def test_missing_cli_and_timeout_are_safe(monkeypatch):
    monkeypatch.setattr(reddit_cli, "executable", lambda: None)
    assert reddit_cli.connection_status()["installed"] is False
    monkeypatch.setattr(reddit_cli, "executable", lambda: "/tools/rdt")
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("secret", 60, output="secret")
    monkeypatch.setattr(reddit_cli.subprocess, "run", timeout)
    status = reddit_cli.connection_status()
    assert status["installed"] is True and status["authenticated"] is False
    assert "timed out" in status["message"] and "secret" not in json.dumps(status)


def test_status_whitelists_fields_and_endpoint(cli):
    cli[0]["stdout"] = json.dumps(envelope({"authenticated": True, "username": "founder", "cookies": "secret", "credential_file": "/private"}))
    status = reddit_cli.connection_status()
    assert status == {"installed": True, "authenticated": True, "username": "founder", "message": "Reddit session connected."}
    from app.main import app
    assert TestClient(app).get("/api/prospects/sources/reddit/status").json() == status
    cli[0]["stdout"] = json.dumps(envelope({"authenticated": False, "error": "secret"}))
    status = reddit_cli.connection_status()
    assert not status["authenticated"] and "secret" not in json.dumps(status)


@pytest.mark.parametrize("error,expected", [
    ("HTTP 403 Forbidden secret", "HTTP 403"),
    ("HTTP 401 Unauthorized secret", "rejected the saved session"),
    ("HTTP 429 rate limited secret", "rate limited"),
    ("Network failure secret", "cookies were found"),
])
def test_status_distinguishes_cookie_presence_from_live_authentication(cli, error, expected):
    cli[0]["stdout"] = json.dumps(envelope({"authenticated": False, "cookie_count": 15, "error": error}))
    status = reddit_cli.connection_status()
    assert status["installed"] and not status["authenticated"]
    assert expected in status["message"]
    assert "secret" not in json.dumps(status)


def test_read_normalizes_041_raw_listings_and_bounds_comments(cli):
    comments = [{"kind": "t1", "data": {"author": "reader", "body": f"comment {i}", "private": "secret"}} for i in range(30)]
    comments.append({"kind": "more", "data": {"count": 10}})
    cli[0]["stdout"] = json.dumps(envelope([
        {"data": {"children": [{"kind": "t3", "data": raw_post()}]}},
        {"data": {"children": comments}},
    ]))
    result = reddit_cli.read("abc123")
    assert result["post"]["id"] == "abc123"
    assert len(result["comments"]) == 25 and result["comments_incomplete"]
    assert "secret" not in json.dumps(result)
    assert cli[1][0][0] == ["/tools/rdt", "read", "abc123", "--limit", "25", "--json"]
    with pytest.raises(reddit_cli.RedditCliError):
        reddit_cli.read("--help")


@pytest.mark.parametrize("changes", [{"created_utc": "unknown"}, {"created_utc": 999999999999999}, {"created_utc": 0}])
def test_invalid_dates_stay_unknown(cli, changes):
    cli[0]["stdout"] = json.dumps(envelope([raw_post(**changes)]))
    assert reddit_cli.search("query")[0]["published_at"] == ""


def source(post_id="abc123", **changes):
    return reddit_cli._post(raw_post(post_id, **changes))


@pytest.fixture
def collector(monkeypatch):
    fetched = []
    monkeypatch.setattr(reddit_cli, "search", lambda query: [source(), source("def456")])
    def read(post_id):
        fetched.append(post_id)
        return {"post": source(post_id), "comments": [{"author": "reader", "body": "I am a CEO"}], "comments_incomplete": True}
    monkeypatch.setattr(reddit_cli, "read", read)
    def model(system, payload, schema, **kwargs):
        assert not kwargs.get("web_search")
        if "post_ids" in schema["properties"]:
            return json.dumps({"post_ids": ["abc123", "abc123", "invented", "def456"]})
        return json.dumps({"posts": [{"id": item["post"]["id"], "quote": "We cannot find our decisions.",
            "context": "Needs a decision tool", "lead_type": "buyer", "personal_pain": True,
            "buyer_role_evidence": "I run a team", "explicit_solution_request": True, "caveats": []} for item in payload["details"]]})
    monkeypatch.setattr(prospects, "_run_codex", model)
    return fetched, model


def test_collector_preserves_cli_identity_quotes_dates_and_deduplicates(collector):
    seen = set()
    connection = {"authenticated": True}
    posts, coverage, warnings = prospects.collect_reddit_cli_query("decisions", seen, connection)
    assert coverage == {"status": "searched", "result_count": 2, "inspected_count": 2, "error": "", "web_fallback": "not_needed"}
    assert not warnings
    assert collector[0] == ["abc123", "def456"]
    assert all(p["collection_source"] == "reddit_cli" and p["author"] == "founder" for p in posts)
    assert all(p["quote"] in raw_post()["selftext"] for p in posts)
    assert all(p["caveats"] for p in posts)
    assert prospects.collect_reddit_cli_query("another query", seen, connection)[0] == []
    assert len(collector[0]) == 2


def test_hallucinated_quote_is_replaced_by_original_title(collector, monkeypatch):
    def model(*args, **kwargs):
        result = json.loads(collector[1](*args, **kwargs))
        for item in result.get("posts", []):
            item.update(quote="Invented buyer complaint", personal_pain=True)
        return json.dumps(result)
    monkeypatch.setattr(prospects, "_run_codex", model)
    posts, _, warnings = prospects.collect_reddit_cli_query("query", set(), {"authenticated": True})
    assert warnings
    assert all(p["quote"] == "We lose decisions" and not p["personal_pain"] for p in posts)


def test_analysis_failure_keeps_fetched_sources(collector, monkeypatch):
    def model(system, payload, schema, **kwargs):
        if "post_ids" in schema["properties"]:
            return collector[1](system, payload, schema, **kwargs)
        raise prospects.CodexError("private model diagnostic")
    monkeypatch.setattr(prospects, "_run_codex", model)
    posts, coverage, warnings = prospects.collect_reddit_cli_query("query", set(), {"authenticated": True})
    assert len(posts) == 2 and coverage["status"] == "partial"
    assert "private" not in json.dumps(warnings)


def test_rate_limit_stops_further_reddit_requests(collector, monkeypatch):
    def limited(post_id):
        raise reddit_cli.RedditCliError("rate_limited")
    monkeypatch.setattr(reddit_cli, "read", limited)
    connection = {"authenticated": True}
    _, coverage, _ = prospects.collect_reddit_cli_query("query", set(), connection)
    assert coverage["status"] == "partial" and not connection["authenticated"]
    monkeypatch.setattr(reddit_cli, "search", lambda *a: pytest.fail("Must stop after rate limiting"))
    assert prospects.collect_reddit_cli_query("next", set(), connection)[1]["status"] == "unavailable"


def test_selection_is_bounded_and_deleted_posts_are_skipped(collector, monkeypatch):
    monkeypatch.setattr(reddit_cli, "search", lambda query: [source(f"abc{i}") for i in range(8)] + [source("deleted", author="[deleted]")])
    def select(system, payload, schema, **kwargs):
        if "post_ids" in schema["properties"]:
            assert all(p["author"] != "[deleted]" for p in payload["posts"])
            return json.dumps({"post_ids": ["invented", *[f"abc{i}" for i in range(8)]]})
        return collector[1](system, payload, schema, **kwargs)
    monkeypatch.setattr(prospects, "_run_codex", select)
    posts, coverage, _ = prospects.collect_reddit_cli_query("query", set(), {"authenticated": True})
    assert len(posts) == coverage["inspected_count"] == 3
    assert collector[0] == ["abc0", "abc1", "abc2"]


def test_vendor_classification_is_excluded_even_without_pain_quote(collector, monkeypatch):
    def model(*args, **kwargs):
        result = json.loads(collector[1](*args, **kwargs))
        for item in result.get("posts", []):
            item.update(lead_type="vendor", quote="")
        return json.dumps(result)
    monkeypatch.setattr(prospects, "_run_codex", model)
    assert prospects.collect_reddit_cli_query("query", set(), {"authenticated": True})[0] == []


@pytest.fixture
def pipeline(monkeypatch, tmp_path):
    monkeypatch.setenv("PROSPECTS_DB_PATH", str(tmp_path / "prospects.sqlite3"))
    monkeypatch.setattr(prospects, "_ACTIVE", "reddit-run")
    monkeypatch.setattr(prospects, "source_snapshot", lambda: {"evidence": [], "warnings": []})
    monkeypatch.setattr(prospects, "search_product_code", lambda *args: [])
    monkeypatch.setattr(prospects, "assess_posts", lambda *args: [])
    monkeypatch.setattr(reddit_cli, "connection_status", lambda: {"authenticated": True, "message": "Connected"})
    # Exercise the retained legacy pipeline explicitly; production discovery uses public search.
    state = {"authenticated": True, "message": "Connected"}
    monkeypatch.setattr(prospects, "collect_reddit_query", lambda query, seen, _: prospects.collect_reddit_cli_query(query, seen, state))
    monkeypatch.setattr(prospects, "collect_public_query", lambda *args: ([], {
        "status": "searched", "result_count": 0, "inspected_count": 0, "error": "", "web_fallback": "not_needed"}, []))
    return {"id": "reddit-run", "status": "running", "started_at": "2026-11-03T00:00:00+00:00", "completed_at": "",
            "queries": [{**q, "status": "pending", "finding": ""} for q in prospects.QUERIES],
            "posts": [], "warnings": [], "error": ""}


def test_web_failure_keeps_cli_results_and_persists_before_web(pipeline, collector, monkeypatch):
    calls = []
    def web(group, now):
        calls.append(group)
        assert not any(q["reddit_fallback"] for q in group)
        with prospects.connection() as db:
            saved = json.loads(db.execute("SELECT payload FROM prospect_runs WHERE id = ?", ("reddit-run",)).fetchone()[0])
        assert len(saved["posts"]) == 2
        raise prospects.CodexError("Web unavailable")
    monkeypatch.setattr(prospects, "research_group", web)
    prospects.execute_run(pipeline)
    run = prospects.get_run("reddit-run")
    assert len(calls) == 5 and len(run["posts"]) == 2
    assert all(q["status"] == "searched" and q["reddit"]["status"] == "searched" for q in run["queries"])
    assert run["status"] == "partial"
    assert len(collector[0]) == 2


def test_fallback_is_per_query_and_does_not_claim_cli_success(pipeline, monkeypatch):
    first = prospects.QUERIES[0]["query"]
    def collect(query, *args):
        error = "Reddit search unavailable" if query == first else ""
        return [], {"status": "unavailable" if error else "searched", "result_count": 0,
                    "inspected_count": 0, "error": error, "web_fallback": "not_needed"}, [error] if error else []
    monkeypatch.setattr(prospects, "collect_reddit_query", collect)
    fallback_post = {**source(), "query": first, "quote": "We lose decisions", "lead_type": "buyer", "personal_pain": True,
                     "buyer_role_evidence": "I run a team", "explicit_solution_request": True, "evidence_kind": "full_post", "caveats": []}
    def web(group, now):
        return {"queries": [{"query": q["query"], "status": "searched", "finding": "Web search done"} for q in group],
                "posts": [dict(fallback_post), {**fallback_post, "url": source("notallowed")["url"], "query": prospects.QUERIES[1]["query"]}], "warnings": []}
    monkeypatch.setattr(prospects, "research_group", web)
    prospects.execute_run(pipeline)
    run = prospects.get_run("reddit-run")
    assert len(run["posts"]) == 1
    assert run["posts"][0]["collection_source"] == "web_fallback"
    coverage = run["queries"][0]["reddit"]
    assert coverage["status"] == "unavailable" and coverage["web_fallback"] == "attempted"
    assert run["status"] == "partial"
    assert all(q["reddit"]["web_fallback"] == "not_needed" for q in run["queries"][1:])


def test_empty_reddit_searches_are_complete_with_successful_web(pipeline, monkeypatch):
    monkeypatch.setattr(reddit_cli, "search", lambda query: [])
    def web(group, now):
        return {"queries": [{"query": q["query"], "status": "searched", "finding": "No leads"} for q in group], "posts": [], "warnings": []}
    monkeypatch.setattr(prospects, "research_group", web)
    prospects.execute_run(pipeline)
    run = prospects.get_run("reddit-run")
    assert run["status"] == "complete" and not run["posts"]
    assert all(q["reddit"]["status"] == "searched" and q["reddit"]["result_count"] == 0 for q in run["queries"])


def test_reddit_web_fallback_instruction_is_explicit(monkeypatch):
    def model(system, payload, schema, **kwargs):
        assert kwargs["web_search"] is True
        assert payload["reddit_fallback_queries"] == ["failed query"]
        assert "Search Reddit ONLY" in system
        return json.dumps({"queries": [], "posts": [], "warnings": []})
    monkeypatch.setattr(prospects, "_run_codex", model)
    prospects.research_group([{"query": "failed query", "reddit_fallback": True}, {"query": "healthy query"}], "now")


@pytest.mark.parametrize("code", ["rate_limited", "forbidden", "not_authenticated"])
def test_source_failure_cannot_be_normalized_to_complete(pipeline, monkeypatch, code):
    calls = []
    def search(query):
        calls.append(query)
        raise reddit_cli.RedditCliError(code)
    monkeypatch.setattr(reddit_cli, "search", search)
    monkeypatch.setattr(prospects, "research_group", lambda group, now: {
        "queries": [{"query": q["query"], "status": "searched", "finding": "Web fallback"} for q in group], "posts": [], "warnings": []})
    prospects.execute_run(pipeline)
    run = prospects.get_run("reddit-run")
    assert len(calls) == 1
    assert run["status"] == prospects.run_progress(run)["status"] == "partial"
    assert all(q["reddit"]["status"] == "unavailable" for q in run["queries"])
