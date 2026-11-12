"""Where the window goes. Pure functions: screen is the available geometry (x, y, w, h), taskbar excluded."""
from __future__ import annotations

CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")


def place(corner: str, screen: tuple[int, int, int, int], size: tuple[int, int], margin: int = 16) -> tuple[int, int]:
    sx, sy, sw, sh = screen
    w, h = size
    left, top = sx + margin, sy + margin
    right, bottom = sx + sw - w - margin, sy + sh - h - margin
    if corner not in CORNERS:
        corner = "bottom-right"
    return (left if "left" in corner else right, top if "top" in corner else bottom)


def clamp(pos: tuple[int, int], screen: tuple[int, int, int, int], size: tuple[int, int]) -> tuple[int, int]:
    """Keep a window of `size` fully inside the screen's available area."""
    sx, sy, sw, sh = screen
    return (min(max(pos[0], sx), sx + sw - size[0]), min(max(pos[1], sy), sy + sh - size[1]))


def anchor_from_position(pos: tuple[int, int], screen: tuple[int, int, int, int], size: tuple[int, int],
                         margin: int = 16) -> tuple[str, tuple[int, int]]:
    """Remember any position as (nearest corner, offset from that corner's spot), so it survives resolution changes."""
    corner = nearest_corner(pos, screen, size)
    bx, by = place(corner, screen, size, margin)
    return corner, (pos[0] - bx, pos[1] - by)


def nearest_corner(pos: tuple[int, int], screen: tuple[int, int, int, int], size: tuple[int, int]) -> str:
    """Which corner the window (top-left at `pos`) is closest to, judged by its centre."""
    sx, sy, sw, sh = screen
    cx, cy = pos[0] + size[0] / 2, pos[1] + size[1] / 2
    return ("top" if cy < sy + sh / 2 else "bottom") + "-" + ("left" if cx < sx + sw / 2 else "right")
