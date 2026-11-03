from datetime import datetime, timezone
import json

import pytest
from fastapi.testclient import TestClient

from app import prospects

NOW = datetime(2026, 11, 2, tzinfo=timezone.utc)


def post(**changes):
    return {"url": "https://www.reddit.com/r/SaaS/comments/abc123/a_problem/", "title": "We lose decisions",
            "author": "founder", "query": prospects.QUERIES[0]["query"], "published_at": "2026-11-01", "date_note": "",
            "quote": "We cannot find our decisions", "context": "We tried a manual log.", "evidence_kind": "full_post",
            "lead_type": "buyer", "personal_pain": True, "buyer_role_evidence": "I run the team",
            "explicit_solution_request": True, "caveats": [], **changes}


def assessment(url=None, **changes):
    return {"url": url or post()["url"], "summary": "A concrete buyer problem", "requirements": [
        {"need": "Search Slack", "status": "supported", "evidence_ids": ["E1"], "explanation": "Explicit read tool", "next_step": "Verify access"}
    ], "introduction_angle": "Offer a focused demo", "next_action": "Review the original post", **changes}


def snapshot():
    return {"evidence": [{"id": "E1", "path": "app/connectors/providers/slack.py", "line": 1, "excerpt": "search"}], "warnings": []}


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.setenv("PROSPECTS_DB_PATH", str(tmp_path / "prospects.sqlite3"))
    monkeypatch.setattr(prospects, "_ACTIVE", None)
    monkeypatch.setattr(prospects, "source_snapshot", snapshot)
    monkeypatch.setattr(prospects, "search_product_code", lambda *args: [])


@pytest.mark.parametrize("url, expected", [
    ("javascript:alert(1)", ""), ("https://x.com.evil.test/a/status/123", ""),
    ("https://user:password@x.com/a/status/123", ""), ("https://x.com:8080/a/status/123", ""),
    ("https://x.com/search?q=pain", ""), ("https://reddit.com/r/SaaS", ""),
    ("https://twitter.com/alice/status/123?utm_source=test", "https://x.com/alice/status/123"),
    ("https://old.reddit.com/r/SaaS/comments/abc123/title/comment?context=3", "https://www.reddit.com/r/saas/comments/abc123/"),
    ("https://news.ycombinator.com/item?id=123", "https://news.ycombinator.com/item?id=123"),
])
def test_only_individual_safe_post_links(url, expected):
    assert prospects.post_url(url) == expected


def test_score_is_explainable_and_grounded():
    result = prospects.rank_post(post(), assessment(), snapshot(), NOW)
    assert result["confidence"] == 100
    assert sum(result["confidence_factors"].values()) == 100
    assert result["coverage"] == 100
    assert result["recommendation"] == "Introduce Jovis"


@pytest.mark.parametrize("changes", [
    {"published_at": ""}, {"published_at": "unknown"}, {"published_at": "2027-01-01"},
    {"published_at": "2025-01-01"}, {"evidence_kind": "snippet"}, {"personal_pain": False},
])
def test_unverified_or_old_posts_are_research_leads(changes):
    result = prospects.rank_post(post(**changes), assessment(), snapshot(), NOW)
    assert result["confidence"] <= 59
    assert sum(result["confidence_factors"].values()) == result["confidence"]
    assert result["recommendation"] == "Research first"


def test_invalid_evidence_cannot_support_a_capability():
    fit = assessment()
    fit["requirements"][0]["evidence_ids"] = ["invented-path"]
    fit["suggested_response"] = "Jovis solves this."
    result = prospects.rank_post(post(), fit, snapshot(), NOW)
    assert result["coverage"] == 0
    assert result["requirements"][0]["status"] == "unknown"
    assert result["recommendation"] == "Check fit first"
    assert result["suggested_response"] == ""


def test_partial_and_missing_capabilities_are_not_ready():
    fit = assessment()
    fit["requirements"][0]["status"] = "partial"
    result = prospects.rank_post(post(), fit, snapshot(), NOW)
    assert result["coverage"] == 50
    assert result["recommendation"] == "Check fit first"
    assert prospects.rank_post(post(), {}, snapshot(), NOW)["recommendation"] == "Check fit first"
    assert prospects.rank_post(post(lead_type="uncertain"), fit, snapshot(), NOW)["confidence"] <= 49


def seed_run():
    return {"id": "test-run", "status": "running", "started_at": "2026-11-02T00:00:00+00:00", "completed_at": "",
            "queries": [{**q, "status": "pending", "finding": ""} for q in prospects.QUERIES],
            "posts": [], "warnings": [], "error": ""}


def test_all_twenty_queries_run_and_posts_deduplicate(isolated, monkeypatch):
    calls = []
    def research(group, now):
        calls.extend(q["query"] for q in group)
        return {"queries": [{"query": q["query"], "status": "searched", "finding": "One relevant post"} for q in group],
                "posts": [post(), post(url="https://old.reddit.com/r/SaaS/comments/abc123/other-title/"), post(lead_type="vendor", url="https://x.com/vendor/status/2")], "warnings": []}
    monkeypatch.setattr(prospects, "research_group", research)
    monkeypatch.setattr(prospects, "assess_posts", lambda posts, _: [assessment(url=p["url"]) for p in posts])
    prospects.execute_run(seed_run())
    result = prospects.get_run("test-run")
    assert len(calls) == len(set(calls)) == 20
    assert result["status"] == "complete"
    assert len(result["posts"]) == 1
    assert result["posts"][0]["url"] == "https://www.reddit.com/r/saas/comments/abc123/"


def test_failed_search_group_preserves_results_and_continues(isolated, monkeypatch):
    calls = []
    def research(group, _):
        calls.append(group)
        if len(calls) == 2:
            raise prospects.CodexError("X unavailable")
        return {"queries": [{"query": q["query"], "status": "searched", "finding": ""} for q in group], "posts": [post()], "warnings": []}
    monkeypatch.setattr(prospects, "research_group", research)
    monkeypatch.setattr(prospects, "assess_posts", lambda posts, _: [assessment(url=p["url"]) for p in posts])
    prospects.execute_run(seed_run())
    result = prospects.get_run()
    assert result["status"] == "partial"
    assert len(calls) == 5
    assert len(result["posts"]) == 1
    assert sum(q["status"] == "unavailable" for q in result["queries"]) == 4


def test_gap_failure_retains_discovered_links(isolated, monkeypatch):
    monkeypatch.setattr(prospects, "research_group", lambda group, _: {"queries": [], "posts": [post()], "warnings": []})
    def broken(*args):
        with prospects.connection() as db:
            saved = json.loads(db.execute("SELECT payload FROM prospect_runs WHERE id = ?", ("test-run",)).fetchone()[0])
        assert len(saved["posts"]) == 1
        assert saved["posts"][0]["recommendation"] != "Introduce Jovis"
        raise prospects.CodexError("Analysis timed out")
    monkeypatch.setattr(prospects, "assess_posts", broken)
    prospects.execute_run(seed_run())
    result = prospects.get_run()
    assert len(result["posts"]) == 1
    assert result["posts"][0]["coverage"] == 0
    assert result["posts"][0]["recommendation"] != "Introduce Jovis"
    assert result["status"] == "partial"


def test_missing_repo_fails_without_searching(isolated, monkeypatch):
    def missing():
        raise prospects.CodexConfigurationError("Set JOVIS_REPO_PATH")
    monkeypatch.setattr(prospects, "source_snapshot", missing)
    monkeypatch.setattr(prospects, "research_group", lambda *args: pytest.fail("Must not search"))
    prospects.execute_run(seed_run())
    assert prospects.get_run()["status"] == "failed"
    assert "JOVIS_REPO_PATH" in prospects.get_run()["error"]


def test_restart_preserves_partial_results(isolated):
    run = seed_run()
    run["posts"] = [post()]
    prospects.save_run(run)
    restored = prospects.get_run()
    assert restored["status"] == "interrupted"
    assert restored["posts"] == run["posts"]


def test_repeated_start_joins_existing_job(isolated, monkeypatch):
    submitted = []
    monkeypatch.setattr(prospects._EXECUTOR, "submit", lambda *args: submitted.append(args))
    first = prospects.start_run()
    second = prospects.start_run()
    assert first["id"] == second["id"]
    assert len(submitted) == 1


def test_source_snapshot_ignores_secrets_and_fingerprints_changes(tmp_path, monkeypatch):
    root = tmp_path / "agent"
    providers = root / "app/connectors/providers"
    providers.mkdir(parents=True)
    file = providers / "slack.py"
    file.write_text('class Slack:\n    def get_tool_names(cls):\n        return ["search"]\n')
    (root / ".env").write_text("PRIVATE_SECRET=do-not-read")
    (providers / "linked.py").symlink_to(root / ".env")
    monkeypatch.setenv("JOVIS_REPO_PATH", str(root))
    first = prospects.source_snapshot()
    assert "do-not-read" not in json.dumps(first)
    file.write_text(file.read_text().replace('"search"', '"search", "history"'))
    assert first["fingerprint"] != prospects.source_snapshot()["fingerprint"]


def test_api_latest_unknown_and_start(isolated, monkeypatch):
    from app import main
    client = TestClient(main.app)
    assert client.get("/api/prospects/runs/latest").json() == {"run": None}
    assert client.get("/api/prospects/runs/no-such-run").status_code == 404
    monkeypatch.setattr(prospects._EXECUTOR, "submit", lambda *args: None)
    response = client.post("/api/prospects/runs")
    assert response.status_code == 200
    run = response.json()
    assert len(run["queries"]) == 20
    assert client.get(f"/api/prospects/runs/{run['id']}").json()["status"] == "running"


def test_source_never_sent_to_web_research(monkeypatch):
    calls = []
    def fake(system, payload, schema, **kwargs):
        calls.append((payload, kwargs))
        return json.dumps({"queries": [], "posts": [], "warnings": []}) if kwargs.get("web_search") else json.dumps({"assessments": []})
    monkeypatch.setattr(prospects, "_run_codex", fake)
    prospects.research_group(prospects.QUERIES[:4], NOW.isoformat())
    prospects.assess_posts([post()], snapshot())
    assert "source_snapshot" not in calls[0][0]
    assert calls[0][1]["web_search"] is True
    assert calls[1][0]["source_snapshot"] == snapshot()
    assert not calls[1][1].get("web_search")


def test_semantic_search_rereads_current_code_and_rejects_unsafe_paths(monkeypatch, tmp_path):
    root = tmp_path / "agent"
    code = root / "app/services/export.py"
    code.parent.mkdir(parents=True)
    code.write_text('def export_report():\n    return "supported"\n')
    (root / "app/config.py").write_text('PRIVATE_SECRET = "do-not-read"')
    monkeypatch.setenv("JOVIS_REPO_PATH", str(root))
    monkeypatch.setattr(prospects.shutil, "which", lambda _: "/bin/semble")
    chunks = [
        {"chunk": {"file_path": "app/services/export.py", "start_line": 1, "end_line": 2, "content": code.read_text()}},
        {"chunk": {"file_path": "../../.env", "start_line": 1, "end_line": 1, "content": "secret"}},
        {"chunk": {"file_path": "app/services/../config.py", "start_line": 1, "end_line": 1, "content": 'PRIVATE_SECRET = "do-not-read"'}},
        {"chunk": {"file_path": "app/services/export.py", "start_line": 1, "end_line": 2, "content": "outdated index"}},
    ]
    def fake(command, **kwargs):
        assert command[1] == "search"
        assert command[-4:] == ["--content", "code", "--top-k", "5"]
        assert not kwargs.get("shell")
        return prospects.subprocess.CompletedProcess(command, 0, json.dumps({"results": chunks}), "")
    monkeypatch.setattr(prospects.subprocess, "run", fake)
    context = snapshot()
    warnings = prospects.search_product_code([post()], context)
    assert len(context["evidence"]) == 2
    assert context["evidence"][-1]["path"] == "app/services/export.py"
    assert context["evidence"][-1]["excerpt"] == code.read_text().strip()
    assert context["semantic_searches"][0]["post_url"] == post()["url"]
    assert any("Stale" in warning for warning in warnings)
    assert "secret" not in json.dumps(context)


def test_semantic_search_missing_cli_is_explicit(monkeypatch):
    monkeypatch.setattr(prospects.shutil, "which", lambda _: None)
    assert "unavailable" in prospects.search_product_code([post()], snapshot())[0]


def test_suggested_response_uses_saved_gaps_and_founder_voice_and_persists(isolated, monkeypatch):
    run = seed_run()
    run.update(status="complete", source_snapshot=snapshot())
    run["posts"] = [prospects.rank_post(post(), assessment(), snapshot(), NOW)]
    prospects.save_run(run)
    monkeypatch.setattr(prospects, "voice_preferences", lambda: ["Keep the useful bit first. What do you use today?"])
    def fake(system, payload, schema, **kwargs):
        assert "solo founder" in system
        assert "Never invent personal experience" in system
        assert "unsupported requirement" in system
        assert not kwargs.get("web_search")
        assert payload["post"]["requirements"][0]["need"] == "Search Slack"
        assert payload["code_evidence"] == snapshot()["evidence"]
        assert payload["voice_preferences"]
        return json.dumps({"suggested_response": "Start by recording the decision and its reason. Which tools do you use?", "response_note": "Confirm their tools."})
    monkeypatch.setattr(prospects, "_run_codex", fake)
    reply = prospects.suggest_response(run["id"], post()["url"])
    assert reply["suggested_response"].startswith("Start by")
    # A background research save must not overwrite a separately saved response.
    prospects.save_run(run)
    restored = prospects.get_run(run["id"])
    assert restored["posts"][0]["suggested_response"] == reply["suggested_response"]
    assert restored["posts"][0]["response_note"] == "Confirm their tools."


def test_unknown_prospect_cannot_generate_reply(isolated, monkeypatch):
    monkeypatch.setattr(prospects, "_run_codex", lambda *args, **kwargs: pytest.fail("Must not generate"))
    with pytest.raises(LookupError):
        prospects.suggest_response("missing-run", post()["url"])


def test_empty_reply_does_not_replace_existing_draft(isolated, monkeypatch):
    run = seed_run()
    run.update(status="complete", source_snapshot=snapshot(), posts=[post()])
    prospects.save_run(run)
    monkeypatch.setattr(prospects, "voice_preferences", lambda: [])
    monkeypatch.setattr(prospects, "_run_codex", lambda *args, **kwargs: json.dumps({"suggested_response": "   ", "response_note": ""}))
    with pytest.raises(prospects.CodexError):
        prospects.suggest_response(run["id"], post()["url"])
    assert not prospects.get_run(run["id"])["posts"][0].get("suggested_response")


def test_response_endpoint_handles_missing_and_busy(isolated, monkeypatch):
    from app import main
    client = TestClient(main.app)
    response = client.post("/api/prospects/runs/missing/response", json={"url":post()["url"]})
    assert response.status_code == 404
    def busy(*args):
        raise main.CodexBusyError("Try again shortly")
    monkeypatch.setattr(main, "suggest_response", busy)
    assert client.post("/api/prospects/runs/test/response",json={"url":post()["url"]}).status_code == 503


def test_analysis_includes_response_fields_and_voice(monkeypatch):
    def fake(system,payload,schema,**kwargs):
        assert "solo founder" in system
        assert "suggested_response" in schema["properties"]["assessments"]["items"]["properties"]
        return json.dumps({"assessments":[]})
    monkeypatch.setattr(prospects,"_run_codex",fake)
    monkeypatch.setattr(prospects,"voice_preferences",lambda:[])
    assert prospects.assess_posts([post()],snapshot()) == []
