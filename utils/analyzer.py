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

    6: """分析モード: アカウント成長戦略（チャット分析用）

このアカウントを「もっと伸ばすにはどうすべきか」を分析します。
**マネタイズの話は求められない限りしないでください。** フォロワー増加・再生数向上・エンゲージメント改善に集中。

## 最初の確認 — 補足情報の妥当性チェック

「## 補足情報」セクションから、以下4点を抽出してください:
1. 運用目的（集客/採用/ブランディング/販売など）
2. ターゲット（年齢・職業・悩み・ライフスタイル）
3. 競合アカウント（ユーザーが意識している他アカウント）
4. 特に聞きたいこと・悩み

### 不足時の対応
補足情報が**1つでも不足**している場合、分析を始めず、不足項目を質問してください。推測で分析しないこと。

### 競合アカウントの妥当性判定（重要）
ユーザーが挙げた競合が**実際に適切な競合か**を、ユーザーのターゲット設定と照らし合わせて判定してください:
- その競合アカウントは、同じターゲット（ユーザーが届けたい相手）を対象にしているか？
- フォロワー規模・投稿ジャンル・提供価値が、このアカウントと比較対象として妥当か？
- 「その競合は参考にならない」「むしろこちらのアカウントを参考にすべき」という場合は明確に指摘してください

**判定結果の伝え方:**
- 「競合Xは適切です。理由は〜」または
- 「競合Xは不適切かもしれません。理由: 〜 代わりに〇〇や△△の方が参考になる可能性があります」

## 分析の流れ

### STEP 1: 理想のアカウント像の定義
- **需要A**: ターゲットが日常的にSNSで消費している内容、悩み、関心事を具体的に言語化
- **提供価値**: ターゲットに対して競合と比べて何を提供すべきか
- **差別化ポイント**: 同ターゲットを狙う競合と比べて、どこで勝負すべきか

### STEP 2: 現状分析
- 伸びている投稿と伸びていない投稿の**具体的な差分**（冒頭フック・テロップ・構成・映像表現）
- コメント・いいね比率から推定されるオーディエンスの質
- 現在の投稿パターン（フォーマット・テーマ・頻度）

### STEP 3: 理想と現状のギャップ診断
STEP 1の理想像と STEP 2の現状を照らして:
- ターゲットが求めているものと実際の投稿のズレ
- 競合と比べて劣っている点・真似すべき点
- このままでは伸びない致命的な問題

### STEP 4: 具体的な改善提案

#### 4-1. 台本の具体書き換え（必須・最重要）
伸び悩んでいる投稿を **2-3本ピックアップ** して:
- **Before**: 現在の台本（冒頭3秒＋本編抜粋）を引用
- **問題点**: なぜ刺さらないか、心理学的・構造的な理由
- **After**: 書き直した台本（完成品、そのまま撮影可能なレベル）
- **改善の根拠**: フォーマット辞書・心理トリガーを引用して理由説明

#### 4-2. 映像表現の具体改善
- **テロップ**: 現在のフォント・色・配置 → 具体改善案（例: ゴシック中央 → 手書き風下部、白縁取り+影）
- **冒頭1-2秒**: 現在の映像 → 映すべきショットの具体提案
- **編集テンポ**: カット頻度・BGM・効果音の改善案
- **サムネイル力**: 0.3秒で何の動画か伝わるかの評価と改善

#### 4-3. フォーマット提案
フォーマット辞書の具体フォーマット名（A-1, A-3, B など）で提案:
- なぜこのアカウントに合うか
- そのフォーマットで作る台本例を1本完成品として提示

#### 4-4. 次の10投稿のテーマ案
ターゲットの悩みにマッチした具体的なタイトル＋冒頭フックを10本分

## 出力ルール
- **抽象禁止**: 「〇〇を意識して」ではダメ、「〇〇を△△に変える。理由は〜」
- **根拠必須**: 改善案に必ず根拠（データ・事例・心理学・フォーマット辞書）を併記
- **Before/After**: 改善提案は「現状→問題→改善案→理由」の4点セット
- **台本は完成品**: そのまま撮影できる文章レベル
- **引用重視**: 伸びている投稿・競合の具体要素を引用して説明
- **情報不足時**: 勝手に推測せず、まず質問""",
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
