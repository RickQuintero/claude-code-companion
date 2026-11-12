import pytest

from avatar import states


@pytest.mark.parametrize("payload,expected", [
    ({"hook_event_name": "SessionStart"}, ("idle", "idle")),
    ({"hook_event_name": "UserPromptSubmit"}, ("thinking", "idle")),
    ({"hook_event_name": "PreToolUse"}, ("working", "idle")),
    ({"hook_event_name": "PostToolUse"}, ("working", "idle")),
    ({"hook_event_name": "Stop"}, ("celebrating", "idle")),
    ({"hook_event_name": "SessionEnd"}, ("idle", "idle")),
    ({"hook_event_name": "PermissionRequest"}, ("attention", "idle")),
    ({"hook_event_name": "Notification", "notification_type": "idle_prompt"}, ("waiting", "idle")),
    ({"hook_event_name": "Notification", "notification_type": "permission_prompt"}, ("attention", "idle")),
    ({"hook_event_name": "Notification"}, ("attention", "idle")),
    ({"hook_event_name": "PostToolUseFailure"}, ("error", "working")),
    ({"hook_event_name": "StopFailure"}, ("error", "idle")),
])
def test_state_for_event_table(payload, expected):
    assert states.state_for_event(payload) == expected


@pytest.mark.parametrize("payload", [{}, {"hook_event_name": "Whatever"}, [], "Stop", None, 5])
def test_state_for_event_ignores_unknown_or_bad_input(payload):
    assert states.state_for_event(payload) is None


def rec(state, ts=1000.0, after="idle"):
    return {"state": state, "after": after, "ts": ts}


def test_celebrating_then_done_then_idle():
    r = rec("celebrating")
    assert states.effective_state(r, 1003.9) == "celebrating"
    assert states.effective_state(r, 1004.1) == "done"
    assert states.effective_state(r, 1063.9) == "done"
    assert states.effective_state(r, 1064.1) == "idle"


def test_error_returns_to_its_after_state():
    r = rec("error", after="working")
    assert states.effective_state(r, 1002.9) == "error"
    assert states.effective_state(r, 1003.1) == "working"


def test_other_states_go_stale_to_idle_after_ten_minutes():
    r = rec("working")
    assert states.effective_state(r, 1599.0) == "working"
    assert states.effective_state(r, 1601.0) == "idle"


def test_attention_and_waiting_also_go_stale():
    assert states.effective_state(rec("attention"), 1601.0) == "idle"
    assert states.effective_state(rec("waiting"), 1601.0) == "idle"


@pytest.mark.parametrize("record", [None, {}, {"state": "dancing", "ts": 1.0}, {"state": "working"}])
def test_missing_or_unknown_record_is_idle(record):
    assert states.effective_state(record, 1000.0) == "idle"
