"""SNS account analysis engine using Anthropic Claude Sonnet with SKILL.md framework."""

import functools
import logging
import os
from pathlib import Path

from anthropic import Anthropic

logger = logging.getLogger(__name__)

SKILLS_DIR = Path(__file__).parent.parent / "skills"

ANALYSIS_MODES = {
    1: ("成功要因抽出", "なぜこのアカウントがうまくいってるか分析する"),
    2: ("ブラッシュアップ提案", "さらに伸ばすための具体的な改善策を提案する"),
    3: ("コンセプト壁打ち", "方向性の検証、ピボット判断を行う"),
    4: ("競合分析", "同ジャンルの競合との差別化ポイントを分析する"),
    5: ("新規アカウント設計", "ゼロからの立ち上げ戦略を設計する"),
}

MODE_INSTRUCTIONS = {
    1: """分析モード: 成功要因抽出
このアカウントがなぜ成功しているのかを分析してください。
特に以下に注力:
- 需要と供給の一致度
- 変数/定数の使い方の巧みさ
- フォーマット選択の適切さ
- 心理トリガーの活用度
最終的に「再現可能な成功法則」として言語化してください。""",

    2: """分析モード: ブラッシュアップ提案
このアカウントの良い点を活かしつつ、さらに伸ばすための改善策を提案してください。
STEP 6の改善提案を特に充実させ、以下を必ず含めてください:
- 致命的/重要/改良余地の3段階で分類した改善点
- 具体的なアクションプラン（今すぐ/1週間以内/1ヶ月以内）
- 横展開・応用提案""",

    3: """分析モード: コンセプト壁打ち
このアカウントのコンセプト（Who×What×How）が正しい方向を向いているか検証してください。
以下の観点で判断:
- 需要Aは実在するか？市場規模は十分か？
- 変数/定数の設定は適切か？
- ピボットすべき要素はあるか？
- 現在のコンセプトの延長で成長余地はあるか？""",

    4: """分析モード: 競合分析
このアカウントが属するジャンルの競合環境を分析し、差別化ポイントを特定してください。
以下を含めてください:
- 同ジャンルでよく見るフォーマットの整理
- このアカウントの変数化ポイント（差別化要因）
- 競合に対する優位性と劣位性
- 市場ポジショニングの提案""",

    5: """分析モード: 新規アカウント設計
提供されたデータを参考に、新規アカウントの立ち上げ戦略を設計してください。
以下を含めてください:
- 推奨コンセプト（Who×What×How）
- 需要Aの定義
- 変数/定数の設計
- 推奨フォーマット
- 初期コンテンツ戦略（最初の30投稿の方向性）
- マネタイズ設計""",
}


@functools.lru_cache(maxsize=1)
def _load_skill_files():
    """Load SKILL.md and all reference files (cached at module level).

    Returns:
        str: Combined content of all skill files.
    """
    parts = []

    skill_path = SKILLS_DIR / "SKILL.md"
    if skill_path.exists():
        parts.append(skill_path.read_text(encoding="utf-8"))

    refs_dir = SKILLS_DIR / "references"
    if refs_dir.exists():
        for ref_file in sorted(refs_dir.glob("*.md")):
            content = ref_file.read_text(encoding="utf-8")
            parts.append(f"\n---\n## 参照: {ref_file.stem}\n\n{content}")

    return "\n".join(parts)


def _build_system_prompt(mode):
    """Build the system prompt with SKILL framework and mode instructions.

    Args:
        mode: Analysis mode number (1-5).

    Returns:
        str: System prompt.
    """
    skill_content = _load_skill_files()
    mode_instruction = MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS[2])

    return f"""あなたはSNSアカウント分析の専門家です。以下の分析フレームワークに厳密に従って分析を行ってください。

{mode_instruction}

---

{skill_content}

---

**重要な注意事項:**
- 必ず上記の6ステップ分析フローに沿って分析を行うこと
- 出力フォーマットに従ってマークダウン形式でレポートを作成すること
- 具体的かつ実用的な分析を心がけ、抽象的な表現を避けること
- 参照ファイル（フォーマット辞書、心理トリガー、失敗パターン集）の知見を積極的に活用すること
- 分析対象の投稿内容（文字起こし）がある場合は、実際の内容に基づいて分析すること
- 映像分析データ（キーフレーム解析）がある場合は、映像面の分析を必ず組み込むこと（撮影スタイル、テロップ、構図、編集手法、サムネイル力など）
- 文字起こし（音声情報）と映像分析（視覚情報）の両方を統合し、総合的な分析を行うこと
- コメント分析データがある場合は、オーディエンスの質・感情・マネタイズ可能性の評価に活用すること
- 時系列トレンドデータがある場合は、成長トレンド・投稿頻度・曜日別パフォーマンス・バイラル傾向の分析に活用すること
- 競合比較データがある場合は、差別化ポイント・優位性・劣位性を具体的に分析し、ポジショニング提案を行うこと
- 各ステップの分析を省略せず、十分な深さと具体性を持って記述すること
- 【投稿横断パターン分析】複数の投稿データがある場合は、必ず「伸びている投稿の共通パターン」と「伸びていない投稿の共通パターン」を比較・対比して抽出すること。共通する要素（テーマ、構成、フック、長さ、テロップ、心理トリガー等）を具体的に列挙し、「このアカウントで再現性の高い勝ちパターン」と「避けるべきパターン」を言語化すること"""


def _build_user_prompt(account_data, transcripts):
    """Build the user prompt with account data and transcripts.

    Args:
        account_data: Dict with account info (name, platform, followers, etc.).
        transcripts: List of dicts with video data and transcripts.

    Returns:
        str: User prompt.
    """
    parts = ["以下のアカウントを分析してください。\n"]

    # Account basic info
    parts.append("## アカウント基本情報")
    parts.append(f"- プラットフォーム: {account_data.get('platform', '不明')}")
    parts.append(f"- アカウント名: {account_data.get('name', '不明')}")
    if account_data.get("followers"):
        parts.append(f"- フォロワー数: {account_data['followers']}")
    if account_data.get("total_posts"):
        parts.append(f"- 総投稿数: {account_data['total_posts']}")
    if account_data.get("profile_text"):
        parts.append(f"- プロフィール文: {account_data['profile_text']}")
    if account_data.get("external_link"):
        parts.append(f"- 外部リンク: {account_data['external_link']}")
    parts.append("")

    # Video data with transcripts (sorted by views desc for cross-post comparison)
    if transcripts:
        sorted_transcripts = sorted(
            transcripts,
            key=lambda x: x.get("view_count", 0) or 0,
            reverse=True,
        )
        parts.append("## 投稿データ（再生数順）\n")
        total = len(sorted_transcripts)
        for i, t in enumerate(sorted_transcripts, 1):
            # Label top/bottom posts for easier cross-post pattern detection
            if total >= 4:
                if i <= max(1, total // 3):
                    rank_label = " 🔥上位"
                elif i > total - max(1, total // 3):
                    rank_label = " ⬇下位"
                else:
                    rank_label = " ➡中位"
            else:
                rank_label = ""
            parts.append(f"### 投稿{i}{rank_label}: {t.get('title', '無題')}")
            if t.get("view_count"):
                parts.append(f"- 再生回数: {t['view_count']:,}")
            if t.get("like_count"):
                parts.append(f"- いいね数: {t['like_count']:,}")
            if t.get("comment_count"):
                parts.append(f"- コメント数: {t['comment_count']:,}")
            if t.get("upload_date"):
                parts.append(f"- 投稿日: {t['upload_date']}")
            if t.get("url"):
                parts.append(f"- URL: {t['url']}")
            if t.get("transcript"):
                parts.append(f"\n**文字起こし:**\n{t['transcript']}")
            if t.get("visual_analysis"):
                parts.append(f"\n**映像分析（キーフレーム解析）:**\n{t['visual_analysis']}")
            if t.get("comment_analysis"):
                parts.append(f"\n**コメント分析:**\n{t['comment_analysis']}")
            parts.append("")

    # Trend analysis
    if account_data.get("trend_analysis"):
        parts.append(f"## 時系列トレンド分析\n{account_data['trend_analysis']}\n")

    # Competitor comparison
    if account_data.get("competitor_comparison"):
        parts.append(f"## 競合アカウント比較\n{account_data['competitor_comparison']}\n")

    # Additional context
    if account_data.get("supplement"):
        parts.append(f"## 補足情報\n{account_data['supplement']}\n")

    # Top/bottom posts for manual analysis
    if account_data.get("top_posts"):
        parts.append("## 伸びている投稿（上位）")
        parts.append(account_data["top_posts"])
        parts.append("")
    if account_data.get("bottom_posts"):
        parts.append("## 伸びていない投稿（下位）")
        parts.append(account_data["bottom_posts"])
        parts.append("")

    return "\n".join(parts)


def run_analysis(account_data, transcripts, mode, openai_api_key):
    """Run SNS account analysis using Anthropic Claude Sonnet.

    Args:
        account_data: Dict with account info.
        transcripts: List of dicts with video data and transcripts.
        mode: Analysis mode number (1-5).
        openai_api_key: OpenAI API key (kept for Whisper; Anthropic key from env).

    Returns:
        Tuple of (report: str | None, error: str | None).
    """
    try:
        anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not anthropic_api_key:
            return None, "ANTHROPIC_API_KEY が設定されていません"

        system_prompt = _build_system_prompt(mode)
        user_prompt = _build_user_prompt(account_data, transcripts)

        client = Anthropic(api_key=anthropic_api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=16000,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
        )

        report = response.content[0].text
        if not report:
            return None, "分析レポートが空です"

        return report, None

    except Exception as e:
        error_msg = str(e)
        if "authentication" in error_msg.lower() or "api key" in error_msg.lower():
            return None, "Anthropic APIキーが無効です"
        if "rate" in error_msg.lower():
            return None, "APIレート制限に達しました。少し待ってから再試行してください。"
        return None, f"分析エラー: {error_msg[:300]}"
