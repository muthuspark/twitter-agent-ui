import os
from pathlib import Path
from typing import Any
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Query, Path as ApiPath
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from app.analytics import AnalyticsConfigurationError, AnalyticsDataError, fetch_analytics_summary
from app.articles import ArticleLinkError, ArticleContentError, fetch_article
from app.config import load_environment
from app.codex_client import (
    CodexConfigurationError,
    CodexError,
    CodexTimeoutError,
    CodexBusyError,
    analyze_with_codex,
    generate_post_ideas_with_codex,
    generate_comment_alternatives_with_codex,
    refine_post_with_codex,
    curate_research_for_essay,
)
from app.editorial import EditorialContextError, load_editorial_context, essay_source
from app.growth import GrowthValidationError, extract_tweet_candidates
from app.storage import GrowthStore
from app.interests import collect_interest_context
from app.feed import fetch_feed_page
from app.trends import ResearchError, fetch_trending_research
from app import reddit_cli
from app.prospect_search import status as prospect_search_status
from app.prospects import (
    get_run as get_prospect_run, start_run as start_prospect_run, suggest_response,
    compact_run, run_progress, research_details, get_prospect, save_draft, draft_versions, publish_reply,
)
from app.twitter_cli import (
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
    search_tweets,
)

load_environment()

app = FastAPI(title="Twitter Agent API")

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


class ArticleRequest(BaseModel):
    url: str


class RefinePostRequest(BaseModel):
    post_text: str


@app.post("/api/posts/refine")
def refine_post(request: RefinePostRequest):
    post_text = request.post_text.strip()
    if not post_text:
        raise HTTPException(status_code=422, detail="Write a post before refining it.")
    if len(post_text) > 280:
        raise HTTPException(status_code=422, detail="Post text must be 280 characters or fewer.")
    try:
        return {"ok": True, "post_text": refine_post_with_codex(post_text)}
    except CodexBusyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CodexTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except CodexConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CodexError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/articles/read")
def article_read(request: ArticleRequest):
    try:
        return fetch_article(request.url)
    except ArticleLinkError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ArticleContentError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except CliTimeoutError as exc:
        raise HTTPException(status_code=504, detail="Loading this X article timed out. Please retry.") from exc
    except CliNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/prospects/sources/research/status")
def public_research_status():
    return prospect_search_status()


@app.get("/api/prospects/sources/reddit/status")
def prospect_reddit_status():
    return reddit_cli.connection_status()


@app.post("/api/prospects/runs")
def prospect_run_start(compact: bool = False):
    run = start_prospect_run()
    return compact_run(run) if compact else run


@app.get("/api/prospects/runs/latest")
def prospect_run_latest(compact: bool = False):
    run = get_prospect_run()
    return {"run": compact_run(run) if compact else run}


@app.get("/api/prospects/runs/{run_id}")
def prospect_run_status(run_id: str, compact: bool = False):
    run = get_prospect_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    return compact_run(run) if compact else run


@app.get("/api/prospects/runs/{run_id}/progress")
def prospect_progress(run_id: str):
    run = get_prospect_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    return run_progress(run)


@app.get("/api/prospects/runs/{run_id}/research")
def prospect_research_details(run_id: str):
    run = get_prospect_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Research run not found")
    return research_details(run)


@app.get("/api/prospects/runs/{run_id}/prospect")
def prospect_detail(run_id: str, url: str = Query(...)):
    try:
        return get_prospect(run_id, url)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class ProspectDraftRequest(BaseModel):
    url: str
    text: str


class ProspectPublishRequest(ProspectDraftRequest):
    username: str


@app.post("/api/prospects/runs/{run_id}/publish")
def prospect_publish_reply(run_id: str, request: ProspectPublishRequest):
    try:
        return publish_reply(run_id, request.url, request.text, request.username)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.put("/api/prospects/runs/{run_id}/draft")
def prospect_draft_save(run_id: str, request: ProspectDraftRequest):
    try:
        return save_draft(run_id, request.url, request.text)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/prospects/runs/{run_id}/versions")
def prospect_draft_versions(run_id: str, url: str = Query(...)):
    try:
        return {"versions": draft_versions(run_id, url)}
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/prospects/runs/{run_id}/response")
def prospect_response(run_id: str, request: dict[str, Any]):
    try:
        return suggest_response(run_id, request.get("url", ""))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CodexBusyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CodexTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except CodexConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CodexError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def analyze_candidates(
    candidates: list[dict[str, Any]],
    profile_focus: str,
    preference_memory: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    return analyze_with_codex(
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
    research_sources: list[dict[str, Any]] | None = None,
    editorial_context: dict[str, Any] | None = None,
    idea_type: str = 'mix',
) -> list[dict[str, Any]]:
    return generate_post_ideas_with_codex(
        profile_focus,
        themes,
        preference_memory=preference_memory,
        count=count,
        recent_liked_posts=recent_liked_posts,
        recent_bookmarked_posts=recent_bookmarked_posts,
        research_sources=research_sources,
        editorial_context=editorial_context,
        idea_type=idea_type,
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


@app.get("/api/feed/thread/{tweet_id}")
def feed_thread(
    tweet_id: str = ApiPath(pattern=r"^[0-9]{1,30}$"),
    cursor: str | None = Query(default=None, max_length=4096),
    limit: int = Query(default=20, ge=1, le=40),
) -> dict[str, Any]:
    try:
        return {"ok": True, **fetch_feed_page(cursor=cursor, limit=limit, tweet_id=tweet_id)}
    except CliNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CliTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except (CliExecutionError, InvalidCliOutputError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/growth/discover")
def growth_discover(request: dict[str, Any]) -> dict[str, Any]:
    query = resolve_search_query(request.get("query"))
    max_results = request.get("max", 20)
    try:
        result = search_tweets(query, max_results)
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


@app.get("/api/growth/comment-candidates")
def growth_comment_candidates() -> dict[str, Any]:
    return {"ok": True, "candidates": get_growth_store().pending_recommendations()}


@app.post("/api/growth/comment-candidates/{recommendation_id}/alternatives")
def growth_comment_alternatives(recommendation_id: int = ApiPath(gt=0)) -> dict[str, Any]:
    store = get_growth_store()
    candidate = next(
        (item for item in store.pending_recommendations() if item["id"] == recommendation_id),
        None,
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Comment candidate not found.")
    try:
        alternatives = generate_comment_alternatives_with_codex(
            candidate["tweet"], candidate["comment"], preference_memory=store.preference_memory()
        )
        return {"ok": True, "alternatives": alternatives}
    except CodexBusyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CodexTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except CodexConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CodexError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/growth/comment-candidates/refresh")
def refresh_comment_candidates(request: dict[str, Any]) -> dict[str, Any]:
    query = resolve_search_query(request.get("query"))
    try:
        max_results = max(1, min(30, int(request.get("max", 12) or 12)))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Max candidates must be between 1 and 30.") from exc
    store = get_growth_store()
    existing = store.pending_recommendations()
    seen_ids = {str(item["tweet_id"]) for item in existing}
    seen_ids.update(store.handled_recommendation_tweet_ids())
    search_source = "search"
    try:
        result = search_tweets(query, max_results)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CliExecutionError as exc:
        if not any(marker in str(exc).lower() for marker in ("not_found", "http 404")):
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        # X sometimes returns 404 for its rotating private search GraphQL route.
        # Keep discovery useful by reviewing the user's recent home timeline instead.
        try:
            result = fetch_feed_page(limit=max_results)
        except CliNotFoundError as feed_exc:
            raise HTTPException(status_code=503, detail=str(feed_exc)) from feed_exc
        except CliTimeoutError as feed_exc:
            raise HTTPException(status_code=504, detail=str(feed_exc)) from feed_exc
        except (CliExecutionError, InvalidCliOutputError) as feed_exc:
            raise HTTPException(status_code=502, detail=str(feed_exc)) from feed_exc
        search_source = "home_timeline"
    except CliNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CliTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except (CliExecutionError, InvalidCliOutputError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if search_source == "home_timeline":
        raw_candidates = [
            {**item, "sourceQuery": query}
            for item in result.get("tweets", [])
            if isinstance(item, dict) and item.get("id") and item.get("text")
        ]
    else:
        raw_candidates = extract_tweet_candidates(result.data, query)
    candidates = [
        item for item in raw_candidates
        if str(item["id"]) not in seen_ids
    ]
    if candidates:
        profile_focus = str(request.get("profile_focus") or "AI, startups, software engineering, and useful conversations for founders and business teams")
        if search_source == "home_timeline":
            profile_focus += f" Prioritize posts related to the user's topic search: {query}."
        try:
            recommendations = analyze_candidates(candidates, profile_focus, store.preference_memory())
        except CodexTimeoutError as exc:
            raise HTTPException(status_code=504, detail=str(exc)) from exc
        except CodexBusyError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except CodexConfigurationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except CodexError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        by_id = {str(item["id"]): item for item in candidates}
        comments = []
        for recommendation in recommendations:
            if recommendation.get("action") != "comment":
                continue
            tweet = by_id.get(str(recommendation.get("tweet_id")))
            if tweet:
                comments.append({**recommendation, "tweet": tweet})
        store.save_recommendations(comments)
    return {
        "ok": True,
        "query": query,
        "search_source": search_source,
        "new_candidates": len(candidates),
        "candidates": store.pending_recommendations(),
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
    except CodexTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except CodexBusyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CodexConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CodexError as exc:
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


def required_editorial_context():
    try:
        return load_editorial_context()
    except EditorialContextError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/posts/editorial-direction")
def editorial_direction():
    return {"ok": True, "direction": required_editorial_context()}


@app.get("/api/posts/saved")
def saved_posts(kind: str = Query("likes", pattern="^(likes|bookmarks)$")):
    fetch = fetch_recent_liked_posts if kind == "likes" else fetch_recent_bookmarked_posts
    try:
        posts = fetch(40)
    except CliNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CliTimeoutError as exc:
        raise HTTPException(status_code=504, detail="Loading saved posts timed out. Please retry.") from exc
    except (CliExecutionError, InvalidCliOutputError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "posts": posts}


@app.get("/api/posts/essay", response_class=PlainTextResponse)
def editorial_essay():
    return required_editorial_context()["content"]


@app.post("/api/posts/ideas")
def post_ideas(request: dict[str, Any]) -> dict[str, Any]:
    editorial = required_editorial_context()
    source_mode = str(request.get("source_mode") or "trends")
    if source_mode not in {"trends", "interests", "essay"}:
        raise HTTPException(status_code=422, detail="Choose essay research, recent interests, or essay only.")
    idea_type = str(request.get("idea_type") or "mix")
    if idea_type not in {"mix", "thought_leadership", "insight", "project", "experiment", "evidence", "counterpoint"}:
        raise HTTPException(status_code=422, detail="Choose a valid idea type.")
    profile_focus = str(request.get("profile_focus") or "").strip()
    themes = str(request.get("themes") or "").strip()
    try:
        count = max(1, min(8, int(request.get("count", 5) or 5)))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail="Ideas must be a number from 1 to 8.") from exc
    store = get_growth_store()
    now = datetime.now(timezone.utc)
    context = {"likes": [], "bookmarks": [], "since": (now - timedelta(days=7)).isoformat(), "until": now.isoformat(), "warning": None}
    research = None
    if source_mode == "trends":
        try:
            research = fetch_trending_research(editorial_context=editorial)
            context.update(since=research["since"], until=research["researched_at"], warning=research["warning"])
        except ResearchError:
            context["warning"] = "Recent research was unavailable. Drafts will draw only from your essay, without new factual claims."
    elif source_mode == "interests":
        context = collect_interest_context(store, fetch_recent_liked_posts, fetch_recent_bookmarked_posts)
        if not context["likes"] and not context["bookmarks"]:
            detail = "No eligible likes or bookmarks found for the last 48 hours. Choose Essay only to draft directly from your essay."
            if context["warning"]:
                detail += " " + context["warning"]
            raise HTTPException(status_code=422, detail=detail)
    try:
        selected = curate_research_for_essay(research["sources"], editorial, themes) if research else []
        if research and not selected:
            context["warning"] = " ".join(filter(None, [context["warning"], "No recent sources had a direct connection to your essay. These drafts use the essay only."]))
        sources = [essay_source(editorial), *selected]
        ideas = generate_post_ideas(
            profile_focus, themes, preference_memory=store.preference_memory(), count=count,
            recent_liked_posts=context["likes"], recent_bookmarked_posts=context["bookmarks"],
            research_sources=sources, editorial_context=editorial, idea_type=idea_type,
        )
    except CodexTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except CodexBusyError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CodexConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CodexError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    by_id = {source["id"]: source for source in sources}
    grounded = []
    for idea in ideas[:count]:
        connection = idea.get("essay_connection", "")
        ids = [source_id for source_id in dict.fromkeys(idea.get("source_ids", [])) if source_id in by_id]
        if ids and isinstance(connection, str) and len(connection.strip()) >= 20:
            grounded.append({**idea, "source_ids": ids, "sources": [by_id[source_id] for source_id in ids], "essay_version": editorial["version"]})
    if not grounded:
        raise HTTPException(status_code=502, detail="Codex returned no drafts with a clear essay connection and valid references. Please try again.")
    return {
        "ok": True, "ideas": grounded,
        "liked_posts_used": len(context["likes"]), "bookmarked_posts_used": len(context["bookmarks"]),
        "unique_posts_used": len({post["id"] for post in context["likes"] + context["bookmarks"]}),
        "context_since": context["since"], "context_until": context["until"],
        "context_warning": context["warning"], "likes_warning": context["warning"],
        "source_mode": source_mode, "research_sources": selected,
        "researched_at": research["researched_at"] if research else None,
        "editorial_direction": {key: editorial[key] for key in ("title", "file", "version", "updated_at")},
    }


@app.post("/api/posts/approve")
def approve_post(request: dict[str, Any]) -> dict[str, Any]:
    post_text = str(request.get("post_text", "") or "").strip()
    metadata = request.get("metadata") if isinstance(request.get("metadata"), dict) else {}
    try:
        post_idea = metadata.get('post_idea')
        if isinstance(post_idea, dict) and post_idea.get('essay_version'):
            if post_idea['essay_version'] != required_editorial_context()['version']:
                raise GrowthValidationError('essay.md has changed since this draft was generated. Generate a fresh draft before posting.')
        if request.get("image_id"):
            raise GrowthValidationError('Image attachments are no longer supported. Refresh the app and approve the text-only draft.')
        result = run_post_action(post_text)
        if isinstance(result.data, dict) and result.data.get("ok") is False:
            raise CliExecutionError("X did not publish this post. Check the session and retry.")
    except GrowthValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except CliNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except CliTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except (CliExecutionError, InvalidCliOutputError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    result_data = result.data if isinstance(result.data, dict) else {"data": result.data}
    post_data = result_data.get("data") if isinstance(result_data.get("data"), dict) else result_data
    tweet_id = str(
        post_data.get("id")
        or post_data.get("tweet_id")
        or post_data.get("tweetId")
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
