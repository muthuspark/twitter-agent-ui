"""One home-timeline page, run in the installed twitter-cli Python environment.

Keep the dependency on twitter-cli's internal pagination API isolated here.
The CLI's public feed command discards continuation cursors.
"""

import contextlib
import json
import sys


def serialize_feed_tweet(tweet, serialize):
    data = serialize(tweet)
    # The CLI serializer omits the quote's language. Preserve it so an
    # English outer post cannot introduce non-English quoted text.
    quote = getattr(tweet, "quoted_tweet", None)
    if quote and data.get("quotedTweet"):
        data["quotedTweet"]["lang"] = quote.lang
    return data


def fetch_page(client, cursor, count, *, parse_timeline, serialize, features, tweet_id=None):
    variables = {
        "count": count,
        "includePromotedContent": False,
        "latestControlAvailable": True,
        "requestContext": "launch",
    }
    if tweet_id:
        variables = {
            "count": count, "focalTweetId": tweet_id, "referrer": "tweet",
            "with_rux_injections": False, "includePromotedContent": True,
            "rankingMode": "Relevance", "withCommunity": True,
            "withQuickPromoteEligibilityTweetFields": True,
            "withBirdwatchNotes": True, "withVoice": True,
        }
    if cursor:
        variables["cursor"] = cursor
    if tweet_id:
        payload = client._graphql_get("TweetDetail", variables, features, field_toggles={
            "withArticleRichContentState": True, "withArticlePlainText": False,
            "withGrokAnalyze": False, "withDisallowedReplyControls": False,
        })
        data = payload.get("data") or {}
        instructions = (((data.get("tweetResult") or {}).get("result") or {}).get("timeline") or {}).get("instructions")
        if instructions is None:
            instructions = (data.get("threaded_conversation_with_injections_v2") or {}).get("instructions")
    else:
        payload = client._graphql_get("HomeTimeline", variables, features)
        instructions = payload.get("data", {}).get("home", {}).get("home_timeline_urt", {}).get("instructions")
    if not isinstance(instructions, list):
        raise ValueError("Twitter returned an unrecognized home timeline response")
    tweets, next_cursor = parse_timeline(payload, lambda _: instructions)
    unique = {str(tweet.id): serialize_feed_tweet(tweet, serialize) for tweet in tweets if tweet.id}
    next_cursor = next_cursor if next_cursor and next_cursor != cursor else None
    return {"tweets": list(unique.values()), "next_cursor": next_cursor, "has_more": bool(next_cursor)}


def main():
    try:
        # Keep CLI diagnostics out of the JSON protocol, including auth messages.
        with contextlib.redirect_stdout(sys.stderr):
            from twitter_cli.cli import _get_client
            from twitter_cli.config import load_config
            from twitter_cli.graphql import FEATURES
            from twitter_cli.parser import parse_timeline_response
            from twitter_cli.serialization import tweet_to_dict

            request = json.load(sys.stdin)
            config = load_config()
            config["rateLimit"] = {**(config.get("rateLimit") or {}), "maxRetries": 1}
            client = _get_client(config, quiet=True)
            page = fetch_page(
                client, request.get("cursor"), request["limit"],
                parse_timeline=parse_timeline_response, serialize=tweet_to_dict, features=FEATURES,
                tweet_id=request.get("tweet_id"),
            )
        json.dump(page, sys.stdout)
    except Exception as exc:
        json.dump({"error": str(exc)}, sys.stdout)
        sys.exit(1)


if __name__ == "__main__":
    main()
