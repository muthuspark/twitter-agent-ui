from typing import Any


class GrowthValidationError(Exception):
    pass


def extract_tweet_candidates(payload: dict[str, Any], source_query: str) -> list[dict[str, Any]]:
    tweets = payload.get("data", [])
    if isinstance(tweets, dict):
        tweets = tweets.get("data", [])
    if not isinstance(tweets, list):
        return []

    candidates: list[dict[str, Any]] = []
    for tweet in tweets:
        if not isinstance(tweet, dict) or not tweet.get("id") or not tweet.get("text"):
            continue
        candidates.append(
            {
                "id": str(tweet["id"]),
                "text": str(tweet["text"]),
                "author": tweet.get("author") or {},
                "metrics": tweet.get("metrics") or {},
                "createdAtISO": tweet.get("createdAtISO") or tweet.get("createdAtLocal") or "",
                "lang": tweet.get("lang") or "",
                "sourceQuery": source_query,
            }
        )
    return candidates


def build_growth_action_command(action: str, tweet_id: str, comment_text: str | None = None) -> list[str]:
    tweet_id = str(tweet_id).strip()
    if not tweet_id:
        raise GrowthValidationError("Tweet id is required")

    if action == "like":
        return ["twitter", "like", tweet_id, "--json"]

    if action == "comment":
        comment = str(comment_text or "").strip()
        if not comment:
            raise GrowthValidationError("Comment text is required")
        return ["twitter", "reply", tweet_id, comment, "--json"]

    raise GrowthValidationError(f"Unsupported growth action: {action}")


def build_post_command(post_text: str) -> list[str]:
    text = str(post_text or "").strip()
    if not text:
        raise GrowthValidationError("Post text is required")
    if len(text) > 280:
        raise GrowthValidationError("Post text must be 280 characters or fewer")
    return ["twitter", "post", text, "--json"]
