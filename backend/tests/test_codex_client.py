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
    assert 'ASD-STE100' in captured['prompt']
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
    monkeypatch.setattr(main, 'fetch_trending_research', lambda: {'sources': [{'id':'1'}], 'since':'today', 'researched_at':'today', 'warning':None})
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(main, 'generate_post_ideas', fail)
    monkeypatch.setattr(main, 'analyze_candidates', fail)
    response = TestClient(main.app).post(endpoint, json={'source_mode':'trends', 'candidates':[{'id':'123','text':'AI tools'}]})
    assert response.status_code == status
    assert response.json()['detail'] == str(error)
