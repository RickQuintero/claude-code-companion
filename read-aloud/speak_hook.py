"""Claude Code "Stop" hook: reads Claude's final reply aloud when read-aloud is switched on.

The hook itself returns at once; a detached worker does the speaking so Claude never waits.
    hook mode   (stdin = hook JSON):   python speak_hook.py
    worker mode (internal):            python speak_hook.py --worker <text file>
Always exits 0 and prints nothing, so it can never block or break a Claude session.
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import core


def open_stdin(raw) -> io.TextIOWrapper:
    """Read the hook JSON as UTF-8 (with or without a BOM) whatever code page Windows defaults to.

    Without this, a reply containing an emoji or some accented characters can fail to decode and be skipped silently."""
    return io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace")


def _spawn_worker(text_file: str) -> None:
    flags = (core.CREATE_NO_WINDOW | 0x00000200) if core.IS_WIN else 0   # no window + own process group
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--worker", text_file],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)


def main(stdin, cfg: dict | None = None, spawn=None) -> int:
    name = None
    try:
        cfg = cfg or core.load_config()
        if not cfg["enabled"]:
            core.log_event("hook: skipped (off)")
            return 0
        core.prune_tmp()
        try:
            payload = json.load(stdin)
        except ValueError:
            core.log_event("hook: skipped (unreadable input)")
            return 0
        text = core.clean_text(core.reply_from_hook(payload if isinstance(payload, dict) else {}))
        if not core.has_words(text):
            core.log_event("hook: skipped (nothing to read)")
            return 0
        text = core.limit_text(text, int(cfg["max_chars"]))
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", dir=core._tmp_dir(), delete=False) as f:
            name = f.name
            f.write(text)
        (spawn or _spawn_worker)(name)
        core.log_event(f"hook: spawned worker ({len(text)} chars)")
    except Exception as e:
        core.log_event(f"hook: error {type(e).__name__}")
        if name:
            Path(name).unlink(missing_ok=True)                 # do not leave an unread file behind
    return 0


def worker(text_file: str) -> int:
    core.log_event("worker: start")
    path = Path(text_file)
    try:
        try:
            text = path.read_text(encoding="utf-8")
        finally:
            path.unlink(missing_ok=True)
        core.claim_reading()
        try:
            core.speak(text, core.load_config())
            core.log_event("worker: done")
        finally:
            core.release_reading()
    except Exception as e:
        core.log_event(f"worker: error {type(e).__name__}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        sys.exit(worker(sys.argv[2]))
    sys.exit(main(open_stdin(sys.stdin.buffer)))
