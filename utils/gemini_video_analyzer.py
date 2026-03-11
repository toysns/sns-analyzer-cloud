"""Video analysis using Google Gemini API — unified transcription + visual analysis."""

import logging
import os
import subprocess
import tempfile
import time

logger = logging.getLogger(__name__)


def _get_genai():
    """Lazy import google-genai to avoid startup crash if not installed."""
    from google import genai
    from google.genai import types
    return genai, types

GEMINI_VIDEO_PROMPT = """あなたはSNS動画分析の専門家です。この動画を詳細に分析し、以下の2つのセクションで日本語で回答してください。

---

## セクション1: 文字起こし（transcript）

動画内の音声を正確に文字起こししてください。
- 話している内容を忠実にテキスト化すること
- BGMのみで音声がない場合は「（音声なし・BGMのみ）」と記載
- テロップ/画面上のテキストも【テロップ: 〇〇】の形式で含めること
- 話者が複数いる場合は区別すること

---

## セクション2: 映像分析（visual_analysis）

以下の観点で詳細に分析してください：

### 1. 全体の映像スタイル
- 撮影方法（自撮り/俯瞰/固定カメラ/一人称視点/複数アングル等）
- 映像のクオリティ（照明、画質、色味、ホワイトバランス）
- 全体的なトーン＆マナー（明るい/暗い/ナチュラル/加工強め等）

### 2. 構図・レイアウト
- 被写体の配置（中央/三分割法/余白の使い方）
- 人物が映っている場合：表情、ジェスチャー、カメラとの距離感
- 背景の工夫（生活感/スタジオ/ロケーション）

### 3. テロップ・テキスト情報
- テロップの有無と量、出現タイミング
- フォントスタイル（ゴシック/明朝/手書き風/ポップ体等）
- テロップの配置、文字サイズ、色、縁取り
- テキストの内容・役割（解説/ツッコミ/感情表現/要約等）

### 4. 編集・演出技法
- カット割りの頻度と効果
- トランジション、エフェクトの使用
- BGM・効果音の使い方と感情への影響
- ズーム、スローモーション等の演出
- テンポ感（早い/ゆったり/緩急あり）

### 5. 動画構成・ストーリーライン
- 冒頭のフック（最初の1-2秒で何をしているか）
- 起承転結やストーリー展開の有無
- 視聴維持のための工夫（テンポ変化、情報の出し方）
- 終盤のCTA（フォロー誘導、次回予告等）

### 6. サムネイル力・冒頭フック分析
**最重要**: TikTokでは最初の0.5秒でスクロールを止められるかが全てを決める。
- スクロール停止力（thumb-stopping power）の10段階評価と理由
- 視覚的なフック要素（目を引く色、表情、テキスト、構図、意外性）
- 情報設計: 0.3秒で「何の動画か」が伝わるか？
- 感情トリガー: 好奇心・共感・驚き・恐怖のどれを狙っているか
- 改善提案: 具体的に何を変えればスクロール停止率が上がるか（3つ以上）

### 7. 競合との差別化要素
- このビジュアルスタイルのユニークさ
- よくあるTikTok動画との違い

---

**出力フォーマット**: 必ず以下の区切りを使って2セクションを分けてください：

===TRANSCRIPT_START===
（文字起こし内容をここに記述）
===TRANSCRIPT_END===

===VISUAL_ANALYSIS_START===
（映像分析内容をここに記述）
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
        genai, types = _get_genai()
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
