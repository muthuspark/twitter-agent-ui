"""The user's essay is the single source of editorial direction."""

from datetime import datetime, timezone
import hashlib
from pathlib import Path

ESSAY_PATH = Path(__file__).resolve().parents[2] / "essay.md"

PROFILE_FOCUS = "AI agents and enterprise AI adoption leadership"

COMPANY_RESEARCH_LENS = (
    "The central research question is: How can enterprises build dependable AI agents and lead "
    "their adoption to deliver measurable business outcomes? "
    "Focus on agent architecture, tools, orchestration, evaluation, reliability, security, "
    "governance, workflow integration, human oversight, change management and adoption leadership. "
    "For each source, identify a concrete technical mechanism, deployment constraint, leadership "
    "decision or business outcome relevant to AI agents or enterprise AI adoption. Explain this "
    "connection in essay_connection. Generic AI relevance or popularity alone is insufficient. "
    "Include evidence that supports, tests or challenges an approach; do not assume agents are "
    "always appropriate or that adoption guarantees productivity or return on investment. "
)


class EditorialContextError(Exception):
    pass


def load_editorial_context():
    try:
        content = ESSAY_PATH.read_text(encoding="utf-8").strip()
        modified = ESSAY_PATH.stat().st_mtime
    except (OSError, UnicodeError) as exc:
        raise EditorialContextError(
            "essay.md could not be read. Restore it before generating ideas."
        ) from exc
    if len(content) < 100 or len(content) > 80_000:
        raise EditorialContextError(
            "essay.md must contain a complete essay of 100 to 80,000 characters."
        )
    version = hashlib.sha256(content.encode()).hexdigest()
    return {
        "title": content.splitlines()[0].lstrip("# ").strip(),
        "content": content,
        "version": version,
        "file": "essay.md",
        "updated_at": datetime.fromtimestamp(modified, timezone.utc).isoformat(),
    }


def essay_source(context):
    return {
        "id": f"essay:{context['version']}",
        "title": context["title"],
        "url": "/api/posts/essay",
        "source": "Your essay",
        "published_at": context["updated_at"],
        "date_basis": "File updated",
        "summary": context["content"],
        "metrics": {},
        "evidence": "essay",
        "traction": "Editorial foundation, not external evidence",
    }
