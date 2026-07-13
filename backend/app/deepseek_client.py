import json
import os
from typing import Any, Callable

import httpx


class DeepSeekConfigurationError(Exception):
    pass


class DeepSeekError(Exception):
    pass


ALLOWED_ACTIONS = {"like", "comment", "skip"}


def _comment_drafts(item: dict[str, Any]) -> list[str]:
    raw_drafts = item.get("comment_drafts")
    if isinstance(raw_drafts, list):
        drafts = [str(draft).strip() for draft in raw_drafts if str(draft).strip()]
    else:
        drafts = []
    fallback = str(item.get("comment", "")).strip()
    if fallback and fallback not in drafts:
        drafts.insert(0, fallback)
    return drafts[:3]


def parse_recommendations(content: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise DeepSeekError("DeepSeek returned invalid recommendation JSON") from exc

    items = payload.get("recommendations")
    if not isinstance(items, list):
        raise DeepSeekError("DeepSeek response did not include recommendations")

    recommendations: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        action = str(item.get("action", "skip")).strip().lower()
        if action not in ALLOWED_ACTIONS:
            action = "skip"
        tweet_id = str(item.get("tweet_id", "")).strip()
        if not tweet_id:
            continue
        confidence = int(item.get("confidence", 0) or 0)
        confidence = max(0, min(100, confidence))
        drafts = _comment_drafts(item)
        recommendations.append(
            {
                "tweet_id": tweet_id,
                "action": action,
                "confidence": confidence,
                "reason": str(item.get("reason", "")).strip(),
                "comment": drafts[0] if drafts else "",
                "comment_drafts": drafts,
                "risk": str(item.get("risk", "medium")).strip().lower() or "medium",
            }
        )
    return recommendations


def parse_post_ideas(content: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise DeepSeekError("DeepSeek returned invalid post idea JSON") from exc

    items = payload.get("ideas")
    if not isinstance(items, list):
        raise DeepSeekError("DeepSeek response did not include ideas")

    ideas: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        post_text = str(item.get("post_text", "")).strip()
        if not post_text:
            continue
        ideas.append(
            {
                "title": str(item.get("title", "")).strip() or "Post idea",
                "angle": str(item.get("angle", "")).strip(),
                "audience": str(item.get("audience", "")).strip(),
                "rationale": str(item.get("rationale", "")).strip(),
                "cta": str(item.get("cta", "")).strip(),
                "post_text": post_text[:280],
            }
        )
    return ideas


def analyze_with_deepseek(
    candidates: list[dict[str, Any]],
    profile_focus: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    post: Callable[..., httpx.Response] | None = None,
    preference_memory: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    resolved_api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not resolved_api_key:
        raise DeepSeekConfigurationError("DEEPSEEK_API_KEY is not configured")

    resolved_model = model or os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
    post_fn = post or httpx.post
    response = post_fn(
        "https://api.deepseek.com/chat/completions",
        headers={
            "Authorization": f"Bearer {resolved_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": resolved_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an X growth strategist for AI, startups, software engineering, "
                        "and personal-brand positioning. Return only valid JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "instruction": (
                                "Evaluate each candidate post and recommend exactly one action: "
                                "like, comment, or skip. Prefer comment only when the draft adds "
                                "specific value. Avoid spammy, political, abusive, or generic engagement. "
                                "Output JSON with key recommendations, where each item has tweet_id, "
                                "action, confidence, reason, comment_drafts, and risk. For comment actions, "
                                "provide exactly three distinct comment_drafts in the user's voice. For like "
                                "or skip actions, comment_drafts can be an empty array."
                            ),
                            "profile_focus": profile_focus,
                            "preference_memory": preference_memory
                            or {"summary": "No preference memory recorded yet."},
                            "candidates": candidates[:20],
                            "example": {
                                "recommendations": [
                                    {
                                        "tweet_id": "123",
                                        "action": "comment",
                                        "confidence": 82,
                                        "reason": "Relevant AI builder asking a technical question.",
                                        "comment_drafts": [
                                            "The hard part is evals, not the agent loop.",
                                            "I would start by listing failure cases before adding tools.",
                                            "Most agent projects fail on judgment, not orchestration.",
                                        ],
                                        "risk": "low",
                                    }
                                ]
                            },
                        }
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 4000,
            "stream": False,
        },
        timeout=45,
    )
    if response.status_code >= 400:
        raise DeepSeekError(f"DeepSeek request failed with HTTP {response.status_code}")

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DeepSeekError("DeepSeek response shape was not recognized") from exc

    return parse_recommendations(content)


def generate_post_ideas_with_deepseek(
    profile_focus: str,
    themes: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    post: Callable[..., httpx.Response] | None = None,
    preference_memory: dict[str, Any] | None = None,
    count: int = 5,
) -> list[dict[str, Any]]:
    resolved_api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not resolved_api_key:
        raise DeepSeekConfigurationError("DEEPSEEK_API_KEY is not configured")

    resolved_model = model or os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash")
    post_fn = post or httpx.post
    response = post_fn(
        "https://api.deepseek.com/chat/completions",
        headers={
            "Authorization": f"Bearer {resolved_api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": resolved_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a B2B founder-led growth strategist for Jovis.ai. "
                        "Write clear original X posts that attract qualified website traffic. "
                        "Return only valid JSON."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "instruction": (
                                "Generate original post ideas for X. Each post must be useful, specific, "
                                "and written for buyers who need answers from live business data. Avoid "
                                "hype, generic AI claims, engagement bait, hashtags, and unsupported metrics. "
                                "Keep post_text at 280 characters or fewer. Include a soft CTA only when natural."
                            ),
                            "profile_focus": profile_focus,
                            "themes": themes,
                            "preference_memory": preference_memory
                            or {"summary": "No preference memory recorded yet."},
                            "count": max(1, min(8, int(count or 5))),
                            "example": {
                                "ideas": [
                                    {
                                        "title": "Data team bottleneck",
                                        "angle": "Business users should not wait days for simple answers.",
                                        "audience": "Founders and RevOps teams",
                                        "rationale": "Targets a frequent buyer pain with a concrete point of view.",
                                        "cta": "See how Jovis works",
                                        "post_text": (
                                            "Most teams do not have a data problem. They have an answer latency problem. "
                                            "The CRM has the signal, support has the context, finance has the truth, "
                                            "but nobody can ask across them in plain English."
                                        ),
                                    }
                                ]
                            },
                        }
                    ),
                },
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": 4000,
            "stream": False,
        },
        timeout=45,
    )
    if response.status_code >= 400:
        raise DeepSeekError(f"DeepSeek request failed with HTTP {response.status_code}")

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DeepSeekError("DeepSeek response shape was not recognized") from exc

    return parse_post_ideas(content)
