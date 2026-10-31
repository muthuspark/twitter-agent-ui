from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Callable

from app.storage import GrowthStore
from app.twitter_cli import (
    CliExecutionError, CliNotFoundError, CliTimeoutError, InvalidCliOutputError,
)


WINDOW_HOURS = 48
SOURCE_LIMIT = 40
CLI_ERRORS = (CliExecutionError, CliNotFoundError, CliTimeoutError, InvalidCliOutputError)


def parse_post_date(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
    # A timezone-free publication date cannot establish a reliable 48-hour window.
    return date.astimezone(timezone.utc) if date.tzinfo else None


def collect_interest_context(
    store: GrowthStore,
    fetch_likes: Callable[..., list[dict[str, Any]]],
    fetch_bookmarks: Callable[..., list[dict[str, Any]]],
    *, now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    since = now - timedelta(hours=WINDOW_HOURS)
    sources = {}
    warnings = []
    used_publication_dates = False
    undated_count = 0
    for action, label, fetch in (
        ("like", "likes", fetch_likes), ("bookmark", "bookmarks", fetch_bookmarks),
    ):
        posts = {post["id"]: post for post in store.recent_interest_posts(action, since, now)}
        try:
            imported = fetch(limit=100)
        except CLI_ERRORS:
            imported = []
            warnings.append(f"Could not load {label} from X; using available activity recorded in this app.")
        for post in imported:
            post_id = str(post.get("id") or "")
            if not post_id or not post.get("text") or post_id in posts:
                continue
            date = parse_post_date(post.get("createdAtISO"))
            if date is None:
                undated_count += 1
                continue
            if since <= date <= now:
                posts[post_id] = {
                    "id": post_id, "text": str(post["text"])[:4000],
                    "timestamp": date.isoformat(), "timestamp_basis": "post_publication_time",
                }
        selected = list(posts.values())[:SOURCE_LIMIT]
        used_publication_dates |= any(post["timestamp_basis"] == "post_publication_time" for post in selected)
        sources[label] = selected
    if used_publication_dates:
        warnings.append(
            "X imports use posts published in the last 48 hours because the CLI does not expose "
            "when you liked or bookmarked them. Activity recorded in this app uses the actual action time."
        )
    if undated_count:
        warnings.append("Imported posts without a reliable publication date were excluded.")
    return {
        **sources, "since": since.isoformat(), "until": now.isoformat(),
        "warning": " ".join(warnings) or None,
    }
