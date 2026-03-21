@echo off
REM ============================================================
REM Setup Example - VRMAgentHost boot-time setup sequence
REM Equivalent to API Test Console "Setup example" scenario
REM ============================================================

if "%~1"=="" (
    set SERVER=http://localhost:34560
) else (
    set SERVER=%~1
)

echo ===============================================
echo Setup Example - VRMAgentHost
echo ===============================================
echo.

echo [1/25] Load VRM (sample01)
curl "%SERVER%/?target=vrm&cmd=load&file=sample01.vrm"
echo.
timeout /t 1 >nul

echo [2/25] Enable LipSync (channel 0, scale 1)
curl "%SERVER%/?target=lipSync&cmd=audiosync_on&channel=0&scale=1"
echo.

echo [3/25] Enable auto blink (freq 1500)
curl "%SERVER%/?target=animation&cmd=auto_blink&enable=true&freq=1500"
echo.

echo [4/25] Allow drag objects
curl "%SERVER%/?target=server&cmd=allow_drag_objects&enable=true"
echo.

echo [5/25] Enable stay-on-top
curl "%SERVER%/?target=server&cmd=stay_on_top&enable=true"
echo.
timeout /t 1 >nul

echo [6/25] Enable FacePoke + SpringBone
curl "%SERVER%/?target=vrm&cmd=body_interaction&enable=true&useFacePoke=true&useSpringBone=true"
echo.
timeout /t 1 >nul

echo [7/25] Play Idle_calm_02 pose
curl "%SERVER%/?target=animation&cmd=play&id=Idle_calm_02&seamless=y"
echo.

echo [8/25] Hide wing menus
curl "%SERVER%/?target=wingsys&cmd=menus_hide"
echo.
timeout /t 1 >nul

echo [9/25] Wing menu labels face camera
curl "%SERVER%/?target=wingsys&cmd=labels&enable=true&face=camera&fg=FFFFFF&bg=00000080"
echo.
timeout /t 1 >nul

echo [10/25] Auto-hide wing menus after 60s
curl "%SERVER%/?target=wingsys&cmd=menus_hide&auto_hide=true&time=60000"
echo.
timeout /t 1 >nul

echo [11/25] Configure wing parameters
curl "%SERVER%/?target=wingsys&cmd=config&left_length=4&right_length=4&angle_delta=20&angle_start=0"
echo.
timeout /t 1 >nul

echo [12/25] Set wing shape
curl "%SERVER%/?target=wingsys&cmd=shape&blade_length=1.0&blade_edge=0.5&blade_modifier=0.0"
echo.
timeout /t 1 >nul

echo [13/25] Define default menus
curl "%SERVER%/?target=wingsys&cmd=menus_define&menu_left=exit,reset_shape,alpha,placeholder&menu_right=exit,reset_pose,resize_move,placeholder"
echo.
timeout /t 1 >nul

echo [14/25] Attach wing menus to avatar
curl "%SERVER%/?target=wingsys&cmd=follow_avatar&enable=true"
echo.
timeout /t 1 >nul

echo [15/25] Show wing menus
curl "%SERVER%/?target=wingsys&cmd=menus_show"
echo.
timeout /t 1 >nul

echo [16/25] Auto-hide resize/move UI after 15s
curl "%SERVER%/?target=server&cmd=resize_move_ui&auto_hide=true&time=15000"
echo.

echo [17/25] Overwrite chest depth to -0.03
curl "%SERVER%/?target=vrm&cmd=body_interaction&enable=true&useFacePoke=true&channel=chest&op=set&facePokeDepth=-0.03"
echo.

echo [18/25] Preset / channel=all (sphere)
curl "%SERVER%/?target=vrm&cmd=body_interaction&enable=true&useFacePoke=true&channel=all&op=set&facePokeRadius=0.03&facePokeForceGain=0.3&pokeMethod=sphere&pokeFalloffMultiplier=1.0&pokeHeight=0.05&pokeBaseStrength=0.005&pokeMaxDynamicStrength=0.015&pokeShapeScale=1.0&facePokeDepth=0.02&visibleFacePoke=false"
echo.

echo [19/25] Preset / channel=head (auto falloff)
curl "%SERVER%/?target=vrm&cmd=body_interaction&enable=true&useFacePoke=true&channel=head&op=set&facePokeRadius=0.02&facePokeForceGain=0.25&pokeMethod=sphere&pokeFalloffMultiplier=0&pokeHeight=0.04&pokeBaseStrength=0.004&pokeMaxDynamicStrength=0.012&pokeShapeScale=0.8&facePokeDepth=0.02&visibleFacePoke=false"
echo.

echo [20/25] Preset / channel=chest
curl "%SERVER%/?target=vrm&cmd=body_interaction&enable=true&useFacePoke=true&channel=chest&op=set&facePokeRadius=0.04&facePokeForceGain=0.4&pokeMethod=cone&pokeFalloffMultiplier=1.0&pokeHeight=0.06&pokeBaseStrength=0.008&pokeMaxDynamicStrength=0.02&pokeShapeScale=1.2&facePokeDepth=0.01&visibleFacePoke=false"
echo.

echo [21/25] Enable FacePoke + SpringBone (re-apply)
curl "%SERVER%/?target=vrm&cmd=body_interaction&enable=true&useFacePoke=true&useSpringBone=true"
echo.
timeout /t 1 >nul

echo [22/25] Load body partition settings
curl "%SERVER%/?target=vrm&cmd=body_partitioning&op=load&filename=body_partitions.json"
echo.
timeout /t 2 >nul

echo [23/25] Load anima definitions
curl "%SERVER%/?target=anima_system&cmd=load_defs&filename=anima_system_defs.json"
echo.

echo [24/25] Clear anima logs
curl "%SERVER%/?target=anima_system&cmd=clear_execute_logs"
echo.

echo [25/25] Start anima polling
curl "%SERVER%/?target=anima_system&cmd=polling&enable=true"
echo.

echo.
echo ===============================================
echo Setup Complete!
echo ===============================================
