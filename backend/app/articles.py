"""Retrieve full X Articles through the authenticated, read-only Twitter CLI."""

import math
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from app.feed import cli_python_command
from app.twitter_cli import CliExecutionError, CliNotFoundError, CliTimeoutError, InvalidCliOutputError


class ArticleLinkError(ValueError):
    pass


class ArticleContentError(ValueError):
    pass


def parse_article_link(value: str) -> tuple[str, str]:
    try:
        parsed = urlsplit(value.strip())
        host = (parsed.hostname or "").lower().removeprefix("www.")
        match = re.fullmatch(r"/([A-Za-z0-9_]{1,15}|i/web)/status/([0-9]+)(?:/)?", parsed.path)
        if (parsed.scheme != "https" or host not in {"x.com", "twitter.com", "mobile.twitter.com"}
                or parsed.username or parsed.password or parsed.port not in {None, 443} or not match):
            raise ValueError()
        return match[2], f"https://x.com/{match[1]}/status/{match[2]}"
    except (ValueError, TypeError, AttributeError):
        raise ArticleLinkError("Paste a full X or Twitter post link, such as https://x.com/username/status/123. Use the post that contains the article.") from None


def normalize_article(payload, source_url):
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise ArticleContentError("X returned an unreadable article response. Try loading the article again.")
    title, body = data.get("articleTitle"), data.get("articleText")
    if not isinstance(title, str) or not title.strip() or not isinstance(body, str) or not body.strip():
        raise ArticleContentError("This post does not expose a full X article. Check the link and your Twitter CLI access; a post preview is not enough to print the article.")
    author = data.get("author") if isinstance(data.get("author"), dict) else {}
    handle = author.get("screenName", "")
    handle = handle if isinstance(handle, str) and re.fullmatch(r"[A-Za-z0-9_]{1,15}", handle) else ""
    rich = payload.get("rich_article")
    if isinstance(rich, dict):
        body = rich_article_markdown(rich) or body
    words = len(re.findall(r"\S+", body))
    return {
        "id": parse_article_link(source_url)[0], "source_url": source_url,
        "title": title.strip(), "markdown": body.replace("\r\n", "\n").strip("\r\n"),
        "author_name": author.get("name") if isinstance(author.get("name"), str) else "",
        "author_handle": handle, "published_at": data.get("createdAtISO") if isinstance(data.get("createdAtISO"), str) else "",
        "word_count": words, "reading_minutes": max(1, math.ceil(words / 220)),
    }


def article_image(media):
    """Only embed original images hosted on X's image CDN."""
    info = media.get("media_info", {}) if isinstance(media, dict) else {}
    url = info.get("original_img_url")
    if not isinstance(url, str):
        return ""
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname != "pbs.twimg.com" or parsed.username
                or parsed.password or parsed.port not in {None, 443}):
            return ""
    except ValueError:
        return ""
    query = dict(parse_qsl(parsed.query))
    query["name"] = "orig"
    url = urlunsplit(parsed._replace(query=urlencode(query), fragment=""))
    # Angle brackets prevent parentheses in a URL from terminating Markdown.
    url = url.replace("<", "%3C").replace(">", "%3E").replace("\n", "%0A").replace("\r", "%0D")
    alt = media.get("alt_text") or info.get("alt_text") or ""
    alt = re.sub(r"[\\\[\]\r\n]", " ", str(alt))
    return f"![{alt}](<{url}>)"


def rich_article_markdown(article):
    state = article.get("content_state") or {}
    blocks = state.get("blocks") or []
    if not blocks:
        return ""
    entities = state.get("entityMap") or {}
    if isinstance(entities, list):
        entities = {str(item["key"]): item.get("value", {}) for item in entities if isinstance(item, dict) and "key" in item}
    media = {str(item.get("media_id")): item for item in article.get("media_entities", []) if isinstance(item, dict)}
    parts = []
    cover = article_image(article.get("cover_media"))
    if cover:
        parts.append(cover)
    ordered_counter = 0
    for block in blocks:
        kind, text = block.get("type", "unstyled"), block.get("text", "")
        if kind == "atomic":
            for span in block.get("entityRanges", []):
                entity = entities.get(str(span.get("key")), {})
                data = entity.get("data") or {}
                if entity.get("type") == "MEDIA":
                    for item in data.get("mediaItems", []):
                        image = article_image(media.get(str(item.get("mediaId"))))
                        if image:
                            parts.append(image)
                elif entity.get("type") == "MARKDOWN" and isinstance(data.get("markdown"), str):
                    parts.append(data["markdown"])
                elif entity.get("type") == "DIVIDER":
                    parts.append("---")
                elif entity.get("type") == "TWEET" and re.fullmatch(r"[0-9]+", str(data.get("tweetId", ""))):
                    parts.append(f"[View embedded post on X](https://x.com/i/web/status/{data['tweetId']})")
            continue
        if not text:
            continue
        if kind != "ordered-list-item":
            ordered_counter = 0
        prefix = {"header-one": "# ", "header-two": "## ", "header-three": "### ",
                  "blockquote": "> ", "unordered-list-item": "- "}.get(kind, "")
        if kind == "ordered-list-item":
            ordered_counter += 1
            prefix = f"{ordered_counter}. "
        parts.append(f"```\n{text}\n```" if kind == "code-block" else prefix + text)
    return "\n\n".join(parts)


def _read_article(tweet_id):
    command = [*cli_python_command(), "-c",
               "import runpy, sys; runpy.run_path(sys.argv[1], run_name='__main__')",
               str(Path(__file__).with_name("article_bridge.py"))]
    try:
        result = subprocess.run(command, input=json.dumps({"tweet_id": tweet_id}), capture_output=True,
                                text=True, timeout=45, check=False)
    except FileNotFoundError as exc:
        raise CliNotFoundError("The twitter CLI Python interpreter was not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise CliTimeoutError("Loading this X article timed out. Please retry.") from exc
    if result.returncode:
        raise CliExecutionError("Unable to load the article")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise InvalidCliOutputError("X returned an invalid article response") from exc


def fetch_article(url):
    tweet_id, source_url = parse_article_link(url)
    try:
        result = _read_article(tweet_id)
    except (CliExecutionError, InvalidCliOutputError) as exc:
        raise ArticleContentError("The Twitter client could not retrieve this article. Check your Twitter CLI sign-in and access to the original post, then retry.") from exc
    return normalize_article(result, source_url)
