import json
import random

import pytest
from PySide6.QtCore import QLockFile, QPoint, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from avatar import statefile
from avatar.config import DEFAULTS, load_config
from avatar.generate_pack import generate_pack


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


class Clock:
    t = 10_000.0

    def __call__(self):
        return self.t


@pytest.fixture
def env(tmp_path, qapp):
    default = tmp_path / "default"
    generate_pack(default)
    clock = Clock()
    calls = []
    paths = {"state": tmp_path / "avatar.json", "speaking": tmp_path / "speaking.json", "config": tmp_path / "config.json"}
    cfg = {**DEFAULTS, "speaking_file": str(paths["speaking"])}
    return {"tmp": tmp_path, "default": default, "clock": clock, "calls": calls, "paths": paths, "cfg": cfg,
            "cursor": [QPoint(-9999, -9999)]}


def make_window(env, real_place=False, **cfg_overrides):
    from avatar.app import AvatarWindow
    cfg = {**env["cfg"], **cfg_overrides}

    def place_fn(corner, screen, size, margin=16):
        env["calls"].append((corner, size))
        return (0, 0)

    extra = {} if real_place else {"place_fn": place_fn}
    return AvatarWindow(cfg, state_path=env["paths"]["state"], default_pack=env["default"], clock=env["clock"],
                        rng=random.Random(1), config_path=env["paths"]["config"], cursor_fn=lambda: env["cursor"][0],
                        packs_dir=env.get("packs_dir", env["tmp"] / "no_packs"), **extra)


def test_window_is_a_click_through_always_on_top_overlay_that_never_takes_focus(env):
    w = make_window(env)
    flags = w.windowFlags()
    for flag in (Qt.WindowType.FramelessWindowHint, Qt.WindowType.WindowStaysOnTopHint, Qt.WindowType.Tool,
                 Qt.WindowType.WindowTransparentForInput, Qt.WindowType.WindowDoesNotAcceptFocus):
        assert flags & flag, flag
    assert w.testAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    assert w.testAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)


def test_a_state_file_selects_that_states_image(env):
    w = make_window(env)
    statefile.write_state(env["paths"]["state"], "thinking", "idle", env["clock"].t)
    w.refresh()
    assert w.current_image_path().name.startswith("thinking")


def test_no_state_file_means_idle(env):
    w = make_window(env)
    w.refresh()
    assert w.current_image_path().name.startswith("idle")


def test_speaking_flag_switches_to_talk_images(env):
    w = make_window(env)
    env["paths"]["speaking"].write_text(json.dumps({"speaking": True, "until": env["clock"].t + 60}), encoding="utf-8")
    seen = set()
    for _ in range(30):
        w.refresh()
        seen.add(w.current_image_path().name)
        env["clock"].t += 0.02
    assert any("_talk" in n for n in seen) and any("_talk" not in n for n in seen)   # the mouth flaps


def test_a_corrupt_state_file_keeps_the_last_good_state(env):
    w = make_window(env)
    statefile.write_state(env["paths"]["state"], "working", "idle", env["clock"].t)
    w.refresh()
    env["paths"]["state"].write_text("{oops", encoding="utf-8")
    w.refresh()
    assert w.current_image_path().name.startswith("working")


def test_a_bad_pack_falls_back_to_the_default_and_says_why(env):
    w = make_window(env, pack=str(env["tmp"] / "missing_pack"))
    assert w.pack.folder == env["default"]
    assert "missing_pack" in w.pack_error
    w.refresh()
    assert w.current_image_path().parent == env["default"]


def test_the_window_is_as_wide_as_configured_and_keeps_the_image_shape(env):
    w = make_window(env, width=220)
    assert (w.width(), w.height()) == (220, 220)         # the default pack is square


def test_it_is_placed_in_the_configured_corner_and_again_when_the_screen_changes(env):
    w = make_window(env, corner="top-left")
    assert env["calls"][-1][0] == "top-left"
    n = len(env["calls"])
    w.on_screen_changed()
    assert len(env["calls"]) == n + 1


def test_settings_changes_apply_and_are_saved(env):
    w = make_window(env)
    w.set_width(300)
    w.set_corner("top-right")
    w.set_opacity(0.5)
    saved = load_config(env["paths"]["config"])
    assert (saved["width"], saved["corner"], saved["opacity"]) == (300, "top-right", 0.5)
    assert w.width() == 300


def test_move_mode_accepts_the_mouse_and_goes_back_to_click_through(env):
    w = make_window(env)
    w.set_move_mode(True)
    assert not (w.windowFlags() & Qt.WindowType.WindowTransparentForInput)
    w.set_move_mode(False)
    assert w.windowFlags() & Qt.WindowType.WindowTransparentForInput


def test_the_tray_menu_offers_the_documented_controls(env):
    w = make_window(env)
    titles = [a.text() for a in w.build_menu().actions()]
    for wanted in ("Show / Hide", "Corner", "Size", "Opacity", "Move mode", "Quit"):
        assert wanted in titles, wanted


def test_a_second_instance_does_not_start(env):
    from avatar.app import create
    lock_path = env["tmp"] / "app.lock"
    held = QLockFile(str(lock_path))
    assert held.tryLock(0)
    try:
        assert create(config_path=env["paths"]["config"], lock_path=lock_path, default_pack=env["default"]) is None
    finally:
        held.unlock()
    first = create(config_path=env["paths"]["config"], lock_path=lock_path, default_pack=env["default"])
    assert first is not None
    assert create(config_path=env["paths"]["config"], lock_path=lock_path, default_pack=env["default"]) is None
    first.release_lock()


def test_painting_actually_draws_the_mascot(env):
    w = make_window(env, width=200)
    w.refresh()
    img = w.grab().toImage()
    opaque = sum(1 for x in range(0, 200, 5) for y in range(0, 200, 5) if img.pixelColor(x, y).alpha() > 0)
    assert opaque > 100 and img.pixelColor(0, 0).alpha() == 0       # mascot pixels drawn, corner stays transparent


# ---------- switching avatars ----------
@pytest.fixture
def two_packs(env):
    packs = env["tmp"] / "packs"
    generate_pack(packs / "alpha")
    generate_pack(packs / "beta")
    (packs / "alpha" / "avatar.json").write_text(json.dumps({"name": "Alpha"}), encoding="utf-8")
    (packs / "beta" / "avatar.json").write_text(json.dumps({"name": "Beta", "width": 220}), encoding="utf-8")
    env["packs_dir"] = packs
    return packs


def test_set_pack_switches_the_pictures_the_size_and_saves_the_choice(env, two_packs):
    w = make_window(env)
    w.set_pack(two_packs / "beta")
    w.refresh()
    assert w.pack.name == "Beta" and w.current_image_path().parent == two_packs / "beta"
    assert w.width() == 220 and w.cfg["width"] == 220
    saved = load_config(env["paths"]["config"])
    assert saved["pack"] == str(two_packs / "beta") and saved["width"] == 220


def test_set_pack_to_a_broken_folder_keeps_the_current_avatar_and_says_why(env, two_packs):
    w = make_window(env)
    before = w.pack.folder
    w.set_pack(env["tmp"] / "not_a_pack")
    assert w.pack.folder == before and "not_a_pack" in w.pack_error


def test_set_pack_without_a_width_hint_keeps_the_current_width(env, two_packs):
    w = make_window(env, width=300)
    w.set_pack(two_packs / "alpha")
    assert w.width() == 300


def test_the_menu_lists_every_avatar_and_ticks_the_current_one(env, two_packs):
    w = make_window(env)
    w.set_pack(two_packs / "beta")
    menu = w.build_menu()
    avatar_menu = next(a.menu() for a in menu.actions() if a.text() == "Avatar")
    avatar_menu.aboutToShow.emit()
    names = {a.text(): a.isChecked() for a in avatar_menu.actions()}
    assert names == {"Alpha": False, "Beta": True}
    next(a for a in avatar_menu.actions() if a.text() == "Alpha").trigger()
    assert w.pack.name == "Alpha"




# ---------- free positioning: the avatar stays exactly where it was dropped ----------
def primary_area():
    g = QGuiApplication.primaryScreen().availableGeometry()
    return g


def test_a_dropped_position_is_kept_exactly_and_survives_a_restart(env):
    w = make_window(env, real_place=True)
    g = primary_area()
    target = QPoint(g.x() + 137, g.y() + 71)                   # nowhere near a corner
    w.set_move_mode(True)
    w.move(target)
    w.finish_drag()
    assert w.pos() == target
    saved = load_config(env["paths"]["config"])
    again = make_window(env, real_place=True, corner=saved["corner"], offset=saved["offset"], screen=saved["screen"])
    assert again.pos() == target


def test_the_dropped_position_is_stored_as_corner_plus_offset_on_this_screen(env):
    w = make_window(env, real_place=True)
    g = primary_area()
    w.set_move_mode(True)
    w.move(QPoint(g.x() + 20, g.y() + 30))
    w.finish_drag()
    saved = load_config(env["paths"]["config"])
    assert saved["corner"] == "top-left" and saved["screen"] == QGuiApplication.primaryScreen().name()
    assert saved["offset"] == [20 - 16, 30 - 16]               # relative to the top-left spot (16 px margin)


def test_a_stored_position_that_no_longer_fits_the_screen_is_pulled_back_inside(env):
    w = make_window(env, real_place=True, corner="bottom-right", offset=[900, 900])
    assert primary_area().contains(w.geometry())


def test_picking_a_corner_from_the_menu_snaps_there_and_forgets_the_offset(env):
    w = make_window(env, real_place=True, corner="top-left", offset=[30, 40])
    w.set_corner("bottom-left")
    assert w.cfg["offset"] == [0, 0] and w.cfg["corner"] == "bottom-left"


def test_finishing_a_drag_unticks_move_mode_and_makes_it_click_through_again(env):
    w = make_window(env, real_place=True)
    menu = w.build_menu()
    action = next(a for a in menu.actions() if a.text() == "Move mode")
    action.setChecked(True)
    assert not (w.windowFlags() & Qt.WindowType.WindowTransparentForInput)
    w.finish_drag()
    assert not action.isChecked()
    assert w.windowFlags() & Qt.WindowType.WindowTransparentForInput


# ---------- the see-through circle under the mouse ----------
def alpha_image(w):
    return w.grab().toImage()


def tick(env, w, seconds):
    env["clock"].t += seconds
    w.update_hover()


def test_the_mouse_cuts_a_soft_circle_and_far_pixels_stay_solid(env):
    w = make_window(env, real_place=True, width=200, hover_radius=60)
    w.refresh()
    base = alpha_image(w)
    centre = QPoint(100, 110)                                          # on the mascot's body
    env["cursor"][0] = w.mapToGlobal(centre)
    tick(env, w, 0.0)
    tick(env, w, 0.3)                                                  # fully faded in
    holed = alpha_image(w)
    assert base.pixelColor(100, 110).alpha() == 255 and holed.pixelColor(100, 110).alpha() < 20
    far = next((x, y) for x in range(200) for y in range(200)
               if base.pixelColor(x, y).alpha() == 255 and ((x - 100) ** 2 + (y - 110) ** 2) ** 0.5 > 70)
    assert holed.pixelColor(*far).alpha() == 255                       # outside the circle: untouched
    edge = next((x, y) for x in range(200) for y in range(200)
                if base.pixelColor(x, y).alpha() == 255 and 0.8 * 60 <= ((x - 100) ** 2 + (y - 110) ** 2) ** 0.5 <= 0.9 * 60)
    assert 0 < holed.pixelColor(*edge).alpha() < 255                   # the edge is soft, not a hard cut


def test_the_circle_follows_the_mouse_and_fades_away_when_it_leaves(env):
    w = make_window(env, real_place=True, width=200, hover_radius=60)
    w.refresh()
    base = alpha_image(w)
    env["cursor"][0] = w.mapToGlobal(QPoint(100, 110))
    tick(env, w, 0.0)
    tick(env, w, 0.3)
    env["cursor"][0] = w.mapToGlobal(QPoint(60, 110))                  # move left: the old centre is solid again
    tick(env, w, 0.03)
    assert alpha_image(w).pixelColor(120, 110).alpha() > 200 and alpha_image(w).pixelColor(60, 110).alpha() < 40
    env["cursor"][0] = QPoint(-9999, -9999)
    tick(env, w, 0.3)
    assert alpha_image(w) == base


def test_the_circle_fades_in_instead_of_popping(env):
    w = make_window(env, real_place=True, width=200, hover_radius=60)
    w.refresh()
    env["cursor"][0] = w.mapToGlobal(QPoint(100, 110))
    tick(env, w, 0.0)
    tick(env, w, 0.075)                                                # half way through a 150 ms fade
    assert 0.3 < w.hover_amount < 0.7


def test_the_circle_can_be_switched_off_and_is_off_during_move_mode(env):
    off = make_window(env, real_place=True, width=200, hover_radius=0)
    env["cursor"][0] = off.mapToGlobal(QPoint(100, 110))
    tick(env, off, 0.0)
    tick(env, off, 0.3)
    assert off.hover_amount == 0
    moving = make_window(env, real_place=True, width=200, hover_radius=60)
    moving.set_move_mode(True)
    env["cursor"][0] = moving.mapToGlobal(QPoint(100, 110))
    tick(env, moving, 0.0)
    tick(env, moving, 0.3)
    assert moving.hover_amount == 0


def test_changing_the_circle_size_from_the_menu_is_saved(env):
    w = make_window(env, real_place=True)
    w.set_hover_radius(90)
    assert w.cfg["hover_radius"] == 90 and load_config(env["paths"]["config"])["hover_radius"] == 90
    menu = w.build_menu()
    titles = [a.text() for a in menu.actions()]
    assert "See-through" in titles
