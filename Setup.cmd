@echo off

setlocal

cd /d "%~dp0"

echo CAT Monitor online setup - Windows x64, Python 3.12 - requires PyPI access

if exist ".venv\Scripts\python.exe" goto install

if defined CAT_MONITOR_PYTHON (

  "%CAT_MONITOR_PYTHON%" -c "import sys,struct; assert sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8" || goto failed

  "%CAT_MONITOR_PYTHON%" -m venv ".venv" || goto failed

) else (

  py -3.12 -c "import sys,struct; assert sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8" || goto failed

  py -3.12 -m venv ".venv" || goto failed

)

:install

".venv\Scripts\python.exe" -c "import sys,struct; assert sys.version_info[:2] == (3,12) and struct.calcsize('P') == 8" || goto failed

".venv\Scripts\python.exe" -m pip install --index-url https://pypi.org/simple -r "requirements.txt" || goto failed

".venv\Scripts\python.exe" -m pip check || goto failed

".venv\Scripts\python.exe" "scripts\initialize.py" || goto failed

echo Setup complete. Double-click Launch CAT Monitor.cmd.

if not defined CAT_MONITOR_NONINTERACTIVE pause

exit /b 0

:failed

echo SETUP FAILED. Check the error above: Python 3.12, PyPI access, or folder permissions may need attention.

echo If Python is elsewhere, set CAT_MONITOR_PYTHON to its full python.exe path.

if not defined CAT_MONITOR_NONINTERACTIVE pause

exit /b 1

