"""Visual analysis of video keyframes using GPT-4o Vision."""

import base64
import json
import logging
import os
import subprocess
import tempfile

from openai import OpenAI

logger = logging.getLogger(__name__)

VISUAL_ANALYSIS_PROMPT = """あなたはSNS動画のビジュアル分析の専門家です。
TikTok/Instagram動画から等間隔で抽出した{num_frames}枚のキーフレームを分析してください。

以下の観点で詳細に分析し、日本語で記述してください：

## 1. 全体の映像スタイル
- 撮影方法（自撮り/俯瞰/固定カメラ/一人称視点/複数アングル等）
- 映像のクオリティ（照明、画質、色味、ホワイトバランス）
- 全体的なトーン＆マナー（明るい/暗い/ナチュラル/加工強め等）

## 2. 構図・レイアウト
- 被写体の配置（中央/三分割法/余白の使い方）
- 人物が映っている場合：表情、ジェスチャー、カメラとの距離感
- 背景の工夫（生活感/スタジオ/ロケーション）

## 3. テロップ・テキスト情報
- テロップの有無と量
- フォントスタイル（ゴシック/明朝/手書き風/ポップ体等）
- テロップの配置（上部/中央/下部/画面全体）
- 文字サイズ、色、縁取り、背景の有無
- テキストの内容・役割（解説/ツッコミ/感情表現/要約等）

## 4. 編集・エフェクト
- カット割りの頻度（推測）
- トランジション、エフェクトの使用
- 画面分割、ズーム、スローモーション等の演出
- Before/After的な構成の有無

## 5. サムネイル力・冒頭フック分析（1枚目のフレーム = 動画の0秒地点）
**最重要セクション**: TikTokでは最初の0.5秒でスクロールを止められるかが全てを決める。
1枚目のフレームを特に詳細に分析し、以下を必ず含めること：
- スクロール停止力（thumb-stopping power）の10段階評価と理由
- 視覚的なフック要素（目を引く色、表情、テキスト、構図、意外性）
- 情報設計: 0.3秒で「何の動画か」が伝わるか？
- 感情トリガー: 好奇心・共感・驚き・恐怖のどれを狙っているか
- 改善提案: 具体的に何を変えればスクロール停止率が上がるか（3つ以上）

## 6. 競合との差別化要素
- このビジュアルスタイルのユニークさ
- よくあるTikTok動画との違い
- ブランドの一貫性（フレーム間での統一感）

各項目を具体的に記述してください。曖昧な表現は避け、「〇〇というフォントで左上に配置」のように具体的に書いてください。"""


def _determine_frame_count(duration):
    """Determine optimal number of keyframes based on video duration.

    Strategy:
        ~15s:  5 frames (short TikTok)
        ~30s:  8 frames
        ~60s: 12 frames
        ~90s: 15 frames
        2m+:  20 frames (cap — GPT-4o Vision limit consideration)

    Returns:
        int: Number of frames to extract.
    """
    if duration is None or duration <= 0:
        return 5
    if duration <= 15:
        return 5
    if duration <= 30:
        return 8
    if duration <= 60:
        return 12
    if duration <= 90:
        return 15
    return 20  # Cap at 20 to keep Vision API costs reasonable


def _get_video_duration(video_path):
    """Get video duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass
    return None


def _extract_keyframes(video_path, output_dir, num_frames=5):
    """Extract evenly-spaced keyframes from a video.

    Args:
        video_path: Path to the video file.
        output_dir: Directory to save frames.
        num_frames: Number of frames to extract.

    Returns:
        Tuple of (list of frame file paths, error string).
    """
    duration = _get_video_duration(video_path)
    if duration is None or duration < 1:
        # Fallback: extract first frame only
        frame_path = os.path.join(output_dir, "frame_001.jpg")
        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-hide_banner", "-loglevel", "error",
                    "-i", video_path,
                    "-vframes", "1",
                    "-q:v", "2",
                    "-y", frame_path,
                ],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and os.path.exists(frame_path):
                return [frame_path], None
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        return [], "フレーム抽出に失敗しました"

    # Calculate timestamps:
    #   Frame 0: t=0.1s (thumbnail / first impression)
    #   Frame 1..N: evenly spaced from 10% to 90% of duration
    thumbnail_ts = min(0.1, duration * 0.01)  # Very start for thumbnail
    if num_frames == 1:
        timestamps = [thumbnail_ts]
    else:
        body_start = duration * 0.10
        body_end = duration * 0.90
        body_count = num_frames - 1
        if body_count == 1:
            body_timestamps = [(body_start + body_end) / 2]
        else:
            step = (body_end - body_start) / (body_count - 1)
            body_timestamps = [body_start + step * i for i in range(body_count)]
        timestamps = [thumbnail_ts] + body_timestamps

    frame_paths = []
    for i, ts in enumerate(timestamps):
        frame_path = os.path.join(output_dir, f"frame_{i+1:03d}.jpg")
        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner", "-loglevel", "error",
                    "-ss", f"{ts:.2f}",
                    "-i", video_path,
                    "-vframes", "1",
                    "-q:v", "2",
                    "-y", frame_path,
                ],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0 and os.path.exists(frame_path):
                frame_paths.append(frame_path)
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

    if not frame_paths:
        return [], "フレーム抽出に失敗しました"

    return frame_paths, None


def _encode_frame(frame_path):
    """Encode a frame image to base64."""
    with open(frame_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _analyze_frames_with_vision(frame_paths, openai_api_key):
    """Send keyframes to GPT-4o Vision for analysis.

    Args:
        frame_paths: List of image file paths.
        openai_api_key: OpenAI API key.

    Returns:
        Tuple of (analysis_text, error).
    """
    try:
        content = [
            {
                "type": "text",
                "text": VISUAL_ANALYSIS_PROMPT.format(num_frames=len(frame_paths)),
            }
        ]

        for i, path in enumerate(frame_paths):
            b64 = _encode_frame(path)
            position_label = _get_position_label(i, len(frame_paths))
            content.append({
                "type": "text",
                "text": f"【フレーム {i+1}/{len(frame_paths)}: {position_label}】",
            })
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{b64}",
                    "detail": "high",
                },
            })

        client = OpenAI(api_key=openai_api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": content}],
            max_tokens=3000,
            temperature=0.2,
        )

        analysis = response.choices[0].message.content
        if not analysis:
            return None, "映像分析結果が空です"

        return analysis.strip(), None

    except Exception as e:
        error_msg = str(e)
        if "api key" in error_msg.lower():
            return None, "OpenAI APIキーが無効です"
        return None, f"映像分析エラー: {error_msg[:300]}"


def _get_position_label(index, total):
    """Get a descriptive label for frame position."""
    if total == 1:
        return "サムネイル / 冒頭"
    if index == 0:
        return "サムネイル / 冒頭0秒"
    if index == total - 1:
        return "終盤"
    # Remaining frames are spread across the body
    body_index = index - 1
    body_total = total - 2  # Exclude first and last
    if body_total <= 0:
        return "中盤"
    ratio = body_index / body_total if body_total > 0 else 0.5
    if ratio <= 0.3:
        return "序盤"
    if ratio <= 0.6:
        return "中盤"
    return "後半"


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
                "-o", output_path,
                url,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            return False, f"動画ダウンロード失敗: {result.stderr[:200]}"
        if not os.path.exists(output_path):
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
        return False, "動画ダウンロードがタイムアウトしました（120秒）"
    except FileNotFoundError:
        return False, "yt-dlpがインストールされていません"


def analyze_video_visuals(url, openai_api_key, num_frames=5, temp_dir=None):
    """Full visual analysis pipeline: download → extract frames → Vision API.

    Args:
        url: Video URL.
        openai_api_key: OpenAI API key.
        num_frames: Number of keyframes to extract (default 5).
        temp_dir: Temp directory. Defaults to system temp.

    Returns:
        Tuple of (visual_analysis_text, error).
    """
    if temp_dir is None:
        temp_dir = os.path.join(tempfile.gettempdir(), "sns_analyzer_frames")
    os.makedirs(temp_dir, exist_ok=True)

    # Use hash for unique temp naming
    video_hash = str(abs(hash(url)))[:12]
    video_path = os.path.join(temp_dir, f"video_{video_hash}.mp4")
    frames_dir = os.path.join(temp_dir, f"frames_{video_hash}")
    os.makedirs(frames_dir, exist_ok=True)

    try:
        # Step 1: Download video
        success, error = _download_video(url, video_path)
        if not success:
            return None, error

        # Step 2: Determine frame count based on duration
        duration = _get_video_duration(video_path)
        actual_frames = _determine_frame_count(duration) if num_frames == 5 else num_frames
        logger.info(f"Video duration: {duration:.1f}s → extracting {actual_frames} frames")

        # Step 3: Extract keyframes
        frame_paths, error = _extract_keyframes(video_path, frames_dir, actual_frames)
        if error:
            return None, error

        # Step 4: Analyze with Vision API
        analysis, error = _analyze_frames_with_vision(frame_paths, openai_api_key)
        return analysis, error

    finally:
        # Cleanup
        try:
            if os.path.exists(video_path):
                os.remove(video_path)
            if os.path.exists(frames_dir):
                for f in os.listdir(frames_dir):
                    os.remove(os.path.join(frames_dir, f))
                os.rmdir(frames_dir)
        except OSError:
            pass
