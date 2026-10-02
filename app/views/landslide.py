"""Landslide susceptibility along the KKH: model skill, drivers, map."""

from __future__ import annotations

import streamlit as st
from streamlit_folium import st_folium

from app import data, maps
from app import theme as T
from src.common import CONFIG, OUTPUTS, settings

FEATURES = [
    ("Terrain", "Elevation, slope, aspect (sin/cos), curvature", "Copernicus GLO-30 DEM"),
    ("Hydrology", "Distance to drainage", "HydroSHEDS flow accumulation"),
    ("Vegetation", "NDVI, Jun–Sep median", "Sentinel-2"),
    ("Rainfall", "Mean annual precipitation", "CHIRPS daily"),
    ("Infrastructure", "Distance to KKH", "config/kkh_line.geojson (optional)"),
    ("Geology", "Distance to faults", "config/faults.geojson (optional)"),
    ("Embeddings", "64 AlphaEarth bands", "Google Satellite Embedding V1, annual"),
]


def render():
    c = data.ctx()
    cfg = settings()["landslide"]
    st.markdown(T.page_header("Landslide susceptibility", "KKH Hunza–Attabad corridor · LightGBM with spatial "
                              "block cross-validation"), unsafe_allow_html=True)
    auc = data.csv("landslide_auc.csv")
    samples = data.csv("landslide_samples.csv")
    pts = CONFIG / "landslide_points.csv"

    st.markdown(T.kpis([
        {"label": "Landslide points", "icon": "landslide",
         "value": str(int(samples["label"].sum())) if samples is not None else "–",
         "sub": "target 150–300" if samples is not None else ("points file present" if pts.exists() else "points file missing"),
         "bad": samples is None},
        {"label": "Best spatial-CV AUC", "icon": "insights",
         "value": f"{auc['auc_oof'].max():.3f}" if auc is not None else "–",
         "sub": auc.sort_values("auc_oof").iloc[-1]["feature_set"] if auc is not None else "model not trained"},
        {"label": "CV blocks", "icon": "grid_view", "value": f"{cfg['block_size_km']} km",
         "sub": f"{cfg['n_folds']} folds, whole blocks held out"},
        {"label": "AlphaEarth year", "icon": "public", "value": str(cfg["alphaearth_year"]), "sub": "annual embedding"},
    ]), unsafe_allow_html=True)

    left, right = st.columns([2, 1], gap="medium")
    with left:
        st.markdown(T.section("Susceptibility map", "toggle layers top right"), unsafe_allow_html=True)
        st_folium(maps.build(c, height=500, layers=("corridor", "susceptibility", "places", "lakes"), basemap="Terrain"),
                  height=500, use_container_width=True, returned_objects=[], key="ls_map")
        if not (OUTPUTS / "susceptibility.png").exists():
            st.markdown("<div class='caption'>No susceptibility layer yet: it appears after training. The dashed "
                        "outline is the modelled corridor.</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='caption'>Overlay: LightGBM probability of a mapped landslide, yellow (low) to red "
                        "(high), ~60 m grid.</div>", unsafe_allow_html=True)
    with right:
        st.markdown(T.section("Model skill"), unsafe_allow_html=True)
        if auc is None:
            st.markdown(T.empty_state("Model not trained yet",
                                      "Add 150–300 landslide points to config/landslide_points.csv (NASA Global "
                                      "Landslide Catalog plus digitized scars), build features in Earth Engine, "
                                      "then train.",
                                      "python -m src.landslide.features\npython -m src.landslide.train"),
                        unsafe_allow_html=True)
        else:
            st.dataframe(auc[["feature_set", "auc_oof", "auc_fold_mean", "auc_fold_std", "n_features"]],
                         hide_index=True, width="stretch", column_config={
                             "feature_set": "Features", "auc_oof": st.column_config.NumberColumn("AUC", format="%.3f"),
                             "auc_fold_mean": st.column_config.NumberColumn("Fold mean", format="%.3f"),
                             "auc_fold_std": st.column_config.NumberColumn("Fold sd", format="%.3f"),
                             "n_features": "Inputs"})
            st.markdown(f"<div class='caption'>{T.esc(auc['cv'].iloc[0])}. Out-of-fold AUC; no random splits.</div>",
                        unsafe_allow_html=True)
        st.markdown(T.section("Inputs"), unsafe_allow_html=True)
        rows = "".join(f"<tr><td><b>{a}</b></td><td>{b}<br><span class='mu'>{s}</span></td></tr>" for a, b, s in FEATURES)
        st.markdown(f"<div class='tbl-wrap'><table class='tbl'>{rows}</table></div>", unsafe_allow_html=True)

    shap_png = OUTPUTS / "landslide_shap.png"
    if shap_png.exists():
        st.markdown(T.section("What drives the model", "SHAP values"), unsafe_allow_html=True)
        st.image(str(shap_png), width="stretch")
