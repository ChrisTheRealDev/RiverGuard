@echo off
setlocal
cd /d "%~dp0"
python -m venv .venv
if errorlevel 1 goto failed
".venv\Scripts\python.exe" -m pip install -r requirements-lock.txt
if errorlevel 1 goto failed
echo V2 is ready. Open Start RiverGuard V2.cmd.
pause
exit /b 0
:failed
echo Setup failed. Install Python 3.14 with Python on PATH and retry.
pause
exit /b 1
