import json

import pytest
from PIL import Image

from avatar.charpack import (Character, Lights, components, dilate, fill_holes, generate_character_pack, layout, recolor,
                             shift, swing)
from avatar.pack import load_pack
from avatar.states import STATES

BODY, BLUE, CORE, SOCKET = (150, 150, 155), (0, 100, 250), (240, 240, 240), (10, 10, 12)
ORANGE, RED = (255, 130, 0), (255, 30, 30)


def test_components_are_four_connected_and_largest_first():
    cells = {(0, 0), (1, 0), (2, 0), (5, 5), (6, 6)}                     # a line of 3, then two diagonal singles
    assert [len(c) for c in components(cells)] == [3, 1, 1]
    assert components(cells)[0] == {(0, 0), (1, 0), (2, 0)}


def test_fill_holes_adds_cells_the_blob_encloses():
    ring = {(x, y) for x in range(5) for y in range(5)} - {(2, 2)}
    assert fill_holes(ring) == ring | {(2, 2)}
    c_shape = {(0, 0), (1, 0), (2, 0), (0, 1), (0, 2), (1, 2), (2, 2)}   # open on the right: nothing enclosed
    assert fill_holes(c_shape) == c_shape


def test_dilate_adds_the_four_neighbours():
    assert dilate({(1, 1)}) == {(1, 1), (0, 1), (2, 1), (1, 0), (1, 2)}


def test_recolor_tints_saturated_colours_and_keeps_white_and_dark():
    r, g, b = recolor((0, 0, 255), (255, 0, 0))
    assert r > 240 and g < 15 and b < 15
    assert recolor((255, 255, 255), (255, 0, 0)) == (255, 255, 255)        # highlights stay white
    assert max(recolor((0, 0, 40), (255, 0, 0))) < 60                      # dark stays dark


def test_swing_keeps_rows_above_the_pivot_and_moves_the_bottom_row_fully():
    cells = {(5, y): (1, 2, 3) for y in range(0, 11)}
    out = swing(cells, amp=2, pivot=4, span=6)
    assert (5, 0) in out and (5, 4) in out                                 # above and at the pivot: unchanged
    assert (7, 10) in out and (5, 10) not in out                           # the bottom moved by 2
    assert shift({(1, 1): (1, 1, 1)}, 2, -1) == {(3, 0): (1, 1, 1)}


def make_sprite():
    cells = {(x, y): BODY for x in range(20) for y in range(24)}
    eye = {(x, y) for x in range(8, 12) for y in range(10, 14)}
    for c in eye:
        cells[c] = BLUE
    for c in ((9, 11), (10, 11), (9, 12), (10, 12)):
        cells[c] = CORE
    return cells, eye


def make_character(**kw):
    return Character(name="Test", width=120, tints={"working": ORANGE, "error": RED, "attention": (255, 230, 0),
                                                     "done": (70, 210, 100), "celebrating": (255, 80, 200)}, **kw)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    sprite, eye = make_sprite()
    lights = Lights(eyes=[eye], accents=set(), socket=SOCKET)
    char = make_character()
    out = tmp_path_factory.mktemp("char")
    generate_character_pack(sprite, lights, char, out)
    return out, sprite, eye, char


def eye_pixel(out, char, state, cell=(8, 10), suffix="", sprite_size=(20, 24)):
    cw, ch, ox, oy = layout(*sprite_size, char)
    im = Image.open(out / f"{state}{suffix}.png")
    px = im.getpixel(((cell[0] + ox) * char.cell_px + char.cell_px // 2, (cell[1] + oy) * char.cell_px + char.cell_px // 2))
    return px[:3]


def test_pack_loads_with_name_and_width_hint(built):
    out, *_ = built
    p = load_pack(out)
    assert p.name == "Test" and p.width == 120
    assert json.loads((out / "avatar.json").read_text(encoding="utf-8"))["width"] == 120


def test_images_have_the_canvas_size_and_transparent_corners(built):
    out, sprite, eye, char = built
    cw, ch, _, _ = layout(20, 24, char)
    files = list(out.glob("*.png"))
    assert len(files) >= 56
    for f in files:
        im = Image.open(f)
        assert im.mode == "RGBA" and im.size == (cw * char.cell_px, ch * char.cell_px), f.name
        assert im.getpixel((0, 0))[3] == 0 and im.getpixel((0, im.height - 1))[3] == 0, f.name     # left corners: no symbols


def test_the_eight_base_images_differ(built):
    out, *_ = built
    blobs = {s: (out / f"{s}.png").read_bytes() for s in STATES}
    assert len(set(blobs.values())) == 8


def test_the_eye_takes_the_state_colour_and_keeps_its_white_core(built):
    out, sprite, eye, char = built
    assert eye_pixel(out, char, "idle") == BLUE                            # native when no tint
    r, g, b = eye_pixel(out, char, "done")                                 # (done does not move, so the cell is fixed)
    assert g > 180 and r < 110 and b < 120                                 # green
    assert eye_pixel(out, char, "done", cell=(9, 11)) == CORE              # core stays white


def test_blinking_switches_the_eye_off_and_talking_enlarges_it(built):
    out, sprite, eye, char = built
    assert eye_pixel(out, char, "idle", suffix="_blink") == SOCKET
    assert eye_pixel(out, char, "idle", cell=(7, 10)) == BODY              # just outside the eye
    assert eye_pixel(out, char, "idle", cell=(7, 10), suffix="_talk") != BODY


def test_every_state_has_talk_blink_and_talk_blink_images(built):
    out, *_ = built
    for s in STATES:
        for suffix in ("_talk", "_blink", "_talk_blink"):
            assert (out / f"{s}{suffix}.png").exists(), s + suffix


def test_moving_states_have_extra_frames_and_thinking_has_three(built):
    out, *_ = built
    p = load_pack(out)
    assert p.frame_count("thinking") == 3
    for s in ("idle", "working", "attention", "celebrating", "error"):
        assert p.frame_count(s) >= 2, s


def test_a_still_body_never_moves_between_frames(tmp_path):
    sprite, eye = make_sprite()
    char = make_character(body_motion=False)
    generate_character_pack(sprite, Lights(eyes=[eye], accents=set(), socket=SOCKET), char, tmp_path)
    _, _, ox, oy = layout(20, 24, char)
    cp = char.cell_px
    box = (ox * cp, (oy + 18) * cp, (ox + 20) * cp, (oy + 24) * cp)          # the lower body, below the eye and its glow
    crops = {f.name: Image.open(f).crop(box).tobytes() for f in tmp_path.glob("*.png")}
    assert len(set(crops.values())) == 1                                      # identical in every state and frame
    p = load_pack(tmp_path)
    assert p.frame_count("idle") == 1 and p.frame_count("attention") == 1    # nothing to animate, so one frame
    assert p.frame_count("thinking") == 3                                     # symbol frames are kept


def test_symbols_have_a_dark_outline_so_white_ones_show_on_light_desktops(built):
    out, sprite, eye, char = built
    cw, ch, ox, oy = layout(20, 24, char)
    x_from = (ox + 20 + char.swing_amp + 1) * char.cell_px                 # the symbol margin on the right
    for state in ("waiting", "thinking"):                                  # white "?" and white dots
        im = Image.open(out / f"{state}.png")
        margin = [im.getpixel((x, y)) for x in range(x_from, im.width) for y in range(0, im.height, 2)]
        assert (18, 18, 26, 255) in margin, state
        assert (240, 240, 240, 255) in margin, state


def test_looking_up_moves_the_eye(built):
    out, sprite, eye, char = built
    # thinking looks up-left by (-1, -2): the cell above the eye is now eye coloured, the old bottom row is socket
    assert eye_pixel(out, char, "thinking", cell=(8, 8)) == BLUE
    assert eye_pixel(out, char, "thinking", cell=(8, 13)) == SOCKET


def test_generation_is_deterministic(built, tmp_path):
    out, sprite, eye, char = built
    other = tmp_path / "again"
    generate_character_pack(sprite, Lights(eyes=[eye], accents=set(), socket=SOCKET), char, other)
    for f in out.iterdir():
        assert f.read_bytes() == (other / f.name).read_bytes(), f.name


def test_several_lights_chase_while_working(tmp_path):
    cells = {(x, y): BODY for x in range(30) for y in range(20)}
    eyes = []
    for i in range(3):
        e = {(3 + i * 8 + dx, 5 + dy) for dx in range(3) for dy in range(3)}
        for c in e:
            cells[c] = BLUE
        eyes.append(e)
    char = make_character(lit={"working": "chase"}, swing_amp=0)           # no drift, so the eyes stay where we look
    generate_character_pack(cells, Lights(eyes=eyes, accents=set(), socket=SOCKET), char, tmp_path)
    lit = []
    for frame in ("working", "working_2", "working_3"):
        row = []
        for i in range(3):
            px = eye_pixel(tmp_path, char, frame, cell=(4 + i * 8, 6), sprite_size=(30, 20))
            row.append(px[0] > 200)                                         # orange = lit, dimmed = dark
        lit.append(row)
    assert all(sum(r) == 1 for r in lit) and len({tuple(r) for r in lit}) == 3   # one light at a time, moving
