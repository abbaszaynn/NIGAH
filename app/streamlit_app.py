"""NIGAH dashboard: lakes, landslide susceptibility, field reports, alerts.

Run from the repo root:
    streamlit run app/streamlit_app.py

Reads only files in outputs/ and config/. Anything missing renders as an empty
state naming the script that produces it; the page never shows invented numbers.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path

import altair as alt
import pandas as pd
import pydeck as pdk
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import theme as T  # noqa: E402
from src.common import ALPHAEARTH_ATTRIBUTION, OUTPUTS, aois, events, settings  # noqa: E402
from src.lakes.anomaly import add_alerts, thresholds  # noqa: E402

st.set_page_config(page_title="NIGAH · GB hazard watch", page_icon=":material/landslide:",
                   layout="wide")
st.markdown(T.CSS, unsafe_allow_html=True)
alt.theme.register("nigah", enable=True)(T.altair_theme)

SENSOR_LABEL = {"s2": "Sentinel-2", "s1": "Sentinel-1", "landsat": "Landsat"}
REPORT_COLORS = {"rockfall": [120, 72, 40, 220], "road_block": [20, 33, 43, 220],
                 "flood_glof": [31, 111, 139, 230], "irrelevant": [150, 150, 150, 160],
                 "": [95, 107, 115, 200]}


# ---------- data ----------

def _mtime(p: Path) -> float:
    return p.stat().st_mtime if p.exists() else 0.0


@st.cache_data
def read_csv(path: str, mtime: float, **kw) -> pd.DataFrame | None:
    return pd.read_csv(path, **kw) if mtime else None


def csv(name: str, **kw) -> pd.DataFrame | None:
    p = OUTPUTS / name
    return read_csv(str(p), _mtime(p), **kw)


@st.cache_data
def lake_alerts(lake: str, mtime: float, th_key: str) -> pd.DataFrame | None:
    if not mtime:
        return None
    df = pd.read_csv(OUTPUTS / f"{lake}_area.csv", parse_dates=["date"])
    s2 = df[df["sensor"] == "s2"].sort_values("date").groupby("date").last()
    if s2.empty:
        return None
    return add_alerts(s2, json.loads(th_key))


def alerts_for(lake: str, th: dict) -> pd.DataFrame | None:
    p = OUTPUTS / f"{lake}_area.csv"
    return lake_alerts(lake, _mtime(p), json.dumps(th, sort_keys=True))


def lake_status(feat: dict, th: dict) -> dict:
    pr = feat["properties"]
    row = {"id": pr["id"], "name": pr["name"], "valley": pr.get("valley", ""),
           "verified": pr.get("verified", False), "drawn": feat["geometry"] is not None,
           "tier": "no_data", "date": None, "area": None, "growth": None, "z": None}
    if not row["drawn"]:
        return row
    a = alerts_for(pr["id"], th)
    if a is not None and len(a):
        last = a.iloc[-1]
        row.update(tier=last["tier"], date=a.index[-1].date(), area=last["area_km2"],
                   growth=last["growth_15d"], z=last["z"])
    return row


def fmt(x, spec: str, dash: str = "–") -> str:
    return dash if x is None or pd.isna(x) else format(x, spec)


# ---------- top bar ----------

th = thresholds()
features = aois()
lakes = [f for f in features.values() if f["properties"]["kind"] == "lake"]
statuses = [lake_status(f, th) for f in lakes]
last_obs = max((s["date"] for s in statuses if s["date"]), default=None)
tuned = "tuned" in th["source"]

st.markdown(f"""
<div class="nigah-bar">
  <div>
    <div class="nigah-mark"><span class="word">NIGAH</span><span class="urdu" lang="ur">نگاہ</span></div>
    <div class="nigah-sub">Glacial lake outburst and landslide early warning for Gilgit-Baltistan.
      Research prototype, not an official NDMA warning.</div>
  </div>
  <div class="nigah-meta">
    Latest clear satellite scene <b>{T.esc(last_obs or "none yet")}</b><br>
    Alert thresholds <b>{"tuned on " + settings()["backtest"]["tune_start"][:4] + "–" + settings()["backtest"]["tune_end"][:4] if tuned else "untuned defaults"}</b>
  </div>
</div>
""", unsafe_allow_html=True)


# ---------- status board ----------

def board_html(rows: list[dict]) -> str:
    body = []
    for r in rows:
        if not r["drawn"]:
            obs = '<span class="muted">AOI not drawn</span>'
        elif r["date"] is None:
            obs = '<span class="muted">No series yet</span>'
        else:
            obs = f'<span class="num">{T.esc(r["date"])}</span>'
        aoi_note = "Not drawn" if not r["drawn"] else ("Verified" if r["verified"] else "Approximate box")
        body.append(
            f"<tr><td class='name'>{T.esc(r['name'])}</td>"
            f"<td class='muted hide-sm'>{T.esc(r['valley'])}</td>"
            f"<td>{T.pill(r['tier'])}</td><td>{obs}</td>"
            f"<td class='r num'>{fmt(r['area'], '.3f')}</td>"
            f"<td class='r num'>{fmt(r['growth'], '+.0%')}</td>"
            f"<td class='r num hide-sm'>{fmt(r['z'], '.1f')}</td>"
            f"<td class='muted hide-sm'>{aoi_note}</td></tr>")
    head = ("<tr><th>Lake</th><th class='hide-sm'>Valley</th><th>Status</th><th>Last observation</th>"
            "<th class='r'>Area km²</th><th class='r'>15-day change</th>"
            "<th class='r hide-sm'>z-score</th><th class='hide-sm'>AOI</th></tr>")
    return f"<div class='board-wrap'><table class='board'>{head}{''.join(body)}</table></div>"


st.markdown(board_html(statuses), unsafe_allow_html=True)
st.markdown(
    f"<div class='caption'>Status is the alert tier of each lake's latest clear Sentinel-2 "
    f"observation. Thresholds from {T.esc(th['source'])}.</div>", unsafe_allow_html=True)

tab_map, tab_lakes, tab_bt, tab_ls, tab_rep, tab_log, tab_about = st.tabs([
    ":material/map: Map", ":material/water: Glacial lakes", ":material/history: Back-test",
    ":material/landslide: Landslide susceptibility", ":material/forum: Field reports",
    ":material/notifications: Alert log", ":material/info: Data & method"])


# ---------- map ----------

with tab_map:
    status_by_id = {s["id"]: s for s in statuses}
    polys = []
    for f in features.values():
        if f["geometry"] is None or f["geometry"]["type"] != "Polygon":
            continue
        pr = f["properties"]
        if pr["kind"] == "lake":
            s = status_by_id[pr["id"]]
            label, _, _, rgba = T.TIERS[s["tier"]]
            detail = f"{label} · last obs {s['date'] or 'none'}"
        else:
            rgba, detail = [20, 33, 43, 25], "Landslide susceptibility corridor"
        polys.append({"polygon": f["geometry"]["coordinates"][0], "name": pr["name"],
                      "detail": detail, "fill": rgba,
                      "line": [20, 33, 43, 200] if pr["kind"] == "lake" else [20, 33, 43, 120]})

    layers = []
    sus_png, sus_b = OUTPUTS / "susceptibility.png", OUTPUTS / "susceptibility_bounds.json"
    show_sus = sus_png.exists() and sus_b.exists()
    if show_sus:
        b = json.loads(sus_b.read_text())
        uri = "data:image/png;base64," + base64.b64encode(sus_png.read_bytes()).decode()
        layers.append(pdk.Layer("BitmapLayer", image=uri, opacity=0.8,
                                bounds=[b["west"], b["south"], b["east"], b["north"]]))
    layers.append(pdk.Layer("PolygonLayer", data=polys, get_polygon="polygon", get_fill_color="fill",
                            get_line_color="line", line_width_min_pixels=1.5, pickable=True))

    reports = csv("reports_triaged.csv")
    pins = pd.DataFrame()
    if reports is not None:
        pins = reports.dropna(subset=["lat", "lon"]).copy()
        pins["label"] = pins["label"].fillna("")
        pins["name"] = pins["title"].fillna("").str.slice(0, 90)
        pins["detail"] = pins["label"].replace("", "unclassified") + " · " + pins["places"].fillna("")
        pins["color"] = pins["label"].map(lambda l: REPORT_COLORS.get(l, REPORT_COLORS[""]))
        layers.append(pdk.Layer("ScatterplotLayer", data=pins[["lon", "lat", "name", "detail", "color"]],
                                get_position=["lon", "lat"], get_fill_color="color",
                                get_radius=350, radius_min_pixels=4, stroked=True,
                                get_line_color=[255, 255, 255], line_width_min_pixels=1,
                                pickable=True))

    deck = pdk.Deck(layers=layers, map_provider="carto", map_style=pdk.map_styles.CARTO_LIGHT,
                    initial_view_state=pdk.ViewState(latitude=36.36, longitude=74.72, zoom=9.2),
                    tooltip={"html": "<b>{name}</b><br/>{detail}",
                             "style": {"fontFamily": "IBM Plex Sans", "fontSize": "12px",
                                       "backgroundColor": T.INK, "color": "white"}})
    st.pydeck_chart(deck, height=560)

    items = [(T.TIERS[t][0], T.TIERS[t][1]) for t in ("alert", "warning", "watch", "normal", "no_data")]
    st.markdown(T.legend(items), unsafe_allow_html=True)
    parts = ["Lake boxes are coloured by alert tier and labelled in the tooltip."]
    parts.append("Susceptibility overlay: LightGBM probability, yellow (low) to red (high)."
                 if show_sus else "Susceptibility overlay appears after `python -m src.landslide.train`.")
    parts.append(f"{len(pins)} geolocated field reports shown." if reports is not None
                 else "Field-report pins appear after `python -m src.nlp.classify predict`.")
    unverified = [f["properties"]["name"] for f in features.values() if not f["properties"].get("verified")]
    if unverified:
        parts.append(f"Unverified AOIs: {', '.join(unverified)}. Boxes are approximate until "
                     "redrawn in the GEE Code Editor.")
    st.markdown(f"<div class='caption'>{T.esc(' '.join(parts))}</div>", unsafe_allow_html=True)


# ---------- lakes ----------

def lake_chart(lake: str, area: pd.DataFrame, al: pd.DataFrame | None, ev: pd.DataFrame) -> alt.Chart:
    d = area.copy()
    d["season"] = d["date"].dt.year
    d["sensor_label"] = d["sensor"].map(SENSOR_LABEL)
    if al is not None:
        d = d.merge(al[["tier", "z", "growth_15d"]].reset_index(), on="date", how="left")
        d.loc[d["sensor"] != "s2", ["tier", "z", "growth_15d"]] = None
    else:
        d["tier"] = d["z"] = d["growth_15d"] = None
    d["tier_label"] = d["tier"].map(lambda t: T.TIERS[t][0] if isinstance(t, str) else "")

    x = alt.X("date:T", title=None)
    y = alt.Y("area_km2:Q", title="Lake area (km²)")
    tip = [alt.Tooltip("date:T", title="Date"), alt.Tooltip("sensor_label:N", title="Sensor"),
           alt.Tooltip("area_km2:Q", title="Area km²", format=".3f"),
           alt.Tooltip("tier_label:N", title="Tier"),
           alt.Tooltip("growth_15d:Q", title="15-day change", format="+.0%"),
           alt.Tooltip("z:Q", title="z-score", format=".1f"),
           alt.Tooltip("valid_frac:Q", title="AOI clear", format=".0%")]
    zoom = alt.selection_interval(bind="scales", encodings=["x"])

    s2 = d[d["sensor"] == "s2"]
    layers = []
    bt = settings()["backtest"]
    band = pd.DataFrame({"start": [pd.Timestamp(bt["tune_start"])], "end": [pd.Timestamp(bt["tune_end"])],
                         "label": ["Tuning period"]})
    layers.append(alt.Chart(band).mark_rect(color=T.PANEL, opacity=0.7).encode(x="start:T", x2="end:T"))
    layers.append(alt.Chart(band).mark_text(align="left", baseline="top", dx=4, dy=4, color=T.INK_3,
                                            fontSize=10).encode(x="start:T", y=alt.value(0), text="label"))
    layers.append(alt.Chart(s2).mark_line(color=T.WATER, strokeWidth=1.4)
                  .encode(x=x, y=y, detail="season:N"))
    layers.append(alt.Chart(d).mark_point(filled=True, size=22, opacity=0.9).encode(
        x=x, y=y, tooltip=tip,
        shape=alt.Shape("sensor_label:N", title="Sensor",
                        scale=alt.Scale(domain=list(SENSOR_LABEL.values()),
                                        range=["circle", "triangle-up", "square"])),
        color=alt.value(T.WATER)).add_params(zoom))
    hits = d[d["tier"].isin(["watch", "warning", "alert"])]
    if len(hits):
        tiers = ["watch", "warning", "alert"]
        layers.append(alt.Chart(hits).mark_point(filled=True, size=70, stroke="white", strokeWidth=1)
                      .encode(x=x, y=y, tooltip=tip,
                              color=alt.Color("tier_label:N", title="Alert tier",
                                              scale=alt.Scale(domain=[T.TIERS[t][0] for t in tiers],
                                                              range=[T.TIERS[t][1] for t in tiers]))))
    lev = ev[ev["lake"] == lake]
    if len(lev):
        lev = lev.assign(label=lev["name"] + lev["verified"].map({True: "", False: " (date unverified)"}))
        layers.append(alt.Chart(lev).mark_rule(color=T.INK, strokeDash=[4, 3]).encode(x="date:T"))
        layers.append(alt.Chart(lev).mark_text(align="left", baseline="top", dx=4, dy=18, color=T.INK,
                                               fontSize=10, fontWeight=500)
                      .encode(x="date:T", y=alt.value(0), text="label:N"))
    return alt.layer(*layers).properties(height=340).resolve_scale(color="independent")


with tab_lakes:
    drawn = [s for s in statuses if s["drawn"]]
    names = {s["name"]: s["id"] for s in drawn}
    pick = st.selectbox("Lake", list(names), index=0, label_visibility="collapsed") if names else None
    lake = names.get(pick) if pick else None
    area = csv(f"{lake}_area.csv", parse_dates=["date"]) if lake else None

    if lake is None:
        st.markdown(T.empty_state("No lake AOIs drawn",
                                  "Draw lake polygons in the GEE Code Editor and paste them into "
                                  "config/aoi.geojson."), unsafe_allow_html=True)
    elif area is None or area.empty:
        st.markdown(T.empty_state(
            f"No area series for {pick} yet",
            "The lake-area pipeline has not been run for this AOI. It measures water area in every "
            "clear Apr–Oct Sentinel-2 scene (and Sentinel-1 for cloudy gaps).",
            f"python -m src.lakes.lake_area --lake {lake} --project YOUR_GEE_PROJECT"),
            unsafe_allow_html=True)
    else:
        al = alerts_for(lake, th)
        st.altair_chart(lake_chart(lake, area, al, events()), width="stretch")
        sensors = ", ".join(SENSOR_LABEL[s] for s in sorted(area["sensor"].unique()))
        st.markdown(
            f"<div class='caption'>Water area inside the AOI per clear scene. Source: {T.esc(sensors)} "
            f"via Google Earth Engine, {area['date'].min().date()} to {area['date'].max().date()}, "
            f"Apr–Oct only. Lines break between seasons. Drag on the chart to pan, scroll to zoom.</div>",
            unsafe_allow_html=True)

        left, right = st.columns([3, 2], gap="large")
        with left:
            st.markdown("### Recent observations")
            if al is not None:
                recent = al.tail(8).iloc[::-1].reset_index()
                recent["tier"] = recent["tier"].map(lambda t: T.TIERS[t][0])
                st.dataframe(recent[["date", "area_km2", "growth_15d", "z", "tier", "valid_frac"]],
                             hide_index=True, width="stretch", column_config={
                                 "date": st.column_config.DateColumn("Date"),
                                 "area_km2": st.column_config.NumberColumn("Area km²", format="%.3f"),
                                 "growth_15d": st.column_config.NumberColumn("15-day change", format="percent"),
                                 "z": st.column_config.NumberColumn("z-score", format="%.1f"),
                                 "tier": "Tier",
                                 "valid_frac": st.column_config.NumberColumn("AOI clear", format="percent")})
            else:
                st.markdown(T.empty_state("No Sentinel-2 observations",
                                          "Alerts run on the Sentinel-2 series only."), unsafe_allow_html=True)
        with right:
            st.markdown("### How tiers are set")
            st.markdown(f"""<div class="note">
<b>Watch</b>: z-score above {th['watch']['z']} or 15-day growth above {th['watch']['growth']:.0%}.<br>
<b>Warning</b>: z-score above {th['warning']['z']} or 15-day growth above {th['warning']['growth']:.0%}.<br>
<b>Alert</b>: both warning rules on one scene, or {th['consecutive_warnings']} warnings in a row.<br><br>
z-score compares area with the median of the previous 60 days. Source: {T.esc(th['source'])}.
</div>""", unsafe_allow_html=True)


# ---------- back-test ----------

RESULT = {"hit": ("Warning fired", "normal"), "miss": ("No warning", "alert"),
          "no_obs": ("No clear scenes", "no_data"), "no_data": ("No series", "no_data")}

with tab_bt:
    summ = csv("backtest_summary.csv")
    if summ is None:
        st.markdown(T.empty_state(
            "Back-test not run yet",
            "Tunes thresholds on 2019–2021 only, then checks whether a warning fired before each "
            "event in config/events.csv and how many days ahead.",
            "python -m src.lakes.backtest --tune"), unsafe_allow_html=True)
    else:
        rows = []
        for r in summ.itertuples():
            label, tier = RESULT.get(r.status, ("Unknown", "no_data"))
            _, fg, bg, _ = T.TIERS[tier]
            lead = "–" if pd.isna(r.lead_days) else f"{int(r.lead_days)} days"
            notes = r.notes if isinstance(r.notes, str) else ""
            notes = "; ".join(n.replace("**", "").replace("`", "") for n in notes.split("; ")
                              if not n.startswith("figure:"))
            rows.append(f"<tr><td class='name'>{T.esc(r.event)}</td><td class='num'>{T.esc(r.date)}</td>"
                        f"<td><span class='pill' style='color:{fg};background:{bg}'>{label}</span></td>"
                        f"<td class='r num'>{lead}</td><td class='r num hide-sm'>{r.obs_in_window}</td>"
                        f"<td class='muted hide-sm'>{T.esc(notes)}</td></tr>")
        st.markdown("<div class='board-wrap'><table class='board'><tr><th>Event</th><th>Date</th>"
                    "<th>Result</th><th class='r'>Lead time</th><th class='r hide-sm'>Scenes in window</th>"
                    "<th class='hide-sm'>Notes</th></tr>" + "".join(rows) + "</table></div>",
                    unsafe_allow_html=True)
        st.markdown(f"<div class='caption'>Lead time is days between the first warning-tier scene and the "
                    f"event, within a {settings()['backtest']['lead_window_days']}-day window. "
                    f"Computed by src/lakes/backtest.py.</div>", unsafe_allow_html=True)
        figs = sorted(OUTPUTS.glob("backtest_*.png"))
        if figs:
            cols = st.columns(2)
            for i, f in enumerate(figs):
                cols[i % 2].image(str(f), width="stretch")
        rep = OUTPUTS / "backtest_report.md"
        if rep.exists():
            with st.expander("Full back-test report"):
                st.markdown(rep.read_text(encoding="utf-8"))


# ---------- landslide ----------

with tab_ls:
    auc = csv("landslide_auc.csv")
    if auc is None:
        st.markdown(T.empty_state(
            "Susceptibility model not trained yet",
            "Needs 150–300 landslide points in config/landslide_points.csv (NASA Global Landslide "
            "Catalog plus digitized scars). Then build features in Earth Engine and train LightGBM "
            "with spatial block cross-validation.",
            "python -m src.landslide.features --project YOUR_GEE_PROJECT\npython -m src.landslide.train"),
            unsafe_allow_html=True)
    else:
        left, right = st.columns([2, 3], gap="large")
        with left:
            st.markdown("### Spatial cross-validation AUC")
            st.dataframe(auc[["feature_set", "auc_oof", "auc_fold_mean", "auc_fold_std", "folds_scored",
                              "n_features"]], hide_index=True, width="stretch", column_config={
                "feature_set": "Features", "auc_oof": st.column_config.NumberColumn("AUC (out-of-fold)", format="%.3f"),
                "auc_fold_mean": st.column_config.NumberColumn("Fold mean", format="%.3f"),
                "auc_fold_std": st.column_config.NumberColumn("Fold sd", format="%.3f"),
                "folds_scored": "Folds", "n_features": "Inputs"})
            st.markdown(f"<div class='caption'>{T.esc(auc['cv'].iloc[0])}. Whole spatial blocks are held "
                        "out together; no random splits.</div>", unsafe_allow_html=True)
        with right:
            shap_png = OUTPUTS / "landslide_shap.png"
            if shap_png.exists():
                st.markdown("### What drives the model")
                st.image(str(shap_png), width="stretch")
        if (OUTPUTS / "susceptibility.png").exists():
            st.markdown("<div class='caption'>The susceptibility map is overlaid on the Map tab.</div>",
                        unsafe_allow_html=True)


# ---------- reports ----------

with tab_rep:
    if reports is None:
        raw = csv("reports_raw.csv")
        if raw is None:
            st.markdown(T.empty_state(
                "No field reports collected yet",
                "Collects GB news from free RSS feeds (Pamir Times, Dawn), keeps items that mention "
                "GB places or hazards, then tags each with a class and a location.",
                "python -m src.nlp.scrape\npython -m src.nlp.classify predict"), unsafe_allow_html=True)
        else:
            st.markdown(T.empty_state(f"{len(raw)} reports collected, not triaged",
                                      "Run the classifier to tag and geolocate them.",
                                      "python -m src.nlp.classify predict"), unsafe_allow_html=True)
    else:
        labels = settings()["nlp"]["labels"]
        have_model = reports["label"].fillna("").ne("").any()
        if not have_model:
            st.markdown("<div class='note'>No trained classifier yet, so reports are unclassified. "
                        "Places are matched from config/gazetteer.csv.</div>", unsafe_allow_html=True)
            shown = reports
        else:
            sel = st.pills("Class", labels, selection_mode="multi",
                           default=[l for l in labels if l != "irrelevant"], label_visibility="collapsed")
            shown = reports[reports["label"].isin(sel or labels)]
        shown = shown.sort_values("published", ascending=False)
        st.dataframe(shown[["published", "label", "confidence", "title", "places", "source", "link"]],
                     hide_index=True, width="stretch", height=460, column_config={
                         "published": st.column_config.DatetimeColumn("Published", format="YYYY-MM-DD"),
                         "label": "Class", "confidence": st.column_config.NumberColumn("Conf.", format="%.2f"),
                         "title": st.column_config.TextColumn("Headline", width="large"),
                         "places": "Places", "source": "Source",
                         "link": st.column_config.LinkColumn("Link", display_text="Open")})
        f1 = csv("nlp_f1.csv", index_col=0)
        if f1 is not None:
            st.markdown("### Classifier on held-out set")
            st.dataframe(f1.loc[[l for l in labels if l in f1.index], ["precision", "recall", "f1-score", "support"]],
                         width="stretch")


# ---------- alert log ----------

with tab_log:
    log = csv("alert_log.csv")
    if log is None or log.empty:
        st.markdown(T.empty_state(
            "No alerts logged",
            "The weekly job refreshes recent scenes, recomputes tiers and logs every Watch, Warning "
            "or Alert observation here. New ones are sent to Telegram.",
            "python -m src.alerts.check --project YOUR_GEE_PROJECT"), unsafe_allow_html=True)
    else:
        log = log.sort_values("date", ascending=False).copy()
        log["tier"] = log["tier"].map(lambda t: T.TIERS.get(t, T.TIERS["no_data"])[0])
        st.dataframe(log[["date", "lake", "tier", "area_km2", "growth_15d", "z", "sent", "logged_at"]],
                     hide_index=True, width="stretch", column_config={
                         "date": "Scene date", "lake": "Lake", "tier": "Tier",
                         "area_km2": st.column_config.NumberColumn("Area km²", format="%.3f"),
                         "growth_15d": st.column_config.NumberColumn("15-day change", format="percent"),
                         "z": st.column_config.NumberColumn("z-score", format="%.1f"),
                         "sent": st.column_config.CheckboxColumn("Telegram sent"),
                         "logged_at": "Logged (UTC)"})


# ---------- about ----------

with tab_about:
    st.markdown(f"""
### Data
- Lake area: Sentinel-2 L1C (`COPERNICUS/S2_HARMONIZED`) with Cloud Score+ masking; Sentinel-1 GRD
  VV backscatter for cloudy gaps; Landsat 5/7/8/9 Collection 2 for pre-2016 history.
- Terrain: Copernicus GLO-30 DEM. Rainfall: CHIRPS daily. Drainage: HydroSHEDS.
- Embeddings: AlphaEarth annual satellite embeddings (2017 onwards, 64 bands, 10 m).
- Reports: public RSS feeds. Labels: hand-corrected.

### Rules this dashboard follows
- Every number on this page was computed by code in the NIGAH repository from the files in `outputs/`.
  Missing outputs are shown as empty, never filled with sample values.
- Alert thresholds are tuned on {settings()['backtest']['tune_start'][:4]}–{settings()['backtest']['tune_end'][:4]}
  only and tested on later events.
- Attabad 2010 predates Sentinel-2 and AlphaEarth, so it is a Landsat-only partial analysis.

### Known limits
- Ice-covered lakes read as dry in spring; turbid water lowers MNDWI; terrain shadow is masked
  but steep valleys still lose pixels.
- Sentinel-1 also reads wet snow and radar shadow as water, so it fills gaps but does not drive alerts.
- AlphaEarth is annual: it informs susceptibility, not real-time warning.
""")
    st.markdown(f"<div class='caption'>{T.esc(ALPHAEARTH_ATTRIBUTION)} Built by Zain Abbas.</div>",
                unsafe_allow_html=True)
