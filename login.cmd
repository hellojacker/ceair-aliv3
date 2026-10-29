@echo off
rem ============================================================
rem  China Eastern login one-shot (double-click to run):
rem  solve slider -> send SMS -> type code -> login -> verify
rem  Extra args are passed through, e.g.:  login.cmd --dry-run
rem ============================================================
chcp 65001 > nul
cd /d "%~dp0"
set CEAIR_NO_PAUSE=1
if not exist ".venv\Scripts\python.exe" (
    echo Missing .venv. Build it first:
    echo     python -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)
".venv\Scripts\python.exe" submit_requests.py %*
set RC=%ERRORLEVEL%
echo.
pause
exit /b %RC%