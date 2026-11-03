import json

from fastapi.testclient import TestClient
import pytest

from app import editorial, codex_client, main


@pytest.fixture
def essay(monkeypatch, tmp_path):
    path = tmp_path / "essay.md"
    path.write_text(
        "How AI Could Enable One Person Companies\n\nAI could help one person run a larger business. Customer trust, reliable operations, ownership and platform dependence still matter. This is a possibility, not an inevitable outcome."
    )
    monkeypatch.setattr(editorial, "ESSAY_PATH", path)
    monkeypatch.setattr(
        main, "get_growth_store", lambda: main.GrowthStore(tmp_path / "growth.sqlite3")
    )
    return path


def test_essay_is_reread_and_version_changes_after_edit(essay):
    original = editorial.load_editorial_context()
    essay.write_text(
        essay.read_text() + "\nDistribution can remain the main bottleneck."
    )
    updated = editorial.load_editorial_context()
    assert original["version"] != updated["version"]
    assert "Distribution" in updated["content"]
    assert updated["title"] == "How AI Could Enable One Person Companies"


@pytest.mark.parametrize("content", [None, "", "A title only"])
def test_missing_or_incomplete_essay_stops_generation(monkeypatch, essay, content):
    if content is None:
        essay.unlink()
    else:
        essay.write_text(content)

    def unexpected(*a, **k):
        pytest.fail("Must not generate without the editorial foundation")

    monkeypatch.setattr(main, "generate_post_ideas", unexpected)
    response = TestClient(main.app).post(
        "/api/posts/ideas", json={"source_mode": "essay"}
    )
    assert response.status_code == 503
    assert "essay.md" in response.json()["detail"]


def test_research_selection_keeps_counterevidence_and_rejects_unknown_ids(
    monkeypatch, essay
):
    sources = [
        {"id": "operations", "title": "AI support needs human escalation"},
        {"id": "generic", "title": "A new model"},
    ]

    def run(system, payload, schema, **kwargs):
        assert payload["editorial_context"]["content"] == essay.read_text()
        assert "do not manufacture confirmation" in system
        return json.dumps(
            {
                "selected_sources": [
                    {
                        "source_id": "operations",
                        "essay_connection": "Tests reliability as a limit on solo business operations.",
                        "evidence_type": "challenges",
                    },
                    {
                        "source_id": "invented",
                        "essay_connection": "This was never supplied as a real research source.",
                        "evidence_type": "supports",
                    },
                    {
                        "source_id": "generic",
                        "essay_connection": "AI is relevant",
                        "evidence_type": "enables",
                    },
                ]
            }
        )

    monkeypatch.setattr(codex_client, "_run_codex", run)
    selected = codex_client.curate_research_for_essay(
        sources, editorial.load_editorial_context()
    )
    assert len(selected) == 1
    assert selected[0]["id"] == "operations"
    assert selected[0]["evidence_type"] == "challenges"


@pytest.mark.parametrize("mode", ["essay", "trends"])
def test_all_drafts_have_essay_connections_and_only_curated_research(
    monkeypatch, essay, mode
):
    sources = [
        {
            "id": "ops",
            "title": "Reliable support automation",
            "url": "https://example.com/support",
        },
        {"id": "offtopic", "title": "A new GPU"},
    ]
    monkeypatch.setattr(
        main,
        "fetch_trending_research",
        lambda **kwargs: {
            "sources": sources,
            "since": "2026-10-24",
            "researched_at": "2026-10-31",
            "warning": None,
        },
    )

    def run(system, payload, schema, **kwargs):
        assert "sole editorial foundation" in system
        if "selected_sources" in schema["properties"]:
            return json.dumps(
                {
                    "selected_sources": [
                        {
                            "source_id": "ops",
                            "essay_connection": "Tests reliability constraints on one-person business operations.",
                            "evidence_type": "tests",
                        }
                    ]
                }
            )
        assert payload["editorial_context"]["content"] == essay.read_text()
        assert payload["idea_type"] == "project"
        assert all(source["id"] != "offtopic" for source in payload["research_sources"])
        return json.dumps(
            {
                "ideas": [
                    {
                        "title": "A support escalation test",
                        "post_text": "Test whether a solo operator can resolve customer requests with AI. Track cases that still need human review.",
                        "essay_connection": "Tests customer support as a constraint on one-person businesses.",
                        "idea_type": "project",
                        "source_ids": [payload["research_sources"][0]["id"]],
                    }
                ]
            }
        )

    monkeypatch.setattr(codex_client, "_run_codex", run)
    response = TestClient(main.app).post(
        "/api/posts/ideas",
        json={
            "source_mode": mode,
            "idea_type": "project",
            "themes": "An unrelated topic cannot override the essay",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert (
        body["ideas"][0]["essay_version"]
        == editorial.load_editorial_context()["version"]
    )
    assert body["ideas"][0]["idea_type"] == "project"
    assert body["ideas"][0]["sources"][0]["evidence"] == "essay"
    assert [source["id"] for source in body["research_sources"]] == (
        ["ops"] if mode == "trends" else []
    )


def test_no_matching_research_uses_essay_without_inventing_news(monkeypatch, essay):
    monkeypatch.setattr(
        main,
        "fetch_trending_research",
        lambda **kwargs: {
            "sources": [],
            "since": "2026-10-24",
            "researched_at": "2026-10-31",
            "warning": None,
        },
    )

    def run(system, payload, schema, **kwargs):
        if "selected_sources" in schema["properties"]:
            return '{"selected_sources":[]}'
        assert "Do not invent recent news" in payload["instruction"]
        return json.dumps(
            {
                "ideas": [
                    {
                        "post_text": "An essay insight.",
                        "essay_connection": "Examines the cost of operating a business alone.",
                        "source_ids": [payload["research_sources"][0]["id"]],
                    }
                ]
            }
        )

    monkeypatch.setattr(codex_client, "_run_codex", run)
    response = TestClient(main.app).post(
        "/api/posts/ideas", json={"source_mode": "trends"}
    )
    assert response.status_code == 200
    assert "essay only" in response.json()["context_warning"]
    assert response.json()["research_sources"] == []


def test_drafts_without_essay_connection_are_rejected(monkeypatch, essay):
    monkeypatch.setattr(
        main,
        "generate_post_ideas",
        lambda *a, **k: [
            {
                "post_text": "Unrelated news",
                "source_ids": [k["research_sources"][0]["id"]],
            }
        ],
    )
    assert (
        TestClient(main.app)
        .post("/api/posts/ideas", json={"source_mode": "essay"})
        .status_code
        == 502
    )


def test_read_essay_endpoint_and_direction_match_file(essay):
    client = TestClient(main.app)
    direction = client.get("/api/posts/editorial-direction").json()["direction"]
    assert direction["content"] == essay.read_text()
    assert client.get("/api/posts/essay").text == essay.read_text()


def test_changed_essay_blocks_stale_draft_approval(monkeypatch, essay):
    old_version = editorial.load_editorial_context()['version']
    essay.write_text(essay.read_text() + '\nA new argument about ownership.')
    def unexpected(*a, **k):
        pytest.fail('A stale essay draft must not be published')
    monkeypatch.setattr(main, 'run_post_action', unexpected)
    response = TestClient(main.app).post('/api/posts/approve', json={
        'post_text': 'An older draft.', 'metadata': {'post_idea': {'essay_version': old_version}},
    })
    assert response.status_code == 422
    assert 'changed' in response.json()['detail']
