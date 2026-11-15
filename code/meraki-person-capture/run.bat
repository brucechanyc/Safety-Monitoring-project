@echo off
REM ===== Run the Meraki person-detection capture on Windows =====
REM Double-click this file, or run it from a Command Prompt in this folder.

cd /d "%~dp0"

REM Use the venv Python if it exists, otherwise fall back to system Python.
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" main.py
) else (
    python main.py
)

pause
