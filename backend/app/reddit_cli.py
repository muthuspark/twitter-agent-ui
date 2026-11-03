"""Read-only Reddit CLI facade: OpenCLI by default, rdt-cli as an opt-in legacy client.

The CLI owns authentication. Only allowlisted public post fields cross this boundary;
credentials and raw CLI diagnostics must never reach research or API responses.
"""

from datetime import datetime, timezone
import json
import os
import re
import shutil
import subprocess


MESSAGES = {
    "missing": "Reddit CLI is not installed. Run uv tool install rdt-cli==0.4.1.",
    "not_authenticated": "Reddit session is unavailable. Log in to Reddit in your browser, then run rdt login as the backend user.",
    "rate_limited": "Reddit rate limited the request. Try again later.",
    "forbidden": "Reddit denied access to this request.",
    "not_found": "This Reddit post is unavailable.",
    "timeout": "Reddit CLI timed out. Try again later.",
    "invalid_output": "Reddit CLI returned an unsupported response. Install rdt-cli==0.4.1.",
    "api_error": "Reddit CLI could not complete the request. Check the local connection and session.",
}


class RedditCliError(Exception):
    def __init__(self, code):
        self.code = code if isinstance(code, str) and code in MESSAGES else "api_error"
        super().__init__(MESSAGES[self.code])


def executable():
    return shutil.which(os.environ.get("REDDIT_CLI_PATH") or "rdt")


def _run(args):
    binary = executable()
    if not binary:
        raise RedditCliError("missing")
    try:
        result = subprocess.run(
            [binary, *args, "--json"], capture_output=True, text=True,
            timeout=60, check=False,
        )
    except subprocess.TimeoutExpired:
        raise RedditCliError("timeout") from None
    except (OSError, UnicodeError):
        raise RedditCliError("api_error") from None
    try:
        envelope = json.loads(result.stdout)
    except (ValueError, TypeError):
        raise RedditCliError("invalid_output") from None
    if not isinstance(envelope, dict) or envelope.get("schema_version") != "1":
        raise RedditCliError("invalid_output")
    if envelope.get("ok") is False:
        error = envelope.get("error")
        raise RedditCliError(error.get("code") if isinstance(error, dict) else "api_error")
    if result.returncode or envelope.get("ok") is not True or "data" not in envelope:
        raise RedditCliError("api_error")
    return envelope["data"]


def connection_status():
    if os.environ.get("REDDIT_CLI_BACKEND", "opencli") != "rdt":
        from app import reddit_browser
        return reddit_browser.connection_status()
    try:
        data = _run(["status"])
        if not isinstance(data, dict) or not isinstance(data.get("authenticated"), bool):
            raise RedditCliError("invalid_output")
        authenticated = data["authenticated"]
        username = data.get("username")
        message = "Reddit session connected." if authenticated else MESSAGES["not_authenticated"]
        if not authenticated:
            # `rdt login` only checks that cookies exist. `status` also probes Reddit,
            # but reports a rejected session inside a successful JSON envelope.
            error = data.get("error")
            error_text = error if isinstance(error, str) else ""
            if re.search(r"\b403\b|forbidden", error_text, re.I):
                message = "Reddit is blocking this request (HTTP 403), even with saved cookies. Check Reddit in your browser on the backend computer. Research will use web fallback while CLI access is unavailable."
            elif re.search(r"\b429\b|rate.limit", error_text, re.I):
                message = MESSAGES["rate_limited"]
            elif re.search(r"\b401\b|unauthorized|expired", error_text, re.I):
                message = "Reddit rejected the saved session. Confirm you are signed in to Reddit in your browser, then run rdt logout followed by rdt login."
            elif isinstance(data.get("cookie_count"), int) and data["cookie_count"] > 0:
                message = "Reddit cookies were found, but live session verification could not finish. Check your connection and refresh the Reddit status."
        return {
            "installed": True, "authenticated": authenticated,
            "username": username if authenticated and isinstance(username, str) and re.fullmatch(r"[\w-]{1,30}", username) else "",
            "message": message,
        }
    except RedditCliError as exc:
        return {"installed": exc.code != "missing", "authenticated": False, "username": "", "message": str(exc)}


def _post(data):
    if not isinstance(data, dict):
        raise RedditCliError("invalid_output")
    post_id = data.get("id", "")
    permalink = data.get("permalink", "")
    if not isinstance(post_id, str) or not re.fullmatch(r"[a-z0-9]+", post_id):
        raise RedditCliError("invalid_output")
    if not isinstance(permalink, str) or not re.match(rf"^/r/[^/]+/comments/{re.escape(post_id)}(?:/|$)", permalink):
        raise RedditCliError("invalid_output")
    fields = {key: data.get(key, "") for key in ("title", "author", "selftext", "subreddit")}
    if any(not isinstance(value, str) for value in fields.values()):
        raise RedditCliError("invalid_output")
    published_at = ""
    try:
        timestamp = float(data.get("created_utc", 0))
        if timestamp > 0:
            date = datetime.fromtimestamp(timestamp, timezone.utc)
            if date <= datetime.now(timezone.utc):
                published_at = date.isoformat()
    except (ValueError, TypeError, OverflowError, OSError):
        pass
    return {**fields, "id": post_id, "url": f"https://www.reddit.com{permalink}", "published_at": published_at}


def search(query):
    if os.environ.get("REDDIT_CLI_BACKEND", "opencli") != "rdt":
        from app import reddit_browser
        return reddit_browser.search(query)
    data = _run(["search", query, "--sort", "relevance", "--time", "month", "--limit", "10", "--compact"])
    if not isinstance(data, list):
        raise RedditCliError("invalid_output")
    return [_post(item) for item in data[:10]]


def read(post_id):
    if os.environ.get("REDDIT_CLI_BACKEND", "opencli") != "rdt":
        from app import reddit_browser
        return reddit_browser.read(post_id)
    if not isinstance(post_id, str) or not re.fullmatch(r"[a-z0-9]+", post_id):
        raise RedditCliError("invalid_output")
    # 0.4.1 returns two raw Reddit listings without --expand-more.
    data = _run(["read", post_id, "--limit", "25"])
    try:
        if not isinstance(data, list) or len(data) != 2:
            raise TypeError
        raw_post = data[0]["data"]["children"][0]["data"]
        raw_comments = data[1]["data"]["children"]
        if not isinstance(raw_comments, list):
            raise TypeError
    except (KeyError, IndexError, TypeError):
        raise RedditCliError("invalid_output") from None
    post = _post(raw_post)
    if post["id"] != post_id:
        raise RedditCliError("invalid_output")
    comments = []
    incomplete = False

    def walk(children, depth=0):
        nonlocal incomplete
        for child in children:
            if not isinstance(child, dict):
                incomplete = True
                continue
            if child.get("kind") == "more":
                incomplete = True
                continue
            item = child.get("data", {})
            if child.get("kind") != "t1" or not isinstance(item, dict):
                continue
            if len(comments) >= 25 or depth >= 8:
                incomplete = True
                continue
            body, author = item.get("body"), item.get("author")
            if isinstance(body, str) and isinstance(author, str):
                comments.append({"author": author, "body": body})
            replies = item.get("replies")
            if isinstance(replies, dict):
                reply_data = replies.get("data")
                nested = reply_data.get("children", []) if isinstance(reply_data, dict) else None
                if isinstance(nested, list):
                    walk(nested, depth + 1)
                else:
                    incomplete = True

    walk(raw_comments)
    count = raw_post.get("num_comments", 0)
    incomplete = incomplete or (isinstance(count, int) and count > len(comments))
    return {"post": post, "comments": comments, "comments_incomplete": incomplete}


def close_research():
    if os.environ.get("REDDIT_CLI_BACKEND", "opencli") != "rdt":
        from app import reddit_browser
        reddit_browser.close_research()
