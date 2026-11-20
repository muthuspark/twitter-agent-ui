import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app import codex_client as client, main, prospects
from app.storage import GrowthStore


PRODUCT = {
    "kind": "product", "need": "chasing updates", "product_fit": "Source supports reporting, subject to setup.",
    "click_reason": "Inspect whether Jovis fits the reporting workflow.", "evidence_ids": ["E1"],
}


def recommendation(tweet_id, opportunity):
    return {"tweet_id": tweet_id, "action": "comment", "confidence": 80,
            "reason": "Specific workflow need", "comment_drafts": ["A grounded reply."],
            "risk": "low", "opportunity": opportunity}


def test_traffic_objective_uses_product_evidence_and_prioritizes_product(monkeypatch):
    context = {"evidence": [{"id": "E1", "excerpt": "reporting interface"}]}
    monkeypatch.setattr(client, "comment_product_context", lambda: context)

    def run(system, payload, schema, **kwargs):
        assert "Product fit takes precedence over the expertise essay" in system
        assert "solo founder" in system
        assert payload["product_context"] == context
        assert "customer result" in system
        assert schema["properties"]["recommendations"]["items"]["properties"]["comment_drafts"]["items"]["maxLength"] == 280
        return json.dumps({"recommendations": [
            recommendation("authority", {"kind": "authority"}), recommendation("product", PRODUCT),
        ]})

    monkeypatch.setattr(client, "_run_codex", run)
    result = client.analyze_with_codex([], "Broad AI expertise")
    assert [item["tweet_id"] for item in result] == ["product", "authority"]
    assert result[0]["opportunity"] == PRODUCT


@pytest.mark.parametrize("overrides", [
    {"evidence_ids": []}, {"evidence_ids": ["invented"]},
    {"evidence_ids": ["E1", "invented"]}, {"click_reason": ""}, {"need": ""}, {"product_fit": ""},
])
def test_ungrounded_product_replies_are_skipped(monkeypatch, overrides):
    monkeypatch.setattr(client, "comment_product_context", lambda: {"evidence": [{"id": "E1"}]})
    monkeypatch.setattr(client, "_run_codex", lambda *a, **kw: json.dumps({
        "recommendations": [recommendation("1", {**PRODUCT, **overrides})],
    }))
    result = client.analyze_with_codex([], "AI")[0]
    assert result["action"] == "skip"
    assert result["comment_drafts"] == []
    assert result["comment"] == ""


def test_missing_product_source_does_not_create_product_opportunity(monkeypatch):
    def missing():
        raise client.CodexConfigurationError("Missing local source")
    monkeypatch.setattr(prospects, "source_snapshot", missing)
    assert client.comment_product_context()["evidence"] == []
    monkeypatch.setattr(client, "_run_codex", lambda *a, **kw: json.dumps({
        "recommendations": [recommendation("1", PRODUCT)],
    }))
    assert client.analyze_with_codex([], "AI")[0]["action"] == "skip"


def test_existing_database_migrates_and_product_queue_survives_reload(tmp_path):
    path = tmp_path / "growth.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("""create table recommendations (
            id integer primary key, tweet_id text, action text, confidence integer,
            reason text, comment text, risk text, created_at text default current_timestamp)""")
        connection.execute("insert into recommendations (tweet_id, action, confidence) values ('legacy', 'comment', 80)")
    store = GrowthStore(path)
    store.save_recommendations([{**recommendation("product", PRODUCT), "comment": "Product reply"}])
    store.save_recommendations([{**recommendation("authority", {"kind": "authority"}), "comment": "Authority reply"}])
    store.save_recommendations([{
        **recommendation("weaker-product", PRODUCT), "confidence": 60, "comment": "Weaker fit reply",
    }])
    rows = GrowthStore(path).pending_recommendations()
    assert rows[0]["tweet_id"] == "product"
    assert rows[0]["opportunity"] == PRODUCT
    assert rows[1]["tweet_id"] == "weaker-product"
    assert next(row for row in rows if row["tweet_id"] == "legacy")["opportunity"] == {}


def test_alternatives_endpoint_keeps_saved_opportunity(monkeypatch, tmp_path):
    store = GrowthStore(tmp_path / "growth.sqlite3")
    saved = store.save_recommendations([{
        **recommendation("1", PRODUCT), "comment": "A product introduction.",
        "tweet": {"id": "1", "text": "I keep chasing updates"},
    }])[0]
    monkeypatch.setattr(main, "get_growth_store", lambda: store)
    def alternatives(tweet, current, **kwargs):
        assert kwargs["opportunity"] == PRODUCT
        return ["First angle", "Second angle"]
    monkeypatch.setattr(main, "generate_comment_alternatives_with_codex", alternatives)
    response = TestClient(main.app).post(f"/api/growth/comment-candidates/{saved['id']}/alternatives")
    assert response.status_code == 200
    assert response.json()["alternatives"] == ["First angle", "Second angle"]


def test_alternative_prompt_receives_current_product_evidence(monkeypatch):
    monkeypatch.setattr(client, "comment_product_context", lambda: {"evidence": [{"id": "E1"}]})
    def run(system, payload, schema, **kwargs):
        assert "Do not turn an authority reply into a product pitch" in system
        assert payload["opportunity"] == PRODUCT
        assert payload["product_context"]["evidence"] == [{"id": "E1"}]
        return json.dumps({"alternatives": ["First grounded angle.", "Second grounded angle."]})
    monkeypatch.setattr(client, "_run_codex", run)
    assert len(client.generate_comment_alternatives_with_codex({}, "Current", opportunity=PRODUCT)) == 2
