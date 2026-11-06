import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


class GrowthStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_db(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                create table if not exists recommendations (
                    id integer primary key autoincrement,
                    tweet_id text not null,
                    action text not null,
                    confidence integer not null,
                    reason text not null,
                    comment text not null,
                    risk text not null,
                    created_at text not null default current_timestamp
                )
                """
            )
            connection.execute(
                """
                create table if not exists actions (
                    id integer primary key autoincrement,
                    recommendation_id integer,
                    action text not null,
                    tweet_id text not null,
                    comment_text text not null,
                    status text not null,
                    command_json text not null,
                    result_json text not null,
                    created_at text not null default current_timestamp
                )
                """
            )
            self._ensure_column(connection, "actions", "metadata_json", "text not null default '{}'")
            self._ensure_column(connection, "recommendations", "candidate_json", "text not null default '{}'")
            self._ensure_column(connection, "recommendations", "comment_drafts_json", "text not null default '[]'")

    def _ensure_column(
        self,
        connection: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {
            row["name"]
            for row in connection.execute(f"pragma table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(f"alter table {table} add column {column} {definition}")

    def save_recommendations(self, recommendations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        saved: list[dict[str, Any]] = []
        with self._connect() as connection:
            pending = {
                str(row["tweet_id"])
                for row in connection.execute(
                    """select r.tweet_id from recommendations r
                    where not exists (select 1 from actions a where a.recommendation_id = r.id)"""
                ).fetchall()
            }
            for recommendation in recommendations:
                tweet_id = str(recommendation["tweet_id"])
                if tweet_id in pending:
                    continue
                cursor = connection.execute(
                    """
                    insert into recommendations
                        (tweet_id, action, confidence, reason, comment, risk, candidate_json, comment_drafts_json)
                    values (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tweet_id,
                        recommendation["action"],
                        int(recommendation["confidence"]),
                        recommendation.get("reason", ""),
                        recommendation.get("comment", ""),
                        recommendation.get("risk", "medium"),
                        json.dumps(recommendation.get("tweet") or {}),
                        json.dumps(recommendation.get("comment_drafts") or []),
                    ),
                )
                saved_item = dict(recommendation)
                saved_item["id"] = cursor.lastrowid
                saved.append(saved_item)
                pending.add(tweet_id)
        return saved

    def pending_recommendations(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """select r.id, r.tweet_id, r.action, r.confidence, r.reason, r.comment, r.risk,
                          r.candidate_json, r.comment_drafts_json, r.created_at
                   from recommendations r
                   where r.action = 'comment'
                     and not exists (select 1 from actions a where a.recommendation_id = r.id)
                   order by r.id desc limit ?""",
                (limit,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "tweet_id": row["tweet_id"],
                "action": row["action"],
                "confidence": row["confidence"],
                "reason": row["reason"],
                "comment": row["comment"],
                "risk": row["risk"],
                "tweet": json.loads(row["candidate_json"]),
                "comment_drafts": json.loads(row["comment_drafts_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def record_action(
        self,
        *,
        recommendation_id: int | None,
        action: str,
        tweet_id: str,
        comment_text: str,
        status: str,
        command: list[str],
        result: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        metadata = metadata or {}
        with self._connect() as connection:
            cursor = connection.execute(
                """
                insert into actions
                    (recommendation_id, action, tweet_id, comment_text, status,
                     command_json, result_json, metadata_json)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    recommendation_id,
                    action,
                    tweet_id,
                    comment_text,
                    status,
                    json.dumps(command),
                    json.dumps(result),
                    json.dumps(metadata),
                ),
            )
        return {
            "id": cursor.lastrowid,
            "recommendation_id": recommendation_id,
            "action": action,
            "tweet_id": tweet_id,
            "comment_text": comment_text,
            "status": status,
            "command": command,
            "result": result,
            "metadata": metadata,
        }

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                select id, recommendation_id, action, tweet_id, comment_text, status,
                       command_json, result_json, metadata_json, created_at
                from actions
                order by id desc
                limit ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "recommendation_id": row["recommendation_id"],
                "action": row["action"],
                "tweet_id": row["tweet_id"],
                "comment_text": row["comment_text"],
                "status": row["status"],
                "command": json.loads(row["command_json"]),
                "result": json.loads(row["result_json"]),
                "metadata": json.loads(row["metadata_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def approved_commented_tweet_ids(self) -> set[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                select distinct tweet_id
                from actions
                where action = 'comment' and status = 'approved'
                """
            ).fetchall()
        return {str(row["tweet_id"]) for row in rows}

    def handled_recommendation_tweet_ids(self) -> set[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """select distinct tweet_id from actions
                   where recommendation_id is not null"""
            ).fetchall()
        return {str(row["tweet_id"]) for row in rows}

    def recent_liked_posts(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                select tweet_id, metadata_json from actions
                where action = 'like' and status = 'approved'
                order by id desc
                """
            ).fetchall()
        posts: dict[str, dict[str, Any]] = {}
        for row in rows:
            source = json.loads(row["metadata_json"]).get("source_tweet") or {}
            if source.get("text") and row["tweet_id"] not in posts:
                posts[row["tweet_id"]] = {"id": row["tweet_id"], "text": source["text"][:4000]}
            if len(posts) >= limit:
                break
        return list(posts.values())

    def recent_interest_posts(
        self, action: str, since: datetime, until: datetime, limit: int = 100,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                select tweet_id, metadata_json, created_at from actions
                where action = ? and status = 'approved'
                  and datetime(created_at) >= datetime(?)
                  and datetime(created_at) <= datetime(?)
                order by created_at desc, id desc
                """,
                (action, since.isoformat(), until.isoformat()),
            ).fetchall()
        posts = {}
        for row in rows:
            source = json.loads(row["metadata_json"]).get("source_tweet") or {}
            if source.get("text") and row["tweet_id"] not in posts:
                posts[row["tweet_id"]] = {
                    "id": row["tweet_id"], "text": str(source["text"])[:4000],
                    "timestamp": row["created_at"], "timestamp_basis": "action_time",
                }
            if len(posts) >= limit:
                break
        return list(posts.values())

    def preference_memory(self, limit: int = 30) -> dict[str, Any]:
        records = list(reversed(self.history(limit=limit)))
        approved_comments = [
            self._memory_example(record)
            for record in records
            if record["action"] == "comment" and record["status"] == "approved"
        ][-5:]
        rejected = [
            self._memory_example(record)
            for record in records
            if record["status"] == "rejected"
        ][-5:]
        skipped = [
            self._memory_example(record)
            for record in records
            if record["action"] == "skip" and record["status"] == "approved"
        ][-5:]

        summary_parts: list[str] = []
        if approved_comments:
            comments = "; ".join(example["comment_text"] for example in approved_comments if example["comment_text"])
            summary_parts.append(
                "Approved comment style favors specific, technical, useful replies"
                + (f": {comments}" if comments else ".")
            )
        if rejected:
            reasons = "; ".join(
                example["recommendation_reason"]
                for example in rejected
                if example["recommendation_reason"]
            )
            summary_parts.append(
                "Rejected recommendations often involve weak fit, generic drafts, or low-value engagement"
                + (f": {reasons}" if reasons else ".")
            )
        if skipped:
            skipped_text = "; ".join(
                example["source_tweet"].get("text", "")
                for example in skipped
                if example["source_tweet"].get("text")
            )
            summary_parts.append(
                "Approved skips indicate topics to avoid"
                + (f": {skipped_text}" if skipped_text else ".")
            )

        return {
            "summary": " ".join(summary_parts) if summary_parts else "No preference memory recorded yet.",
            "approved_comment_examples": approved_comments,
            "rejected_examples": rejected,
            "skip_examples": skipped,
        }

    def _memory_example(self, record: dict[str, Any]) -> dict[str, Any]:
        metadata = record.get("metadata") or {}
        return {
            "action": record["action"],
            "status": record["status"],
            "tweet_id": record["tweet_id"],
            "comment_text": record["comment_text"],
            "source_tweet": metadata.get("source_tweet") or {},
            "recommendation_reason": metadata.get("recommendation_reason") or "",
            "comment_drafts": metadata.get("comment_drafts") or [],
            "created_at": record["created_at"],
        }
