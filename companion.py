"""Setup and hook registration for claude-code-companion (read-aloud voice + pixel avatar for Claude Code, Windows).

    python companion.py setup                                  create .venv and install the requirements
    python companion.py hooks --show                           print exactly what would change in Claude's settings
    python companion.py hooks --apply [--only avatar|read-aloud]
    python companion.py hooks --remove [--only avatar|read-aloud]
    python companion.py test                                   run all three test suites

Hooks are registered in ~/.claude/settings.json (use --settings PATH for another file). Before --apply, a backup is
saved next to it as settings.json.bak-companion. Hooks are registered in exec form (no shell) and never see reply text.
"""
from __future__ import annotations

import argparse
import copy
import difflib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
DEFAULT_SETTINGS = Path.home() / ".claude" / "settings.json"
AVATAR_EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure", "Notification",
                 "PermissionRequest", "Stop", "StopFailure", "SessionEnd")
TOOLS = ("avatar", "read-aloud")
# how to recognise our own entries again (so --remove only ever touches what --apply wrote)
SUFFIXES = {"avatar": "avatar-app\\avatar\\hook.py", "read-aloud": "read-aloud\\speak_hook.py"}


def venv_python() -> str:
    exe = VENV / "Scripts" / "python.exe"
    return str(exe) if exe.exists() else sys.executable


def build_entries(python: str, root: str | Path = ROOT, only: str | None = None) -> dict:
    """Event -> list of hook entries, in exec form (no shell). The avatar hook is async so Claude never waits for it."""
    root = str(root)
    entries: dict[str, list] = {}
    if only in (None, "avatar"):
        hook = {"type": "command", "command": python, "args": [root + "\\avatar-app\\avatar\\hook.py"],
                "timeout": 5, "async": True}
        for event in AVATAR_EVENTS:
            entries.setdefault(event, []).append({"hooks": [dict(hook)]})
    if only in (None, "read-aloud"):
        hook = {"type": "command", "command": python, "args": [root + "\\read-aloud\\speak_hook.py"], "timeout": 10}
        entries.setdefault("Stop", []).append({"hooks": [hook]})
    return entries


def _tool_of(entry) -> str | None:
    for hook in entry.get("hooks", []) if isinstance(entry, dict) else []:
        for arg in hook.get("args", []) if isinstance(hook, dict) else []:
            norm = arg.lower().replace("/", "\\") if isinstance(arg, str) else ""
            for tool, suffix in SUFFIXES.items():
                if norm.endswith(suffix):
                    return tool
    return None


def merge_into(settings: dict, entries: dict) -> dict:
    out = copy.deepcopy(settings)
    hooks = out.setdefault("hooks", {})
    for event, new in entries.items():
        current = hooks.setdefault(event, [])
        for entry in new:
            if _tool_of(entry) not in {_tool_of(e) for e in current}:
                current.append(copy.deepcopy(entry))
    return out


def unregister(settings: dict, only: str | None = None) -> dict:
    out = copy.deepcopy(settings)
    hooks = out.get("hooks")
    if not isinstance(hooks, dict):
        return out
    for event in list(hooks):
        hooks[event] = [e for e in hooks[event] if _tool_of(e) is None or (only is not None and _tool_of(e) != only)]
        if not hooks[event]:
            del hooks[event]
    if not hooks:
        del out["hooks"]
    return out


def setup(run=subprocess.run, exists=lambda p: Path(p).exists()) -> None:
    """Create the shared virtual environment and install the requirements into it."""
    if not exists(VENV / "Scripts" / "python.exe"):
        run([sys.executable, "-m", "venv", str(VENV)], check=True)
    run([str(VENV / "Scripts" / "python.exe"), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], check=True)


def run_tests() -> int:
    code = 0
    for folder in ("tests", "avatar-app", "read-aloud"):
        print(f"== {folder}")
        code |= subprocess.run([venv_python(), "-m", "pytest", "-q"], cwd=ROOT / folder if folder != "tests" else ROOT).returncode
    return code


def _dump(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _hooks_command(args) -> int:
    try:
        before_text = args.settings.read_text(encoding="utf-8")
        before = json.loads(before_text)
        if not isinstance(before, dict):
            raise ValueError("settings file is not a JSON object")
    except (OSError, ValueError) as e:
        print(f"Cannot read {args.settings}: {e}. Nothing changed.", file=sys.stderr)
        return 2
    after = unregister(before, args.only) if args.remove else merge_into(before, build_entries(venv_python(), ROOT, args.only))
    if args.show:
        diff = difflib.unified_diff(_dump(before).splitlines(True), _dump(after).splitlines(True),
                                    "settings.json (now)", "settings.json (after)")
        sys.stdout.write("".join(diff) or "No change.\n")
        return 0
    if args.apply:
        shutil.copy2(args.settings, args.settings.with_name(args.settings.name + ".bak-companion"))
    args.settings.write_text(_dump(after), encoding="utf-8")
    print("Done." if after != before else "Already in that state.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup", help="create .venv and install requirements")
    sub.add_parser("test", help="run all test suites")
    hooks = sub.add_parser("hooks", help="show / apply / remove the Claude Code hooks")
    mode = hooks.add_mutually_exclusive_group(required=True)
    for flag in ("show", "apply", "remove"):
        mode.add_argument(f"--{flag}", action="store_true")
    hooks.add_argument("--only", choices=TOOLS)
    hooks.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS)
    args = ap.parse_args(argv)
    if args.cmd == "setup":
        setup()
        return 0
    if args.cmd == "test":
        return run_tests()
    return _hooks_command(args)


if __name__ == "__main__":
    sys.exit(main())
