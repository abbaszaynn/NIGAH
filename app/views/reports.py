"""Field reports: Urdu/English news triaged into hazard classes and placed on the map."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from app import data, maps
from app import theme as T
from src.common import settings

CLASS_LABEL = {"rockfall": "Rockfall", "road_block": "Road block", "flood_glof": "Flood / GLOF",
               "irrelevant": "Irrelevant", "": "Unclassified"}


def render():
    c = data.ctx()
    st.markdown(T.page_header("Field reports", "Public news in Urdu and English, triaged by an XLM-R classifier "
                              "and geolocated with the GB gazetteer"), unsafe_allow_html=True)
    rep = c.reports
    if rep is None:
        raw = data.csv("reports_raw.csv")
        st.markdown(T.empty_state(
            f"{len(raw)} reports collected, not yet triaged" if raw is not None else "No field reports collected yet",
            "Collects GB news from free RSS feeds (Pamir Times, Dawn), keeps items that mention GB places or "
            "hazards, tags each with a class and places it on the map.",
            ("" if raw is not None else "python -m src.nlp.scrape\n") + "python -m src.nlp.classify predict"),
            unsafe_allow_html=True)
        return

    rep = rep.copy()
    rep["label"] = rep["label"].fillna("")
    now = pd.Timestamp(c.now)
    last7 = rep[rep["published"] >= now - pd.Timedelta(days=7)]
    last30 = rep[rep["published"] >= now - pd.Timedelta(days=30)]
    has_model = rep["label"].ne("").any()
    labels = settings()["nlp"]["labels"]
    items = [{"label": "Reports, 7 days", "icon": "forum", "value": str(len(last7)), "sub": f"{len(last30)} in 30 days"},
             {"label": "Geolocated", "icon": "location_on", "value": f"{rep['lat'].notna().mean():.0%}",
              "sub": f"{int(rep['lat'].notna().sum())} of {len(rep)}"}]
    if has_model:
        for l in [x for x in labels if x != "irrelevant"]:
            items.append({"label": f"{CLASS_LABEL[l]}, 30 d", "icon": "label", "value": str(int((last30["label"] == l).sum())),
                          "sub": "classifier output"})
    else:
        items.append({"label": "Classifier", "icon": "label_off", "value": "not trained", "text": True,
                      "sub": "reports shown unclassified", "bad": True})
    st.markdown(T.kpis(items), unsafe_allow_html=True)

    left, right = st.columns([1.4, 1], gap="medium")
    with right:
        sel = labels
        if has_model:
            sel = st.pills("Classes", labels, selection_mode="multi", default=[l for l in labels if l != "irrelevant"],
                           format_func=lambda l: CLASS_LABEL[l]) or labels
        q = st.text_input("Search headlines or places", placeholder="e.g. Attabad, KKH, سیلاب")
        shown = rep[rep["label"].isin(sel)] if has_model else rep
        if q:
            mask = shown["title"].fillna("").str.contains(q, case=False) | shown["places"].fillna("").str.contains(q, case=False)
            shown = shown[mask]
        shown = shown.sort_values("published", ascending=False)
        if has_model:
            counts = shown.assign(day=shown["published"].dt.tz_localize(None).dt.floor("D"),
                                  cls=shown["label"].map(CLASS_LABEL))
            st.altair_chart(alt.Chart(counts).mark_bar().encode(
                x=alt.X("day:T", title=None), y=alt.Y("count():Q", title="Reports"),
                color=alt.Color("cls:N", title="Class")).properties(height=140), width="stretch")
    with left:
        st_folium(maps.build(c, height=460, layers=("lakes", "corridor", "reports", "places"), basemap="Terrain"),
                  height=460, use_container_width=True, returned_objects=[], key="rep_map")
    st.dataframe(shown[["published", "label", "confidence", "title", "places", "source", "link"]], hide_index=True,
                 width="stretch", height=420, column_config={
                     "published": st.column_config.DatetimeColumn("Published", format="YYYY-MM-DD HH:mm"),
                     "label": "Class", "confidence": st.column_config.ProgressColumn("Confidence", min_value=0, max_value=1),
                     "title": st.column_config.TextColumn("Headline", width="large"), "places": "Places",
                     "source": "Source", "link": st.column_config.LinkColumn("Link", display_text="Open")})
    st.markdown("<div class='caption'>Reports are unverified public news. Places are matched from "
                "config/gazetteer.csv; a report is pinned at its first matched place.</div>", unsafe_allow_html=True)

    f1 = data.csv("nlp_f1.csv", index_col=0)
    if f1 is not None:
        st.markdown(T.section("Classifier on held-out set"), unsafe_allow_html=True)
        st.dataframe(f1.loc[[l for l in labels if l in f1.index], ["precision", "recall", "f1-score", "support"]],
                     width="stretch")
