"""Invite-code authentication for SNS Analyzer."""

import os

import streamlit as st


def check_authentication():
    """Check if the user is authenticated. Show login UI if not.

    Call this AFTER st.set_page_config().

    Returns:
        True if authenticated or auth is disabled (no INVITE_CODES set).
    """
    if st.session_state.get("authenticated"):
        return True

    codes_raw = os.environ.get("INVITE_CODES", "")
    if not codes_raw:
        return True

    valid_codes = {c.strip() for c in codes_raw.split(",") if c.strip()}

    st.title("📊 SNS Analyzer")
    st.markdown("利用するには招待コードを入力してください。")

    code = st.text_input("招待コード", type="password", key="_invite_code_input")
    if st.button("ログイン", type="primary"):
        if code in valid_codes:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("招待コードが正しくありません。")

    return False
