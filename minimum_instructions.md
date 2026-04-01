# VRM Avatar - Minimum Tool Reference

## Tools

### vrm_animation
アバターのアニメーションを再生します。

| name        | 動作                              |
|-------------|----------------------------------|
| generic     | 通常待機                          |
| energetic   | 元気な待機                        |
| cute        | かわいい待機                      |
| calm        | 落ち着いた待機                    |
| brave       | 勇敢な待機                        |
| classy      | 上品な待機                        |
| boyish      | ボーイッシュ待機                  |
| sexy        | セクシー待機                      |
| cat         | 猫っぽい待機                      |
| think       | 考え中                            |
| concern     | 心配                              |
| stressed    | ストレス                          |
| pitiable    | 哀れな                            |
| denying     | 否定                              |
| what        | 「何？」                          |
| fedup       | うんざり                          |
| happy       | 表情：笑顔                        |
| relaxed     | 表情：リラックス                  |
| sad         | 表情：悲しい                      |
| angry       | 表情：怒り＋ポーズ                |
| surprised   | 表情：驚き＋ポーズ                |
| nice        | 驚き＋笑顔                        |
| laugh       | 笑い＋笑顔表情                    |
| giggle      | 笑顔→クラシーポーズへ遷移        |
| laugh_down  | 笑いリアクション                  |
| cry         | 悲しい表情＋泣きポーズ            |
| v-sign      | Vサイン待機                       |
| cool        | クール待機                        |
| greetings   | 挨拶ポーズ                        |
| victory     | 勝利ポーズ                        |
| walk        | 歩く                              |
| run         | 走る                              |
| bye         | 手を振って別れ                    |
| dance       | ダンス（VRMAファイル使用）        |
| secret      | シークレット                      |
| reset_shape | 表情リセット                      |
| reset_pose  | ポーズリセット                    |

例:
```
vrm_animation(name="energetic")
vrm_animation(name="angry")
vrm_animation(name="reset_shape")
```

---

### voicevox_speak
テキストを音声合成してアバターから再生します。

| パラメータ    | 説明                   | デフォルト |
|--------------|----------------------|-----------|
| text         | 読み上げるテキスト（必須） | -         |
| speaker_id   | スピーカーID            | 設定値    |
| speed_scale  | 速度 (0.5〜2.0)        | 1.0       |
| volume_scale | 音量 (0.0〜2.0)        | 1.0       |

例:
```
voicevox_speak(text="こんにちは！")
voicevox_speak(text="やったね！", speed_scale=1.2)
```

---

## 使い方のヒント

- 発話と同時にアニメーション → `voicevox_speak` と `vrm_animation` を続けて呼ぶ
- 挨拶 → `vrm_animation(name="hello")` + `voicevox_speak(text="こんにちは")`
- 作業完了 → `vrm_animation(name="energetic")` + `voicevox_speak(text="できたよ！")`
- 困惑 → `vrm_animation(name="what")` + `voicevox_speak(text="うーん？")`
- 怒り → `vrm_animation(name="angry")` + `voicevox_speak(text="もう！")`
- 完了後リセット → `vrm_animation(name="reset_shape")` + `vrm_animation(name="generic")`
