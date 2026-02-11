"""Comment sentiment analysis using yt-dlp + GPT-4o."""

import json
import logging
import os
import subprocess
import tempfile

from openai import OpenAI

logger = logging.getLogger(__name__)

COMMENT_ANALYSIS_PROMPT = """あなたはSNSのコメント分析の専門家です。
以下はTikTok動画のコメント一覧です。これらを分析して、以下の形式でJSON出力してください。

```json
{
  "total_analyzed": コメント数,
  "sentiment_distribution": {
    "positive": 割合（0-100の整数）,
    "neutral": 割合（0-100の整数）,
    "negative": 割合（0-100の整数）
  },
  "intent_distribution": {
    "appreciation": 割合,
    "question": 割合,
    "empathy": 割合,
    "sharing_experience": 割合,
    "criticism": 割合,
    "joke_humor": 割合,
    "request": 割合
  },
  "audience_quality_score": 1-10の評価,
  "audience_quality_reason": "評価の理由（1文）",
  "monetization_potential": "high/medium/low",
  "monetization_reason": "マネタイズ可能性の理由（1文）",
  "top_themes": ["テーマ1", "テーマ2", "テーマ3"],
  "notable_comments": [
    {"text": "特徴的なコメント1", "type": "タイプ"},
    {"text": "特徴的なコメント2", "type": "タイプ"}
  ],
  "summary": "コメント欄全体の特徴を3文以内で要約"
}
```

分類の基準:
- appreciation: 褒める、応援、「すごい」「かわいい」「最高」等
- question: 質問、「これ何？」「どこで買えますか？」等
- empathy: 共感、「わかる」「私も」等の自己投影
- sharing_experience: 自分の体験を共有、長文コメント
- criticism: 批判、否定、アンチコメント
- joke_humor: ネタ、ボケ、面白い返し
- request: リクエスト、「次は〇〇やって」等

audience_quality_score の基準:
- 8-10: 質問や体験共有が多い → 購買力・エンゲージメント高
- 5-7: 応援系が多いが一般的 → 平均的
- 1-4: 絵文字のみ、短文のみ、荒れている → マネタイズ困難

JSON以外のテキストは出力しないでください。"""


def fetch_comments(video_url, max_comments=50):
    """Fetch comments from a video using yt-dlp.

    Args:
        video_url: URL of the video.
        max_comments: Maximum number of comments to fetch.

    Returns:
        Tuple of (list of comment dicts, error string).
    """
    temp_dir = os.path.join(tempfile.gettempdir(), "sns_analyzer_comments")
    os.makedirs(temp_dir, exist_ok=True)
    video_hash = str(abs(hash(video_url)))[:12]
    info_path = os.path.join(temp_dir, f"comments_{video_hash}.json")

    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--skip-download",
                "--write-comments",
                "--dump-json",
                "--extractor-args",
                f"tiktok:comment_count={max_comments}",
                video_url,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.returncode != 0:
            # Try without extractor-args (may not be supported)
            result = subprocess.run(
                [
                    "yt-dlp",
                    "--skip-download",
                    "--write-comments",
                    "--dump-json",
                    video_url,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

        if result.returncode != 0:
            return [], f"コメント取得失敗: {result.stderr[:200]}"

        # Parse JSON output
        data = json.loads(result.stdout)
        raw_comments = data.get("comments", [])

        if not raw_comments:
            return [], None  # No error, just no comments

        # Extract comment text and metadata
        comments = []
        for c in raw_comments[:max_comments]:
            comment = {
                "text": c.get("text", ""),
                "author": c.get("author", ""),
                "likes": c.get("like_count", 0) or 0,
                "timestamp": c.get("timestamp", ""),
            }
            if comment["text"]:
                comments.append(comment)

        return comments, None

    except json.JSONDecodeError:
        return [], "コメントデータの解析に失敗しました"
    except subprocess.TimeoutExpired:
        return [], "コメント取得がタイムアウトしました（60秒）"
    except FileNotFoundError:
        return [], "yt-dlpがインストールされていません"
    finally:
        try:
            if os.path.exists(info_path):
                os.remove(info_path)
        except OSError:
            pass


def analyze_comments(comments, openai_api_key):
    """Analyze comment sentiment and quality using GPT-4o.

    Args:
        comments: List of comment dicts with 'text' field.
        openai_api_key: OpenAI API key.

    Returns:
        Tuple of (analysis_dict, error string).
    """
    if not comments:
        return None, "コメントがありません"

    if not openai_api_key:
        return None, "OpenAI APIキーが設定されていません"

    # Build comment list text
    comment_texts = []
    for i, c in enumerate(comments[:50], 1):
        likes_str = f" (いいね: {c['likes']})" if c.get("likes") else ""
        comment_texts.append(f"{i}. {c['text']}{likes_str}")

    comments_input = "\n".join(comment_texts)

    try:
        client = OpenAI(api_key=openai_api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # Use mini for cost efficiency
            messages=[
                {"role": "system", "content": COMMENT_ANALYSIS_PROMPT},
                {"role": "user", "content": f"以下のコメントを分析してください：\n\n{comments_input}"},
            ],
            max_tokens=1500,
            temperature=0.1,
        )

        raw_text = response.choices[0].message.content.strip()

        # Extract JSON
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].split("```")[0].strip()

        analysis = json.loads(raw_text)
        return analysis, None

    except json.JSONDecodeError:
        return None, "コメント分析結果の解析に失敗しました"
    except Exception as e:
        return None, f"コメント分析エラー: {str(e)[:200]}"


def format_comment_analysis(analysis):
    """Format comment analysis dict into readable text for the AI prompt.

    Args:
        analysis: Dict from analyze_comments().

    Returns:
        Formatted string.
    """
    if not analysis:
        return ""

    parts = []
    parts.append(f"分析コメント数: {analysis.get('total_analyzed', 0)}")

    # Sentiment
    sent = analysis.get("sentiment_distribution", {})
    if sent:
        parts.append(f"感情分布: ポジティブ {sent.get('positive', 0)}% / "
                      f"ニュートラル {sent.get('neutral', 0)}% / "
                      f"ネガティブ {sent.get('negative', 0)}%")

    # Intent
    intent = analysis.get("intent_distribution", {})
    if intent:
        intent_parts = []
        labels = {
            "appreciation": "応援・称賛",
            "question": "質問",
            "empathy": "共感",
            "sharing_experience": "体験共有",
            "criticism": "批判",
            "joke_humor": "ユーモア",
            "request": "リクエスト",
        }
        for key, label in labels.items():
            val = intent.get(key, 0)
            if val > 0:
                intent_parts.append(f"{label} {val}%")
        parts.append(f"意図分布: {' / '.join(intent_parts)}")

    # Quality
    score = analysis.get("audience_quality_score")
    if score:
        parts.append(f"オーディエンス品質スコア: {score}/10 — {analysis.get('audience_quality_reason', '')}")

    # Monetization
    mon = analysis.get("monetization_potential")
    if mon:
        parts.append(f"マネタイズ可能性: {mon} — {analysis.get('monetization_reason', '')}")

    # Themes
    themes = analysis.get("top_themes", [])
    if themes:
        parts.append(f"主要テーマ: {', '.join(themes)}")

    # Summary
    summary = analysis.get("summary")
    if summary:
        parts.append(f"総評: {summary}")

    return "\n".join(parts)


def fetch_and_analyze_comments(video_url, openai_api_key, max_comments=50):
    """Full pipeline: fetch comments + analyze.

    Args:
        video_url: Video URL.
        openai_api_key: OpenAI API key.
        max_comments: Max comments to fetch.

    Returns:
        Tuple of (formatted_analysis_text, raw_analysis_dict, error).
    """
    comments, error = fetch_comments(video_url, max_comments)
    if error:
        return None, None, error
    if not comments:
        return None, None, None  # No comments available, not an error

    analysis, error = analyze_comments(comments, openai_api_key)
    if error:
        return None, None, error

    formatted = format_comment_analysis(analysis)
    return formatted, analysis, None
