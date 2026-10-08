"""Apex Patch Feedback Copilot — Streamlit entry point.

Kept intentionally thin: page configuration, the global stylesheet, and a
single call into :func:`src.ui.app_shell.run`. All behaviour lives in
``src/core`` (domain), ``src/services`` (use cases), and ``src/ui`` (widgets).
"""
from __future__ import annotations

import streamlit as st

from src import __version__
from src.ui.app_shell import run
from src.ui.theme import CUSTOM_CSS

st.set_page_config(page_title="Apex 版本反馈与问题分流助手", page_icon="◫", layout="wide")
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

run(__version__)
