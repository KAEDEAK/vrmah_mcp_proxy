## プロキシスクリプトの選択

| スクリプト | 用途 | ツール数 |
|---|---|---|
| `vrmah_mcp_proxy.py` | **標準版**。Claude / Codex など高性能モデル向け。汎用 `vrm_command` で全 API にアクセス可能。MCP リソース対応。 | 4〜5 |
| `vrmah_minimum_proxy.py` | **最小版**。軽量モデル向け。`vrm_animation`（名前指定で再生）と `voicevox_speak` のみ。スキーマが単純なため軽量モデルでも使いやすい。 | 2〜3 |

迷ったら標準版を使う。軽量モデルで `vrm_command` が使いこなせない場合は最小版に切り替える。


## 共通の準備
1. config.json の各サーバーと音声の設定
2. VRM Agent Host を起動し、VRM を読み込んでおく
3. VOICEVOX を起動しておく（音声を使う場合）


## Windows 11 + Powershell, Claude Code CLI

### 登録
claude mcp add vrm_proxy_claude -- py vrmah_mcp_proxy/vrmah_mcp_proxy.py

### 登録確認
claude mcp list
claude mcp get vrm_proxy_claude

### 試す
Claude Code を再起動してから:
VRM Agent Host の MCP で挨拶してみて

### 登録解除
claude mcp remove vrm_proxy_claude

### CLAUDE.md への追記
README.md の「CLAUDE.md への追記例」を参照し、アバター連携の設定を追記


## Windows 11 + VS Code (Claude Code 拡張)

### 登録（基本）
プロジェクトルートに .mcp.json を作成:

```json
{
  "mcpServers": {
    "vrm_proxy": {
      "command": "python",
      "args": ["vrmah_mcp_proxy/vrmah_mcp_proxy.py"]
    }
  }
}
```

python が使えない場合は py や python3 に置き換える

### 登録（エージェントごとに config を分ける場合）
`--config` オプションで別の設定ファイルを指定できる。
接続先や音声をエージェントごとに分けたい場合に使用:

```json
{
  "mcpServers": {
    "vrm_proxy_for_claude": {
      "command": "python",
      "args": ["vrmah_mcp_proxy/vrmah_mcp_proxy.py"]
    },
    "vrm_proxy_for_codex": {
      "command": "python",
      "args": [
        "vrmah_mcp_proxy/vrmah_mcp_proxy.py",
        "--config", "config_for_codex.json"
      ]
    }
  }
}
```

サーバー名が異なるため、ツール名のプレフィックスも変わる:
- `mcp__vrm_proxy_for_claude__voicevox_speak`
- `mcp__vrm_proxy_for_codex__voicevox_speak`

CLAUDE.md や CODEX.md の ToolSearch クエリも対応するプレフィックスに合わせること。

### 確認
VS Code のウィンドウをリロード (Ctrl+Shift+P → Developer: Reload Window)
Claude Code 拡張の MCP 接続状態を確認

### 試す
VRM Agent Host の MCP で挨拶してみて

### 登録解除
.mcp.json から該当エントリを削除

### 補足: GitHub Copilot の場合
.mcp.json ではなく .vscode/mcp.json に作成し、キー名を servers にする:

```json
{
  "servers": {
    "vrm_proxy": {
      "command": "python",
      "args": ["vrmah_mcp_proxy/vrmah_mcp_proxy.py"]
    }
  }
}
```


## Windows 11 + WSL + Codex CLI

### 登録
codex mcp add vrm_proxy_codex -- python3 vrmah_mcp_proxy/vrmah_mcp_proxy.py --base-url http://<ip-address-vrmah>:34560

### 登録確認
codex mcp list
codex mcp get vrm_proxy_codex

### 試す
VRM Agent Host の MCP で挨拶してみて

### 登録解除
codex mcp remove vrm_proxy_codex


## MCP リソース URI とファイルの対応

LLM は MCP リソース URI 経由でドキュメントを読み込みます。

| MCP リソース URI | 読み込み元ファイル | 内容 |
|---|---|---|
| `vrm-proxy://instructions` | (vrmah_mcp_proxy.py 内にハードコード) | ツール使用方法の短い説明 |
| `vrm-proxy://api-spec` | `instructions.md` | API クイックリファレンス |
| `vrm-proxy://api-spec-detailed` | `detailed_instructions.md` | API 詳細リファレンス（全コマンド） |

ドキュメント内の相互参照はファイル名ではなく MCP リソース URI で記載しています。

## 共通メモ
- CLAUDE.md / Agents.md にアバター連携の推奨を記載すると自動的に使ってくれる (README.md 参照)
- アニメーション ID は animation_ids.txt を参照
- スピーカー一覧は voicevox_speakers ツールで確認可能
- 詳しくは README.md を参照

### 便利なキーボードショートカット (CLI)
CTRL+C 中断
CTRL+Z いったん抜ける。 fg $1 で戻る