from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import trends, main

NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)
SINCE = NOW - timedelta(days=7)
DATE = (NOW - timedelta(hours=4)).isoformat()


def client_for(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_hn_filters_dates_topics_and_ids_and_preserves_metrics():
    good = dict(objectID='123', title='AI coding tools', points=80, num_comments=12,
                created_at=DATE, url='https://example.com/ai?utm_source=hn')
    hits = [good, {**good, 'objectID': ''}, {**good, 'created_at': '2020-01-01'},
            {**good, 'created_at': (NOW + timedelta(days=1)).isoformat()},
            {**good, 'title': 'My favorite sandwich'}, {**good, 'points': 10}]
    with client_for(lambda req: httpx.Response(200, json={'hits': hits})) as client:
        sources = trends.fetch_hacker_news(client, SINCE, NOW)
    assert len(sources) == 1
    assert sources[0]['metrics'] == {'points': 80, 'comments': 12}
    assert sources[0]['date_basis'] == 'Submitted'
    assert sources[0]['url'] == 'https://example.com/ai'


def test_github_uses_creation_date_not_recent_updates():
    repo = dict(id=1, full_name='org/ai', html_url='https://github.com/org/ai',
                created_at=DATE, updated_at=DATE, stargazers_count=100, forks_count=2)
    items = [repo, {**repo, 'created_at': '2020-01-01'}, {**repo, 'fork': True},
             {**repo, 'stargazers_count': 24}]
    with client_for(lambda req: httpx.Response(200, json={'items': items})) as client:
        sources = trends.fetch_github(client, SINCE, NOW)
    assert len(sources) == 1
    assert sources[0]['metrics']['stars'] == 100
    assert sources[0]['date_basis'] == 'Created'


@pytest.mark.parametrize('atom', [False, True])
def test_publishers_require_publication_dates_and_do_not_invent_popularity(atom):
    if atom:
        xml = f'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>New AI tool</title><published>{DATE}</published><link href="https://example.com/ai"/><summary>Useful tool</summary></entry><entry><title>Updated old tool</title><updated>{DATE}</updated><link href="https://example.com/old"/></entry></feed>'
    else:
        xml = f'<rss><channel><item><title>New AI tool</title><pubDate>{DATE}</pubDate><link>https://example.com/ai</link><description>&lt;p&gt;Useful tool&lt;/p&gt;</description></item></channel></rss>'
    with client_for(lambda req: httpx.Response(200, text=xml)) as client:
        sources = trends.fetch_publisher(client, 'Publisher', 'https://example.com/feed', SINCE, NOW)
    assert len(sources) == 1
    assert sources[0]['summary'] == 'Useful tool'
    assert sources[0]['metrics'] == {}
    assert sources[0]['evidence'] == 'publisher'


def test_research_partial_failures_dedupe_and_all_failure():
    def handler(req):
        if req.url.host == 'hn.algolia.com':
            return httpx.Response(200, json={'hits': [dict(objectID='123', title='AI tools', points=90, created_at=DATE, url='https://example.com/ai')]})
        if req.url.host == 'openai.com':
            return httpx.Response(200, text=f'<rss><channel><item><title>AI tools</title><pubDate>{DATE}</pubDate><link>https://example.com/ai?utm_campaign=test</link><description>Longer official summary of these AI tools.</description></item></channel></rss>')
        return httpx.Response(503)
    with client_for(handler) as client:
        result = trends.fetch_trending_research(now=NOW, client=client)
    assert len(result['sources']) == 1
    assert result['sources'][0]['metrics']['points'] == 90
    assert result['sources'][0]['summary'].startswith('Longer official')
    assert 'GitHub was unavailable' in result['warning']
    assert 'rank' not in result['sources'][0]
    with client_for(lambda req: httpx.Response(503)) as client:
        with pytest.raises(trends.ResearchError):
            trends.fetch_trending_research(now=NOW, client=client)


@pytest.mark.parametrize('url', ['javascript:alert(1)', 'https://user:pass@example.com', 'not a url'])
def test_unsafe_source_links_rejected(url):
    assert trends.safe_url(url) == ''


def test_trend_api_attaches_only_real_references(monkeypatch, tmp_path):
    source = {'id': 'hn:123', 'title': 'AI tools', 'url': 'https://example.com/ai'}
    research = {'sources': [source], 'since': SINCE.isoformat(), 'researched_at': DATE, 'warning': None}
    monkeypatch.setattr(main, 'get_growth_store', lambda: main.GrowthStore(tmp_path / 'growth.sqlite3'))
    monkeypatch.setattr(main, 'fetch_trending_research', lambda: research)
    captured = {}
    def generate(*args, **kwargs):
        captured.update(kwargs)
        return [{'post_text': 'An original draft.', 'source_ids': ['hn:123', 'fake']},
                {'post_text': 'Unsupported draft.', 'source_ids': ['fake']}]
    monkeypatch.setattr(main, 'generate_post_ideas', generate)
    response = TestClient(main.app).post('/api/posts/ideas', json={'source_mode': 'trends'})
    assert response.status_code == 200
    assert response.json()['ideas'] == [{'post_text': 'An original draft.', 'source_ids': ['hn:123'], 'sources': [source]}]
    assert captured['recent_liked_posts'] == []
    assert captured['research_sources'] == [source]
    monkeypatch.setattr(main, 'generate_post_ideas', lambda *a, **k: [{'source_ids': ['fake']}])
    assert TestClient(main.app).post('/api/posts/ideas', json={'source_mode': 'trends'}).status_code == 502


def test_trend_api_research_failure_and_invalid_mode(monkeypatch):
    def unavailable():
        raise trends.ResearchError('No recent sources')
    monkeypatch.setattr(main, 'fetch_trending_research', unavailable)
    client = TestClient(main.app)
    assert client.post('/api/posts/ideas', json={'source_mode': 'trends'}).status_code == 503
    assert client.post('/api/posts/ideas', json={'source_mode': 'unknown'}).status_code == 422


def test_research_prompt_requires_source_ids_and_distinguishes_metrics(monkeypatch):
    from app.codex_client import generate_post_ideas_with_codex
    from app import codex_client
    captured = {}
    source = {'id': 'hn:123', 'title': 'AI tools', 'metrics': {'points': 80}}
    def run(system, payload, schema, **kwargs):
        captured.update(payload)
        return '{"ideas":[{"post_text":"Original observation.","source_ids":["hn:123","hn:123",99]}]}'
    monkeypatch.setattr(codex_client, '_run_codex', run)
    ideas = generate_post_ideas_with_codex('Technology and AI', '', research_sources=[source])
    prompt = captured
    assert prompt['research_sources'] == [source]
    assert 'Each idea MUST include source_ids' in prompt['instruction']
    assert 'cumulative, not growth today' in prompt['instruction']
    assert ideas[0]['source_ids'] == ['hn:123']


@pytest.mark.parametrize('use_research', [False, True])
def test_post_writing_style_applies_to_both_modes_over_voice_memory(use_research, monkeypatch):
    from app.codex_client import generate_post_ideas_with_codex
    from app import codex_client
    captured = {}
    def run(system, payload, schema, **kwargs):
        captured['system'] = system
        return '{"ideas":[{"post_text":"A clear draft."}]}'
    monkeypatch.setattr(codex_client, '_run_codex', run)
    generate_post_ideas_with_codex(
        'Technology and AI', '',
        preference_memory={'summary': 'Use elaborate vocabulary and long sentences.'},
        research_sources=[{'id': 'hn:123', 'title': 'AI tools'}] if use_research else None,
        recent_liked_posts=[] if use_research else [{'id': '123', 'text': 'AI tools'}],
    )
    system = captured['system']
    for requirement in [
        'ASD-STE100', 'approximately 80%', 'not formal compliance',
        'one main idea per sentence', 'Use active voice', 'Keep terminology consistent',
        'concrete examples', 'Introduce complex ideas progressively',
        'Preserve technical accuracy', 'conditions and uncertainty',
        'comprehension, not merely brevity', 'take precedence over conflicting style',
    ]:
        assert requirement in system
