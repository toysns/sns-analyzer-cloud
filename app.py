"""SNS Analyzer - TikTok/Instagram account analysis tool."""

import json
import os
import re

import streamlit as st

from utils.session import init_session_state, clear_analysis_state
from utils.tiktok_fetcher import (
    extract_username as extract_tiktok_username,
    fetch_tiktok_profile,
    fetch_tiktok_videos,
    videos_to_dataframe as tiktok_videos_to_dataframe,
    sample_videos_for_analysis,
)
from utils.instagram_fetcher import (
    extract_instagram_username,
    fetch_instagram_profile,
    fetch_instagram_videos,
    fetch_instagram_auto,
    is_apify_available,
    videos_to_dataframe as instagram_videos_to_dataframe,
)
from utils.url_router import (
    detect_platform as route_detect_platform,
    get_collection_method_label,
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
from utils.gemini_video_analyzer import analyze_video_with_gemini
from utils.comment_analyzer import fetch_and_analyze_comments
from utils.trend_analyzer import analyze_trends, format_trend_analysis
from utils.competitor_analyzer import (
    fetch_competitor_data,
    format_competitor_comparison,
    build_main_account_stats,
)

# --- Page Config ---
st.set_page_config(
    page_title="SNS Analyzer",
    page_icon="📊",
    layout="wide",
)

# --- Initialize ---
init_session_state()

# --- API Key Check ---
def _get_secret(key, default=""):
    """Get secret from environment or st.secrets."""
    val = os.environ.get(key, "")
    if val:
        return val
    try:
        return st.secrets.get(key, default)
    except Exception:
        return default

OPENAI_API_KEY = _get_secret("OPENAI_API_KEY")
GEMINI_API_KEY = _get_secret("GEMINI_API_KEY")
APIFY_API_TOKEN = _get_secret("APIFY_API_TOKEN")


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

WHISPER_LANGUAGES = {
    "日本語": "ja",
    "English": "en",
    "한국어": "ko",
    "中文": "zh",
    "自動検出": "auto",
}

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
    st.caption("TikTok/InstagramアカウントURLを入力 → 動画一覧から分析対象を選択 → 文字起こし+分析レポート生成")

    # --- Step 1: URL Input ---
    col1, col2, col3 = st.columns([3, 1, 1])
    with col1:
        url_input = st.text_input(
            "アカウントURL またはユーザー名",
            placeholder="https://www.tiktok.com/@username または https://www.instagram.com/username/",
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
    with col3:
        whisper_lang = st.selectbox(
            "文字起こし言語",
            options=list(WHISPER_LANGUAGES.keys()),
            index=0,  # Default: 日本語
            key="whisper_language",
        )

    if not url_input:
        st.info("アカウントURLを入力してください（TikTok: https://www.tiktok.com/@username / Instagram: https://www.instagram.com/username/）")
        return

    # Detect platform
    platform = _detect_platform(url_input)
    if platform is None:
        # Default to TikTok for bare usernames
        platform = "tiktok"

    # --- Unified auto-fetch flow (Instagram: Apify / TikTok: yt-dlp) ---
    if platform == "instagram":
        username = extract_instagram_username(url_input)
    else:
        username = extract_tiktok_username(url_input)

    if not username:
        st.error("ユーザー名を取得できませんでした。URLを確認してください。")
        return

    platform_label = "Instagram" if platform == "instagram" else "TikTok"
    st.session_state["account_name"] = username
    st.session_state["platform"] = platform_label

    # Phase 1: Fetch metadata
    if st.session_state.get("tiktok_videos") is None:
        collection_method = get_collection_method_label(platform)
        st.caption(f"検出プラットフォーム: **{platform_label}** / ユーザー: **@{username}** / 収集方法: {collection_method}")

        # Show Apify status for Instagram
        if platform == "instagram":
            if is_apify_available():
                st.success("Apify: 接続可能 — Instagramデータを自動収集します")
            else:
                st.warning(
                    "APIFY_API_TOKEN未設定 — yt-dlpフォールバックで取得を試みます。\n"
                    "Apifyを設定するとInstagramデータをより確実に収集できます。"
                )

        if st.button("動画を取得", type="primary", key="fetch_videos"):
            _fetch_metadata(username, platform)

        # Manual Reel URL fallback for Instagram
        if platform == "instagram":
            st.divider()
            with st.expander("手動でReel URLを入力する（自動取得がうまくいかない場合）"):
                reel_urls_input = st.text_area(
                    "Reel URLを1行に1つずつ貼り付け",
                    placeholder="https://www.instagram.com/reel/ABC123/\nhttps://www.instagram.com/reel/DEF456/",
                    height=120,
                    key="instagram_reel_urls",
                )
                if st.button("この動画を分析対象にする", key="fetch_ig_reels"):
                    _build_instagram_video_list(username, reel_urls_input)
        return

    # Phase 2: Video selection
    if st.session_state.get("analysis_report") is None:
        _render_video_selector(username, mode)
        return

    # Phase 3: Show results
    _show_analysis_results(username, mode)


def _fetch_metadata(username, platform="tiktok"):
    """Fetch account metadata for TikTok or Instagram.

    Instagram uses Apify (primary) with yt-dlp fallback.
    TikTok uses yt-dlp directly.
    """
    platform_label = "Instagram" if platform == "instagram" else "TikTok"

    with st.status(f"{platform_label}のメタデータを取得中...", expanded=True) as status:
        st.write("アカウント情報を取得中...")

        if platform == "instagram":
            # Unified Instagram fetch: Apify → yt-dlp fallback
            def _progress(msg):
                st.write(f"  {msg}")

            profile, videos, method, error = fetch_instagram_auto(
                username, max_count=30, progress_callback=_progress
            )
            to_df = instagram_videos_to_dataframe

            if videos:
                method_label = "Apify" if method == "apify" else "yt-dlp"
                st.write(f"  ✓ {method_label}で取得成功")
                st.session_state["collection_method"] = method
        else:
            profile = fetch_tiktok_profile(username)
            videos = fetch_tiktok_videos(username)
            to_df = tiktok_videos_to_dataframe
            st.session_state["collection_method"] = "ytdlp"

        if videos is None:
            status.update(label="メタデータ取得に失敗しました", state="error")
            if platform == "instagram":
                st.error(
                    "Instagramのメタデータ取得に失敗しました。\n"
                    "上の「手動でReel URLを入力する」から直接URLを入力するか、"
                    "「手動分析」タブでデータを手動入力して分析できます。"
                )
            else:
                st.error(
                    f"{platform_label}のメタデータ取得に失敗しました。"
                    f"{platform_label}のアクセス制限の可能性があります。"
                    "「手動分析」タブでデータを手動入力して分析できます。"
                )
            return

        st.session_state["tiktok_profile"] = profile
        st.session_state["tiktok_videos"] = videos
        st.session_state["tiktok_df"] = to_df(videos)

        msg = f"{len(videos)}本の動画を取得しました"
        if profile:
            msg += f" | フォロワー: {profile.get('followers', '不明')}"
        status.update(label=msg, state="complete")

    st.rerun()


def _build_instagram_video_list(username, reel_urls_input):
    """Build video list from user-provided Instagram Reel URLs."""
    if not reel_urls_input or not reel_urls_input.strip():
        st.warning("Reel URLを1つ以上入力してください。")
        return

    urls = [u.strip() for u in reel_urls_input.strip().split("\n") if u.strip()]
    # Filter to valid Instagram Reel URLs
    valid_urls = [u for u in urls if "instagram.com/reel/" in u or "instagram.com/p/" in u]

    if not valid_urls:
        st.error("有効なInstagram Reel URLが見つかりませんでした。\n例: https://www.instagram.com/reel/ABC123/")
        return

    videos = []
    for i, url in enumerate(valid_urls):
        # Extract reel ID from URL
        reel_id = ""
        match = re.search(r"(?:reel|p)/([A-Za-z0-9_-]+)", url)
        if match:
            reel_id = match.group(1)

        videos.append({
            "id": reel_id,
            "title": f"Reel {i + 1}: {reel_id}",
            "view_count": 0,
            "like_count": 0,
            "comment_count": 0,
            "upload_date": "",
            "url": url,
            "duration": 0,
        })

    st.session_state["tiktok_profile"] = {
        "username": username,
        "display_name": username,
        "followers": "不明",
    }
    st.session_state["tiktok_videos"] = videos
    st.session_state["tiktok_df"] = instagram_videos_to_dataframe(videos)

    st.success(f"{len(videos)}本のReelを登録しました。")
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

    # --- Optional analysis toggles ---
    st.markdown("**追加分析オプション**（選択した項目が分析レポートに含まれます）")
    opt_col1, opt_col2, opt_col3, opt_col4 = st.columns(4)
    with opt_col1:
        enable_gemini = st.checkbox(
            "🎥 Gemini動画分析",
            key="opt_gemini",
            value=False,
            help="Gemini APIで動画を丸ごと分析。文字起こし＋映像分析を統合実行します。ONにすると従来のWhisper文字起こし＋映像分析の代わりに使用されます。",
            disabled=not GEMINI_API_KEY,
        )
        if not GEMINI_API_KEY:
            st.caption("⚠ GEMINI_API_KEY未設定")
    with opt_col2:
        # Disable separate visual analysis when Gemini is on (Gemini includes it)
        enable_visual = st.checkbox(
            "🎬 映像分析",
            key="opt_visual",
            value=False,
            help="動画からキーフレームを抽出し、撮影スタイル・テロップ・構図などを分析します（+約$0.02/本）",
            disabled=st.session_state.get("opt_gemini", False),
        )
        if st.session_state.get("opt_gemini", False):
            st.caption("Geminiに含まれます")
    with opt_col3:
        enable_comments = st.checkbox(
            "💬 コメント分析",
            key="opt_comments",
            value=False,
            help="コメント欄の感情分析・オーディエンス品質・マネタイズ可能性を評価します（+約$0.005/本）",
        )
    with opt_col4:
        enable_competitor = st.checkbox(
            "🔍 競合比較",
            key="opt_competitor",
            value=False,
            help="競合アカウントのメタデータを取得して比較分析を行います",
        )

    # Competitor accounts input (shown only when toggled on)
    if enable_competitor:
        st.caption("競合アカウントのURLを入力すると、メタデータを取得して比較分析を行います")
        competitor_input = st.text_area(
            "競合アカウントURL（1行1アカウント、最大3つ）",
            key="competitor_urls",
            height=100,
            placeholder="https://www.tiktok.com/@competitor1\nhttps://www.tiktok.com/@competitor2",
        )

    st.divider()

    # Selected count and cost estimate
    st.markdown(f"**{selected_count}本**を選択中")
    if selected_count > 0:
        cost_estimate = _estimate_cost(selected_count, enable_visual, enable_comments, enable_gemini)
        time_estimate = _estimate_time(selected_count, enable_visual, enable_comments, enable_gemini)
        st.caption(
            f"💰 推定コスト: **${cost_estimate:.2f}** | "
            f"⏱ 推定時間: **約{time_estimate}分**"
        )
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


def _estimate_cost(video_count, visual=False, comments=False, gemini=False):
    """Estimate API cost for the analysis run.

    Approximate per-video costs:
        - Whisper transcription: ~$0.006 (avg 1min audio)
        - GPT-4o Vision (visual): ~$0.02 (5 frames)
        - GPT-4o-mini (comments): ~$0.005
        - Gemini 2.0 Flash (video): ~$0.01 (replaces Whisper + Vision)
        - Claude Sonnet report (fixed): ~$0.08
    """
    if gemini:
        per_video = 0.01  # Gemini video analysis (transcription + visual combined)
    else:
        per_video = 0.006  # Whisper
        if visual:
            per_video += 0.02
    if comments:
        per_video += 0.005
    report_cost = 0.08  # Claude Sonnet
    return video_count * per_video + report_cost


def _estimate_time(video_count, visual=False, comments=False, gemini=False):
    """Estimate processing time in minutes.

    Approximate per-video time:
        - Download + transcribe: ~30s
        - Visual analysis: ~15s
        - Comment analysis: ~10s
        - Gemini video analysis: ~40s (download + upload + analysis)
        - Claude report (fixed): ~20s
    """
    if gemini:
        per_video_sec = 40  # download + upload + Gemini analysis
    else:
        per_video_sec = 30  # download + transcribe
        if visual:
            per_video_sec += 15
    if comments:
        per_video_sec += 10
    total_sec = video_count * per_video_sec + 20  # + report generation
    return max(1, round(total_sec / 60))


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

    # Read optional analysis toggles
    enable_gemini = st.session_state.get("opt_gemini", False)
    enable_visual = st.session_state.get("opt_visual", False)
    enable_comments = st.session_state.get("opt_comments", False)
    enable_competitor = st.session_state.get("opt_competitor", False)

    # Language for Whisper transcription
    lang_label = st.session_state.get("whisper_language", "日本語")
    whisper_lang = WHISPER_LANGUAGES.get(lang_label, "ja")

    with st.status("分析を実行中...", expanded=True) as status:
        # Calculate total steps dynamically
        if enable_gemini:
            steps_per_video = 1  # Gemini does transcription + visual in one call
        else:
            steps_per_video = 1  # transcribe always
            if enable_visual:
                steps_per_video += 1
        if enable_comments:
            steps_per_video += 1
        total_steps = len(selected) * steps_per_video
        current_step = 0

        # Build step description
        if enable_gemini:
            step_parts = ["Gemini動画分析（文字起こし＋映像分析）"]
        else:
            step_parts = ["文字起こし"]
            if enable_visual:
                step_parts.append("映像分析")
        if enable_comments:
            step_parts.append("コメント分析")
        step_desc = "＋".join(step_parts)

        # Step 1: Transcribe + optional Visual + optional Comment analysis per video
        st.write(f"Step 1: {len(selected)}本の動画を{step_desc}中...")
        transcripts = []
        progress_bar = st.progress(0)
        for i, video in enumerate(selected):
            title_short = video['title'][:30] if video.get('title') else '無題'
            video_with_transcript = dict(video)

            if enable_gemini:
                # Gemini unified analysis: transcription + visual in one call
                st.write(f"  [{i+1}/{len(selected)}] {title_short} — Gemini動画分析中...")
                transcript, visual_analysis, error = analyze_video_with_gemini(
                    video["url"], GEMINI_API_KEY,
                    video_url=video.get("video_url"),
                )
                if transcript:
                    video_with_transcript["transcript"] = transcript
                else:
                    video_with_transcript["transcript"] = f"(文字起こし失敗: {error})"
                    st.write(f"    ⚠ {error}")
                if visual_analysis:
                    video_with_transcript["visual_analysis"] = visual_analysis
                elif error:
                    video_with_transcript["visual_analysis"] = f"(映像分析失敗: {error})"
                current_step += 1
                progress_bar.progress(current_step / total_steps)
            else:
                # Traditional pipeline: Whisper + optional GPT-4o Vision
                st.write(f"  [{i+1}/{len(selected)}] {title_short} — 文字起こし中...")
                transcript, error = transcribe_video_url(
                    video["url"], OPENAI_API_KEY, language=whisper_lang,
                    video_url=video.get("video_url"),
                )
                if transcript:
                    video_with_transcript["transcript"] = transcript
                else:
                    video_with_transcript["transcript"] = f"(文字起こし失敗: {error})"
                    st.write(f"    ⚠ {error}")
                current_step += 1
                progress_bar.progress(current_step / total_steps)

                # Visual analysis (optional, GPT-4o Vision)
                if enable_visual:
                    st.write(f"  [{i+1}/{len(selected)}] {title_short} — 映像分析中...")
                    visual_analysis, vis_error = analyze_video_visuals(
                        video["url"], OPENAI_API_KEY, num_frames=5,
                        video_url=video.get("video_url"),
                    )
                    if visual_analysis:
                        video_with_transcript["visual_analysis"] = visual_analysis
                    else:
                        video_with_transcript["visual_analysis"] = f"(映像分析失敗: {vis_error})"
                        st.write(f"    ⚠ 映像分析: {vis_error}")
                    current_step += 1
                    progress_bar.progress(current_step / total_steps)

            # Comment analysis (optional, works with both Gemini and traditional)
            if enable_comments:
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

        # Step 2: Competitor analysis (only if toggled on and URLs provided)
        competitor_text = ""
        if enable_competitor:
            competitor_urls_raw = st.session_state.get("competitor_urls", "").strip()
            if competitor_urls_raw:
                comp_urls = [u.strip() for u in competitor_urls_raw.split("\n") if u.strip()][:3]
                st.write(f"競合分析: {len(comp_urls)}つの競合アカウントのデータを取得中...")
                competitors = fetch_competitor_data(comp_urls)
                main_stats = build_main_account_stats(videos, profile)
                competitor_text = format_competitor_comparison(main_stats, competitors)
                if competitor_text:
                    st.write(f"  → {len([c for c in competitors if 'error' not in c])}アカウントの比較データを取得")

        # Save to Sheets
        platform_label = st.session_state.get("platform", "TikTok")
        platform_prefix = "instagram" if platform_label == "Instagram" else "tiktok"
        st.write("スプレッドシートに保存中...")
        _save_to_sheets(transcripts, username, platform_prefix)

        # AI Analysis
        st.write("Claude Sonnetで分析レポートを生成中...")

        # Time-series trend analysis (always run - uses existing metadata, no API call)
        trend_data = analyze_trends(videos)
        trend_text = format_trend_analysis(trend_data) if trend_data else ""

        account_data = {
            "platform": platform_label,
            "name": username,
            "followers": profile.get("followers", "不明") if profile else "不明",
            "total_posts": len(videos),
            "trend_analysis": trend_text,
            "competitor_comparison": competitor_text,
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

    # Visual analysis results
    if st.session_state.get("transcription_results"):
        visual_results = [t for t in st.session_state["transcription_results"] if t.get("visual_analysis")]
        if visual_results:
            with st.expander(f"🎬 映像分析結果（{len(visual_results)}本）", expanded=False):
                for t in visual_results:
                    st.markdown(f"### {t.get('title', '無題')[:50]}")
                    if t["visual_analysis"].startswith("(映像分析失敗"):
                        st.warning(t["visual_analysis"])
                    else:
                        st.markdown(t["visual_analysis"])
                    st.divider()

    # Comment analysis results
    if st.session_state.get("transcription_results"):
        comment_results = [t for t in st.session_state["transcription_results"] if t.get("comment_analysis")]
        if comment_results:
            with st.expander(f"💬 コメント分析結果（{len(comment_results)}本）", expanded=False):
                for t in comment_results:
                    st.markdown(f"### {t.get('title', '無題')[:50]}")
                    if t["comment_analysis"].startswith("(コメント分析失敗"):
                        st.warning(t["comment_analysis"])
                    else:
                        st.markdown(t["comment_analysis"])
                    st.divider()

    # Analysis report
    if st.session_state.get("analysis_report"):
        st.subheader("分析レポート")
        st.markdown(st.session_state["analysis_report"])

        # Download button
        platform_label = st.session_state.get("platform", "TikTok")
        platform_prefix = "instagram" if platform_label == "Instagram" else "tiktok"
        mode_name = ANALYSIS_MODES.get(mode, ("不明",))[0]
        report_text = export_report_text(
            st.session_state["analysis_report"],
            username,
            platform_label,
            mode_name,
        )
        filename = generate_filename(username, platform_prefix)
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
        st.success(f"OpenAI API Key: 設定済み (****{OPENAI_API_KEY[-4:]}) — 文字起こし(Whisper)/映像分析(GPT-4o)用")
    else:
        st.error("OpenAI API Key: 未設定 (環境変数 OPENAI_API_KEY を設定してください)")
    if GEMINI_API_KEY:
        st.success(f"Gemini API Key: 設定済み (****{GEMINI_API_KEY[-4:]}) — Gemini動画分析用")
    else:
        st.warning("Gemini API Key: 未設定 (環境変数 GEMINI_API_KEY を設定するとGemini動画分析が使えます)")
    if APIFY_API_TOKEN:
        st.success(f"Apify API Token: 設定済み (****{APIFY_API_TOKEN[-4:]}) — Instagram自動収集用")
    else:
        st.warning("Apify API Token: 未設定 (環境変数 APIFY_API_TOKEN を設定するとInstagramの自動データ収集が使えます)")

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
st.caption("TikTok/Instagramアカウントを自動分析し、改善レポートを生成します（Instagram: Apify / TikTok: yt-dlp）")

tab1, tab2, tab3 = st.tabs(["自動分析", "手動分析", "設定"])

with tab1:
    render_auto_analysis_tab()

with tab2:
    render_manual_analysis_tab()

with tab3:
    render_settings_tab()
