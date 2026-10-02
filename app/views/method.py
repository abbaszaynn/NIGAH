"""Data & method: sources, rules, limits, attribution."""

from __future__ import annotations

import streamlit as st

from app import data
from app import theme as T
from src.common import ALPHAEARTH_ATTRIBUTION, OUTPUTS, settings


def render():
    c = data.ctx()
    bt = settings()["backtest"]
    st.markdown(T.page_header("Data & method", "How every number on this dashboard is produced"),
                unsafe_allow_html=True)
    left, right = st.columns([1.3, 1], gap="large")
    with left:
        st.markdown(f"""
### Detection
- **Lake area**: Sentinel-2 L1C (`COPERNICUS/S2_HARMONIZED`), Apr–Oct. Water where MNDWI(B3, B11) > threshold,
  slope < 10°, not in terrain shadow, Cloud Score+ `cs_cdf` ≥ 0.6. A scene counts only if ≥ 80% of the AOI is usable.
- **Gap-fill**: Sentinel-1 GRD VV backscatter below −18 dB. Wet snow and radar shadow also read dark, so radar
  never drives an alert.
- **History**: Landsat 5/7/8/9 Collection 2 for pre-2016 events (Attabad 2010 is a partial, Landsat-only analysis).

### Alert rules
- **z-score**: area against the median and MAD of the previous 60 days (needs ≥ 3 earlier scenes).
- **15-day change**: relative change since the previous scene, scaled to 15 days (not computed across gaps > 45 days).
- Thresholds tuned on {bt['tune_start'][:4]}–{bt['tune_end'][:4]} only and tested on later events.
  Active source: {c.th['source']}.
- An alert stays in force for {data.ACTIVE_DAYS} days after its scene date. In season, a lake with no clear scene
  for {data.STALE_DAYS} days is shown as **Data stale**, never as normal.
- A series that fails quality checks (e.g. area stuck at a ceiling) is shown as **QA failed** and cannot issue alerts.

### Messages
- OASIS **CAP 1.2** XML per alert, status *Exercise* until the protocol is agreed with GBDMA/NDMA.
- Bulletin text in English and Urdu; Telegram delivery from the weekly GitHub Actions job.
""")
    with right:
        st.markdown("""
### Risk knowledge
- Landslide susceptibility: LightGBM on terrain, hydrology, NDVI, CHIRPS rainfall and AlphaEarth embeddings,
  validated with spatial block cross-validation.

### Field reports
- Public RSS news (Pamir Times, Dawn), Urdu and English, triaged by fine-tuned XLM-R into rockfall, road block,
  flood/GLOF or irrelevant; places matched to a GB gazetteer.

### Context
- Weather: Open-Meteo 7-day forecast (temperature, precipitation, freezing level). Context only.
- Basemaps: Esri World Imagery, OpenTopoMap, CARTO.

### Honesty rules
- Every number is computed by code in this repository from files in `outputs/`.
- Missing outputs show as empty states naming the command that produces them, never sample values.
- AOIs and event dates marked unverified are flagged wherever they are used.
""")
        reports = sorted(p.name for p in OUTPUTS.glob("backtest_report.md"))
        if reports:
            with st.expander("Back-test report"):
                st.markdown((OUTPUTS / reports[0]).read_text(encoding="utf-8"))
    st.markdown(f"<div class='caption'>{T.esc(ALPHAEARTH_ATTRIBUTION)} Weather data by Open-Meteo.com (CC BY 4.0). "
                "NIGAH is a research prototype by Zain Abbas and does not issue official warnings.</div>",
                unsafe_allow_html=True)
