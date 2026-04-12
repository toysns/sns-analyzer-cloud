"""Video analysis using Google Gemini API — unified transcription + visual analysis."""

import logging
import os
import subprocess
import tempfile
import time

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

GEMINI_VIDEO_PROMPT = """この動画の内容を正確に記録してください。分析や評価は不要です。見たまま・聞こえたままを報告してください。

---

## セクション1: 文字起こし（transcript）

- 話している内容を忠実にテキスト化
- BGMのみで音声がない場合は「（音声なし・BGMのみ）」
- 画面上のテロップも【テロップ: 〇〇】の形式で含める
- 話者が複数いる場合は区別する

## セクション2: 映像の事実描写（visual_description）

判断や評価はせず、見えたものをそのまま書いてください：

- **映っているもの**: 人物（人数・性別・年齢層・服装）、場所、物、食べ物など
- **撮影方法**: 自撮り/固定/俯瞰/一人称 など
- **画面の見た目**: 明るさ、色味、背景
- **テロップ**: 文字の内容、フォントの見た目、色、配置、出現タイミング
- **編集**: カット回数、BGM/効果音の有無、テンポ（早い/ゆっくり）
- **時系列の流れ**: 冒頭→中盤→終盤で何が起きているかを順に記述
- **冒頭1-2秒**: 最初に画面に映るもの・聞こえるものを具体的に

---

**出力フォーマット**: 必ず以下の区切りを使って2セクションを分けてください：

===TRANSCRIPT_START===
（文字起こし内容）
===TRANSCRIPT_END===

===VISUAL_ANALYSIS_START===
（映像の事実描写）
===VISUAL_ANALYSIS_END==="""


def _download_video(url, output_path):
    """Download video using yt-dlp.

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
            error_lines = [
                l.strip()
                for l in result.stderr.split("\n")
                if l.strip() and "ERROR" in l.upper()
            ]
            error_msg = (
                error_lines[-1][:200] if error_lines else result.stderr[-200:].strip()
            )
            return False, f"動画ダウンロード失敗: {error_msg}"
        if not os.path.exists(output_path):
            # yt-dlp may add an extension
            for ext in [".mp4", ".webm", ".mkv"]:
                if os.path.exists(output_path + ext):
                    os.rename(output_path + ext, output_path)
                    break
            else:
                base_dir = os.path.dirname(output_path)
                base_name = os.path.basename(output_path)
                for f in os.listdir(base_dir):
                    if f.startswith(base_name.split(".")[0]):
                        os.rename(os.path.join(base_dir, f), output_path)
                        break
        if not os.path.exists(output_path):
            return False, "動画ファイルが見つかりません"
        return True, ""
    except subprocess.TimeoutExpired:
        return False, "動画ダウンロードがタイムアウトしました（180秒）"
    except FileNotFoundError:
        return False, "yt-dlpがインストールされていません"


def _parse_gemini_response(text):
    """Parse Gemini response into transcript and visual analysis sections.

    Args:
        text: Raw response text from Gemini.

    Returns:
        Tuple of (transcript: str, visual_analysis: str).
    """
    transcript = ""
    visual_analysis = ""

    # Extract transcript
    if "===TRANSCRIPT_START===" in text and "===TRANSCRIPT_END===" in text:
        start = text.index("===TRANSCRIPT_START===") + len("===TRANSCRIPT_START===")
        end = text.index("===TRANSCRIPT_END===")
        transcript = text[start:end].strip()

    # Extract visual analysis
    if "===VISUAL_ANALYSIS_START===" in text and "===VISUAL_ANALYSIS_END===" in text:
        start = text.index("===VISUAL_ANALYSIS_START===") + len(
            "===VISUAL_ANALYSIS_START==="
        )
        end = text.index("===VISUAL_ANALYSIS_END===")
        visual_analysis = text[start:end].strip()

    # Fallback: if markers not found, treat entire response as combined output
    if not transcript and not visual_analysis:
        transcript = "(構造化パースに失敗 — 全文を文字起こしとして使用)"
        visual_analysis = text.strip()

    return transcript, visual_analysis


def _wait_for_file_active(client, file_ref, timeout=120):
    """Wait for an uploaded file to become ACTIVE (processed by Gemini).

    Args:
        client: genai.Client instance.
        file_ref: File reference returned from upload.
        timeout: Maximum seconds to wait.

    Returns:
        Tuple of (file_ref, error).
    """
    start = time.time()
    while time.time() - start < timeout:
        file_info = client.files.get(name=file_ref.name)
        if file_info.state == "ACTIVE":
            return file_info, None
        if file_info.state == "FAILED":
            return None, "Geminiでの動画処理に失敗しました"
        time.sleep(2)
    return None, f"動画処理がタイムアウトしました（{timeout}秒）"


def analyze_video_with_gemini(url, gemini_api_key, temp_dir=None):
    """Full Gemini video analysis pipeline: download → upload → unified analysis.

    Uses Gemini's native video understanding to perform transcription and
    visual analysis in a single API call, replacing the separate Whisper +
    GPT-4o Vision pipeline.

    Args:
        url: Video URL (TikTok, Instagram, etc.).
        gemini_api_key: Google AI Studio API key.
        temp_dir: Temp directory. Defaults to system temp.

    Returns:
        Tuple of (transcript: str | None, visual_analysis: str | None, error: str | None).
    """
    if temp_dir is None:
        temp_dir = os.path.join(tempfile.gettempdir(), "sns_analyzer_gemini")
    os.makedirs(temp_dir, exist_ok=True)

    video_hash = str(abs(hash(url)))[:12]
    video_path = os.path.join(temp_dir, f"video_{video_hash}.mp4")

    uploaded_file = None
    client = None

    try:
        # Step 1: Download video
        success, error = _download_video(url, video_path)
        if not success:
            return None, None, error

        # Step 2: Upload to Gemini File API
        client = genai.Client(api_key=gemini_api_key)
        try:
            uploaded_file = client.files.upload(
                file=video_path,
                config=types.UploadFileConfig(mime_type="video/mp4"),
            )
        except Exception as e:
            return None, None, f"Geminiへの動画アップロード失敗: {str(e)[:300]}"

        # Step 3: Wait for file processing
        file_ref, error = _wait_for_file_active(client, uploaded_file)
        if error:
            return None, None, error

        # Step 4: Analyze with Gemini
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=[GEMINI_VIDEO_PROMPT, file_ref],
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=8000,
                ),
            )
        except Exception as e:
            error_msg = str(e)
            if "api key" in error_msg.lower() or "api_key" in error_msg.lower():
                return None, None, "Gemini APIキーが無効です"
            return None, None, f"Gemini分析エラー: {error_msg[:300]}"

        if not response.text:
            return None, None, "Geminiからの応答が空です"

        # Step 5: Parse response
        transcript, visual_analysis = _parse_gemini_response(response.text)
        return transcript, visual_analysis, None

    finally:
        # Cleanup local file
        try:
            if os.path.exists(video_path):
                os.remove(video_path)
        except OSError:
            pass
        # Cleanup uploaded file from Gemini
        if uploaded_file and client:
            try:
                client.files.delete(name=uploaded_file.name)
            except Exception:
                pass
