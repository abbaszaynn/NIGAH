# NIGAH dashboard design

Mode: **Operate**. Users are NDMA/GBDMA officers at a desk in daylight and field staff on a phone.
They need to see in seconds which lake is in what state, and why. The tool disappears into the task.

## World
A field survey sheet: warm paper background, deep glacial ink, one water-blue accent.
Light theme, picked for daylight offices and outdoor phone use.

## Tokens (app/theme.py, .streamlit/config.toml)
| Role | Value |
|---|---|
| Ink / secondary / tertiary text | `#14212B` / `#45535D` / `#5F6B73` |
| Paper / surface / panel / rule | `#F6F5F1` / `#FFFFFF` / `#ECEAE3` / `#D9D6CC` |
| Water accent (lake series, links, focus) | `#1F6F8B` |
| Alert / Warning / Watch / Normal | `#B42318` / `#B54708` / `#8A5A00` / `#2F6B4F` on tinted pills |
| Type | IBM Plex Sans for UI; IBM Plex Mono only for dates and measurements |

## Rules
- Hazard colours are the only saturated colours, and a tier is always shown with its text label (and the Alert pill has a distinct diamond marker), never colour alone.
- Numbers use tabular figures and do not wrap.
- Every chart and figure carries a caption with data source and date range.
- Missing outputs render as an empty state that names the command that produces them. No sample or placeholder numbers, ever.
- No emoji as icons; tab icons are Material Symbols.
- Motion: none beyond Streamlit defaults. `prefers-reduced-motion` is respected.
- Mobile (<640 px): the status board drops Valley, z-score and AOI columns and scrolls inside its own box; the page never scrolls sideways.
