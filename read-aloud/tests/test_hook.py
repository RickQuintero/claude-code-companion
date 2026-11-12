import io
import json
from pathlib import Path

import core
import speak_hook


def _transcript(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "t.jsonl"
    p.write_text(json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": text}]}}), encoding="utf-8")
    return p


def _run(payload, cfg, spawned):
    return speak_hook.main(io.StringIO(json.dumps(payload) if not isinstance(payload, str) else payload), cfg=cfg,
                           spawn=lambda path: spawned.append(Path(path).read_text(encoding="utf-8")))


def test_does_nothing_when_switched_off(tmp_path):
    spawned = []
    assert _run({"transcript_path": str(_transcript(tmp_path, "Hello there.")) }, {**core.DEFAULTS, "enabled": False}, spawned) == 0
    assert spawned == []


def test_hands_the_cleaned_reply_to_a_worker_when_on(tmp_path):
    spawned = []
    text = "## Done\nHere is `code`:\n```py\nx=1\n```\nAll good."
    assert _run({"transcript_path": str(_transcript(tmp_path, text))}, {**core.DEFAULTS, "enabled": True}, spawned) == 0
    assert len(spawned) == 1 and "x=1" not in spawned[0] and spawned[0].startswith("Done Here is code")


def test_never_fails_on_bad_input_and_skips_empty_replies(tmp_path):
    spawned = []
    on = {**core.DEFAULTS, "enabled": True}
    assert _run("{{{ not json", on, spawned) == 0
    assert _run({}, on, spawned) == 0
    assert _run({"transcript_path": str(_transcript(tmp_path, "```\nonly code\n```"))}, on, spawned) == 0
    assert all("only code" not in s for s in spawned)


def test_long_replies_are_capped(tmp_path):
    spawned = []
    _run({"transcript_path": str(_transcript(tmp_path, "A sentence. " * 2000))}, {**core.DEFAULTS, "enabled": True, "max_chars": 300}, spawned)
    assert len(spawned) == 1 and len(spawned[0]) < 400 and "truncated" in spawned[0].lower()


# ---------- a tiny trace of what the hook did (never the reply text), and cleanup of stale files ----------
import os
import time

import pytest


def _log():
    p = core.STATE_DIR / "hook.log"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def test_every_run_leaves_a_one_line_trace_without_the_reply_text():
    spawned = []
    reply = "A very private sentence about my project."
    _run({"last_assistant_message": reply}, {**core.DEFAULTS, "enabled": True}, spawned)
    assert "hook: spawned worker" in _log() and "private" not in _log()
    _run({"last_assistant_message": reply}, {**core.DEFAULTS, "enabled": False}, spawned)
    assert "hook: skipped (off)" in _log()
    _run({"last_assistant_message": "```\nonly code\n```"}, {**core.DEFAULTS, "enabled": True}, spawned)
    assert "hook: skipped (nothing to read)" in _log()


def test_a_failure_is_logged_by_type_only_and_leaves_no_temp_file_behind():
    def boom(path):
        raise OSError("disk full while reading my private reply")

    speak_hook.main(io.StringIO(json.dumps({"last_assistant_message": "Hello there."})),
                    cfg={**core.DEFAULTS, "enabled": True}, spawn=boom)
    assert "hook: error OSError" in _log() and "private" not in _log()
    assert list(core._tmp_dir().glob("*.txt")) == []


def test_stale_temp_files_are_removed_and_fresh_ones_kept():
    d = core._tmp_dir()
    old, fresh = d / "old.txt", d / "fresh.txt"
    old.write_text("")
    fresh.write_text("x")
    os.utime(old, (time.time() - 7200, time.time() - 7200))
    core.prune_tmp(3600)
    assert not old.exists() and fresh.exists()


def test_the_hook_cleans_up_old_leftovers_each_time_it_runs():
    stale = core._tmp_dir() / "stale.txt"
    stale.write_text("")
    os.utime(stale, (time.time() - 7200, time.time() - 7200))
    _run({"last_assistant_message": "Hello there."}, {**core.DEFAULTS, "enabled": True}, [])
    assert not stale.exists()


def test_the_log_stays_small():
    for i in range(3000):
        core.log_event("x" * 60)
    core.log_event("the last line")
    assert (core.STATE_DIR / "hook.log").stat().st_size < 100_000 and "the last line" in _log()


def test_the_worker_logs_start_done_and_errors_by_type(monkeypatch, tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("Hello there.", encoding="utf-8")
    monkeypatch.setattr(core, "speak", lambda text, cfg: None)
    assert speak_hook.worker(str(f)) == 0
    assert "worker: start" in _log() and "worker: done" in _log()
    g = tmp_path / "u.txt"
    g.write_text("Another private reply.", encoding="utf-8")

    def boom(text, cfg):
        raise RuntimeError("secret reply text")

    monkeypatch.setattr(core, "speak", boom)
    speak_hook.worker(str(g))
    assert "worker: error RuntimeError" in _log() and "secret" not in _log() and "private" not in _log()


def test_stdin_is_read_as_utf8_even_with_emoji_and_a_byte_order_mark():
    # Windows reads piped stdin with the legacy code page by default; the gear emoji has a byte that code page cannot decode
    body = json.dumps({"last_assistant_message": "Open the \u2699\ufe0f Settings section, then press Generate."},
                      ensure_ascii=False).encode("utf-8")
    spawned = []
    for raw in (body, b"\xef\xbb\xbf" + body):
        speak_hook.main(speak_hook.open_stdin(io.BytesIO(raw)), cfg={**core.DEFAULTS, "enabled": True},
                        spawn=lambda p: spawned.append(Path(p).read_text(encoding="utf-8")))
    assert len(spawned) == 2 and all("Settings section" in s for s in spawned)
    assert "unreadable input" not in _log()
