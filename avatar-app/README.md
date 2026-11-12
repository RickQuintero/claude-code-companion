# avatar-app

A small transparent mascot in a corner of your screen. It floats over every app, clicks pass through it, and it
never takes focus.

## States
| State | When |
|---|---|
| idle | session start/end, or nothing happened for a while |
| thinking | you sent a prompt |
| working | Claude is running tools |
| attention | Claude needs permission |
| waiting | Claude is waiting for your answer |
| error | a tool or the turn failed (3 s, then back to working/idle) |
| celebrating | Claude finished (4 s) |
| done | after celebrating, for 60 s; then idle |

Anything unchanged for 10 minutes returns to idle. While the read-aloud voice is speaking, the mouth moves.

## How it works
`avatar/hook.py` runs on Claude Code events, writes the state word to `state/avatar.json` and starts the window on
SessionStart (a second copy exits by itself). It reads only the event name. The read-aloud hook writes
`../read-aloud/state/speaking.json` while audio plays. The window reads both files 10 times a second.

## The tray menu
Show/Hide, **Avatar** (every pack in `packs/`), Corner, Size, Opacity, **See-through**, **Move mode**, Quit.
- **Move mode:** drag the avatar anywhere, on any monitor. It stays exactly where you drop it and click-through comes
  back by itself. (Stored in `config.json` as nearest corner + offset, and always pulled back fully on screen.)
- **See-through:** when the mouse is over the avatar, a soft circle around the pointer fades to transparent so you can
  see what is underneath (Off / 40 / 60 / 90 px; `hover_radius` in `config.json`).
- `config.json` is created on first change and ignored by git.

## Make your own avatar
Copy `packs/default` to a new folder and replace the PNGs (all the same size, transparent background). Choose it in the
**Avatar** menu. If a pack is broken, nothing changes and the tray tooltip says why.

Image names: `<state>[_<n>][_talk][_blink].png`
- Required: `idle thinking working attention celebrating error waiting done` as `<state>.png`.
- `_talk` = mouth open, `_blink` = eyes closed, `_talk_blink` = both. Missing variants fall back (blink is dropped first,
  then talk).
- Extra animation frames: `working_2.png`, `working_3.png` ... (consecutive), played at `fps`.

`avatar.json` (optional): `{"name": "...", "fps": 8, "blink_min": 3.0, "blink_max": 6.0, "blink_ms": 120, "width": 200}`
(`width` is the window width in px used when someone picks this avatar).

### Building a pack from your own pixel art
`avatar/pixelate.py` cuts out a background and shrinks a picture to a clean pixel grid; `avatar/charpack.py` turns a
small sprite plus a description of its "eyes" into all the states (eye colours, looking up/down, chasing lights, blinking,
talking, bobbing or swinging, symbols). It is a library, see its docstring and `tests/test_charpack.py` for a complete
example. `python -m avatar.generate_pack` redraws the default pack.

## Develop
`..\.venv\Scripts\python.exe -m pytest -q` from this folder (offscreen Qt, no display needed).
