import json
import subprocess
from types import SimpleNamespace

import pytest

from app import reddit_browser, reddit_cli


def row(post_id="abc123", **changes):
    return {"id": post_id, "permalink": f"/r/SaaS/comments/{post_id}/decisions/",
            "title": "Where are our decisions?", "author": "founder", "subreddit": "SaaS",
            "selftext": "", "created_utc": 1793491200, **changes}


@pytest.fixture
def cli(monkeypatch):
    calls = []
    response = {"stdout": json.dumps({"ok": True, "data": []}), "returncode": 0, "stderr": "private diagnostics"}
    monkeypatch.setattr(reddit_browser.shutil, "which", lambda path: "/tools/opencli")
    monkeypatch.setenv("REDDIT_CLI_BACKEND", "opencli")
    reddit_browser._LISTINGS.clear()
    def run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(**response)
    monkeypatch.setattr(reddit_browser.subprocess, "run", run)
    yield response, calls
    reddit_browser._LISTINGS.clear()


def respond(cli, data):
    cli[0]["stdout"] = json.dumps({"ok": True, "data": data})


def test_browser_is_default_and_legacy_is_explicit(monkeypatch):
    monkeypatch.delenv("REDDIT_CLI_BACKEND", raising=False)
    monkeypatch.setattr(reddit_browser, "connection_status", lambda: {"authenticated": True})
    assert reddit_cli.connection_status() == {"authenticated": True}
    monkeypatch.setattr(reddit_browser, "search", lambda query: [query])
    monkeypatch.setattr(reddit_browser, "read", lambda post_id: {"id": post_id})
    assert reddit_cli.search("query") == ["query"]
    assert reddit_cli.read("abc123") == {"id": "abc123"}


def test_identity_is_verified_but_private_identity_fields_are_discarded(cli):
    respond(cli, [{"field": "Username", "value": "u/founder"}, {"field": "Inbox Count", "value": "secret"}])
    status = reddit_cli.connection_status()
    assert status["authenticated"] and status["username"] == "founder"
    assert "Chrome" in status["message"] and "secret" not in json.dumps(status)
    assert cli[1][0][0] == ["/tools/opencli", "reddit", "whoami", "-f", "json", "--window", "background"]
    assert cli[1][0][1]["env"]["OPENCLI_CLOSE_OWNED_TAB"] == "1"
    respond(cli, [])
    assert not reddit_cli.connection_status()["authenticated"]


def test_search_navigates_real_search_page_and_normalizes_only_public_fields(cli):
    respond(cli, {"posts": [row(cookie="secret")], "empty": False})
    posts = reddit_cli.search('"decisions" & team')
    commands = [call[0] for call in cli[1]]
    assert commands[0][1:3] == ["browser", "open"]
    assert "q=%22decisions%22+%26+team" in commands[0][3] and "t=month" in commands[0][3]
    assert "sort=relevance" in commands[0][3]
    assert commands[1][1:3] == ["browser", "eval"]
    assert "fetch(" not in commands[1][3]
    assert "secret" not in json.dumps(posts)
    assert posts[0]["published_at"] and posts[0]["author"] == "founder"
    assert posts[0]["url"].startswith("https://www.reddit.com/r/SaaS/comments/abc123/")
    assert cli[1][0][1]["timeout"] == 60


def test_empty_search_requires_explicit_empty_state(cli):
    respond(cli, {"posts": [], "empty": True})
    assert reddit_cli.search("no results") == []
    respond(cli, {"posts": [], "empty": False})
    with pytest.raises(reddit_cli.RedditCliError) as caught:
        reddit_cli.search("loading or markup drift")
    assert caught.value.code == "invalid_output"


def test_reader_preserves_original_text_and_bounds_comments(cli):
    reddit_browser._LISTINGS["abc123"] = reddit_cli._post(row())
    respond(cli, [{"type": "POST", "author": "updated-author", "text": "Updated title\n\nWe lose decisions.\nSecond paragraph."},
                  *[{"type": "L0", "author": "reader", "text": f"Reply {i}"} for i in range(30)],
                  {"type": "L1", "author": "", "text": "[+3 more replies]"}])
    result = reddit_cli.read("abc123")
    assert result["post"]["title"] == "Updated title"
    assert result["post"]["selftext"] == "We lose decisions.\nSecond paragraph."
    assert result["post"]["author"] == "updated-author"
    assert result["post"]["id"] == "abc123" and result["post"]["published_at"]
    assert len(result["comments"]) == 25 and result["comments_incomplete"]
    command = cli[1][0][0]
    assert command[1:4] == ["reddit", "read", "abc123"]
    assert command[command.index("--depth") + 1] == "1"
    assert command[command.index("--max-length") + 1] == "40000"


def test_reader_rejects_unseen_ids_and_malformed_post_rows(cli):
    with pytest.raises(reddit_cli.RedditCliError):
        reddit_cli.read("--help")
    with pytest.raises(reddit_cli.RedditCliError):
        reddit_cli.read("unseen")
    assert not cli[1]
    reddit_browser._LISTINGS["abc123"] = reddit_cli._post(row())
    respond(cli, [{"type": "L0", "author": "reader", "text": "comment"}])
    with pytest.raises(reddit_cli.RedditCliError):
        reddit_cli.read("abc123")


@pytest.mark.parametrize("code,expected", [("LOGIN_WALL", "not_authenticated"), ("AUTH_REQUIRED", "not_authenticated"),
    ("RATE_LIMITED", "rate_limited"), ("UNKNOWN_PRIVATE_CODE", "api_error")])
def test_errors_never_forward_upstream_diagnostics(cli, code, expected):
    cli[0]["stdout"] = json.dumps({"ok": False, "error": {"code": code, "message": "secret", "hint": "secret"}})
    with pytest.raises(reddit_cli.RedditCliError) as caught:
        reddit_browser._run(["reddit", "whoami"])
    assert caught.value.code == expected and "secret" not in str(caught.value)


def test_bridge_missing_and_timeouts_are_actionable(cli, monkeypatch):
    monkeypatch.setattr(reddit_browser.shutil, "which", lambda path: None)
    assert not reddit_cli.connection_status()["installed"]
    monkeypatch.setattr(reddit_browser.shutil, "which", lambda path: "/tools/opencli")
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("private", 60)
    monkeypatch.setattr(reddit_browser.subprocess, "run", timeout)
    status = reddit_cli.connection_status()
    assert not status["authenticated"] and "Chrome" in status["message"]
    assert "private" not in json.dumps(status)


def test_dom_block_is_not_treated_as_an_empty_success(cli):
    respond(cli, {"error": "forbidden"})
    with pytest.raises(reddit_cli.RedditCliError) as caught:
        reddit_cli.search("query")
    assert caught.value.code == "forbidden"


def test_cleanup_releases_only_owned_session_even_on_error(cli):
    reddit_browser._LISTINGS["abc123"] = reddit_cli._post(row())
    cli[0]["stdout"] = json.dumps({"ok": False, "error": {"code": "SESSION_NOT_FOUND"}})
    reddit_cli.close_research()
    assert not reddit_browser._LISTINGS
    assert cli[1][0][0] == ["/tools/opencli", "browser", "close", "--session", reddit_browser.SESSION]


def test_comment_timeout_is_uncertain_and_not_retried(monkeypatch):
    calls = []
    def command(args, **kwargs):
        calls.append(args)
        if args[:2] == ["browser", "eval"]:
            raise reddit_browser.BrowserRedditError("timeout")
        return {}
    monkeypatch.setattr(reddit_browser, "_run", command)
    result = reddit_browser.post_comment("abc123", "My reply", "founder")
    assert result["status"] == "uncertain"
    assert [args[1] for args in calls] == ["open", "eval", "close"]
    assert calls[0][calls[0].index("--session") + 1] == calls[-1][-1]


def test_comment_success_requires_identity_from_reddit_and_preserves_exact_text(monkeypatch):
    calls = []
    text = "Reply with `code`, quotes, and\nnewlines."
    def command(args, **kwargs):
        calls.append(args)
        return {"status": "posted", "comment_id": "reply123"} if args[:2] == ["browser", "eval"] else {}
    monkeypatch.setattr(reddit_browser, "_run", command)
    result = reddit_browser.post_comment("abc123", text, "founder")
    assert result["status"] == "posted" and result["comment_id"] == "reply123"
    assert json.dumps({"postId": "abc123", "text": text, "username": "founder"}) in calls[1][2]


def test_comment_navigation_failure_does_not_submit(monkeypatch):
    calls = []
    def command(args, **kwargs):
        calls.append(args)
        if args[:2] == ["browser", "open"]:
            raise reddit_browser.BrowserRedditError("not_authenticated")
        return {}
    monkeypatch.setattr(reddit_browser, "_run", command)
    assert reddit_browser.post_comment("abc123", "Reply", "founder")["status"] == "failed"
    assert [args[1] for args in calls] == ["open", "close"]
