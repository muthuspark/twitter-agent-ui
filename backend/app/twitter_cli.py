import json
import random
import subprocess
from dataclasses import dataclass
from typing import Any

from app.growth import build_growth_action_command, build_post_command, extract_tweet_candidates


class ValidationError(Exception):
    pass


class CliExecutionError(Exception):
    pass


class CliTimeoutError(Exception):
    pass


class CliNotFoundError(Exception):
    pass


class InvalidCliOutputError(Exception):
    pass


@dataclass(frozen=True)
class CliResult:
    command: list[str]
    data: Any


JOVIS_SEARCH_QUERIES: tuple[str, ...] = (
    "data team bottleneck",
    "waiting on data team",
    "manual reporting",
    "chat with database",
    "ask questions of data",
    "AI data analyst",
    "RevOps reporting",
    "support analytics",
    "CRM analytics",
    "business users data",
    "founder dashboard",
    "dashboard is outdated",
    "can't trust dashboard",
    "spreadsheet reporting",
    "single source of truth",
)


def resolve_search_query(query: Any = None) -> str:
    text = str(query or "").strip()
    if text:
        return text
    return random.choice(JOVIS_SEARCH_QUERIES)


def _coerce_max(value: Any) -> int:
    if value in (None, ""):
        return 20
    try:
        max_value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Max must be between 1 and 100") from exc
    if not 1 <= max_value <= 100:
        raise ValidationError("Max must be between 1 and 100")
    return max_value


def _parse_cli_response(completed: subprocess.CompletedProcess) -> Any:
    # twitter-cli 0.8.5 prints cookie progress before its JSON for write commands.
    # Only accept a complete JSON response at the end, never braces in a log line.
    data = None
    parsed = False
    try:
        data = json.loads(completed.stdout)
        parsed = True
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        offset = 0
        for line in completed.stdout.splitlines(keepends=True):
            candidate = line.lstrip()
            if candidate.startswith(('{', '[')):
                start = offset + len(line) - len(candidate)
                try:
                    value, end = decoder.raw_decode(completed.stdout, start)
                    if not completed.stdout[end:].strip():
                        data, parsed = value, True
                        break
                except json.JSONDecodeError:
                    pass
            offset += len(line)

    if completed.returncode != 0 or (isinstance(data, dict) and data.get('ok') is False):
        error = data.get('error') if isinstance(data, dict) else None
        if isinstance(error, dict) and error.get('message'):
            code = str(error.get('code') or 'api_error')
            raise CliExecutionError(f"X request failed ({code}): {error['message']}")
        if isinstance(error, str) and error.strip():
            raise CliExecutionError(error)
        if 'Failed to init ClientTransaction' in completed.stderr:
            raise CliExecutionError(
                'The Twitter CLI failed and its X transaction setup reported an error. '
                'The warning alone does not confirm whether a post was published. '
                'Check your X profile before trying again to avoid a duplicate post.'
            )
        raise CliExecutionError(
            completed.stderr.strip() or completed.stdout.strip() or 'Twitter CLI command failed'
        )
    if not parsed:
        raise InvalidCliOutputError(
            'Twitter CLI returned invalid JSON. For posting commands, check your X profile '
            'before trying again to avoid a duplicate post.'
        )
    return data


def _run_json_command(command: list[str], timeout: int = 25) -> CliResult:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CliTimeoutError("The twitter command timed out") from exc
    except FileNotFoundError as exc:
        raise CliNotFoundError("The twitter CLI was not found on PATH") from exc

    data = _parse_cli_response(completed)
    return CliResult(command=command, data=data)


def search_tweets(query: Any = None, limit: Any = 20) -> CliResult:
    command = ["twitter", "search", resolve_search_query(query), "--max", str(_coerce_max(limit)), "--json"]
    for attempt in range(2):
        try:
            return _run_json_command(command, timeout=60)
        except CliExecutionError as exc:
            if attempt or not any(marker in str(exc).lower() for marker in ("not_found", "http 404")):
                raise
    raise CliExecutionError("Twitter search failed after retrying the X search endpoint.")


def run_growth_action(action: str, tweet_id: str, comment_text: str | None = None) -> CliResult:
    command = build_growth_action_command(action, tweet_id, comment_text)
    return _run_json_command(command)


def run_post_action(post_text: str) -> CliResult:
    return _run_json_command(build_post_command(post_text))


def fetch_recent_liked_posts(limit: int = 20) -> list[dict[str, Any]]:
    identity = _run_json_command(["twitter", "whoami", "--json"]).data
    if identity.get("ok") is False:
        raise CliExecutionError("Unable to identify the authenticated X account")
    profile = identity.get("data") or {}
    profile = profile.get("user", profile)
    handle = profile.get("screenName") or profile.get("username")
    if not handle:
        raise InvalidCliOutputError("Twitter CLI did not return the authenticated username")
    result = _run_json_command(["twitter", "likes", handle, "--max", str(limit), "--json"])
    if result.data.get("ok") is False:
        raise CliExecutionError("Unable to fetch recently liked posts from X")
    return extract_tweet_candidates(result.data, "")[:limit]


def fetch_recent_bookmarked_posts(limit: int = 100) -> list[dict[str, Any]]:
    result = _run_json_command(["twitter", "bookmarks", "--max", str(_coerce_max(limit)), "--json"])
    if result.data.get("ok") is False:
        raise CliExecutionError("Unable to fetch bookmarked posts from X")
    return extract_tweet_candidates(result.data, "")[:limit]
