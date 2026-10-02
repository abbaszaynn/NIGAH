"""Altair chart builders. Anomalies use shape + colour + text, never colour alone."""

from __future__ import annotations

import altair as alt
import pandas as pd

from app import theme as T
from app.data import SENSOR_LABEL
from src.common import settings

HAZ = ["watch", "warning", "alert"]
SHAPES = {"watch": "circle", "warning": "triangle-up", "alert": "diamond"}


def _tier_scale(mode):
    return alt.Scale(domain=[T.TIER_LABEL[t] for t in HAZ], range=[T.tier_color(mode, t) for t in HAZ])


def _shape_scale():
    return alt.Scale(domain=[T.TIER_LABEL[t] for t in HAZ], range=[SHAPES[t] for t in HAZ])


def lake_main(lk, ev: pd.DataFrame, th: dict, mode: str, start=None, end=None, show_s1=True) -> alt.Chart:
    m = T.MODES[mode]
    al = lk.series.reset_index().copy()
    k = th["warning"]["z"] * 1.4826
    al["lo"] = (al["baseline_median"] - k * al["baseline_mad"]).clip(lower=0)
    al["hi"] = al["baseline_median"] + k * al["baseline_mad"]
    al["season"] = al["date"].dt.year
    al["tier_label"] = al["tier"].map(T.TIER_LABEL)
    raw = lk.raw.copy()
    raw["sensor_label"] = raw["sensor"].map(SENSOR_LABEL)
    raw["season"] = raw["date"].dt.year
    if start is not None:
        al = al[(al["date"] >= start) & (al["date"] <= end)]
        raw = raw[(raw["date"] >= start) & (raw["date"] <= end)]

    x = alt.X("date:T", title=None)
    y = alt.Y("area_km2:Q", title="Water area (km²)")
    tip = [alt.Tooltip("date:T", title="Scene"), alt.Tooltip("area_km2:Q", title="Area km²", format=".3f"),
           alt.Tooltip("tier_label:N", title="Tier"), alt.Tooltip("growth_15d:Q", title="15-day change", format="+.0%"),
           alt.Tooltip("z:Q", title="z-score", format=".1f"),
           alt.Tooltip("baseline_median:Q", title="60-day median", format=".3f"),
           alt.Tooltip("valid_frac:Q", title="AOI clear", format=".0%")]
    layers = []

    bt = settings()["backtest"]
    band = pd.DataFrame({"s": [pd.Timestamp(bt["tune_start"])], "e": [pd.Timestamp(bt["tune_end"])], "t": ["Tuning period"]})
    if start is None or (band["e"][0] >= start and band["s"][0] <= end):
        layers.append(alt.Chart(band).mark_rect(color=m["surface2"], opacity=0.55).encode(x="s:T", x2="e:T"))
        layers.append(alt.Chart(band).mark_text(align="left", baseline="top", dx=4, dy=4, fontSize=10,
                                                color=m["ink3"]).encode(x="s:T", y=alt.value(0), text="t:N"))

    layers.append(alt.Chart(al.dropna(subset=["lo"])).mark_area(color=m["accent"], opacity=0.13)
                  .encode(x=x, y=alt.Y("lo:Q", title="Water area (km²)"), y2="hi:Q", detail="season:N"))
    layers.append(alt.Chart(al.dropna(subset=["baseline_median"])).mark_line(color=m["accent"], strokeDash=[3, 3],
                  strokeWidth=1, opacity=0.8).encode(x=x, y="baseline_median:Q", detail="season:N"))
    if show_s1:
        s1 = raw[raw["sensor"] == "s1"]
        if len(s1):
            layers.append(alt.Chart(s1).mark_point(shape="triangle-down", size=14, opacity=0.45, color=m["ink3"])
                          .encode(x=x, y=y, tooltip=[alt.Tooltip("date:T"), alt.Tooltip("area_km2:Q", format=".3f"),
                                                     alt.Tooltip("sensor_label:N", title="Sensor")]))
    layers.append(alt.Chart(al).mark_line(color=m["accent"], strokeWidth=1.6).encode(x=x, y=y, detail="season:N"))
    layers.append(alt.Chart(al).mark_point(filled=True, size=18, color=m["accent"]).encode(x=x, y=y, tooltip=tip))
    hits = al[al["tier"].isin(HAZ)]
    if len(hits):
        layers.append(alt.Chart(hits).mark_point(filled=True, size=90, stroke=m["surface"], strokeWidth=1).encode(
            x=x, y=y, tooltip=tip,
            color=alt.Color("tier_label:N", title="Alert tier", scale=_tier_scale(mode)),
            shape=alt.Shape("tier_label:N", title="Alert tier", scale=_shape_scale())))
    lev = ev[ev["lake"] == lk.id]
    if start is not None:
        lev = lev[(lev["date"] >= start) & (lev["date"] <= end)]
    if len(lev):
        lev = lev.assign(label=lev["name"] + lev["verified"].map({True: "", False: " (date unverified)"}))
        layers.append(alt.Chart(lev).mark_rule(color=m["ink"], strokeDash=[5, 3], strokeWidth=1.2).encode(x="date:T"))
        layers.append(alt.Chart(lev).mark_text(align="left", baseline="top", dx=5, dy=20, fontSize=10.5,
                                               fontWeight=600, color=m["ink"]).encode(x="date:T", y=alt.value(0), text="label:N"))
    zoom = alt.selection_interval(bind="scales", encodings=["x"], zoom="wheel![event.shiftKey]")
    return alt.layer(*layers).add_params(zoom).properties(height=360)


def rule_panel(lk, field: str, title: str, fmt: str, watch: float, warn: float, mode: str, start=None, end=None):
    m = T.MODES[mode]
    al = lk.series.reset_index()[["date", field, "tier"]].dropna(subset=[field])
    al["season"] = al["date"].dt.year
    if start is not None:
        al = al[(al["date"] >= start) & (al["date"] <= end)]
    th = pd.DataFrame({"v": [watch, warn], "t": [f"Watch {format(watch, fmt)}", f"Warning {format(warn, fmt)}"],
                       "tier": ["watch", "warning"]})
    base = alt.Chart(al).encode(x=alt.X("date:T", title=None))
    line = base.mark_line(color=m["ink2"], strokeWidth=1).encode(y=alt.Y(f"{field}:Q", title=title,
                                                                         axis=alt.Axis(format=fmt)), detail="season:N")
    pts = base.mark_point(filled=True, size=16, color=m["ink2"]).encode(
        y=f"{field}:Q", tooltip=[alt.Tooltip("date:T"), alt.Tooltip(f"{field}:Q", format=fmt)])
    rules = alt.Chart(th).mark_rule(strokeDash=[4, 3]).encode(
        y="v:Q", color=alt.Color("tier:N", scale=alt.Scale(domain=["watch", "warning"],
                                 range=[T.tier_color(mode, "watch"), T.tier_color(mode, "warning")]), legend=None))
    labels = alt.Chart(th).mark_text(align="left", baseline="bottom", dx=4, dy=-2, fontSize=10).encode(
        y="v:Q", x=alt.value(0), text="t:N",
        color=alt.Color("tier:N", scale=alt.Scale(domain=["watch", "warning"],
                        range=[T.tier_color(mode, "watch"), T.tier_color(mode, "warning")]), legend=None))
    zoom = alt.selection_interval(bind="scales", encodings=["x"], zoom="wheel![event.shiftKey]")
    return alt.layer(rules, line, pts, labels).add_params(zoom).properties(height=200)


def seasonal(lk, mode: str) -> alt.Chart:
    m = T.MODES[mode]
    d = lk.series.reset_index()[["date", "area_km2"]].copy()
    d["year"] = d["date"].dt.year.astype(str)
    d["day"] = pd.to_datetime("2000-" + d["date"].dt.strftime("%m-%d"))
    latest = d["year"].max()
    d["current"] = d["year"].eq(latest)
    past = alt.Chart(d[~d["current"]]).mark_line(strokeWidth=1, opacity=0.55, point=alt.OverlayMarkDef(size=10)).encode(
        x=alt.X("day:T", title=None, axis=alt.Axis(format="%b")),
        y=alt.Y("area_km2:Q", title="Water area (km²)"),
        color=alt.Color("year:N", title="Season", scale=alt.Scale(scheme="greys" if mode == "light" else "blues")),
        tooltip=["year:N", alt.Tooltip("date:T"), alt.Tooltip("area_km2:Q", format=".3f")])
    cur = alt.Chart(d[d["current"]]).mark_line(strokeWidth=2.6, color=m["accent"], point=alt.OverlayMarkDef(size=30)).encode(
        x="day:T", y="area_km2:Q", tooltip=["year:N", alt.Tooltip("date:T"), alt.Tooltip("area_km2:Q", format=".3f")])
    return alt.layer(past, cur).properties(height=260, title=f"{latest} (bold) against earlier seasons")


def weather(df: pd.DataFrame, mode: str) -> alt.Chart:
    m = T.MODES[mode]
    base = alt.Chart(df).encode(x=alt.X("date:T", title=None, axis=alt.Axis(format="%a %d")))
    rng = base.mark_bar(size=8, cornerRadius=3, color=T.tier_color(mode, "warning"), opacity=0.75).encode(
        y=alt.Y("temperature_2m_min:Q", title="Air temperature (°C)"), y2="temperature_2m_max:Q",
        tooltip=[alt.Tooltip("date:T", title="Day"), alt.Tooltip("temperature_2m_max:Q", title="Max °C", format=".1f"),
                 alt.Tooltip("temperature_2m_min:Q", title="Min °C", format=".1f"),
                 alt.Tooltip("precipitation_sum:Q", title="Precip. mm", format=".1f"),
                 alt.Tooltip("freezing_level_max:Q", title="Freezing level m", format=",.0f")])
    zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=m["ink3"], strokeDash=[2, 2]).encode(y="y:Q")
    temp = alt.layer(zero, rng).properties(height=150)
    fl = base.mark_line(color=m["accent"], point=True).encode(
        y=alt.Y("freezing_level_max:Q", title="Freezing level (m)", scale=alt.Scale(zero=False)),
        tooltip=[alt.Tooltip("date:T"), alt.Tooltip("freezing_level_max:Q", title="m", format=",.0f")]
    ).properties(height=110)
    return alt.vconcat(temp, fl, spacing=6)


def alert_timeline(log: pd.DataFrame, mode: str) -> alt.Chart:
    d = log.copy()
    d["date"] = pd.to_datetime(d["date"])
    d["tier_label"] = d["tier"].map(T.TIER_LABEL)
    return alt.Chart(d).mark_point(filled=True, size=80).encode(
        x=alt.X("date:T", title=None), y=alt.Y("lake:N", title=None),
        color=alt.Color("tier_label:N", title="Tier", scale=_tier_scale(mode)),
        shape=alt.Shape("tier_label:N", title="Tier", scale=_shape_scale()),
        tooltip=["lake:N", alt.Tooltip("date:T"), "tier_label:N", alt.Tooltip("area_km2:Q", format=".3f"),
                 alt.Tooltip("growth_15d:Q", format="+.0%")]
    ).properties(height=max(120, 40 * d["lake"].nunique()))
