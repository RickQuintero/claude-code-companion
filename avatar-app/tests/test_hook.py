import io
import json

import pytest

from avatar import hook, statefile


def run(payload, tmp_path, launch=None, now=500.0):
    stdin = io.StringIO(payload if isinstance(payload, str) else json.dumps(payload))
    path = tmp_path / "avatar.json"
    code = hook.main(stdin, state_path=path, now=now, launch=launch or (lambda: None))
    return code, path


def test_stop_writes_celebrating(tmp_path):
    code, path = run({"hook_event_name": "Stop"}, tmp_path)
    assert code == 0
    assert statefile.read_state(path) == {"state": "celebrating", "after": "idle", "ts": 500.0}


def test_a_leading_byte_order_mark_is_tolerated(tmp_path):
    # PowerShell pipes put a BOM in front of the JSON; the hook must still understand it
    code, path = run("﻿" + json.dumps({"hook_event_name": "Stop"}), tmp_path)
    assert code == 0 and statefile.read_state(path)["state"] == "celebrating"


def test_tool_failure_remembers_to_return_to_working(tmp_path):
    _, path = run({"hook_event_name": "PostToolUseFailure"}, tmp_path)
    assert statefile.read_state(path)["after"] == "working"


@pytest.mark.parametrize("raw", ["", "not json", "[]", '"Stop"', "x" * (5 * 1024 * 1024),
                                 json.dumps({"hook_event_name": "Whatever"}), "{}"])
def test_bad_or_unknown_input_exits_zero_and_writes_nothing(tmp_path, raw):
    code, path = run(raw, tmp_path)
    assert code == 0 and not path.exists()


def test_message_text_is_never_stored_or_passed_on(tmp_path):
    evil = "'; Remove-Item C:\\x -Recurse; '"
    launched = []
    _, path = run({"hook_event_name": "SessionStart", "message": evil, "prompt": evil}, tmp_path,
                  launch=lambda: launched.append(1))
    assert evil not in path.read_text(encoding="utf-8")
    assert launched == [1]


def test_only_session_start_launches_the_app(tmp_path):
    launched = []
    for event in ("Stop", "PreToolUse", "UserPromptSubmit"):
        run({"hook_event_name": event}, tmp_path, launch=lambda: launched.append(1))
    assert launched == []


def test_failures_inside_launch_or_write_still_exit_zero(tmp_path):
    def boom():
        raise RuntimeError("no app")

    code, _ = run({"hook_event_name": "SessionStart"}, tmp_path, launch=boom)
    assert code == 0
    blocker = tmp_path / "file"
    blocker.write_text("x")
    code = hook.main(io.StringIO(json.dumps({"hook_event_name": "Stop"})), state_path=blocker / "sub" / "a.json",
                     now=1.0, launch=lambda: None)
    assert code == 0
