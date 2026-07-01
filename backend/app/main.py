import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import load_environment
from app.models import Preset, PresetField, RunRequest, RunResponse
from app.deepseek_client import DeepSeekConfigurationError, DeepSeekError, analyze_with_deepseek
from app.growth import GrowthValidationError, extract_tweet_candidates
from app.storage import GrowthStore
from app.twitter_cli import (
    PRESETS,
    CliExecutionError,
    CliNotFoundError,
    CliTimeoutError,
    InvalidCliOutputError,
    ValidationError,
    run_growth_action,
    run_twitter_command,
)

load_environment()

app = FastAPI(title="Twitter CLI Workbench API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_growth_store() -> GrowthStore:
    default_path = Path(__file__).resolve().parents[1] / "growth.sqlite3"
    return GrowthStore(os.environ.get("GROWTH_DB_PATH", default_path))


def analyze_candidates(
    candidates: list[dict[str, Any]],
    profile_focus: str,
    preference_memory: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return analyze_with_deepseek(
        candidates,
        profile_focus,
        preference_memory=preference_memory,
    )


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/presets")
def presets() -> dict[str, list[Preset]]:
    result: list[Preset] = []
    for preset in PRESETS.values():
        fields: list[PresetField] = []
        if preset.requires_query:
            fields.append(
                PresetField(
                    name="query",
                    label="Query",
                    type="text",
                    required=True,
                )
            )
        if preset.supports_max:
            fields.append(
                PresetField(
                    name="max",
                    label="Max results",
                    type="number",
                    required=False,
                    default=20,
                    min=1,
                    max=100,
                )
            )
        result.append(
            Preset(
                id=preset.id,
                label=preset.label,
                description=preset.description,
                fields=fields,
            )
        )
    return {"presets": result}


@app.post("/api/run", response_model=RunResponse)
def run_command(request: RunRequest) -> RunResponse:
    try:
        result = run_twitter_command(request.preset, request.options)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CliNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CliTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except InvalidCliOutputError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except CliExecutionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return RunResponse(ok=True, command=result.command, data=result.data)


@app.post("/api/growth/discover")
def growth_discover(request: dict[str, Any]) -> dict[str, Any]:
    query = str(request.get("query", "")).strip()
    if not query:
        raise HTTPException(status_code=422, detail="Query is required")
    max_results = request.get("max", 20)
    try:
        result = run_twitter_command("search", {"query": query, "max": max_results})
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CliNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CliTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except (CliExecutionError, InvalidCliOutputError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    hidden_tweet_ids = get_growth_store().approved_commented_tweet_ids()
    candidates = [
        candidate
        for candidate in extract_tweet_candidates(result.data, query)
        if candidate["id"] not in hidden_tweet_ids
    ]

    return {
        "ok": True,
        "command": result.command,
        "candidates": candidates,
    }


@app.post("/api/growth/analyze")
def growth_analyze(request: dict[str, Any]) -> dict[str, Any]:
    candidates = request.get("candidates", [])
    if not isinstance(candidates, list) or not candidates:
        raise HTTPException(status_code=422, detail="Candidates are required")
    profile_focus = str(
        request.get("profile_focus")
        or "AI, startups, software engineering, and personal brand"
    )
    store = get_growth_store()
    preference_memory = store.preference_memory()
    try:
        recommendations = analyze_candidates(candidates, profile_focus, preference_memory)
    except DeepSeekConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DeepSeekError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    saved = store.save_recommendations(recommendations)
    return {"ok": True, "recommendations": saved}


@app.post("/api/growth/approve")
def growth_approve(request: dict[str, Any]) -> dict[str, Any]:
    action = str(request.get("action", "")).strip()
    tweet_id = str(request.get("tweet_id", "")).strip()
    comment_text = str(request.get("comment_text", "") or "")
    recommendation_id = request.get("recommendation_id")
    if action == "skip":
        if not tweet_id:
            raise HTTPException(status_code=422, detail="Tweet id is required")
        record = get_growth_store().record_action(
            recommendation_id=recommendation_id,
            action=action,
            tweet_id=tweet_id,
            comment_text=comment_text,
            status="approved",
            command=[],
            result={"ok": True, "skipped": True},
            metadata=request.get("metadata") if isinstance(request.get("metadata"), dict) else {},
        )
        return {"ok": True, "record": record}

    try:
        result = run_growth_action(action, tweet_id, comment_text)
    except GrowthValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CliNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CliTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except (CliExecutionError, InvalidCliOutputError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    record = get_growth_store().record_action(
        recommendation_id=recommendation_id,
        action=action,
        tweet_id=tweet_id,
        comment_text=comment_text,
        status="approved",
        command=result.command,
        result=result.data,
        metadata=request.get("metadata") if isinstance(request.get("metadata"), dict) else {},
    )
    return {"ok": True, "record": record}


@app.post("/api/growth/reject")
def growth_reject(request: dict[str, Any]) -> dict[str, Any]:
    action = str(request.get("action", "")).strip() or "skip"
    tweet_id = str(request.get("tweet_id", "")).strip()
    if not tweet_id:
        raise HTTPException(status_code=422, detail="Tweet id is required")
    record = get_growth_store().record_action(
        recommendation_id=request.get("recommendation_id"),
        action=action,
        tweet_id=tweet_id,
        comment_text=str(request.get("comment_text", "") or ""),
        status="rejected",
        command=[],
        result={"ok": True},
        metadata=request.get("metadata") if isinstance(request.get("metadata"), dict) else {},
    )
    return {"ok": True, "record": record}


@app.get("/api/growth/history")
def growth_history() -> dict[str, Any]:
    return {"ok": True, "history": get_growth_store().history()}
