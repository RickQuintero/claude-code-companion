"""Claude Code "Stop" hook: reads Claude's final reply aloud when read-aloud is switched on.

The hook itself returns at once; a detached worker does the speaking so Claude never waits.
    hook mode   (stdin = hook JSON):   python speak_hook.py
    worker mode (internal):            python speak_hook.py --worker <text file>
Always exits 0 and prints nothing, so it can never block or break a Claude session.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import core


def _spawn_worker(text_file: str) -> None:
    flags = (core.CREATE_NO_WINDOW | 0x00000200) if core.IS_WIN else 0   # no window + own process group
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--worker", text_file],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)


def main(stdin, cfg: dict | None = None, spawn=None) -> int:
    try:
        cfg = cfg or core.load_config()
        if not cfg["enabled"]:
            return 0
        try:
            payload = json.load(stdin)
        except ValueError:
            return 0
        text = core.clean_text(core.reply_from_hook(payload if isinstance(payload, dict) else {}))
        if not core.has_words(text):
            return 0
        text = core.limit_text(text, int(cfg["max_chars"]))
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", dir=core._tmp_dir(), delete=False) as f:
            f.write(text)
        (spawn or _spawn_worker)(f.name)
    except Exception:
        pass
    return 0


def worker(text_file: str) -> int:
    path = Path(text_file)
    try:
        text = path.read_text(encoding="utf-8")
    finally:
        path.unlink(missing_ok=True)
    core.claim_reading()
    try:
        core.speak(text, core.load_config())
    except Exception:
        pass
    finally:
        core.release_reading()
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        sys.exit(worker(sys.argv[2]))
    sys.exit(main(sys.stdin))
