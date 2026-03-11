"""Manus API client for Instagram data collection via browser agent.

Manus is used as a data collection backend for Instagram accounts,
where yt-dlp is unreliable. The client creates a task that instructs
Manus's browser agent to visit an Instagram profile and collect
Reel metadata in structured JSON format.

API Reference: https://open.manus.im/docs
"""

import json
import logging
import os
import time

import requests

logger = logging.getLogger(__name__)

MANUS_API_BASE = "https://api.manus.im/v1"
DEFAULT_TIMEOUT = 30
POLL_INTERVAL = 10  # seconds between status checks
MAX_POLL_TIME = 300  # 5 minutes max wait


def get_manus_api_key():
    """Get Manus API key from environment."""
    return os.environ.get("MANUS_API_KEY", "")


def _headers(api_key):
    """Build request headers."""
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _build_instagram_collection_prompt(username, max_videos=30):
    """Build the task prompt for Manus to collect Instagram Reel data.

    The prompt instructs Manus's browser agent to:
    1. Visit the Instagram profile
    2. Navigate to the Reels tab
    3. Collect metadata for each Reel
    4. Return structured JSON
    """
    return f"""Visit the Instagram profile https://www.instagram.com/{username}/reels/ and collect data about their Reels.

IMPORTANT: You must return the data as valid JSON and nothing else.

Instructions:
1. Go to https://www.instagram.com/{username}/reels/
2. Scroll through the Reels tab to load up to {max_videos} Reels
3. For each Reel, collect:
   - The Reel URL (e.g., https://www.instagram.com/reel/ABC123/)
   - The caption/title text (first 100 characters)
   - View count (if visible)
   - Like count (if visible)
   - Comment count (if visible)
   - Upload date (if visible, format: YYYY-MM-DD)
4. Also collect the profile info:
   - Display name
   - Follower count
   - Following count
   - Total post count
   - Bio text

Return ONLY a JSON object in this exact format:
{{
  "profile": {{
    "username": "{username}",
    "display_name": "",
    "followers": 0,
    "following": 0,
    "total_posts": 0,
    "bio": ""
  }},
  "videos": [
    {{
      "id": "reel_shortcode",
      "title": "caption text...",
      "url": "https://www.instagram.com/reel/ABC123/",
      "view_count": 0,
      "like_count": 0,
      "comment_count": 0,
      "upload_date": "2025-01-01",
      "duration": 0
    }}
  ]
}}

If a value is not visible, use 0 for numbers and "" for strings.
Return ONLY the JSON, no other text."""


def create_collection_task(username, api_key=None, max_videos=30):
    """Create a Manus task to collect Instagram Reel data.

    Args:
        username: Instagram username (without @).
        api_key: Manus API key. Uses env var if not provided.
        max_videos: Maximum number of videos to collect.

    Returns:
        (task_id, error): task_id string on success, or (None, error_message).
    """
    api_key = api_key or get_manus_api_key()
    if not api_key:
        return None, "MANUS_API_KEY is not set"

    prompt = _build_instagram_collection_prompt(username, max_videos)

    try:
        resp = requests.post(
            f"{MANUS_API_BASE}/tasks",
            headers=_headers(api_key),
            json={"prompt": prompt},
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        task_id = data.get("id") or data.get("task_id")
        if not task_id:
            return None, f"No task_id in response: {data}"
        logger.info("Manus task created: %s for @%s", task_id, username)
        return task_id, None
    except requests.exceptions.HTTPError as e:
        return None, f"Manus API error: {e.response.status_code} {e.response.text[:200]}"
    except requests.exceptions.RequestException as e:
        return None, f"Manus API request failed: {e}"


def poll_task_status(task_id, api_key=None):
    """Check the status of a Manus task.

    Returns:
        (status, result_data, error): status string, result dict (if complete), error message.
    """
    api_key = api_key or get_manus_api_key()
    if not api_key:
        return None, None, "MANUS_API_KEY is not set"

    try:
        resp = requests.get(
            f"{MANUS_API_BASE}/tasks/{task_id}",
            headers=_headers(api_key),
            timeout=DEFAULT_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()

        status = data.get("status", "unknown")
        return status, data, None
    except requests.exceptions.RequestException as e:
        return None, None, f"Manus API request failed: {e}"


def wait_for_task(task_id, api_key=None, max_wait=MAX_POLL_TIME,
                  poll_interval=POLL_INTERVAL, progress_callback=None):
    """Wait for a Manus task to complete, polling periodically.

    Args:
        task_id: The Manus task ID.
        api_key: Manus API key.
        max_wait: Maximum seconds to wait.
        poll_interval: Seconds between polls.
        progress_callback: Optional callable(status_str, elapsed_sec) for UI updates.

    Returns:
        (result_data, error): The task result dict or (None, error_message).
    """
    api_key = api_key or get_manus_api_key()
    start = time.time()

    while True:
        elapsed = time.time() - start
        if elapsed > max_wait:
            return None, f"Manus task timed out after {max_wait}s"

        status, data, error = poll_task_status(task_id, api_key)
        if error:
            return None, error

        if progress_callback:
            progress_callback(status, int(elapsed))

        if status in ("completed", "done", "finished"):
            return data, None
        elif status in ("failed", "error", "cancelled"):
            error_msg = data.get("error", "") if data else ""
            return None, f"Manus task {status}: {error_msg}"

        time.sleep(poll_interval)


def parse_collection_result(task_data):
    """Parse Manus task result into profile and videos.

    Extracts the JSON output from the task result, handling various
    response formats from Manus.

    Args:
        task_data: The raw task response dict from Manus API.

    Returns:
        (profile, videos, error): profile dict, list of video dicts, or error.
    """
    # Try to find the output/result text from different possible response formats
    output_text = None
    for key in ("output", "result", "response", "content"):
        if key in task_data and task_data[key]:
            output_text = task_data[key]
            break

    # Check nested structures
    if output_text is None:
        outputs = task_data.get("outputs", [])
        if outputs:
            for out in outputs:
                if isinstance(out, dict):
                    output_text = out.get("content") or out.get("text") or out.get("output")
                elif isinstance(out, str):
                    output_text = out
                if output_text:
                    break

    if not output_text:
        return None, None, "No output found in Manus task result"

    # If output_text is already a dict, use directly
    if isinstance(output_text, dict):
        parsed = output_text
    else:
        # Extract JSON from the output text (might have surrounding text)
        parsed = _extract_json(str(output_text))

    if not parsed:
        return None, None, "Could not parse JSON from Manus output"

    profile = parsed.get("profile")
    videos = parsed.get("videos", [])

    if not videos:
        return profile, None, "No videos found in Manus output"

    # Normalize video data
    normalized = []
    for v in videos:
        normalized.append({
            "id": v.get("id", ""),
            "title": v.get("title", "無題")[:100],
            "view_count": _to_int(v.get("view_count", 0)),
            "like_count": _to_int(v.get("like_count", 0)),
            "comment_count": _to_int(v.get("comment_count", 0)),
            "upload_date": v.get("upload_date", ""),
            "url": v.get("url", ""),
            "duration": _to_int(v.get("duration", 0)),
        })

    # Sort by view_count descending
    normalized.sort(key=lambda x: x["view_count"], reverse=True)

    # Normalize profile
    if profile:
        profile = {
            "username": profile.get("username", ""),
            "display_name": profile.get("display_name", ""),
            "followers": _to_int(profile.get("followers", 0)),
            "following": _to_int(profile.get("following", 0)),
            "total_posts": _to_int(profile.get("total_posts", 0)),
            "bio": profile.get("bio", ""),
        }

    return profile, normalized, None


def _extract_json(text):
    """Extract a JSON object from text that may contain non-JSON content."""
    # Try parsing the whole text first
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # Find JSON block between ```json ... ``` markers
    import re
    json_block = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    if json_block:
        try:
            return json.loads(json_block.group(1))
        except json.JSONDecodeError:
            pass

    # Find the first { ... } block
    brace_start = text.find("{")
    if brace_start == -1:
        return None

    # Find matching closing brace
    depth = 0
    for i in range(brace_start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[brace_start:i + 1])
                except json.JSONDecodeError:
                    return None

    return None


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

    # Handle K/M suffixes
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


def collect_instagram_data(username, api_key=None, max_videos=30,
                           progress_callback=None):
    """High-level function: Create task, wait, parse results.

    This is the main entry point for collecting Instagram data via Manus.

    Args:
        username: Instagram username (without @).
        api_key: Manus API key.
        max_videos: Maximum videos to collect.
        progress_callback: Optional callable(message_str) for UI updates.

    Returns:
        (profile, videos, error): profile dict, list of video dicts, or error.
    """
    api_key = api_key or get_manus_api_key()

    if progress_callback:
        progress_callback("Manusタスクを作成中...")

    task_id, error = create_collection_task(username, api_key, max_videos)
    if error:
        return None, None, error

    if progress_callback:
        progress_callback(f"Manusがデータ収集中... (タスクID: {task_id[:8]}...)")

    def _poll_cb(status, elapsed):
        if progress_callback:
            progress_callback(f"Manus収集中: {status} ({elapsed}秒経過)")

    task_data, error = wait_for_task(task_id, api_key, progress_callback=_poll_cb)
    if error:
        return None, None, error

    if progress_callback:
        progress_callback("収集データを解析中...")

    return parse_collection_result(task_data)
