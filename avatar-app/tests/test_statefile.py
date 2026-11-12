import json

import pytest

from avatar import statefile


def test_round_trip(tmp_path):
    p = tmp_path / "s" / "avatar.json"
    statefile.write_state(p, "working", "idle", 123.5)
    assert statefile.read_state(p) == {"state": "working", "after": "idle", "ts": 123.5}


def test_write_leaves_no_temp_files(tmp_path):
    statefile.write_state(tmp_path / "avatar.json", "idle", "idle", 1.0)
    assert [f.name for f in tmp_path.iterdir()] == ["avatar.json"]


@pytest.mark.parametrize("content", ["", "{broken", "[]", '"x"', '{"state":"dancing"}', '{"state":5}'])
def test_read_state_is_none_for_bad_files(tmp_path, content):
    p = tmp_path / "avatar.json"
    p.write_text(content, encoding="utf-8")
    assert statefile.read_state(p) is None


def test_read_state_is_none_when_missing(tmp_path):
    assert statefile.read_state(tmp_path / "nope.json") is None


def test_speaking_true_only_until_the_deadline(tmp_path):
    p = tmp_path / "speaking.json"
    p.write_text(json.dumps({"speaking": True, "until": 100.0}), encoding="utf-8")
    assert statefile.read_speaking(p, 99.9) is True
    assert statefile.read_speaking(p, 100.1) is False     # worker was killed: flag must expire


def test_speaking_false_when_flag_off_missing_or_corrupt(tmp_path):
    p = tmp_path / "speaking.json"
    assert statefile.read_speaking(p, 1.0) is False
    p.write_text(json.dumps({"speaking": False, "until": 999.0}), encoding="utf-8")
    assert statefile.read_speaking(p, 1.0) is False
    p.write_text("{oops", encoding="utf-8")
    assert statefile.read_speaking(p, 1.0) is False
    p.write_text(json.dumps({"speaking": True}), encoding="utf-8")
    assert statefile.read_speaking(p, 1.0) is False
