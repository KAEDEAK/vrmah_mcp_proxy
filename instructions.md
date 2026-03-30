# VRM Agent Host API クイックリファレンス

本ドキュメントは基本的な操作コマンドのみを記載しています。
詳細なパラメータや高度な機能については `vrm-proxy://api-spec-detailed` リソースを参照してください。

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

## 詳細リファレンス

以下の機能については `vrm-proxy://api-spec-detailed` リソースを参照:

- Body Interaction（クリック/ドラッグ検知、Face Poke、SpringBone）
- Body Partitioning（部位カスタム定義）
- IK/FK 制御（四肢の位置/回転制御、アニメーション）
- 瞬きの片目制御（blink_left/blink_right）
- 画像オーバーレイ（image）
- 重力・SpringBone 物理制御
- Wing Menu 詳細設定（色、形状、ハイライト）
- 設定ファイル（config.json）の詳細
- Debug Telemetry / Debug Status
