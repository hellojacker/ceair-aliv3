@echo off
rem ---------------------------------------------------------------
rem  ceair project shell with the project-local virtualenv enabled.
rem  Double-click this file, then run e.g.:
rem      python ceair_solver.py --until-t001=1
rem      python submit_requests.py probe
rem  Fresh shell: type "exit".
rem ---------------------------------------------------------------
cd /d "%~dp0"
rem ??? .pyc?????? site-packages/__pycache__ ??? pyc ????? Crypto\Protocol\KDF.*.pyc?
set PYTHONDONTWRITEBYTECODE=1
if not exist ".venv\Scripts\python.exe" (
    echo [.] .venv is missing. Rebuild it with:
    echo     python -m venv .venv
    echo     .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
)
call ".venv\Scripts\activate.bat"
echo.
echo (ceair) virtualenv active: %VIRTUAL_ENV%
".venv\Scripts\python.exe" -c "import sys;print('  python', sys.version.split()[0])"
echo   try: python check_env.py
echo.
cmd /k
