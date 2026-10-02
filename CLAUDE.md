# NIGAH: GLOF and landslide early warning for Gilgit-Baltistan

Context for Claude Code. Read this first in every session.

## Goal

A free, open prototype that:

1. Tracks glacial lake area from satellites and flags dangerous growth (GLOF).
2. Maps landslide susceptibility along a Karakoram Highway (KKH) segment.
3. Triages Urdu/English local reports of rockfall, road blocks and floods.
4. Shows all three on one dashboard and sends alerts.

Built by Zain Abbas for an NDMA AI/ML application. Everything must stay free: no paid APIs, no paid cloud.

## Honesty rules for this project

- Never report a metric that was not computed by code in this repo.
- Tune thresholds on early years, test on later years. Never tune on the test event.
- Say clearly where data is missing (e.g. Attabad 2010 predates Sentinel-2 and AlphaEarth).
- The dashboard never shows placeholder or synthetic numbers. Missing outputs render as an empty state that says which script produces them.

## Free stack

- Google Earth Engine (noncommercial project) via `earthengine-api`, plus `geemap`
- Sentinel-2 L1C `COPERNICUS/S2_HARMONIZED`, cloud mask `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED`
- Sentinel-1 SAR `COPERNICUS/S1_GRD` (cloudy months)
- Landsat 5/7/8/9 Collection 2 (pre-2016 history)
- DEM `COPERNICUS/DEM/GLO30`
- Rainfall `UCSB-CHG/CHIRPS/DAILY`
- AlphaEarth embeddings `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL` (annual, 2017+, 64 bands, 10 m)
- Labels: ICIMOD glacial lake inventory, NASA Global Landslide Catalog, own digitizing
- Python: pandas, scikit-learn, lightgbm, shap, matplotlib, transformers
- Dashboard: Streamlit Community Cloud. Alerts: Telegram bot. Schedule: GitHub Actions cron

## Repo layout

```
nigah/
  CLAUDE.md
  requirements.txt
  config/aoi.geojson          # lake + KKH polygons (verified in GEE Code Editor)
  config/events.csv           # known events: name, date, type, source URL
  config/settings.toml        # thresholds, date ranges, tuning/test split
  config/gazetteer.csv        # GB place names for report geolocation
  src/common.py               # config loading, paths, GEE init
  src/lakes/lake_area.py      # S2 (+S1) lake-area time series
  src/lakes/anomaly.py        # anomaly + growth-rate alert rules
  src/lakes/backtest.py       # lead time vs known events
  src/lakes/qa.py             # series quality checks; QA-failed lakes cannot alert
  src/landslide/features.py   # DEM, rainfall, NDVI, AlphaEarth stack
  src/landslide/train.py      # LightGBM + spatial CV + SHAP
  src/nlp/scrape.py           # RSS/news collection
  src/nlp/classify.py         # XLM-R triage + place extraction
  src/alerts/telegram.py
  src/alerts/cap.py           # tier protocol + OASIS CAP 1.2 messages, EN/UR bulletins
  src/alerts/check.py         # weekly refresh -> tiers -> alert log -> Telegram
  app/streamlit_app.py        # entry: top nav, sidebar clock/status, auto-refresh
  app/theme.py                # dark "control room" + light "daylight" tokens, CSS, components
  app/data.py                 # loaders, lake status, freshness, health checks, Open-Meteo weather
  app/maps.py, app/charts.py  # folium operational map, Altair charts
  app/views/                  # Situation room, Lake monitor, Alerts & bulletins, Landslide risk,
                              # Field reports, System health, Data & method
  outputs/                    # csv, png, reports (gitignored except final figures)
  .github/workflows/weekly.yml
```

Run every script from the repo root as a module, e.g. `python -m src.lakes.lake_area --lake shisper`.

## Phases

### Phase 0: setup (1-2 days)

- [x] Create GEE Cloud project, register for noncommercial use, `earthengine authenticate` (project vocal-oarlock-472219-q6, 2026-10-02)
- [x] Create repo, venv, requirements.txt
- [ ] Draw AOIs in GEE Code Editor: Shisper lake, Khurdopin/Shimshal, Badswat, KKH Hunza-Attabad segment. Export to config/aoi.geojson (set `"verified": true` per feature once checked)
- [ ] Fill config/events.csv with dated events and a source link for each (set `verified` to true once sourced)

Done when: `python -c "import ee; ee.Initialize(project='...')"` works and AOIs are verified on imagery.

### Phase 1: lake monitoring (weeks 2-3)

- [ ] Sentinel-2 L1C, months Apr-Oct, Cloud Score+ mask (cs_cdf >= 0.6)
- [ ] Water = MNDWI(B3,B11) > threshold AND slope < 10 deg AND not in terrain shadow
- [ ] Keep scenes where >= 80% of AOI is clear; one scene per date
- [ ] Add Sentinel-1 water (VV backscatter below threshold) for cloudy gaps
- [ ] Output outputs/<lake>_area.csv and a time-series plot

Known pitfalls: frozen or ice-covered lake reads as non-water in spring; turbid water can lower MNDWI; mountain shadow reads as water without the shadow mask.
Done when: area series for Shisper looks physically sensible (lake fills, then drops at outbursts).
Status 2026-10-02: first real Shisper run (2016-2026) FAILS this check. The series sits at ~0.092 km² in 37% of
scenes = the flat (<10°) area inside the approximate box; MNDWI marks 12.6 of 13.4 km² as water in April (snow/ice).
Next: redraw the AOI on the lake basin, add a snow/ice exclusion (e.g. NIR B8 < 0.15), and reconsider the slope
mask (GLO30 predates the lake). Attabad 2026 looks plausible (1.6 -> 2.7 -> 1.9 km²).

### Phase 2: back-test (week 4)

- [x] Alert rules: robust z-score vs prior 60-day baseline, and 15-day growth rate
      (growth compares with the latest scene >= 10 days earlier; never scaled up, which amplified noise)
- [ ] Tune thresholds on 2019-2021 seasons only
- [ ] Test on Shisper May 2022: did a warning fire before the outburst, and how many days ahead
- [ ] Repeat for Badswat 2018
- [ ] Attabad 2010: Landsat-only partial analysis, labelled as partial
- [ ] Report: lead time, false alerts per season, one figure per event

Done when: outputs/backtest_report.md exists with numbers produced by code.

### Phase 3: landslide susceptibility (weeks 5-6)

- [ ] Positives: 150-300 landslide points (catalog + digitized scars). Negatives: random stable points, 1:1 to 1:3
- [ ] Features: slope, aspect, curvature, elevation, distance to drainage/road/faults, NDVI, CHIRPS rainfall, lithology (if digitized), AlphaEarth 64 bands
- [ ] LightGBM with spatial block cross-validation (no random splits)
- [ ] Compare AUC: terrain-only vs terrain + AlphaEarth
- [ ] SHAP summary plot; export susceptibility GeoTIFF

Done when: map + AUC table + SHAP figure in outputs/.

### Phase 4: NLP triage (week 7)

- [ ] Collect GB news/RSS (Pamir Times, Dawn, local pages). No paid X API
- [ ] Label 500-1000 items: rockfall / road_block / flood_glof / irrelevant (LLM pre-label, human correct)
- [ ] Fine-tune XLM-R (reuse thesis code); report per-class F1 on held-out set
- [ ] Place-name extraction with a GB gazetteer

Done when: classifier + confusion matrix + 20 example predictions.

### Phase 5: dashboard and alerts (week 8)

- [x] Streamlit: map (lakes, susceptibility, report pins), lake-area charts, alert log (UI built; fills as outputs appear)
- [x] Alert tiers: watch / warning / alert; Telegram bot message (code written; needs bot token)
- [x] GitHub Actions weekly job reruns lake check (workflow written; needs secrets)

Done when: public demo URL + one test alert received on phone.

## AlphaEarth usage notes

- Use for susceptibility features, year-over-year change, and similarity search for lakes like Shisper.
- Not for real-time warning: it is annual.
- Custom Satellite Embeddings (higher frequency) academic program: apply by 15 Oct 2026.
- Attribution required: "The AlphaEarth Foundations Satellite Embedding dataset is produced by Google and Google DeepMind."

## Conventions

- Every script takes config from config/ and writes to outputs/
- Every figure has a caption stating data source and date range
- Commit after each phase with a short results note
- Dashboard design rules live in app/theme.py and DESIGN.md: tier colour is always paired with a text label, numbers use tabular figures, no emoji as icons.
