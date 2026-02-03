# ☁️ Streamlit Cloudデプロイガイド

このガイドでは、SNS分析ツールをStreamlit Cloudにデプロイする手順を説明します。

## 📋 前提条件

- GitHubアカウント
- Google Cloud Platform アカウント
- Google Sheets API 有効化済み
- サービスアカウント認証情報

## 🎯 デプロイ手順（完全版）

### Step 1: GitHubリポジトリの準備

#### 1-1. リポジトリの作成

GitHubで新しいリポジトリを作成：
```
名前: sns-analyzer-cloud
説明: TikTok & Instagram分析ツール
Public または Private
```

#### 1-2. ローカルでGit初期化

```bash
cd sns-analyzer-cloud

# Git初期化
git init

# ファイルを追加
git add .

# 初回コミット
git commit -m "Initial commit: SNS分析ツール クラウド版"

# ブランチ名をmainに変更
git branch -M main

# リモートリポジトリを追加（your-usernameを自分のユーザー名に変更）
git remote add origin https://github.com/your-username/sns-analyzer-cloud.git

# プッシュ
git push -u origin main
```

#### 1-3. 機密情報の確認

`.gitignore`に以下が含まれているか確認：
```
.streamlit/secrets.toml
google_credentials.json
*.json
```

これらのファイルはGitHubにpushされません。

---

### Step 2: Google Cloud Platformの設定

#### 2-1. Google Sheets APIの有効化

1. https://console.cloud.google.com/ にアクセス
2. プロジェクトを選択（または新規作成）
3. 「APIとサービス」 > 「ライブラリ」
4. 「Google Sheets API」を検索
5. 「有効にする」をクリック

#### 2-2. サービスアカウントの作成（既にある場合はスキップ）

1. 「APIとサービス」 > 「認証情報」
2. 「認証情報を作成」 > 「サービスアカウント」
3. 名前: `tiktok-analyzer-service`
4. ロール: `編集者` または `オーナー`
5. 完了

#### 2-3. 認証情報JSONの取得（既にある場合はスキップ）

1. 作成したサービスアカウントをクリック
2. 「キー」タブ
3. 「鍵を追加」 > 「新しい鍵を作成」
4. JSON形式を選択
5. ダウンロード

#### 2-4. Googleスプレッドシートの共有

分析データを保存するスプレッドシート：
1. https://docs.google.com/spreadsheets/ で新規作成
2. 名前: `TikTok分析データベース`
3. サービスアカウントのメールアドレスと共有（編集者権限）
   - 例: `tiktok-analyzer-service@your-project.iam.gserviceaccount.com`

---

### Step 3: Streamlit Cloudでデプロイ

#### 3-1. Streamlit Cloudにログイン

1. https://share.streamlit.io にアクセス
2. 「Continue with GitHub」でログイン
3. GitHubアカウント連携を許可

#### 3-2. 新しいアプリをデプロイ

1. 「New app」ボタンをクリック
2. 設定：
   ```
   Repository: your-username/sns-analyzer-cloud
   Branch: main
   Main file path: app.py
   App URL: 任意（例: sns-analyzer-tool）
   ```
3. 「Deploy!」をクリック

#### 3-3. Streamlit Secretsの設定

デプロイが完了したら（初回は失敗する可能性があります）：

1. アプリの右上メニュー > 「Settings」
2. 「Secrets」タブを選択
3. 以下の内容を貼り付け（**実際の値に置き換えてください**）：

```toml
[google_credentials]
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-private-key-id"
private_key = "-----BEGIN PRIVATE KEY-----\nYour Private Key Here\n-----END PRIVATE KEY-----\n"
client_email = "your-service-account@your-project.iam.gserviceaccount.com"
client_id = "your-client-id"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your-service-account%40your-project.iam.gserviceaccount.com"
universe_domain = "googleapis.com"
```

4. 「Save」をクリック
5. アプリが自動的に再起動します

---

### Step 4: デプロイの確認

#### 4-1. アプリの動作確認

1. デプロイされたアプリのURLにアクセス
   - 例: `https://your-app.streamlit.app`

2. 「システム要件チェック」を展開
   - ✅ Python: 確認
   - ✅ yt-dlp: 確認
   - ✅ ffmpeg: 確認

3. 簡単なテストを実行
   - TikTokタブでアカウント情報を取得してみる
   - 成功すれば完了！

#### 4-2. トラブルシューティング

**エラー: "yt-dlpが見つかりません"**
→ requirements.txtに`yt-dlp`が含まれているか確認

**エラー: "Google認証情報が設定されていません"**
→ Streamlit Secretsが正しく設定されているか確認

**エラー: "Googleスプレッドシート認証に失敗しました"**
→ サービスアカウントがスプレッドシートと共有されているか確認

---

## 🔄 更新とメンテナンス

### コードの更新

```bash
# ローカルで修正
git add .
git commit -m "Update: 機能追加"
git push

# Streamlit Cloudが自動的に再デプロイ
```

### Secretsの更新

1. Streamlit Cloud > Settings > Secrets
2. 内容を編集
3. Save
4. アプリが自動的に再起動

### ログの確認

1. Streamlit Cloud > Manage app
2. 「Logs」タブ
3. エラーログを確認

---

## 💡 ベストプラクティス

### セキュリティ

- ✅ `.gitignore`に機密情報を追加
- ✅ Streamlit Secretsを使用（環境変数）
- ✅ サービスアカウントに最小限の権限
- ✅ Private リポジトリ推奨（センシティブな場合）

### パフォーマンス

- ✅ `@st.cache_resource`でクライアント接続をキャッシュ
- ✅ `/tmp`ディレクトリで一時ファイル管理
- ✅ 大量データは分割処理

### メンテナンス

- ✅ requirements.txtのバージョン固定
- ✅ 定期的な依存パッケージ更新
- ✅ エラーログの定期確認

---

## 📊 リソース制限

Streamlit Cloudの無料枠：
- メモリ: 1GB
- CPU: 0.078 vCPU
- ストレージ: 一時（/tmp）のみ

**注意:**
- 動画ダウンロードはメモリを消費
- 大量の動画を同時処理しない
- 一時ファイルは定期的にクリーンアップ

---

## 🆘 ヘルプ

### 公式ドキュメント
- Streamlit Cloud: https://docs.streamlit.io/streamlit-community-cloud
- Streamlit Secrets: https://docs.streamlit.io/streamlit-community-cloud/deploy-your-app/secrets-management

### サポート
- Streamlit Community: https://discuss.streamlit.io
- GitHub Issues: https://github.com/your-username/sns-analyzer-cloud/issues

---

## ✅ デプロイチェックリスト

デプロイ前の最終確認：

- [ ] GitHubリポジトリ作成済み
- [ ] コードをpush済み
- [ ] `.gitignore`で機密情報を除外
- [ ] Google Sheets API有効化
- [ ] サービスアカウント作成済み
- [ ] スプレッドシートを共有済み
- [ ] requirements.txt確認
- [ ] Streamlit Cloudでデプロイ
- [ ] Secretsを設定
- [ ] 動作確認完了

全てチェックできたら、デプロイ完了です！🎉
