"""Control the read-aloud hook.

    python read_aloud.py on | off          read every reply automatically (or not)
    python read_aloud.py stop              stop talking right now
    python read_aloud.py say "some text"   speak a sentence (test)
    python read_aloud.py voices            list Voice Studio's voices
    python read_aloud.py voice <name>      pick a Voice Studio voice (e.g. alloy, ash, coral)
    python read_aloud.py engine auto|windows
    python read_aloud.py speed 1.2
    python read_aloud.py status
"""
import json
import sys
import urllib.request

import core


def main(argv: list[str]) -> int:
    cfg = core.load_config()
    cmd = argv[1] if len(argv) > 1 else "status"
    arg = " ".join(argv[2:])
    if cmd in ("on", "off"):
        cfg["enabled"] = cmd == "on"
        core.save_config(cfg)
        print(f"Read aloud is {cmd.upper()}.")
    elif cmd == "stop":
        core.stop_reading()
        print("Stopped.")
    elif cmd == "say":
        core.speak(core.clean_text(arg), cfg)
    elif cmd == "voices":
        base = core.check_loopback(cfg["voicestudio_url"])
        with urllib.request.urlopen(base + "/v1/audio/voices", timeout=30) as r:
            data = json.load(r)
        for v in (data.get("voices", data) if isinstance(data, dict) else data):
            print(f"  {v.get('voice_id')}  ({v.get('type')})")
    elif cmd in ("voice", "engine", "speed") and arg:
        key = {"voice": "voice", "engine": "engine", "speed": "speed"}[cmd]
        cfg[key] = float(arg) if cmd == "speed" else arg
        core.save_config(cfg)
        print(f"{key} = {cfg[key]}")
    else:
        for k in ("enabled", "engine", "voice", "speed", "voicestudio_url", "max_chars"):
            print(f"  {k}: {cfg[k]}")
        print(f"  config file: {core.CONFIG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
