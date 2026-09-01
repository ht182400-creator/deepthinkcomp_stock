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
echo [0/3] Freeing port %PORT% ...
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

REM ---------- Start ----------
echo.
echo [1/3] Starting server on http://localhost:%PORT%
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
