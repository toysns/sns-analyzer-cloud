#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import streamlit as st
import subprocess
import json
import csv
import os
from datetime import datetime
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# ページ設定
st.set_page_config(
    page_title="SNS分析ツール（TikTok & Instagram）",
    page_icon="🎬",
    layout="wide"
)

# Googleスプレッドシート認証
@st.cache_resource
def get_google_sheets_client():
    """Googleスプレッドシートクライアントを取得"""
    try:
        # 認証情報のパス（ユーザーのDesktopにあるJSONファイル）
        creds_path = str(Path("/tmp")/google_credentials.json")
        
        if not os.path.exists(creds_path):
            st.error(f"認証ファイルが見つかりません: {creds_path}")
            return None
        
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_path, scope)
        client = gspread.authorize(creds)
        
        return client
    except Exception as e:
        st.error(f"Google認証エラー: {str(e)}")
        return None

def save_to_google_sheets(client, account_name, videos_data, platform="tiktok"):
    """Googleスプレッドシートに保存（アカウントごとにシート分け）"""
    try:
        # スプレッドシートを開く
        spreadsheet = client.open("TikTok分析データベース")
        
        # シート名（プラットフォーム接頭辞付き）
        sheet_name = f"{platform}_{account_name}" if platform == "instagram" else account_name
        
        # シートが存在するか確認
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
            # 既存シートがあれば削除して再作成
            spreadsheet.del_worksheet(worksheet)
        except:
            pass
        
        # 新しいシートを作成
        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=10)
        
        # ヘッダー行
        headers = ['日時', '順位', 'タイトル', '再生回数', 'いいね数', 'コメント数', '投稿日時', '文字起こし', 'URL']
        worksheet.append_row(headers)
        
        # データ行を追加
        for video in videos_data:
            row = [
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                str(video.get('順位', '')),
                str(video.get('タイトル', '')),
                str(video.get('再生回数', '')),
                str(video.get('いいね数', '')),
                str(video.get('コメント数', '')),
                str(video.get('投稿日時', '')),
                str(video.get('文字起こし', '')),
                str(video.get('URL', ''))
            ]
            worksheet.append_row(row)
        
        # スプレッドシートのURLを返す
        return True, spreadsheet.url
        
    except Exception as e:
        return False, str(e)

# TikTok用関数
def get_metadata(account_name):
    """TikTokアカウントのメタデータを取得"""
    script_path = str(Path("/tmp")/tiktok_metadata.py")
    result = subprocess.run(
        ['python3', script_path, account_name],
        capture_output=True,
        text=True
    )
    return result.returncode == 0

def transcribe_video(video_url, output_dir):
    """動画を文字起こし（TikTok用）"""
    script_path = str(Path("/tmp")/instagram_to_text.sh")
    result = subprocess.run(
        [script_path, video_url],
        capture_output=True,
        text=True,
        cwd=output_dir
    )
    
    if result.returncode == 0:
        # 文字起こし結果を取得
        output_files = [f for f in os.listdir(output_dir) if f.endswith('.txt')]
        if output_files:
            latest_file = max([os.path.join(output_dir, f) for f in output_files], key=os.path.getmtime)
            with open(latest_file, 'r', encoding='utf-8') as f:
                return f.read(), None
    
    return None, "文字起こし失敗"

# Instagram用関数
def get_instagram_profile(account_name, login_user=None):
    """Instagramアカウントのプロフィール情報のみ取得"""
    try:
        import instaloader
        L = instaloader.Instaloader()
        
        # ログイン処理
        if login_user:
            session_file = os.path.expanduser(f"~/.instaloader-session")
            if os.path.exists(session_file):
                L.load_session_from_file(login_user, session_file)
        
        # プロフィール取得
        profile = instaloader.Profile.from_username(L.context, account_name)
        
        return {
            'username': profile.username,
            'followers': profile.followers,
            'mediacount': profile.mediacount,
            'full_name': profile.full_name
        }
    except Exception as e:
        return None

def transcribe_instagram_video(video_url, output_dir):
    """Instagram動画を文字起こし"""
    return transcribe_video(video_url, output_dir)

# メインUI
st.title("🎬 SNS分析ツール（TikTok & Instagram）")

# タブUI
tab1, tab2, tab3 = st.tabs(["📱 TikTok", "📸 Instagram", "🤖 Claude分析テンプレート"])

# =====================
# TikTokタブ
# =====================
with tab1:
    st.header("TikTok分析")
    
    # Step 1: メタデータ取得
    st.subheader("📝 Step 1: アカウント情報取得")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        account_name = st.text_input(
            "TikTokアカウント名（@なし）",
            placeholder="例: toysns",
            key="tiktok_account"
        )
    
    with col2:
        st.write("")
        st.write("")
        fetch_button = st.button("🔍 取得", use_container_width=True, key="tiktok_fetch")
    
    if fetch_button and account_name:
        with st.spinner("メタデータ取得中..."):
            if get_metadata(account_name):
                # CSVファイルを読み込み
                csv_file = str(Path("/tmp")/tiktok_{account_name}_metadata.csv")
                
                if os.path.exists(csv_file):
                    df = pd.read_csv(csv_file)
                    
                    # セッション状態に保存
                    st.session_state['tiktok_df'] = df
                    st.session_state['tiktok_account_name'] = account_name
                    
                    st.success("✅ 取得完了！")
                    
                    # 統計情報表示
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("総投稿数", f"{len(df)}本")
                    with col2:
                        avg_views = int(df['再生回数'].mean())
                        st.metric("平均再生数", f"{avg_views:,}回")
                    with col3:
                        total_likes = int(df['いいね数'].sum())
                        st.metric("総いいね数", f"{total_likes:,}")
                else:
                    st.error("CSVファイルが見つかりません")
            else:
                st.error("メタデータ取得に失敗しました")
    
    # Step 2: 動画選択
    if 'tiktok_df' in st.session_state:
        st.markdown("---")
        st.subheader("🎯 Step 2: 動画選択")
        
        df = st.session_state['tiktok_df']
        
        # クイック選択ボタン
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            if st.button("📊 上位10本", use_container_width=True, key="tiktok_top10"):
                st.session_state['tiktok_selected_indices'] = list(range(min(10, len(df))))
        
        with col2:
            if st.button("⚖️ 上位5本+下位5本", use_container_width=True, key="tiktok_mixed"):
                indices = list(range(min(5, len(df)))) + list(range(max(0, len(df)-5), len(df)))
                st.session_state['tiktok_selected_indices'] = indices
        
        with col3:
            if st.button("🎲 ランダム10本", use_container_width=True, key="tiktok_random"):
                import random
                st.session_state['tiktok_selected_indices'] = random.sample(range(len(df)), min(10, len(df)))
        
        with col4:
            if st.button("🔄 選択解除", use_container_width=True, key="tiktok_clear"):
                st.session_state['tiktok_selected_indices'] = []
        
        # 初期化
        if 'tiktok_selected_indices' not in st.session_state:
            st.session_state['tiktok_selected_indices'] = []
        
        # データテーブルで選択
        st.dataframe(
            df[['順位', 'タイトル', '再生回数', 'いいね数', 'コメント数', '投稿日時']].head(50),
            use_container_width=True
        )
        
        selected = st.multiselect(
            f"文字起こしする動画を選択（{len(st.session_state['tiktok_selected_indices'])}本選択中）",
            options=range(len(df)),
            format_func=lambda x: f"{x+1}位: {df.iloc[x]['タイトル'][:50]}... ({df.iloc[x]['再生回数']:,}回)",
            default=st.session_state['tiktok_selected_indices'],
            key="tiktok_multiselect"
        )
        
        st.session_state['tiktok_selected_indices'] = selected
        
        # Step 3: 文字起こし
        if st.session_state['tiktok_selected_indices']:
            st.markdown("---")
            st.subheader("🚀 Step 3: 文字起こし & スプレッドシート保存")
            
            if st.button("▶️ 文字起こし開始", use_container_width=True, type="primary", key="tiktok_transcribe"):
                df = st.session_state['tiktok_df']
                selected_indices = st.session_state['tiktok_selected_indices']
                account_name = st.session_state['tiktok_account_name']
                output_dir = str(Path("/tmp")/instagram_transcripts")
                
                # Googleスプレッドシートクライアント取得
                client = get_google_sheets_client()
                
                if client is None:
                    st.error("❌ Googleスプレッドシート認証に失敗しました")
                    st.stop()
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                results = []
                
                for i, idx in enumerate(selected_indices):
                    row = df.iloc[idx]
                    video_url = row['URL']
                    
                    status_text.text(f"処理中: {i+1}/{len(selected_indices)} - {row['タイトル'][:30]}...")
                    
                    # 文字起こし実行
                    transcript, error = transcribe_video(video_url, output_dir)
                    
                    if transcript:
                        results.append({
                            '順位': f"{idx+1}位",
                            'タイトル': str(row['タイトル']),
                            '再生回数': f"{row['再生回数']:,}回",
                            'いいね数': f"{row['いいね数']:,}",
                            'コメント数': f"{row['コメント数']:,}",
                            '投稿日時': str(row['投稿日時']),
                            '文字起こし': transcript,
                            'URL': str(video_url)
                        })
                    
                    progress_bar.progress((i + 1) / len(selected_indices))
                
                status_text.text("文字起こし完了！Googleスプレッドシートに保存中...")
                
                # Googleスプレッドシートに保存
                success, result = save_to_google_sheets(client, account_name, results, platform="tiktok")
                
                # 結果をセッション状態に保存
                st.session_state['tiktok_transcription_results'] = {
                    'success': success,
                    'result': result,
                    'results': results,
                    'account_name': account_name,
                    'df': df,
                    'output_dir': output_dir
                }
                
                if success:
                    st.success("✅ 完了！")
                    st.markdown(f"### 📊 スプレッドシート")
                    st.markdown(f"[{result}]({result})")
                    st.markdown(f"→ シート「**{account_name}**」に保存されました")
                    
                    # 結果ディレクトリも開く
                    st.info(f"📁 ローカルファイル: `{output_dir}`")
                else:
                    st.error(f"❌ 保存エラー: {result}")

# Claude分析用テキスト生成（TikTok）
if 'tiktok_transcription_results' in st.session_state and st.session_state['tiktok_transcription_results']['success']:
    st.markdown("---")
    st.markdown("### 🤖 Claude分析用テキスト生成")
    st.markdown("分析に最適な5本を自動選択してフォーマットします")
    
    # セッション状態の初期化
    if 'tiktok_show_analysis_text' not in st.session_state:
        st.session_state.tiktok_show_analysis_text = False
    
    # ボタンを常に表示
    if st.button("📊 Claude分析用テキストを生成", use_container_width=True, type="secondary", key="tiktok_generate_analysis"):
        st.session_state.tiktok_show_analysis_text = True
    
    # テキストを生成して表示
    if st.session_state.tiktok_show_analysis_text:
        trans_data = st.session_state['tiktok_transcription_results']
        results = trans_data['results']
        account_name = trans_data['account_name']
        df = trans_data['df']
        
        # サンプリングロジック: 5本を選択
        total = len(results)
        
        if total >= 5:
            # 上位2本
            top_2 = results[:2]
            # 中位2本
            mid_start = total // 2 - 1
            mid_2 = results[mid_start:mid_start+2]
            # 下位1本
            bottom_1 = [results[-1]]
            
            sampled = top_2 + mid_2 + bottom_1
        elif total >= 3:
            # 3-4本の場合は上位2本+下位1本
            sampled = results[:2] + [results[-1]]
        else:
            # 3本未満の場合は全部
            sampled = results
        
        # 基本データの計算
        total_videos = len(df)
        avg_views = int(df['再生回数'].mean())
        
        # 分析用テキストを生成
        analysis_text = f"""# {account_name} アカウント分析

## 基本データ
- アカウント名: @{account_name}
- 総投稿数: {total_videos}本
- 平均再生数: {avg_views:,}回

## 分析対象動画（{len(sampled)}本）

"""
        
        for i, video in enumerate(sampled, 1):
            analysis_text += f"""### {video['順位']} - {video['再生回数']}
- **タイトル:** {video['タイトル']}
- **いいね:** {video['いいね数']}
- **コメント:** {video['コメント数']}
- **投稿日時:** {video['投稿日時']}
- **URL:** {video['URL']}

**文字起こし:**
```
{video['文字起こし']}
```

---

"""
        
        # expanderで折りたたみ式に
        with st.expander("📋 分析用テキストを表示（クリックして展開）", expanded=True):
            st.text_area(
                "このテキストをコピーしてClaudeに貼り付けてください 👇",
                analysis_text,
                height=400,
                key="tiktok_analysis_textarea"
            )
        
        st.success("✅ 分析用テキストを生成しました！上記をコピーしてClaudeに貼り付けてください。")

# =====================
# Instagramタブ
# =====================
with tab2:
    st.header("Instagram分析")
    
    # Step 1: アカウント情報取得
    st.subheader("📝 Step 1: アカウント情報取得")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        instagram_account = st.text_input(
            "Instagramアカウント名（@なし）",
            placeholder="例: susumetamachans",
            key="instagram_account"
        )
    
    with col2:
        st.write("")
        st.write("")
        instagram_fetch_button = st.button("🔍 取得", use_container_width=True, key="instagram_fetch")
    
    if instagram_fetch_button and instagram_account:
        with st.spinner("プロフィール情報取得中..."):
            # ログインユーザーがあればセッションから取得
            login_user = st.session_state.get('instagram_login_user', None)
            profile = get_instagram_profile(instagram_account, login_user)
            
            if profile:
                st.session_state['instagram_profile'] = profile
                st.session_state['instagram_account_name'] = instagram_account
                
                st.success("✅ 取得完了！")
                
                # プロフィール情報表示
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("フォロワー数", f"{profile['followers']:,}")
                with col2:
                    st.metric("投稿数", f"{profile['mediacount']}")
                with col3:
                    st.metric("アカウント名", profile['username'])
            else:
                st.error("プロフィール情報の取得に失敗しました")
                st.info("💡 ヒント: 非公開アカウントの場合はログインが必要です")
    
    # Step 2: URL入力
    if 'instagram_profile' in st.session_state:
        st.markdown("---")
        st.subheader("📋 Step 2: 分析対象動画URLを入力")
        
        st.info("💡 Instagramで分析したい動画を開き、URLをコピーして1行1個で貼り付けてください")
        
        instagram_urls = st.text_area(
            "動画URL（1行1個）",
            placeholder="https://www.instagram.com/p/XXX/\nhttps://www.instagram.com/p/YYY/\nhttps://www.instagram.com/p/ZZZ/",
            height=200,
            key="instagram_urls_input"
        )
        
        # URLをパース
        if instagram_urls:
            urls = [url.strip() for url in instagram_urls.split('\n') if url.strip()]
            st.info(f"✅ {len(urls)}本の動画URLが入力されています")
            
            # Step 3用に保存（別のキー名を使用）
            if 'instagram_url_list' not in st.session_state:
                st.session_state['instagram_url_list'] = []
            st.session_state['instagram_url_list'] = urls
        
        # Step 3: 文字起こし
        if 'instagram_url_list' in st.session_state and st.session_state['instagram_url_list']:
            st.markdown("---")
            st.subheader("🚀 Step 3: 文字起こし & スプレッドシート保存")
            
            if st.button("▶️ 文字起こし開始", use_container_width=True, type="primary", key="instagram_transcribe"):
                urls = st.session_state['instagram_url_list']
                account_name = st.session_state['instagram_account_name']
                output_dir = str(Path("/tmp")/instagram_transcripts")
                
                # Googleスプレッドシートクライアント取得
                client = get_google_sheets_client()
                
                if client is None:
                    st.error("❌ Googleスプレッドシート認証に失敗しました")
                    st.stop()
                
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                results = []
                
                for i, url in enumerate(urls):
                    status_text.text(f"処理中: {i+1}/{len(urls)} - {url[:50]}...")
                    
                    # 文字起こし実行
                    transcript, error = transcribe_instagram_video(url, output_dir)
                    
                    if transcript:
                        results.append({
                            '順位': f"{i+1}",
                            'タイトル': url.split('/')[-2] if '/' in url else url,  # shortcode
                            '再生回数': '',  # Instagramは非公開
                            'いいね数': '',
                            'コメント数': '',
                            '投稿日時': '',
                            '文字起こし': transcript,
                            'URL': str(url)
                        })
                    
                    progress_bar.progress((i + 1) / len(urls))
                
                status_text.text("文字起こし完了！Googleスプレッドシートに保存中...")
                
                # Googleスプレッドシートに保存
                success, result = save_to_google_sheets(client, account_name, results, platform="instagram")
                
                # 結果をセッション状態に保存
                st.session_state['instagram_transcription_results'] = {
                    'success': success,
                    'result': result,
                    'results': results,
                    'account_name': account_name,
                    'profile': st.session_state['instagram_profile'],
                    'output_dir': output_dir
                }
                
                if success:
                    st.success("✅ 完了！")
                    st.markdown(f"### 📊 スプレッドシート")
                    st.markdown(f"[{result}]({result})")
                    st.markdown(f"→ シート「**instagram_{account_name}**」に保存されました")
                    
                    # 結果ディレクトリも開く
                    st.info(f"📁 ローカルファイル: `{output_dir}`")
                else:
                    st.error(f"❌ 保存エラー: {result}")

# Claude分析用テキスト生成（Instagram）
if 'instagram_transcription_results' in st.session_state and st.session_state['instagram_transcription_results']['success']:
    st.markdown("---")
    st.markdown("### 🤖 Claude分析用テキスト生成")
    st.markdown("分析に最適な動画を自動選択してフォーマットします")
    
    # セッション状態の初期化
    if 'instagram_show_analysis_text' not in st.session_state:
        st.session_state.instagram_show_analysis_text = False
    
    # ボタンを常に表示
    if st.button("📊 Claude分析用テキストを生成", use_container_width=True, type="secondary", key="instagram_generate_analysis"):
        st.session_state.instagram_show_analysis_text = True
    
    # テキストを生成して表示
    if st.session_state.instagram_show_analysis_text:
        trans_data = st.session_state['instagram_transcription_results']
        results = trans_data['results']
        account_name = trans_data['account_name']
        profile = trans_data['profile']
        
        # サンプリングロジック
        total = len(results)
        
        if total >= 5:
            top_2 = results[:2]
            mid_start = total // 2 - 1
            mid_2 = results[mid_start:mid_start+2]
            bottom_1 = [results[-1]]
            sampled = top_2 + mid_2 + bottom_1
        elif total >= 3:
            sampled = results[:2] + [results[-1]]
        else:
            sampled = results
        
        # 分析用テキストを生成
        analysis_text = f"""# {account_name} アカウント分析（Instagram）

## 基本データ
- アカウント名: @{account_name}
- フォロワー数: {profile['followers']:,}
- 総投稿数: {profile['mediacount']}本

## 分析対象動画（{len(sampled)}本）

"""
        
        for i, video in enumerate(sampled, 1):
            analysis_text += f"""### {i}番目 - {video['URL']}
- **URL:** {video['URL']}

**文字起こし:**
```
{video['文字起こし']}
```

---

"""
        
        # expanderで折りたたみ式に
        with st.expander("📋 分析用テキストを表示（クリックして展開）", expanded=True):
            st.text_area(
                "このテキストをコピーしてClaudeに貼り付けてください 👇",
                analysis_text,
                height=400,
                key="instagram_analysis_textarea"
            )
        
        st.success("✅ 分析用テキストを生成しました！上記をコピーしてClaudeに貼り付けてください。")

# =====================
# Claude分析テンプレートタブ
# =====================
with tab3:
    st.header("🤖 Claude分析テンプレート生成")
    st.markdown("**SNS分析スキルv2.0**に最適化されたテンプレートを生成します")
    
    # Step 1: 基本情報
    st.subheader("📝 Step 1: 基本情報")
    
    col1, col2 = st.columns(2)
    
    with col1:
        template_account_name = st.text_input(
            "アカウント名",
            placeholder="@example",
            key="template_account"
        )
        template_followers = st.text_input(
            "フォロワー数",
            placeholder="1.2万",
            key="template_followers"
        )
        template_platform = st.selectbox(
            "プラットフォーム",
            ["TikTok", "Instagram", "YouTube"],
            key="template_platform"
        )
    
    with col2:
        template_posts = st.text_input(
            "投稿数",
            placeholder="50本",
            key="template_posts"
        )
        template_period = st.text_input(
            "運用期間",
            placeholder="6ヶ月",
            key="template_period"
        )
        template_frequency = st.text_input(
            "投稿頻度",
            placeholder="週2回",
            key="template_frequency"
        )
    
    # Step 2: 分析モード選択
    st.markdown("---")
    st.subheader("🎯 Step 2: 分析モード選択")
    
    analysis_mode = st.radio(
        "どのモードで分析しますか？",
        [
            "モード2：ブラッシュアップ案（推奨）- さらに伸ばすための具体的改善策",
            "モード1：成功要因抽出 - なぜこのアカウントがうまくいってるか分析",
            "モード3：コンセプト壁打ち - 方向性の検証、ピボット判断"
        ],
        key="template_mode"
    )
    
    # モード番号を抽出
    mode_number = analysis_mode.split("：")[0].replace("モード", "")
    
    # Step 3: コンセプト（任意）
    st.markdown("---")
    st.subheader("💡 Step 3: コンセプト（わかる範囲で）")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        concept_who = st.text_area(
            "Who（誰に）",
            placeholder="例: 過去に副業で失敗した20代社会人",
            height=100,
            key="template_who"
        )
    
    with col2:
        concept_what = st.text_area(
            "What（何を）",
            placeholder="例: 副業の失敗談と教訓",
            height=100,
            key="template_what"
        )
    
    with col3:
        concept_how = st.text_area(
            "How（どのように）",
            placeholder="例: 1分動画、失敗談→教訓の2部構成",
            height=100,
            key="template_how"
        )
    
    # Step 4: 伸びてる投稿データ
    st.markdown("---")
    st.subheader("📊 Step 4: 伸びてる投稿データ（上位10本）")
    st.markdown("💡 **形式**: `投稿日 | テーマ | 再生数 | いいね | コメント | 保存`（各項目を `|` で区切る）")
    
    top_posts_input = st.text_area(
        "上位10投稿（1行1投稿）",
        placeholder="""2024/01/15 | 投資で50万損した話 | 25万 | 5000 | 300 | 800
2024/01/20 | 副業詐欺に遭った話 | 20万 | 4000 | 250 | 600
2024/01/25 | ギャンブルで100万溶かした話 | 18万 | 3500 | 200 | 500""",
        height=250,
        key="template_top_posts"
    )
    
    # Step 5: 伸びてない投稿データ
    st.markdown("---")
    st.subheader("📉 Step 5: 伸びてない投稿データ（下位10本）")
    
    bottom_posts_input = st.text_area(
        "下位10投稿（1行1投稿）",
        placeholder="""2024/02/01 | 成功するコツ | 2万 | 400 | 20 | 50
2024/02/05 | 稼ぐ方法 | 1.5万 | 350 | 15 | 40
2024/02/10 | 効率化テクニック | 1万 | 300 | 10 | 30""",
        height=250,
        key="template_bottom_posts"
    )
    
    # Step 6: 補足情報（任意）
    st.markdown("---")
    st.subheader("📝 Step 6: 補足情報（任意）")
    
    supplement = st.text_area(
        "その他気になる点・特記事項",
        placeholder="例: ターゲット層は20代社会人、副業に興味あり。コメント欄は共感コメントが多い。保存率が低い。",
        height=100,
        key="template_supplement"
    )
    
    # 生成ボタン
    st.markdown("---")
    
    if st.button("🚀 Claude分析用テンプレートを生成", use_container_width=True, type="primary", key="generate_template"):
        
        # 投稿データをパース
        def parse_posts(text):
            lines = [line.strip() for line in text.strip().split('\n') if line.strip()]
            posts = []
            for line in lines:
                parts = [p.strip() for p in line.split('|')]
                if len(parts) >= 6:
                    posts.append({
                        '投稿日': parts[0],
                        'テーマ': parts[1],
                        '再生数': parts[2],
                        'いいね': parts[3],
                        'コメント': parts[4],
                        '保存': parts[5]
                    })
            return posts
        
        top_posts = parse_posts(top_posts_input) if top_posts_input else []
        bottom_posts = parse_posts(bottom_posts_input) if bottom_posts_input else []
        
        # テンプレート生成
        template_output = f"""# SNSアカウント分析依頼

## 基本情報
- アカウント名：{template_account_name if template_account_name else '（入力なし）'}
- プラットフォーム：{template_platform}
- フォロワー数：{template_followers if template_followers else '（入力なし）'}
- 投稿数：{template_posts if template_posts else '（入力なし）'}
- 運用期間：{template_period if template_period else '（入力なし）'}
- 投稿頻度：{template_frequency if template_frequency else '（入力なし）'}

## 分析モード
モード{mode_number}

## コンセプト（わかる範囲で）
- Who：{concept_who if concept_who else '（入力なし）'}
- What：{concept_what if concept_what else '（入力なし）'}
- How：{concept_how if concept_how else '（入力なし）'}

"""
        
        # 伸びてる投稿データ
        if top_posts:
            template_output += """## 伸びてる投稿（上位10本）

| 投稿日 | テーマ | 再生数 | いいね | コメント | 保存 |
|--------|--------|--------|--------|----------|------|
"""
            for post in top_posts:
                template_output += f"| {post['投稿日']} | {post['テーマ']} | {post['再生数']} | {post['いいね']} | {post['コメント']} | {post['保存']} |\n"
            template_output += "\n"
        
        # 伸びてない投稿データ
        if bottom_posts:
            template_output += """## 伸びてない投稿（下位10本）

| 投稿日 | テーマ | 再生数 | いいね | コメント | 保存 |
|--------|--------|--------|--------|----------|------|
"""
            for post in bottom_posts:
                template_output += f"| {post['投稿日']} | {post['テーマ']} | {post['再生数']} | {post['いいね']} | {post['コメント']} | {post['保存']} |\n"
            template_output += "\n"
        
        # 補足情報
        if supplement:
            template_output += f"""## 補足情報
{supplement}

"""
        
        # 依頼文
        template_output += """---

このアカウントを分析して、ブラッシュアップ案を提案してください。
"""
        
        # 結果を表示
        with st.expander("📋 生成されたテンプレート（クリックして展開）", expanded=True):
            st.text_area(
                "このテキストをコピーしてClaudeに貼り付けてください 👇",
                template_output,
                height=500,
                key="generated_template_output"
            )
        
        st.success("✅ テンプレート生成完了！上記をコピーしてClaudeに貼り付けてください。")
        st.info("💡 **使い方**: Claudeに貼り付けると、SNS分析スキルv2.0が自動的に起動し、詳細な分析とブラッシュアップ案が提示されます。")

# フッター
st.markdown("---")
st.markdown("**💡 使い方:**")
st.markdown("### タブ1・2（TikTok/Instagram）")
st.markdown("1. アカウント情報を取得")
st.markdown("2. 分析対象を選択/入力")
st.markdown("3. 文字起こし実行")
st.markdown("4. Googleスプレッドシートに自動保存")
st.markdown("5. Claude分析用テキストを生成")
st.markdown("")
st.markdown("### タブ3（Claude分析テンプレート）")
st.markdown("1. 基本情報を入力（アカウント名、フォロワー数等）")
st.markdown("2. 分析モードを選択")
st.markdown("3. 伸びてる投稿 / 伸びてない投稿のデータを入力")
st.markdown("4. テンプレート生成 → Claudeに貼り付け")
