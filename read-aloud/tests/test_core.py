import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

import core

CURLY = "’"


# ---------- clean_text ----------
def test_code_blocks_are_skipped_not_read():
    out = core.clean_text("Before\n```python\nprint('x')\n```\nAfter")
    assert "print" not in out and "code block" in out.lower()
    assert out.startswith("Before") and out.endswith("After")


def test_markdown_symbols_links_and_urls_are_cleaned():
    md = "## Title\n- **bold** item with `inline` code and [a link](https://x.io/page)\nSee https://example.com/a/b now"
    out = core.clean_text(md)
    assert out == "Title bold item with inline code and a link See link now"


def test_tables_are_dropped_and_curly_quotes_are_kept():
    out = core.clean_text(f"| a | b |\n|---|---|\n| 1 | 2 |\nIt{CURLY}s fine")
    assert out == f"It{CURLY}s fine"


# ---------- limit_text / split_chunks ----------
def test_limit_text_cuts_at_a_sentence_and_says_so():
    text = "One sentence here. " * 100
    out = core.limit_text(text, 200)
    assert len(out) <= 260 and "truncated" in out.lower()
    assert core.limit_text("short", 200) == "short"


def test_split_chunks_keeps_all_words_and_starts_small():
    text = " ".join(f"Sentence number {i} is here." for i in range(60))
    chunks = core.split_chunks(text, first=100, rest=300)
    assert len(chunks[0]) <= 100 and all(len(c) <= 300 for c in chunks)
    assert " ".join(chunks).split() == text.split()


def test_split_chunks_handles_one_giant_sentence():
    text = "word " * 500
    chunks = core.split_chunks(text, first=100, rest=300)
    assert all(len(c) <= 300 for c in chunks) and " ".join(chunks).split() == text.split()


# ---------- transcript reading ----------
def _write(path: Path, entries: list[dict]) -> Path:
    path.write_text("\n".join(json.dumps(e) for e in entries), encoding="utf-8")
    return path


def _a(*blocks):
    return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}}


def _u(content):
    return {"type": "user", "message": {"role": "user", "content": content}}


def test_last_reply_is_the_text_after_the_last_tool_result(tmp_path):
    t = _write(tmp_path / "t.jsonl", [
        _u("do it"),
        _a({"type": "text", "text": "Narration before tool"}, {"type": "tool_use", "id": "1", "name": "Bash", "input": {}}),
        _u([{"type": "tool_result", "tool_use_id": "1", "content": "ok"}]),
        _a({"type": "thinking", "thinking": "secret"}),
        _a({"type": "text", "text": "Final answer part one."}),
        _a({"type": "text", "text": "Part two."}),
    ])
    assert core.last_reply(t) == "Final answer part one. Part two."


def test_last_reply_is_empty_when_the_turn_ends_with_a_tool_call(tmp_path):
    t = _write(tmp_path / "t.jsonl", [_u("hi"), _a({"type": "tool_use", "id": "1", "name": "Bash", "input": {}})])
    assert core.last_reply(t) == ""


def test_last_reply_survives_garbage_and_missing_files(tmp_path):
    t = tmp_path / "t.jsonl"
    t.write_text("not json\n" + json.dumps(_a({"type": "text", "text": "ok"})) + "\n{broken", encoding="utf-8")
    assert core.last_reply(t) == "ok"
    assert core.last_reply(tmp_path / "missing.jsonl") == ""


def test_reply_from_hook_prefers_the_message_the_hook_provides(tmp_path):
    t = _write(tmp_path / "t.jsonl", [_a({"type": "text", "text": "from file"})])
    assert core.reply_from_hook({"last_assistant_message": "from hook", "transcript_path": str(t)}) == "from hook"
    assert core.reply_from_hook({"transcript_path": str(t)}) == "from file"
    assert core.reply_from_hook({}) == ""


# ---------- the Windows speech path must never put text inside a command ----------
EVIL = f"hello{CURLY}; Write-Output 'INJECTED'; ‘bye"


def test_sapi_command_never_contains_the_text():
    args, env = core.sapi_command(EVIL, rate=0, voice="")
    assert all("INJECTED" not in a and "hello" not in a for a in args)
    assert env["RA_TEXT"] == EVIL


@pytest.mark.skipif(not core.IS_WIN, reason="PowerShell path is Windows-only")
def test_sapi_script_treats_curly_quotes_as_plain_text():
    args, env = core.sapi_command(EVIL, rate=0, voice="", dry_run=True)
    out = subprocess.run(args, env={**core.os.environ, **env}, capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.stdout.strip() == EVIL


# ---------- local-only URL ----------
@pytest.mark.parametrize("url", ["http://127.0.0.1:3900", "http://localhost:3900/", "http://[::1]:3900"])
def test_loopback_urls_are_accepted(url):
    assert core.check_loopback(url).startswith("http://")


@pytest.mark.parametrize("url", ["https://example.com", "http://127.0.0.1.evil.com", "http://192.168.1.5:3900", "http://0.0.0.0:3900", "ftp://127.0.0.1"])
def test_other_urls_are_refused(url):
    with pytest.raises(ValueError):
        core.check_loopback(url)


# ---------- Voice Studio client against a fake local server ----------
class _Fake(BaseHTTPRequestHandler):
    seen: list = []
    fail = 0

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _Fake.seen.append(body)
        if _Fake.fail:
            _Fake.fail -= 1
            self.send_response(503); self.end_headers(); self.wfile.write(b"starting"); return
        self.send_response(200); self.send_header("Content-Type", "audio/wav"); self.end_headers(); self.wfile.write(b"RIFFfake")

    def do_GET(self):
        self.send_response(200); self.end_headers(); self.wfile.write(b"[]")


@pytest.fixture
def fake_server():
    _Fake.seen, _Fake.fail = [], 0
    srv = HTTPServer(("127.0.0.1", 0), _Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def test_synth_sends_the_text_as_json_and_returns_audio(fake_server):
    cfg = {**core.DEFAULTS, "voicestudio_url": fake_server, "voice": "ash"}
    assert core.synth_voicestudio(f"Don{CURLY}t panic", cfg) == b"RIFFfake"
    assert _Fake.seen == [{"model": "tts-1", "voice": "ash", "input": f"Don{CURLY}t panic", "response_format": "wav", "speed": 1.0}]


def test_synth_retries_while_the_app_is_still_starting(fake_server):
    _Fake.fail = 2
    cfg = {**core.DEFAULTS, "voicestudio_url": fake_server}
    assert core.synth_voicestudio("hi", cfg, retries=3, wait=0.01) == b"RIFFfake"


def test_synth_raises_unavailable_when_nothing_listens():
    cfg = {**core.DEFAULTS, "voicestudio_url": "http://127.0.0.1:9"}
    with pytest.raises(core.Unavailable):
        core.synth_voicestudio("hi", cfg, retries=1, wait=0.01)


# ---------- the speaking pipeline, with fakes for sound ----------
def test_chunks_play_in_order_and_synthesis_runs_ahead():
    played, made = [], []

    def synth(chunk, cfg):
        made.append(chunk); return chunk.encode()

    core.speak("First sentence. Second sentence. Third sentence.", {**core.DEFAULTS, "first_chunk": 10, "chunk": 20},
               synth=synth, play=lambda wav: played.append(wav.decode()), sapi=lambda t, c: pytest.fail("fallback not expected"))
    assert [p for p in played] == made and " ".join(played).split() == "First sentence. Second sentence. Third sentence.".split()


def test_falls_back_to_the_windows_voice_when_voice_studio_is_down():
    spoken = []

    def synth(chunk, cfg):
        raise core.Unavailable("down")

    core.speak("Hello there. Another one.", core.DEFAULTS, synth=synth, play=lambda w: pytest.fail("no audio expected"),
               sapi=lambda text, cfg: spoken.append(text))
    assert " ".join(spoken).split() == "Hello there. Another one.".split()


# ---------- the speaking flag the avatar window reads ----------
def _wav(seconds: float, rate: int = 24000) -> bytes:
    import io
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * seconds))
    return buf.getvalue()


def _flag():
    return json.loads((core.STATE_DIR / "speaking.json").read_text(encoding="utf-8"))


def test_wav_seconds_reads_the_header_and_falls_back_for_junk():
    assert abs(core.wav_seconds(_wav(1.0)) - 1.0) < 0.05
    assert core.wav_seconds(b"junk") == len(b"junk") / 48000


def test_speak_raises_the_flag_while_audio_plays_and_lowers_it_after():
    import time
    seen = []
    core.speak("Hello there.", core.DEFAULTS, synth=lambda c, cfg: _wav(1.0),
               play=lambda wav: seen.append(_flag()), sapi=lambda t, c: pytest.fail("no fallback expected"))
    assert seen[0]["speaking"] is True and 0.7 < seen[0]["until"] - time.time() < 1.3
    assert _flag()["speaking"] is False


def test_windows_voice_path_also_raises_the_flag():
    import time
    seen = []
    cfg = {**core.DEFAULTS, "engine": "windows"}
    core.speak("Fourteen chars", cfg, sapi=lambda t, c: seen.append(_flag()))
    assert seen[0]["speaking"] is True and 0.3 < seen[0]["until"] - time.time() < 1.6
    assert _flag()["speaking"] is False


def test_flag_is_lowered_even_when_playing_fails():
    def boom(wav):
        raise OSError("sound device gone")

    with pytest.raises(OSError):
        core.speak("Hello there.", core.DEFAULTS, synth=lambda c, cfg: _wav(0.2), play=boom, sapi=lambda t, c: None)
    assert _flag()["speaking"] is False


def test_stop_reading_lowers_the_flag():
    core.write_speaking(True, 60.0)
    core.stop_reading()
    assert _flag()["speaking"] is False
