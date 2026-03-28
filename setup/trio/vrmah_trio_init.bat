@echo off
REM ============================================================
REM vrmah_trio_init.bat
REM VRM Agent Host x3 レイアウト再現バッチ
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
echo VRM Agent Host Trio - Initializing layout...
echo ============================================================

REM --- Instance 1: port 34560 (右側, 斜め45度) ---
echo.
echo [1/3] Instance 34560 - Window + Avatar setup...
curl -s "http://%HOST%:34560?target=server&cmd=resize_move&left=1474&top=605&width=933&height=788"
curl -s "http://%HOST%:34560?target=vrm&cmd=setLoc&xyz=0,0.3,-1"
curl -s "http://%HOST%:34560?target=vrm&cmd=setRot&xyz=0,45,0"
curl -s "http://%HOST%:34560?target=camera&cmd=fov&value=45"
curl -s "http://%HOST%:34560?target=animation&cmd=play&id=Idle_energetic&seamless=y"
curl -s "http://%HOST%:34560?target=wingsys&cmd=follow_avatar&enable=true"
curl -s "http://%HOST%:34560?target=server&cmd=stay_on_top&enable=true"
echo     Done.

REM --- Instance 2: port 34562 (左側, 斜め315度) ---
echo.
echo [2/3] Instance 34562 - Window + Avatar setup...
curl -s "http://%HOST%:34562?target=server&cmd=resize_move&left=106&top=606&width=910&height=789"
curl -s "http://%HOST%:34562?target=vrm&cmd=setLoc&xyz=0,0.3,-1"
curl -s "http://%HOST%:34562?target=vrm&cmd=setRot&xyz=0,315,0"
curl -s "http://%HOST%:34562?target=camera&cmd=fov&value=45"
curl -s "http://%HOST%:34562?target=animation&cmd=play&id=Idle_cute&seamless=y"
curl -s "http://%HOST%:34562?target=wingsys&cmd=follow_avatar&enable=true"
curl -s "http://%HOST%:34562?target=server&cmd=stay_on_top&enable=true"
echo     Done.

REM --- Instance 3: port 34564 (中央, 正面やや上向き) ---
echo.
echo [3/3] Instance 34564 - Window + Avatar setup...
curl -s "http://%HOST%:34564?target=server&cmd=resize_move&left=888&top=606&width=679&height=787"
curl -s "http://%HOST%:34564?target=vrm&cmd=setLoc&xyz=0,0.3,-1.3"
curl -s "http://%HOST%:34564?target=vrm&cmd=setRot&xyz=10,0,0"
curl -s "http://%HOST%:34564?target=camera&cmd=fov&value=45"
curl -s "http://%HOST%:34564?target=animation&cmd=play&id=Idle_energetic&seamless=y"
curl -s "http://%HOST%:34564?target=wingsys&cmd=follow_avatar&enable=true"
curl -s "http://%HOST%:34564?target=server&cmd=stay_on_top&enable=true"
echo     Done.

echo.
echo ============================================================
echo All 3 instances configured successfully!
echo   34560: right  (1474,605)  933x788  rot(0,45,0)
echo   34562: left   (106,606)   910x789  rot(0,315,0)
echo   34564: center (888,606)   679x787  rot(10,0,0)
echo ============================================================
