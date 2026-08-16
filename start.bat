REM ============================================================
REM  DeepThinkCompStock - P1 launcher
REM  Double-click to start, then open http://localhost:8899
REM  Kills any process on the port first, then starts fresh.
REM ============================================================
@echo off
SETLOCAL EnableDelayedExpansion

echo ============================================================
echo   DeepThinkCompStock - P1 skeleton
echo ============================================================

REM ---------- Config ----------
set "PORT=8899"
set "PROJECT_DIR=%~dp0"
set "MANAGED_PYTHON=C:\Users\ht182\.workbuddy\binaries\python\versions\3.13.12\python.exe"

REM Fallback to system Python if managed not found
if not exist "%MANAGED_PYTHON%" (
    for %%p in (python3.exe python.exe py.exe) do (
        for /f "delims=" %%x in ('where %%p 2^>nul') do (
            if not defined FOUND set "MANAGED_PYTHON=%%x" & set "FOUND=1"
        )
    )
    if not defined FOUND (
        echo [ERROR] Python not found. Install Python 3.10+ first.
        pause
        exit /b 1
    )
)
echo    Python: %MANAGED_PYTHON%

REM ---------- Kill existing process on the port ----------
echo.
echo [0/3] Killing existing process on port %PORT% ...
for /f "tokens=5" %%p in ('netstat -aon ^| findstr /c:":%PORT% " ^| findstr /i "LISTENING"') do (
    taskkill /F /PID %%p >nul 2>&1 && echo    Killed PID %%p
)
ping -n 2 127.0.0.1 >nul
echo    Port %PORT% clear.

REM ---------- Install dependencies ----------
echo.
echo [1/3] Checking dependencies ...
"%MANAGED_PYTHON%" -c "import fastapi,uvicorn,requests,httpx,pypinyin" 2>nul
if errorlevel 1 (
    echo    Installing dependencies ...
    "%MANAGED_PYTHON%" -m pip install -r "%PROJECT_DIR%requirements.txt" -q
)

REM ---------- Start ----------
echo.
echo [2/3] Starting server on http://localhost:%PORT%
echo         API docs: http://localhost:%PORT%/docs
echo         Press Ctrl+C to stop
echo ============================================================
echo.

cd /d "%PROJECT_DIR%"
"%MANAGED_PYTHON%" server.py --port %PORT%

echo.
echo    Server stopped.
pause
ENDLOCAL
