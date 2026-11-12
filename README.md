# claude-code-companion

> **Fan-made, unofficial.** This project is not made by, affiliated with, or endorsed by Anthropic. "Claude" and
> "Claude Code" belong to Anthropic. The default avatar is a pixel-art homage to Claude Code's mascot.

A small, local, Windows companion for [Claude Code](https://claude.com/claude-code): it **reads Claude's replies out
loud** and shows a **pixel avatar** in a corner of your screen that reacts to what Claude is doing, so you know what
is going on while you work in other apps.

| | |
|---|---|
| **`read-aloud/`** | A Claude Code `Stop` hook that speaks Claude's final reply with a local voice (Windows voice, or the optional Voice Studio app). |
| **`avatar-app/`** | A transparent, always-on-top, click-through avatar. It shows idle / thinking / working / attention / waiting / error / celebrating / done, and moves its mouth while the voice is speaking. |

They work together (the voice tells the avatar when it is talking) but **each also works alone**.

![the default avatar in all its states](avatar-app/docs/contact_sheet.png)

## Requirements
- Windows 10 or 11, and Python 3.10 or newer.
- Optional: [Voice Studio](https://github.com/debpalash/voicestudio) (a separate, AGPL-licensed local text-to-speech
  app) for nicer voices. It is **not** included or needed: this project only calls its local HTTP API on `127.0.0.1`.
  Without it, the built-in Windows voice is used.

## Quick start
```bash
python companion.py setup                 # creates .venv and installs PySide6, Pillow, pytest
.venv\Scripts\python.exe companion.py hooks --show     # see exactly what would change in ~/.claude/settings.json
.venv\Scripts\python.exe companion.py hooks --apply    # register the hooks (a backup is saved first)
avatar-app\start-avatar.bat               # start the avatar (it also starts itself with each Claude session)
.venv\Scripts\python.exe read-aloud\read_aloud.py on   # turn reading aloud on
```
Start a new Claude Code session afterwards so it picks up the hooks. To remove everything again:
`companion.py hooks --remove` (use `--only avatar` or `--only read-aloud` to pick one).

## Using one tool only
- Avatar only: `companion.py hooks --apply --only avatar`
- Voice only: `companion.py hooks --apply --only read-aloud`, then `read_aloud.py on`

## Safety and privacy
- Hooks are registered in **exec form (no shell)**. Reply text is never placed in a command line. This matters: a
  hook that builds a shell command from reply text can be tricked into running commands (a real flaw found in another
  read-aloud plugin).
- The **avatar hook reads only the event name**, never your prompts or Claude's messages, writes one word to a small
  file, and always exits 0 in a few milliseconds. It runs asynchronously, so Claude never waits for it.
- The read-aloud hook only talks to `127.0.0.1` (Voice Studio) or the Windows speech engine; non-local URLs are refused.
  Nothing is uploaded anywhere. There is no telemetry.
- Neither hook can block or break a Claude session.

## Make your own avatar
Any folder in `avatar-app/packs/` with the eight base images appears in the tray menu's **Avatar** list. See
[`avatar-app/README.md`](avatar-app/README.md) for the file naming, and for building a pack from your own pixel art
with the included `pixelate` and `charpack` helpers. Character packs based on other people's work are not included.

## Tests
```bash
.venv\Scripts\python.exe companion.py test
```

## Licenses and thanks
Code: [MIT](LICENSE). Uses PySide6 (LGPL-3.0, not bundled; installed from PyPI) and Pillow (HPND). Voice Studio,
if you choose to use it, is a separate program under its own license.
