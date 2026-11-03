"""The user's essay is the single source of editorial direction."""

from datetime import datetime, timezone
import hashlib
from pathlib import Path

ESSAY_PATH = Path(__file__).resolve().parents[2] / "essay.md"

COMPANY_RESEARCH_LENS = (
    "The central research question is: What does this source reveal about the future of companies "
    "as software factories run by one person or a small group of people? "
    "A software factory coordinates AI agents, tools and automated workflows to deliver products "
    "or services across business functions. Consider both solo operators and small groups. "
    "For each source, identify the specific change in company structure, productive capacity, "
    "human coordination, ownership, operating costs or responsibility, or a constraint preventing "
    "that change. Explain this mechanism in essay_connection. Generic AI relevance or faster task "
    "execution alone is insufficient without an implication for how the company operates. "
    "Include evidence that supports, tests or challenges this future; do not assume the transition "
    "is inevitable or require every source to endorse it. "
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
