"""Time-series trend analysis for video performance data."""

from datetime import datetime, timedelta


def analyze_trends(videos):
    """Analyze posting and performance trends from video metadata.

    Args:
        videos: List of video dicts with view_count, like_count,
                comment_count, upload_date fields.
                Expected to be sorted by view_count desc.

    Returns:
        Dict with trend analysis data, or None if insufficient data.
    """
    if not videos or len(videos) < 3:
        return None

    # Sort by date for time-series analysis
    dated_videos = []
    for v in videos:
        date_str = v.get("upload_date", "")
        if date_str:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d")
                dated_videos.append({**v, "_date": dt})
            except ValueError:
                continue

    if len(dated_videos) < 3:
        return None

    dated_videos.sort(key=lambda x: x["_date"])

    result = {}

    # --- Posting frequency ---
    dates = [v["_date"] for v in dated_videos]
    total_days = (dates[-1] - dates[0]).days
    if total_days > 0:
        posts_per_week = len(dated_videos) / (total_days / 7)
        result["posting_frequency"] = round(posts_per_week, 1)
        result["period_days"] = total_days
        result["total_posts_analyzed"] = len(dated_videos)
    else:
        result["posting_frequency"] = None
        result["period_days"] = 0
        result["total_posts_analyzed"] = len(dated_videos)

    # --- Posting gaps ---
    gaps = []
    for i in range(1, len(dates)):
        gap = (dates[i] - dates[i - 1]).days
        gaps.append(gap)
    if gaps:
        result["avg_gap_days"] = round(sum(gaps) / len(gaps), 1)
        result["max_gap_days"] = max(gaps)
        result["min_gap_days"] = min(gaps)

    # --- Performance trend (compare first half vs second half) ---
    mid = len(dated_videos) // 2
    first_half = dated_videos[:mid]
    second_half = dated_videos[mid:]

    def avg_metric(vids, key):
        vals = [v.get(key, 0) or 0 for v in vids]
        return sum(vals) / len(vals) if vals else 0

    first_avg_views = avg_metric(first_half, "view_count")
    second_avg_views = avg_metric(second_half, "view_count")
    first_avg_likes = avg_metric(first_half, "like_count")
    second_avg_likes = avg_metric(second_half, "like_count")

    if first_avg_views > 0:
        view_change = ((second_avg_views - first_avg_views) / first_avg_views) * 100
    else:
        view_change = 0

    if first_avg_likes > 0:
        like_change = ((second_avg_likes - first_avg_likes) / first_avg_likes) * 100
    else:
        like_change = 0

    result["performance_trend"] = {
        "first_half_avg_views": int(first_avg_views),
        "second_half_avg_views": int(second_avg_views),
        "view_change_pct": round(view_change, 1),
        "first_half_avg_likes": int(first_avg_likes),
        "second_half_avg_likes": int(second_avg_likes),
        "like_change_pct": round(like_change, 1),
    }

    # Determine trend direction
    if view_change > 20:
        result["trend_direction"] = "growth"
        result["trend_label"] = "成長中"
    elif view_change < -20:
        result["trend_direction"] = "declining"
        result["trend_label"] = "低下傾向"
    else:
        result["trend_direction"] = "stable"
        result["trend_label"] = "安定"

    # --- Engagement rate trend ---
    first_eng = []
    for v in first_half:
        views = v.get("view_count", 0) or 0
        likes = v.get("like_count", 0) or 0
        if views > 0:
            first_eng.append(likes / views * 100)
    second_eng = []
    for v in second_half:
        views = v.get("view_count", 0) or 0
        likes = v.get("like_count", 0) or 0
        if views > 0:
            second_eng.append(likes / views * 100)

    if first_eng and second_eng:
        first_avg_eng = sum(first_eng) / len(first_eng)
        second_avg_eng = sum(second_eng) / len(second_eng)
        result["engagement_trend"] = {
            "first_half_avg_rate": round(first_avg_eng, 2),
            "second_half_avg_rate": round(second_avg_eng, 2),
        }

    # --- Top performing day of week ---
    day_performance = {}
    day_names_ja = {
        0: "月曜", 1: "火曜", 2: "水曜",
        3: "木曜", 4: "金曜", 5: "土曜", 6: "日曜",
    }
    for v in dated_videos:
        dow = v["_date"].weekday()
        if dow not in day_performance:
            day_performance[dow] = {"views": [], "count": 0}
        day_performance[dow]["views"].append(v.get("view_count", 0) or 0)
        day_performance[dow]["count"] += 1

    if day_performance:
        day_stats = []
        for dow, data in day_performance.items():
            avg_views = sum(data["views"]) / len(data["views"]) if data["views"] else 0
            day_stats.append({
                "day": day_names_ja[dow],
                "avg_views": int(avg_views),
                "post_count": data["count"],
            })
        day_stats.sort(key=lambda x: x["avg_views"], reverse=True)
        result["day_of_week_performance"] = day_stats

    # --- Viral outlier detection ---
    all_views = [v.get("view_count", 0) or 0 for v in dated_videos]
    avg_views = sum(all_views) / len(all_views)
    std_dev = (sum((x - avg_views) ** 2 for x in all_views) / len(all_views)) ** 0.5
    threshold = avg_views + 2 * std_dev if std_dev > 0 else avg_views * 3

    viral_videos = []
    for v in dated_videos:
        if (v.get("view_count", 0) or 0) > threshold and threshold > 0:
            viral_videos.append({
                "title": v.get("title", "")[:40],
                "views": v.get("view_count", 0),
                "date": v.get("upload_date", ""),
            })
    result["viral_outliers"] = viral_videos
    result["viral_count"] = len(viral_videos)
    result["average_views"] = int(avg_views)

    return result


def format_trend_analysis(analysis):
    """Format trend analysis into readable text for the AI prompt.

    Args:
        analysis: Dict from analyze_trends().

    Returns:
        Formatted string.
    """
    if not analysis:
        return ""

    parts = []
    parts.append(f"分析期間: {analysis.get('period_days', 0)}日間 / "
                 f"分析投稿数: {analysis.get('total_posts_analyzed', 0)}本")

    # Posting frequency
    freq = analysis.get("posting_frequency")
    if freq:
        parts.append(f"投稿頻度: 週{freq}本（平均投稿間隔: {analysis.get('avg_gap_days', 0)}日 / "
                     f"最大空白: {analysis.get('max_gap_days', 0)}日）")

    # Performance trend
    trend = analysis.get("performance_trend", {})
    label = analysis.get("trend_label", "")
    if trend:
        parts.append(f"パフォーマンス推移: 【{label}】")
        parts.append(f"  前半平均再生数: {trend['first_half_avg_views']:,} → "
                     f"後半平均再生数: {trend['second_half_avg_views']:,}（{trend['view_change_pct']:+.1f}%）")
        parts.append(f"  前半平均いいね: {trend['first_half_avg_likes']:,} → "
                     f"後半平均いいね: {trend['second_half_avg_likes']:,}（{trend['like_change_pct']:+.1f}%）")

    # Engagement trend
    eng = analysis.get("engagement_trend", {})
    if eng:
        parts.append(f"エンゲージメント率推移: 前半 {eng['first_half_avg_rate']:.2f}% → "
                     f"後半 {eng['second_half_avg_rate']:.2f}%")

    # Day of week
    day_stats = analysis.get("day_of_week_performance", [])
    if day_stats:
        best = day_stats[0]
        parts.append(f"最もパフォーマンスが高い曜日: {best['day']}（平均{best['avg_views']:,}再生 / {best['post_count']}投稿）")

    # Viral
    avg = analysis.get("average_views", 0)
    viral = analysis.get("viral_outliers", [])
    parts.append(f"全体平均再生数: {avg:,}")
    if viral:
        parts.append(f"バイラル投稿（平均の2σ超え）: {len(viral)}本")
        for v in viral[:3]:
            parts.append(f"  - {v['title']} ({v['views']:,}再生, {v['date']})")

    return "\n".join(parts)
