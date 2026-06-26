"""Streamlit launcher — embeds the FastAPI voice UI or documents the native client."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

FASTAPI_PORT = int(os.getenv("FRONTEND_PORT", "8080"))
FASTAPI_URL = os.getenv("FRONTEND_URL", f"http://127.0.0.1:{FASTAPI_PORT}")


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


st.set_page_config(
    page_title="LangGraph Voice Agent",
    page_icon="🎙️",
    layout="wide",
)

st.title("🗣️ LinguaAI — Voice Language Coach")
st.caption("AI-powered language learning through real-time voice conversation")

tab_web, tab_native, tab_setup = st.tabs(["Browser UI (FastAPI)", "Native client", "Setup"])

with tab_setup:
    st.markdown(
        """
        **Before starting a call**, run these in separate terminals:

        1. `docker compose up -d`
        2. `uv run langgraph dev`
        3. `uv run -m src.livekit.agent dev`
        4. Start this UI (FastAPI tab) or the native client
        """
    )
    st.code(
        f"""# Terminal A — web UI (recommended)
uv run python -m src.frontend.server

# Open {FASTAPI_URL}

# Terminal B — optional native mic client (no browser)
uv run python -m src.frontend.native_client
""",
        language="bash",
    )

with tab_web:
    st.markdown(
        f"""
        The **FastAPI** app serves the same flow as
        [langgraph-voice-call-agent-web](https://github.com/ahmad2b/langgraph-voice-call-agent-web):
        token API + LiveKit voice call in the browser.

        Start the server, then use the embedded page below.
        """
    )
    if st.button("Open in new tab", type="primary"):
        st.markdown(f"[{FASTAPI_URL}]({FASTAPI_URL})")

    st.components.v1.iframe(f"{FASTAPI_URL}/", height=720, scrolling=True)

    with st.expander("Start FastAPI from here (optional)"):
        if st.button("Launch server subprocess"):
            root = _project_root()
            proc = subprocess.Popen(
                [sys.executable, "-m", "src.frontend.server"],
                cwd=str(root),
                env=os.environ.copy(),
            )
            st.success(f"Started PID {proc.pid} — open {FASTAPI_URL}")
            st.info("Prefer running `uv run python -m src.frontend.server` in a dedicated terminal.")

with tab_native:
    st.markdown(
        """
        **Native client** uses the LiveKit Python SDK + your system microphone.
        No browser required; best on Linux/macOS. On Windows, prefer the FastAPI browser UI.
        """
    )
    st.code("uv run python -m src.frontend.native_client", language="bash")
    st.warning("Press Ctrl+C in the terminal to end the call.")
