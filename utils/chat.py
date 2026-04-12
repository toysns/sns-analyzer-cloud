"""Chat UI backend for SNS Analyzer — conversational analysis bot."""

import logging
import os
import re

from anthropic import Anthropic

from utils.analyzer import _load_skill_files
from utils.tiktok_fetcher import (
    extract_username as extract_tiktok_username,
    fetch_tiktok_profile,
    fetch_tiktok_videos,
    sample_videos_for_analysis,
)
from utils.instagram_fetcher import (
    extract_instagram_username,
)
from utils.transcriber import transcribe_video_url
from utils.trend_analyzer import analyze_trends, format_trend_analysis

logger = logging.getLogger(__name__)

WELCOME_MESSAGE = (
    "こんにちは！SNSアカウント分析アシスタントです。\n\n"
    "分析したいTikTokまたはInstagramアカウントの**URL**を貼ってください。\n"
    "URLがなくても、SNSに関する質問があればお気軽にどうぞ！"
)


def detect_url_in_message(text):
    """Detect TikTok or Instagram URL in user message.

    Returns:
        Tuple of (url, platform) or (None, None).
    """
    tiktok_match = re.search(
        r"https?://(?:www\.)?tiktok\.com/@[A-Za-z0-9_.]+", text
    )
    if tiktok_match:
        return tiktok_match.group(0), "tiktok"

    instagram_match = re.search(
        r"https?://(?:www\.)?instagram\.com/[A-Za-z0-9_.]+", text
    )
    if instagram_match:
        return instagram_match.group(0), "instagram"

    return None, None


def build_chat_system_prompt(context=None):
    """Build system prompt for chat mode.

    Args:
        context: Optional dict with analysis results to include as context.
            Keys: account_data, report, transcripts.
    """
    skill_content = _load_skill_files()

    parts = [
        "あなたはプロのSNSコンサルタントのアシスタントです。",
        "ユーザーのSNSアカウントを分析し、具体的で実用的なアドバイスを提供します。",
        "フレンドリーかつ専門的に対応してください。",
        "回答は簡潔に、ただし具体性を失わないようにしてください。",
        "",
        "以下の分析フレームワークと知識ベースを活用して回答してください：",
        "",
        "---",
        "",
        skill_content,
    ]

    if context and context.get("report"):
        parts.extend([
            "",
            "---",
            "",
            "## 現在の分析コンテキスト",
            "",
        ])
        acct = context.get("account_data", {})
        if acct:
            parts.append(f"- プラットフォーム: {acct.get('platform', '不明')}")
            parts.append(f"- アカウント名: {acct.get('name', '不明')}")
            if acct.get("followers"):
                parts.append(f"- フォロワー数: {acct['followers']}")
        parts.extend([
            "",
            "### 分析レポート",
            context["report"],
        ])

    return "\n".join(parts)


def stream_chat_response(messages, system_prompt):
    """Stream a chat response from Claude.

    Args:
        messages: List of {"role": ..., "content": ...} dicts.
        system_prompt: System prompt string.

    Yields:
        Text chunks.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        yield "ANTHROPIC_API_KEY が設定されていません。設定タブで確認してください。"
        return

    client = Anthropic(api_key=api_key)

    # Keep last 20 turns to stay within token limits
    recent_messages = messages[-20:]

    try:
        with client.messages.stream(
            model="claude-sonnet-4-20250514",
            max_tokens=8000,
            system=system_prompt,
            messages=recent_messages,
            temperature=0.5,
        ) as stream:
            for text in stream.text_stream:
                yield text
    except Exception as e:
        error_msg = str(e)
        if "authentication" in error_msg.lower() or "api key" in error_msg.lower():
            yield "APIキーが無効です。設定を確認してください。"
        elif "rate" in error_msg.lower():
            yield "APIレート制限に達しました。少し待ってから再試行してください。"
        else:
            yield f"エラーが発生しました: {error_msg[:200]}"


def _fetch_instagram_via_apify(username, max_count=50):
    """Fetch Instagram Reels via Apify Instagram Reel Scraper.

    Returns:
        Tuple of (profile, videos, error).
    """
    import json
    import subprocess

    apify_token = os.environ.get("APIFY_TOKEN", "")
    if not apify_token:
        return None, None, "APIFY_TOKEN が設定されていません"

    # Call Apify API directly
    import urllib.request
    api_url = "https://api.apify.com/v2/acts/apify~instagram-reel-scraper/run-sync-get-dataset-items"
    payload = json.dumps({
        "username": [username],
        "resultsLimit": max_count,
    }).encode()

    req = urllib.request.Request(
        f"{api_url}?token={apify_token}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            items = json.loads(resp.read().decode())
    except Exception as e:
        return None, None, f"Apify API エラー: {str(e)[:200]}"

    if not items:
        return None, None, f"@{username} の Reel が見つかりませんでした"

    # Build profile from first item
    first = items[0]
    profile = {
        "username": first.get("ownerUsername", username),
        "display_name": first.get("ownerFullName", username),
    }

    # Convert Apify items to our video format
    videos = []
    for item in items:
        videos.append({
            "title": (item.get("caption") or "")[:100],
            "url": item.get("url", ""),
            "view_count": item.get("viewCount") or item.get("playCount") or 0,
            "like_count": item.get("likesCount", 0),
            "comment_count": item.get("commentsCount", 0),
            "upload_date": (item.get("timestamp") or "")[:10],
        })

    return profile, videos, None


def fetch_account_data(url, platform):
    """Fetch account metadata and videos.

    Returns:
        Tuple of (profile, videos, error).
        profile: dict with account info.
        videos: list of video dicts sorted by view_count desc.
    """
    try:
        if platform == "tiktok":
            username = extract_tiktok_username(url)
            profile = fetch_tiktok_profile(username)
            if not profile:
                return None, None, f"@{username} のプロフィールを取得できませんでした"
            videos = fetch_tiktok_videos(username, max_count=50)
            if not videos:
                return profile, [], "動画が見つかりませんでした"
        elif platform == "instagram":
            username = extract_instagram_username(url)
            profile, videos, error = _fetch_instagram_via_apify(username)
            if error:
                return None, None, error
            if not videos:
                return profile, [], "Reel が見つかりませんでした"
        else:
            return None, None, "対応していないプラットフォームです"

        # Sort by view count
        videos.sort(key=lambda v: v.get("view_count", 0) or 0, reverse=True)
        return profile, videos, None

    except Exception as e:
        return None, None, f"メタデータ取得エラー: {str(e)[:200]}"


def run_chat_analysis(profile, videos, platform, progress_callback=None):
    """Run the full analysis pipeline for chat mode.

    Uses Gemini for video understanding (transcription + visual analysis),
    then Claude for deep analysis with the SKILL framework.

    Args:
        profile: Account profile dict.
        videos: List of video dicts.
        platform: "tiktok" or "instagram".
        progress_callback: Optional callable(message) for progress updates.

    Returns:
        Tuple of (account_data, transcripts, report, error).
    """
    gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
    openai_api_key = os.environ.get("OPENAI_API_KEY", "")

    # Sample videos for analysis
    sampled = sample_videos_for_analysis(videos)
    if not sampled:
        return None, None, None, "分析対象の動画がありません"

    # Analyze videos with Gemini (preferred) or fall back to Whisper
    transcripts = []
    use_gemini = bool(gemini_api_key)

    for i, video in enumerate(sampled):
        video_url = video.get("url", "")
        if not video_url:
            continue

        title_short = (video.get("title") or "無題")[:30]
        if progress_callback:
            method = "Gemini" if use_gemini else "Whisper"
            progress_callback(
                f"[{i+1}/{len(sampled)}] {title_short} — {method}で分析中..."
            )

        transcript_data = {
            "title": video.get("title", ""),
            "url": video_url,
            "view_count": video.get("view_count", 0),
            "like_count": video.get("like_count", 0),
            "comment_count": video.get("comment_count", 0),
            "upload_date": video.get("upload_date", ""),
        }

        if use_gemini:
            from utils.gemini_video_analyzer import analyze_video_with_gemini
            transcript, visual_analysis, err = analyze_video_with_gemini(
                video_url, gemini_api_key
            )
            transcript_data["transcript"] = transcript or f"(文字起こし失敗: {err})"
            if visual_analysis:
                transcript_data["visual_analysis"] = visual_analysis
        else:
            transcript_text, err = transcribe_video_url(
                video_url, openai_api_key, language="ja"
            )
            transcript_data["transcript"] = transcript_text or "(文字起こし失敗)"

        transcripts.append(transcript_data)

    # Build account data
    account_data = {
        "platform": platform,
        "name": profile.get("username") or profile.get("display_name", "不明"),
        "followers": profile.get("followers"),
        "total_posts": len(videos),
    }

    # Trend analysis
    trend_result = analyze_trends(videos)
    if trend_result:
        account_data["trend_analysis"] = format_trend_analysis(trend_result)

    if progress_callback:
        progress_callback("Claude で分析レポートを生成中...")

    # Run Claude analysis (mode 2 = improvement suggestions)
    from utils.analyzer import run_analysis
    report, error = run_analysis(account_data, transcripts, 2, openai_api_key)

    if error:
        return account_data, transcripts, None, error

    return account_data, transcripts, report, None
