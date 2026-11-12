@echo off
rem Starts the avatar window (a second copy exits by itself). Quit it from its tray icon.
cd /d "%~dp0"
if exist "%~dp0..\.venv\Scripts\pythonw.exe" (
  start "" "%~dp0..\.venv\Scripts\pythonw.exe" -m avatar.app
) else (
  start "" pythonw -m avatar.app
)
