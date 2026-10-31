import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess

from app.twitter_cli import CliExecutionError, CliNotFoundError, CliTimeoutError, InvalidCliOutputError


def cli_python_command() -> list[str]:
    configured = os.environ.get("TWITTER_CLI_PYTHON")
    if configured:
        return [configured]
    executable = shutil.which("twitter")
    if not executable:
        raise CliNotFoundError("The twitter CLI was not found on PATH")
    try:
        with Path(executable).open() as file:
            shebang = file.readline().strip()
    except (OSError, UnicodeError) as exc:
        raise CliExecutionError("Set TWITTER_CLI_PYTHON to the Python interpreter containing twitter-cli") from exc
    command = shlex.split(shebang[2:]) if shebang.startswith("#!") else []
    if not command or not any("python" in Path(part).name.lower() for part in command):
        raise CliExecutionError("Set TWITTER_CLI_PYTHON to the Python interpreter containing twitter-cli")
    return command


def fetch_feed_page(cursor: str | None = None, limit: int = 20) -> dict:
    # Running the file directly would put app/twitter_cli.py ahead of the
    # installed twitter_cli package on sys.path.
    command = [
        *cli_python_command(), "-c",
        "import runpy, sys; runpy.run_path(sys.argv[1], run_name='__main__')",
        str(Path(__file__).with_name("feed_bridge.py")),
    ]
    try:
        completed = subprocess.run(
            command, input=json.dumps({"cursor": cursor, "limit": limit}),
            capture_output=True, text=True, timeout=45, check=False,
        )
    except FileNotFoundError as exc:
        raise CliNotFoundError("The twitter CLI Python interpreter was not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise CliTimeoutError("Loading your Twitter feed timed out. Try again.") from exc
    if completed.returncode:
        raise CliExecutionError("Unable to load your Twitter feed. Check your CLI sign-in and try again.")
    try:
        page = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise InvalidCliOutputError("Twitter returned an invalid feed page") from exc
    if (
        not isinstance(page, dict) or not isinstance(page.get("tweets"), list)
        or not all(isinstance(tweet, dict) and tweet.get("id") for tweet in page["tweets"])
        or not isinstance(page.get("has_more"), bool)
        or (page.get("next_cursor") is not None and not isinstance(page["next_cursor"], str))
    ):
        raise InvalidCliOutputError("Twitter returned an invalid feed page")
    next_cursor = page.get("next_cursor")
    if not next_cursor or next_cursor == cursor:
        page.update(next_cursor=None, has_more=False)
    return page
