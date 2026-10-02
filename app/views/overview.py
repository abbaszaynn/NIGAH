"""Situation room: what is in force now, where, and how fresh the evidence is."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from app import charts, data, maps
from app import theme as T
from app.views.common import alert_card, fmt, lake_table, weather_panel


def render():
    c = data.ctx()
    now_pkt = c.now.astimezone(data.PKT)
    nxt = data.next_scheduled_run(c.now)
    meta = f"Updated <b>{now_pkt:%d %b %Y, %H:%M} PKT</b>"
    if nxt:
        meta += f"<br>Next scheduled lake check <b>{nxt.astimezone(data.PKT):%a %d %b, %H:%M} PKT</b>"
    st.markdown(T.page_header("Situation room", "Glacial lake outburst and landslide early warning · "
                              "Gilgit-Baltistan", meta), unsafe_allow_html=True)

    o = c.overall
    right = (f"Lakes watched <b>{sum(l.drawn for l in c.lakes)}</b> of {len(c.lakes)}<br>"
             f"Thresholds <b>{'tuned' if c.th['tuned'] else 'untuned defaults'}</b>")
    st.markdown(T.banner(o["tier"], o["level"], o["headline"], o["body"], right), unsafe_allow_html=True)

    active = [l for l in c.lakes if l.active]
    counts = {t: sum(l.tier == t for l in c.lakes) for t in ("alert", "warning", "watch")}
    monitored = [l for l in c.lakes if l.series is not None]
    qa_ok = [l for l in monitored if l.tier != "qa_failed"]
    latest = max((l.date for l in monitored), default=None)
    age = (c.now.replace(tzinfo=None) - latest.to_pydatetime()).days if latest is not None else None
    rep7 = None
    if c.reports is not None:
        rep7 = int((c.reports["published"] >= pd.Timestamp(c.now) - pd.Timedelta(days=7)).sum())
    st.markdown(T.kpis([
        {"label": "Alerts in force", "icon": "notifications_active", "value": str(len(active)),
         "sub": " · ".join(f"{v} {k}" for k, v in counts.items() if v) or "none"},
        {"label": "Lakes with a series", "icon": "water", "value": f"{len(monitored)} / {len(c.lakes)}",
         "sub": f"{len(qa_ok)} pass quality checks", "bad": len(qa_ok) < len(monitored)},
        {"label": "Latest clear scene", "icon": "satellite_alt",
         "value": latest.strftime("%d %b %Y") if latest is not None else "none", "text": latest is None,
         "sub": f"{age} days ago" if age is not None else "run the lake pipeline",
         "bad": age is not None and data.in_season(c.now) and age > data.STALE_DAYS},
        {"label": "Field reports, 7 days", "icon": "forum",
         "value": str(rep7) if rep7 is not None else "–",
         "sub": "geolocated news items" if rep7 is not None else "not collected yet"},
        {"label": "Season", "icon": "calendar_month", "text": True,
         "value": "Monitoring" if data.in_season(c.now) else "Off season",
         "sub": "Apr–Oct satellite window"},
    ]), unsafe_allow_html=True)

    left, right = st.columns([2.15, 1], gap="medium")
    with left:
        st.markdown(T.section("Operational map", "Click a lake for details · layers top right"),
                    unsafe_allow_html=True)
        st_folium(maps.build(c, height=540), height=540, use_container_width=True, returned_objects=[],
                  key="overview_map")
        st.markdown(T.legend_tiers(("alert", "warning", "watch", "normal", "qa_failed", "stale", "no_data")),
                    unsafe_allow_html=True)
        st.write("")
        st.markdown(T.section("Lake status board", "latest clear Sentinel-2 scene per lake"),
                    unsafe_allow_html=True)
        lake_table(c)
    with right:
        st.markdown(T.section("Alerts in force", f"{len(active)} active"), unsafe_allow_html=True)
        if active:
            for lk in sorted(active, key=lambda l: -T.TIER_ORDER.index(l.tier) if l.tier in T.TIER_ORDER else 0):
                st.markdown(alert_card(lk), unsafe_allow_html=True)
        else:
            st.markdown(T.empty_state("No alert in force",
                                      "No lake's latest valid scene crossed a threshold within the last "
                                      f"{data.ACTIVE_DAYS} days.", ic="check_circle"), unsafe_allow_html=True)
        issues = [(l, i) for l in c.lakes for i in l.issues if i["level"] == "fail"]
        if issues:
            st.markdown(T.section("Data quality", f"{len(issues)} blocking"), unsafe_allow_html=True)
            for lk, i in issues:
                st.markdown(f'<div class="acard"><div class="top">{T.pill("qa_failed")}'
                            f'<span class="num" style="color:var(--ink3);font-size:.75rem">{T.esc(lk.id)}</span></div>'
                            f'<div class="t">{T.esc(lk.name)}: alerts suppressed</div>'
                            f'<div class="d">{T.esc(i["message"])}</div></div>', unsafe_allow_html=True)
        focus = next((l for l in active), None) or next((l for l in c.lakes if l.centroid), None)
        if focus:
            weather_panel(focus, c.mode, compact=True)
        st.markdown(T.section("Recent activity"), unsafe_allow_html=True)
        st.markdown(activity(c), unsafe_allow_html=True)



def activity(c) -> str:
    items = []
    if c.log is not None and len(c.log):
        for r in c.log.sort_values("date", ascending=False).head(8).itertuples():
            items.append((pd.Timestamp(r.date), T.icon(T.TIER_ICON.get(r.tier, "info"), f"var(--t-{r.tier})"),
                          f"<b>{T.esc(T.TIER_LABEL.get(r.tier, r.tier))}</b> {T.esc(r.lake)} · "
                          f"{fmt(r.area_km2, '.3f')} km²" + (" · sent" if str(r.sent) == "True" else "")))
    if c.reports is not None:
        for r in c.reports.dropna(subset=["published"]).sort_values("published", ascending=False).head(6).itertuples():
            items.append((r.published.tz_localize(None), T.icon("forum", "var(--accent)"),
                          f"<b>{T.esc(r.label if isinstance(r.label, str) and r.label else 'report')}</b> "
                          f"{T.esc(str(r.title)[:80])}"))
    for lk in c.lakes:
        if lk.date is not None:
            items.append((lk.date, T.icon("satellite_alt", "var(--ink3)"),
                          f"<b>Scene</b> {T.esc(lk.name)} · {fmt(lk.area, '.3f')} km²"))
    if not items:
        return T.empty_state("Nothing yet", "Alerts, field reports and satellite scenes will appear here.")
    items.sort(key=lambda x: x[0], reverse=True)
    lis = "".join(f'<li><span class="dt">{d:%d %b %Y}</span>{ic}<span>{txt}</span></li>' for d, ic, txt in items[:12])
    return f'<div class="panel" style="padding:.3rem .9rem"><ul class="tl">{lis}</ul></div>'
