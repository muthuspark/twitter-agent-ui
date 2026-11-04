"""Allowlisted public communities and individual discussion URL formats."""
import re
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

# Name, public hostname, individual discussion path (not homepages, categories or profiles).
COMMUNITIES = (
    ("Indie Hackers", "www.indiehackers.com", r"/post/[^/]+"),
    ("UK Business Forums", "www.ukbusinessforums.co.uk", r"/threads/[^/]+"),
    ("The Fastlane Forum", "www.thefastlaneforum.com", r"/community/threads/[^/]+"),
    ("Product Hunt Forums", "www.producthunt.com", r"/p/[^/]+/[^/]+"),
    ("The Workplace Stack Exchange", "workplace.stackexchange.com", r"/(?:questions|q)/\d+(?:/[^/]+)?"),
    ("Project Management Stack Exchange", "pm.stackexchange.com", r"/(?:questions|q)/\d+(?:/[^/]+)?"),
    ("Atlassian Community", "community.atlassian.com", r"/forums/(?:discussion/\d+/[^/]+|.+/(?:qaq-p|td-p)/\d+)"),
    ("Asana Community", "forum.asana.com", r"/t/[^/]+/\d+(?:/\d+)?"),
    ("monday.com Community", "community.monday.com", r"/t/[^/]+/\d+(?:/\d+)?"),
    ("ClickUp Feedback", "feedback.clickup.com", r"/[^/]+/p/[^/]+"),
    ("Airtable Community", "community.airtable.com", r"/[^/]+-\d+/[^/]+-\d+"),
    ("Zapier Community", "community.zapier.com", r"/[^/]+-\d+/[^/]+-\d+"),
    ("Make Community", "community.make.com", r"/t/[^/]+/\d+(?:/\d+)?"),
    ("n8n Community", "community.n8n.io", r"/t/[^/]+/\d+(?:/\d+)?"),
    ("Superhuman / Coda Community", "connect.superhuman.com", r"/t/[^/]+/\d+(?:/\d+)?"),
    ("HubSpot Community", "community.hubspot.com", r"/t5/.+/(?:td-p|idi-p)/\d+"),
    ("Zoho Community", "help.zoho.com", r"/portal/en/community/topic/[^/]+"),
    ("UiPath Community", "forum.uipath.com", r"/t/[^/]+/\d+(?:/\d+)?"),
    ("Microsoft Power Platform Community", "community.powerplatform.com", r"/forums/thread/details"),
    ("Microsoft Tech Community", "techcommunity.microsoft.com", r"/discussions/[^/]+/[^/]+/\d+"),
)


def community_batch(index):
    """Rotate five communities per query; each receives five of the 20 problem queries."""
    start = (index % 4) * 5
    return COMMUNITIES[start:start + 5]


def directory():
    return [{"name": name, "url": f"https://{domain}"} for name, domain, _ in COMMUNITIES]


def canonical_url(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
            return ""
        host = (parsed.hostname or "").lower()
        path = parsed.path.rstrip("/")
        for _, domain, pattern in COMMUNITIES:
            if host.removeprefix("www.") != domain.removeprefix("www.") or not re.fullmatch(pattern, path, re.I):
                continue
            query = ""
            if domain == "community.powerplatform.com":
                thread = parse_qs(parsed.query).get("threadid", [""])[0]
                if not re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", thread, re.I):
                    return ""
                query = urlencode({"threadid": thread.lower()})
            return urlunsplit(("https", domain, path, query, ""))
    except (ValueError, TypeError):
        pass
    return ""
