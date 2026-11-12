# read-aloud

A Claude Code `Stop` hook that reads Claude's final reply out loud. It returns in about 0.2 s and a detached worker does
the speaking, so Claude never waits. A new reply cancels the previous reading.

## Use it
```bash
python read_aloud.py on | off          read every reply automatically (or not)
python read_aloud.py stop              stop talking right now
python read_aloud.py say "text"        speak a sentence (a quick test)
python read_aloud.py voices            list Voice Studio's voices
python read_aloud.py voice <name>      pick a Voice Studio voice
python read_aloud.py engine auto|windows
python read_aloud.py speed 1.2
python read_aloud.py status
```
Run these with the repo's `.venv\Scripts\python.exe`. Settings live in `config.json` (created on first change, ignored
by git; see `config.example.json`).

## Voices
- **Windows voice** (always available): set `sapi_voice` in `config.json` to an installed voice name and `sapi_rate`
  (-10 to 10). List what is installed with
  `(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() | % { $_.VoiceInfo.Name }`.
  Only the classic "Desktop" voices work; Windows 11's "Natural" Narrator voices are not available to other programs.
  An unknown voice name falls back to the default voice.
- **Voice Studio** (optional): start the app, then `read_aloud.py voices` and `read_aloud.py voice <name>`. If it is not
  running, the hook falls back to the Windows voice.

## What gets read
Markdown is cleaned (code blocks are skipped with a short "code block" note, links and URLs are simplified), long
replies are cut at a sentence at `max_chars`, and speech starts after the first short chunk while the rest is prepared.

## Safety
The reply text never goes into a command line. It goes to Voice Studio as JSON over `127.0.0.1`, or to a fixed
PowerShell script through an environment variable. Non-local URLs are refused. The hook always exits 0 and prints nothing.
While audio plays it writes `state/speaking.json` (`speaking` plus an `until` time that expires by itself if the worker
is killed), which the avatar uses to move its mouth.

## If a reply is not spoken
Look at `state/hook.log`. Each reply adds one line (never the reply text): `hook: skipped (off)`, `hook: spawned worker`,
`worker: done`, or `hook: error <ExceptionType>` / `worker: error <ExceptionType>`. The hook reads Claude's message as
UTF-8, so emoji and accented characters are fine. A nearly full memory (for example a heavy AI tool running next to it)
can make the hook too slow; free some RAM or close that tool.

## Develop
`..\.venv\Scripts\python.exe -m pytest -q` from this folder.
