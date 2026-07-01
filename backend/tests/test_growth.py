import json
import sqlite3
import subprocess

from app.deepseek_client import analyze_with_deepseek, parse_recommendations
from app.growth import (
    GrowthValidationError,
    build_growth_action_command,
    extract_tweet_candidates,
)
from app.storage import GrowthStore
from app.twitter_cli import run_growth_action


def test_extract_tweet_candidates_from_cli_envelope():
    payload = {
        "ok": True,
        "data": [
            {
                "id": "123",
                "text": "AI agents need better evals",
                "author": {"name": "Ada", "screenName": "ada"},
                "metrics": {"likes": 4, "replies": 1, "retweets": 0, "views": 500},
                "createdAtISO": "2026-07-01T00:00:00+00:00",
                "lang": "en",
            }
        ],
    }

    candidates = extract_tweet_candidates(payload, "AI agents")

    assert candidates == [
        {
            "id": "123",
            "text": "AI agents need better evals",
            "author": {"name": "Ada", "screenName": "ada"},
            "metrics": {"likes": 4, "replies": 1, "retweets": 0, "views": 500},
            "createdAtISO": "2026-07-01T00:00:00+00:00",
            "lang": "en",
            "sourceQuery": "AI agents",
        }
    ]


def test_parse_recommendations_accepts_deepseek_json_shape():
    content = json.dumps(
        {
            "recommendations": [
                {
                    "tweet_id": "123",
                    "action": "comment",
                    "confidence": 82,
                    "reason": "Relevant founder asking about AI agents.",
                    "comment": "The hard part is evals, not the agent loop.",
                    "risk": "low",
                }
            ]
        }
    )

    parsed = parse_recommendations(content)

    assert parsed[0]["tweet_id"] == "123"
    assert parsed[0]["action"] == "comment"
    assert parsed[0]["confidence"] == 82


def test_parse_recommendations_preserves_three_comment_drafts():
    content = json.dumps(
        {
            "recommendations": [
                {
                    "tweet_id": "123",
                    "action": "comment",
                    "confidence": 82,
                    "reason": "Relevant founder asking about AI agents.",
                    "comment_drafts": [
                        "Evals are the bottleneck.",
                        "I would start with failure cases.",
                        "Agent loops are easy; product judgment is harder.",
                    ],
                    "risk": "low",
                }
            ]
        }
    )

    parsed = parse_recommendations(content)

    assert parsed[0]["comment"] == "Evals are the bottleneck."
    assert parsed[0]["comment_drafts"] == [
        "Evals are the bottleneck.",
        "I would start with failure cases.",
        "Agent loops are easy; product judgment is harder.",
    ]


def test_build_growth_action_command_for_like():
    assert build_growth_action_command("like", "123", None) == ["twitter", "like", "123", "--json"]


def test_build_growth_action_command_for_comment():
    assert build_growth_action_command("comment", "123", "Useful point") == [
        "twitter",
        "reply",
        "123",
        "Useful point",
        "--json",
    ]


def test_rejects_comment_without_text():
    try:
        build_growth_action_command("comment", "123", " ")
    except GrowthValidationError as exc:
        assert str(exc) == "Comment text is required"
    else:
        raise AssertionError("Expected GrowthValidationError")


def test_run_growth_action_executes_safe_argument_list(monkeypatch):
    def fake_run(command, capture_output, text, timeout, check):
        assert command == ["twitter", "like", "123", "--json"]
        return subprocess.CompletedProcess(command, 0, json.dumps({"ok": True}), "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_growth_action("like", "123")

    assert result.command == ["twitter", "like", "123", "--json"]
    assert result.data == {"ok": True}


def test_growth_store_records_recommendations_and_actions(tmp_path):
    db_path = tmp_path / "growth.sqlite3"
    store = GrowthStore(db_path)
    store.save_recommendations(
        [
            {
                "tweet_id": "123",
                "action": "like",
                "confidence": 77,
                "reason": "Relevant low-engagement AI post.",
                "comment": "",
                "risk": "low",
            }
        ]
    )
    store.record_action(
        recommendation_id=1,
        action="like",
        tweet_id="123",
        comment_text="",
        status="approved",
        command=["twitter", "like", "123", "--json"],
        result={"ok": True},
    )

    history = store.history()

    assert history[0]["tweet_id"] == "123"
    assert history[0]["status"] == "approved"
    assert history[0]["command"] == ["twitter", "like", "123", "--json"]

    with sqlite3.connect(db_path) as connection:
        count = connection.execute("select count(*) from recommendations").fetchone()[0]
    assert count == 1


def test_growth_store_records_action_metadata_for_memory(tmp_path):
    store = GrowthStore(tmp_path / "growth.sqlite3")
    store.record_action(
        recommendation_id=1,
        action="comment",
        tweet_id="123",
        comment_text="Evals are the bottleneck, not the agent loop.",
        status="approved",
        command=["twitter", "reply", "123", "Evals are the bottleneck, not the agent loop.", "--json"],
        result={"ok": True},
        metadata={
            "source_tweet": {
                "text": "How should founders think about AI agents?",
                "author": {"screenName": "founder"},
            },
            "recommendation_reason": "Technical founder question in your niche.",
            "comment_drafts": [
                "Evals are the bottleneck, not the agent loop.",
                "Start with failure cases.",
                "The product judgment matters more than orchestration.",
            ],
        },
    )

    history = store.history()

    assert history[0]["metadata"]["source_tweet"]["text"] == "How should founders think about AI agents?"
    assert history[0]["metadata"]["recommendation_reason"] == "Technical founder question in your niche."
    assert history[0]["metadata"]["comment_drafts"][1] == "Start with failure cases."


def test_growth_store_returns_only_approved_commented_tweet_ids(tmp_path):
    store = GrowthStore(tmp_path / "growth.sqlite3")
    store.record_action(
        recommendation_id=1,
        action="comment",
        tweet_id="commented",
        comment_text="Useful point",
        status="approved",
        command=["twitter", "reply", "commented", "Useful point", "--json"],
        result={"ok": True},
    )
    store.record_action(
        recommendation_id=2,
        action="like",
        tweet_id="liked",
        comment_text="",
        status="approved",
        command=["twitter", "like", "liked", "--json"],
        result={"ok": True},
    )
    store.record_action(
        recommendation_id=3,
        action="comment",
        tweet_id="rejected",
        comment_text="Rejected draft",
        status="rejected",
        command=[],
        result={"ok": True},
    )

    assert store.approved_commented_tweet_ids() == {"commented"}


def test_growth_store_builds_preference_memory_from_recent_decisions(tmp_path):
    store = GrowthStore(tmp_path / "growth.sqlite3")
    store.record_action(
        recommendation_id=1,
        action="comment",
        tweet_id="approved-comment",
        comment_text="Evals are the bottleneck, not orchestration.",
        status="approved",
        command=["twitter", "reply", "approved-comment", "Evals are the bottleneck, not orchestration.", "--json"],
        result={"ok": True},
        metadata={
            "source_tweet": {"text": "AI agents are easy now", "author": {"screenName": "builder"}},
            "recommendation_reason": "Good technical discussion.",
            "comment_drafts": ["Evals are the bottleneck, not orchestration."],
        },
    )
    store.record_action(
        recommendation_id=2,
        action="comment",
        tweet_id="rejected-comment",
        comment_text="Generic hype reply",
        status="rejected",
        command=[],
        result={"ok": True},
        metadata={
            "source_tweet": {"text": "AI will change everything", "author": {"screenName": "hype"}},
            "recommendation_reason": "Too broad.",
            "comment_drafts": ["Generic hype reply"],
        },
    )
    store.record_action(
        recommendation_id=3,
        action="skip",
        tweet_id="approved-skip",
        comment_text="",
        status="approved",
        command=[],
        result={"ok": True, "skipped": True},
        metadata={
            "source_tweet": {"text": "Motivation thread for founders", "author": {"screenName": "coach"}},
            "recommendation_reason": "Low technical relevance.",
            "comment_drafts": [],
        },
    )

    memory = store.preference_memory()

    assert "technical" in memory["summary"].lower()
    assert memory["approved_comment_examples"][0]["comment_text"] == "Evals are the bottleneck, not orchestration."
    assert memory["rejected_examples"][0]["source_tweet"]["text"] == "AI will change everything"
    assert memory["skip_examples"][0]["source_tweet"]["author"]["screenName"] == "coach"


def test_deepseek_request_includes_preference_memory():
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"recommendations":[{"tweet_id":"123","action":"skip","confidence":60,"reason":"Already covered","comment_drafts":[],"risk":"low"}]}'
                        }
                    }
                ]
            }

    def fake_post(url, headers, json, timeout):
        captured["payload"] = json
        return FakeResponse()

    analyze_with_deepseek(
        [{"id": "123", "text": "AI agents are easy"}],
        "AI and software engineering",
        api_key="test-key",
        post=fake_post,
        preference_memory={"summary": "User prefers technical replies about evals."},
    )

    user_content = captured["payload"]["messages"][1]["content"]
    assert "User prefers technical replies about evals" in user_content
