@ECHO OFF
ECHO xbot Demo
ECHO Relative file path: %~dp0main.py
uv run %~dp0main.py
PAUSE