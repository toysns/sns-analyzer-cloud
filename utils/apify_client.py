"""Apify API client for Instagram data collection.

Uses Apify's Instagram Reel Scraper actor to collect Reel metadata.
Much cheaper (~$0.003/query) and more reliable than browser-agent approaches.

API Reference: https://docs.apify.com/api/v2
Actor: apify/instagram-reel-scraper
"""

import logging
import re
from datetime import datetime

import requests
from utils.config import get_secret

logger = logging.getLogger(__name__)

# Apify actor for Instagram reels scraping
ACTOR_ID = "apify~instagram-reel-scraper"
APIFY_API_BASE = "https://api.apify.com/v2"
# Synchronous run timeout (Apify max: 300s)
SYNC_TIMEOUT = 290


def get_apify_api_token():
    """Get Apify API token from environment or Streamlit Cloud secrets."""
    return get_secret("APIFY_API_TOKEN", "APIFY_TOKEN")


def collect_instagram_data(username, api_token=None, max_videos=30,
                           progress_callback=None):
    """Collect Instagram profile and Reel data via Apify.

    Uses the synchronous run endpoint to start the actor, wait for
    completion, and return dataset items in a single HTTP call.

    Args:
        username: Instagram username (without @).
        api_token: Apify API token. Uses env var if not provided.
        max_videos: Maximum number of results to collect.
        progress_callback: Optional callable(str) for UI status updates.

    Returns:
        (profile, videos, error): profile dict, list of video dicts, or error.
    """
    api_token = api_token or get_apify_api_token()
    if not api_token:
        return None, None, "APIFY_API_TOKEN / APIFY_TOKEN未設定"

    if progress_callback:
        progress_callback("Apifyでデータ収集中...")

    # Build actor input (instagram-reel-scraper uses "username" not "usernames")
    run_input = {
        "username": [username],
        "resultsLimit": max_videos,
    }

    try:
        # Use synchronous endpoint: run actor + get dataset items in one call
        url = (
            f"{APIFY_API_BASE}/acts/{ACTOR_ID}"
            f"/run-sync-get-dataset-items"
            f"?token={api_token}"
            f"&format=json"
            f"&clean=true"
        )

        if progress_callback:
            progress_callback(f"Apify Actor実行中 (@{username})...")

        resp = requests.post(
            url,
            json=run_input,
            headers={"Content-Type": "application/json"},
            timeout=SYNC_TIMEOUT + 10,  # HTTP timeout slightly longer than Apify timeout
        )

        if resp.status_code == 408:
            return None, None, "Apifyタイムアウト（5分超過）。動画数を減らしてください。"

        resp.raise_for_status()
        items = resp.json()

        if not items:
            return None, None, "Apifyから結果が返りませんでした"

        if progress_callback:
            progress_callback(f"収集完了: {len(items)}件のデータを解析中...")

        return _parse_items(items, username)

    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else "unknown"
        body = e.response.text[:200] if e.response is not None else ""
        return None, None, f"Apify APIエラー: {status} {body}"
    except requests.exceptions.Timeout:
        return None, None, "Apify APIリクエストがタイムアウトしました"
    except requests.exceptions.RequestException as e:
        return None, None, f"Apify APIリクエスト失敗: {e}"


def _parse_items(items, username):
    """Parse Apify dataset items into profile and videos.

    The Instagram Profile Scraper returns items where each item
    represents a post/reel with profile info embedded.

    Args:
        items: List of dataset item dicts from Apify.
        username: The Instagram username for fallback values.

    Returns:
        (profile, videos, error)
    """
    profile = None
    videos = []

    for item in items:
        # Extract profile from the first item (profile data is repeated)
        if profile is None:
            profile = _extract_profile(item, username)

        # Extract video/reel data
        video = _extract_video(item)
        if video:
            videos.append(video)

    if not videos:
        return profile, None, "動画データが見つかりませんでした"

    # Sort by view_count descending
    videos.sort(key=lambda x: x["view_count"], reverse=True)

    return profile, videos, None


def _extract_profile(item, username):
    """Extract profile info from an Apify reel-scraper item."""
    return {
        "username": item.get("ownerUsername") or item.get("username") or username,
        "display_name": item.get("ownerFullName") or item.get("ownerUsername") or username,
        "followers": _to_int(
            item.get("followersCount")
            or item.get("ownerFollowerCount")
            or 0
        ),
    }


def _extract_video(item):
    """Extract video/reel data from an Apify reel-scraper dataset item.

    The instagram-reel-scraper returns reels directly so no type filtering needed.
    Handles various field names that Apify may return.
    """
    # Extract shortcode/ID
    shortcode = (
        item.get("shortCode") or item.get("shortcode")
        or item.get("id") or item.get("inputUrl") or ""
    )

    # Build URL
    url = item.get("url") or item.get("inputUrl") or ""
    if not url and shortcode:
        url = f"https://www.instagram.com/reel/{shortcode}/"

    # Extract caption
    caption = item.get("caption") or ""
    if caption:
        caption = caption[:100]
    else:
        caption = "無題"

    # Parse timestamp
    upload_date = ""
    timestamp = item.get("timestamp") or item.get("createDateTime")
    if timestamp:
        try:
            if isinstance(timestamp, str):
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                upload_date = dt.strftime("%Y-%m-%d")
            elif isinstance(timestamp, (int, float)):
                upload_date = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")
        except (ValueError, OSError):
            pass

    # Direct video download URL (Apify often provides this)
    video_url = (
        item.get("videoUrl") or item.get("video_url")
        or item.get("displayUrl") or ""
    )

    # Reel scraper uses playCount/playsCount for views, likesCount, commentsCount
    return {
        "id": shortcode,
        "title": caption,
        "view_count": _to_int(
            item.get("playCount") or item.get("playsCount")
            or item.get("videoPlayCount") or item.get("videoViewCount")
            or item.get("viewCount") or 0
        ),
        "like_count": _to_int(
            item.get("likesCount") or item.get("likes") or 0
        ),
        "comment_count": _to_int(
            item.get("commentsCount") or item.get("comments") or 0
        ),
        "upload_date": upload_date,
        "url": url,
        "video_url": video_url,
        "duration": _to_int(
            item.get("videoDuration") or item.get("duration") or 0
        ),
    }


def _to_int(value):
    """Convert a value to int, handling strings like '1.2K', '5万', etc."""
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if not isinstance(value, str):
        return 0

    value = value.strip().replace(",", "").replace(" ", "")
    if not value:
        return 0

    multiplier = 1
    if value.upper().endswith("K"):
        multiplier = 1000
        value = value[:-1]
    elif value.upper().endswith("M"):
        multiplier = 1_000_000
        value = value[:-1]
    elif value.endswith("万"):
        multiplier = 10_000
        value = value[:-1]
    elif value.endswith("億"):
        multiplier = 100_000_000
        value = value[:-1]

    try:
        return int(float(value) * multiplier)
    except (ValueError, TypeError):
        return 0
