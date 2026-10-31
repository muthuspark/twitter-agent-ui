import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.analytics import AnalyticsConfigurationError, AnalyticsDataError, fetch_analytics_summary
from app.config import load_environment
from app.models import Preset, PresetField, RunRequest, RunResponse
from app.deepseek_client import (
    DeepSeekConfigurationError,
    DeepSeekError,
    analyze_with_deepseek,
    generate_post_ideas_with_deepseek,
)
from app.growth import GrowthValidationError, extract_tweet_candidates
from app.storage import GrowthStore
from app.interests import collect_interest_context
from app.feed import fetch_feed_page
from app.twitter_cli import (
    PRESETS,
    CliExecutionError,
    CliNotFoundError,
    CliTimeoutError,
    InvalidCliOutputError,
    ValidationError,
    fetch_recent_liked_posts,
    fetch_recent_bookmarked_posts,
    resolve_search_query,
    run_growth_action,
    run_post_action,
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


def generate_post_ideas(
    profile_focus: str,
    themes: str,
    preference_memory: dict[str, Any] | None = None,
    count: int = 5,
    recent_liked_posts: list[dict[str, Any]] | None = None,
    recent_bookmarked_posts: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    return generate_post_ideas_with_deepseek(
        profile_focus,
        themes,
        preference_memory=preference_memory,
        count=count,
        recent_liked_posts=recent_liked_posts,
        recent_bookmarked_posts=recent_bookmarked_posts,
    )


@app.get("/api/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/api/analytics/summary")
def analytics_summary(start_date: str = "28daysAgo", end_date: str = "yesterday") -> dict[str, Any]:
    try:
        summary = fetch_analytics_summary(start_date=start_date, end_date=end_date)
    except AnalyticsConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AnalyticsDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "ok": True,
        "property_id": os.environ.get("GA4_PROPERTY_ID", ""),
        "start_date": summary.start_date,
        "end_date": summary.end_date,
        "metrics": summary.metrics,
        "acquisition": summary.acquisition,
        "pages": summary.pages,
        "campaigns": summary.campaigns,
        "landing_pages": summary.landing_pages,
        "funnel_events": summary.funnel_events,
        "recommendations": summary.recommendations,
    }


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
                    required=False,
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


@app.get("/api/feed")
def home_feed(
    cursor: str | None = Query(default=None, max_length=4096),
    limit: int = Query(default=20, ge=1, le=40),
) -> dict[str, Any]:
    try:
        return {"ok": True, **fetch_feed_page(cursor=cursor, limit=limit)}
    except CliNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CliTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except (CliExecutionError, InvalidCliOutputError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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
    query = resolve_search_query(request.get("query"))
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


@app.post("/api/posts/ideas")
def post_ideas(request: dict[str, Any]) -> dict[str, Any]:
    profile_focus = str(request.get("profile_focus") or "").strip()
    themes = str(request.get("themes") or "").strip()
    count = int(request.get("count", 5) or 5)
    store = get_growth_store()
    context = collect_interest_context(store, fetch_recent_liked_posts, fetch_recent_bookmarked_posts)
    if not context["likes"] and not context["bookmarks"]:
        detail = "No eligible likes or bookmarks found for the last 48 hours. Try again after liking or saving posts."
        if context["warning"]:
            detail += " " + context["warning"]
        raise HTTPException(status_code=422, detail=detail)
    try:
        ideas = generate_post_ideas(
            profile_focus,
            themes,
            preference_memory=store.preference_memory(),
            count=count,
            recent_liked_posts=context["likes"],
            recent_bookmarked_posts=context["bookmarks"],
        )
    except DeepSeekConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DeepSeekError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "ok": True, "ideas": ideas,
        "liked_posts_used": len(context["likes"]),
        "bookmarked_posts_used": len(context["bookmarks"]),
        "unique_posts_used": len({post["id"] for post in context["likes"] + context["bookmarks"]}),
        "context_since": context["since"], "context_until": context["until"],
        "context_warning": context["warning"], "likes_warning": context["warning"],
    }


@app.post("/api/posts/approve")
def approve_post(request: dict[str, Any]) -> dict[str, Any]:
    post_text = str(request.get("post_text", "") or "").strip()
    metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
    try:
        result = run_post_action(post_text)
    except GrowthValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CliNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CliTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except (CliExecutionError, InvalidCliOutputError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    result_data = result.data if isinstance(result.data, dict) else {"data": result.data}
    tweet_id = str(
        result_data.get("id")
        or result_data.get("tweet_id")
        or result_data.get("tweetId")
        or ""
    )
    record = get_growth_store().record_action(
        recommendation_id=None,
        action="post",
        tweet_id=tweet_id,
        comment_text=post_text,
        status="approved",
        command=result.command,
        result=result_data,
        metadata=metadata,
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
