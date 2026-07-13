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
    build_command,
    resolve_search_query,
    run_twitter_command,
)


def test_builds_feed_command_with_json_and_max():
    command = build_command("feed", {"max": 12})

    assert command == ["twitter", "feed", "--max", "12", "--json"]


def test_builds_search_command_with_query_and_max():
    command = build_command("search", {"query": "ai agents", "max": 8})

    assert command == ["twitter", "search", "ai agents", "--max", "8", "--json"]


def test_rejects_unknown_preset():
    with pytest.raises(ValidationError, match="Unsupported command preset"):
        build_command("delete", {"max": 5})


def test_rejects_out_of_range_max():
    with pytest.raises(ValidationError, match="Max must be between 1 and 100"):
        build_command("feed", {"max": 500})


def test_builds_search_command_with_random_jovis_query_when_query_is_empty(monkeypatch):
    monkeypatch.setattr("app.twitter_cli.random.choice", lambda queries: "RevOps reporting")

    command = build_command("search", {"max": 10})

    assert command == ["twitter", "search", "RevOps reporting", "--max", "10", "--json"]


def test_resolve_search_query_uses_jovis_target_customer_batch():
    assert "data team bottleneck" in JOVIS_SEARCH_QUERIES
    assert "single source of truth" in JOVIS_SEARCH_QUERIES
    assert resolve_search_query(" chat with database ") == "chat with database"


def test_runs_command_and_parses_json(monkeypatch):
    def fake_run(command, capture_output, text, timeout, check):
        assert command == ["twitter", "status", "--json"]
        assert capture_output is True
        assert text is True
        assert timeout == 25
        assert check is False
        return subprocess.CompletedProcess(command, 0, json.dumps({"ok": True}), "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_twitter_command("status", {})

    assert result.command == ["twitter", "status", "--json"]
    assert result.data == {"ok": True}


def test_maps_non_zero_exit_to_execution_error(monkeypatch):
    def fake_run(command, capture_output, text, timeout, check):
        return subprocess.CompletedProcess(command, 1, "", "not authenticated")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(CliExecutionError) as error:
        run_twitter_command("feed", {"max": 3})

    assert "not authenticated" in str(error.value)


def test_maps_timeout_to_timeout_error(monkeypatch):
    def fake_run(command, capture_output, text, timeout, check):
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(CliTimeoutError):
        run_twitter_command("feed", {"max": 3})


def test_maps_missing_binary_to_not_found_error(monkeypatch):
    def fake_run(command, capture_output, text, timeout, check):
        raise FileNotFoundError("twitter")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(CliNotFoundError):
        run_twitter_command("feed", {"max": 3})


def test_maps_invalid_json_to_output_error(monkeypatch):
    def fake_run(command, capture_output, text, timeout, check):
        return subprocess.CompletedProcess(command, 0, "plain table output", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(InvalidCliOutputError):
        run_twitter_command("feed", {"max": 3})
