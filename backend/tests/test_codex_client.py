import json
from pathlib import Path
import subprocess

from fastapi.testclient import TestClient
import pytest

from app import codex_client as client, main


def test_cli_uses_schema_stdin_isolation_and_never_calls_http(monkeypatch):
    captured = {}
    class Process:
        returncode = 0
        def __init__(self, command, **kwargs):
            captured['command'] = command
            captured['kwargs'] = kwargs
            schema = json.loads(Path(command[command.index('--output-schema') + 1]).read_text())
            assert schema['additionalProperties'] is False
            assert schema['properties']['ideas']['items']['properties']['post_text']['maxLength'] == 280
            Path(command[command.index('--output-last-message') + 1]).write_text('{"ideas":[{"post_text":"A clear draft."}]}')
        def communicate(self, prompt, timeout):
            captured['prompt'] = prompt.decode()
            assert timeout == 180
    monkeypatch.setattr(subprocess, 'Popen', Process)
    monkeypatch.setenv('CODEX_MODEL', 'configured-model')
    result = client.generate_post_ideas_with_codex('AI', 'Tools', count=1)
    command = captured['command']
    assert command[0] == 'codex'
    assert command[-1] == '-'
    assert command[command.index('--sandbox') + 1] == 'read-only'
    assert command[command.index('--model') + 1] == 'configured-model'
    assert '--ignore-user-config' in command and '--ephemeral' in command
    assert 'image_generation' in command and 'shell_tool' in command
    assert 'Do not call tools' in captured['prompt']
    assert client.POST_WRITING_STYLE in captured['prompt']
    assert result[0]['post_text'] == 'A clear draft.'
    assert not Path(command[command.index('--cd') + 1]).exists()


@pytest.mark.parametrize('failure', ['missing', 'exit', 'invalid', 'empty', 'timeout'])
def test_cli_failures_are_clear_and_never_return_logs(monkeypatch, failure):
    class Process:
        pid = 12345
        returncode = 1 if failure == 'exit' else 0
        def __init__(self, command, **kwargs):
            if failure == 'missing':
                raise FileNotFoundError('secret credential')
            if failure == 'invalid':
                Path(command[command.index('--output-last-message') + 1]).write_text('not JSON')
        def communicate(self, prompt, timeout):
            if failure == 'timeout':
                raise subprocess.TimeoutExpired('codex', timeout)
        def wait(self):
            pass
    killed = []
    monkeypatch.setattr(subprocess, 'Popen', Process)
    monkeypatch.setattr(client.os, 'killpg', lambda *args: killed.append(args))
    expected = client.CodexConfigurationError if failure == 'missing' else client.CodexError
    with pytest.raises(expected) as error:
        client.generate_post_ideas_with_codex('AI', '')
    assert 'secret' not in str(error.value)
    assert 'Codex' in str(error.value)
    if failure == 'timeout':
        assert killed


@pytest.mark.parametrize('error,status', [
    (client.CodexConfigurationError('Sign in to Codex'), 503),
    (client.CodexTimeoutError('Timed out'), 504),
    (client.CodexBusyError('Busy'), 503),
    (client.CodexError('Invalid result'), 502),
])
@pytest.mark.parametrize('endpoint', ['/api/posts/ideas', '/api/growth/analyze'])
def test_ai_endpoints_map_cli_errors_to_http(monkeypatch, tmp_path, error, status, endpoint):
    monkeypatch.setattr(main, 'get_growth_store', lambda: main.GrowthStore(tmp_path / 'growth.sqlite3'))
    monkeypatch.setattr(main, 'fetch_trending_research', lambda **kwargs: {'sources': [{'id':'1'}], 'since':'today', 'researched_at':'today', 'warning':None})
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(main, 'curate_research_for_essay', lambda sources, *a: sources)
    monkeypatch.setattr(main, 'generate_post_ideas', fail)
    monkeypatch.setattr(main, 'analyze_candidates', fail)
    response = TestClient(main.app).post(endpoint, json={'source_mode':'trends', 'candidates':[{'id':'123','text':'AI tools'}]})
    assert response.status_code == status
    assert response.json()['detail'] == str(error)


def test_research_cli_enables_live_search_without_enabling_write_tools(monkeypatch):
    captured = {}
    class Process:
        returncode = 0
        def __init__(self, command, **kwargs):
            captured["command"] = command
            Path(command[command.index("--output-last-message") + 1]).write_text('{"sources":[]}')
        def communicate(self, prompt, timeout):
            captured["prompt"] = prompt.decode()
    monkeypatch.setattr(subprocess, "Popen", Process)
    client._run_codex("Research the essay", {}, client._object_schema({"sources": {"type": "array"}}), web_search=True)
    assert 'web_search="live"' in captured["command"]
    assert 'web_search="disabled"' not in captured["command"]
    assert "shell_tool" in captured["command"]
    assert "Research using live web search" in captured["prompt"]
    assert "Do not call tools" not in captured["prompt"]


@pytest.mark.parametrize("mode", ["comment", "alternatives", "refine"])
def test_human_writing_rules_cover_all_short_form_writing(monkeypatch, mode):
    def run(system, payload, schema, **kwargs):
        assert client.POST_WRITING_STYLE in system
        assert "ASD-STE100" not in system
        assert "20 and 50 words" in system
        if mode == "comment":
            return '{"recommendations":[]}'
        if mode == "alternatives":
            return json.dumps({"alternatives": [
                "A failed tool call needs somewhere to go. If nobody owns the handoff, adding more tools just gives the agent more ways to get stuck.",
                "The review step can become the slowest part. Someone still needs enough context and time to catch what the agent missed before it goes out.",
            ]})
        return '{"post_text":"A short draft."}'

    monkeypatch.setattr(client, "_run_codex", run)
    if mode == "comment":
        client.analyze_with_codex([], "AI agents")
    elif mode == "alternatives":
        client.generate_comment_alternatives_with_codex({"text": "Tool failures"}, "Old draft")
    else:
        client.refine_post_with_codex("A short draft.")


@pytest.mark.parametrize("mode", ["essay", "research", "interests"])
def test_job_future_brief_applies_to_every_post_idea_mode(monkeypatch, mode):
    def run(system, payload, schema, **kwargs):
        assert payload["post_idea_brief"] == client.POST_IDEA_BRIEF
        assert "future of jobs in the AI era" in payload["post_idea_brief"]
        assert client.POST_IDEA_DIRECTION in system
        assert client.POST_WRITING_STYLE in system
        assert "title is not published" in system
        assert "sole editorial foundation" in system
        return '{"ideas":[{"post_text":"An original thought about changing work."}]}'

    monkeypatch.setattr(client, "_run_codex", run)
    client.generate_post_ideas_with_codex(
        "", "", count=1,
        research_sources=[{"id": "project:1", "title": "Agent project"}] if mode == "research" else None,
        recent_liked_posts=[{"id": "1", "text": "AI at work"}] if mode == "interests" else None,
    )
