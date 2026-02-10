"""TikTok metadata fetching via yt-dlp."""

import json
import logging
import re
import subprocess
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)


def extract_username(url_or_username):
    """Extract TikTok username from URL or return as-is.

    Accepts:
        - https://www.tiktok.com/@username
        - @username
        - username
    """
    match = re.search(r"tiktok\.com/@([^/?]+)", url_or_username)
    if match:
        return match.group(1)
    return url_or_username.lstrip("@").strip()


def fetch_tiktok_profile(username):
    """Fetch TikTok user profile info.

    Returns:
        dict with 'username', 'display_name', 'followers' or None on failure.
    """
    url = f"https://www.tiktok.com/@{username}"
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--flat-playlist",
                "--dump-json",
                "--playlist-end", "1",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.warning("yt-dlp profile fetch failed: %s", result.stderr[:300])
            return None

        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                return {
                    "username": username,
                    "display_name": data.get("uploader", username),
                    "followers": data.get("channel_follower_count", "不明"),
                }
            except json.JSONDecodeError:
                continue

        return None
    except subprocess.TimeoutExpired:
        logger.error("TikTok profile fetch timed out for %s", username)
        return None
    except FileNotFoundError:
        logger.error("yt-dlp not found")
        return None


def fetch_tiktok_videos(username, max_count=100):
    """Fetch video metadata from a TikTok account.

    Returns:
        List of dicts with video metadata, sorted by view_count desc.
        Returns None on failure.
    """
    url = f"https://www.tiktok.com/@{username}"
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--flat-playlist",
                "--dump-json",
                f"--playlist-end={max_count}",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            logger.warning("yt-dlp video fetch failed: %s", result.stderr[:300])
            return None

        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                timestamp = data.get("timestamp")
                upload_date = ""
                if timestamp:
                    upload_date = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
                elif data.get("upload_date"):
                    raw = data["upload_date"]
                    upload_date = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}" if len(raw) == 8 else raw

                video = {
                    "id": data.get("id", ""),
                    "title": data.get("title", ""),
                    "view_count": data.get("view_count", 0) or 0,
                    "like_count": data.get("like_count", 0) or 0,
                    "comment_count": data.get("comment_count", 0) or 0,
                    "upload_date": upload_date,
                    "url": data.get("url") or data.get("webpage_url") or f"https://www.tiktok.com/@{username}/video/{data.get('id', '')}",
                    "duration": data.get("duration", 0) or 0,
                }
                videos.append(video)
            except json.JSONDecodeError:
                continue

        if not videos:
            return None

        videos.sort(key=lambda x: x["view_count"], reverse=True)
        return videos

    except subprocess.TimeoutExpired:
        logger.error("TikTok video fetch timed out for %s", username)
        return None
    except FileNotFoundError:
        logger.error("yt-dlp not found")
        return None


def videos_to_dataframe(videos):
    """Convert video list to a display-ready DataFrame.

    Returns:
        pd.DataFrame with Japanese column names.
    """
    rows = []
    for i, v in enumerate(videos, 1):
        rows.append({
            "順位": i,
            "タイトル": v["title"][:50] if v["title"] else "",
            "再生回数": v["view_count"],
            "いいね数": v["like_count"],
            "コメント数": v["comment_count"],
            "投稿日時": v["upload_date"],
            "URL": v["url"],
        })
    return pd.DataFrame(rows)


def sample_videos_for_analysis(videos, count=5):
    """Select videos for analysis using the sampling strategy.

    Strategy:
        - >= 5 videos: top 2 + middle 2 + bottom 1
        - 3-4 videos: top 2 + bottom 1
        - < 3 videos: all

    Args:
        videos: List of video dicts, already sorted by view_count desc.
        count: Target number of videos (default 5).

    Returns:
        List of selected video dicts.
    """
    n = len(videos)
    if n == 0:
        return []
    if n <= 2:
        return list(videos)
    if n <= 4:
        return [videos[0], videos[1], videos[-1]]

    mid = n // 2
    selected = [
        videos[0],
        videos[1],
        videos[mid - 1],
        videos[mid],
        videos[-1],
    ]
    return selected[:count]
