"""The window's own settings (config.json). Anything unreadable or invalid quietly becomes the default."""
from __future__ import annotations

import json
from pathlib import Path

from .placement import CORNERS

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

DEFAULTS: dict = {
    "corner": "bottom-right",
    "width": 160,
    "opacity": 1.0,
    "pack": "packs/default",
    "speaking_file": str(ROOT.parent / "read-aloud" / "state" / "speaking.json"),     # written by the read-aloud hook
    "visible": True,
    "screen": "",                 # name of the monitor the avatar lives on; empty = the primary monitor
    "offset": [0, 0],             # where it was dropped, relative to its corner's usual spot (so any position is kept)
    "hover_radius": 60,           # px of the see-through circle under the mouse; 0 = off
}

_is_int = lambda v: isinstance(v, int) and not isinstance(v, bool)    # noqa: E731

_VALID = {
    "corner": lambda v: v in CORNERS,
    "width": lambda v: isinstance(v, int) and not isinstance(v, bool) and 64 <= v <= 600,
    "opacity": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and 0.2 <= v <= 1.0,
    "pack": lambda v: isinstance(v, str) and v != "",
    "speaking_file": lambda v: isinstance(v, str) and v != "",
    "visible": lambda v: isinstance(v, bool),
    "screen": lambda v: isinstance(v, str),
    "offset": lambda v: isinstance(v, (list, tuple)) and len(v) == 2 and all(_is_int(n) and abs(n) <= 10000 for n in v),
    "hover_radius": lambda v: _is_int(v) and 0 <= v <= 300,
}


def load_config(path: Path | None = None) -> dict:
    cfg = {**DEFAULTS, "offset": list(DEFAULTS["offset"])}               # never share the default list
    try:
        data = json.loads((path or CONFIG_PATH).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return cfg
    if isinstance(data, dict):
        for key, ok in _VALID.items():
            if key in data and ok(data[key]):
                cfg[key] = list(data[key]) if key == "offset" else data[key]
    return cfg


def save_config(cfg: dict, path: Path | None = None) -> None:
    target = path or CONFIG_PATH
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({k: cfg[k] for k in DEFAULTS if k in cfg}, indent=2), encoding="utf-8")
    except OSError:
        pass
