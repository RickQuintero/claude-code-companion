"""The eight avatar states, the hook-event mapping, and the timers that move one state into the next."""
from __future__ import annotations

STATES = ("idle", "thinking", "working", "attention", "celebrating", "error", "waiting", "done")

CELEBRATE_SECONDS = 4.0    # celebrating -> done
DONE_SECONDS = 60.0        # done -> idle
ERROR_SECONDS = 3.0        # error -> its "after" state
STALE_SECONDS = 600.0      # anything else with no new event -> idle (covers a killed session)

_SIMPLE = {
    "SessionStart": ("idle", "idle"),
    "SessionEnd": ("idle", "idle"),
    "UserPromptSubmit": ("thinking", "idle"),
    "PreToolUse": ("working", "idle"),
    "PostToolUse": ("working", "idle"),
    "Stop": ("celebrating", "idle"),
    "PermissionRequest": ("attention", "idle"),
    "PostToolUseFailure": ("error", "working"),
    "StopFailure": ("error", "idle"),
}


def state_for_event(payload) -> tuple[str, str] | None:
    """Map a Claude hook payload to (state, after). None for anything we do not understand."""
    if not isinstance(payload, dict):
        return None
    event = payload.get("hook_event_name")
    if event == "Notification":
        return ("waiting" if payload.get("notification_type") == "idle_prompt" else "attention", "idle")
    return _SIMPLE.get(event) if isinstance(event, str) else None


def effective_state(record: dict | None, now: float) -> str:
    """The state to show right now, given the last record written by the hook."""
    if not isinstance(record, dict):
        return "idle"
    state, ts = record.get("state"), record.get("ts")
    if state not in STATES or not isinstance(ts, (int, float)):
        return "idle"
    age = now - ts
    if state == "celebrating":
        if age < CELEBRATE_SECONDS:
            return "celebrating"
        return "done" if age < CELEBRATE_SECONDS + DONE_SECONDS else "idle"
    if state == "done":
        return "done" if age < DONE_SECONDS else "idle"
    if state == "error" and age >= ERROR_SECONDS:
        after = record.get("after")
        return after if after in STATES else "idle"
    return "idle" if age >= STALE_SECONDS else state
