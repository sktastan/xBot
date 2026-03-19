@ECHO OFF
ECHO Relative file path: %~dp0app\src\updateDB.py
uv run %~dp0app\src\updateDB.py
PAUSE