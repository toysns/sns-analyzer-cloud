"""Report formatting and export utilities."""

import datetime


def format_report_header(account_name, platform, mode_name):
    """Generate a report header with metadata.

    Returns:
        str: Formatted header string.
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""---
**分析対象:** {account_name} ({platform})
**分析モード:** {mode_name}
**分析日時:** {now}
---

"""


def export_report_text(report, account_name, platform, mode_name):
    """Generate a downloadable report text.

    Args:
        report: The analysis report markdown.
        account_name: Name of the analyzed account.
        platform: Platform name (TikTok/Instagram).
        mode_name: Analysis mode name.

    Returns:
        str: Complete report text for download.
    """
    header = format_report_header(account_name, platform, mode_name)
    now = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    return f"""# {account_name} SNS分析レポート
{header}
{report}

---
生成日時: {now}
ツール: SNS Analyzer v2.0
"""


def generate_filename(account_name, platform):
    """Generate a filename for the report download.

    Returns:
        str: Filename like 'toysns_tiktok_analysis_20260210.md'
    """
    now = datetime.datetime.now().strftime("%Y%m%d")
    safe_name = account_name.replace(" ", "_").replace("/", "_")
    return f"{safe_name}_{platform}_analysis_{now}.md"


def prepare_sheets_data(transcripts, account_name):
    """Prepare transcription data for Google Sheets saving.

    Args:
        transcripts: List of dicts with video data and transcripts.
        account_name: Account name for metadata.

    Returns:
        List of dicts ready for sheets.save_videos_to_sheet().
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    rows = []
    for i, t in enumerate(transcripts, 1):
        rows.append({
            "日時": now,
            "順位": i,
            "タイトル": t.get("title", ""),
            "再生回数": t.get("view_count", ""),
            "いいね数": t.get("like_count", ""),
            "コメント数": t.get("comment_count", ""),
            "投稿日時": t.get("upload_date", ""),
            "文字起こし": t.get("transcript", ""),
            "URL": t.get("url", ""),
        })
    return rows
