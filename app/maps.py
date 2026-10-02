"""Folium operational map: basemap switcher, toggleable hazard layers, fullscreen, measuring."""

from __future__ import annotations

import base64
import json

import folium
import pandas as pd
from folium import plugins

from app import theme as T
from app.data import Ctx
from src.common import CONFIG, OUTPUTS

ESRI_IMAGERY = ("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community")
ESRI_LABELS = ("https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/"
               "MapServer/tile/{z}/{y}/{x}", "Labels © Esri")
OPENTOPO = ("https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
            "Map data © OpenStreetMap contributors, SRTM | Style © OpenTopoMap (CC-BY-SA)")
REPORT_ICON = {"rockfall": "terrain", "road_block": "block", "flood_glof": "flood", "irrelevant": "remove",
               "": "chat"}


def _popup(lk) -> str:
    rows = [("Status", T.TIER_LABEL[lk.tier]), ("Valley", lk.valley)]
    if lk.date is not None:
        rows += [("Latest scene", f"{lk.date.date()} ({lk.age_days} d ago)"),
                 ("Water area", f"{lk.area:.3f} km²")]
        if lk.growth is not None and lk.growth == lk.growth:
            rows.append(("15-day change", f"{lk.growth:+.0%}"))
    if lk.downstream:
        rows.append(("Downstream", ", ".join(lk.downstream)))
    rows.append(("AOI", "verified" if lk.verified else "approximate, unverified"))
    body = "".join(f"<tr><td style='color:#666;padding-right:8px'>{T.esc(k)}</td><td><b>{T.esc(v)}</b></td></tr>"
                   for k, v in rows)
    return f"<div style='font-family:IBM Plex Sans,sans-serif;font-size:12px'><b>{T.esc(lk.name)}</b><table>{body}</table></div>"


def build(c: Ctx, height: int = 560, focus: str | None = None, layers: tuple = ("lakes", "corridor",
          "susceptibility", "reports", "places"), basemap: str = "Satellite") -> folium.Map:
    m = folium.Map(location=[36.36, 74.72], zoom_start=10, tiles=None, control_scale=True,
                   prefer_canvas=True, height=height)
    bases = {
        "Satellite": folium.TileLayer(ESRI_IMAGERY[0], attr=ESRI_IMAGERY[1], name="Satellite (Esri)"),
        "Terrain": folium.TileLayer(OPENTOPO[0], attr=OPENTOPO[1], name="Terrain (OpenTopoMap)", max_zoom=17),
        "Streets": folium.TileLayer(
            f"https://{{s}}.basemaps.cartocdn.com/{'dark_all' if c.mode == 'dark' else 'light_all'}/{{z}}/{{x}}/{{y}}{{r}}.png",
            attr="© OpenStreetMap contributors © CARTO", name="Streets (CARTO)", subdomains="abcd", max_zoom=20),
    }
    # Leaflet shows the last base layer added, so add the default last
    for name in [b for b in bases if b != basemap] + [basemap]:
        bases[name].add_to(m)
    folium.TileLayer(ESRI_LABELS[0], attr=ESRI_LABELS[1], name="Place labels", overlay=True,
                     show=basemap == "Satellite").add_to(m)

    if "susceptibility" in layers:
        png, bj = OUTPUTS / "susceptibility.png", OUTPUTS / "susceptibility_bounds.json"
        if png.exists() and bj.exists():
            b = json.loads(bj.read_text())
            uri = "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode()
            folium.raster_layers.ImageOverlay(uri, bounds=[[b["south"], b["west"]], [b["north"], b["east"]]],
                                              opacity=0.7, name="Landslide susceptibility").add_to(m)

    if "corridor" in layers:
        fg = folium.FeatureGroup(name="KKH corridor (landslide AOI)")
        for f in c.features.values():
            if f["properties"]["kind"] == "corridor" and f["geometry"]:
                folium.GeoJson(f, style_function=lambda _: {"color": "#E6EDF2" if c.mode == "dark" else "#14212B",
                                                            "weight": 1.5, "dashArray": "6 4", "fillOpacity": 0},
                               tooltip=f["properties"]["name"]).add_to(fg)
        fg.add_to(m)

    if "lakes" in layers:
        fg = folium.FeatureGroup(name="Glacial lakes (alert status)")
        for lk in c.lakes:
            if not lk.drawn:
                continue
            col = T.tier_color(c.mode, lk.tier)
            folium.GeoJson(lk.feature, style_function=lambda _, col=col: {
                "color": col, "weight": 3, "fillColor": col, "fillOpacity": 0.22},
                tooltip=f"{lk.name}: {T.TIER_LABEL[lk.tier]}",
                popup=folium.Popup(_popup(lk), max_width=280)).add_to(fg)
            lat, lon = lk.centroid
            folium.Marker([lat, lon], icon=folium.DivIcon(
                icon_size=(160, 20), icon_anchor=(-10, 10),
                html=f"<div style='font:600 11px IBM Plex Sans,sans-serif;color:#fff;"
                     f"text-shadow:0 0 3px #000,0 0 6px #000;white-space:nowrap'>{T.esc(lk.name)} · "
                     f"{T.esc(T.TIER_LABEL[lk.tier])}</div>")).add_to(fg)
        fg.add_to(m)

    if "places" in layers:
        fg = folium.FeatureGroup(name="Settlements (gazetteer)", show=False)
        gz = pd.read_csv(CONFIG / "gazetteer.csv")
        for r in gz.itertuples():
            folium.CircleMarker([r.lat, r.lon], radius=3, color="#E6EDF2", weight=1, fill=True,
                                fill_opacity=0.9, tooltip=f"{r.name} ({r.district})").add_to(fg)
        fg.add_to(m)

    if "reports" in layers and c.reports is not None:
        fg = folium.FeatureGroup(name="Field reports")
        pins = c.reports.dropna(subset=["lat", "lon"])
        for r in pins.itertuples():
            label = r.label if isinstance(r.label, str) else ""
            when = r.published.strftime("%Y-%m-%d") if pd.notna(r.published) else "date unknown"
            folium.CircleMarker([r.lat, r.lon], radius=6, color="#ffffff", weight=1.5, fill=True,
                                fill_color="#4FB3D9", fill_opacity=0.95,
                                tooltip=f"{label or 'unclassified'} · {when}",
                                popup=folium.Popup(f"<b>{T.esc(r.title)}</b><br>{T.esc(r.places)}<br>"
                                                   f"<a href='{T.esc(r.link)}' target='_blank'>source</a>",
                                                   max_width=280)).add_to(fg)
        fg.add_to(m)

    if focus:
        lk = next((l for l in c.lakes if l.id == focus and l.drawn), None)
        if lk:
            ring = lk.feature["geometry"]["coordinates"][0]
            lats, lons = [p[1] for p in ring], [p[0] for p in ring]
            m.fit_bounds([[min(lats) - 0.02, min(lons) - 0.03], [max(lats) + 0.02, max(lons) + 0.03]])

    folium.LayerControl(collapsed=True, position="topright").add_to(m)
    plugins.Fullscreen(position="topleft").add_to(m)
    plugins.MousePosition(position="bottomleft", separator=" , ", num_digits=4, prefix="Lat, Lon:").add_to(m)
    plugins.MeasureControl(position="bottomleft", primary_length_unit="kilometers",
                           primary_area_unit="sqkilometers").add_to(m)
    return m
