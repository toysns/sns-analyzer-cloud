"""Extract account metadata from screenshots using OpenAI GPT-4o Vision."""

import base64
import json
import logging

from openai import OpenAI

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """この画像はSNSアカウントのプロフィール画面のスクリーンショットです。
以下の情報を画像から読み取り、JSON形式で返してください。

読み取れない項目は null としてください。数値はカンマなしの整数で返してください（例: 12300）。

```json
{
  "platform": "TikTok または Instagram または その他",
  "account_name": "アカウント名（@なし）",
  "display_name": "表示名",
  "followers": フォロワー数（整数）,
  "following": フォロー数（整数）,
  "total_posts": 投稿数（整数）,
  "total_likes": いいね数の合計（整数、TikTokの場合のみ）,
  "profile_text": "プロフィール文（全文）",
  "external_link": "外部リンク（あれば）"
}
```

重要:
- 「1.2万」は 12000、「5.3K」は 5300、「1.5M」は 1500000 のように数値に変換してください
- JSON以外のテキストは出力しないでください
- プロフィール文は改行を含む全文をそのまま記載してください"""


def extract_metadata_from_screenshot(image_bytes, openai_api_key):
    """Extract account metadata from a screenshot using GPT-4o Vision.

    Args:
        image_bytes: Raw bytes of the uploaded image.
        openai_api_key: OpenAI API key.

    Returns:
        Tuple of (metadata_dict, error_string).
        metadata_dict is None on failure.
    """
    try:
        if not openai_api_key:
            return None, "OpenAI APIキーが設定されていません"

        # Encode image to base64
        b64_image = base64.b64encode(image_bytes).decode("utf-8")

        # Detect image type from first bytes
        if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            media_type = "image/png"
        elif image_bytes[:2] == b'\xff\xd8':
            media_type = "image/jpeg"
        elif image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
            media_type = "image/webp"
        else:
            media_type = "image/png"  # fallback

        client = OpenAI(api_key=openai_api_key)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": EXTRACTION_PROMPT},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media_type};base64,{b64_image}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
            max_tokens=1000,
            temperature=0.1,
        )

        raw_text = response.choices[0].message.content.strip()

        # Extract JSON from response (handle markdown code blocks)
        if "```json" in raw_text:
            raw_text = raw_text.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_text:
            raw_text = raw_text.split("```")[1].split("```")[0].strip()

        metadata = json.loads(raw_text)

        # Normalize numeric fields
        for field in ["followers", "following", "total_posts", "total_likes"]:
            val = metadata.get(field)
            if val is not None:
                try:
                    metadata[field] = int(val)
                except (ValueError, TypeError):
                    metadata[field] = None

        return metadata, None

    except json.JSONDecodeError as e:
        logger.error("Failed to parse Vision API response as JSON: %s", e)
        return None, f"読み取り結果のJSON解析に失敗しました: {raw_text[:200]}"
    except Exception as e:
        error_msg = str(e)
        if "api key" in error_msg.lower():
            return None, "OpenAI APIキーが無効です"
        return None, f"スクリーンショット解析エラー: {error_msg[:300]}"
