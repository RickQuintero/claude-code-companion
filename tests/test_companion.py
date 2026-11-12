import copy
import json

import companion as c

PY = r"C:\x\claude-code-companion\.venv\Scripts\python.exe"
ROOT = r"C:\x\claude-code-companion"
AVATAR_HOOK = ROOT + r"\avatar-app\avatar\hook.py"
VOICE_HOOK = ROOT + r"\read-aloud\speak_hook.py"
OTHER = {"hooks": [{"type": "command", "command": "other-tool", "args": ["--flag"]}]}
AVATAR_EVENTS = {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure", "Notification",
                 "PermissionRequest", "Stop", "StopFailure", "SessionEnd"}


def settings():
    return {"permissions": {"allow": ["Read"]}, "hooks": {"Stop": [copy.deepcopy(OTHER)]}, "theme": "dark"}


def test_avatar_entries_cover_every_event_and_use_the_safe_exec_form():
    entries = c.build_entries(PY, ROOT, only="avatar")
    assert set(entries) == AVATAR_EVENTS
    assert entries["Stop"][0]["hooks"][0] == {"type": "command", "command": PY, "args": [AVATAR_HOOK],
                                              "timeout": 5, "async": True}


def test_read_aloud_entry_is_a_single_stop_hook():
    entries = c.build_entries(PY, ROOT, only="read-aloud")
    assert set(entries) == {"Stop"}
    assert entries["Stop"][0]["hooks"][0] == {"type": "command", "command": PY, "args": [VOICE_HOOK], "timeout": 10}


def test_both_tools_share_the_stop_event_without_clobbering_each_other():
    entries = c.build_entries(PY, ROOT)
    assert set(entries) == AVATAR_EVENTS
    assert len(entries["Stop"]) == 2


def test_no_shell_syntax_anywhere_in_what_is_registered():
    blob = json.dumps(c.build_entries(PY, ROOT))
    assert "$" not in blob and "&&" not in blob and "|" not in blob and ";" not in blob


def test_merge_keeps_everything_that_was_there():
    merged = c.merge_into(settings(), c.build_entries(PY, ROOT))
    assert merged["permissions"] == {"allow": ["Read"]} and merged["theme"] == "dark"
    assert merged["hooks"]["Stop"][0] == OTHER and len(merged["hooks"]["Stop"]) == 3


def test_merge_is_idempotent_and_does_not_change_its_input():
    original = settings()
    snapshot = copy.deepcopy(original)
    once = c.merge_into(original, c.build_entries(PY, ROOT))
    assert original == snapshot
    assert c.merge_into(once, c.build_entries(PY, ROOT)) == once


def test_merge_works_without_any_hooks_key():
    assert set(c.merge_into({}, c.build_entries(PY, ROOT))["hooks"]) == AVATAR_EVENTS


def test_unregister_restores_the_original_exactly():
    merged = c.merge_into(settings(), c.build_entries(PY, ROOT))
    assert c.unregister(merged) == settings()


def test_unregister_only_one_tool_leaves_the_other():
    merged = c.merge_into(settings(), c.build_entries(PY, ROOT))
    no_avatar = c.unregister(merged, only="avatar")
    assert set(no_avatar["hooks"]) == {"Stop"} and len(no_avatar["hooks"]["Stop"]) == 2      # other tool + read-aloud
    no_voice = c.unregister(merged, only="read-aloud")
    assert set(no_voice["hooks"]) == AVATAR_EVENTS and len(no_voice["hooks"]["Stop"]) == 2   # other tool + avatar


def test_unregister_drops_the_hooks_key_when_nothing_else_used_it():
    merged = c.merge_into({"theme": "dark"}, c.build_entries(PY, ROOT))
    assert c.unregister(merged) == {"theme": "dark"}


def test_cli_show_changes_nothing_apply_backs_up_and_remove_restores(tmp_path, capsys):
    target = tmp_path / "settings.json"
    target.write_text(json.dumps(settings(), indent=2), encoding="utf-8")
    before = target.read_text(encoding="utf-8")
    assert c.main(["hooks", "--show", "--settings", str(target)]) == 0
    assert target.read_text(encoding="utf-8") == before and "PreToolUse" in capsys.readouterr().out
    assert c.main(["hooks", "--apply", "--settings", str(target)]) == 0
    assert (tmp_path / "settings.json.bak-companion").read_text(encoding="utf-8") == before
    assert "PreToolUse" in json.loads(target.read_text(encoding="utf-8"))["hooks"]
    assert c.main(["hooks", "--remove", "--settings", str(target)]) == 0
    assert json.loads(target.read_text(encoding="utf-8")) == settings()


def test_cli_only_flag_limits_what_is_applied(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text("{}", encoding="utf-8")
    assert c.main(["hooks", "--apply", "--only", "read-aloud", "--settings", str(target)]) == 0
    assert set(json.loads(target.read_text(encoding="utf-8"))["hooks"]) == {"Stop"}


def test_cli_refuses_to_touch_a_settings_file_it_cannot_parse(tmp_path):
    target = tmp_path / "settings.json"
    target.write_text("{not json", encoding="utf-8")
    assert c.main(["hooks", "--apply", "--settings", str(target)]) != 0
    assert target.read_text(encoding="utf-8") == "{not json"


def test_setup_creates_the_venv_and_installs_requirements():
    calls = []
    c.setup(run=lambda args, **kw: calls.append(list(args)), exists=lambda p: False)
    assert calls[0][1:3] == ["-m", "venv"]
    assert calls[1][1:5] == ["-m", "pip", "install", "-r"] and calls[1][0].endswith("python.exe")


def test_setup_reuses_an_existing_venv():
    calls = []
    c.setup(run=lambda args, **kw: calls.append(list(args)), exists=lambda p: True)
    assert len(calls) == 1 and calls[0][1:3] == ["-m", "pip"]
