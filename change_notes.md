# VRM MCP Proxy - Change Notes

## 2026-06-06: MCP lifecycle 対策追加

- `_lifecycle.py` を追加し、stdio MCP プロセスの lifecycle 管理を導入
- 起動時に `instance_registry.json` へ実行中インスタンスを登録し、同一 identity の古い世代を supersede するように変更
- hard idle timeout は既定で無効化し、Codex Desktop が保持している現行 transport を時間経過だけで閉じないように変更
- parent watch / native parent wait により、親プロセス終了時の自動終了を補助
- `vrmah_mcp_proxy.py` は request in-flight を `_lifecycle.mark_request_start/end()` で計測し、処理中に watchdog が終了しないように変更
- `vrmah_minimum_proxy.py` にも同じ `_lifecycle.py` ベースの lifecycle 管理を追加
- registry identity に `script_file` を追加し、`vrmah_mcp_proxy.py` と `vrmah_minimum_proxy.py` が同一 config/base_url でも互いに supersede しないように変更
- `.gitignore` に lifecycle runtime files (`instance_registry.json`, `instance_registry.json.lock`) の除外を追加

## 2026-04-04: VRMAH本体バージョンv2.3.0 対応

## 2026-04-04: FK ヘルパーツール追加 + クライアントサイド bones フィルタ

### 新規 MCP ツール (3種)

- `fk_sample_pose`: アニメーション中に N 回 `fk get_all` をサンプリングし、各ボーン・各軸の min/max/avg 統計を返す
  - signed angle 正規化 (-180..180) + unwrap による連続角展開で統計精度を確保
- `fk_snapshot_to_frame`: 現在の FK ボーン回転を `ik animation op=edit` で IK アニメーションフレームとして保存 (rotation のみ)
- `fk_rotate_delta`: 指定ボーンの現在回転に delta を加算して `fk set` (coord=global 対応)

### 新規ユーティリティ (内部)

- `_signed_angle()`: 0-360 Euler を -180..180 に正規化
- `_extract_error_message()`: VRMCommandResult からエラーメッセージを抽出 (フォールバック付き)
- `_unwrap_angles()`: signed 角度の時系列を連続角に展開 (隣接差 < 180 前提)
- `_fk_get_all()`: `fk get_all` の薄いラッパー (`main` キーワードのみサーバーに渡す)
- `_filter_bone_list()`: カンマ区切りボーン名によるクライアントサイドフィルタ

### bones パラメータ拡張 (fk_sample_pose, fk_snapshot_to_frame)

- `"main"`: VRM Agent Host 側で主要18ボーンに絞り込み (従来通り)
- カンマ区切りボーン名 (例: `"Hips,Spine,Head"`): サーバーから全ボーン取得後、MCP Proxy でクライアントサイドフィルタ (新規)
- 省略: 全ボーン (従来通り)

### ツール定義 (schema)

- 3 ツールを `_tool_definitions()` に追加
- `_handle_tool_call()` にディスパッチ分岐追加
- bones パラメータの description を更新: カンマ区切り対応を明記

### ドキュメント更新

- `instructions.md`: FK セクションに MCP Proxy ヘルパーツール概要を追加
- `detailed_instructions.md`: MCP Proxy FK ヘルパーツールセクション新設、get_all bones パラメータにクライアントサイドフィルタの説明追加
