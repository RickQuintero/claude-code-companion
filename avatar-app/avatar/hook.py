"""Claude Code hook: turns a hook event into a state word in state/avatar.json.

Safety: reads only the event name and notification type from the hook JSON (never message text),
never prints, never raises, always exits 0. Run as:  python avatar\\hook.py   (JSON on stdin)
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

if __package__ in (None, ""):                      # started as a plain script by Claude
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from avatar.statefile import write_state
from avatar.states import state_for_event

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "state" / "avatar.json"
MAX_STDIN = 1024 * 1024
_CREATE_NO_WINDOW = 0x08000000
_NEW_PROCESS_GROUP = 0x00000200


def launch_app() -> None:
    """Start the avatar window detached. A second copy exits on its own (lock file in the app)."""
    exe = Path(sys.executable).with_name("pythonw.exe")           # same venv as this hook, but no console window
    if not exe.exists():
        exe = Path(sys.executable)
    subprocess.Popen([str(exe), "-m", "avatar.app"], cwd=str(ROOT), stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=_CREATE_NO_WINDOW | _NEW_PROCESS_GROUP)


def main(stdin, state_path: Path | None = None, now: float | None = None, launch=None) -> int:
    try:
        try:
            payload = json.loads(stdin.read(MAX_STDIN).lstrip("﻿"))
        except ValueError:
            return 0
        event = payload.get("hook_event_name") if isinstance(payload, dict) else None
        mapped = state_for_event(
            {"hook_event_name": event, "notification_type": payload.get("notification_type")}
            if isinstance(payload, dict) else None)
        if mapped is None:
            return 0
        state, after = mapped
        write_state(state_path or STATE_PATH, state, after, time.time() if now is None else now)
        if event == "SessionStart":
            (launch or launch_app)()
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    import io
    sys.exit(main(io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")))
