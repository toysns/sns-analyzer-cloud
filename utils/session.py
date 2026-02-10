"""Session state management for the SNS Analyzer app."""

import streamlit as st

DEFAULTS = {
    # Common
    "platform": "",
    "account_name": "",
    "account_url": "",
    # TikTok metadata
    "tiktok_profile": None,
    "tiktok_videos": None,
    "tiktok_df": None,
    # Video selection
    "selected_indices": [],
    # Transcription
    "transcription_results": None,
    # Analysis
    "analysis_report": None,
    # Instagram manual input
    "instagram_profile_manual": {},
    "instagram_urls": [],
    # Manual analysis tab
    "manual_account_info": {},
    "manual_top_posts": "",
    "manual_bottom_posts": "",
    # Sheets
    "sheets_saved": False,
}


def init_session_state():
    """Initialize all session state keys with defaults."""
    for key, default in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = default


def clear_analysis_state():
    """Reset all analysis-related state for a new analysis."""
    keys_to_reset = [
        "platform",
        "account_name",
        "account_url",
        "tiktok_profile",
        "tiktok_videos",
        "tiktok_df",
        "selected_indices",
        "transcription_results",
        "analysis_report",
        "instagram_profile_manual",
        "instagram_urls",
        "sheets_saved",
    ]
    for key in keys_to_reset:
        st.session_state[key] = DEFAULTS.get(key)
