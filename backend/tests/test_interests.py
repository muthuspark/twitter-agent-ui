from datetime import datetime, timedelta, timezone

import pytest

from app.interests import collect_interest_context, parse_post_date
from app.storage import GrowthStore
from app.twitter_cli import CliExecutionError


NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)


def post(post_id, date):
    return {"id": post_id, "text": "A useful reference", "createdAtISO": date}


def test_filters_imports_at_48_hour_boundary_and_deduplicates(tmp_path):
    store = GrowthStore(tmp_path / "growth.sqlite3")
    imported = [
        post("boundary", (NOW - timedelta(hours=48)).isoformat()),
        post("recent", (NOW - timedelta(hours=1)).isoformat()),
        post("recent", (NOW - timedelta(hours=1)).isoformat()),
        post("old", (NOW - timedelta(hours=48, seconds=1)).isoformat()),
        post("future", (NOW + timedelta(seconds=1)).isoformat()),
        post("unknown", "bad date"),
        post("naive", "2026-10-31T10:00:00"),
    ]
    context = collect_interest_context(
        store, lambda **kw: imported, lambda **kw: [imported[1]], now=NOW,
    )
    assert [item["id"] for item in context["likes"]] == ["boundary", "recent"]
    assert [item["id"] for item in context["bookmarks"]] == ["recent"]
    assert context["likes"][0]["timestamp_basis"] == "post_publication_time"
    assert "publication" in context["warning"]
    assert "without a reliable" in context["warning"]


def test_uses_action_time_for_old_posts_saved_recently_and_excludes_stale_actions(tmp_path):
    store = GrowthStore(tmp_path / "growth.sqlite3")
    for action, status, post_id, hours in [
        ("like", "approved", "liked", 47),
        ("bookmark", "approved", "saved", 1),
        ("like", "approved", "stale", 49),
        ("bookmark", "rejected", "rejected", 1),
        ("like", "approved", "future", -1),
    ]:
        record = store.record_action(
            recommendation_id=None, action=action, tweet_id=post_id,
            comment_text="", status=status, command=[], result={},
            metadata={"source_tweet": {"text": "An old post I saved today", "createdAtISO": "2020-01-01T00:00:00Z"}},
        )
        with store._connect() as connection:
            connection.execute("update actions set created_at = ? where id = ?", ((NOW - timedelta(hours=hours)).isoformat(), record["id"]))

    def unavailable(**kwargs):
        raise CliExecutionError("Unavailable")

    context = collect_interest_context(store, unavailable, unavailable, now=NOW)
    assert [item["id"] for item in context["likes"]] == ["liked"]
    assert [item["id"] for item in context["bookmarks"]] == ["saved"]
    assert context["bookmarks"][0]["timestamp_basis"] == "action_time"
    assert "Could not load likes" in context["warning"]
    assert "Could not load bookmarks" in context["warning"]


def test_one_failed_source_does_not_discard_other_source(tmp_path):
    def unavailable(**kwargs):
        raise CliExecutionError("Unavailable")

    context = collect_interest_context(
        GrowthStore(tmp_path / "growth.sqlite3"), unavailable,
        lambda **kw: [post("saved", NOW.isoformat())], now=NOW,
    )
    assert not context["likes"]
    assert context["bookmarks"][0]["id"] == "saved"


@pytest.mark.parametrize("value", [None, "", "not-a-date", "2026-10-31T10:00:00"])
def test_rejects_unreliable_dates(value):
    assert parse_post_date(value) is None


def test_parses_offsets_and_twitter_dates():
    assert parse_post_date("2026-10-31T17:30:00+05:30") == NOW
    assert parse_post_date("Sat Oct 31 12:00:00 +0000 2026") == NOW
