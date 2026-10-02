"""NIGAH early-warning dashboard.

Run from the repo root:
    streamlit run app/streamlit_app.py

Reads only outputs/ and config/ (plus live Open-Meteo weather for context).
Missing outputs render as empty states that name the script producing them.
"""

from __future__ import annotations

import sys
from pathlib import Path

import altair as alt
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import data  # noqa: E402
from app import theme as T  # noqa: E402
from app.views import alerts, health, lakes, landslide, method, overview, reports  # noqa: E402

st.set_page_config(page_title="NIGAH · GB early warning", page_icon=":material/crisis_alert:", layout="wide",
                   initial_sidebar_state="auto")
mode = data.mode()
st.markdown(T.css(mode), unsafe_allow_html=True)
alt.theme.register("nigah", enable=True)(T.altair_theme(mode))


def sidebar():
    c = data.ctx()
    with st.sidebar:
        st.markdown('<div class="brand"><span class="w">NIGAH</span><span class="u" lang="ur">نگاہ</span></div>'
                    '<div class="brand-sub">GLOF and landslide early warning, Gilgit-Baltistan. '
                    'Research prototype, not an official NDMA warning.</div>', unsafe_allow_html=True)
        st.markdown(T.pill(c.overall["tier"], c.overall["level"]), unsafe_allow_html=True)
        st.write("")
        auto = st.toggle("Auto-refresh when data changes", value=True,
                         help="Checks outputs/ every minute and reloads the page when a pipeline writes new results.")
        live(auto)
        st.divider()
        st.markdown("<div class='caption'>Theme: app menu (⋮) → Settings → Theme. Dark suits an operations room, "
                    "light suits daylight and phones.</div>", unsafe_allow_html=True)


def _clock():
    now = data.now_utc()
    st.markdown(f"<div class='clock'><b>{now.astimezone(data.PKT):%H:%M}</b> PKT · {now:%H:%M} UTC<br>"
                f"{now.astimezone(data.PKT):%a %d %b %Y}</div>", unsafe_allow_html=True)
    sig = data.outputs_signature()
    prev = st.session_state.get("outputs_sig")
    st.session_state["outputs_sig"] = sig
    if prev is not None and sig != prev:
        st.rerun(scope="app")


def live(auto: bool):
    if auto:
        st.fragment(run_every="60s")(_clock)()
    else:
        _clock()


pages = [
    st.Page(overview.render, title="Situation room", icon=":material/space_dashboard:", url_path="situation", default=True),
    st.Page(lakes.render, title="Lake monitor", icon=":material/water:", url_path="lakes"),
    st.Page(alerts.render, title="Alerts & bulletins", icon=":material/campaign:", url_path="alerts"),
    st.Page(landslide.render, title="Landslide risk", icon=":material/landslide:", url_path="landslide"),
    st.Page(reports.render, title="Field reports", icon=":material/forum:", url_path="reports"),
    st.Page(health.render, title="System health", icon=":material/monitor_heart:", url_path="health"),
    st.Page(method.render, title="Data & method", icon=":material/menu_book:", url_path="method"),
]
nav = st.navigation(pages, position="top")
sidebar()
nav.run()
