"""One home-timeline page, run in the installed twitter-cli Python environment.

Keep the dependency on twitter-cli's internal pagination API isolated here.
The CLI's public feed command discards continuation cursors.
"""

import contextlib
import json
import sys


def fetch_page(client, cursor, count, *, parse_timeline, serialize, features):
    variables = {
        "count": count,
        "includePromotedContent": False,
        "latestControlAvailable": True,
        "requestContext": "launch",
    }
    if cursor:
        variables["cursor"] = cursor
    payload = client._graphql_get("HomeTimeline", variables, features)
    instructions = payload.get("data", {}).get("home", {}).get("home_timeline_urt", {}).get("instructions")
    if not isinstance(instructions, list):
        raise ValueError("Twitter returned an unrecognized home timeline response")
    tweets, next_cursor = parse_timeline(payload, lambda _: instructions)
    unique = {str(tweet.id): serialize(tweet) for tweet in tweets if tweet.id}
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
            )
        json.dump(page, sys.stdout)
    except Exception as exc:
        json.dump({"error": str(exc)}, sys.stdout)
        sys.exit(1)


if __name__ == "__main__":
    main()
