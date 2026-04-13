"""Invite-code authentication for SNS Analyzer."""

import os

import streamlit as st


def check_authentication():
    """Check if the user is authenticated. Show login UI if not.

    Call this AFTER st.set_page_config().

    Sets st.session_state["is_admin"] based on whether the code matches
    ADMIN_INVITE_CODES (admin codes get full access to all tabs).

    Returns:
        True if authenticated or auth is disabled (no INVITE_CODES set).
    """
    if st.session_state.get("authenticated"):
        return True

    codes_raw = os.environ.get("INVITE_CODES", "")
    admin_codes_raw = os.environ.get("ADMIN_INVITE_CODES", "")

    if not codes_raw and not admin_codes_raw:
        # No auth configured — allow access as admin (local dev)
        st.session_state["is_admin"] = True
        return True

    valid_codes = {c.strip() for c in codes_raw.split(",") if c.strip()}
    admin_codes = {c.strip() for c in admin_codes_raw.split(",") if c.strip()}
    all_valid = valid_codes | admin_codes

    st.title("📊 SNS Analyzer")
    st.markdown("利用するには招待コードを入力してください。")

    code = st.text_input("招待コード", type="password", key="_invite_code_input")
    if st.button("ログイン", type="primary"):
        if code in all_valid:
            st.session_state["authenticated"] = True
            st.session_state["is_admin"] = code in admin_codes
            st.rerun()
        else:
            st.error("招待コードが正しくありません。")

    return False
