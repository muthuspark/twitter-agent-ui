"""Preserve rich article data before twitter-cli's text-only parser drops it.

Run inside the installed CLI's Python environment, as with feed_bridge.py.
"""
import contextlib
import json
import sys


def fetch_rich_article(client, tweet_id, serialize):
    original = client._graphql_get
    captured = {}

    def capture(*args, **kwargs):
        response = original(*args, **kwargs)
        if args and args[0] == "TweetResultByRestId":
            captured.update(response)
        return response

    client._graphql_get = capture
    try:
        tweet = client.fetch_article(tweet_id)
    finally:
        client._graphql_get = original
    result = captured.get("data", {}).get("tweetResult", {}).get("result", {})
    result = result.get("tweet", result)
    rich = result.get("article", {}).get("article_results", {}).get("result")
    if not isinstance(rich, dict):
        raise ValueError("X did not return the article's rich content")
    return {"data": serialize(tweet), "rich_article": rich}


def main():
    try:
        with contextlib.redirect_stdout(sys.stderr):
            from twitter_cli.cli import _get_client
            from twitter_cli.config import load_config
            from twitter_cli.serialization import tweet_to_dict

            request = json.load(sys.stdin)
            config = load_config()
            config["rateLimit"] = {**(config.get("rateLimit") or {}), "maxRetries": 1}
            result = fetch_rich_article(_get_client(config, quiet=True), request["tweet_id"], tweet_to_dict)
        json.dump(result, sys.stdout)
    except Exception:
        # Do not expose auth diagnostics or upstream response bodies to the UI.
        json.dump({"error": "Unable to retrieve the full article from X"}, sys.stdout)
        sys.exit(1)


if __name__ == "__main__":
    main()
