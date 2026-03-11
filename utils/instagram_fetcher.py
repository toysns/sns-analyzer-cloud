"""Instagram metadata fetching via Manus API (primary) with yt-dlp fallback.

Data collection strategy:
    - Primary: Manus browser agent (reliable for Instagram public profiles)
    - Fallback: yt-dlp (used when Manus is unavailable or fails)
"""

import json
import logging
import re
import subprocess
from datetime import datetime

import pandas as pd

from utils.manus_client import collect_instagram_data, get_manus_api_key

logger = logging.getLogger(__name__)


def extract_instagram_username(url_or_username):
    """Extract Instagram username from URL or return as-is.

    Accepts:
        - https://www.instagram.com/username/
        - https://www.instagram.com/username/reels/
        - @username
        - username
    """
    match = re.search(r"instagram\.com/([^/?#]+)", url_or_username)
    if match:
        username = match.group(1)
        # Filter out non-profile paths
        if username in ("reel", "p", "stories", "explore", "accounts"):
            return None
        return username.rstrip("/")
    return url_or_username.lstrip("@").strip()


def fetch_instagram_profile(username):
    """Fetch Instagram user profile info via yt-dlp.

    Returns:
        dict with 'username', 'display_name', 'followers' or None on failure.
    """
    url = f"https://www.instagram.com/{username}/reels/"
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--flat-playlist",
                "--dump-json",
                "--playlist-end", "1",
                "--no-check-certificates",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            logger.warning("yt-dlp Instagram profile fetch failed: %s", result.stderr[:300])
            return None

        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                return {
                    "username": username,
                    "display_name": data.get("uploader", data.get("channel", username)),
                    "followers": data.get("channel_follower_count", "不明"),
                }
            except json.JSONDecodeError:
                continue

        return None
    except subprocess.TimeoutExpired:
        logger.error("Instagram profile fetch timed out for %s", username)
        return None
    except FileNotFoundError:
        logger.error("yt-dlp not found")
        return None


def fetch_instagram_videos(username, max_count=50):
    """Fetch Reels metadata from an Instagram account.

    Tries the /reels/ tab first (Reels only), falls back to the main
    profile page if needed.

    Returns:
        List of dicts with video metadata, sorted by view_count desc.
        Returns None on failure.
    """
    # Try Reels tab first, then main profile
    urls_to_try = [
        f"https://www.instagram.com/{username}/reels/",
        f"https://www.instagram.com/{username}/",
    ]

    for url in urls_to_try:
        videos = _fetch_videos_from_url(url, username, max_count)
        if videos:
            return videos

    return None


def _fetch_videos_from_url(url, username, max_count):
    """Fetch video metadata from a specific Instagram URL.

    Returns:
        List of video dicts or None on failure.
    """
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--flat-playlist",
                "--dump-json",
                "--no-check-certificates",
                "--retries", "3",
                f"--playlist-end={max_count}",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            logger.warning("yt-dlp Instagram video fetch failed for %s: %s", url, result.stderr[:300])
            return None

        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
                video = _parse_video_entry(data, username)
                if video:
                    videos.append(video)
            except json.JSONDecodeError:
                continue

        if not videos:
            return None

        videos.sort(key=lambda x: x["view_count"], reverse=True)
        return videos

    except subprocess.TimeoutExpired:
        logger.error("Instagram video fetch timed out for %s", url)
        return None
    except FileNotFoundError:
        logger.error("yt-dlp not found")
        return None


def _parse_video_entry(data, username):
    """Parse a single yt-dlp JSON entry into a normalized video dict.

    Returns:
        dict with video metadata or None if not a video.
    """
    # Skip non-video entries (images, carousels without video)
    media_type = data.get("_type", "")
    if media_type == "playlist":
        return None

    video_id = data.get("id", "")

    # Parse upload date
    timestamp = data.get("timestamp")
    upload_date = ""
    if timestamp:
        upload_date = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
    elif data.get("upload_date"):
        raw = data["upload_date"]
        upload_date = f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}" if len(raw) == 8 else raw

    # Build URL
    url = data.get("url") or data.get("webpage_url") or ""
    if not url and video_id:
        url = f"https://www.instagram.com/reel/{video_id}/"

    # Instagram often reports view_count as 0 or None for Reels;
    # use like_count as a fallback signal for popularity
    view_count = data.get("view_count", 0) or 0
    like_count = data.get("like_count", 0) or 0
    comment_count = data.get("comment_count", 0) or 0

    title = data.get("title") or data.get("description", "")
    if title:
        title = title[:100]  # Truncate long captions
    else:
        title = "無題"

    return {
        "id": video_id,
        "title": title,
        "view_count": view_count,
        "like_count": like_count,
        "comment_count": comment_count,
        "upload_date": upload_date,
        "url": url,
        "duration": data.get("duration", 0) or 0,
    }


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


# =============================================================================
# Manus-based Instagram collection (primary method)
# =============================================================================

def is_manus_available():
    """Check if Manus API key is configured."""
    return bool(get_manus_api_key())


def fetch_instagram_via_manus(username, max_count=30, progress_callback=None):
    """Fetch Instagram profile and videos using Manus browser agent.

    Args:
        username: Instagram username (without @).
        max_count: Max number of videos to collect.
        progress_callback: Optional callable(str) for status updates.

    Returns:
        (profile, videos, error): profile dict, list of video dicts, or error string.
    """
    api_key = get_manus_api_key()
    if not api_key:
        return None, None, "MANUS_API_KEY未設定"

    profile, videos, error = collect_instagram_data(
        username,
        api_key=api_key,
        max_videos=max_count,
        progress_callback=progress_callback,
    )

    if error:
        logger.warning("Manus collection failed for @%s: %s", username, error)
        return profile, videos, error

    return profile, videos, None


def fetch_instagram_auto(username, max_count=30, progress_callback=None):
    """Auto-fetch Instagram data: Manus first, yt-dlp fallback.

    This is the unified entry point for Instagram data collection.
    It tries Manus first (better for Instagram) and falls back to
    yt-dlp if Manus is unavailable or fails.

    Args:
        username: Instagram username (without @).
        max_count: Max number of videos to collect.
        progress_callback: Optional callable(str) for status updates.

    Returns:
        (profile, videos, method, error):
            profile: dict with profile info.
            videos: list of video dicts.
            method: "manus" or "ytdlp" indicating which method succeeded.
            error: error string if both methods failed.
    """
    # Try Manus first
    if is_manus_available():
        if progress_callback:
            progress_callback("Manus AIでInstagramデータを収集中...")

        profile, videos, error = fetch_instagram_via_manus(
            username, max_count, progress_callback
        )
        if videos:
            logger.info("Manus collection succeeded for @%s: %d videos", username, len(videos))
            return profile, videos, "manus", None

        logger.warning("Manus failed for @%s, falling back to yt-dlp: %s", username, error)
        if progress_callback:
            progress_callback(f"Manus失敗 ({error})、yt-dlpにフォールバック中...")
    else:
        if progress_callback:
            progress_callback("MANUS_API_KEY未設定のため、yt-dlpで取得中...")

    # Fallback to yt-dlp
    if progress_callback:
        progress_callback("yt-dlpでInstagramデータを取得中...")

    profile = fetch_instagram_profile(username)
    videos = fetch_instagram_videos(username, max_count)

    if videos:
        return profile, videos, "ytdlp", None

    return profile, None, "ytdlp", "Instagram動画の取得に失敗しました（Manus・yt-dlp両方失敗）"
