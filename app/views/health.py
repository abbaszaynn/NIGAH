"""System health: MHEWS pillar coverage, pipeline freshness, configuration and data-quality checks."""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from app import data
from app import theme as T

PILLAR_TIER = {"ok": "normal", "partial": "watch", "gap": "alert"}
PILLAR_TEXT = {"ok": "In place", "partial": "Partial", "gap": "Gap"}


def render():
    c = data.ctx()
    st.markdown(T.page_header("System health", "Is the warning chain working end to end?"), unsafe_allow_html=True)
    pipe = data.pipeline_status(c.now)
    checks = data.config_checks(c)

    st.markdown(T.section("Early-warning chain", "UN Early Warnings for All / WMO MHEWS four pillars"),
                unsafe_allow_html=True)
    cols = st.columns(4)
    for col, p in zip(cols, data.pillars(c, pipe, checks)):
        col.markdown(f"<div class='panel' style='height:100%'><div style='font-weight:600;font-size:.9rem'>"
                     f"{T.esc(p['pillar'])}</div><div style='margin:.45rem 0'>"
                     f"{T.pill(PILLAR_TIER[p['status']], PILLAR_TEXT[p['status']])}</div>"
                     f"<div style='font-size:.8rem;color:var(--ink2)'>{T.esc(p['evidence'])}</div></div>",
                     unsafe_allow_html=True)

    left, right = st.columns([1.6, 1], gap="medium")
    with left:
        st.markdown(T.section("Pipeline freshness"), unsafe_allow_html=True)
        st.dataframe(pipe, hide_index=True, width="stretch", column_config={
            "component": "Component", "status": "Status",
            "updated": st.column_config.DatetimeColumn("Last updated (UTC)", format="YYYY-MM-DD HH:mm"),
            "age_days": st.column_config.NumberColumn("Age (d)", format="%.1f"), "files": "Files",
            "cadence": "Expected", "producer": st.column_config.TextColumn("Produced by", width="medium")})
    with right:
        st.markdown(T.section("Configuration", f"{sum(x['ok'] for x in checks)}/{len(checks)} passing"),
                    unsafe_allow_html=True)
        html = "".join(f"<div class='chk'>{T.icon('check_circle' if x['ok'] else 'error', 'var(--t-normal)' if x['ok'] else 'var(--t-warning)')}"
                       f"<div><div class='n'>{T.esc(x['name'])}</div><div class='h'>{T.esc(x['hint'])}</div></div>"
                       f"<div class='v'>{T.esc(x['value'])}</div></div>" for x in checks)
        st.markdown(f"<div class='panel' style='padding:.2rem .9rem'>{html}</div>", unsafe_allow_html=True)

    st.markdown(T.section("Satellite data quality", "per lake and season"), unsafe_allow_html=True)
    rows, monthly = [], []
    for lk in c.lakes:
        if lk.raw is None:
            continue
        r = lk.raw.copy()
        r["season"] = r["date"].dt.year
        for (season, sensor), g in r.groupby(["season", "sensor"]):
            rows.append({"lake": lk.name, "season": season, "sensor": data.SENSOR_LABEL[sensor], "scenes": len(g),
                         "mean_clear": g["valid_frac"].mean(), "min_area": g["area_km2"].min(),
                         "max_area": g["area_km2"].max()})
        r["month"] = r["date"].dt.to_period("M").dt.to_timestamp()
        monthly.append(r.groupby(["month", "sensor"]).size().rename("scenes").reset_index().assign(lake=lk.name))
        for i in lk.issues:
            st.markdown(f"<div class='acard'><div class='top'>"
                        f"{T.pill('qa_failed' if i['level'] == 'fail' else 'stale', 'QA fail' if i['level'] == 'fail' else 'QA warning')}"
                        f"<span class='num' style='color:var(--ink3);font-size:.75rem'>{T.esc(i['code'])}</span></div>"
                        f"<div class='t'>{T.esc(lk.name)}</div><div class='d'>{T.esc(i['message'])}</div></div>",
                        unsafe_allow_html=True)
    if not rows:
        st.markdown(T.empty_state("No satellite series yet", "Data-quality statistics appear after the first lake run.",
                                  "python -m src.lakes.lake_area --lake shisper"), unsafe_allow_html=True)
        return
    m = pd.concat(monthly)
    m["sensor"] = m["sensor"].map(data.SENSOR_LABEL)
    st.altair_chart(alt.Chart(m).mark_bar().encode(
        x=alt.X("month:T", title=None), y=alt.Y("scenes:Q", title="Clear scenes per month"),
        color=alt.Color("sensor:N", title="Sensor", scale=alt.Scale(range=[T.MODES[c.mode]["accent"], T.MODES[c.mode]["ink3"], "#8a7fb5"])),
        tooltip=["lake:N", alt.Tooltip("month:T", format="%b %Y"), "sensor:N", "scenes:Q"]).properties(height=170),
        width="stretch")
    st.dataframe(pd.DataFrame(rows).sort_values(["lake", "season", "sensor"], ascending=[True, False, True]),
                 hide_index=True, width="stretch", column_config={
                     "lake": "Lake", "season": st.column_config.NumberColumn("Season", format="%d"), "sensor": "Sensor",
                     "scenes": "Clear scenes", "mean_clear": st.column_config.ProgressColumn("Mean AOI clear", format="percent", min_value=0, max_value=1),
                     "min_area": st.column_config.NumberColumn("Min km²", format="%.3f"),
                     "max_area": st.column_config.NumberColumn("Max km²", format="%.3f")})
    st.markdown("<div class='caption'>Scenes kept only when at least 80% of the AOI is usable (cloud-free and "
                "not in terrain shadow).</div>", unsafe_allow_html=True)
