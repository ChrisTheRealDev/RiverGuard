@echo off
cd /d "%~dp0"
echo Installing RiverGuard dependencies. Internet is required for this step.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
if errorlevel 1 (
    echo Setup failed. Check the message above. Install Python 3.14 with PATH enabled first.
) else (
    echo Setup complete. See START HERE.txt to install Ollama for local Rill chat.
    echo Then double-click Start RiverGuard.cmd.
)
pause
