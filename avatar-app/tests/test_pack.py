import json
from pathlib import Path

import pytest
from PIL import Image

from avatar.pack import Pack, PackError, load_pack_or_default, load_pack
from avatar.states import STATES


def png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (4, 4), (0, 0, 0, 0)).save(path)


def make_pack(folder: Path, extra=(), skip=(), avatar_json=None) -> Path:
    for s in STATES:
        if s not in skip:
            png(folder / f"{s}.png")
    for name in extra:
        png(folder / name)
    if avatar_json is not None:
        (folder / "avatar.json").write_text(avatar_json, encoding="utf-8")
    return folder


def test_a_complete_pack_loads_with_defaults(tmp_path):
    p = load_pack(make_pack(tmp_path / "p"))
    assert isinstance(p, Pack)
    assert (p.fps, p.blink_min, p.blink_max, p.blink_ms) == (8.0, 3.0, 6.0, 120)
    assert p.name == "p"


def test_avatar_json_overrides_defaults(tmp_path):
    f = make_pack(tmp_path / "p", avatar_json=json.dumps({"name": "Rob", "fps": 4, "blink_min": 1, "blink_max": 2, "blink_ms": 80}))
    p = load_pack(f)
    assert (p.name, p.fps, p.blink_min, p.blink_max, p.blink_ms) == ("Rob", 4.0, 1.0, 2.0, 80)


def test_missing_folder_is_a_pack_error(tmp_path):
    with pytest.raises(PackError):
        load_pack(tmp_path / "nope")


@pytest.mark.parametrize("state", STATES)
def test_every_base_image_is_required(tmp_path, state):
    with pytest.raises(PackError, match=state):
        load_pack(make_pack(tmp_path / "p", skip=(state,)))


@pytest.mark.parametrize("bad", ["{broken", "[]", '"x"', json.dumps({"fps": "fast"}), json.dumps({"fps": 0}),
                                 json.dumps({"blink_min": 5, "blink_max": 2})])
def test_bad_avatar_json_is_a_pack_error(tmp_path, bad):
    with pytest.raises(PackError):
        load_pack(make_pack(tmp_path / "p", avatar_json=bad))


def test_frame_count_counts_consecutive_numbered_frames(tmp_path):
    p = load_pack(make_pack(tmp_path / "p", extra=("working_2.png", "working_3.png", "idle_5.png")))
    assert p.frame_count("working") == 3
    assert p.frame_count("idle") == 1       # _5 is not consecutive, so it is ignored
    assert p.frame_count("done") == 1


def test_image_fallbacks_drop_blink_then_talk_but_keep_the_frame(tmp_path):
    f = make_pack(tmp_path / "p", extra=("working_2.png", "working_talk.png"))
    p = load_pack(f)
    assert p.image("working", 1, talk=True, blink=True) == f / "working_2.png"    # frame 2 has no talk image
    assert p.image("working", 0, talk=True, blink=True) == f / "working_talk.png"
    assert p.image("working", 0, talk=False, blink=False) == f / "working.png"


def test_image_prefers_the_most_specific_variant(tmp_path):
    f = make_pack(tmp_path / "p", extra=("idle_talk.png", "idle_blink.png", "idle_talk_blink.png"))
    p = load_pack(f)
    assert p.image("idle", 0, True, True) == f / "idle_talk_blink.png"
    assert p.image("idle", 0, True, False) == f / "idle_talk.png"
    assert p.image("idle", 0, False, True) == f / "idle_blink.png"
    assert p.image("idle", 0, False, False) == f / "idle.png"


def test_frame_index_wraps(tmp_path):
    f = make_pack(tmp_path / "p", extra=("working_2.png",))
    p = load_pack(f)
    assert p.image("working", 4, False, False) == f / "working.png"
    assert p.image("working", 5, False, False) == f / "working_2.png"


def test_a_broken_pack_falls_back_to_the_default_with_a_message(tmp_path):
    default = make_pack(tmp_path / "default")
    pack, error = load_pack_or_default(tmp_path / "missing", default)
    assert pack.folder == default and "missing" in error


def test_no_pack_chosen_uses_the_default_silently(tmp_path):
    default = make_pack(tmp_path / "default")
    pack, error = load_pack_or_default(None, default)
    assert pack.folder == default and error is None


def test_a_good_pack_is_used_as_is(tmp_path):
    default = make_pack(tmp_path / "default")
    mine = make_pack(tmp_path / "mine")
    pack, error = load_pack_or_default(mine, default)
    assert pack.folder == mine and error is None



# ---------- width hint and discovering packs ----------
def test_avatar_json_can_suggest_a_window_width(tmp_path):
    from avatar.pack import load_pack
    assert load_pack(make_pack(tmp_path / "a")).width is None
    assert load_pack(make_pack(tmp_path / "b", avatar_json=json.dumps({"width": 220}))).width == 220


@pytest.mark.parametrize("bad", [10, 5000, "wide", 2.5, True])
def test_a_silly_width_hint_is_a_pack_error(tmp_path, bad):
    with pytest.raises(PackError):
        load_pack(make_pack(tmp_path / "p", avatar_json=json.dumps({"width": bad})))


def test_discover_finds_only_valid_packs_sorted_by_name(tmp_path):
    from avatar.pack import discover_packs
    make_pack(tmp_path / "zeta", avatar_json=json.dumps({"name": "Zeta"}))
    make_pack(tmp_path / "alpha", avatar_json=json.dumps({"name": "Alpha"}))
    make_pack(tmp_path / "broken", skip=("idle",))
    (tmp_path / "notes.txt").write_text("not a pack")
    assert [p.name for p in discover_packs(tmp_path)] == ["Alpha", "Zeta"]


def test_discover_on_a_missing_folder_is_empty(tmp_path):
    from avatar.pack import discover_packs
    assert discover_packs(tmp_path / "nope") == []
