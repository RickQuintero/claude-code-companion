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
