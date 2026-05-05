"""Configuration helpers for local env vars and Streamlit Cloud secrets."""

import json
import os
from typing import Any, Mapping


def _streamlit_secrets() -> Mapping[str, Any]:
    """Return Streamlit secrets when available, otherwise an empty mapping."""
    try:
        import streamlit as st

        return st.secrets
    except Exception:
        return {}


def get_secret(*names: str, default: str = "") -> str:
    """Read the first configured value from environment variables or st.secrets.

    Environment variables win so local overrides keep working. Multiple names
    support deployment aliases such as APIFY_API_TOKEN and APIFY_TOKEN.
    """
    for name in names:
        value = os.environ.get(name, "")
        if value:
            return str(value)

    secrets = _streamlit_secrets()
    for name in names:
        try:
            value = secrets.get(name)
        except Exception:
            value = None
        if value:
            return str(value)

    return default


def get_google_credentials() -> dict | None:
    """Return Google service account credentials from env or Streamlit secrets.

    Supported formats:
    - GOOGLE_CREDENTIALS='{"type":"service_account",...}'
    - [google_credentials] table in Streamlit Cloud Secrets
    """
    raw = get_secret("GOOGLE_CREDENTIALS")
    if raw:
        return json.loads(raw)

    secrets = _streamlit_secrets()
    try:
        table = secrets.get("google_credentials")
    except Exception:
        table = None

    if table:
        return dict(table)

    return None
