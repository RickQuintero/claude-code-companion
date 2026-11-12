import pytest

from avatar.placement import nearest_corner, place

SCREEN = (0, 0, 1920, 1040)                 # available geometry (taskbar already excluded)
SECOND = (1920, 0, 1920, 1080)              # a monitor to the right of the first
SIZE = (160, 150)


@pytest.mark.parametrize("corner,expected", [
    ("top-left", (16, 16)),
    ("top-right", (1920 - 160 - 16, 16)),
    ("bottom-left", (16, 1040 - 150 - 16)),
    ("bottom-right", (1920 - 160 - 16, 1040 - 150 - 16)),
])
def test_corners_on_the_first_monitor(corner, expected):
    assert place(corner, SCREEN, SIZE) == expected


def test_bottom_right_on_a_monitor_that_does_not_start_at_zero():
    assert place("bottom-right", SECOND, SIZE) == (1920 + 1920 - 160 - 16, 1080 - 150 - 16)


def test_an_unknown_corner_means_bottom_right():
    assert place("middle", SCREEN, SIZE) == place("bottom-right", SCREEN, SIZE)


def test_margin_is_adjustable():
    assert place("top-left", SCREEN, SIZE, margin=0) == (0, 0)


@pytest.mark.parametrize("pos,expected", [
    ((100, 100), "top-left"), ((1700, 100), "top-right"),
    ((100, 900), "bottom-left"), ((1700, 900), "bottom-right"),
])
def test_nearest_corner_by_window_centre(pos, expected):
    x, y = pos
    assert nearest_corner((x - 80, y - 75), SCREEN, SIZE) == expected


# ---------- free positioning: any dropped position is remembered as nearest corner + offset ----------
from avatar.placement import anchor_from_position, clamp


@pytest.mark.parametrize("pos", [(100, 100), (1700, 900), (900, 500), (5, 1000), (1750, 30), (960, 540)])
def test_any_position_round_trips_through_corner_and_offset(pos):
    corner, (dx, dy) = anchor_from_position(pos, SCREEN, SIZE)
    bx, by = place(corner, SCREEN, SIZE)
    assert (bx + dx, by + dy) == pos


@pytest.mark.parametrize("pos,corner", [((100, 100), "top-left"), ((1700, 100), "top-right"),
                                        ((100, 900), "bottom-left"), ((1700, 900), "bottom-right")])
def test_the_anchor_corner_is_the_nearest_one(pos, corner):
    assert anchor_from_position(pos, SCREEN, SIZE)[0] == corner


def test_clamp_keeps_the_window_fully_on_the_screen():
    assert clamp((5000, 5000), SCREEN, SIZE) == (1920 - 160, 1040 - 150)
    assert clamp((-300, -80), SCREEN, SIZE) == (0, 0)
    assert clamp((400, 300), SCREEN, SIZE) == (400, 300)
    assert clamp((2000, 10), SECOND, SIZE) == (2000, 10)                 # on a second monitor, relative to that monitor
    assert clamp((100, 10), SECOND, SIZE) == (1920, 10)
