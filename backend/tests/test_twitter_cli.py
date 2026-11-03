import json
import subprocess

import pytest

from app.twitter_cli import (
    CliExecutionError,
    CliNotFoundError,
    CliTimeoutError,
    InvalidCliOutputError,
    ValidationError,
    JOVIS_SEARCH_QUERIES,
    resolve_search_query,
    search_tweets,
    fetch_recent_liked_posts,
    fetch_recent_bookmarked_posts,
)



def test_fetches_recent_likes_for_authenticated_account(monkeypatch):
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        data = {"user": {"screenName": "my-account"}} if command[1] == "whoami" else [
            {"id": "123", "text": "Useful post"}
        ]
        return subprocess.CompletedProcess(command, 0, json.dumps({"ok": True, "data": data}), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert fetch_recent_liked_posts()[0]["text"] == "Useful post"
    assert commands == [
        ["twitter", "whoami", "--json"],
        ["twitter", "likes", "my-account", "--max", "20", "--json"],
    ]


def test_builds_search_command_with_query_and_max(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: subprocess.CompletedProcess(command, 0, '{"ok":true}', ""))
    command = search_tweets("ai agents", 8).command

    assert command == ["twitter", "search", "ai agents", "--max", "8", "--json"]


def test_fetches_bookmarks_with_source_dates(monkeypatch):
    def fake_run(command, **kwargs):
        assert command == ["twitter", "bookmarks", "--max", "100", "--json"]
        data = {"ok": True, "data": [{"id": "123", "text": "Saved post", "createdAtISO": "2026-10-31T00:00:00Z"}]}
        return subprocess.CompletedProcess(command, 0, json.dumps(data), "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert fetch_recent_bookmarked_posts()[0]["createdAtISO"] == "2026-10-31T00:00:00Z"


def test_bookmark_api_failure_is_not_treated_as_an_empty_collection(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: subprocess.CompletedProcess([], 0, '{"ok":false}', ""))
    with pytest.raises(CliExecutionError):
        fetch_recent_bookmarked_posts()



def test_rejects_out_of_range_max():
    with pytest.raises(ValidationError, match="Max must be between 1 and 100"):
        search_tweets("agents", 500)


def test_builds_search_command_with_random_jovis_query_when_query_is_empty(monkeypatch):
    monkeypatch.setattr("app.twitter_cli.random.choice", lambda queries: "RevOps reporting")

    monkeypatch.setattr(subprocess, "run", lambda command, **kwargs: subprocess.CompletedProcess(command, 0, '{"ok":true}', ""))
    command = search_tweets(limit=10).command

    assert command == ["twitter", "search", "RevOps reporting", "--max", "10", "--json"]


def test_resolve_search_query_uses_jovis_target_customer_batch():
    assert "data team bottleneck" in JOVIS_SEARCH_QUERIES
    assert "single source of truth" in JOVIS_SEARCH_QUERIES
    assert resolve_search_query(" chat with database ") == "chat with database"


def test_runs_command_and_parses_json(monkeypatch):
    def fake_run(command, capture_output, text, timeout, check):
        assert command == ["twitter", "search", "agents", "--max", "20", "--json"]
        assert capture_output is True
        assert text is True
        assert timeout == 25
        assert check is False
        return subprocess.CompletedProcess(command, 0, json.dumps({"ok": True}), "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = search_tweets("agents")

    assert result.command == ["twitter", "search", "agents", "--max", "20", "--json"]
    assert result.data == {"ok": True}


def test_maps_non_zero_exit_to_execution_error(monkeypatch):
    def fake_run(command, capture_output, text, timeout, check):
        return subprocess.CompletedProcess(command, 1, "", "not authenticated")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(CliExecutionError) as error:
        search_tweets("agents", 3)

    assert "not authenticated" in str(error.value)


def test_maps_timeout_to_timeout_error(monkeypatch):
    def fake_run(command, capture_output, text, timeout, check):
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(CliTimeoutError):
        search_tweets("agents", 3)


def test_maps_missing_binary_to_not_found_error(monkeypatch):
    def fake_run(command, capture_output, text, timeout, check):
        raise FileNotFoundError("twitter")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(CliNotFoundError):
        search_tweets("agents", 3)


def test_maps_invalid_json_to_output_error(monkeypatch):
    def fake_run(command, capture_output, text, timeout, check):
        return subprocess.CompletedProcess(command, 0, "plain table output", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(InvalidCliOutputError):
        search_tweets("agents", 3)


TRANSACTION_WARNING = "WARNING twitter_cli.client: Failed to init ClientTransaction: 'NoneType' object has no attribute 'group'"


def test_post_accepts_cookie_progress_before_success_json_without_retry(monkeypatch):
    from app.twitter_cli import run_post_action
    calls = []
    def run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0,
            '\nGetting Twitter cookies...\n' + json.dumps({'ok': True, 'data': {'success': True, 'id': '123'}}),
            TRANSACTION_WARNING)
    monkeypatch.setattr(subprocess, 'run', run)
    result = run_post_action('Approved post')
    assert result.data['data']['id'] == '123'
    assert len(calls) == 1


@pytest.mark.parametrize('exit_code', [0, 1])
def test_actual_api_error_is_shown_instead_of_transaction_warning(monkeypatch, exit_code):
    from app.twitter_cli import run_post_action
    def run(command, **kwargs):
        return subprocess.CompletedProcess(command, exit_code,
            'Getting Twitter cookies...\n' + json.dumps({'ok': False, 'error': {
                'code': 'forbidden', 'message': 'Post failed (HTTP 403): permission denied'}}),
            TRANSACTION_WARNING)
    monkeypatch.setattr(subprocess, 'run', run)
    with pytest.raises(CliExecutionError, match=r'forbidden.*Post failed \(HTTP 403\)') as error:
        run_post_action('Approved post')
    assert 'NoneType' not in str(error.value)


def test_log_braces_and_trailing_garbage_do_not_become_a_success(monkeypatch):
    from app.twitter_cli import run_post_action
    monkeypatch.setattr(subprocess, 'run', lambda command, **kw:
        subprocess.CompletedProcess(command, 0, 'log {"ok":true}\nnot JSON', ''))
    with pytest.raises(InvalidCliOutputError, match='check your X profile'):
        run_post_action('Approved post')
