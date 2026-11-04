from collections import Counter
import json

import pytest

from app import prospect_search, prospects
from app.prospect_sources import COMMUNITIES, canonical_url, community_batch, directory

NOW = "2026-11-04T00:00:00+00:00"
THREADS = [
    "/post/lost-business-context-123", "/threads/lost-context.123/", "/community/threads/lost-context.123/",
    "/p/general/lost-context", "/questions/123/lost-context", "/questions/123/lost-context",
    "/forums/discussion/123/lost-context", "/t/lost-context/123", "/t/lost-context/123",
    "/feature-requests/p/lost-context", "/other-questions-13/lost-context-123", "/how-do-i-3/lost-context-123",
    "/t/lost-context/123", "/t/lost-context/123", "/t/lost-context/123",
    "/t5/CRM/lost-context/td-p/123", "/portal/en/community/topic/lost-context", "/t/lost-context/123",
    "/forums/thread/details/?threadid=12345678-1234-1234-1234-123456789abc",
    "/discussions/teams/lost-context/123",
]


def test_twenty_distinct_communities_are_covered_evenly():
    assert len(COMMUNITIES) == len({domain for _, domain, _ in COMMUNITIES}) == 20
    counts = Counter(domain for index in range(20) for _, domain, _ in community_batch(index))
    assert len(counts) == 20 and set(counts.values()) == {5}
    assert len(directory()) == 20


@pytest.mark.parametrize("community,path", list(zip(COMMUNITIES, THREADS)))
def test_only_discussion_pages_accepted(community, path):
    _, domain, _ = community
    url = f"https://{domain}{path}"
    assert canonical_url(url)
    assert prospects.post_url(url) == canonical_url(url)
    assert canonical_url(url + "#comment-1") == canonical_url(url)
    assert canonical_url(f"https://{domain}") == ""
    assert canonical_url(f"https://{domain}/users/founder") == ""
    assert canonical_url(f"https://{domain}.evil.test{path}") == ""
    assert canonical_url(f"https://secret@{domain}{path}") == ""
    assert canonical_url(f"http://{domain}{path}") == ""


def test_powerplatform_keeps_only_thread_identity():
    base = "https://community.powerplatform.com/forums/thread/details/"
    identity = "12345678-1234-1234-1234-123456789abc"
    assert canonical_url(base + "?action=reply&threadid=" + identity) == base.rstrip("/") + "?threadid=" + identity
    assert not canonical_url(base + "?action=reply")
    assert not canonical_url("https://www.linkedin.com/posts/test-123")


def test_community_search_is_scoped_recent_and_rejects_non_threads(monkeypatch):
    calls = []
    valid = "https://www.indiehackers.com/post/lost-context-123"
    def search(query, now, domains):
        calls.append(domains)
        return [{"url": url, "publishedDate": date, "text": "We lose team decisions.", "title": "Lost context"}
                for url, date in [
                    (valid, "2026-11-03T00:00:00Z"),
                    ("https://www.indiehackers.com/", "2026-11-03T00:00:00Z"),
                    ("https://www.indiehackers.com/post/old-123", "2026-11-01T00:00:00Z"),
                    ("https://community.n8n.io/t/outside-selected-group/123", "2026-11-03T00:00:00Z"),
                    ("https://www.linkedin.com/posts/123", "2026-11-03T00:00:00Z"),
                ]]
    monkeypatch.setattr(prospect_search, "_exa", search)
    results = prospect_search.communities("decisions", NOW, 0)
    assert calls == [[domain for _, domain, _ in community_batch(0)]]
    assert len(results) == 1 and results[0]["url"] == valid
    assert results[0]["collection_source"] == "exa_community" and results[0]["evidence_kind"] == "snippet"


def test_community_excerpt_enters_existing_quote_and_fit_pipeline(monkeypatch):
    url = "https://community.n8n.io/t/lost-context/123"
    monkeypatch.setattr(prospect_search, "communities", lambda *args: [{
        "url": url, "title": "Lost decisions", "text": "We lose team decisions.", "author": "founder",
        "published_at": "2026-11-03T00:00:00Z", "evidence_kind": "snippet", "collection_source": "exa_community", "caveats": [],
    }])
    monkeypatch.setattr(prospects, "_run_codex", lambda *args, **kwargs: json.dumps({"posts": [{
        "id": "0", "quote": "We lose team decisions.", "context": "Manual follow-up", "lead_type": "buyer",
        "personal_pain": True, "buyer_role_evidence": "", "explicit_solution_request": False, "caveats": [],
    }]}))
    posts, coverage, _ = prospects.collect_public_query("communities", "decisions", set(), NOW, 2)
    assert len(posts) == 1 and posts[0]["url"] == url and posts[0]["personal_pain"]
    assert coverage["provider"] == "exa" and coverage["status"] == "searched"
    assert coverage["domains"] == [domain for _, domain, _ in community_batch(2)]
