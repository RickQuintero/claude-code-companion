"""Builds an avatar pack from a small pixel sprite plus a description of its "lights" (eyes).

A sprite is {(col, row): (r, g, b)} for every opaque cell. `Lights` says which cells are eyes (the state lights), which
cells are accents that follow the state colour, and what colour a switched-off eye has. From that this module makes
the 8 states: the eyes take the state colour, look up or down, dim, chase each other or switch off for a blink,
talking enlarges the main eye, the body bobs or swings, and symbols (! ? check, dots, confetti) float on the right.
"""
from __future__ import annotations

import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image

from .generate_pack import CHECK, CONFETTI, EXCLAIM, GREEN, QUESTION, RED, WHITE, YELLOW
from .pixelate import cut_out_background, pixelate
from .states import STATES

OUTLINE = (18, 18, 26)
Cell = tuple[int, int]
Rgb = tuple[int, int, int]
Sprite = dict[Cell, Rgb]


@dataclass
class Lights:
    eyes: list[set[Cell]]                      # eyes[0] is the main (biggest) eye
    socket: Rgb                                # colour of a switched-off eye
    accents: set[Cell] = field(default_factory=set)


@dataclass
class Character:
    name: str
    width: int                                 # suggested window width in px
    tints: dict[str, Rgb | None] = field(default_factory=dict)        # state -> eye colour (missing = native)
    lit: dict[str, str] = field(default_factory=dict)                 # state -> all | main | chase | pairs (many eyes)
    looks: dict[str, tuple[int, int]] = field(default_factory=lambda: {"thinking": (-1, -2), "waiting": (0, 2),
                                                                      "error": (0, 2)})
    pivot: float | None = None                 # swing starts at this fraction of the height; None = drift sideways
    swing_amp: int = 2
    symbol_scale: int = 2
    cell_px: int = 4
    body_motion: bool = True                   # False = the body never moves; only lights and symbols animate


# state -> frames of (motion factor, bob in cells, symbol)
FRAMES: dict[str, list[tuple[int, int, str | None]]] = {
    "idle": [(0, 0, None), (0, -1, None)],
    "thinking": [(0, 0, "dots1"), (0, 0, "dots2"), (0, 0, "dots3")],
    "working": [(-1, 0, None), (1, 0, None)],
    "attention": [(0, 0, "excl"), (0, -1, "excl")],
    "celebrating": [(-1, -2, "confetti1"), (1, 0, "confetti2")],
    "error": [(0, 0, "excl_red"), (0, -1, "excl_red")],
    "waiting": [(0, 0, "question")],
    "done": [(0, 0, "check")],
}


# ---------------------------------------------------------------- small pure helpers
def components(cells: set[Cell]) -> list[set[Cell]]:
    """4-connected groups, largest first (ties broken by position so the result is deterministic)."""
    left, out = set(cells), []
    for start in sorted(cells):
        if start not in left:
            continue
        left.remove(start)
        comp, queue = {start}, deque([start])
        while queue:
            x, y = queue.popleft()
            for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if n in left:
                    left.remove(n)
                    comp.add(n)
                    queue.append(n)
        out.append(comp)
    return sorted(out, key=lambda c: (-len(c), min(c)))


def fill_holes(blob: set[Cell]) -> set[Cell]:
    """The blob plus any cells it fully encloses (the white core inside an iris, say)."""
    xs, ys = [c[0] for c in blob], [c[1] for c in blob]
    x0, x1, y0, y1 = min(xs) - 1, max(xs) + 1, min(ys) - 1, max(ys) + 1
    outside, queue = {(x0, y0)}, deque([(x0, y0)])
    while queue:
        x, y = queue.popleft()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if x0 <= n[0] <= x1 and y0 <= n[1] <= y1 and n not in outside and n not in blob:
                outside.add(n)
                queue.append(n)
    return {(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1) if (x, y) not in outside}


def dilate(cells: set[Cell]) -> set[Cell]:
    return set(cells) | {(x + dx, y + dy) for x, y in cells for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))}


def mix(a: Rgb, b: Rgb, t: float) -> Rgb:
    return tuple(round(a[i] * (1 - t) + b[i] * t) for i in range(3))


def recolor(rgb: Rgb, target: Rgb) -> Rgb:
    """Give a colour the hue of `target` while keeping its brightness; white highlights stay white."""
    hi, lo = max(rgb), min(rgb)
    if hi == 0:
        return rgb
    white = 1 - (hi - lo) / hi
    return tuple(round(target[i] * hi / 255 * (1 - white) + hi * white) for i in range(3))


def shift(cells: Sprite, dx: int, dy: int) -> Sprite:
    return {(x + dx, y + dy): c for (x, y), c in cells.items()}


def swing(cells: Sprite, amp: int, pivot: int, span: int) -> Sprite:
    """Hang from a pivot row: rows above stay, rows below slide sideways by up to `amp` cells."""
    out = {}
    for (x, y), c in cells.items():
        k = max(0.0, min(1.0, (y - pivot) / span)) if span else 0.0
        out[(x + round(amp * k), y)] = c
    return out


# ---------------------------------------------------------------- building the sprite from a picture
def build_sprite(reference: Path, grid_w: int, tolerance: int = 12, crop: tuple | None = None, colors: int = 24,
                 outline=(18, 18, 26, 255)) -> Sprite:
    im = Image.open(reference).convert("RGBA")
    if crop:
        im = im.crop(crop)
    small = pixelate(cut_out_background(im, tolerance), grid_w, colors=colors, outline=outline)
    return {(x, y): small.getpixel((x, y))[:3] for y in range(small.height) for x in range(small.width)
            if small.getpixel((x, y))[3] == 255}


# ---------------------------------------------------------------- frames
def layout(sw: int, sh: int, char: Character) -> tuple[int, int, int, int]:
    """(canvas width, canvas height, sprite origin x, sprite origin y) in cells."""
    ox, oy = char.swing_amp + 2, 3
    symbol_w = 7 * char.symbol_scale + 1
    return ox + sw + char.swing_amp + 1 + symbol_w, oy + sh + 3, ox, oy


def _symbol_cells(name: str, sc: int, x0: int, y0: int) -> Sprite:
    def bitmap(rows, colour):
        return {(x0 + i * sc + a, y0 + j * sc + b): colour[:3] for j, row in enumerate(rows)
                for i, ch in enumerate(row) if ch == "X" for a in range(sc) for b in range(sc)}

    if name == "excl":
        return bitmap(EXCLAIM, YELLOW)
    if name == "excl_red":
        return bitmap(EXCLAIM, RED)
    if name == "question":
        return bitmap(QUESTION, WHITE)
    if name == "check":
        return bitmap(CHECK, GREEN)
    if name.startswith("dots"):
        return {(x0 + 3 * k * sc + a, y0 + 3 * sc + b): WHITE[:3] for k in range(int(name[4:]))
                for a in range(2 * sc) for b in range(2 * sc)}
    if name.startswith("confetti"):
        shift_rows = (int(name[8:]) - 1) * sc
        spots = [(0, 1), (3, 3), (6, 2), (1, 7), (5, 9), (2, 12), (6, 14), (4, 17)]
        return {(x0 + dx * sc + a, y0 + dy * sc + shift_rows + b): CONFETTI[i % len(CONFETTI)][2][:3]
                for i, (dx, dy) in enumerate(spots) for a in range(sc) for b in range(sc)}
    return {}


def _lit_set(mode: str, n_eyes: int, frame: int) -> set[int]:
    if mode == "main":
        return {0}
    if mode == "chase":
        return {i for i in range(n_eyes) if i % 3 == frame % 3}
    if mode == "pairs":
        return {i for i in range(n_eyes) if i % 2 == frame % 2}
    return set(range(n_eyes))


def _frame(sprite: Sprite, lights: Lights, char: Character, state: str, frame: int, talk: bool, blink: bool) -> Image.Image:
    factor, bob, symbol = _frames_for(char, state)[frame]
    tint = char.tints.get(state)
    cells = dict(sprite)
    lit = _lit_set(char.lit.get(state, "all"), len(lights.eyes), frame)
    look = char.looks.get(state, (0, 0)) if len(lights.eyes) == 1 else (0, 0)
    for i, eye in enumerate(lights.eyes):
        moved = {(x + look[0], y + look[1]) for x, y in eye} if look != (0, 0) else set(eye)
        for c in eye:
            cells[c] = lights.socket
        for (x, y), c in zip(sorted(eye), sorted(moved)):
            colour = lights.socket if blink else sprite[(x, y)]
            if not blink:
                colour = recolor(colour, tint) if tint else colour
                if i not in lit:
                    colour = mix(colour, lights.socket, 0.75)
            cells[c] = colour
        if talk and not blink and i == 0:
            glow = mix(recolor(sprite[min(eye)], tint) if tint else sprite[min(eye)], WHITE[:3], 0.35)
            for c in dilate(moved) - moved:
                if c in sprite:
                    cells[c] = glow
    if tint and not blink:
        for c in lights.accents:
            cells[c] = recolor(sprite[c], tint)
    sw = max(x for x, _ in sprite) + 1
    sh = max(y for _, y in sprite) + 1
    if char.pivot is None:
        cells = shift(cells, factor * char.swing_amp, 0)
    else:
        cells = swing(cells, factor * char.swing_amp, round(sh * char.pivot), sh - round(sh * char.pivot))
    cells = shift(cells, 0, bob)
    cw, ch, ox, oy = layout(sw, sh, char)
    cells = shift(cells, ox, oy)
    if symbol:
        sym = _symbol_cells(symbol, char.symbol_scale, ox + sw + char.swing_amp + 1, 1)
        for x, y in sym:                       # a dark outline keeps white symbols visible on light desktops
            for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if n not in sym and n not in cells:
                    cells[n] = OUTLINE
        cells.update(sym)
    img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    for (x, y), rgb in cells.items():
        if 0 <= x < cw and 0 <= y < ch:
            img.putpixel((x, y), (*rgb, 255))
    return img.resize((cw * char.cell_px, ch * char.cell_px), Image.NEAREST)


def _frames_for(char: Character, state: str) -> list[tuple[int, int, str | None]]:
    frames = FRAMES[state]
    mode = char.lit.get(state)
    if not char.body_motion:
        frames = [(0, 0, symbol) for _, _, symbol in frames]
        if mode not in ("chase", "pairs"):               # the lights need their frames; otherwise drop exact repeats
            frames = list(dict.fromkeys(frames))
    if mode == "chase" and len(frames) < 3:
        frames = (frames * 2)[:3]
    return frames


def contact_sheet(pack_dir: Path, out: Path, tile_h: int = 190) -> None:
    """Every base image plus idle talking and blinking, on a dark and on a light background (for a human to look at)."""
    names = [f"{s}.png" for s in STATES] + ["idle_talk.png", "idle_blink.png"]
    first = Image.open(Path(pack_dir) / names[0])
    tw = round(first.width * tile_h / first.height)
    sheet = Image.new("RGBA", (tw * 5, tile_h * 4), (30, 30, 34, 255))
    sheet.paste(Image.new("RGBA", (tw * 5, tile_h * 2), (236, 236, 240, 255)), (0, tile_h * 2))
    for row in (0, 2):
        for i, n in enumerate(names):
            im = Image.open(Path(pack_dir) / n).resize((tw, tile_h), Image.NEAREST)
            sheet.alpha_composite(im, ((i % 5) * tw, (row + i // 5) * tile_h))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)


def generate_character_pack(sprite: Sprite, lights: Lights, char: Character, out: Path) -> None:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "avatar.json").write_text(json.dumps(
        {"name": char.name, "fps": 8, "blink_min": 3.0, "blink_max": 6.0, "blink_ms": 150, "width": char.width},
        indent=2), encoding="utf-8")
    for state in STATES:
        for n in range(len(_frames_for(char, state))):
            stem = state if n == 0 else f"{state}_{n + 1}"
            for talk in (False, True):
                for blink in (False, True):
                    name = stem + ("_talk" if talk else "") + ("_blink" if blink else "") + ".png"
                    _frame(sprite, lights, char, state, n, talk, blink).save(out / name)
