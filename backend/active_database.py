import json
import os
import re
from pathlib import Path


SESSIONS_DIR = Path(__file__).resolve().parent / "runtime" / "sessions"
_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _session_file(session_id: str) -> Path:
    if not session_id or not _SESSION_ID_PATTERN.fullmatch(session_id):
        raise ValueError("Invalid session_id.")
    return SESSIONS_DIR / f"{session_id}.json"


def save_session_database_path(
    session_id: str,
    path: str,
    name: str | None = None,
):
    state_file = _session_file(session_id)
    database_path = str(Path(path).expanduser().resolve())
    state_file.parent.mkdir(parents=True, exist_ok=True)
    temporary_file = state_file.with_suffix(".tmp")
    temporary_file.write_text(
        json.dumps({"path": database_path, "name": name}),
        encoding="utf-8",
    )
    os.replace(temporary_file, state_file)


def get_session_database_path(session_id: str) -> str | None:
    state_file = _session_file(session_id)
    try:
        data = json.loads(state_file.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None

    path = data.get("path")
    return path if isinstance(path, str) and path else None


def clear_session_database_path(session_id: str):
    state_file = _session_file(session_id)
    try:
        state_file.unlink()
    except FileNotFoundError:
        pass
