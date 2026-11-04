"""Public prospect sources. No browser, cookies, or account session access."""
from datetime import datetime, timedelta, timezone
from html import unescape
import os
import re
from urllib.parse import urlsplit

import httpx

from app.prospect_sources import community_batch, directory, canonical_url


class SearchError(Exception):
    pass


def status():
    configured = bool(os.environ.get("EXA_WEB_SEARCH_API", "").strip())
    return {"configured": configured, "communities": directory(),
            "message": "Exa searches Reddit and 20 additional public communities; Hacker News uses public search. No browser session is used."
            if configured else "Set EXA_WEB_SEARCH_API in .env to enable Reddit and community discovery. Hacker News uses public search."}


def _request(method, url, **kwargs):
    try:
        response = httpx.request(method, url, timeout=30, follow_redirects=False, **kwargs)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except (httpx.HTTPError, ValueError):
        # Never expose response bodies, request headers or credentials.
        raise SearchError("Public search unavailable; check API configuration, quota and connectivity.") from None


def _since(now):
    return datetime.fromisoformat(now.replace("Z", "+00:00")) - timedelta(days=2)


def within_window(published_at, now):
    try:
        date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        end = datetime.fromisoformat(now.replace("Z", "+00:00"))
        return end - timedelta(days=2) <= date <= end
    except (ValueError, TypeError, AttributeError):
        return False


def _exa(query, now, domains):
    key = os.environ.get("EXA_WEB_SEARCH_API", "").strip()
    if not key:
        raise SearchError("Exa search unavailable: set EXA_WEB_SEARCH_API in .env.")
    data = _request("POST", "https://api.exa.ai/search", headers={"x-api-key": key}, json={
        "query": query, "type": "auto", "includeDomains": domains,
        "startPublishedDate": _since(now).isoformat(), "endPublishedDate": now, "numResults": 10,
        "contents": {"text": {"maxCharacters": 12000}, "highlights": True},
    })
    if not isinstance(data.get("results"), list):
        raise SearchError("Exa search returned an unsupported response.")
    return data["results"][:10]


def reddit(query, now):
    data = {"results": _exa(query, now, ["reddit.com"])}
    results = []
    for item in data["results"][:10]:
        if not isinstance(item, dict):
            continue
        if not within_window(item.get("publishedDate"), now):
            continue
        url = item.get("url", "")
        try:
            parsed = urlsplit(url)
        except ValueError:
            continue
        if parsed.scheme != "https" or parsed.hostname not in {"reddit.com", "www.reddit.com", "old.reddit.com"}:
            continue
        if not re.match(r"^/r/[^/]+/comments/[a-z0-9]+(?:/|$)", parsed.path, re.I):
            continue
        text = item.get("text") or "\n".join(x for x in item.get("highlights", []) if isinstance(x, str))
        if not isinstance(text, str) or not text.strip():
            continue
        results.append({"url": url, "title": str(item.get("title") or "Reddit discussion"),
                        "author": str(item.get("author") or ""), "published_at": str(item.get("publishedDate") or ""),
                        "text": text[:12000], "evidence_kind": "snippet", "collection_source": "exa",
                        "caveats": ["Exa indexed excerpt; original-post attribution and comment coverage may be incomplete."]})
    return results


def communities(query, now, index=0):
    domains = [domain for _, domain, _ in community_batch(index)]
    results = []
    for item in _exa(query, now, domains):
        if not isinstance(item, dict) or not within_window(item.get("publishedDate"), now):
            continue
        url = canonical_url(item.get("url"))
        if not url or urlsplit(url).hostname not in domains:
            continue
        text = item.get("text") or "\n".join(x for x in (item.get("highlights") or []) if isinstance(x, str))
        if not isinstance(text, str) or not text.strip():
            continue
        results.append({"url": url, "title": str(item.get("title") or "Community discussion"),
                        "author": str(item.get("author") or ""), "published_at": str(item.get("publishedDate") or ""),
                        "text": text[:12000], "evidence_kind": "snippet", "collection_source": "exa_community",
                        "caveats": ["Exa indexed excerpt; publication date and original-author attribution need verification. Recent activity alone does not establish a recent original post."]})
    return results


def hackernews(query, now):
    data = _request("GET", "https://hn.algolia.com/api/v1/search_by_date", params={
        "query": query.replace('"', ''), "tags": "(story,comment)", "hitsPerPage": 10,
        "numericFilters": f"created_at_i>={int(_since(now).timestamp())},created_at_i<={int(datetime.fromisoformat(now.replace('Z', '+00:00')).timestamp())}",
    })
    if not isinstance(data.get("hits"), list):
        raise SearchError("Hacker News search returned an unsupported response.")
    results = []
    for item in data["hits"][:10]:
        if not isinstance(item, dict) or not str(item.get("objectID", "")).isdigit():
            continue
        if not within_window(item.get("created_at"), now):
            continue
        title = str(item.get("title") or item.get("story_title") or "Hacker News discussion")
        text = item.get("comment_text") or item.get("story_text") or ""
        # Preserve text boundaries when removing indexed HTML.
        text = unescape(re.sub(r"<[^>]+>", " ", text))
        if not text.strip():
            continue
        results.append({"url": f"https://news.ycombinator.com/item?id={item['objectID']}",
                        "title": title, "text": text[:12000], "author": str(item.get("author") or ""),
                        "published_at": str(item.get("created_at") or ""), "evidence_kind": "full_post",
                        "collection_source": "hn_algolia", "caveats": ["Search index text; surrounding replies were not collected."]})
    return results
