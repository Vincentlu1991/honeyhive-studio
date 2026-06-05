from __future__ import annotations

import os
from urllib.parse import urlparse

import requests
import streamlit as st
import streamlit.components.v1 as components


DEFAULT_COMFY_APP_URL = os.getenv("COMFY_APP_URL", "http://localhost:8501")
DEFAULT_SECRETARY_APP_URL = os.getenv("SECRETARY_APP_URL", "http://localhost:8507")


st.set_page_config(page_title="Unified AI Workspace", layout="wide")
st.title("Unified AI Workspace")
st.caption("One portal, two projects: video generation and personal secretary")


page = st.sidebar.radio(
    "Pages",
    [
        "ComfyUI Video Project",
        "Personal Secretary Project",
    ],
)


st.sidebar.subheader("Target URLs")
comfy_url = st.sidebar.text_input("ComfyUI app URL", value=DEFAULT_COMFY_APP_URL)
secretary_url = st.sidebar.text_input("Secretary app URL", value=DEFAULT_SECRETARY_APP_URL)


def check_url(url: str) -> tuple[bool, str]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False, "Invalid URL"

    try:
        resp = requests.get(url, timeout=2)
        if 200 <= resp.status_code < 500:
            return True, f"Reachable (status {resp.status_code})"
        return False, f"Unhealthy (status {resp.status_code})"
    except Exception as exc:
        return False, f"Unreachable ({exc})"


if page == "ComfyUI Video Project":
    st.subheader("ComfyUI Video Project")
    ok, msg = check_url(comfy_url)
    if ok:
        st.success(msg)
    else:
        st.warning(msg)

    st.markdown("Run command if not started:")
    st.code(
        "cd \"C:/Users/User/OneDrive/文档/New project/agent-platform\"\n"
        "$env:PYTHONPATH='src'\n"
        ".\\.venv\\Scripts\\python.exe -m streamlit run app_robust.py",
        language="powershell",
    )

    components.iframe(comfy_url, height=900, scrolling=True)

elif page == "Personal Secretary Project":
    st.subheader("Personal Secretary Project")
    ok, msg = check_url(secretary_url)
    if ok:
        st.success(msg)
    else:
        st.warning(msg)

    st.markdown("Run command if not started:")
    st.code(
        "cd \"C:/Users/User/OneDrive/文档/New project/personal-secretary\"\n"
        "$env:PYTHONPATH='src'\n"
        ".\\.venv\\Scripts\\python.exe -m streamlit run app_dashboard.py",
        language="powershell",
    )

    components.iframe(secretary_url, height=900, scrolling=True)
