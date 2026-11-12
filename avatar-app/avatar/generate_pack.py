"""Draws the default avatar pack (the Claude pixel mascot, all states) deterministically.

    python -m avatar.generate_pack          -> packs/default/ and assets/contact_sheet.png

Pixel grid of 20x20 cells at 10 px per cell (200x200 PNGs). Mascot geometry (a pixel-art homage to Claude Code's mascot):
body 12x8 cells, arms 2 cells out on each side, two 1x2 eye slits, four 1x2 legs in two pairs.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

from .states import STATES

GRID, CELL = 20, 10
BODY = (216, 119, 86)                 # the orange of the Claude Code mascot
_BODY, DARK = (*BODY, 255), (9, 9, 11, 255)
YELLOW, RED, GREEN, WHITE = (255, 200, 40, 255), (220, 60, 60, 255), (80, 180, 100, 255), (240, 240, 240, 255)
ROOT = Path(__file__).resolve().parent.parent

EXCLAIM = ["XX", "XX", "XX", "XX", "..", "XX"]
QUESTION = [".XX.", "X..X", "...X", "..X.", "....", "..X."]
CHECK = ["......X", ".....XX", "X...XX.", "XX.XX..", ".XXX...", "..X...."]
X_EYE = ["X.X", ".X.", "X.X"]
HAPPY_EYE = [".X.", "X.X"]
CONFETTI = [(2, 1, YELLOW), (5, 3, RED), (15, 2, GREEN), (17, 5, WHITE), (8, 0, GREEN), (12, 4, YELLOW),
            (1, 6, WHITE), (18, 2, RED)]


def _rect(d, x, y, w, h, color):
    d.rectangle([x, y, x + w - 1, y + h - 1], fill=color)


def _bitmap(d, rows, x, y, color):
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch == "X":
                d.point((x + i, y + j), fill=color)


def _extra(d, name):
    if name == "excl":
        _bitmap(d, EXCLAIM, 9, 0, YELLOW)
    elif name == "excl_red":
        _bitmap(d, EXCLAIM, 9, 0, RED)
    elif name == "question":
        _bitmap(d, QUESTION, 8, 0, WHITE)
    elif name == "check":
        _bitmap(d, CHECK, 7, 0, GREEN)
    elif name.startswith("dots"):
        for k in range(int(name[4:])):
            _rect(d, 6 + 3 * k, 3, 2, 2, WHITE)
    elif name.startswith("confetti"):
        shift = int(name[8:]) - 1
        for x, y, c in CONFETTI:
            d.point((x, y + shift), fill=c)


def _mascot(d, dy=0, dx=0, arms="down", legs="both", eyes="slit", blink=False, talk=False):
    bx, by = 4 + dx, 7 + dy
    _rect(d, bx, by, 12, 8, _BODY)
    left_up = arms in ("up", "swing_l")
    right_up = arms in ("up", "swing_r")
    _rect(d, bx - 2, by + (2 if left_up else 4), 2, 2, _BODY)
    _rect(d, bx + 12, by + (2 if right_up else 4), 2, 2, _BODY)
    heights = {"both": (2, 2, 2, 2), "ab": (2, 2, 1, 1), "ba": (1, 1, 2, 2)}[legs]
    for col, h in zip((1, 3, 8, 10), heights):
        _rect(d, bx + col, by + 8, 1, h, _BODY)
    kind = {"slit": "shut", "up": "shutu", "happy": "flat"}.get(eyes, eyes) if blink else eyes
    for ex in (bx + 2, bx + 9):
        if kind == "slit":
            _rect(d, ex, by + 2, 1, 2, DARK)
        elif kind == "up":
            _rect(d, ex, by + 1, 1, 2, DARK)
        elif kind == "shut":
            _rect(d, ex, by + 3, 1, 1, DARK)
        elif kind == "shutu":
            _rect(d, ex, by + 2, 1, 1, DARK)
        elif kind == "x":
            _bitmap(d, X_EYE, ex - 1, by + 2, DARK)
        elif kind == "happy":
            _bitmap(d, HAPPY_EYE, ex - 1, by + 2, DARK)
        elif kind == "flat":
            _rect(d, ex - 1, by + 3, 3, 1, DARK)
    if talk:
        _rect(d, bx + 4, by + 5, 4, 1, DARK)


# frames per state: kwargs for _mascot plus an optional "extra" symbol
POSES: dict[str, list[dict]] = {
    "idle": [{}, {"dy": 1}],
    "thinking": [{"eyes": "up", "extra": f"dots{n}"} for n in (1, 2, 3)],
    "working": [{"arms": "swing_l", "legs": "ab"}, {"arms": "swing_r", "legs": "ba"}],
    "attention": [{"arms": "up", "extra": "excl"}, {"arms": "up", "dy": -1, "extra": "excl"}],
    "celebrating": [{"dy": -2, "arms": "up", "extra": "confetti1"}, {"dy": -1, "arms": "up", "extra": "confetti2"}],
    "error": [{"eyes": "x", "extra": "excl_red"}],
    "waiting": [{"extra": "question"}],
    "done": [{"eyes": "happy", "extra": "check"}],
}
BLINKS = {"slit", "up", "happy"}          # eye kinds that have a blink version


def _render(pose: dict, talk: bool, blink: bool, cell: int) -> Image.Image:
    img = Image.new("RGBA", (GRID, GRID), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    kwargs = {k: v for k, v in pose.items() if k != "extra"}
    _mascot(d, talk=talk, blink=blink, **kwargs)
    if "extra" in pose:
        _extra(d, pose["extra"])
    return img.resize((GRID * cell, GRID * cell), Image.NEAREST)


def generate_pack(out: Path, cell: int = CELL) -> None:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "avatar.json").write_text(json.dumps(
        {"name": "Claude mascot", "fps": 8, "blink_min": 3.0, "blink_max": 6.0, "blink_ms": 120}, indent=2), encoding="utf-8")
    for state in STATES:
        for n, pose in enumerate(POSES[state], start=1):
            stem = state if n == 1 else f"{state}_{n}"
            for talk in (False, True):
                for blink in (False, True):
                    if blink and pose.get("eyes", "slit") not in BLINKS:
                        continue
                    name = stem + ("_talk" if talk else "") + ("_blink" if blink else "") + ".png"
                    _render(pose, talk, blink, cell).save(out / name)


def contact_sheet(pack_dir: Path, out: Path, size: int = 200) -> None:
    """All base images, plus idle talking and idle blinking, on a dark background (for a human to look at)."""
    names = [f"{s}.png" for s in STATES] + ["idle_talk.png", "idle_blink.png"]
    sheet = Image.new("RGBA", (size * 5, size * 2), DARK)
    for i, n in enumerate(names):
        im = Image.open(Path(pack_dir) / n).resize((size, size), Image.NEAREST)
        sheet.alpha_composite(im, ((i % 5) * size, (i // 5) * size))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


if __name__ == "__main__":
    generate_pack(ROOT / "packs" / "default")
    contact_sheet(ROOT / "packs" / "default", ROOT / "assets" / "contact_sheet.png")
    print("wrote", ROOT / "packs" / "default", file=sys.stderr)
