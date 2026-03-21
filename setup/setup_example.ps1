# ============================================================
# Setup Example - VRMAgentHost boot-time setup sequence
# Equivalent to API Test Console "Setup example" scenario
# ============================================================

param(
    [string]$Server = "http://localhost:34560"
)


function Invoke-Step {
    param(
        [string]$StepLabel,
        [string]$Query,
        [int]$WaitMs = 0
    )
    Write-Host $StepLabel -ForegroundColor Cyan
    try {
        $response = Invoke-WebRequest -Uri "$Server/?$Query" -UseBasicParsing -ErrorAction Stop
        Write-Host $response.Content
    } catch {
        Write-Host "  ERROR: $_" -ForegroundColor Red
    }
    if ($WaitMs -gt 0) {
        Start-Sleep -Milliseconds $WaitMs
    }
}

Write-Host "===============================================" -ForegroundColor Yellow
Write-Host "Setup Example - VRMAgentHost"                    -ForegroundColor Yellow
Write-Host "===============================================" -ForegroundColor Yellow
Write-Host ""

Invoke-Step "[1/25] Load VRM (sample01)" `
    "target=vrm&cmd=load&file=sample01.vrm" -WaitMs 1000

Invoke-Step "[2/25] Enable LipSync (channel 0, scale 1)" `
    "target=lipSync&cmd=audiosync_on&channel=0&scale=1"

Invoke-Step "[3/25] Enable auto blink (freq 1500)" `
    "target=animation&cmd=auto_blink&enable=true&freq=1500"

Invoke-Step "[4/25] Allow drag objects" `
    "target=server&cmd=allow_drag_objects&enable=true"

Invoke-Step "[5/25] Enable stay-on-top" `
    "target=server&cmd=stay_on_top&enable=true" -WaitMs 1000

Invoke-Step "[6/25] Enable FacePoke + SpringBone" `
    "target=vrm&cmd=body_interaction&enable=true&useFacePoke=true&useSpringBone=true" -WaitMs 1000

Invoke-Step "[7/25] Play Idle_calm_02 pose" `
    "target=animation&cmd=play&id=Idle_calm_02&seamless=y"

Invoke-Step "[8/25] Hide wing menus" `
    "target=wingsys&cmd=menus_hide" -WaitMs 1000

Invoke-Step "[9/25] Wing menu labels face camera" `
    "target=wingsys&cmd=labels&enable=true&face=camera&fg=FFFFFF&bg=00000080" -WaitMs 1000

Invoke-Step "[10/25] Auto-hide wing menus after 60s" `
    "target=wingsys&cmd=menus_hide&auto_hide=true&time=60000" -WaitMs 1000

Invoke-Step "[11/25] Configure wing parameters" `
    "target=wingsys&cmd=config&left_length=4&right_length=4&angle_delta=20&angle_start=0" -WaitMs 1000

Invoke-Step "[12/25] Set wing shape" `
    "target=wingsys&cmd=shape&blade_length=1.0&blade_edge=0.5&blade_modifier=0.0" -WaitMs 1000

Invoke-Step "[13/25] Define default menus" `
    "target=wingsys&cmd=menus_define&menu_left=exit,reset_shape,alpha,placeholder&menu_right=exit,reset_pose,resize_move,placeholder" -WaitMs 1000

Invoke-Step "[14/25] Attach wing menus to avatar" `
    "target=wingsys&cmd=follow_avatar&enable=true" -WaitMs 1000

Invoke-Step "[15/25] Show wing menus" `
    "target=wingsys&cmd=menus_show" -WaitMs 1000

Invoke-Step "[16/25] Auto-hide resize/move UI after 15s" `
    "target=server&cmd=resize_move_ui&auto_hide=true&time=15000"

Invoke-Step "[17/25] Overwrite chest depth to -0.03" `
    "target=vrm&cmd=body_interaction&enable=true&useFacePoke=true&channel=chest&op=set&facePokeDepth=-0.03"

Invoke-Step "[18/25] Preset / channel=all (sphere)" `
    "target=vrm&cmd=body_interaction&enable=true&useFacePoke=true&channel=all&op=set&facePokeRadius=0.03&facePokeForceGain=0.3&pokeMethod=sphere&pokeFalloffMultiplier=1.0&pokeHeight=0.05&pokeBaseStrength=0.005&pokeMaxDynamicStrength=0.015&pokeShapeScale=1.0&facePokeDepth=0.02&visibleFacePoke=false"

Invoke-Step "[19/25] Preset / channel=head (auto falloff)" `
    "target=vrm&cmd=body_interaction&enable=true&useFacePoke=true&channel=head&op=set&facePokeRadius=0.02&facePokeForceGain=0.25&pokeMethod=sphere&pokeFalloffMultiplier=0&pokeHeight=0.04&pokeBaseStrength=0.004&pokeMaxDynamicStrength=0.012&pokeShapeScale=0.8&facePokeDepth=0.02&visibleFacePoke=false"

Invoke-Step "[20/25] Preset / channel=chest" `
    "target=vrm&cmd=body_interaction&enable=true&useFacePoke=true&channel=chest&op=set&facePokeRadius=0.04&facePokeForceGain=0.4&pokeMethod=cone&pokeFalloffMultiplier=1.0&pokeHeight=0.06&pokeBaseStrength=0.008&pokeMaxDynamicStrength=0.02&pokeShapeScale=1.2&facePokeDepth=0.01&visibleFacePoke=false"

Invoke-Step "[21/25] Enable FacePoke + SpringBone (re-apply)" `
    "target=vrm&cmd=body_interaction&enable=true&useFacePoke=true&useSpringBone=true" -WaitMs 1000

Invoke-Step "[22/25] Load body partition settings" `
    "target=vrm&cmd=body_partitioning&op=load&filename=body_partitions.json" -WaitMs 2000

Invoke-Step "[23/25] Load anima definitions" `
    "target=anima_system&cmd=load_defs&filename=anima_system_defs.json"

Invoke-Step "[24/25] Clear anima logs" `
    "target=anima_system&cmd=clear_execute_logs"

Invoke-Step "[25/25] Start anima polling" `
    "target=anima_system&cmd=polling&enable=true"

Write-Host ""
Write-Host "===============================================" -ForegroundColor Green
Write-Host "Setup Complete!"                                 -ForegroundColor Green
Write-Host "===============================================" -ForegroundColor Green
