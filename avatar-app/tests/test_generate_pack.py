import hashlib
import json

import pytest
from PIL import Image

from avatar.generate_pack import BODY, generate_pack
from avatar.pack import load_pack
from avatar.states import STATES


@pytest.fixture(scope="module")
def pack_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("pack")
    generate_pack(out)
    return out


def test_all_base_images_exist_and_the_pack_loads(pack_dir):
    p = load_pack(pack_dir)
    assert p.name == "Claude mascot" and p.fps == 8.0
    for s in STATES:
        assert (pack_dir / f"{s}.png").exists()


def test_every_image_is_200_square_rgba_with_transparent_corners(pack_dir):
    pngs = list(pack_dir.glob("*.png"))
    assert len(pngs) > 40
    for f in pngs:
        im = Image.open(f)
        assert im.mode == "RGBA" and im.size == (200, 200), f.name
        for corner in [(0, 0), (199, 0), (0, 199), (199, 199)]:
            assert im.getpixel(corner)[3] == 0, f.name


def test_idle_uses_the_measured_body_colour(pack_dir):
    assert Image.open(pack_dir / "idle.png").getpixel((100, 110)) == (*BODY, 255)
    assert BODY == (216, 119, 86)


def test_the_eight_base_images_are_all_different(pack_dir):
    digests = {s: hashlib.md5(Image.open(pack_dir / f"{s}.png").tobytes()).hexdigest() for s in STATES}
    assert len(set(digests.values())) == 8


def test_every_state_has_a_talk_image_that_differs(pack_dir):
    for s in STATES:
        base = Image.open(pack_dir / f"{s}.png").tobytes()
        assert (pack_dir / f"{s}_talk.png").exists(), s
        assert Image.open(pack_dir / f"{s}_talk.png").tobytes() != base, s


def test_calm_states_have_blink_and_talk_blink_images(pack_dir):
    for s in ("idle", "done", "waiting"):
        for suffix in ("_blink", "_talk_blink"):
            assert (pack_dir / f"{s}{suffix}.png").exists(), s + suffix
        assert Image.open(pack_dir / f"{s}_blink.png").tobytes() != Image.open(pack_dir / f"{s}.png").tobytes()


def test_moving_states_have_extra_frames(pack_dir):
    p = load_pack(pack_dir)
    assert p.frame_count("working") >= 2 and p.frame_count("thinking") == 3
    assert p.frame_count("celebrating") >= 2 and p.frame_count("idle") >= 2


def test_generation_is_deterministic(pack_dir, tmp_path):
    other = tmp_path / "again"
    generate_pack(other)
    names = sorted(f.name for f in pack_dir.iterdir())
    assert names == sorted(f.name for f in other.iterdir())
    for n in names:
        assert (pack_dir / n).read_bytes() == (other / n).read_bytes(), n


def test_avatar_json_is_valid(pack_dir):
    data = json.loads((pack_dir / "avatar.json").read_text(encoding="utf-8"))
    assert data["name"] == "Claude mascot" and data["fps"] == 8
