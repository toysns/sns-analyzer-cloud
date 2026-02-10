"""Google Sheets integration for saving analysis data."""

import json
import logging
import os

import gspread
from oauth2client.service_account import ServiceAccountCredentials

logger = logging.getLogger(__name__)

SCOPES = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]

DEFAULT_SPREADSHEET = "TikTok分析データベース"

HEADERS = ["日時", "順位", "タイトル", "再生回数", "いいね数", "コメント数", "投稿日時", "文字起こし", "URL"]


def get_sheets_client(creds_source=None):
    """Create and return a gspread client.

    Args:
        creds_source: Either a dict of credentials, a JSON string, or None.
            If None, reads from GOOGLE_CREDENTIALS env var.

    Returns:
        gspread.Client or None if authentication fails.
    """
    try:
        if creds_source is None:
            creds_raw = os.environ.get("GOOGLE_CREDENTIALS")
            if not creds_raw:
                logger.error("GOOGLE_CREDENTIALS environment variable not set")
                return None
            creds_dict = json.loads(creds_raw)
        elif isinstance(creds_source, str):
            creds_dict = json.loads(creds_source)
        else:
            creds_dict = dict(creds_source)

        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPES)
        client = gspread.authorize(creds)
        return client
    except json.JSONDecodeError as e:
        logger.error("Failed to parse Google credentials JSON: %s", e)
        return None
    except Exception as e:
        logger.error("Google Sheets authentication failed: %s", e)
        return None


def save_videos_to_sheet(client, sheet_name, data, spreadsheet_name=None):
    """Save video analysis data to a Google Sheets worksheet.

    Args:
        client: Authenticated gspread client.
        sheet_name: Name for the worksheet (e.g., 'toysns' or 'instagram_username').
        data: List of dicts with keys matching HEADERS.
        spreadsheet_name: Name of the spreadsheet. Defaults to DEFAULT_SPREADSHEET.

    Returns:
        Tuple of (success: bool, message: str).
    """
    if spreadsheet_name is None:
        spreadsheet_name = os.environ.get("SPREADSHEET_NAME", DEFAULT_SPREADSHEET)

    try:
        spreadsheet = client.open(spreadsheet_name)
    except gspread.exceptions.SpreadsheetNotFound:
        return False, f"スプレッドシート '{spreadsheet_name}' が見つかりません。サービスアカウントに共有されているか確認してください。"
    except gspread.exceptions.APIError as e:
        return False, f"Google Sheets APIエラー: {e}"

    try:
        # Delete existing worksheet if it exists, then create new
        try:
            existing = spreadsheet.worksheet(sheet_name)
            spreadsheet.del_worksheet(existing)
        except gspread.exceptions.WorksheetNotFound:
            pass

        worksheet = spreadsheet.add_worksheet(title=sheet_name, rows=len(data) + 1, cols=len(HEADERS))
        worksheet.update("A1", [HEADERS])

        if data:
            rows = []
            for item in data:
                row = [
                    item.get("日時", ""),
                    item.get("順位", ""),
                    item.get("タイトル", ""),
                    item.get("再生回数", ""),
                    item.get("いいね数", ""),
                    item.get("コメント数", ""),
                    item.get("投稿日時", ""),
                    item.get("文字起こし", ""),
                    item.get("URL", ""),
                ]
                rows.append(row)
            worksheet.update(f"A2:I{len(rows) + 1}", rows)

        url = spreadsheet.url
        return True, url

    except gspread.exceptions.APIError as e:
        return False, f"シート保存エラー: {e}"
    except Exception as e:
        return False, f"予期しないエラー: {e}"
