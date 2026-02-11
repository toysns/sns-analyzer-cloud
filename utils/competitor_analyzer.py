"""Competitor account comparison analysis."""

import logging

from utils.tiktok_fetcher import (
    extract_username,
    fetch_tiktok_profile,
    fetch_tiktok_videos,
)
from utils.trend_analyzer import analyze_trends

logger = logging.getLogger(__name__)


def fetch_competitor_data(usernames):
    """Fetch metadata for competitor accounts.

    Args:
        usernames: List of TikTok usernames or URLs.

    Returns:
        List of competitor data dicts.
    """
    competitors = []
    for raw in usernames:
        username = extract_username(raw.strip())
        if not username:
            continue

        profile = fetch_tiktok_profile(username)
        videos = fetch_tiktok_videos(username, max_count=50)

        if videos is None:
            competitors.append({
                "username": username,
                "error": "メタデータ取得失敗",
            })
            continue

        # Calculate basic stats
        view_counts = [v.get("view_count", 0) or 0 for v in videos]
        like_counts = [v.get("like_count", 0) or 0 for v in videos]
        comment_counts = [v.get("comment_count", 0) or 0 for v in videos]

        avg_views = sum(view_counts) / len(view_counts) if view_counts else 0
        avg_likes = sum(like_counts) / len(like_counts) if like_counts else 0
        avg_comments = sum(comment_counts) / len(comment_counts) if comment_counts else 0
        max_views = max(view_counts) if view_counts else 0

        # Engagement rate
        total_views = sum(view_counts)
        total_likes = sum(like_counts)
        engagement_rate = (total_likes / total_views * 100) if total_views > 0 else 0

        # Trend
        trend_data = analyze_trends(videos)
        trend_label = trend_data.get("trend_label", "不明") if trend_data else "不明"
        posting_freq = trend_data.get("posting_frequency") if trend_data else None

        comp = {
            "username": username,
            "followers": profile.get("followers", "不明") if profile else "不明",
            "total_posts": len(videos),
            "avg_views": int(avg_views),
            "avg_likes": int(avg_likes),
            "avg_comments": int(avg_comments),
            "max_views": max_views,
            "engagement_rate": round(engagement_rate, 2),
            "trend": trend_label,
            "posting_frequency": posting_freq,
        }
        competitors.append(comp)

    return competitors


def format_competitor_comparison(main_data, competitors):
    """Format comparison data for the AI prompt.

    Args:
        main_data: Dict with the main account's stats.
        competitors: List of competitor data dicts from fetch_competitor_data().

    Returns:
        Formatted comparison string.
    """
    if not competitors:
        return ""

    valid_competitors = [c for c in competitors if "error" not in c]
    if not valid_competitors:
        return ""

    parts = []
    parts.append("### 比較対象アカウント一覧\n")

    # Header
    parts.append("| 指標 | **分析対象** |")
    header_sep = "|------|------|"
    for c in valid_competitors:
        parts[0 + 1] += f" @{c['username']} |"
        header_sep += "------|"
    parts.append(header_sep)

    # Rows
    def add_row(label, main_val, comp_key):
        row = f"| {label} | {main_val} |"
        for c in valid_competitors:
            row += f" {c.get(comp_key, '—')} |"
        parts.append(row)

    add_row("フォロワー", main_data.get("followers", "—"), "followers")
    add_row("投稿数", main_data.get("total_posts", "—"), "total_posts")
    add_row("平均再生数", f"{main_data.get('avg_views', 0):,}", "avg_views")
    add_row("平均いいね", f"{main_data.get('avg_likes', 0):,}", "avg_likes")
    add_row("最高再生数", f"{main_data.get('max_views', 0):,}", "max_views")
    add_row("エンゲージメント率", f"{main_data.get('engagement_rate', 0)}%", "engagement_rate")
    add_row("トレンド", main_data.get("trend", "—"), "trend")

    freq = main_data.get("posting_frequency")
    freq_str = f"週{freq}本" if freq else "—"
    row = f"| 投稿頻度 | {freq_str} |"
    for c in valid_competitors:
        cf = c.get("posting_frequency")
        row += f" {'週' + str(cf) + '本' if cf else '—'} |"
    parts.append(row)

    parts.append("")

    # Format competitor values for readability
    for c in valid_competitors:
        if isinstance(c.get("avg_views"), int):
            c["avg_views"] = f"{c['avg_views']:,}"
        if isinstance(c.get("avg_likes"), int):
            c["avg_likes"] = f"{c['avg_likes']:,}"
        if isinstance(c.get("max_views"), int):
            c["max_views"] = f"{c['max_views']:,}"
        if isinstance(c.get("engagement_rate"), float):
            c["engagement_rate"] = f"{c['engagement_rate']}%"
        if isinstance(c.get("followers"), int):
            c["followers"] = f"{c['followers']:,}"

    # Failed accounts
    failed = [c for c in competitors if "error" in c]
    if failed:
        parts.append(f"※ 取得失敗: {', '.join(c['username'] for c in failed)}")

    return "\n".join(parts)


def build_main_account_stats(videos, profile):
    """Build stats dict for the main account (same format as competitor).

    Args:
        videos: List of video dicts.
        profile: Profile dict.

    Returns:
        Stats dict.
    """
    if not videos:
        return {}

    view_counts = [v.get("view_count", 0) or 0 for v in videos]
    like_counts = [v.get("like_count", 0) or 0 for v in videos]

    avg_views = sum(view_counts) / len(view_counts) if view_counts else 0
    avg_likes = sum(like_counts) / len(like_counts) if like_counts else 0
    max_views = max(view_counts) if view_counts else 0

    total_views = sum(view_counts)
    total_likes = sum(like_counts)
    engagement_rate = (total_likes / total_views * 100) if total_views > 0 else 0

    trend_data = analyze_trends(videos)
    trend_label = trend_data.get("trend_label", "不明") if trend_data else "不明"
    posting_freq = trend_data.get("posting_frequency") if trend_data else None

    return {
        "followers": profile.get("followers", "不明") if profile else "不明",
        "total_posts": len(videos),
        "avg_views": int(avg_views),
        "avg_likes": int(avg_likes),
        "max_views": max_views,
        "engagement_rate": round(engagement_rate, 2),
        "trend": trend_label,
        "posting_frequency": posting_freq,
    }
