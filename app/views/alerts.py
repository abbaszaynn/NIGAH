"""Alerts & bulletins: what is in force, the warning matrix, CAP 1.2 messages, history, dissemination."""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from app import charts, data
from app import theme as T
from app.views.common import alert_card, fmt
from src.alerts.cap import PROTOCOL, bulletin, cap_xml, identifier


def render():
    c = data.ctx()
    st.markdown(T.page_header("Alerts & bulletins", "Warning matrix, messages in OASIS CAP 1.2, and the alert "
                              "history"), unsafe_allow_html=True)
    active = [l for l in c.lakes if l.active]

    st.markdown(T.section("In force", f"{len(active)} active · valid {data.ACTIVE_DAYS} days from scene date"),
                unsafe_allow_html=True)
    if not active:
        st.markdown(T.empty_state("No alert in force",
                                  "Bulletins and CAP messages appear here when a lake's latest valid scene "
                                  "crosses the watch line. Lakes that fail quality checks never issue alerts.",
                                  ic="check_circle"), unsafe_allow_html=True)
    for lk in active:
        obs = {"date": lk.date.date().isoformat(), "tier": lk.tier, "area_km2": lk.area,
               "growth_15d": lk.growth, "z": lk.z, "sensor": "s2"}
        en, ur = bulletin(lk.feature, obs)
        left, right = st.columns([1.1, 1], gap="medium")
        with left:
            st.markdown(alert_card(lk), unsafe_allow_html=True)
        with right:
            st.markdown(f"<div class='panel'><div style='font-size:.86rem;color:var(--ink)'>{T.esc(en)}</div>"
                        f"<div class='ur' lang='ur' style='margin-top:.5rem;color:var(--ink)'>{T.esc(ur)}</div></div>",
                        unsafe_allow_html=True)
            xml = cap_xml(lk.feature, obs, datetime.now(timezone.utc))
            st.download_button("Download CAP 1.2 XML", xml.encode(), f"{identifier(lk.id, obs['date'], lk.tier)}.xml",
                               "application/xml", icon=":material/download:", key=f"cap_{lk.id}")
            with st.expander("View CAP message"):
                st.code(xml, language="xml")

    st.markdown(T.section("Warning matrix", "tier → trigger → CAP fields → suggested action"), unsafe_allow_html=True)
    th = c.th
    trig = {
        "watch": f"z &gt; {th['watch']['z']} or 15-day growth &gt; {th['watch']['growth']:.0%}",
        "warning": f"z &gt; {th['warning']['z']} or 15-day growth &gt; {th['warning']['growth']:.0%}",
        "alert": f"both warning rules on one scene, or {th['consecutive_warnings']} warnings in a row",
    }
    rows = "".join(
        f"<tr><td>{T.pill(t)}</td><td>{trig[t]}</td>"
        f"<td class='num'>{p['severity']}<br><span class='mu'>{p['urgency']} · {p['certainty']}</span></td>"
        f"<td>{T.esc(p['action'])}</td><td class='ur' lang='ur'>{T.esc(p['action_ur'])}</td></tr>"
        for t, p in PROTOCOL.items())
    st.markdown(f"<div class='tbl-wrap'><table class='tbl'><tr><th>Tier</th><th>Trigger (Sentinel-2 scene)</th>"
                f"<th>CAP severity<br>urgency · certainty</th><th>Suggested action</th><th>اردو</th></tr>{rows}</table></div>"
                f"<div class='caption'>Triggers are computed by src/lakes/anomaly.py with thresholds from "
                f"{T.esc(th['source'])}. The CAP mapping and actions are a NIGAH proposal pending agreement with "
                f"GBDMA/NDMA; messages are issued with CAP status <b>Exercise</b> until then.</div>",
                unsafe_allow_html=True)

    st.markdown(T.section("Alert history"), unsafe_allow_html=True)
    log = c.log
    if log is None or log.empty:
        st.markdown(T.empty_state("No alerts logged",
                                  "The weekly job refreshes recent scenes, recomputes tiers and logs every Watch, "
                                  "Warning or Alert scene here, then sends new ones to Telegram.",
                                  "python -m src.alerts.check"), unsafe_allow_html=True)
    else:
        log = log.copy()
        log["date"] = pd.to_datetime(log["date"])
        f1, f2, f3 = st.columns([1.2, 1.2, 1])
        lakes = f1.multiselect("Lakes", sorted(log["lake"].unique()), placeholder="All lakes")
        tiers = f2.pills("Tiers", ["watch", "warning", "alert"], selection_mode="multi",
                         default=["watch", "warning", "alert"], format_func=lambda t: T.TIER_LABEL[t])
        f = log[(log["lake"].isin(lakes) if lakes else True) & log["tier"].isin(tiers or ["watch", "warning", "alert"])]
        f3.download_button("Download log (CSV)", f.to_csv(index=False).encode(), "nigah_alert_log.csv", "text/csv",
                           icon=":material/download:", width="stretch")
        if len(f):
            st.altair_chart(charts.alert_timeline(f, c.mode), width="stretch")
        f = f.sort_values("date", ascending=False)
        f["tier"] = f["tier"].map(T.TIER_LABEL)
        st.dataframe(f[["date", "lake", "tier", "area_km2", "growth_15d", "z", "sent", "logged_at"]], hide_index=True,
                     width="stretch", column_config={
                         "date": st.column_config.DateColumn("Scene", format="YYYY-MM-DD"), "lake": "Lake", "tier": "Tier",
                         "area_km2": st.column_config.NumberColumn("Area km²", format="%.3f"),
                         "growth_15d": st.column_config.NumberColumn("15-day change", format="percent"),
                         "z": st.column_config.NumberColumn("z-score", format="%.1f"),
                         "sent": st.column_config.CheckboxColumn("Telegram sent"), "logged_at": "Logged (UTC)"})

    st.markdown(T.section("Dissemination channels"), unsafe_allow_html=True)
    tg = data.secret_present("TELEGRAM_BOT_TOKEN") and data.secret_present("TELEGRAM_CHAT_ID")
    sent = int(log["sent"].astype(str).eq("True").sum()) if log is not None and len(log) else 0
    rows = [
        ("send", "Telegram bot", "configured" if tg else "not configured",
         f"{sent} messages sent" if tg else "Add TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID secrets", tg),
        ("description", "CAP 1.2 XML", "available", "Generated per alert; status Exercise", True),
        ("translate", "Bulletin text", "English + Urdu", "Template text; review wording with GBDMA", True),
    ]
    html = "".join(f"<div class='chk'>{T.icon(ic, 'var(--t-normal)' if ok else 'var(--t-warning)')}"
                   f"<div><div class='n'>{n}</div><div class='h'>{T.esc(h)}</div></div><div class='v'>{v}</div></div>"
                   for ic, n, v, h, ok in rows)
    st.markdown(f"<div class='panel'>{html}</div>", unsafe_allow_html=True)
