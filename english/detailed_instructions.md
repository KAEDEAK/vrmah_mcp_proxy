This is VRM Agent Host - API Detailed Reference (vrm-proxy://api-spec-detailed)

This document covers all general-purpose commands for VRM Agent Host.
It summarizes command basics and lists available commands organized by target.

VRM Agent Host - Server-Side Specifications
- Provides server functionality for controlling VRoid via HTTP, built on Unity 6.
- HTTPS is not supported (if you need HTTPS, set up a reverse proxy or similar on your own).
- Some operations require a wait time before the next command (judge by HTTP status or the `succeeded` field in the response).
- Wing menu presets differ between the first and second application by design. This is due to parameter accumulation; the second application converges to the specified parameters.
- When changing wing menu presets or parameters, it is recommended to temporarily disable interaction using eventLock/eventUnlock.
- Non-standard VRoid models may not work because part names differ. Also, the initial position/rotation may not face forward upon loading.

Overview
- Listening endpoint: `http://localhost:34560/` (or the server/port specified by the user)
- Control method: send GET requests with `target` and `cmd` query parameters.
  Example: `http://localhost:34560/?target=vrm&cmd=load&file=model.vrm`
- Audio playback: send binary data to `POST /waveplay/` (RIFF/WAVE mono 16-bit 48kHz) for immediate playback.

Configuration load order (startup)
- Base: `Assets/Resources/default_config.json`
- Merge order: `config.json` -> `lastWindowBounds.json` -> `override_*.json` (ascending) -> `override.json`
- Merge rules: dictionaries are deep-merged, arrays are replaced, and false/0/empty values also overwrite. Invalid JSON is skipped with warnings.
- Save policy: runtime does not overwrite `config.json`. Even with `saveWindowBounds=true`, only `window.position` is written to `lastWindowBounds.json`.
  - Save location: project root (same directory as `config_dump.json`).

Quick start
- Check server status: `GET /?target=server&cmd=getstatus`
- Load a VRM: `GET /?target=vrm&cmd=load&file=model.vrm`
- Fill background color: `GET /?target=background&cmd=fill&color=FF0000`
- Play animation: `GET /?target=animation&cmd=play&id=Idle_generic&seamless=y`

Request basics
- Format: `GET /?target=<target>&cmd=<command>&<params...>`
- Example: `/?target=vrm&cmd=move&from=0,0,0&to=1,2,1&duration=1000&delta=10,80,10`
- In Windows `cmd.exe`, `%` is used for environment expansion. If your query includes `#RRGGBB`, escape `#` as `%23` (or `%%23` in `cmd.exe`).

Target-specific command list

vrm
Load VRM/VRM10, position/rotation control, and gaze control.

| cmd | Summary | Example |
| --- | --- | --- |
| load | Load a VRM file | `?target=vrm&cmd=load&file=model.vrm[&keep_posture=true]` |
| setLoc | Set position | `?target=vrm&cmd=setLoc&xyz=0,1,0` |
| getLoc | Get current position (includes VRM root, neck, spine coordinates) | `?target=vrm&cmd=getLoc` |
| getRot | Get current rotation (includes VRM root, neck, spine angles) | `?target=vrm&cmd=getRot` |
| setRot | Set rotation | `?target=vrm&cmd=setRot&xyz=0,90,0` |
| move | Interpolated movement | `?target=vrm&cmd=move&from=0,0,0&to=1,2,1&duration=1000&delta=10,80,10` |
| rotate | Interpolated rotation | `?target=vrm&cmd=rotate&from=0,0,0&to=0,180,0&duration=1000&delta=10,80,10` |
| stop_move | Stop movement process | `?target=vrm&cmd=stop_move` |
| stop_rotate | Stop rotation process | `?target=vrm&cmd=stop_rotate` |
| look | Set gaze angles directly | `?target=vrm&cmd=look&mode=deg&yaw=30&pitch=-15` |
| look_at_bone | Look at a specified bone | `?target=vrm&cmd=look_at_bone&bone=LeftHand` |
| look_at_camera | Look toward camera | `?target=vrm&cmd=look_at_camera` |
| gaze_control | Enable/disable gaze control | `?target=vrm&cmd=gaze_control&enable=true` |
| look_at_head | (Legacy) enable/disable gaze control | `?target=vrm&cmd=look_at_head&enable=false` |
| debug_lock_status | Check AGIA lock state | `?target=vrm&cmd=debug_lock_status` |
| debug_force_unlock | Force release AGIA lock | `?target=vrm&cmd=debug_force_unlock` |
| body_interaction | Enable body interaction (click/drag) | `?target=vrm&cmd=body_interaction&enable=true&useFacePoke=true|false&useSpringBone=true|false[&useFacePokeShader=true|false][&channel=all|head|chest|arms|lower]` |
| body_interaction_status | Get/edit body interaction state | `?target=vrm&cmd=body_interaction_status[...]` or `&op=edit&(...)` |
| body_partitioning | Partition definition/record/save | `?target=vrm&cmd=body_partitioning&op=set|rec_start|rec_end|reset|delete|save|load[...]` |
| body_partitioning_status | Get partition state (similar top-level structure to body_interaction_status) | `?target=vrm&cmd=body_partitioning_status[...]` |
| lock_pos | Position lock (gravity on/off) | `?target=vrm&cmd=lock_pos&enable=true[&ground_offset=0.5][&springbone_gravity=true][&springbone_power=1.0]` |
| springbone_gravity | SpringBone physics control (hair/clothes) | `?target=vrm&cmd=springbone_gravity&power=1.0[&stiffness=1.0][&drag=0.4][&radius=0.05][&category=hair][&part=TransformName]` |
| springbone_gravity_get | Get SpringBone physics settings | `?target=vrm&cmd=springbone_gravity_get` |

Example getLoc/getRot response (excerpt)
```json
{
  "status": 200,
  "data": {
    "pos_xyz": {"x": 0.0, "y": 0.0, "z": 0.0},
    "neck_xyz": {"x": 0.0, "y": 1.5, "z": 0.0},
    "spine_xyz": {"x": 0.0, "y": 1.2, "z": 0.0}
  }
}
```

Notes
- Gaze control is based on VRM10 standard LookAt (`Vrm10RuntimeLookAt`).
- Per-eye control using `eye` parameter is not supported in VRM10.
- If `load` is requested during AGIA playback, server returns `409 busy`.
- When `keep_posture=true` is specified, the current position/rotation is saved before loading and automatically restored after load (client-side processing).

Body Interaction (click/drag)
- Enable:
  - `?target=vrm&cmd=body_interaction&enable=true&useFacePoke=true|false&useSpringBone=true|false[&useFacePokeShader=true|false][&visibleCollider=true|false][&visibleFacePoke=true|false]`
- Independent toggles:
  - `useFacePoke`: CPU Face Poke
  - `useSpringBone`: SpringBone collider interaction
- Runtime condition: each feature runs only when `enable=true` and its own flag is true.
- Status: `?target=vrm&cmd=body_interaction_status`
  - add `&detailed=true` to include history and drag tracking fields
- Invalid usage: adding `enable` to `body_interaction_status` is invalid, returns 400 + `invalid parameter`.
- Coexistence policy: body interaction remains active even when wing menu is open. While RESIZE_MOVE UI is active, window operations are prioritized and interaction start/continue is blocked.

Visualization (debug/tuning)
- `visibleCollider=true`: show SpringBone reaction range as red spheres
- `visibleFacePoke=true`: show Face Poke deformation position/intensity as green spheres
- Show both: `visible=true` (legacy compatibility) or both explicit flags true

Simplified status schema
- Top-level: `clicked`, `dragged`, `dragging`
- `parts`: `standardName`, `modelName`, click/drag counters and timestamps, optional `feel`
- `detailed=true` adds:
  - `history`, `historySize`, `expirationMs`
  - while dragging: `dragPart`, `dragStart`, `dragCurrent`
  - when not dragging: `lastDrag`

Filter options
- `value=true|false`: clicked/not-clicked filter
- `equal=N`: exactly N clicks
- `greater=N` (or legacy typo `grater=N`): more than N clicks
- `less=N`: fewer than N clicks
- Multiple conditions are AND-combined
- Top-level `clicked`/`dragged` are recalculated after filtering

Edit mode (`op=edit`)
- `targetModelName=NAME` or `targetStandardName=NAME` required
- `clickCount=N` / `dragCount=N` (integer >= 0)
- `feel=TEXT` (max 255 chars). `feel=` clears the field.
- Setting a counter to 0 resets flags and timestamps
- Setting a counter >=1 sets flags true and timestamp to now

Examples
- `?target=vrm&cmd=body_interaction_status&op=edit&targetStandardName=UpperChest&clickCount=0`
- `?target=vrm&cmd=body_interaction_status&op=edit&targetModelName=J_Bip_C_Head&dragCount=5&feel=touched`
- `?target=vrm&cmd=body_interaction_status&op=edit&targetModelName=J_Bip_C_Head&feel=`

Implementation notes
- VRM0.x: adds a small sphere collider to target spring bones only while dragging
- VRM1.0 (FastSpringBone): applies local force near pointer joints and creates VRM10 springbone colliders dynamically
- Face Poke: CPU deformation or shader deformation (CPU recommended)

Optional key parameters
- Visualization: `visibleCollider`, `visibleFacePoke`, `visible`
- VRM1.0 control: `vrm10PointerCollider=true|false`
- Face Poke: `facePokeImplementation=cpu|shader`, `facePokeRadius`, `facePokeForceGain`
- Face Poke channel: `channel=all|head|chest|arms|lower`
- SpringBone only: `localRadius`, `localForce`, `falloff`, `maxJoints`, `patterns`
- Distance control: `springBonePointerDepth`, `facePokeDepth`
- Collider sizing: `springBonePointerRadius`, `springBonePointerDepth`

Examples
```text
# FacePoke only
?target=vrm&cmd=body_interaction&enable=true&useFacePoke=true&useSpringBone=false&facePokeRadius=0.03&facePokeForceGain=0.3

# SpringBone only
?target=vrm&cmd=body_interaction&enable=true&useFacePoke=false&useSpringBone=true&localRadius=0.06&localForce=1.5

# Both enabled
?target=vrm&cmd=body_interaction&enable=true&useFacePoke=true&useSpringBone=true&facePokeRadius=0.03&localRadius=0.06
```

Body Partitioning (summary)
- Purpose: define subregions inside head/chest/arms/lower (for example ears and eyes) and aggregate click/drag by those regions
- Define: `?target=vrm&cmd=body_partitioning&op=set&tune_target=<standardName|modelName>&partition_id=1&partition_name=left_ear`
- Record flow: `op=rec_start&partition_id=1` -> drag to sample -> `op=rec_end[&dilate=0.005]`
- Status: `body_partitioning_status` includes `enabled/parts/clicked/dragged/dragging`
- Filters: `value/equal/greater/less` are applied to `clickCount` with AND logic

background
Set background image or solid color.

| cmd | Summary | Example |
| --- | --- | --- |
| load | Set background image | `?target=background&cmd=load&file=bg.png` |
| fill | Fill with solid color | `?target=background&cmd=fill&color=FF0000` |
| transparent | Enable alpha-blended transparent window | `?target=background&cmd=transparent&enable=true` |

In Windows `cmd.exe`, if using `color=%23FF0000`, write `%%23...` due to `%` expansion. Both `RRGGBB` and `#RRGGBB` are accepted.

image
Image overlay and destination control.

| cmd | Summary | Example |
| --- | --- | --- |
| enable | Enable image overlay and update default autohide time | `?target=image&cmd=enable&enable=true&autohide=15000` |
| clear | Clear currently displayed image | `?target=image&cmd=clear` |
| status | Get display status | `?target=image&cmd=status` |
| size | Set/get size and unit | `?target=image&cmd=size&w=80&h=60&unit=percent` |
| show | Show last received image again | `?target=image&cmd=show` |
| set_destination | Switch image destination | `?target=image&cmd=set_destination&where=image_display` |
| reset_eyes | Restore eye textures | `?target=image&cmd=reset_eyes` |
| eyes_debug | Get eye texture diagnostics | `?target=image&cmd=eyes_debug` |

world
World gravity settings.

| cmd | Summary | Example |
| --- | --- | --- |
| gravity | Set gravity vector and enable state | `?target=world&cmd=gravity&part=world&xyz=0,-9.81,0&enable=true` |
| gravity_get | Get current gravity settings | `?target=world&cmd=gravity_get` |

Gravity and SpringBone control
- Gravity system includes world gravity, avatar position lock, and SpringBone physics
- `lock_pos`:
  - `enable=true`: keep avatar fixed in air
  - `enable=false`: gravity enabled
  - `springbone_gravity=true`: keep hair/clothes gravity while position is locked
- `springbone_gravity`: control `power`, `stiffness`, `drag`, `radius`
  - global / category (`hair|chest|arms|lower|body`) / part scope
- Priority: part > category > global

animation
AGIA playback, blend shapes, blink and mouth control.

| cmd | Summary | Example |
| --- | --- | --- |
| reset | Reset animation state (including lock) | `?target=animation&cmd=reset` |
| play | Play by ID or vrma file | `?target=animation&cmd=play&id=Idle_generic&seamless=y` |
| stop | Stop | `?target=animation&cmd=stop` |
| resume | Resume | `?target=animation&cmd=resume` |
| getstatus | Get status (includes neck/spine coordinates) | `?target=animation&cmd=getstatus&opt=alias` |
| shape | BlendShape control (`Relaxed/Angry/Aa/Ih/Ou/Ee/Oh`) | `?target=animation&cmd=shape&word=Relaxed&seamless=y&refresh=y` |
| mouth | Mouth shape control (`A/I/U/E/O`) | `?target=animation&cmd=mouth&word=A&seamless=y&refresh=y` |
| auto_prepare_seamless | Configure seamless pre-setup | `?target=animation&cmd=auto_prepare_seamless&enable=true` |
| get_auto_prepare_seamless | Get seamless pre-setup status | `?target=animation&cmd=get_auto_prepare_seamless` |
| reset_blink | Reset blink | `?target=animation&cmd=reset_blink&seamless=y` |
| reset_mouth | Reset mouth shape | `?target=animation&cmd=reset_mouth&seamless=y` |
| auto_blink | Configure auto blink | `?target=animation&cmd=auto_blink&enable=true&freq=2000` |
| debug_lock_status | Check AGIA lock state | `?target=animation&cmd=debug_lock_status` |
| debug_force_unlock | Force release AGIA lock | `?target=animation&cmd=debug_force_unlock` |

Important parameters
- `seamless`: `y`/`n` (default `n`)
- `refresh`: reset expressions before applying (`y`/`n`, default `y`)
- `continue`: loop playback for vrma files (`y`/`n`, default `n`)

Blink control in `shape`
- `blink=left,right` (0-1)
- `blink_left` / `blink_right` for per-eye control
- `keep_other=y|n`: keep opposite eye value in per-eye mode
- Deprecated: `side` returns 400
- Invalid combinations (`blink` with per-eye params) return 400

ik
Inverse Kinematics control for limbs (Animation Rigging TwoBoneIKConstraint based).

| cmd | Summary | Example |
| --- | --- | --- |
| setup | Create/initialize IK rig for loaded VRM | `?target=ik&cmd=setup` |
| set | Set limb position/rotation | `?target=ik&cmd=set&limb=RightArm&pos=0.25,1.35,0.2&rot=0,0,0&weight=1&coord=local` |
| get | Get current limb state | `?target=ik&cmd=get&limb=RightArm` |
| enable | Enable/disable IK globally or per limb | `?target=ik&cmd=enable&enable=true` |
| play | Play IK animation / apply specific frame | `?target=ik&cmd=play&anim_name=wave_hands` |
| stop | Stop IK animation playback | `?target=ik&cmd=stop` |
| animation&op=load | Load animations from JSON file | `?target=ik&cmd=animation&op=load&file=ik_animation_presets.json` |
| animation&op=save | Save animations to JSON file | `?target=ik&cmd=animation&op=save&file=ik_animation_presets.json` |
| animation&op=list | List loaded animation names | `?target=ik&cmd=animation&op=list` |
| animation&op=inspect | Inspect animation details | `?target=ik&cmd=animation&op=inspect&anim_name=wave_hands` |
| animation&op=status | Show frame count and frame list | `?target=ik&cmd=animation&op=status&anim_name=wave_hands` |
| animation&op=edit | Add/update frame parts | `?target=ik&cmd=animation&op=edit&...` |
| animation&op=edit_clip | Configure clip loop range | `?target=ik&cmd=animation&op=edit_clip&...` |
| animation&op=delete_part | Delete part from a frame | `?target=ik&cmd=animation&op=delete_part&...` |
| animation&op=delete_frame | Delete frame | `?target=ik&cmd=animation&op=delete_frame&...` |
| animation&op=delete | Delete animation | `?target=ik&cmd=animation&op=delete&anim_name=wave_hands` |

IK/FK notes
- `coord=global`: world coordinates
- `coord=local`: coordinates relative to VRM root
- IK default is global; FK default is local
- Animation Rigging package is required for IK
- File I/O is restricted to `.json` under project root

fk
Forward Kinematics direct control for humanoid bones.

| cmd | Summary | Example |
| --- | --- | --- |
| set | Set bone position/rotation | `?target=fk&cmd=set&bone=RightHand&rot=40,10,10&coord=local` |
| get | Get bone state | `?target=fk&cmd=get&bone=RightHand` |
| push | Push FK override stack | `?target=fk&cmd=push` |
| pop | Pop FK override stack | `?target=fk&cmd=pop` |
| reset | Clear FK overrides | `?target=fk&cmd=reset` |
| enable | Enable/disable FK globally | `?target=fk&cmd=enable&enable=true` |
| pose_save | Save named pose | `?target=fk&cmd=pose_save&pose_name=my_pose` |
| pose_overwrite | Overwrite named pose | `?target=fk&cmd=pose_overwrite&pose_name=my_pose` |
| pose_load | Load named pose | `?target=fk&cmd=pose_load&pose_name=my_pose` |
| pose_delete | Delete named pose | `?target=fk&cmd=pose_delete&pose_name=my_pose` |
| pose_file&op=save | Save poses to JSON | `?target=fk&cmd=pose_file&op=save&file=pose_presets.json` |
| pose_file&op=load | Load poses from JSON | `?target=fk&cmd=pose_file&op=load&file=pose_presets.json` |

lipSync
Audio-driven mouth control.

| cmd | Summary | Example |
| --- | --- | --- |
| getstatus | Get current state | `?target=lipSync&cmd=getstatus` |
| audiosync | Start lip sync (`channel=1` for output audio) | `?target=lipSync&cmd=audiosync&channel=1&scale=3` |
| audiosync_on | Same as audiosync (start) | `?target=lipSync&cmd=audiosync_on&channel=1&scale=3` |
| audiosync_off | Stop lip sync | `?target=lipSync&cmd=audiosync_off` |

Channel IDs
- 0: WavePlayback
- 1: ExternalAudio (WASAPI loopback, Windows)
- 2: Microphone (default)

server
Window/transparency/WAVE playback/config reload/debug endpoints.

| cmd | Summary | Example |
| --- | --- | --- |
| transparent | Enable/disable chroma-key transparent window | `?target=server&cmd=transparent&enable=true` |
| allow_drag_objects | Enable/disable drag operations | `?target=server&cmd=allow_drag_objects&enable=true` |
| stay_on_top | Always-on-top | `?target=server&cmd=stay_on_top&enable=true` |
| pointer_events_none | Mouse event pass-through | `?target=server&cmd=pointer_events_none&enable=true` |
| getstatus | Get server status | `?target=server&cmd=getstatus&flt=web&limit=10` |
| terminate | Exit application | `?target=server&cmd=terminate` |
| waveplay_start | Enable wave playback listener | `?target=server&cmd=waveplay_start` |
| waveplay_stop | Pause playback and clear queue | `?target=server&cmd=waveplay_stop` |
| waveplay_reset | Clear playback queue only | `?target=server&cmd=waveplay_reset` |
| waveplay_status | Get listener status | `?target=server&cmd=waveplay_status` |
| waveplay_ping | Measure wave playback latency | `?target=server&cmd=waveplay_ping` |
| waveplay_volume | Get/set playback volume | `?target=server&cmd=waveplay_volume&value=1.0` |
| waveplay_concurrency | Get/set playback concurrency mode | `?target=server&cmd=waveplay_concurrency&type=interrupt` |
| reload_config | Reload config files | `?target=server&cmd=reload_config` |
| debugInfo | Get/control runtime telemetry | `?target=server&cmd=debugInfo` |
| diagnostics | Run a full server configuration check | `?target=server&cmd=diagnostics` |
| verify | Verify runtime file integrity against manifest | `?target=server&cmd=verify` |
| dump_config | Dump in-memory config to `config_dump.json` | `?target=server&cmd=dump_config` |
| bring_to_top | Set re-bring interval for topmost behavior | `?target=server&cmd=bring_to_top&value=30000` |
| resize_move_ui | Show/hide resize-move UI and auto-hide timer | `?target=server&cmd=resize_move_ui&enable=true&auto_hide=true&time=30000` |
| resize_move | Set VRM window rect | `?target=server&cmd=resize_move&left=100&top=100&width=1280&height=720` |

Diagnostics / verification
- `diagnostics`: No parameters. Returns `threat_level`, `threat_label`, `score`, `findings`, and `sections` (`wave_playback`, `image_display`, `body_interaction`, `network`, `config_provenance`, `system`).
- `verify`: No parameters. Verifies runtime files against `runtime_files.json` (Linux: `runtime_files_linux.json`) and returns `total_checked`, `skipped_permission`, `issue_count`, `unknown_files`, `modified_files`, `missing_files`, `type_mismatch`.

Debug telemetry
- Feature gate: `telemetryEnabled` in config.json
- If disabled: debug telemetry endpoints return errors (`503` / `422`)
- If enabled: collection can be toggled with `debugInfo&enable=true|false`

camera
Camera projection, placement, and auto-adjustment.

| cmd | Summary | Example |
| --- | --- | --- |
| orthographic | Set orthographic projection | `?target=camera&cmd=orthographic&enable=true&size=0.4` |
| adjust | Auto-adjust camera to loaded VRM | `?target=camera&cmd=adjust` |
| fov | Set field of view | `?target=camera&cmd=fov&value=60` |
| getstatus | Get camera status | `?target=camera&cmd=getstatus` |
| setLoc | Set camera position | `?target=camera&cmd=setLoc&xyz=0,1.5,-2` |
| setRot | Set camera rotation (Euler) | `?target=camera&cmd=setRot&xyz=0,180,0` |
| look_at_vrm | Rotate camera to VRM head | `?target=camera&cmd=look_at_vrm` |

light
Directional light alignment.

| cmd | Summary | Example |
| --- | --- | --- |
| moveto_camera | Align light position/rotation to camera | `?target=light&cmd=moveto_camera` |

credits
Use `target=credits` to return credits JSON.

wing menu system (`wingsys`)
Show up to 100 wing leaves per side behind the avatar. Clicking leaves triggers actions.

| cmd | Summary | Example |
| --- | --- | --- |
| menus_show | Show menu | `?target=wingsys&cmd=menus_show` / `&side=left` |
| menus_hide | Hide menu | `?target=wingsys&cmd=menus_hide` / `&side=right` |
| menus_define | Define menu items | `?target=wingsys&cmd=menus_define&menus=item1,item2` |
| menus_clear | Clear menu items | `?target=wingsys&cmd=menus_clear` |
| config | Change wing config | `?target=wingsys&cmd=config&left_length=4&right_length=4&angle_delta=20&angle_start=0` |
| shape | Set wing shape | `?target=wingsys&cmd=shape&blade_length=1.0&blade_edge=0.5&blade_modifier=0.0` |
| position | Set wing position | `?target=wingsys&cmd=position&xyz=0,1,0` |
| rotate | Set wing rotation | `?target=wingsys&cmd=rotate&xyz=0,90,0` |
| scale | Set wing scale | `?target=wingsys&cmd=scale&xyz=1,1,1` |
| color | Set wing color modes | `?target=wingsys&cmd=color&values=white,gaming,lightblue,yellow[,click]` |
| color_click_mode | Set click color mode only | `?target=wingsys&cmd=color_click_mode&mode=gaming` |
| click_highlight | Set click highlight duration | `?target=wingsys&cmd=click_highlight&duration=2.0` |
| color_status | Get color modes | `?target=wingsys&cmd=color_status` |
| highlight | Highlight wing leaves | `?target=wingsys&cmd=highlight&action=set&wing_index=0&duration=5.0` |
| follow_avatar | Enable auto follow avatar | `?target=wingsys&cmd=follow_avatar&enable=true` |
| menus_status | Get menu definition/config state | `?target=wingsys&cmd=menus_status` |
| labels | Configure ASCII labels | `?target=wingsys&cmd=labels&enable=true&fg=FFFFFF&bg=00000080&face=camera` |
| labels_status | Get label status | `?target=wingsys&cmd=labels_status` |
| menus_interaction_status | Get click/hover runtime state | `?target=wingsys&cmd=menus_interaction_status` |
| user_mode | Enable user menu preset mode | `?target=wingsys&cmd=user_mode&enable=true&base=USER` |
| export_shape | Export wing mesh shape to JSON | `?target=wingsys&cmd=export_shape` |
| import_shape | Import wing shape from JSON (POST) | `POST ?target=wingsys&cmd=import_shape` |

`multiple` target
- Run multiple commands sequentially in one request:
  - `?target=multiple&cmd=exec_all&target=vrm&cmd=load&file=model.vrm&target=animation&cmd=play&id=Idle_generic`

WAVE playback endpoint (`/waveplay/`)
- Endpoint: `POST /waveplay/` (`RIFF/WAVE mono 16-bit 48kHz`)
- Uses same HTTP port (`httpPort`)
- Disabled when `wavePlaybackEnabled=false`
- Headers: `X-Audio-ID`, `X-Volume`, `X-Speaker`, `X-Spatial`
- Success response: `200 OK {"status":"ok","id":"<X-Audio-ID>"}`
- Spatial mode follows avatar head position (`spatialBlend=1.0`)
- Volume range: `0.0` to `3.0` (`1.0` standard)

WAVE concurrency (`server: waveplay_concurrency`)
- Modes: `interrupt` (default) / `queue` / `reject`

Key `config.json` fields
Based on `Assets/Resources/default_config.json`:
- HTTP/HTTPS ports and enable flags (HTTPS currently unused)
- Localhost-only and allowed remote IP controls
- Output filters for getstatus
- Seamless preparation settings
- VSync / target framerate
- Wave playback options, volume, spatialization, payload limits
- Lip sync offset
- Concurrency mode
- Shadows
- Camera projection/FOV/AA/transform/head tracking
- File listing control
- Window behavior and bounds
- Materials/rim/outline
- Directional light config
- Verbose logging
- Animation ID mappings

`export_shape` / `import_shape`
- `export_shape` returns global wing settings and per-wing mesh vertices as JSON
- `import_shape` accepts exported JSON and applies `global_settings`
- Use cases: backup/restore, sharing shape presets across environments, debugging state snapshots

`labels` command
- Parameters:
  - `enable`: show/hide labels (optional)
  - `side`: `left` / `right` (default both)
  - `fg`: text color (`RRGGBB` or `RRGGBBAA`)
  - `bg`: background color (`RRGGBB` or `RRGGBBAA`)
  - `face`: `front` / `back` / `camera`

Interaction status
- Endpoint: `?target=wingsys&cmd=menus_interaction_status`
- Add `detailed=true` for click history
- Runtime click/hover state is handled by this endpoint, while `menus_status` focuses on menu definitions/config

Basic operations
- Left click: execute wing function (menu remains open)
- Right click: toggle menu open/close

Tests
- `TEST/` contains many batch scripts using `curl`
- Examples: `TEST/batch/cmd/animation_getstatus.bat`, `TEST/batch/cmd/waveplay_ping.bat`

Developer notes
- HTTPS is not implemented yet; related settings are placeholders
- Unity Editor always enables verbose logs
