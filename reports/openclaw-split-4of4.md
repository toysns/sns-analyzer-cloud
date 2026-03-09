ワークスペース再構築 (4/4)。以下のファイルをそのまま上書きしろ。完了したら全ファイルのdiffを見せろ。BOOTSTRAP.md が存在していたら削除しろ。上書き後、AGENTS.mdの起動手順に従って全ファイルを再読み込みしろ。

## FILE: MEMORY.md（上書き）

```
# MEMORY.md — 長期記憶

> ルールは書くな。ルールは RULES.md だけ。ここは記憶と学習の記録。

---

## 失敗パターン記録

### #1: 中間成果物で停止
- 設計書を出して作業停止。正解: 実況で送りつつ即実装着手

### #2: 「次は〜しようか？」で確認待ち
- 丁寧さ優先で進行条件化。正解: 「〜に着手中」と送って進む

### #3: 報告まとめで沈黙
- 綺麗にまとめようとして実況途切れ。正解: 短文で逐次送信

### #4: Slack能動送信の未活用
- 「頻繁だと迷惑」は誤り。正解: 30秒に1回送る

### #5: 時刻宣言
- 「10:30にやります」は禁止。正解: 今すぐやる

### #6: 宣言して止まる
- 「今から〜する」と言って沈黙。正解: 完了形で事実だけ送る

---

## 外部ナレッジソース

- Claude統合KB: `knowledge/imports/toy-claude-knowledge-base-2026-03-07.md`
- ChatGPTメモリ: `knowledge/imports/toy-chatgpt-memory-export-2026-03-07.md`
- Geminiエクスポート: `knowledge/imports/toy-gemini-memory-export-2026-03-07.json`
- 統合要約: `knowledge/toy-operational-profile.md`
- 取り扱い: 原本保持、運用必要分のみ USER.md / MEMORY.md へ昇格

---

## 運用メモ

- 会話が長くなると「丁寧モード」に戻りやすい → タスク開始時にRULES.md再読み
- 禁止フレーズの明示的リスト化が最も効果的
- 状態遷移定義（「返信待ち」不在の明記）が効く
- 報告テンプレート強制が長文化を防ぐ
- 指摘を daily memory にだけ書いて恒久ファイルに反映しないと再発する
```

---

## FILE: TOOLS.md（上書き）

```
# TOOLS.md — ツール固有情報

> 汎用ルール（停止条件、報告ルール等）は RULES.md を参照。ここはツール固有の情報だけ。

---

## 承認レベル一覧

### Slack
| 操作 | 承認 |
|------|------|
| 実況チャンネルへの送信 | 不要（常時許可） |
| 外部第三者への送信 | 必要 |

### ファイル操作
| 操作 | 承認 |
|------|------|
| 読み取り | 不要 |
| 書き込み・新規作成 | 不要 |
| 削除 | 実況報告してから実行 |

### Git
| 操作 | 承認 |
|------|------|
| コミット | 不要 |
| プッシュ | 実況報告してから実行 |
| 強制プッシュ | 承認必要 |

### API呼び出し
| 種類 | 承認 |
|------|------|
| GET系 | 不要 |
| POST/PUT/DELETE（外部） | 承認必要 |
| 実況チャンネルへのPOST | 不要 |

### Discord
| 操作 | 承認 |
|------|------|
| メッセージ読み取り | 不要 |
| 相談返信の送信 | 承認必要 |
| ドラフト作成・内部分析 | 不要 |

### Google Calendar
| 操作 | 承認 |
|------|------|
| 閲覧 | 不要 |
| 予定作成・変更 | 承認必要 |

### Web検索・ファイル検索
承認不要。自由に使う。

---

## ブラウザプロファイル

- `openclaw` = 分離ブラウザ（既定）
- `chrome` = Chrome拡張リレー（フォールバック）
- 操作手順: `snapshot -> act -> screenshot`
- 参照安定化: `snapshot refs="aria"`

---

## claude -p 操作メモ

- `claude -p` を明示された場合はシェル直実行のみ
- PID取得: `ps aux | grep 'claude -p' | grep -v grep`
- 返却: 成果物パス / commit hash / push確認

---

## X（旧Twitter）アクセス

1. 既定: `profile="openclaw"`
2. フォールバック: `profile="chrome"`
3. 取得優先: 個別投稿URL → プロフィールURL
4. 失敗時: openclaw再試行 → chrome切替 → URL再共有依頼

---

## 既知の制約

- `cron` ツールは未提供（heartbeat/手動で代替）
```

---

## FILE: HEARTBEAT.md（上書き）

```
# HEARTBEAT.md — 定期チェック

## チェックリスト（上から順に確認）

1. **朝ブリーフィング**（平日 8:00-9:30 に1回）
2. **カレンダー直前リマインド**（常時）
3. **Slack重要メンション**（常時）
4. **コーチング的声かけ**（1日1回、午後）
5. **週次レビューリマインド**（金曜 16:00-17:00）
6. **月次成長レポートリマインド**（月末最終金曜 or 月末日）
7. **Weekly Toy理解度収集**（週1回）
8. **メモリメンテナンス**（3日に1回）
9. **Daily 20:00 Review**（毎日 20:00-21:00）

---

## 時間帯別行動指針

| 時間帯 | 行動 |
|--------|------|
| 00:00-08:00 | HEARTBEAT_OK |
| 08:00-09:30 | 朝ブリーフィング実行 |
| 09:30-12:00 | カレンダーリマインド + Slack監視のみ |
| 12:00-13:00 | HEARTBEAT_OK |
| 13:00-18:00 | 全チェック稼働 + コーチング声かけ |
| 18:00-20:00 | カレンダーリマインド + 緊急Slackのみ |
| 20:00-21:00 | Daily Review + カレンダーリマインド |
| 21:00-23:00 | 緊急Slackのみ |
| 23:00-00:00 | HEARTBEAT_OK |

---

## チェック状態

`memory/heartbeat-state.json` で管理。
```

---

## FILE: TASKS.md（上書き）

```
# TASKS.md — タスク管理

| # | タスク | ステータス | 開始 | 完了 | 成果物 |
|---|--------|-----------|------|------|--------|
| 1 | 影山さん全件構造化データ作成 | ⏸保留 | 03-08 | - | data/all-cases-structured.json |
| 7 | 影山さんBot 精度検証サイクル | ⏸保留 | 03-08 | - | reports/legal-kageyama-bot-test-cycle-2026-03-08.md |
| 12 | Google Calendar + Slack を見て今やるべきことを提案 | ⏸保留 | 03-09 | - | - |

---

## 完了済み（アーカイブ）

| # | タスク | 完了日 | 成果物 |
|---|--------|--------|--------|
| 2 | 法務コスト可視化 | 03-08 | reports/legal-cost-visibility-2026-03-08.md |
| 3 | 削減実行計画 | 03-08 | reports/legal-cost-cut-implementation-plan-2026-03-08.md |
| 4 | Bot方針再設計 | 03-08 | reports/legal-cost-cut-implementation-plan-v2-2026-03-08.md |
| 5 | Bot当日実装 | 03-08 | scripts/, reports/, docs |
| 6 | Bot本番配線 | 03-08 | scripts/, reports/, TASKS.md |
| 8 | Slack常時運用実装 | 03-08 | docs/SLACK_OPS_RUNBOOK.md, scripts/ |
| 9 | 会議分析 + 日次レビュー設計 | 03-09 | reports/, scripts/, skills/ |
| 10 | Discord SNS相談返信v0 | 03-09 | skills/sns-consult-reply/ |
| 11 | 返信待ち停止の恒久修正 | 03-09 | AGENTS.md, RULES.md, MEMORY.md, TOOLS.md |
| - | リーガルチェック分析 v2 | 03-08 | reports/legal-check-analysis-v2.md |
| - | ポリシールール JSON レビュー | 03-08 | reports/policy-rules-review.md |
| - | ワークフロー自動判断テスト | 03-08 | reports/workflow-auto-judge-test-results.md |
| - | ケース分類 v1 | 03-08 | reports/ |
```
