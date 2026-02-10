# SNS Analyzer v2

TikTok/Instagramアカウントを自動分析し、改善レポートを生成するWebツール。

## 機能

### 自動分析（TikTok）
1. アカウントURL入力
2. yt-dlpでメタデータ自動取得（最大100本）
3. 上位+中間+下位から5本を自動選択
4. OpenAI Whisper APIで文字起こし
5. GPT-4oでSKILLフレームワーク準拠の分析レポート自動生成
6. Googleスプレッドシートにデータ保存

### 手動分析（TikTok/Instagram）
- メタデータ・文字起こしテキストを手動入力
- 動画URLからの文字起こしも可能
- 5つの分析モード対応

### 分析モード
1. 成功要因抽出
2. ブラッシュアップ提案
3. コンセプト壁打ち
4. 競合分析
5. 新規アカウント設計

## セットアップ

### 必要なもの
- OpenAI APIキー（Whisper + GPT-4o）
- Google Service Account JSON（スプレッドシート保存用）

### ローカル実行
```bash
# 環境変数を設定
export OPENAI_API_KEY="sk-..."
export GOOGLE_CREDENTIALS='{"type":"service_account",...}'
export SPREADSHEET_NAME="TikTok分析データベース"

# 依存関係インストール
pip install -r requirements.txt

# 起動
streamlit run app.py
```

### Docker実行
```bash
docker build -t sns-analyzer .
docker run -p 8501:8501 \
  -e OPENAI_API_KEY="sk-..." \
  -e GOOGLE_CREDENTIALS='...' \
  -e SPREADSHEET_NAME="TikTok分析データベース" \
  sns-analyzer
```

### Railwayデプロイ
1. GitHubリポジトリをRailwayに接続
2. 環境変数を設定: `OPENAI_API_KEY`, `GOOGLE_CREDENTIALS`, `SPREADSHEET_NAME`
3. 自動デプロイ

## 技術スタック
- Streamlit（Web UI）
- yt-dlp（動画メタデータ・ダウンロード）
- ffmpeg（音声抽出）
- OpenAI Whisper API（文字起こし）
- OpenAI GPT-4o（分析）
- gspread（Googleスプレッドシート）

## コスト
- Railway: $5/月（基本料）
- 1回の分析: 約$0.09（Whisper $0.06 + GPT-4o $0.03）
