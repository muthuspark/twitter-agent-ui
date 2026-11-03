from concurrent.futures import ThreadPoolExecutor
import json
import shutil
import subprocess
import threading

import pytest
from fastapi.testclient import TestClient

from app import prospects, reddit_browser
from app.main import app


URL = "https://www.reddit.com/r/saas/comments/abc123/"


@pytest.fixture
def saved(monkeypatch, tmp_path):
    monkeypatch.setenv("PROSPECTS_DB_PATH", str(tmp_path / "prospects.sqlite3"))
    monkeypatch.setenv("REDDIT_CLI_BACKEND", "opencli")
    run = {"id": "publication-run", "status": "complete", "started_at": "2026-11-03", "queries": [],
           "posts": [{"url": URL, "title": "Lost decisions", "requirements": []}], "warnings": []}
    prospects.save_run(run)
    calls = []
    def post(post_id, text, username):
        calls.append((post_id, text, username))
        assert prospects.publication_status(URL)["status"] == "pending"
        return {"status": "posted", "comment_id": "reply123", "message": "Reply posted on Reddit."}
    monkeypatch.setattr(reddit_browser, "post_comment", post)
    return run, calls


def test_exact_edited_text_is_saved_and_posted_once_across_runs(saved):
    text = "  Try a decision log.\n\nWhat happens after a meeting? & <details>  "
    result = prospects.publish_reply("publication-run", URL, text, "founder")
    assert saved[1] == [("abc123", text, "founder")]
    assert result["status"] == "posted" and result["text"] == text
    assert result["comment_url"] == URL + "_/reply123/"
    assert prospects.get_prospect("publication-run", URL)["publication"] == result
    assert prospects.get_prospect("publication-run", URL)["draft_text"] == text
    assert prospects.publish_reply("publication-run", URL, "A duplicate", "founder") == result
    run = {**saved[0], "id": "later-run"}
    prospects.save_run(run)
    assert prospects.publish_reply("later-run", URL, "Another duplicate", "founder") == result
    assert len(saved[1]) == 1


@pytest.mark.parametrize("text", ["", "   ", "x" * 10001])
def test_invalid_replies_never_reach_reddit(saved, text):
    with pytest.raises(ValueError):
        prospects.publish_reply("publication-run", URL, text, "founder")
    assert not saved[1] and prospects.publication_status(URL) is None


def test_only_saved_reddit_destinations_and_valid_accounts_can_be_posted(saved):
    with pytest.raises(LookupError):
        prospects.publish_reply("publication-run", URL.replace("abc123", "other"), "Reply", "founder")
    run = saved[0]
    run["posts"].append({"url": "https://x.com/person/status/123"})
    prospects.save_run(run)
    with pytest.raises(ValueError, match="Reddit"):
        prospects.publish_reply("publication-run", "https://x.com/person/status/123", "Reply", "founder")
    with pytest.raises(ValueError):
        prospects.publish_reply("publication-run", URL, "Reply", "other account")
    assert not saved[1]


def test_pending_request_blocks_concurrent_duplicate(saved, monkeypatch):
    started, finish = threading.Event(), threading.Event()
    def waiting(*args):
        saved[1].append(args)
        started.set()
        assert finish.wait(5)
        return {"status": "posted", "comment_id": "reply123", "message": "Posted"}
    monkeypatch.setattr(reddit_browser, "post_comment", waiting)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(prospects.publish_reply, "publication-run", URL, "Reply", "founder")
        assert started.wait(5)
        try:
            duplicate = prospects.publish_reply("publication-run", URL, "Duplicate", "founder")
            assert duplicate["status"] == "pending"
        finally:
            finish.set()
        assert future.result()["status"] == "posted"
    assert len(saved[1]) == 1


def test_definite_failure_allows_manual_retry_but_unknown_outcome_blocks_it(saved, monkeypatch):
    monkeypatch.setattr(reddit_browser, "post_comment", lambda *args: {"status": "failed", "message": "Rate limited"})
    assert prospects.publish_reply("publication-run", URL, "Reply", "founder")["status"] == "failed"
    monkeypatch.setattr(reddit_browser, "post_comment", lambda *args: {"status": "uncertain", "message": "Check Reddit"})
    assert prospects.publish_reply("publication-run", URL, "Reply", "founder")["status"] == "uncertain"
    monkeypatch.setattr(reddit_browser, "post_comment", lambda *args: pytest.fail("No retry of uncertain publication"))
    assert prospects.publish_reply("publication-run", URL, "Reply", "founder")["status"] == "uncertain"


def test_unsaved_reply_is_not_submitted(saved, monkeypatch):
    monkeypatch.setattr(prospects, "save_draft", lambda *args: (_ for _ in ()).throw(OSError("private")))
    result = prospects.publish_reply("publication-run", URL, "Reply", "founder")
    assert result["status"] == "failed" and "private" not in result["message"]
    assert not saved[1]


def test_publication_endpoint_preserves_text_and_validation(saved):
    client = TestClient(app)
    path = "/api/prospects/runs/publication-run/publish"
    body = {"url": URL, "text": "My edited reply", "username": "founder"}
    response = client.post(path, json=body)
    assert response.status_code == 200 and response.json()["status"] == "posted"
    assert saved[1][0][1] == body["text"]
    assert client.post(path, json={**body, "text": ""}).status_code == 422
    assert client.post(path, json={**body, "url": URL.replace("abc123", "other")}).status_code == 404
    assert client.post(path, json={"url": URL, "text": "Reply"}).status_code == 422


@pytest.mark.skipif(not shutil.which("node"), reason="Node is required to verify browser-side JavaScript")
@pytest.mark.parametrize("scenario,expected,posts", [
    ("success", "posted", 1), ("wrong_account", "failed", 0),
    ("unauthenticated", "failed", 0), ("read_error", "failed", 0),
    ("write_error", "uncertain", 1), ("missing_confirmation", "uncertain", 1),
    ("rate_limit", "failed", 1), ("rejected", "failed", 1), ("server_error", "uncertain", 1),
])
def test_real_browser_script_with_mocked_reddit_responses(scenario, expected, posts):
    # Execute the actual write script with fake fetch. No network or publication.
    text = 'Exact reply with "quotes", & symbols, and\nnewlines.'
    harness = """
const scenario = SCENARIO;
const input = INPUT;
const requests = [];
global.location = {origin:'https://www.reddit.com'};
global.fetch = async (url, options) => {
  const write = options.method === 'POST';
  requests.push({url,write,body:options.body});
  if (!write) {
    if (scenario === 'read_error') throw new Error('private');
    return {ok:scenario !== 'unauthenticated', json:async () => ({data:{name:scenario === 'wrong_account' ? 'someone-else' : 'founder',modhash:'private'}})};
  }
  if (scenario === 'write_error') throw new Error('private');
  if (scenario === 'server_error') return {ok:false,status:500};
  if (scenario === 'rejected') return {ok:false,status:403};
  if (scenario === 'rate_limit') return {ok:true,json:async () => ({json:{errors:[['RATELIMIT','private']]}})};
  if (scenario === 'missing_confirmation') return {ok:true,json:async () => ({json:{errors:[]}})};
  return {ok:true,json:async () => ({json:{errors:[],data:{things:[{kind:'t1',data:{id:'reply123',parent_id:'t3_abc123',author:'founder'}}]}}})};
};
(SCRIPT)(input).then(result => {
  const writes=requests.filter(r=>r.write);
  const body=writes[0] ? Object.fromEntries(new URLSearchParams(writes[0].body)) : null;
  console.log(JSON.stringify({result,writes:writes.length,text:body?.text,parent:body?.thing_id}));
});
""".replace("SCENARIO", json.dumps(scenario)).replace("INPUT", json.dumps({"postId": "abc123", "text": text, "username": "founder"})).replace("SCRIPT", reddit_browser.COMMENT_SCRIPT)
    process = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=10, check=True)
    result = json.loads(process.stdout)
    assert result["result"]["status"] == expected and result["writes"] == posts
    assert "private" not in json.dumps(result["result"])
    if posts:
        assert result["text"] == text and result["parent"] == "t3_abc123"
