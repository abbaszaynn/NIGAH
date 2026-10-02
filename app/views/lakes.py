"""Lake monitor: one lake in depth. Area vs normal range, rule panels, seasons, observations."""

from __future__ import annotations

import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from app import charts, data, maps
from app import theme as T
from app.views.common import fmt, weather_panel


def render():
    c = data.ctx()
    drawn = [l for l in c.lakes if l.drawn]
    st.markdown(T.page_header("Lake monitor", "Sentinel-2 water area per clear scene, against each lake's own "
                              "60-day normal range"), unsafe_allow_html=True)
    if not drawn:
        st.markdown(T.empty_state("No lake AOIs drawn", "Draw lake polygons in the GEE Code Editor and paste "
                                  "them into config/aoi.geojson."), unsafe_allow_html=True)
        return
    names = {l.name: l for l in drawn}
    default = next((l.name for l in drawn if l.series is not None), drawn[0].name)
    pick = st.segmented_control("Lake", list(names), default=default, label_visibility="collapsed",
                                key="lake_pick") or default
    lk = names[pick]

    down = f" · downstream {', '.join(lk.downstream)}" if lk.downstream else ""
    st.markdown(f"<div style='display:flex;gap:.6rem;align-items:center;flex-wrap:wrap;margin:.3rem 0 .8rem'>"
                f"<span style='font-size:1.15rem;font-weight:600'>{T.esc(lk.name)}</span>{T.pill(lk.tier)}"
                f"<span style='color:var(--ink3);font-size:.85rem'>{T.esc(lk.valley)}{T.esc(down)} · AOI "
                f"{'verified' if lk.verified else 'approximate, not verified'}</span></div>", unsafe_allow_html=True)

    for i in lk.issues:
        tier = "qa_failed" if i["level"] == "fail" else "stale"
        st.markdown(f"<div class='acard' style='border-color:var(--t-{tier})'><div class='top'>"
                    f"{T.pill(tier, 'Blocking: alerts suppressed' if i['level'] == 'fail' else 'Caution')}</div>"
                    f"<div class='d'>{T.esc(i['message'])}</div></div>", unsafe_allow_html=True)

    if lk.series is None:
        st.markdown(T.empty_state(f"No area series for {lk.name} yet",
                                  "Measures water area in every clear Apr–Oct Sentinel-2 scene, plus "
                                  "Sentinel-1 radar for cloudy gaps.",
                                  f"python -m src.lakes.lake_area --lake {lk.id}"), unsafe_allow_html=True)
        return

    th = c.th
    st.markdown(T.kpis([
        {"label": "Water area", "icon": "water", "value": f"{fmt(lk.area, '.3f')} km²",
         "sub": f"scene {lk.date:%d %b %Y}"},
        {"label": "60-day median", "icon": "horizontal_rule", "value": f"{fmt(lk.baseline, '.3f')} km²",
         "sub": f"departure {fmt(lk.departure, '+.0%')}"},
        {"label": "15-day change", "icon": "trending_up", "value": fmt(lk.growth, "+.0%"),
         "sub": f"warning above {th['warning']['growth']:.0%}",
         "bad": lk.growth is not None and lk.growth == lk.growth and lk.growth > th["warning"]["growth"]},
        {"label": "Robust z-score", "icon": "query_stats", "value": fmt(lk.z, ".1f"),
         "sub": f"warning above {th['warning']['z']}",
         "bad": lk.z is not None and lk.z == lk.z and lk.z > th["warning"]["z"]},
        {"label": "Clear scenes", "icon": "satellite_alt", "value": str(lk.n_obs),
         "sub": f"{lk.n_season} in {lk.date.year} · last {lk.age_days} d ago",
         "bad": data.in_season(c.now) and lk.age_days > data.STALE_DAYS},
    ]), unsafe_allow_html=True)

    years = sorted(lk.series.index.year.unique())
    c1, c2, c3 = st.columns([3, 1.2, 1.2])
    with c1:
        y0, y1 = st.select_slider("Seasons shown", options=years, value=(years[0], years[-1]),
                                  key=f"yr_{lk.id}") if len(years) > 1 else (years[0], years[0])
    with c2:
        show_s1 = st.toggle("Sentinel-1 gap-fill points", value=True, key=f"s1_{lk.id}")
    with c3:
        st.download_button("Download series (CSV)", lk.series.to_csv().encode(), f"{lk.id}_alerts.csv",
                           "text/csv", icon=":material/download:", width="stretch")
    start, end = pd.Timestamp(f"{y0}-01-01"), pd.Timestamp(f"{y1}-12-31")

    main, side = st.columns([2.3, 1.1], gap="medium")
    with main:
        t1, t2, t3, t4 = st.tabs([":material/monitoring: Anomaly monitor", ":material/stacked_line_chart: Season comparison",
                                  ":material/table: Observations", ":material/map: Map"])
        with t1:
            st.altair_chart(charts.lake_main(lk, c.events, th, c.mode, start, end, show_s1), width="stretch")
            st.markdown(f"<div class='caption'>Shaded band: normal range, the 60-day median ± {th['warning']['z']} "
                        f"robust standard deviations (scenes above it trip the z-score rule). Dashed line: "
                        f"60-day median. Source: Sentinel-2 L1C MNDWI with Cloud Score+ mask"
                        f"{' and Sentinel-1 VV (grey triangles, gap-fill only)' if show_s1 else ''}, Google Earth "
                        f"Engine, {max(start, lk.raw['date'].min()):%Y-%m-%d} to {min(end, lk.raw['date'].max()):%Y-%m-%d}, "
                        f"Apr–Oct. Drag to pan, Shift + scroll to zoom.</div>", unsafe_allow_html=True)
            a, b = st.columns(2)
            with a:
                st.altair_chart(charts.rule_panel(lk, "z", "Robust z-score", ".1f", th["watch"]["z"],
                                                  th["warning"]["z"], c.mode, start, end), width="stretch")
            with b:
                st.altair_chart(charts.rule_panel(lk, "growth_15d", "15-day change", "+.0%", th["watch"]["growth"],
                                                  th["warning"]["growth"], c.mode, start, end), width="stretch")
            st.markdown(f"<div class='caption'>Rule panels: each scene's value against the watch and warning lines. "
                        f"Thresholds from {T.esc(th['source'])}.</div>", unsafe_allow_html=True)
        with t2:
            st.altair_chart(charts.seasonal(lk, c.mode), width="stretch")
            st.markdown("<div class='caption'>Each season plotted on a common Apr–Oct axis, so this year can be "
                        "compared with the same weeks in earlier years. Source: Sentinel-2, as above.</div>",
                        unsafe_allow_html=True)
        with t3:
            obs = lk.series.reset_index().sort_values("date", ascending=False)
            obs["tier"] = obs["tier"].map(T.TIER_LABEL)
            st.dataframe(obs[["date", "area_km2", "baseline_median", "growth_15d", "z", "tier", "valid_frac", "scene"]],
                         hide_index=True, width="stretch", height=420, column_config={
                             "date": st.column_config.DateColumn("Scene", format="YYYY-MM-DD"),
                             "area_km2": st.column_config.NumberColumn("Area km²", format="%.4f"),
                             "baseline_median": st.column_config.NumberColumn("60-day median", format="%.4f"),
                             "growth_15d": st.column_config.NumberColumn("15-day change", format="percent"),
                             "z": st.column_config.NumberColumn("z-score", format="%.1f"),
                             "tier": "Rule tier",
                             "valid_frac": st.column_config.ProgressColumn("AOI clear", format="percent",
                                                                           min_value=0, max_value=1),
                             "scene": "Scene id"})
        with t4:
            st_folium(maps.build(c, height=480, focus=lk.id), height=480, use_container_width=True,
                      returned_objects=[], key=f"lakemap_{lk.id}")

    with side:
        st.markdown(T.section("Threshold crossings", "latest first"), unsafe_allow_html=True)
        hits = lk.series[lk.series["tier"].isin(["watch", "warning", "alert"])].iloc[::-1].head(10)
        if len(hits):
            lis = "".join(
                f"<li><span class='dt'>{d:%d %b %Y}</span>{T.icon(T.TIER_ICON[r.tier], f'var(--t-{r.tier})')}"
                f"<span><b>{T.TIER_LABEL[r.tier]}</b> · {fmt(r.area_km2, '.3f')} km² · "
                f"{fmt(r.growth_15d, '+.0%')} · z {fmt(r.z, '.1f')}</span></li>" for d, r in hits.iterrows())
            st.markdown(f"<div class='panel' style='padding:.3rem .9rem'><ul class='tl'>{lis}</ul></div>",
                        unsafe_allow_html=True)
            if lk.tier == "qa_failed":
                st.markdown("<div class='caption'>Computed by the rules but suppressed: this series failed QA.</div>",
                            unsafe_allow_html=True)
        else:
            st.markdown(T.empty_state("No crossings", "No scene crossed the watch line."), unsafe_allow_html=True)
        st.write("")
        weather_panel(lk, c.mode)
