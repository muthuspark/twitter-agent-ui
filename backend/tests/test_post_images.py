import json
from pathlib import Path
import subprocess

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from app import main, post_images
from app.twitter_cli import CliResult, run_post_action


@pytest.fixture
def ready_image(monkeypatch, tmp_path):
    monkeypatch.setenv('POST_IMAGE_DIR', str(tmp_path / 'media'))
    image_id = 'a' * 32
    directory = post_images.job_dir(image_id)
    directory.mkdir(parents=True)
    Image.new('RGB', (32, 24)).save(directory / 'image.jpg')
    post_images.save_job(directory, {'id': image_id, 'status': 'ready'})
    return image_id, directory / 'image.jpg'


def test_codex_generation_uses_native_tool_and_persists_real_image(monkeypatch, tmp_path):
    directory = tmp_path / 'job'
    directory.mkdir()
    job = {'id': 'a' * 32, 'status': 'queued', 'prompt': post_images.image_prompt('Check AI extensions.', 'Trust')}
    class Process:
        returncode = 0
        def __init__(self, command, **kwargs):
            assert command[0] == 'codex'
            assert '--ignore-user-config' in command
            assert command[command.index('--sandbox') + 1] == 'workspace-write'
            assert command[-1] == '-'
        def communicate(self, prompt, timeout):
            assert b'native image generation tool' in prompt
            assert timeout == 600
            Image.new('RGB', (64, 48), 'red').save(directory / 'source.png')
    monkeypatch.setattr(subprocess, 'Popen', Process)
    post_images.generate_image(directory, job)
    result = json.loads((directory / 'status.json').read_text())
    assert result['status'] == 'ready'
    assert result['width'] == 64
    assert result['url'].endswith('/file')
    with Image.open(directory / 'image.jpg') as image:
        assert image.format == 'JPEG'


def test_codex_failure_is_reported_without_logs_or_fake_images(monkeypatch, tmp_path):
    def missing(*args, **kwargs):
        raise FileNotFoundError('secret internal path')
    monkeypatch.setattr(subprocess, 'Popen', missing)
    post_images.generate_image(tmp_path, {'id': 'a' * 32, 'prompt': 'A post image'})
    result = json.loads((tmp_path / 'status.json').read_text())
    assert result['status'] == 'failed'
    assert 'not found' in result['error']
    assert 'secret' not in result['error']
    assert not (tmp_path / 'image.jpg').exists()


@pytest.mark.parametrize('image_id', ['../secret', '/tmp/file', 'bad', None])
def test_arbitrary_image_paths_are_rejected(image_id):
    with pytest.raises(post_images.ImageGenerationError):
        post_images.ready_image_path(image_id)


def test_interrupted_generation_does_not_stay_pending(monkeypatch, tmp_path):
    monkeypatch.setenv('POST_IMAGE_DIR', str(tmp_path))
    directory = tmp_path / ('b' * 32)
    directory.mkdir()
    post_images.save_job(directory, {'id': 'b' * 32, 'status': 'generating'})
    assert post_images.get_image_job('b' * 32)['status'] == 'failed'


def test_image_preview_and_text_plus_image_publish_use_same_file(monkeypatch, tmp_path, ready_image):
    image_id, path = ready_image
    monkeypatch.setattr(main, 'get_growth_store', lambda: main.GrowthStore(tmp_path / 'growth.sqlite3'))
    def publish(text, image_path):
        assert text == 'Approved with image'
        assert image_path == str(path)
        return CliResult(command=['twitter', 'post', text, '--image', image_path, '--json'], data={'ok': True, 'id': '123'})
    monkeypatch.setattr(main, 'run_post_action', publish)
    client = TestClient(main.app)
    preview = client.get(f'/api/posts/images/{image_id}/file')
    assert preview.status_code == 200
    assert preview.headers['content-type'] == 'image/jpeg'
    response = client.post('/api/posts/approve', json={'post_text': 'Approved with image', 'image_id': image_id})
    assert response.status_code == 200
    assert response.json()['record']['metadata']['image']['id'] == image_id
    assert response.json()['record']['tweet_id'] == '123'


def test_pending_or_unknown_image_never_silently_posts_text(monkeypatch, ready_image):
    image_id, path = ready_image
    post_images.save_job(path.parent, {'id': image_id, 'status': 'queued'})
    def unexpected(*args, **kwargs):
        pytest.fail('Must not publish before the requested image is ready')
    monkeypatch.setattr(main, 'run_post_action', unexpected)
    client = TestClient(main.app)
    assert client.post('/api/posts/approve', json={'post_text': 'Draft', 'image_id': image_id}).status_code == 422
    assert client.post('/api/posts/approve', json={'post_text': 'Draft', 'image_id': '../secret'}).status_code == 422


def test_cli_failure_does_not_record_post_as_published(monkeypatch, tmp_path):
    store = main.GrowthStore(tmp_path / 'growth.sqlite3')
    monkeypatch.setattr(main, 'get_growth_store', lambda: store)
    monkeypatch.setattr(main, 'run_post_action', lambda text: CliResult(command=[], data={'ok': False}))
    assert TestClient(main.app).post('/api/posts/approve', json={'post_text': 'Draft'}).status_code == 502
    assert store.history() == []


def test_image_post_uses_argument_list_and_upload_timeout(monkeypatch):
    def run(command, **kwargs):
        assert command == ['twitter', 'post', 'Approved post', '--json', '--image', '/tmp/a photo.jpg']
        assert kwargs['timeout'] == 90
        return subprocess.CompletedProcess(command, 0, '{"ok":true}', '')
    monkeypatch.setattr(subprocess, 'run', run)
    assert run_post_action('Approved post', image_path='/tmp/a photo.jpg').data['ok']


def test_image_creation_rejects_empty_and_overlength_text():
    for text in ['', 'x' * 281]:
        assert TestClient(main.app).post('/api/posts/images', json={'post_text': text}).status_code == 422
