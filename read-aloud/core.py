"""Read-aloud engine: turn Claude's last reply into speech, safely and locally.

Voices: Voice Studio's local API (http://127.0.0.1:3900) when it is running, else the Windows system voice.
Safety rules this file keeps: the reply text is never placed inside a command line or script string (it travels
as JSON to the local API, or in an environment variable to a fixed PowerShell script); only loopback URLs are used.
"""
from __future__ import annotations

import io
import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path

IS_WIN = sys.platform == "win32"
HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"
STATE_DIR = HERE / "state"
CREATE_NO_WINDOW = 0x08000000

DEFAULTS = {
    "enabled": False,            # read every reply automatically
    "engine": "auto",            # auto = Voice Studio if it answers, else the Windows voice; "windows" = Windows voice only
    "voicestudio_url": "http://127.0.0.1:3900",
    "voice": "alloy",            # one of Voice Studio's voices (see: read_aloud.py voices)
    "speed": 1.0,
    "sapi_voice": "",            # exact Windows voice name, empty = default
    "sapi_rate": 0,              # -10 .. 10
    "max_chars": 6000,
    "first_chunk": 160,          # a small first piece so speech starts quickly
    "chunk": 420,
}


class Unavailable(RuntimeError):
    """The Voice Studio API cannot speak right now."""


# ------------------------------------------------------------------ config
def load_config(path: Path | None = None) -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads((path or CONFIG_PATH).read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg: dict, path: Path | None = None) -> None:
    (path or CONFIG_PATH).write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ text
_PLACEHOLDER = "(code block skipped)"


def clean_text(md: str) -> str:
    s = re.sub(r"```.*?```", f" {_PLACEHOLDER} ", md, flags=re.S)
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"^\s*\|.*\|\s*$", " ", s, flags=re.M)
    s = re.sub(r"^[ \t]*[-*+]\s+", "", s, flags=re.M)
    s = re.sub(r"^[ \t]*#{1,6}\s*", "", s, flags=re.M)
    s = re.sub(r"https?://\S+", " link ", s)
    s = re.sub(r"[*>]+", "", s)
    s = re.sub(r"(?<!\w)_+|_+(?!\w)", "", s)
    return re.sub(r"\s+", " ", s).strip()


def has_words(text: str) -> bool:
    return len(re.sub(re.escape(_PLACEHOLDER), "", text).strip(" .,;:!?-")) >= 2


def limit_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    ends = [m.end() for m in re.finditer(r"[.!?](?=\s)", cut)]
    if ends and ends[-1] > max_chars // 2:
        cut = cut[: ends[-1]]
    return cut.strip() + " (Reply truncated.)"


def _split_words(sentence: str, limit: int) -> list[str]:
    out, cur = [], ""
    for word in sentence.split():
        if cur and len(cur) + 1 + len(word) > limit:
            out.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    return out + ([cur] if cur else [])


def split_chunks(text: str, first: int = 160, rest: int = 420) -> list[str]:
    chunks, cur = [], ""
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        if not sentence:
            continue
        limit = first if not chunks else rest
        for piece in ([sentence] if len(sentence) <= limit else _split_words(sentence, limit)):
            limit = first if not chunks else rest
            if cur and len(cur) + 1 + len(piece) > limit:
                chunks.append(cur)
                cur = piece
            else:
                cur = f"{cur} {piece}".strip()
    return chunks + ([cur] if cur else [])


# ------------------------------------------------------------------ transcript
def last_reply(transcript: Path) -> str:
    """The text Claude wrote after the last tool result (or the last user message)."""
    try:
        lines = Path(transcript).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    parts: list[str] = []
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        if entry.get("type") == "user":
            break
        if entry.get("type") != "assistant":
            continue
        content = (entry.get("message") or {}).get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            if texts:
                parts.append(" ".join(texts))
    return " ".join(reversed(parts)).strip()


def reply_from_hook(payload: dict) -> str:
    message = payload.get("last_assistant_message")
    if isinstance(message, str) and message.strip():
        return message
    path = payload.get("transcript_path")
    return last_reply(Path(path)) if isinstance(path, str) and path else ""


# ------------------------------------------------------------------ local-only URL
def check_loopback(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError(f"only a local http address is allowed, not {url!r}")
    return f"http://{parsed.netloc}"


# ------------------------------------------------------------------ Voice Studio
def synth_voicestudio(text: str, cfg: dict, timeout: float = 120, retries: int = 30, wait: float = 2.0) -> bytes:
    base = check_loopback(cfg["voicestudio_url"])
    body = json.dumps({"model": "tts-1", "voice": cfg["voice"], "input": text,
                       "response_format": "wav", "speed": float(cfg["speed"])}).encode("utf-8")
    req = urllib.request.Request(base + "/v1/audio/speech", data=body, headers={"Content-Type": "application/json"})
    for attempt in range(max(1, retries)):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 503 and attempt + 1 < retries:   # "still starting"
                time.sleep(wait)
                continue
            raise Unavailable(f"Voice Studio answered {exc.code}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise Unavailable(f"Voice Studio is not reachable: {exc}") from exc
    raise Unavailable("Voice Studio did not become ready")


def play_wav(wav: bytes) -> None:
    import winsound
    fd, name = tempfile.mkstemp(suffix=".wav", dir=_tmp_dir())
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(wav)
        winsound.PlaySound(name, winsound.SND_FILENAME)
    finally:
        Path(name).unlink(missing_ok=True)


# ------------------------------------------------------------------ Windows voice (fixed script, text via environment)
_SAPI_SCRIPT = (
    "$ErrorActionPreference='Stop';[Console]::OutputEncoding=[Text.Encoding]::UTF8;"
    "if($env:RA_DRYRUN){Write-Output $env:RA_TEXT;exit 0};"
    "Add-Type -AssemblyName System.Speech;"
    "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
    "if($env:RA_VOICE){try{$s.SelectVoice($env:RA_VOICE)}catch{}};"   # unknown name -> default voice, never silence
    "$s.Rate=[int]$env:RA_RATE;"
    "$s.Speak($env:RA_TEXT)"
)


def sapi_command(text: str, rate: int, voice: str, dry_run: bool = False) -> tuple[list[str], dict]:
    args = ["powershell", "-NoProfile", "-NonInteractive", "-Command", _SAPI_SCRIPT]
    env = {"RA_TEXT": text, "RA_RATE": str(int(rate)), "RA_VOICE": voice}
    if dry_run:
        env["RA_DRYRUN"] = "1"
    return args, env


def speak_sapi(text: str, cfg: dict) -> None:
    args, env = sapi_command(text, cfg["sapi_rate"], cfg["sapi_voice"])
    subprocess.run(args, env={**os.environ, **env}, capture_output=True, timeout=600,
                   creationflags=CREATE_NO_WINDOW if IS_WIN else 0)


# ------------------------------------------------------------------ "I am speaking" flag (read by the avatar window)
def wav_seconds(wav: bytes) -> float:
    try:
        with wave.open(io.BytesIO(wav), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except (wave.Error, EOFError, ZeroDivisionError):
        return len(wav) / 48000


def write_speaking(speaking: bool, duration: float = 0.0) -> None:
    """Best effort. `until` lets a reader ignore a stale 'true' if this process is killed mid-sentence."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        (STATE_DIR / "speaking.json").write_text(
            json.dumps({"speaking": bool(speaking), "until": time.time() + duration}), encoding="utf-8")
    except OSError:
        pass


# ------------------------------------------------------------------ the pipeline
def speak(text: str, cfg: dict, synth=None, play=None, sapi=None) -> None:
    synth, play, sapi = synth or synth_voicestudio, play or play_wav, sapi or speak_sapi
    chunks = split_chunks(text, cfg["first_chunk"], cfg["chunk"])

    def say_windows(chunk: str) -> None:
        write_speaking(True, len(chunk) / 14 + 0.3)     # rough: about 14 characters per second plus startup
        sapi(chunk, cfg)

    try:
        if cfg["engine"] == "windows":
            for chunk in chunks:
                say_windows(chunk)
            return
        ready: queue.Queue = queue.Queue(maxsize=2)

        def producer() -> None:
            for chunk in chunks:
                try:
                    ready.put((chunk, synth(chunk, cfg)))
                except Unavailable:
                    ready.put((chunk, None))   # play this and the rest with the Windows voice
            ready.put(None)

        threading.Thread(target=producer, daemon=True).start()
        while (item := ready.get()) is not None:
            chunk, wav = item
            if wav is None:
                say_windows(chunk)
            else:
                write_speaking(True, wav_seconds(wav) + 0.2)
                play(wav)
    finally:
        write_speaking(False)


# ------------------------------------------------------------------ one reading at a time
def _tmp_dir() -> Path:
    d = STATE_DIR / "tmp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_event(message: str) -> None:
    """One line in state/hook.log so a silent failure can be explained later. Never put reply text in `message`."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        path = STATE_DIR / "hook.log"
        if path.exists() and path.stat().st_size > 64 * 1024:                  # keep it small: drop the older half
            path.write_text(path.read_text(encoding="utf-8", errors="replace")[-32 * 1024:], encoding="utf-8")
        with path.open("a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass


def prune_tmp(max_age: float = 3600.0) -> None:
    """Remove temp text files that a worker never picked up (for example a hook that was killed half way)."""
    try:
        for f in _tmp_dir().iterdir():
            if f.is_file() and time.time() - f.stat().st_mtime > max_age:
                f.unlink(missing_ok=True)
    except OSError:
        pass


def _pid_file() -> Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    return STATE_DIR / "worker.pid"


def stop_reading(keep_pid: int | None = None) -> None:
    if keep_pid is None:
        write_speaking(False)
    try:
        pid = int(_pid_file().read_text())
    except (OSError, ValueError):
        return
    if pid != keep_pid and IS_WIN:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, creationflags=CREATE_NO_WINDOW)
    if keep_pid is None:
        _pid_file().unlink(missing_ok=True)


def claim_reading() -> None:
    stop_reading(keep_pid=os.getpid())
    _pid_file().write_text(str(os.getpid()))


def release_reading() -> None:
    try:
        if int(_pid_file().read_text()) == os.getpid():
            _pid_file().unlink(missing_ok=True)
    except (OSError, ValueError):
        pass
