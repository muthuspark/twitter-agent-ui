import pytest
from app import linkedin_likes as likes


def post(count='4', state='Reaction button state: no reaction', text='Feed post\nAgent evaluations'):
    return {'key': 'post-key', 'count': count, 'state': state, 'text': text}


@pytest.mark.parametrize('count', ['0', '1', '2', '3', '4'])
def test_only_confirmed_counts_below_five_qualify(count):
    assert likes.eligible(post(count=count))


@pytest.mark.parametrize('count', ['5', '6', '92', '828', '', '1K', '4 comments', None])
def test_missing_or_nonqualifying_counts_never_become_zero(count):
    assert not likes.eligible(post(count=count))


def test_skips_ads_and_existing_reactions():
    assert not likes.eligible(post(text='Feed post\nPromoted\nAI agents'))
    assert not likes.eligible(post(state='Reaction button state: Like'))


def test_no_model_call_without_candidates(monkeypatch):
    def unexpected(*a, **k):
        pytest.fail('No classification needed for an empty set')
    monkeypatch.setattr(likes, '_run_codex', unexpected)
    assert likes.relevant_keys([], {}) == set()


def test_only_model_selected_supplied_posts_are_used(monkeypatch):
    monkeypatch.setattr(likes, '_run_codex', lambda *a, **k: '{"selected_keys":["post-key","invented"]}')
    assert likes.relevant_keys([post()], {}) == {'post-key'}


@pytest.mark.parametrize('outcome', ['liked', 'uncertain'])
def test_run_journals_writes_and_never_retries_them(monkeypatch, tmp_path, outcome):
    calls = []
    monkeypatch.setattr(likes, 'ROOT', tmp_path)
    monkeypatch.setattr(likes, 'load_editorial_context', lambda: {'content': 'AI agents'})
    monkeypatch.setattr(likes, 'relevant_keys', lambda posts, context: {p['key'] for p in posts})
    def cli(*args):
        if args[:2] == ('linkedin', 'whoami'):
            return {'logged_in': True, 'public_id': 'my-account'}
        if args[:2] in [('browser', 'open'), ('browser', 'close')]:
            return {}
        if args[2] == likes.SNAPSHOT:
            return [post()]
        calls.append(args)
        return {'status': outcome}
    monkeypatch.setattr(likes, 'opencli', cli)
    if outcome == 'uncertain':
        with pytest.raises(RuntimeError, match='could not be confirmed'):
            likes.run(apply=True, limit=1)
    else:
        assert likes.run(apply=True, limit=1)['liked'] == 1
    assert likes.run(apply=True, limit=1)['liked'] == 0
    assert len(calls) == 1
