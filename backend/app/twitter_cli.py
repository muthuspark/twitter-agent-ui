import json
import random
import subprocess
from dataclasses import dataclass
from typing import Any

from app.growth import build_growth_action_command, build_post_command


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
class PresetDefinition:
    id: str
    label: str
    description: str
    base_args: tuple[str, ...]
    requires_query: bool = False
    supports_max: bool = False


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


PRESETS: dict[str, PresetDefinition] = {
    "feed": PresetDefinition(
        id="feed",
        label="Feed",
        description="Fetch the authenticated home timeline.",
        base_args=("feed",),
        supports_max=True,
    ),
    "search": PresetDefinition(
        id="search",
        label="Search",
        description="Search tweets by keyword.",
        base_args=("search",),
        requires_query=True,
        supports_max=True,
    ),
    "bookmarks": PresetDefinition(
        id="bookmarks",
        label="Bookmarks",
        description="Fetch bookmarked tweets.",
        base_args=("bookmarks",),
        supports_max=True,
    ),
    "status": PresetDefinition(
        id="status",
        label="Status",
        description="Check whether the current session is authenticated.",
        base_args=("status",),
    ),
    "whoami": PresetDefinition(
        id="whoami",
        label="Whoami",
        description="Show the authenticated user's profile.",
        base_args=("whoami",),
    ),
}


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


def build_command(preset_id: str, options: dict[str, Any] | None = None) -> list[str]:
    options = options or {}
    preset = PRESETS.get(preset_id)
    if preset is None:
        raise ValidationError(f"Unsupported command preset: {preset_id}")

    command = ["twitter", *preset.base_args]

    if preset.requires_query:
        command.append(resolve_search_query(options.get("query")))

    if preset.supports_max:
        command.extend(["--max", str(_coerce_max(options.get("max")))])

    command.append("--json")
    return command


def run_twitter_command(preset_id: str, options: dict[str, Any] | None = None) -> CliResult:
    command = build_command(preset_id, options)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CliTimeoutError("The twitter command timed out") from exc
    except FileNotFoundError as exc:
        raise CliNotFoundError("The twitter CLI was not found on PATH") from exc

    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "Twitter CLI command failed"
        raise CliExecutionError(message)

    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise InvalidCliOutputError("Twitter CLI returned invalid JSON") from exc

    return CliResult(command=command, data=data)


def _run_json_command(command: list[str]) -> CliResult:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise CliTimeoutError("The twitter command timed out") from exc
    except FileNotFoundError as exc:
        raise CliNotFoundError("The twitter CLI was not found on PATH") from exc

    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "Twitter CLI command failed"
        raise CliExecutionError(message)

    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise InvalidCliOutputError("Twitter CLI returned invalid JSON") from exc
    return CliResult(command=command, data=data)


def run_growth_action(action: str, tweet_id: str, comment_text: str | None = None) -> CliResult:
    command = build_growth_action_command(action, tweet_id, comment_text)
    return _run_json_command(command)


def run_post_action(post_text: str) -> CliResult:
    command = build_post_command(post_text)
    return _run_json_command(command)
