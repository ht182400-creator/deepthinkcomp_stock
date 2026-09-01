REM ============================================================
REM  DeepThinkCompStock - 环境自检 / 修复（非侵入，不重启服务）
REM  用途：腾讯/东财行情报 TLS CA 证书错误、或启动报 ModuleNotFoundError 时，
REM        先跑本脚本确认并补装依赖，再手动重启服务。
REM  用法：双击，或在项目根目录执行 check_env.bat
REM ============================================================
@echo off
SETLOCAL EnableDelayedExpansion

set "PROJECT_DIR=%~dp0"
set "MANAGED_PYTHON=C:\Users\ht182\.workbuddy\binaries\python\versions\3.13.12\python.exe"

if not exist "%MANAGED_PYTHON%" (
    echo [ERROR] 找不到托管 Python：%MANAGED_PYTHON%
    pause & exit /b 1
)

echo ============================================================
echo   环境自检  %MANAGED_PYTHON%
echo ============================================================

REM ---------- 1) CA 证书包路径是否有效 ----------
echo.
echo [1/3] 检查 TLS CA 证书包（certifi）...
for /f "delims=" %%l in ('"%MANAGED_PYTHON%" -c "import os,certifi; p=certifi.where(); print('OK' if os.path.exists(p) else 'MISSING', p)" 2^>^&1') do set "CERT_LINE=%%l"
echo     %CERT_LINE%
echo     %CERT_LINE% | findstr /i "MISSING" >nul && set "NEED_FIX=1"

REM ---------- 2) 服务端依赖是否齐全 ----------
echo.
echo [2/3] 检查服务端依赖（fastapi/uvicorn/requests/httpx/pypinyin）...
"%MANAGED_PYTHON%" -c "import fastapi,uvicorn,requests,httpx,pypinyin; print('DEPS_OK')" >nul 2>&1
if errorlevel 1 (
    echo     依赖缺失，需要补装。
    set "NEED_FIX=1"
) else (
    echo     DEPS_OK
)

REM ---------- 3) 需要修复则重装依赖 ----------
echo.
if defined NEED_FIX (
    echo [3/3] 检测到问题，执行 pip install -r requirements.txt ...
    "%MANAGED_PYTHON%" -m pip install -r "%PROJECT_DIR%requirements.txt" -q
    echo     重装完成。请手动重启服务（双击 start.bat 或 python server.py --port 8899）。
) else (
    echo [3/3] 环境正常，无需修复。如仍报 TLS 错误，多半是旧服务进程未重启，请重启服务。
)

echo.
echo 完成。
ENDLOCAL
pause
