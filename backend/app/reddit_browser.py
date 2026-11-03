"""Reddit collection and explicitly requested replies through signed-in Chrome.

Search navigates the real search page: OpenCLI's built-in fetch-based search can
hit a login wall even when navigation and its post reader work in the same session.
"""

import json
import os
import re
import shutil
import subprocess
import uuid
from urllib.parse import urlencode

from app.reddit_cli import RedditCliError, _post


MESSAGES = {
    "missing": "OpenCLI is not installed. Run npm install -g @jackwener/opencli@2.0.2.",
    "not_authenticated": "OpenCLI could not access signed-in Reddit. Keep Chrome open with the OpenCLI extension connected and sign in to reddit.com.",
    "forbidden": "Reddit blocked browser collection. Research will use web fallback.",
    "rate_limited": "Reddit rate limited browser collection. Try again later.",
    "timeout": "OpenCLI timed out. Check that Chrome and the OpenCLI extension are running.",
    "not_found": "The Reddit post is unavailable in this browser session.",
    "invalid_output": "OpenCLI returned an unsupported Reddit response. Research will use web fallback.",
    "api_error": "OpenCLI could not complete Reddit collection. Run opencli doctor to check the browser connection and profile.",
}
SESSION = f"jovis-reddit-{os.getpid()}"
_LISTINGS = {}


class BrowserRedditError(RedditCliError):
    def __init__(self, code):
        super().__init__(code)
        self.args = (MESSAGES[self.code],)


def _run(args, timeout=60):
    binary = shutil.which(os.environ.get("OPENCLI_PATH") or "opencli")
    if not binary:
        raise BrowserRedditError("missing")
    try:
        result = subprocess.run(
            [binary, *args], capture_output=True, text=True, timeout=timeout, check=False,
            env={**os.environ, "OPENCLI_CLOSE_OWNED_TAB": "1"},
        )
    except subprocess.TimeoutExpired:
        raise BrowserRedditError("timeout") from None
    except (OSError, UnicodeError):
        raise BrowserRedditError("api_error") from None
    try:
        envelope = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise BrowserRedditError("invalid_output") from None
    if not isinstance(envelope, dict):
        raise BrowserRedditError("invalid_output")
    if envelope.get("ok") is False:
        error = envelope.get("error")
        code = error.get("code") if isinstance(error, dict) else ""
        # Never forward upstream messages, page previews, hints, or trace paths.
        mapped = {
            "AUTH_REQUIRED": "not_authenticated", "LOGIN_WALL": "not_authenticated",
            "RATE_LIMITED": "rate_limited", "EMPTY_RESULT": "not_found",
            "TIMEOUT": "timeout",
        }.get(code, "api_error") if isinstance(code, str) else "api_error"
        raise BrowserRedditError(mapped)
    if result.returncode or envelope.get("ok") is not True or "data" not in envelope:
        raise BrowserRedditError("invalid_output")
    return envelope["data"]


def connection_status():
    try:
        rows = _run(["reddit", "whoami", "-f", "json", "--window", "background"])
        if not isinstance(rows, list):
            raise BrowserRedditError("invalid_output")
        username = next((row.get("value") for row in rows if isinstance(row, dict) and row.get("field") == "Username"), "")
        if not isinstance(username, str) or not re.fullmatch(r"u/[A-Za-z0-9_-]{1,30}", username):
            raise BrowserRedditError("not_authenticated")
        return {"installed": True, "authenticated": True, "username": username[2:],
                "message": "Reddit connected through Chrome (OpenCLI)."}
    except RedditCliError as exc:
        return {"installed": exc.code != "missing", "authenticated": False, "username": "", "message": str(exc)}


SEARCH_SCRIPT = r"""(() => {
  if (location.origin !== 'https://www.reddit.com' || location.pathname !== '/search/')
    return {error: 'not_authenticated'};
  const text = document.body?.innerText || '';
  if (/blocked by network security|access denied|whoa there, pardner/i.test(text))
    return {error: 'forbidden'};
  if (/too many requests|rate limit exceeded/i.test(text)) return {error: 'rate_limited'};
  const units = Array.from(document.querySelectorAll('[data-testid="search-post-unit"]')).slice(0,10);
  const posts = units.map(unit => {
    const link = unit.querySelector('a[data-testid="post-title"]');
    const heading = unit.querySelector('a[data-testid="post-title-text"]');
    const permalink = link?.getAttribute('href') || '';
    const id = permalink.match(/\/comments\/([a-z0-9]+)(?:\/|$)/)?.[1] || '';
    let author = '';
    for (const tracker of unit.querySelectorAll('search-telemetry-tracker[data-faceplate-tracking-context]')) {
      try {
        const context = JSON.parse(tracker.getAttribute('data-faceplate-tracking-context'));
        if (context?.post?.id === 't3_' + id && typeof context?.profile?.name === 'string') {
          author = context.profile.name; break;
        }
      } catch {}
    }
    const stamp = Date.parse(unit.querySelector('time[datetime]')?.getAttribute('datetime') || '');
    return {id, permalink, title: (heading?.textContent || link?.getAttribute('aria-label') || '').trim(),
      author, subreddit: permalink.match(/^\/r\/([^/]+)/)?.[1] || '',
      created_utc: Number.isFinite(stamp) ? stamp / 1000 : 0, selftext: ''};
  });
  const empty = /no (?:results|posts) found|couldn.t find any results|there (?:are|were) no results|we couldn.t find/i.test(text);
  return {posts, empty};
})()"""


def search(query):
    url = "https://www.reddit.com/search/?" + urlencode({"q": query, "type": "posts", "sort": "relevance", "t": "month"})
    _run(["browser", "open", url, "--session", SESSION, "--window", "background"])
    data = _run(["browser", "eval", SEARCH_SCRIPT, "--session", SESSION])
    if not isinstance(data, dict):
        raise BrowserRedditError("invalid_output")
    if data.get("error"):
        raise BrowserRedditError(data["error"])
    if not isinstance(data.get("posts"), list) or (not data["posts"] and data.get("empty") is not True):
        raise BrowserRedditError("invalid_output")
    try:
        posts = [_post(post) for post in data["posts"][:10]]
    except RedditCliError:
        raise BrowserRedditError("invalid_output") from None
    for post in posts:
        _LISTINGS[post["id"]] = post
    # Retain at most one run's search budget in memory, never credential data.
    while len(_LISTINGS) > 200:
        del _LISTINGS[next(iter(_LISTINGS))]
    return posts


def read(post_id):
    if not isinstance(post_id, str) or not re.fullmatch(r"[a-z0-9]+", post_id) or post_id not in _LISTINGS:
        raise BrowserRedditError("invalid_output")
    rows = _run(["reddit", "read", post_id, "--limit", "25", "--depth", "1",
                 "--max-length", "40000", "-f", "json", "--window", "background"])
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict) or rows[0].get("type") != "POST":
        raise BrowserRedditError("invalid_output")
    original = rows[0]
    text, author = original.get("text"), original.get("author")
    if not isinstance(text, str) or not isinstance(author, str):
        raise BrowserRedditError("invalid_output")
    title, _, body = text.partition("\n\n")
    post = {**_LISTINGS[post_id], "title": title, "selftext": body, "author": author}
    comments = []
    for row in rows[1:]:
        if not isinstance(row, dict):
            raise BrowserRedditError("invalid_output")
        if row.get("type") == "L0" and isinstance(row.get("author"), str) and isinstance(row.get("text"), str):
            comments.append({"author": row["author"], "body": row["text"]})
    # OpenCLI's row output omits completeness metadata; never claim exhaustive coverage.
    return {"post": post, "comments": comments[:25], "comments_incomplete": True}


def close_research():
    _LISTINGS.clear()
    try:
        _run(["browser", "close", "--session", SESSION], timeout=10)
    except RedditCliError:
        pass  # Cleanup failure must not discard saved research.


# Fixed write operation, invoked only by the explicit reply-publication endpoint.
# Reddit documents `thing_id` as the parent parameter for POST /api/comment.
COMMENT_SCRIPT = r"""async ({postId, text, username}) => {
  let submitted = false;
  try {
    if (location.origin !== 'https://www.reddit.com') return {status:'failed', code:'not_authenticated'};
    const meResponse = await fetch('/api/me.json?raw_json=1', {credentials:'include'});
    if (!meResponse.ok) return {status:'failed', code:'not_authenticated'};
    const me = (await meResponse.json())?.data;
    if (!me?.name || me.name.toLowerCase() !== username.toLowerCase())
      return {status:'failed', code:'account_changed'};
    const body = new URLSearchParams({api_type:'json', thing_id:'t3_' + postId, text, raw_json:'1'});
    if (me.modhash) body.set('uh', me.modhash);
    submitted = true;
    const response = await fetch('/api/comment', {
      method:'POST', credentials:'include', headers:{'Content-Type':'application/x-www-form-urlencoded'}, body:body.toString()
    });
    if (!response.ok) {
      if ([400,401,403,404,429].includes(response.status)) return {status:'failed', code:response.status === 429 ? 'rate_limited' : 'rejected'};
      return {status:'uncertain'};
    }
    const result = await response.json();
    const errors = result?.json?.errors;
    if (Array.isArray(errors) && errors.length) {
      const rateLimited = errors.some(error => Array.isArray(error) && error[0] === 'RATELIMIT');
      return {status:'failed', code:rateLimited ? 'rate_limited' : 'rejected'};
    }
    const things = result?.json?.data?.things;
    const comment = Array.isArray(things) ? things.find(thing => thing?.kind === 't1')?.data : null;
    if (!comment || comment.parent_id !== 't3_' + postId || comment.author?.toLowerCase() !== username.toLowerCase()
        || !/^[a-z0-9]+$/.test(comment.id || '')) return {status:'uncertain'};
    return {status:'posted', comment_id:comment.id};
  } catch {
    return {status:submitted ? 'uncertain' : 'failed', code:'connection'};
  }
}"""


def post_comment(post_id, text, username):
    if not re.fullmatch(r"[a-z0-9]+", post_id) or not re.fullmatch(r"[A-Za-z0-9_-]{1,30}", username):
        raise ValueError("Invalid Reddit post or account")
    session = f"jovis-reddit-reply-{uuid.uuid4().hex}"
    try:
        try:
            _run(["browser", "open", "https://www.reddit.com", "--session", session, "--window", "background"])
        except RedditCliError as exc:
            return {"status": "failed", "message": str(exc)}
        payload = json.dumps({"postId": post_id, "text": text, "username": username})
        try:
            # No retries: once this command starts, a timeout may conceal a successful post.
            result = _run(["browser", "eval", f"({COMMENT_SCRIPT})({payload})", "--session", session])
        except RedditCliError:
            return {"status": "uncertain", "message": "Posting could not be confirmed. Check Reddit before posting again."}
        if isinstance(result, dict) and result.get("status") == "posted" and isinstance(result.get("comment_id"), str) and re.fullmatch(r"[a-z0-9]+", result["comment_id"]):
            return {"status": "posted", "comment_id": result["comment_id"], "message": "Reply posted on Reddit."}
        if isinstance(result, dict) and result.get("status") == "failed":
            messages = {"account_changed": "The signed-in Reddit account changed. Refresh Reddit status before posting.",
                        "not_authenticated": MESSAGES["not_authenticated"], "rate_limited": MESSAGES["rate_limited"],
                        "rejected": "Reddit rejected the reply. Check that the thread allows comments and your account can reply there.",
                        "connection": "Could not connect to Reddit. Your reply was not submitted."}
            return {"status": "failed", "message": messages.get(result.get("code"), "The reply was not submitted. Check Reddit and try again.")}
        return {"status": "uncertain", "message": "Posting could not be confirmed. Check Reddit before posting again."}
    finally:
        try:
            _run(["browser", "close", "--session", session], timeout=10)
        except RedditCliError:
            pass
