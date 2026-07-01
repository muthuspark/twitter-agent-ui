from pathlib import Path

from dotenv import load_dotenv


def load_environment() -> None:
    backend_root = Path(__file__).resolve().parents[1]
    project_root = backend_root.parent
    load_dotenv(project_root / ".env", override=False)
    load_dotenv(backend_root / ".env", override=False)
