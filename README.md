# 🎬 SNS分析ツール（TikTok & Instagram）- クラウド版

TikTokとInstagramのアカウント分析、動画文字起こし、Googleスプレッドシート連携を行うStreamlitアプリケーションです。

## 🌟 機能

### 📱 TikTok分析
- アカウント情報の自動取得
- 動画メタデータの取得（再生数、いいね、コメント数）
- 選択した動画の自動文字起こし
- Googleスプレッドシートへの自動保存
- Claude分析用テキスト自動生成

### 📸 Instagram分析
- プロフィール情報の取得
- リール動画の文字起こし
- Googleスプレッドシートへの自動保存
- Claude分析用テキスト自動生成

### 🤖 Claude分析テンプレート
- 手動入力による分析テンプレート生成
- 複数の分析モード対応
- SNS分析スキルv4.0との連携

## 📋 必要要件

### システム要件
- Python 3.9+
- yt-dlp
- ffmpeg
- openai-whisper

### Pythonパッケージ
```
streamlit>=1.28.0
pandas>=2.0.0
gspread>=5.11.0
oauth2client>=4.1.3
instaloader>=4.10.0
yt-dlp>=2023.10.0
openai-whisper>=20231117
```

### Google Cloud設定
- Google Sheets API有効化
- サービスアカウント作成
- 認証情報JSON

## 🚀 ローカルでの実行

### 1. リポジトリのクローン
```bash
git clone https://github.com/your-username/sns-analyzer-cloud.git
cd sns-analyzer-cloud
```

### 2. 依存パッケージのインストール
```bash
pip install -r requirements.txt
```

### 3. Streamlit Secretsの設定
`.streamlit/secrets.toml`を作成：
```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

`secrets.toml`を編集して、Google認証情報を入力してください。

### 4. アプリケーションの起動
```bash
streamlit run app.py
```

ブラウザで http://localhost:8501 が開きます。

## ☁️ Streamlit Cloudへのデプロイ

詳細は [DEPLOY.md](docs/DEPLOY.md) を参照してください。

### 簡易手順

1. **GitHubリポジトリの作成**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/your-username/sns-analyzer-cloud.git
   git push -u origin main
   ```

2. **Streamlit Cloudでデプロイ**
   - https://share.streamlit.io にアクセス
   - GitHubアカウントでログイン
   - "New app" をクリック
   - リポジトリを選択
   - Branch: `main`
   - Main file path: `app.py`
   - Deploy!

3. **Secretsの設定**
   - アプリの設定 > Secrets
   - `.streamlit/secrets.toml.example`の内容をコピー
   - Google認証情報を入力
   - Save

## 📖 使い方

### TikTok分析

1. **アカウント情報取得**
   - TikTokアカウント名（@なし）を入力
   - 「取得」ボタンをクリック

2. **動画選択**
   - 上位10本、上位5本+下位5本、ランダム10本から選択
   - または手動で選択

3. **文字起こし実行**
   - 「文字起こし開始」ボタンをクリック
   - Googleスプレッドシートに自動保存

4. **Claude分析用テキスト生成**
   - 自動的に最適な5本を選択
   - コピーしてClaudeに貼り付け

### Instagram分析

1. **アカウント情報取得**
   - Instagramアカウント名（@なし）を入力
   - 「取得」ボタンをクリック

2. **動画URL入力**
   - 分析したい動画のURLを1行1個で入力

3. **文字起こし実行**
   - 「文字起こし開始」ボタンをクリック
   - Googleスプレッドシートに自動保存

### Claude分析テンプレート

1. **基本情報入力**
   - アカウント名、フォロワー数、投稿数など

2. **分析モード選択**
   - モード1〜5から選択

3. **投稿データ入力**
   - 伸びてる投稿（上位10本）
   - 伸びてない投稿（下位10本）

4. **テンプレート生成**
   - コピーしてClaudeに貼り付け

## 🔧 トラブルシューティング

### yt-dlpが見つからない
```bash
pip install yt-dlp
```

### ffmpegが見つからない
```bash
# Mac
brew install ffmpeg

# Ubuntu/Debian
sudo apt-get install ffmpeg

# Windows
# https://ffmpeg.org/download.html からダウンロード
```

### Whisperのインストール失敗
```bash
pip install openai-whisper --upgrade
```

### Google認証エラー
- Streamlit Secretsが正しく設定されているか確認
- Google Sheets APIが有効化されているか確認
- サービスアカウントに適切な権限があるか確認

## 📄 ライセンス

MIT License

## 🤝 貢献

プルリクエスト歓迎！

## 📧 お問い合わせ

Issue を作成してください。
