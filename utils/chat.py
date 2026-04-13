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

CONTEXT_QUESTIONS = """アカウントのデータを取得しました！📥

質の高い分析をするため、いくつか教えてください:

**1. このアカウントの運用目的は？**
（例: 集客、採用、ブランディング、商品販売、など）

**2. 誰に届けたいですか？（ターゲット）**
（例: 30代女性で子育てに悩む人、SNS運用を始めたいオーナー、など）
できるだけ具体的に。年齢・職業・悩み・ライフスタイルなど

**3. 競合で意識しているアカウントはありますか？**
（URLか名前を教えてください。複数OK。なければ「なし」でも大丈夫）

**4. 特に聞きたいこと・悩みは？**
（例: 伸び悩んでる、リーチは出るがフォロワーにならない、台本が思いつかない、など）

まとめて1メッセージで答えてくれたら、分析を始めます！"""



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


def generate_hypothesis(profile, videos, platform):
    """Use Claude to form a hypothesis about the account from metadata/captions.

    Returns dynamic hypothesis + contextualized questions based on actual content.

    Returns:
        String with hypothesis + questions, or fallback static questions on error.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return CONTEXT_QUESTIONS

    # Build compact metadata summary for Claude (top 10 + bottom 5 by views)
    sorted_videos = sorted(
        videos, key=lambda v: v.get("view_count", 0) or 0, reverse=True
    )
    sample = sorted_videos[:10] + sorted_videos[-5:] if len(sorted_videos) > 15 else sorted_videos

    video_summary = []
    for i, v in enumerate(sample, 1):
        title = (v.get("title") or "")[:150]
        views = v.get("view_count", 0)
        likes = v.get("like_count", 0)
        comments = v.get("comment_count", 0)
        video_summary.append(
            f"{i}. [再生 {views:,} / いいね {likes:,} / コメント {comments:,}] {title}"
        )

    username = profile.get("username") or profile.get("display_name", "不明")
    display_name = profile.get("display_name", "")

    prompt = f"""あなたはSNSアカウント分析の専門家です。以下のアカウント情報から、**仮説**を立てて、ユーザーに確認の質問を投げてください。

## アカウント情報
- プラットフォーム: {platform}
- アカウント名: @{username} ({display_name})
- 取得した投稿数: {len(videos)}本

## 投稿サンプル（上位+下位の計{len(sample)}本、再生数順）
{chr(10).join(video_summary)}

---

## あなたのタスク

キャプションの内容・再生数の偏り・コメント/いいね比率・投稿パターンから、以下を**仮説として推測**してください:

1. **このアカウントは何をしているか**（提供価値・テーマ）
2. **誰に向けた投稿か**（**具体的なペルソナ1名**で）
3. **運用目的の推測**（集客/販売/ブランディング/コンテンツ収益化 など）

そして、その仮説を**短く提示した上で、最も重要な1つの質問だけ**投げてください。
ユーザーと対話しながら段階的に進めるので、質問を大量に出さないこと。

## ペルソナの書き方ルール（最重要）

ターゲットは**絶対に1名のペルソナに絞り切る**こと。「20代〜40代女性」のような括り方は禁止。

### 悪い例（NG）
- 「20〜40代のパニック障害に悩む人」
- 「副業に興味がある男女」
- 「ダイエットしたい女性」

### 良い例（OK）
- 「32歳・東京在住・会社員・既婚で1歳児を育てる母親。産後のホルモン変化でパニック発作に悩み、病院で『異常なし』と言われて行き場を失っている」
- 「28歳・男性・都内在住のIT会社員。副業を始めたいが家族にバレたくない。月3-5万の収入を目指してる」

名前・年齢・性別・職業・家族構成・住んでる場所・具体的な悩み・ライフスタイルのうち、**投稿内容から推測できるものを最大限具体的に**書く。

## 出力フォーマット

```
アカウントを見てみました！仮説を立ててみたので、1つだけ確認させてください🔍

### 私の仮説
- **やっていること**: [推測]
- **ターゲット（1名のペルソナ）**: [具体的なペルソナ1名]
- **運用目的**: [推測]

※ 上位投稿の「○○」と下位投稿の「××」の差から、[伸びる要素の仮説]と推測しました。

### 確認したいこと
[仮説の中で最も不確実な1点だけを質問。「このペルソナ合ってる？」「この目的で合ってる？」など、**1問だけ**]
```

- 質問は**1つだけ**
- ペルソナは具体的に1名で
- 投稿サンプルの具体例を1-2個引用して根拠を見せる
- 段階的に対話を進めることを意識（確認が終わったら次の質問に進む）"""

    try:
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )
        return response.content[0].text
    except Exception as e:
        logger.warning("Hypothesis generation failed: %s", e)
        return CONTEXT_QUESTIONS


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

    # Retry up to 3 times for transient 5xx errors
    import time as _time
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                items = json.loads(resp.read().decode())
            break
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code >= 500 and attempt < 2:
                _time.sleep(3 * (attempt + 1))
                continue
            return None, None, f"Apify API エラー: HTTP {e.code} — 時間をおいて再試行してください"
        except Exception as e:
            last_err = e
            if attempt < 2:
                _time.sleep(3 * (attempt + 1))
                continue
            return None, None, f"Apify API エラー: {str(e)[:200]}"
    else:
        return None, None, f"Apify API エラー: {str(last_err)[:200]}"

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


def _select_videos_for_analysis(videos, max_count=10):
    """Select videos for deep analysis with maximum contrast.

    Strategy: pick from top, middle, and bottom performers
    to give Claude the best picture of what works and what doesn't.

    Args:
        videos: List of video dicts, sorted by view_count desc.
        max_count: Target number of videos.

    Returns:
        List of selected video dicts.
    """
    n = len(videos)
    if n <= max_count:
        return list(videos)

    # Split into top/middle/bottom thirds
    third = max(1, n // 3)
    top = videos[:third]
    mid = videos[third:third * 2]
    bottom = videos[third * 2:]

    # Allocate: 40% top, 20% middle, 40% bottom (maximize contrast)
    n_top = max(1, int(max_count * 0.4))
    n_mid = max(1, int(max_count * 0.2))
    n_bottom = max_count - n_top - n_mid

    import random
    selected = []
    selected.extend(top[:n_top] if len(top) >= n_top else top)
    selected.extend(random.sample(mid, min(n_mid, len(mid))) if mid else [])
    selected.extend(bottom[:n_bottom] if len(bottom) >= n_bottom else bottom)

    return selected[:max_count]


def _analyze_single_video(video, gemini_api_key, openai_api_key, use_gemini):
    """Analyze a single video. Designed to run in a thread pool.

    Returns:
        Dict with video data + transcript + visual_analysis.
    """
    video_url = video.get("url", "")
    transcript_data = {
        "title": video.get("title", ""),
        "url": video_url,
        "view_count": video.get("view_count", 0),
        "like_count": video.get("like_count", 0),
        "comment_count": video.get("comment_count", 0),
        "upload_date": video.get("upload_date", ""),
    }

    if not video_url:
        transcript_data["transcript"] = "(URLなし)"
        return transcript_data

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

    return transcript_data


def run_chat_analysis(profile, videos, platform, progress_callback=None,
                      max_videos=50, max_workers=10, user_context=None):
    """Run the full analysis pipeline for chat mode with parallel processing.

    Uses Gemini for video understanding (transcription + visual analysis),
    then Claude for deep analysis with the SKILL framework.
    Videos are processed in parallel for speed.

    Args:
        profile: Account profile dict.
        videos: List of video dicts (sorted by view_count desc).
        platform: "tiktok" or "instagram".
        progress_callback: Optional callable(message) for progress updates.
        max_videos: Number of videos for deep Gemini analysis (default 10).
        max_workers: Number of parallel threads (default 5).
        user_context: Optional string with user-provided context
            (purpose, target, competitors, concerns).

    Returns:
        Tuple of (account_data, transcripts, report, error).
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
    openai_api_key = os.environ.get("OPENAI_API_KEY", "")
    use_gemini = bool(gemini_api_key)

    # Select videos for deep analysis
    sampled = _select_videos_for_analysis(videos, max_count=max_videos)
    if not sampled:
        return None, None, None, "分析対象の動画がありません"

    method = "Gemini" if use_gemini else "Whisper"
    if progress_callback:
        progress_callback(
            f"{len(sampled)}本の動画を{method}で並列分析中（{max_workers}並列）..."
        )

    # Parallel video analysis
    transcripts = [None] * len(sampled)
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(
                _analyze_single_video, video,
                gemini_api_key, openai_api_key, use_gemini
            ): i
            for i, video in enumerate(sampled)
        }

        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            completed += 1
            try:
                transcripts[idx] = future.result()
            except Exception as e:
                transcripts[idx] = {
                    "title": sampled[idx].get("title", ""),
                    "url": sampled[idx].get("url", ""),
                    "view_count": sampled[idx].get("view_count", 0),
                    "transcript": f"(分析失敗: {str(e)[:100]})",
                }
            if progress_callback:
                progress_callback(f"動画分析: {completed}/{len(sampled)} 完了")

    # Remove None entries (shouldn't happen but safety)
    transcripts = [t for t in transcripts if t is not None]

    # Build account data (uses ALL videos for stats, not just sampled)
    account_data = {
        "platform": platform,
        "name": profile.get("username") or profile.get("display_name", "不明"),
        "followers": profile.get("followers"),
        "total_posts": len(videos),
    }

    # Trend analysis on ALL videos (free, metadata only)
    trend_result = analyze_trends(videos)
    if trend_result:
        account_data["trend_analysis"] = format_trend_analysis(trend_result)

    # Inject user-provided context (purpose/target/competitors/concerns)
    if user_context:
        account_data["supplement"] = user_context

    if progress_callback:
        progress_callback("Claude で分析レポートを生成中...")

    # Run Claude analysis (mode 2 = improvement suggestions)
    from utils.analyzer import run_analysis
    # Mode 6 = アカウント成長戦略（チャット専用、マネタイズより成長にフォーカス）
    report, error = run_analysis(account_data, transcripts, 6, openai_api_key)

    if error:
        return account_data, transcripts, None, error

    return account_data, transcripts, report, None
