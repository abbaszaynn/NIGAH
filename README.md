# NIGAH (نگاہ)

Free, open GLOF and landslide early-warning prototype for Gilgit-Baltistan:
satellite lake-area monitoring, KKH landslide susceptibility, Urdu/English report triage,
one dashboard and Telegram alerts. Project plan and rules: [CLAUDE.md](CLAUDE.md).

## Quick start

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # Windows; use .venv/bin on Linux/macOS
earthengine authenticate
```

```bash
# Phase 1-2: lake area, alert tiers, back-test
python -m src.lakes.lake_area --lake shisper --project YOUR_GEE_PROJECT
python -m src.lakes.anomaly --lake shisper
python -m src.lakes.backtest --tune

# Phase 3: landslide susceptibility (needs config/landslide_points.csv)
python -m src.landslide.features --project YOUR_GEE_PROJECT
python -m src.landslide.train

# Phase 4: reports
python -m src.nlp.scrape
python -m src.nlp.classify predict

# Phase 5: dashboard and alerts
streamlit run app/streamlit_app.py
python -m src.alerts.telegram --test
python -m src.alerts.check --project YOUR_GEE_PROJECT
```

Before trusting any number: draw and verify the AOIs in `config/aoi.geojson`, and add a
source link and `verified=true` for each event in `config/events.csv`.

The AlphaEarth Foundations Satellite Embedding dataset is produced by Google and Google DeepMind.
