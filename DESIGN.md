# NIGAH dashboard design

Mode: **Operate**. Users: NDMA/GBDMA duty officers in an operations room (wall display or desk)
and field staff on phones. They must see in seconds what is in force, where, and how fresh the evidence is.

## Structure (top navigation)
| Page | Answers |
|---|---|
| Situation room | What is in force now? Threat banner, KPI strip, operational map, alerts in force, data-quality blockers, weather outlook, lake status board, activity feed |
| Lake monitor | Why is a lake in this state? Area vs 60-day normal range, z-score and growth rule panels, season comparison, observations, focused map |
| Alerts & bulletins | What do we send? Warning matrix (tier → trigger → CAP fields → action, EN/UR), CAP 1.2 XML, history, channels |
| Landslide risk | Where along the KKH? Susceptibility map, spatial-CV AUC, inputs, SHAP |
| Field reports | What are people reporting? Triaged news on map and table |
| System health | Is the warning chain working? MHEWS four pillars, pipeline freshness, configuration and data-quality checks |
| Data & method | How is every number made? |

## Standards followed
- **OASIS CAP 1.2** for alert messages (status `Exercise` until the protocol is agreed with GBDMA/NDMA).
- **UN Early Warnings for All / WMO MHEWS** four pillars as the System health frame.
- Graded tiers (Watch / Warning / Alert) with a published trigger and suggested action per tier.
- Degraded states are first-class: **QA failed**, **Data stale**, **Off season**, **No data**. A lake without
  trustworthy data is never shown as Normal, and the banner says "absence of an alert does not mean safe".

## World and tokens (app/theme.py, .streamlit/config.toml)
- Dark "control room" (default) and light "daylight"; viewers switch in Settings → Theme.
- Hazard colours are the only saturated colours. Every status has a label **and** a distinct icon shape
  (visibility / warning triangle / crisis diamond …), so nothing relies on colour alone. Chart anomalies use
  shape + colour + tooltip text.
- IBM Plex Sans for UI, IBM Plex Mono for numbers and dates (tabular), Noto Nastaliq Urdu for Urdu.

## Rules
- Every chart and figure carries a caption with data source and date range.
- Missing outputs render as empty states naming the producing command. No sample numbers, ever.
- Chart zoom needs Shift + scroll so page scrolling never gets trapped in a chart.
- Auto-refresh reloads only when files in outputs/ change.
- Phone: nav folds into the sidebar, no horizontal page scroll.
