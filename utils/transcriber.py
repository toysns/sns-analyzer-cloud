"""Video transcription pipeline: download → audio extraction → OpenAI Whisper API."""

import logging
import os
import re
import subprocess
import tempfile

import requests
from openai import OpenAI

logger = logging.getLogger(__name__)

MAX_AUDIO_SIZE_BYTES = 25 * 1024 * 1024  # 25MB Whisper API limit


def _extract_video_id(url):
    """Extract a short ID from a video URL for temp file naming."""
    match = re.search(r"video/(\d+)", url)
    if match:
        return match.group(1)
    match = re.search(r"reel/([A-Za-z0-9_-]+)", url)
    if match:
        return match.group(1)
    # Fallback: hash of URL
    return str(abs(hash(url)))[:12]


def _download_video_direct(video_url, output_path):
    """Download video directly via HTTP from a CDN URL.

    Returns:
        Tuple of (success: bool, error_message: str).
    """
    try:
        resp = requests.get(video_url, timeout=120, stream=True)
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
                f.write(chunk)
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return True, ""
        return False, "ダウンロードしたファイルが空です"
    except requests.exceptions.RequestException as e:
        return False, f"直接ダウンロード失敗: {str(e)[:200]}"


def _download_video(url, output_path, video_url=None):
    """Download video using yt-dlp, with direct HTTP fallback.

    Args:
        url: Video page URL (for yt-dlp).
        output_path: Path to save the video.
        video_url: Optional direct video CDN URL for HTTP download fallback.

    Returns:
        Tuple of (success: bool, error_message: str).
    """
    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--quiet",
                "--no-warnings",
                "--no-check-certificates",
                "--retries", "3",
                "--fragment-retries", "3",
                "-f", "best[ext=mp4]/best",
                "-o", output_path,
                url,
            ],
            capture_output=True,
            text=True,
            timeout=180,
        )
        if result.returncode != 0:
            error_lines = [l.strip() for l in result.stderr.split('\n') if l.strip() and 'ERROR' in l.upper()]
            ytdlp_error = error_lines[-1][:200] if error_lines else result.stderr[-200:].strip()
            # Try direct download fallback if video_url is available
            if video_url:
                logger.info("yt-dlp failed, trying direct download: %s", video_url[:100])
                return _download_video_direct(video_url, output_path)
            return False, f"動画ダウンロード失敗: {ytdlp_error}"
        if not os.path.exists(output_path):
            # yt-dlp may add an extension
            for ext in [".mp4", ".webm", ".mkv"]:
                if os.path.exists(output_path + ext):
                    os.rename(output_path + ext, output_path)
                    break
            else:
                # Check for any file with the base name
                base_dir = os.path.dirname(output_path)
                base_name = os.path.basename(output_path)
                for f in os.listdir(base_dir):
                    if f.startswith(base_name.split(".")[0]):
                        os.rename(os.path.join(base_dir, f), output_path)
                        break
        if not os.path.exists(output_path):
            if video_url:
                return _download_video_direct(video_url, output_path)
            return False, "動画ファイルが見つかりません"
        return True, ""
    except subprocess.TimeoutExpired:
        if video_url:
            return _download_video_direct(video_url, output_path)
        return False, "動画ダウンロードがタイムアウトしました（120秒）"
    except FileNotFoundError:
        if video_url:
            return _download_video_direct(video_url, output_path)
        return False, "yt-dlpがインストールされていません"


def _extract_audio(video_path, audio_path):
    """Extract audio from video using ffmpeg.

    Returns:
        Tuple of (success: bool, error_message: str).
    """
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel", "error",
                "-i", video_path,
                "-vn",
                "-acodec", "libmp3lame",
                "-b:a", "64k",
                "-y",
                audio_path,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            # stderrから実際のエラー行だけ抽出
            error_lines = [l.strip() for l in result.stderr.split('\n') if l.strip()]
            error_msg = error_lines[-1][:200] if error_lines else "不明なエラー"
            return False, f"音声抽出失敗: {error_msg}"
        if not os.path.exists(audio_path):
            return False, "音声ファイルが生成されませんでした"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "音声抽出がタイムアウトしました"
    except FileNotFoundError:
        return False, "ffmpegがインストールされていません"


def _transcribe_audio_openai(audio_path, api_key, language="ja"):
    """Transcribe audio using OpenAI Whisper API.

    Args:
        audio_path: Path to the audio file.
        api_key: OpenAI API key.
        language: Language code for Whisper (e.g. "ja", "en", "ko", "zh").
            Use None or "auto" for auto-detection.

    Returns:
        Tuple of (transcript: str | None, error: str | None).
    """
    file_size = os.path.getsize(audio_path)
    if file_size > MAX_AUDIO_SIZE_BYTES:
        return None, f"音声ファイルが25MBを超えています（{file_size / 1024 / 1024:.1f}MB）"

    if file_size == 0:
        return None, "音声ファイルが空です"

    try:
        client = OpenAI(api_key=api_key)
        with open(audio_path, "rb") as audio_file:
            whisper_kwargs = {
                "model": "whisper-1",
                "file": audio_file,
                "response_format": "text",
            }
            if language and language != "auto":
                whisper_kwargs["language"] = language
            response = client.audio.transcriptions.create(**whisper_kwargs)

        transcript = response.strip() if isinstance(response, str) else str(response).strip()
        if not transcript:
            return None, "文字起こし結果が空です（音声がない可能性があります）"
        return transcript, None

    except Exception as e:
        error_msg = str(e)
        if "authentication" in error_msg.lower() or "api key" in error_msg.lower():
            return None, "OpenAI APIキーが無効です"
        if "rate" in error_msg.lower():
            return None, "OpenAI APIのレート制限に達しました。少し待ってから再試行してください。"
        return None, f"文字起こしエラー: {error_msg[:200]}"


def transcribe_video_url(url, openai_api_key, temp_dir=None, language="ja",
                         video_url=None):
    """Full transcription pipeline: download → extract audio → transcribe.

    Args:
        url: Video URL (TikTok or Instagram).
        openai_api_key: OpenAI API key.
        temp_dir: Directory for temporary files. Defaults to system temp.
        language: Language code for Whisper ("ja", "en", "ko", "zh", "auto").
        video_url: Optional direct video CDN URL for download fallback.

    Returns:
        Tuple of (transcript: str | None, error: str | None).
    """
    if temp_dir is None:
        temp_dir = os.path.join(tempfile.gettempdir(), "sns_analyzer")
    os.makedirs(temp_dir, exist_ok=True)

    video_id = _extract_video_id(url)
    video_path = os.path.join(temp_dir, f"video_{video_id}.mp4")
    audio_path = os.path.join(temp_dir, f"audio_{video_id}.mp3")

    try:
        # Step 1: Download video
        success, error = _download_video(url, video_path, video_url=video_url)
        if not success:
            return None, error

        # Step 2: Extract audio
        success, error = _extract_audio(video_path, audio_path)
        if not success:
            return None, error

        # Step 3: Transcribe via OpenAI API
        transcript, error = _transcribe_audio_openai(audio_path, openai_api_key, language)
        return transcript, error

    finally:
        # Cleanup temp files
        for path in [video_path, audio_path]:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass
