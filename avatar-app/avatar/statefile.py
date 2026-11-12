"""Tiny JSON files shared between the hook, the read-aloud worker and the window."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .states import STATES


def write_state(path: Path, state: str, after: str, now: float) -> None:
    """Atomic write: a reader never sees half a file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps({"state": state, "after": after, "ts": now}), encoding="utf-8")
    os.replace(tmp, path)


def _load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def read_state(path: Path) -> dict | None:
    data = _load(path)
    if isinstance(data, dict) and data.get("state") in STATES:
        return data
    return None


def read_speaking(path: Path, now: float) -> bool:
    """True only while the read-aloud worker says it is speaking AND its promised end time has not passed."""
    data = _load(path)
    if not isinstance(data, dict) or data.get("speaking") is not True:
        return False
    until = data.get("until")
    return isinstance(until, (int, float)) and now < until
