# VRM Agent Host API クイックリファレンス

本ドキュメントで基本操作の大半をカバーしています。ここに記載のないコマンドのみ `vrm-proxy://api-spec-detailed` を参照してください。

## http で直接制御する場合(mcpではない場合)
待受ポート: `http://localhost:34560/` (または ユーザーが指定したサーバー・ポート)
リクエスト形式: `GET /?target=<対象>&cmd=<コマンド>&<パラメータ...>`

---
## 初期設定
以下のスクリプトで VRMモデルのロード～メニュー調整、Lipsync設定、位置調整などが一括で可能
- setup/setup_example.bat
- setup/setup_example.sh
- setup/setup_example.ps1

## VRM モデル

### ロード
```
?target=vrm&cmd=load&file=model.vrm
```

### 位置・回転の取得
```
?target=vrm&cmd=getLoc
?target=vrm&cmd=getRot
```

---

## アニメーション

### 再生
```
?target=animation&cmd=play&id=Idle_generic&seamless=y
```

主なアニメーションID:
- `Idle_generic` / `Idle_cute` / `Idle_calm` - 待機
- `Angry_01` / `Brave_01` / `Shy_01` - 感情表現
- `Layer_look_away` - 視線そらし

### 停止・再開・リセット
```
?target=animation&cmd=stop
?target=animation&cmd=resume
?target=animation&cmd=reset
```

### 状態取得
```
?target=animation&cmd=getstatus
```
- `currentAnimationElapsedSeconds`: 現在のアニメーション維持時間（秒）。アニメーションが変わった時のみリセット。

---

## 表情・口・瞬き

### 表情
```
?target=animation&cmd=shape&word=Relaxed&seamless=y
?target=animation&cmd=shape&word=Angry&seamless=y
```
表情: `Relaxed`, `Angry`, `Aa`, `Ih`, `Ou`, `Ee`, `Oh`

### 口形状
```
?target=animation&cmd=mouth&word=A&seamless=y
?target=animation&cmd=reset_mouth&seamless=y
```

### 瞬き
```
?target=animation&cmd=shape&blink=0,1&seamless=y
?target=animation&cmd=reset_blink&seamless=y
```
blink=左,右 (0=開, 1=閉)

### 自動瞬き
```
?target=animation&cmd=auto_blink&enable=true&freq=2000
?target=animation&cmd=auto_blink&enable=false
```

---

## 視線制御

### 視線自動追従のオン/オフ
```
?target=vrm&cmd=gaze_control&enable=true
?target=vrm&cmd=gaze_control&enable=false
```

### カメラを見る
```
?target=vrm&cmd=look_at_camera
```

### 視線角度を直接指定
```
?target=vrm&cmd=look&mode=deg&yaw=30&pitch=-15
```

---

## リップシンク

### 音声同期開始（出力音声）
```
?target=lipSync&cmd=audiosync&channel=1&scale=3
```
channel: 0=WavePlayback, 1=ExternalAudio(WASAPI), 2=Microphone

### 停止
```
?target=lipSync&cmd=audiosync_off
```

### 状態取得
```
?target=lipSync&cmd=getstatus
```

---

## 羽メニュー (Wing Menu)

### 表示・非表示
```
?target=wingsys&cmd=menus_show
?target=wingsys&cmd=menus_hide
?target=wingsys&cmd=menus_show&side=left
?target=wingsys&cmd=menus_hide&side=right
```

### 状態取得
```
?target=wingsys&cmd=menus_status
```

### ラベル表示
```
?target=wingsys&cmd=labels&enable=true&face=camera
?target=wingsys&cmd=labels&enable=false
```

### イベントロック（設定変更中のクリック無効化）
```
?target=wingsys&cmd=eventLock
?target=wingsys&cmd=eventUnlock
```

---

## 背景

### 単色塗りつぶし
```
?target=background&cmd=fill&color=FF0000
?target=background&cmd=fill&color=00FF00
```

### 透過ウィンドウ
```
?target=background&cmd=transparent&enable=true
?target=background&cmd=transparent&enable=false
```

---

## サーバー・ウィンドウ

### サーバー状態
```
?target=server&cmd=getstatus
```

### 最前面
```
?target=server&cmd=stay_on_top&enable=true
```

### マウスイベント透過
```
?target=server&cmd=pointer_events_none&enable=true
```

### サーバー診断
サーバーの設定状態を一括診断し、確認が必要な項目を提示します。
```
?target=server&cmd=diagnostics
```
- パラメータなし
- 診断対象: WavePlayback, 画像受信, Body Interaction, ネットワーク, Config Override, システム状態
- レスポンス: `threat_level`(0-4), `threat_label`(SAFE/NOTICE/CAUTION/WARNING/DANGER), `findings`(確認項目), `sections`(各セクション詳細)
- 用途: 現在の設定が意図したものか確認する際に利用。意図しない設定がある場合は見直しを検討してください。

### ファイル整合性検証
実行ディレクトリのファイル整合性をマニフェスト（`runtime_files.json` / Linux は `runtime_files_linux.json`）と照合します。
```
?target=server&cmd=verify
```
- パラメータなし
- レスポンス: `total_checked`, `skipped_permission`, `issue_count`, `unknown_files`, `modified_files`, `missing_files`, `type_mismatch`
- 判定の目安: `issue_count=0` なら問題なし。`issue_count>0` の場合は、返却された配列を確認して改変・欠落・未知ファイルを特定してください。

---

## 音声再生

### Wave再生（POST）
```
POST /waveplay/
Content-Type: application/octet-stream
(RIFF/WAVE mono 16bit 48kHz バイナリ)
```

### 再生制御
```
?target=server&cmd=waveplay_start
?target=server&cmd=waveplay_stop
?target=server&cmd=waveplay_volume&value=1.0
```

---

## カメラ

### VRMに合わせて調整
```
?target=camera&cmd=adjust
```

### VRMを見る
```
?target=camera&cmd=look_at_vrm
```

---

---

## VOICEVOX 音声合成

VOICEVOX が設定されている場合、テキストを音声合成して VRM Agent Host で再生できます。

### 音声合成・再生
```
voicevox_speak ツールを使用
  text: "こんにちは"
  speaker_id: 43  (省略可)
  speed_scale: 1.0  (省略可)
  volume_scale: 1.0  (省略可)
```

### スピーカー一覧取得
```
voicevox_speakers ツールを使用
```

設定は `vrmah_mcp_proxy/config.json` で行います:
```json
{
  "version": 2.0,
  "vrmah": {
    "host": "http://<ip-address-vrmah>:34560",
    "candidates": ["http://<ip-address-vrmah-candidate>:34560"]
  },
  "voice": {
    "type": "voicebox",
    "server": "http://<ip-address-voicevox>:50021",
    "candidates": ["http://<ip-address-voicevox-candidate>:50021", "http://<ip-address-vrmah>:50021"],
    "name": "櫻歌ミコ",
    "speaker_uuid": "...",
    "style_id": 43
  }
}
```

---

## FK（Forward Kinematics）

### 基本操作
```
?target=fk&cmd=enable&enable=true
?target=fk&cmd=set&bone=Hips&rot=10,20,0
?target=fk&cmd=get&bone=Hips&coord=global
?target=fk&cmd=get_all&bones=main
?target=fk&cmd=reset
```

### ボーンマスク（IK 併用時に有用）
```
?target=fk&cmd=set_mask&exclude=LeftUpperLeg,LeftLowerLeg,LeftFoot,RightUpperLeg,RightLowerLeg,RightFoot
?target=fk&cmd=get_mask
?target=fk&cmd=clear_mask
```

### FK アニメーションクリップ再生
```
?target=fk&cmd=play&file=ik-abcd1234.vrm.json&loop=n&speed=1.0&blend=0.25
?target=fk&cmd=stop&reset=y
?target=fk&cmd=animation&op=list_files
?target=fk&cmd=animation&op=inspect&file=ik-abcd1234.vrm.json
```

`FK_FOLDER` 配下の VRM humanoid FK clip JSON (`vrm_humanoid_fk_major_v1` schema) を再生する。事前に `fk enable=true` を呼ぶ必要がある。

### FK クリップアップロード (POST)
```
POST ?target=fk&cmd=upload_clip&name=ik-abcd1234
Content-Type: application/json
body: <FK clip JSON object>
```

VRM humanoid FK クリップを `FK_FOLDER/<name>.vrm.json` に保存する。`name` は `[A-Za-z0-9_-]{1,64}`、body サイズ上限 8 MB、重複は 409。`soma_to_vrm` 自動再生パイプライン (下記 `fk_generate_and_play`) から呼ばれる。

### MCP Proxy ヘルパーツール（FK 用）

VRM Agent Host API を組み合わせた高レベル操作。MCP ツールとして利用可能。

| ツール | 概要 |
|--------|------|
| `fk_sample_pose` | アニメーション中に N 回サンプリングし、各ボーンの min/max/avg 統計を返す |
| `fk_snapshot_to_frame` | 現在の FK ボーン回転を IK アニメーションフレームとして保存（rotation のみ） |
| `fk_rotate_delta` | 指定ボーンに相対回転を加算（coord=global 対応） |
| `fk_generate_and_play` | テキストから FK アニメーションを生成して再生 (soma_to_vrm 自動再生パイプライン) |

- `bones` パラメータ: `"main"` で主要18ボーン、カンマ区切りボーン名（例: `"Hips,Spine,Head"`）で任意フィルタ、省略で全ボーン

#### `fk_generate_and_play`

1 回のツール呼び出しで「テキスト → soma_to_vrm 推論 → upload_clip → fk play」を完結する。

入力 (`inputSchema`):

| 名前 | 型 | 必須 | デフォルト | 範囲/制約 |
|------|----|------|----------|----------|
| `text` | string | YES | — | 1-2048 文字。動作のテキスト記述 |
| `pose_type` | string | NO | `"T"` | `"T"` / `"A"` |
| `loop` | boolean | NO | `false` | — |
| `speed` | number | NO | `1.0` | 0.1-5.0 |
| `blend` | number | NO | `0.25` | 0.0-5.0 (秒) |
| `auto_enable_fk` | boolean | NO | `true` | `true` で `fk enable=true` を内部発行 |

返り値 (`structuredContent`): `{ok, job_id, idempotency_key, clip_name, clip_file, clip_bytes, frame_count, fps, auto_enable_fk, play_response}`

エラー時 `{ok:false, error, ...}` (HTTP status / `retry_after_ms` 等を含む場合あり)。

挙動:
- `idempotency_key = "ik-" + uuid16` を払い出し、soma_to_vrm の `POST /generate` へ submit
- 同期完了 (200) なら poll をスキップ、202 なら `GET /jobs/<id>` を 3 秒 × 5 回 poll
- transport failure のみ同一 `idempotency_key` で submit を最大 2 回再試行
- poll 中の 4xx/500 は確定失敗として即中断 (5xx は破棄、4xx は status を返す)
- 結果クリップを `GET /jobs/<id>/file` で取得し、`upload_clip` で VRM Agent Host へアップロード後、`fk enable` (任意) → `fk stop&reset=y` → `fk play` を発行

設定: `config.json` に以下を追加:
```json
"soma_to_vrm": {
  "host": "http://<ip-address-vrmah>:9571",
  "candidates": ["http://localhost:9571"]
}
```

---

## IK（Inverse Kinematics）

### 基本操作
```
?target=ik&cmd=enable&enable=true
?target=ik&cmd=set&limb=LeftLeg&weight=1&enable=true
?target=ik&cmd=get&limb=LeftLeg
?target=ik&cmd=reset
```

### FK + IK 連携（上半身 FK + 脚 IK 固定）
```
1. fk enable&enable=true + ik enable&enable=true
2. fk set_mask で脚ボーン除外
3. ik set で両脚 weight=1
4. fk set で上半身回転 → 脚は自動的にワールド位置を維持
```

---

## 詳細リファレンス

上記で見つからないコマンド（Body Interaction, Body Partitioning, 画像オーバーレイ, 重力・SpringBone, Wing Menu 詳細設定, config.json 詳細, Debug 等）は `vrm-proxy://api-spec-detailed` を参照。
