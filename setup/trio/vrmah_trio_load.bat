@echo off
REM ============================================================
REM vrmah_trio_load.bat
REM VRM Agent Host x3 モデルロード
REM 前提: 3つのインスタンスが既に起動済み (port 34560, 34562, 34564)
REM Generated: 2026-03-29
REM ============================================================

setlocal

if "%~1"=="" (
    set HOST=localhost
) else (
    set HOST=%~1
)

echo ============================================================
echo VRM Agent Host Trio - Loading VRM models...
echo ============================================================

echo.
echo [1/3] Instance 34560 - Loading sample01.vrm...
curl -s "http://%HOST%:34560?target=vrm&cmd=load&file=sample01.vrm"

echo.
echo [2/3] Instance 34562 - Loading sample05.vrm...
curl -s "http://%HOST%:34562?target=vrm&cmd=load&file=sample05.vrm"

echo.
echo [3/3] Instance 34564 - Loading sample02.vrm...
curl -s "http://%HOST%:34564?target=vrm&cmd=load&file=sample02.vrm"

echo.
echo ============================================================
echo All models loaded!
echo   34560: sample01.vrm
echo   34562: sample05.vrm
echo   34564: sample02.vrm
echo ============================================================
