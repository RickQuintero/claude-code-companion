import json

from avatar.config import DEFAULTS, load_config, save_config


def test_missing_file_gives_defaults(tmp_path):
    assert load_config(tmp_path / "c.json") == DEFAULTS


def test_round_trip(tmp_path):
    p = tmp_path / "c.json"
    save_config({**DEFAULTS, "corner": "top-left", "width": 220}, p)
    cfg = load_config(p)
    assert cfg["corner"] == "top-left" and cfg["width"] == 220


def test_corrupt_or_wrong_shape_gives_defaults(tmp_path):
    p = tmp_path / "c.json"
    for text in ("", "{oops", "[]", '"x"'):
        p.write_text(text, encoding="utf-8")
        assert load_config(p) == DEFAULTS


def test_bad_values_fall_back_one_key_at_a_time(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"corner": "middle", "width": "big", "opacity": 7, "visible": "yes", "pack": "mine"}),
                 encoding="utf-8")
    cfg = load_config(p)
    assert cfg["corner"] == DEFAULTS["corner"] and cfg["width"] == DEFAULTS["width"]
    assert cfg["opacity"] == DEFAULTS["opacity"] and cfg["visible"] is True
    assert cfg["pack"] == "mine"                       # the one good value survives


def test_unknown_keys_are_ignored(tmp_path):
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"future_setting": 1, "width": 200}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg["width"] == 200 and "future_setting" not in cfg


def test_position_and_hover_settings_have_sane_defaults_and_validation(tmp_path):
    assert DEFAULTS["offset"] == [0, 0] and DEFAULTS["screen"] == "" and DEFAULTS["hover_radius"] == 60
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"offset": [30, -12], "screen": "DISPLAY2", "hover_radius": 90}), encoding="utf-8")
    cfg = load_config(p)
    assert cfg["offset"] == [30, -12] and cfg["screen"] == "DISPLAY2" and cfg["hover_radius"] == 90
    for bad in ({"offset": [1]}, {"offset": "x"}, {"offset": [1, "a"]}, {"offset": [99999, 0]}, {"hover_radius": -1},
                {"hover_radius": 9999}, {"hover_radius": "big"}, {"screen": 5}):
        p.write_text(json.dumps(bad), encoding="utf-8")
        loaded = load_config(p)
        key = next(iter(bad))
        assert loaded[key] == DEFAULTS[key], bad
    p.write_text(json.dumps({"hover_radius": 0}), encoding="utf-8")
    assert load_config(p)["hover_radius"] == 0                            # 0 means off
