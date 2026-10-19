REM ============================================================
REM  DeepThinkCompStock - P1 launcher (minimal/robust)
REM  Double-click to start, then open http://localhost:8899
REM ============================================================
@echo off
SETLOCAL EnableDelayedExpansion

set "PORT=8899"
set "PROJECT_DIR=%~dp0"
set "MANAGED_PYTHON=C:\Users\ht182\.workbuddy\binaries\python\versions\3.13.12\python.exe"

echo ============================================================
echo   DeepThinkCompStock - P1
echo ============================================================
echo    Python: %MANAGED_PYTHON%

REM ---------- Free port (dump netstat to temp file, then parse) ----------
echo.
echo [0/4] Freeing port %PORT% ...
set "FOUND=0"
set "NSFILE=%TEMP%\dtcs_ns_%RANDOM%.txt"
netstat -ano > "%NSFILE%" 2>nul
for /f "tokens=1-5" %%a in ('type "%NSFILE%" ^| findstr /c:":%PORT%"') do (
    if /i "%%d"=="LISTENING" if not "%%e"=="" (
        set "FOUND=1"
        echo    Killing stale PID %%e ...
        taskkill /F /PID %%e >nul 2>&1 && echo    Killed %%e || echo    [WARN] could not kill %%e (may belong to another session)
    )
)
del "%NSFILE%" 2>nul
if "%FOUND%"=="0" (
    echo    Port %PORT% already free - no kill needed.
) else (
    echo    Waiting for OS to release the socket ...
    ping -n 3 127.0.0.1 >nul
    echo    Port %PORT% clear.
)

REM ---------- Dependency self-check (core packages only) ----------
REM  server.py exits at import stage when deps are missing, so probe and install first.
echo.
echo [1/4] Checking core dependencies (fastapi/uvicorn/requests/httpx/pypinyin) ...
"%MANAGED_PYTHON%" -c "import fastapi,uvicorn,requests,httpx,pypinyin" >nul 2>&1
if errorlevel 1 (
    echo     Missing core deps - running pip install -r requirements.txt ...
    "%MANAGED_PYTHON%" -m pip install -r "%PROJECT_DIR%requirements.txt" --disable-pip-version-check --no-warn-script-location
    if errorlevel 1 (
        echo     [ERROR] pip install failed. Install manually:
        echo         "%MANAGED_PYTHON%" -m pip install -r "%PROJECT_DIR%requirements.txt"
        pause
        exit /b 1
    )
    echo     Dependencies installed.
) else (
    echo     Core deps OK.
)

REM ---------- Start ----------
echo.
echo [2/4] Starting server on http://localhost:%PORT%
echo         API docs: http://localhost:%PORT%/docs
echo         Press Ctrl+C to stop
echo ============================================================
echo.

cd /d "%PROJECT_DIR%"
"%MANAGED_PYTHON%" server.py --port %PORT%
set "RC=%errorlevel%"
echo.
echo    Server stopped (exit %RC%).
pause
ENDLOCAL
exit /b %RC%
