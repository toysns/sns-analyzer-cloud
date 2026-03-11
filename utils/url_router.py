"""URL routing: detect platform and dispatch to the appropriate data collector.

Unified entry point for both Instagram (Apify) and TikTok (yt-dlp) flows.
The user just provides a URL; this module figures out which backend to use.
"""

import logging
import re

logger = logging.getLogger(__name__)


def detect_platform(url_or_username):
    """Detect platform from URL or username input.

    Returns:
        "instagram", "tiktok", or None if unrecognizable.
    """
    text = url_or_username.strip().lower()

    if "instagram.com" in text:
        return "instagram"
    if "tiktok.com" in text:
        return "tiktok"

    # Bare username defaults to TikTok (existing behavior)
    return None


def extract_username(url_or_username, platform):
    """Extract username based on platform.

    Args:
        url_or_username: URL string or bare username.
        platform: "instagram" or "tiktok".

    Returns:
        Username string or None if extraction failed.
    """
    if platform == "instagram":
        return _extract_instagram_username(url_or_username)
    elif platform == "tiktok":
        return _extract_tiktok_username(url_or_username)
    return None


def _extract_instagram_username(url_or_username):
    """Extract Instagram username from URL or bare input."""
    match = re.search(r"instagram\.com/([^/?#]+)", url_or_username)
    if match:
        username = match.group(1)
        if username in ("reel", "p", "stories", "explore", "accounts"):
            return None
        return username.rstrip("/")
    return url_or_username.lstrip("@").strip()


def _extract_tiktok_username(url_or_username):
    """Extract TikTok username from URL or bare input."""
    match = re.search(r"tiktok\.com/@([^/?]+)", url_or_username)
    if match:
        return match.group(1)
    return url_or_username.lstrip("@").strip()


def should_use_apify(platform):
    """Determine if Apify should be used for data collection.

    Instagram → Apify (scraper API, reliable & cheap)
    TikTok → yt-dlp (existing pipeline, works well for TikTok)
    """
    return platform == "instagram"


def get_collection_method_label(platform):
    """Get a human-readable label for the collection method being used."""
    if platform == "instagram":
        return "Apify (Instagram Scraper)"
    return "yt-dlp (ダイレクト取得)"
