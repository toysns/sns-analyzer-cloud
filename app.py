"""SNS Analyzer - TikTok/Instagram account analysis tool."""

import json
import os
import re

import streamlit as st

from utils.session import init_session_state, clear_analysis_state
from utils.tiktok_fetcher import (
    extract_username,
    fetch_tiktok_profile,
    fetch_tiktok_videos,
    videos_to_dataframe,
    sample_videos_for_analysis,
)
from utils.transcriber import transcribe_video_url
from utils.sheets import get_sheets_client, save_videos_to_sheet
from utils.analyzer import run_analysis, ANALYSIS_MODES
from utils.report import (
    export_report_text,
    generate_filename,
    prepare_sheets_data,
)
from utils.screenshot_reader import extract_metadata_from_screenshot
from utils.visual_analyzer import analyze_video_visuals
from utils.comment_analyzer import fetch_and_analyze_comments
from utils.trend_analyzer import analyze_trends, format_trend_analysis

# --- Page Config ---
st.set_page_config(
    page_title="SNS Analyzer",
    page_icon="📊",
    layout="wide",
)

# --- Initialize ---
init_session_state()

# --- API Key Check ---
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")


def _detect_platform(url):
    """Detect platform from URL."""
    if "tiktok.com" in url:
        return "tiktok"
    if "instagram.com" in url:
        return "instagram"
    return None


# ==============================================================================
# Tab 1: Auto Analysis
# ==============================================================================

SORT_OPTIONS = {
    "再生回数（多い順）": ("view_count", False),
    "再生回数（少ない順）": ("view_count", True),
    "いいね数（多い順）": ("like_count", False),
    "いいね数（少ない順）": ("like_count", True),
    "コメント数（多い順）": ("comment_count", False),
    "コメント数（少ない順）": ("comment_count", True),
    "投稿日（新しい順）": ("upload_date", False),
    "投稿日（古い順）": ("upload_date", True),
}


def render_auto_analysis_tab():
    """Render the main auto-analysis tab."""
    st.header("自動分析")
    st.caption("TikTokアカウントURLを入力 → 動画一覧から分析対象を選択 → 文字起こし+分析レポート生成")

    # --- Step 1: URL Input ---
    col1, col2 = st.columns([3, 1])
    with col1:
        url_input = st.text_input(
            "アカウントURL またはユーザー名",
            placeholder="https://www.tiktok.com/@username または @username",
            key="url_input",
        )
    with col2:
        mode = st.selectbox(
            "分析モード",
            options=list(ANALYSIS_MODES.keys()),
            format_func=lambda x: f"{x}. {ANALYSIS_MODES[x][0]}",
            index=1,  # Default: ブラッシュアップ
            key="analysis_mode",
        )

    if not url_input:
        st.info("TikTokのアカウントURL（例: https://www.tiktok.com/@username）を入力してください。")
        return

    # Detect platform
    platform = _detect_platform(url_input)
    if platform == "instagram":
        st.warning("Instagramアカウントが検出されました。「手動分析」タブでInstagram分析ができます。")
        return
    if platform is None and not url_input.startswith("@") and "/" not in url_input:
        platform = "tiktok"

    username = extract_username(url_input)
    if not username:
        st.error("ユーザー名を取得できませんでした。URLを確認してください。")
        return

    st.session_state["account_name"] = username
    st.session_state["platform"] = "TikTok"

    # --- Phase 1: Fetch metadata ---
    if st.session_state.get("tiktok_videos") is None:
        if st.button("動画を取得", type="primary", key="fetch_videos"):
            _fetch_metadata(username)
        return

    # --- Phase 2: Video selection ---
    if st.session_state.get("analysis_report") is None:
        _render_video_selector(username, mode)
        return

    # --- Phase 3: Show results ---
    _show_analysis_results(username, mode)


def _fetch_metadata(username):
    """Fetch TikTok account metadata."""
    with st.status("メタデータを取得中...", expanded=True) as status:
        st.write("アカウント情報を取得中...")
        profile = fetch_tiktok_profile(username)
        videos = fetch_tiktok_videos(username)

        if videos is None:
            status.update(label="メタデータ取得に失敗しました", state="error")
            st.error(
                "TikTokのメタデータ取得に失敗しました。"
                "TikTokのアクセス制限の可能性があります。"
                "「手動分析」タブでデータを手動入力して分析できます。"
            )
            return

        st.session_state["tiktok_profile"] = profile
        st.session_state["tiktok_videos"] = videos
        st.session_state["tiktok_df"] = videos_to_dataframe(videos)

        msg = f"{len(videos)}本の動画を取得しました"
        if profile:
            msg += f" | フォロワー: {profile.get('followers', '不明')}"
        status.update(label=msg, state="complete")

    st.rerun()


def _render_video_selector(username, mode):
    """Render video list with checkboxes and sort controls."""
    videos = st.session_state["tiktok_videos"]
    profile = st.session_state.get("tiktok_profile")

    # Account summary
    if profile:
        st.markdown(f"**@{username}** | フォロワー: {profile.get('followers', '不明')} | 取得動画: {len(videos)}本")
    else:
        st.markdown(f"**@{username}** | 取得動画: {len(videos)}本")

    st.divider()

    # Sort controls
    col_sort, col_select = st.columns([2, 2])
    with col_sort:
        sort_key = st.selectbox(
            "並び替え",
            options=list(SORT_OPTIONS.keys()),
            key="sort_option",
        )
    with col_select:
        col_all, col_none, col_auto = st.columns(3)
        with col_all:
            if st.button("全選択", key="select_all", use_container_width=True):
                for i in range(len(videos)):
                    st.session_state[f"video_check_{i}"] = True
                st.rerun()
        with col_none:
            if st.button("全解除", key="select_none", use_container_width=True):
                for i in range(len(videos)):
                    st.session_state[f"video_check_{i}"] = False
                st.rerun()
        with col_auto:
            if st.button("自動選択", key="select_auto", use_container_width=True):
                auto_indices = _get_auto_select_indices(videos)
                for i in range(len(videos)):
                    st.session_state[f"video_check_{i}"] = i in auto_indices
                st.rerun()

    # Sort videos
    sort_field, ascending = SORT_OPTIONS[sort_key]
    indexed_videos = list(enumerate(videos))
    indexed_videos.sort(
        key=lambda x: x[1].get(sort_field, 0) or 0,
        reverse=not ascending,
    )

    # Video list with checkboxes
    st.markdown(f"**分析する動画を選択してください（{len(videos)}本中）**")

    selected_count = 0
    for original_idx, video in indexed_videos:
        check_key = f"video_check_{original_idx}"
        if check_key not in st.session_state:
            st.session_state[check_key] = False

        views = f"{video['view_count']:,}" if video.get('view_count') else "0"
        likes = f"{video['like_count']:,}" if video.get('like_count') else "0"
        comments = f"{video['comment_count']:,}" if video.get('comment_count') else "0"
        date = video.get('upload_date', '')
        title = video.get('title', '無題')[:60]

        label = f"**{title}** | {views} 再生 | {likes} いいね | {comments} コメント | {date}"

        checked = st.checkbox(label, key=check_key)
        if checked:
            selected_count += 1

    st.divider()

    # Selected count and analyze button
    st.markdown(f"**{selected_count}本**を選択中")
    if selected_count > 10:
        st.warning("10本以上選択すると文字起こしのコストと時間がかかります。5-8本程度を推奨します。")

    col_analyze, col_reset = st.columns([3, 1])
    with col_analyze:
        if st.button(
            f"選択した{selected_count}本で分析を実行",
            type="primary",
            key="run_analysis",
            disabled=selected_count == 0,
        ):
            _run_analysis_with_selection(username, mode)
    with col_reset:
        if st.button("最初からやり直す", key="reset_auto"):
            clear_analysis_state()
            st.rerun()


def _get_auto_select_indices(videos):
    """Get indices for auto-selection (top + middle + bottom)."""
    n = len(videos)
    if n == 0:
        return set()
    if n <= 2:
        return set(range(n))
    if n <= 4:
        return {0, 1, n - 1}
    mid = n // 2
    return {0, 1, mid - 1, mid, n - 1}


def _run_analysis_with_selection(username, mode):
    """Execute analysis with user-selected videos."""
    videos = st.session_state["tiktok_videos"]
    profile = st.session_state.get("tiktok_profile")

    # Gather selected videos
    selected = []
    for i, video in enumerate(videos):
        if st.session_state.get(f"video_check_{i}", False):
            selected.append(video)

    if not selected:
        st.error("動画が選択されていません。")
        return

    with st.status("分析を実行中...", expanded=True) as status:
        total_steps = len(selected) * 3  # transcribe + visual + comments per video
        current_step = 0

        # Step 1: Transcribe + Visual + Comment analysis per video
        st.write(f"Step 1/3: {len(selected)}本の動画を文字起こし＋映像分析＋コメント分析中...")
        transcripts = []
        progress_bar = st.progress(0)
        for i, video in enumerate(selected):
            title_short = video['title'][:30] if video.get('title') else '無題'

            # Transcription
            st.write(f"  [{i+1}/{len(selected)}] {title_short} — 文字起こし中...")
            transcript, error = transcribe_video_url(video["url"], OPENAI_API_KEY)
            video_with_transcript = dict(video)
            if transcript:
                video_with_transcript["transcript"] = transcript
            else:
                video_with_transcript["transcript"] = f"(文字起こし失敗: {error})"
                st.write(f"    ⚠ {error}")
            current_step += 1
            progress_bar.progress(current_step / total_steps)

            # Visual analysis
            st.write(f"  [{i+1}/{len(selected)}] {title_short} — 映像分析中...")
            visual_analysis, vis_error = analyze_video_visuals(
                video["url"], OPENAI_API_KEY, num_frames=5
            )
            if visual_analysis:
                video_with_transcript["visual_analysis"] = visual_analysis
            else:
                video_with_transcript["visual_analysis"] = f"(映像分析失敗: {vis_error})"
                st.write(f"    ⚠ 映像分析: {vis_error}")
            current_step += 1
            progress_bar.progress(current_step / total_steps)

            # Comment analysis
            st.write(f"  [{i+1}/{len(selected)}] {title_short} — コメント分析中...")
            comment_text, comment_data, cmt_error = fetch_and_analyze_comments(
                video["url"], OPENAI_API_KEY, max_comments=50
            )
            if comment_text:
                video_with_transcript["comment_analysis"] = comment_text
            elif cmt_error:
                video_with_transcript["comment_analysis"] = f"(コメント分析失敗: {cmt_error})"
                st.write(f"    ⚠ コメント: {cmt_error}")
            else:
                video_with_transcript["comment_analysis"] = "(コメントなし)"
            current_step += 1
            progress_bar.progress(current_step / total_steps)

            transcripts.append(video_with_transcript)

        st.session_state["transcription_results"] = transcripts

        # Step 2: Save to Sheets
        st.write("Step 2/3: スプレッドシートに保存中...")
        _save_to_sheets(transcripts, username, "tiktok")

        # Step 3: AI Analysis
        st.write("Step 3/3: Claude Sonnetで分析レポートを生成中...")

        # Time-series trend analysis (uses existing metadata, no API call)
        trend_data = analyze_trends(videos)
        trend_text = format_trend_analysis(trend_data) if trend_data else ""

        account_data = {
            "platform": "TikTok",
            "name": username,
            "followers": profile.get("followers", "不明") if profile else "不明",
            "total_posts": len(videos),
            "trend_analysis": trend_text,
        }
        report, error = run_analysis(account_data, transcripts, mode, OPENAI_API_KEY)

        if report:
            st.session_state["analysis_report"] = report
            status.update(label="分析完了!", state="complete")
        else:
            status.update(label="分析レポート生成に失敗しました", state="error")
            st.error(f"分析エラー: {error}")
            return

    st.rerun()


def _show_analysis_results(username, mode):
    """Display analysis results."""
    # Video list
    if st.session_state.get("tiktok_df") is not None:
        with st.expander(f"取得した動画一覧（{len(st.session_state['tiktok_df'])}本）", expanded=False):
            st.dataframe(
                st.session_state["tiktok_df"],
                use_container_width=True,
                hide_index=True,
            )

    # Transcription results
    if st.session_state.get("transcription_results"):
        with st.expander("文字起こし結果", expanded=False):
            for t in st.session_state["transcription_results"]:
                st.markdown(f"**{t.get('title', '無題')[:50]}** (再生: {t.get('view_count', 0):,})")
                st.text(t.get("transcript", "")[:500])
                st.divider()

    # Analysis report
    if st.session_state.get("analysis_report"):
        st.subheader("分析レポート")
        st.markdown(st.session_state["analysis_report"])

        # Download button
        mode_name = ANALYSIS_MODES.get(mode, ("不明",))[0]
        report_text = export_report_text(
            st.session_state["analysis_report"],
            username,
            "TikTok",
            mode_name,
        )
        filename = generate_filename(username, "tiktok")
        st.download_button(
            "レポートをダウンロード",
            data=report_text,
            file_name=filename,
            mime="text/markdown",
        )

    # Reset button
    if st.button("新しい分析を開始", key="reset_auto"):
        clear_analysis_state()
        st.rerun()


def _save_to_sheets(transcripts, account_name, platform_prefix):
    """Save transcription data to Google Sheets."""
    creds_raw = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_raw:
        st.write("  ⚠ GOOGLE_CREDENTIALS が設定されていません。スプレッドシート保存をスキップ。")
        return

    client = get_sheets_client(creds_raw)
    if not client:
        st.write("  ⚠ Google Sheets認証に失敗しました。スキップ。")
        return

    sheet_name = f"{platform_prefix}_{account_name}" if platform_prefix == "instagram" else account_name
    rows = prepare_sheets_data(transcripts, account_name)
    success, msg = save_videos_to_sheet(client, sheet_name, rows)

    if success:
        st.write(f"  → 保存完了")
        st.session_state["sheets_saved"] = True
    else:
        st.write(f"  ⚠ 保存失敗: {msg}")


# ==============================================================================
# Tab 2: Manual Analysis
# ==============================================================================

def render_manual_analysis_tab():
    """Render the manual analysis tab for any platform."""
    st.header("手動分析")
    st.caption("メタデータや文字起こしテキストを手動で入力して分析します。Instagramアカウントの分析もこちらから。")

    # --- Screenshot upload section ---
    with st.expander("📸 スクリーンショットからデータを読み取る", expanded=False):
        st.caption("プロフィール画面のスクショをアップロードすると、フォロワー数・投稿数・プロフィール文などを自動で読み取ります")
        uploaded_file = st.file_uploader(
            "プロフィールのスクリーンショット",
            type=["png", "jpg", "jpeg", "webp"],
            key="screenshot_upload",
        )
        if uploaded_file is not None:
            col_img, col_btn = st.columns([2, 1])
            with col_img:
                st.image(uploaded_file, caption="アップロードされた画像", use_container_width=True)
            with col_btn:
                if st.button("読み取り実行", type="primary", key="extract_screenshot"):
                    with st.spinner("画像を解析中..."):
                        image_bytes = uploaded_file.getvalue()
                        metadata, error = extract_metadata_from_screenshot(image_bytes, OPENAI_API_KEY)
                    if metadata:
                        st.success("読み取り完了！下のフォームに自動入力しました")
                        # Auto-fill form fields via session state
                        if metadata.get("platform"):
                            platform_map = {"TikTok": "TikTok", "Instagram": "Instagram"}
                            detected = metadata["platform"]
                            for key in platform_map:
                                if key.lower() in detected.lower():
                                    st.session_state["manual_platform"] = key
                                    break
                        if metadata.get("account_name"):
                            st.session_state["manual_account_name"] = str(metadata["account_name"])
                        if metadata.get("followers") is not None:
                            st.session_state["manual_followers"] = str(metadata["followers"])
                        if metadata.get("total_posts") is not None:
                            st.session_state["manual_total_posts"] = str(metadata["total_posts"])
                        if metadata.get("profile_text"):
                            st.session_state["manual_profile"] = str(metadata["profile_text"])
                        # Store extra metadata for display
                        st.session_state["screenshot_metadata"] = metadata
                        st.rerun()
                    else:
                        st.error(f"読み取りに失敗しました: {error}")

    # Show extracted metadata summary if available
    if st.session_state.get("screenshot_metadata"):
        meta = st.session_state["screenshot_metadata"]
        cols = []
        if meta.get("followers") is not None:
            cols.append(f"フォロワー: **{meta['followers']:,}**")
        if meta.get("following") is not None:
            cols.append(f"フォロー: **{meta['following']:,}**")
        if meta.get("total_posts") is not None:
            cols.append(f"投稿数: **{meta['total_posts']:,}**")
        if meta.get("total_likes") is not None:
            cols.append(f"いいね合計: **{meta['total_likes']:,}**")
        if cols:
            st.info("📸 読み取り結果: " + " | ".join(cols))

    st.divider()

    # Account info
    col1, col2, col3 = st.columns(3)
    with col1:
        platform = st.selectbox("プラットフォーム", ["TikTok", "Instagram"], key="manual_platform")
    with col2:
        account_name = st.text_input("アカウント名", key="manual_account_name")
    with col3:
        followers = st.text_input("フォロワー数", key="manual_followers")

    col4, col5, col6 = st.columns(3)
    with col4:
        total_posts = st.text_input("総投稿数", key="manual_total_posts")
    with col5:
        posting_freq = st.text_input("投稿頻度（例: 週3本）", key="manual_freq")
    with col6:
        mode = st.selectbox(
            "分析モード",
            options=list(ANALYSIS_MODES.keys()),
            format_func=lambda x: f"{x}. {ANALYSIS_MODES[x][0]}",
            index=1,
            key="manual_mode",
        )

    profile_text = st.text_area("プロフィール文", key="manual_profile", height=80)

    st.subheader("投稿データ")
    st.caption("伸びてる投稿と伸びてない投稿の情報を入力してください。形式: 日付 | テーマ | 再生数 | いいね | コメント（1行1投稿）")

    col_top, col_bottom = st.columns(2)
    with col_top:
        top_posts = st.text_area(
            "伸びてる投稿（上位5-10本）",
            key="manual_top_posts",
            height=200,
            placeholder="2025-12-01 | 朝ルーティン | 100,000 | 5,000 | 200",
        )
    with col_bottom:
        bottom_posts = st.text_area(
            "伸びてない投稿（下位5-10本）",
            key="manual_bottom_posts",
            height=200,
            placeholder="2025-12-05 | 商品レビュー | 1,000 | 50 | 3",
        )

    # Optional: video URLs for transcription
    st.subheader("動画文字起こし（任意）")
    video_urls_text = st.text_area(
        "文字起こししたい動画のURL（1行1URL）",
        key="manual_video_urls",
        height=100,
        placeholder="https://www.tiktok.com/@user/video/123...\nhttps://www.instagram.com/reel/ABC...",
    )

    # Or paste transcripts directly
    manual_transcripts_text = st.text_area(
        "または文字起こしテキストを直接入力",
        key="manual_transcripts_text",
        height=200,
        placeholder="投稿1のテキスト...\n---\n投稿2のテキスト...",
    )

    supplement = st.text_area("補足情報（任意）", key="manual_supplement", height=80)

    if st.button("分析を実行", type="primary", key="run_manual_analysis"):
        if not account_name:
            st.error("アカウント名を入力してください。")
            return

        transcripts = []

        # Transcribe videos if URLs provided
        if video_urls_text.strip():
            urls = [u.strip() for u in video_urls_text.strip().split("\n") if u.strip()]
            with st.status(f"{len(urls)}本の動画を文字起こし中...") as status:
                for i, url in enumerate(urls):
                    st.write(f"[{i+1}/{len(urls)}] {url[:60]}...")
                    transcript, error = transcribe_video_url(url, OPENAI_API_KEY)
                    transcripts.append({
                        "title": f"投稿{i+1}",
                        "url": url,
                        "transcript": transcript if transcript else f"(失敗: {error})",
                    })
                status.update(label="文字起こし完了", state="complete")

        # Parse manual transcripts
        elif manual_transcripts_text.strip():
            for i, text in enumerate(manual_transcripts_text.strip().split("---"), 1):
                text = text.strip()
                if text:
                    transcripts.append({
                        "title": f"投稿{i}",
                        "transcript": text,
                    })

        # Build account data
        account_data = {
            "platform": platform,
            "name": account_name,
            "followers": followers,
            "total_posts": total_posts,
            "posting_freq": posting_freq,
            "profile_text": profile_text,
            "top_posts": top_posts,
            "bottom_posts": bottom_posts,
            "supplement": supplement,
        }

        # Run analysis
        with st.spinner("Claude Sonnetで分析中..."):
            report, error = run_analysis(account_data, transcripts, mode, OPENAI_API_KEY)

        if report:
            st.session_state["analysis_report"] = report
            st.subheader("分析レポート")
            st.markdown(report)

            # Download
            mode_name = ANALYSIS_MODES.get(mode, ("不明",))[0]
            report_text = export_report_text(report, account_name, platform, mode_name)
            filename = generate_filename(account_name, platform.lower())
            st.download_button(
                "レポートをダウンロード",
                data=report_text,
                file_name=filename,
                mime="text/markdown",
            )

            # Save to sheets
            if transcripts:
                _save_to_sheets(
                    transcripts,
                    account_name,
                    "instagram" if platform == "Instagram" else "tiktok",
                )
        else:
            st.error(f"分析に失敗しました: {error}")


# ==============================================================================
# Tab 3: Settings
# ==============================================================================

def render_settings_tab():
    """Render the settings/diagnostics tab."""
    st.header("設定・接続テスト")

    # API Key status
    st.subheader("APIキー状態")
    ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
    if ANTHROPIC_API_KEY:
        st.success(f"Anthropic API Key: 設定済み (****{ANTHROPIC_API_KEY[-4:]})")
    else:
        st.error("Anthropic API Key: 未設定 (環境変数 ANTHROPIC_API_KEY を設定してください)")
    if OPENAI_API_KEY:
        st.success(f"OpenAI API Key: 設定済み (****{OPENAI_API_KEY[-4:]}) — 文字起こし(Whisper)用")
    else:
        st.error("OpenAI API Key: 未設定 (環境変数 OPENAI_API_KEY を設定してください)")

    # Google Sheets test
    st.subheader("Google Sheets接続")
    creds_raw = os.environ.get("GOOGLE_CREDENTIALS")
    if creds_raw:
        st.success("GOOGLE_CREDENTIALS: 設定済み")
        if st.button("接続テスト", key="test_sheets"):
            client = get_sheets_client(creds_raw)
            if client:
                spreadsheet_name = os.environ.get("SPREADSHEET_NAME", "TikTok分析データベース")
                try:
                    spreadsheet = client.open(spreadsheet_name)
                    st.success(f"スプレッドシート '{spreadsheet_name}' に接続成功! (URL: {spreadsheet.url})")
                except Exception as e:
                    st.error(f"スプレッドシートの取得に失敗: {e}")
            else:
                st.error("認証に失敗しました")
    else:
        st.warning("GOOGLE_CREDENTIALS: 未設定")

    # System info
    st.subheader("システム情報")
    import subprocess
    checks = {
        "yt-dlp": ["yt-dlp", "--version"],
        "ffmpeg": ["ffmpeg", "-version"],
    }
    for name, cmd in checks.items():
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            version = result.stdout.strip().split("\n")[0]
            st.success(f"{name}: {version}")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            st.error(f"{name}: 未インストール")

    # Analysis modes info
    st.subheader("分析モード一覧")
    for num, (name, desc) in ANALYSIS_MODES.items():
        st.markdown(f"**{num}. {name}** - {desc}")


# ==============================================================================
# Main App
# ==============================================================================

st.title("📊 SNS Analyzer")
st.caption("TikTok/Instagramアカウントを自動分析し、改善レポートを生成します")

tab1, tab2, tab3 = st.tabs(["自動分析", "手動分析", "設定"])

with tab1:
    render_auto_analysis_tab()

with tab2:
    render_manual_analysis_tab()

with tab3:
    render_settings_tab()
