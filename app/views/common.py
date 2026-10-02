"""Pieces shared across pages."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import charts, data
from app import theme as T
from src.alerts.cap import PROTOCOL


def fmt(x, spec: str, dash: str = "–") -> str:
    try:
        return dash if x is None or pd.isna(x) else format(x, spec)
    except (TypeError, ValueError):
        return dash


def alert_card(lk) -> str:
    p = PROTOCOL[lk.tier]
    facts = [f"<span><b>Scene</b> {lk.date:%d %b %Y}</span>",
             f"<span><b>Area</b> {fmt(lk.area, '.3f')} km²</span>",
             f"<span><b>15-day</b> {fmt(lk.growth, '+.0%')}</span>",
             f"<span><b>z</b> {fmt(lk.z, '.1f')}</span>",
             f"<span><b>CAP</b> {p['severity']} · {p['urgency']} · {p['certainty']}</span>"]
    down = f" Downstream: {', '.join(lk.downstream)}." if lk.downstream else ""
    return (f'<div class="acard"><div class="top">{T.pill(lk.tier)}'
            f'<span class="num" style="color:var(--ink3);font-size:.75rem">{lk.age_days} d ago</span></div>'
            f'<div class="t">{T.esc(p["headline"])}: {T.esc(lk.name)}</div>'
            f'<div class="d">{T.esc(p["action"])}{T.esc(down)}</div>'
            f'<div class="f">{"".join(facts)}</div></div>')


def lake_table(c):
    rows = []
    for lk in c.lakes:
        trend = []
        if lk.series is not None:
            trend = lk.series["area_km2"].tail(24).round(4).tolist()
        issues = "; ".join(i["code"].replace("_", " ") for i in lk.issues)
        rows.append({
            "Lake": lk.name, "Status": T.TIER_LABEL[lk.tier],
            "Rule tier": T.TIER_LABEL.get(lk.hazard_tier, lk.hazard_tier) if lk.series is not None else "–",
            "Latest scene": lk.date.date() if lk.date is not None else None,
            "Age (d)": lk.age_days, "Area km²": lk.area, "vs 60-day median": lk.departure,
            "15-day change": lk.growth, "z-score": lk.z, "Trend (last 24 scenes)": trend,
            "Checks": issues or ("AOI not drawn" if not lk.drawn else ("no series" if lk.series is None else "ok")),
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, hide_index=True, width="stretch", column_config={
        "Latest scene": st.column_config.DateColumn(format="YYYY-MM-DD"),
        "Area km²": st.column_config.NumberColumn(format="%.3f"),
        "vs 60-day median": st.column_config.NumberColumn(format="percent"),
        "15-day change": st.column_config.NumberColumn(format="percent"),
        "z-score": st.column_config.NumberColumn(format="%.1f"),
        "Trend (last 24 scenes)": st.column_config.LineChartColumn(width="medium"),
    })
    st.markdown("<div class='caption'>Status is what the board acts on: QA failures and stale data override "
                "the rule tier. Rule tier is what the alert rules computed on the latest scene.</div>",
                unsafe_allow_html=True)


def weather_panel(lk, mode: str, compact: bool = False):
    lat, lon = lk.centroid
    wx = data.weather(lat, lon)
    st.markdown(T.section(f"Weather outlook · {lk.name}", "7 days"), unsafe_allow_html=True)
    if wx is None:
        st.markdown(T.empty_state("Forecast unavailable", "Open-Meteo could not be reached. Retries hourly.",
                                  ic="cloud_off"), unsafe_allow_html=True)
        return
    hot = wx[wx["temperature_2m_max"] > 0]
    fl = wx["freezing_level_max"].max()
    st.altair_chart(charts.weather(wx, mode), width="stretch")
    elev = wx.attrs.get("elevation")
    st.markdown(f"<div class='caption'>Highest freezing level {fl:,.0f} m · {len(hot)} of {len(wx)} days above 0 °C "
                f"at the grid elevation ({fmt(elev, ',.0f')} m). Warm spells speed melt and lake filling; this is "
                f"context, not an alert rule. Source: Open-Meteo forecast (CC BY 4.0), fetched {wx.attrs['fetched']}."
                "</div>", unsafe_allow_html=True)
