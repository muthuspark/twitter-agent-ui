import pytest
from fastapi.testclient import TestClient
from app import articles
from app.twitter_cli import CliTimeoutError, CliNotFoundError, CliExecutionError

EXAMPLE = "https://x.com/shannholmberg/status/2117202336451895796"


def payload():
    return {"ok":True,"data":{"id":"2117202336451895796","articleTitle":"  A full article  ",
        "articleText":"Intro paragraph.\n\n# A section\n\nLast paragraph.",
        "author":{"name":"Author","screenName":"shannholmberg"},"createdAtISO":"2026-11-02T10:29:07+00:00"}}


@pytest.mark.parametrize("url", [
    "https://x.com/user/status/123", "https://twitter.com/user/status/123?s=20",
    "https://mobile.twitter.com/user/status/123/", "https://www.x.com/i/web/status/123#fragment",
])
def test_valid_post_links_are_canonical_and_reduce_to_numeric_id(url):
    tweet_id,canonical=articles.parse_article_link(url)
    assert tweet_id=="123" and canonical.startswith("https://x.com/")
    assert "?" not in canonical and "#" not in canonical


@pytest.mark.parametrize("url", ["https://x.com.evil.test/user/status/123", "https://x.com@evil.test/user/status/123",
    "https://name:pass@x.com/user/status/123", "http://x.com/user/status/123", "https://x.com:8080/user/status/123",
    "https://x.com/user/status/not-a-number", "https://x.com/user", "https://x.com/i/article/123",
    "file:///etc/passwd", "javascript:alert(1)", "123; echo unsafe", "https://127.0.0.1/user/status/123"])
def test_invalid_urls_cannot_be_used_as_commands_or_arbitrary_fetches(url):
    with pytest.raises(articles.ArticleLinkError):articles.parse_article_link(url)


def test_fetches_only_read_only_article_command_and_preserves_full_body(monkeypatch):
    data=payload();data['data']['articleText']+='\n\n'+'Full content. '*10000
    def fake(tweet_id):
        assert tweet_id=='2117202336451895796'
        return data
    monkeypatch.setattr(articles,'_read_article',fake)
    result=articles.fetch_article(EXAMPLE+'?s=20')
    assert result['markdown']==data['data']['articleText']
    assert result['title']=='A full article'
    assert result['source_url']==EXAMPLE and result['author_handle']=='shannholmberg'
    assert result['word_count']>10000


@pytest.mark.parametrize('data',[{}, {'data':[]}, {'data':{'text':'A post preview only'}},
    {'data':{'articleTitle':'Title','articleText':' '}}, {'data':{'articleTitle':'Title','articleText':123}}])
def test_never_substitutes_post_preview_for_article_content(data):
    with pytest.raises(articles.ArticleContentError):articles.normalize_article(data,EXAMPLE)


def test_handles_missing_or_invalid_author_and_date_without_inventing_metadata():
    data=payload();data['data']['author']={'screenName':'<script>','name':None};data['data']['createdAtISO']=None
    result=articles.normalize_article(data,EXAMPLE)
    assert result['author_name']==result['author_handle']==result['published_at']==''


def test_article_endpoint_and_failure_states(monkeypatch):
    from app import main
    client=TestClient(main.app)
    monkeypatch.setattr(articles,'_read_article',lambda tweet_id:payload())
    assert client.post('/api/articles/read',json={'url':EXAMPLE}).json()['title']=='A full article'
    assert client.post('/api/articles/read',json={'url':'https://example.com'}).status_code==422
    assert client.post('/api/articles/read',json={'url':None}).status_code==422
    for exception,status in [(CliTimeoutError('timeout'),504),(CliNotFoundError('missing CLI'),503),(CliExecutionError('auth failed'),502)]:
        def fail(*args,**kwargs):raise exception
        monkeypatch.setattr(articles,'_read_article',fail)
        assert client.post('/api/articles/read',json={'url':EXAMPLE}).status_code==status


def image(media_id, url):
    return {'media_id': media_id, 'media_info': {'original_img_url': url}}


def test_rich_article_preserves_cover_inline_order_and_atomic_content():
    rich = {
        'cover_media': image('cover', 'https://pbs.twimg.com/media/cover.jpg'),
        # API media order differs from document order.
        'media_entities': [image('second', 'https://pbs.twimg.com/media/second.jpg'),
                           image('first', 'https://pbs.twimg.com/media/first.jpg')],
        'content_state': {
            'entityMap': [
                {'key': '9', 'value': {'type': 'MEDIA', 'data': {'mediaItems': [{'mediaId': 'first'}]}}},
                {'key': '3', 'value': {'type': 'MEDIA', 'data': {'mediaItems': [{'mediaId': 'second'}]}}},
                {'key': '1', 'value': {'type': 'MARKDOWN', 'data': {'markdown': '| A | B |\n|---|---|\n| 1 | 2 |'}}},
                {'key': '2', 'value': {'type': 'TWEET', 'data': {'tweetId': '123'}}},
            ],
            'blocks': [
                {'type': 'unstyled', 'text': 'Intro'},
                {'type': 'atomic', 'entityRanges': [{'key': 9}]},
                {'type': 'header-two', 'text': 'Middle'},
                {'type': 'atomic', 'entityRanges': [{'key': 3}]},
                {'type': 'atomic', 'entityRanges': [{'key': 1}]},
                {'type': 'atomic', 'entityRanges': [{'key': 2}]},
                {'type': 'unstyled', 'text': 'Last paragraph'},
            ],
        },
    }
    data=payload();data['rich_article']=rich
    body=articles.normalize_article(data, EXAMPLE)['markdown']
    positions=[body.index(value) for value in ['cover.jpg', 'Intro', 'first.jpg', '## Middle', 'second.jpg', '| A | B |', 'https://x.com/i/web/status/123', 'Last paragraph']]
    assert positions==sorted(positions)
    assert body.count('![')==3


@pytest.mark.parametrize('url', ['http://pbs.twimg.com/media/x.jpg', 'https://pbs.twimg.com.evil.test/x',
    'https://evil.test/x', 'file:///etc/passwd', 'https://user:pass@pbs.twimg.com/x', 'https://pbs.twimg.com:8080/x'])
def test_upstream_media_cannot_embed_arbitrary_or_insecure_urls(url):
    assert articles.article_image(image('1', url))==''


def test_missing_media_is_skipped_and_dict_entity_map_is_supported():
    rich={'content_state': {'blocks': [{'type':'atomic','entityRanges':[{'key':0}]}],
        'entityMap': {'0': {'type':'MEDIA', 'data': {'mediaItems':[{'mediaId':'missing'}]}}}}}
    assert articles.rich_article_markdown(rich)==''
    data=payload();data['rich_article']=rich
    assert articles.normalize_article(data, EXAMPLE)['markdown']==data['data']['articleText']


def test_bridge_preserves_raw_article_without_changing_client():
    from app.article_bridge import fetch_rich_article
    class Client:
        def _graphql_get(self, operation):
            assert operation=='TweetResultByRestId'
            return {'data':{'tweetResult':{'result':{'tweet':{'article':{'article_results':{'result':{'title':'Title','cover_media':{}}}}}}}}}
        def fetch_article(self, tweet_id):
            assert tweet_id=='123'
            self._graphql_get('TweetResultByRestId')
            return 'parsed tweet'
    client=Client();original=client._graphql_get
    result=fetch_rich_article(client,'123',lambda tweet: {'articleText':tweet})
    assert result['rich_article']['title']=='Title'
    assert result['data']['articleText']=='parsed tweet'
    assert client._graphql_get==original


def test_article_bridge_runs_in_cli_environment_with_bounded_timeout(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(articles,'cli_python_command',lambda:['/cli/python'])
    def run(command, **kwargs):
        assert command[0]=='/cli/python' and command[-1].endswith('/article_bridge.py')
        assert kwargs['timeout']==45 and kwargs['capture_output']
        assert kwargs['input']=='{"tweet_id": "123"}'
        return SimpleNamespace(returncode=0,stdout='{"data": {}}')
    monkeypatch.setattr(articles.subprocess,'run',run)
    assert articles._read_article('123')=={'data':{}}
