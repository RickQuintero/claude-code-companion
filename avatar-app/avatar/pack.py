"""Avatar packs: a folder of same-size PNGs plus an optional avatar.json.

Image names:  <state>[_<n>][_talk][_blink].png   (n starts at 2; <state>.png is frame 1)
Required:     the 8 base images <state>.png. Everything else is optional and falls back gracefully.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .states import STATES


class PackError(Exception):
    pass


@dataclass
class Pack:
    folder: Path
    name: str = ""
    fps: float = 8.0
    blink_min: float = 3.0
    blink_max: float = 6.0
    blink_ms: int = 120
    width: int | None = None              # suggested window width in px when this pack is chosen
    files: frozenset = field(default_factory=frozenset)

    def frame_count(self, state: str) -> int:
        n = 1
        while f"{state}_{n + 1}.png" in self.files:
            n += 1
        return n

    def image(self, state: str, frame: int, talk: bool, blink: bool) -> Path:
        """Best matching PNG. `frame` is a 0-based counter that wraps. Blink is dropped first, then talk."""
        number = frame % self.frame_count(state) + 1
        stem = state if number == 1 else f"{state}_{number}"
        variants = [(talk, blink), (talk, False), (False, blink), (False, False)] if talk or blink else [(False, False)]
        for t, b in variants:
            name = stem + ("_talk" if t else "") + ("_blink" if b else "") + ".png"
            if name in self.files:
                return self.folder / name
        return self.folder / f"{state}.png"


def _number(data: dict, key: str, default: float, minimum: float) -> float:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < minimum:
        raise PackError(f"avatar.json: '{key}' must be a number >= {minimum}")
    return float(value)


def load_pack(folder: Path) -> Pack:
    folder = Path(folder)
    if not folder.is_dir():
        raise PackError(f"pack folder not found: {folder}")
    files = frozenset(p.name for p in folder.glob("*.png"))
    missing = [s for s in STATES if f"{s}.png" not in files]
    if missing:
        raise PackError(f"pack {folder.name} is missing required images: {', '.join(m + '.png' for m in missing)}")
    data: dict = {}
    meta = folder / "avatar.json"
    if meta.exists():
        try:
            data = json.loads(meta.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as e:
            raise PackError(f"avatar.json is not valid JSON: {e}") from e
        if not isinstance(data, dict):
            raise PackError("avatar.json must contain a JSON object")
    width = data.get("width")
    if width is not None and (isinstance(width, bool) or not isinstance(width, int) or not 64 <= width <= 600):
        raise PackError("avatar.json: 'width' must be a whole number from 64 to 600")
    pack = Pack(folder=folder, name=str(data.get("name") or folder.name), files=files, width=width,
                fps=_number(data, "fps", 8.0, 0.1), blink_min=_number(data, "blink_min", 3.0, 0.0),
                blink_max=_number(data, "blink_max", 6.0, 0.0), blink_ms=int(_number(data, "blink_ms", 120, 1)))
    if pack.blink_max < pack.blink_min:
        raise PackError("avatar.json: blink_max must be >= blink_min")
    return pack


def discover_packs(packs_dir: Path) -> list[Pack]:
    """Every usable pack folder inside packs_dir, sorted by name. Broken ones are skipped."""
    found = []
    folders = sorted(p for p in Path(packs_dir).iterdir() if p.is_dir()) if Path(packs_dir).is_dir() else []
    for folder in folders:
        try:
            found.append(load_pack(folder))
        except PackError:
            continue
    return sorted(found, key=lambda p: p.name.lower())


def load_pack_or_default(folder: Path | None, default: Path) -> tuple[Pack, str | None]:
    """The chosen pack, or the bundled default plus a message when the chosen one is unusable."""
    if folder is not None:
        try:
            return load_pack(folder), None
        except PackError as e:
            return load_pack(default), str(e)
    return load_pack(default), None
