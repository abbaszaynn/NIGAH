"""Design tokens, CSS and HTML components for the NIGAH dashboard.

Two modes from one token set:
  dark  "control room": default, for an operations room or a wall display
  light "daylight": offices and phones outdoors
Viewers switch in the app menu (Settings -> Theme). Hazard tiers are the only
saturated colours and always carry a text label and a distinct marker shape.
"""

from __future__ import annotations

import html

MODES = {
    "dark": {
        "bg": "#0B1117", "surface": "#111A22", "surface2": "#172330", "rule": "#243341",
        "ink": "#E6EDF2", "ink2": "#AEBBC6", "ink3": "#8796A3", "accent": "#4FB3D9",
        "tiers": {
            "alert": ("#FF6B61", "rgba(255,107,97,0.14)"),
            "warning": ("#FF9F4D", "rgba(255,159,77,0.14)"),
            "watch": ("#F2C94C", "rgba(242,201,76,0.13)"),
            "normal": ("#4CC38A", "rgba(76,195,138,0.13)"),
            "no_baseline": ("#8796A3", "rgba(135,150,163,0.14)"),
            "no_data": ("#8796A3", "rgba(135,150,163,0.14)"),
            "stale": ("#C9A86A", "rgba(201,168,106,0.14)"),
            "qa_failed": ("#B9A3E3", "rgba(185,163,227,0.14)"),
            "off_season": ("#8FB8D0", "rgba(143,184,208,0.13)"),
        },
        "basemap": "cartodbdark_matter",
    },
    "light": {
        "bg": "#F6F5F1", "surface": "#FFFFFF", "surface2": "#ECEAE3", "rule": "#D9D6CC",
        "ink": "#14212B", "ink2": "#45535D", "ink3": "#5F6B73", "accent": "#1F6F8B",
        "tiers": {
            "alert": ("#B42318", "#FCE9E7"),
            "warning": ("#B54708", "#FDEFE3"),
            "watch": ("#8A5A00", "#FBF3DC"),
            "normal": ("#2F6B4F", "#E6F1EA"),
            "no_baseline": ("#5F6B73", "#ECEAE3"),
            "no_data": ("#5F6B73", "#ECEAE3"),
            "stale": ("#7A5B1E", "#F4ECDC"),
            "qa_failed": ("#5B4B8A", "#EEEAF6"),
            "off_season": ("#3C6478", "#E5EEF3"),
        },
        "basemap": "cartodbpositron",
    },
}

TIER_LABEL = {"alert": "Alert", "warning": "Warning", "watch": "Watch", "normal": "Normal",
              "no_baseline": "Too little history", "no_data": "No data", "stale": "Data stale",
              "qa_failed": "QA failed", "off_season": "Off season"}
# Material Symbols glyph per tier: shape differs, so tier reads without colour
TIER_ICON = {"alert": "crisis_alert", "warning": "warning", "watch": "visibility",
             "normal": "check_circle", "no_baseline": "hourglass_empty", "no_data": "do_not_disturb_on",
             "stale": "schedule", "qa_failed": "report", "off_season": "ac_unit"}
TIER_ORDER = ["no_data", "no_baseline", "normal", "watch", "warning", "alert"]

FONTS = ("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500"
         "&family=IBM+Plex+Sans:wght@400;500;600;700&family=Noto+Nastaliq+Urdu:wght@400;600&display=swap")
ICONS = ("https://fonts.googleapis.com/css2?family=Material+Symbols+Rounded:"
         "opsz,wght,FILL,GRAD@20..24,400,0..1,0&display=block")


def tier_color(mode: str, tier: str) -> str:
    return MODES[mode]["tiers"].get(tier, MODES[mode]["tiers"]["no_data"])[0]


def css(mode: str) -> str:
    m = MODES[mode]
    tier_vars = "".join(f"--t-{k}: {fg}; --t-{k}-bg: {bg};" for k, (fg, bg) in m["tiers"].items())
    return f"""
<style>
@import url('{FONTS}');
@import url('{ICONS}');
:root {{
  --bg: {m['bg']}; --surface: {m['surface']}; --surface2: {m['surface2']}; --rule: {m['rule']};
  --ink: {m['ink']}; --ink2: {m['ink2']}; --ink3: {m['ink3']}; --accent: {m['accent']};
  {tier_vars}
  --r: 8px;
}}
.stApp, .stApp p, .stApp li, .stApp label, .stApp input, .stApp button, .stApp table,
.stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp textarea {{
  font-family: 'IBM Plex Sans', system-ui, sans-serif;
}}
.stApp code, .stApp pre, .num {{ font-family: 'IBM Plex Mono', ui-monospace, monospace; }}
.stApp {{ font-variant-numeric: tabular-nums; }}
.num {{ white-space: nowrap; }}
.block-container {{ padding-top: 4.6rem; padding-bottom: 3rem; max-width: 1600px; }}
.stApp h1 {{ font-size: 1.45rem; font-weight: 700; letter-spacing: -0.01em; margin: 0 0 0.1rem; padding: 0; }}
.stApp h3 {{ font-size: 0.98rem; font-weight: 600; margin: 0 0 0.5rem; padding: 0; color: var(--ink); }}
.msr {{ font-family: 'Material Symbols Rounded'; font-weight: normal; font-style: normal;
  font-size: 1.15em; line-height: 1; letter-spacing: normal; text-transform: none; display: inline-block;
  white-space: nowrap; direction: ltr; -webkit-font-smoothing: antialiased; vertical-align: -0.18em;
  font-variation-settings: 'FILL' 1; }}

/* page header */
.ph {{ display: flex; justify-content: space-between; align-items: flex-end; gap: 1rem; flex-wrap: wrap;
  margin-bottom: 1rem; }}
.ph .sub {{ color: var(--ink2); font-size: 0.9rem; }}
.ph .meta {{ color: var(--ink3); font-size: 0.8rem; text-align: right; line-height: 1.55; }}
.ph .meta b {{ color: var(--ink); font-weight: 500; }}

/* sidebar brand */
.brand {{ display: flex; align-items: baseline; gap: 0.5rem; margin: 0.2rem 0 0.1rem; }}
.brand .w {{ font-size: 1.35rem; font-weight: 700; letter-spacing: 0.1em; color: var(--ink); }}
.brand .u {{ font-size: 1.15rem; color: var(--accent); }}
.brand-sub {{ color: var(--ink3); font-size: 0.78rem; line-height: 1.4; margin-bottom: 0.6rem; }}
.clock {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.8rem; color: var(--ink2); line-height: 1.6; }}
.clock b {{ color: var(--ink); font-weight: 500; }}

/* threat banner */
.banner {{ display: grid; grid-template-columns: auto 1fr auto; gap: 1rem; align-items: center;
  padding: 0.95rem 1.15rem; border-radius: var(--r); background: var(--tb); border: 1px solid var(--tc);
  margin-bottom: 0.9rem; }}
.banner .ic {{ font-size: 2rem; color: var(--tc); }}
.banner .lvl {{ font-size: 0.74rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: var(--tc); }}
.banner .hd {{ font-size: 1.12rem; font-weight: 600; color: var(--ink); margin-top: 0.1rem; }}
.banner .bd {{ font-size: 0.88rem; color: var(--ink2); margin-top: 0.2rem; }}
.banner .rt {{ text-align: right; font-size: 0.8rem; color: var(--ink2); line-height: 1.55; }}
@media (max-width: 720px) {{ .banner {{ grid-template-columns: auto 1fr; }} .banner .rt {{ grid-column: 1 / -1; text-align: left; }} }}

/* KPI strip: one bordered strip with dividers */
.kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); background: var(--surface);
  border: 1px solid var(--rule); border-radius: var(--r); margin-bottom: 1rem; overflow: hidden; }}
.kpi {{ padding: 0.75rem 1rem; border-right: 1px solid var(--rule); min-width: 0; }}
.kpi:last-child {{ border-right: 0; }}
.kpi .l {{ font-size: 0.74rem; color: var(--ink3); font-weight: 500; display: flex; gap: 0.35rem; align-items: center; }}
.kpi .v {{ font-size: 1.35rem; font-weight: 600; color: var(--ink); margin-top: 0.2rem;
  font-family: 'IBM Plex Mono', monospace; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.kpi .v.t {{ font-family: 'IBM Plex Sans', sans-serif; font-size: 1.1rem; }}
.kpi .s {{ font-size: 0.76rem; color: var(--ink2); margin-top: 0.15rem; }}
.kpi .s.bad {{ color: var(--t-warning); }}

/* panel */
.panel {{ background: var(--surface); border: 1px solid var(--rule); border-radius: var(--r); padding: 0.9rem 1rem; }}
.ph3 {{ display: flex; justify-content: space-between; align-items: baseline; gap: 0.5rem; margin: 0.2rem 0 0.5rem; }}
.ph3 h3 {{ margin: 0; }}
.ph3 .m {{ font-size: 0.76rem; color: var(--ink3); }}

/* tier pill */
.pill {{ display: inline-flex; align-items: center; gap: 0.3rem; padding: 0.12rem 0.55rem 0.12rem 0.4rem;
  border-radius: 999px; font-size: 0.78rem; font-weight: 600; white-space: nowrap; }}

/* alert cards */
.acard {{ background: var(--surface); border: 1px solid var(--rule); border-radius: var(--r);
  padding: 0.75rem 0.9rem; margin-bottom: 0.6rem; }}
.acard .top {{ display: flex; justify-content: space-between; gap: 0.5rem; align-items: center; }}
.acard .t {{ font-weight: 600; color: var(--ink); margin-top: 0.4rem; font-size: 0.92rem; }}
.acard .d {{ color: var(--ink2); font-size: 0.84rem; margin-top: 0.2rem; }}
.acard .f {{ display: flex; flex-wrap: wrap; gap: 0.25rem 0.9rem; margin-top: 0.45rem; font-size: 0.74rem; color: var(--ink3); }}
.acard .f b {{ color: var(--ink2); font-weight: 500; }}

/* tables */
.tbl {{ width: 100%; border-collapse: collapse; font-size: 0.86rem; }}
.tbl th {{ text-align: left; font-weight: 500; color: var(--ink3); font-size: 0.74rem; padding: 0.5rem 0.7rem;
  border-bottom: 1px solid var(--rule); white-space: nowrap; }}
.tbl td {{ padding: 0.55rem 0.7rem; border-bottom: 1px solid var(--rule); color: var(--ink); vertical-align: top; }}
.tbl tr:last-child td {{ border-bottom: 0; }}
.tbl .r {{ text-align: right; }}
.tbl .mu {{ color: var(--ink3); }}
.tbl-wrap {{ overflow-x: auto; background: var(--surface); border: 1px solid var(--rule); border-radius: var(--r); }}

/* timeline */
.tl {{ list-style: none; padding: 0; margin: 0; }}
.tl li {{ display: grid; grid-template-columns: 5.6rem 1.4rem 1fr; gap: 0.4rem; padding: 0.45rem 0;
  border-bottom: 1px solid var(--rule); font-size: 0.84rem; color: var(--ink2); align-items: start; }}
.tl li:last-child {{ border-bottom: 0; }}
.tl .dt {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem; color: var(--ink3); }}
.tl b {{ color: var(--ink); font-weight: 500; }}

/* checks */
.chk {{ display: grid; grid-template-columns: 1.4rem 1fr auto; gap: 0.5rem; padding: 0.5rem 0;
  border-bottom: 1px solid var(--rule); font-size: 0.86rem; align-items: start; }}
.chk:last-child {{ border-bottom: 0; }}
.chk .n {{ color: var(--ink); }}
.chk .h {{ color: var(--ink3); font-size: 0.78rem; margin-top: 0.1rem; }}
.chk .v {{ color: var(--ink2); font-size: 0.8rem; white-space: nowrap; font-family: 'IBM Plex Mono', monospace; }}

/* empty state */
.empty {{ border: 1px dashed var(--rule); border-radius: var(--r); padding: 1rem 1.1rem; background: var(--surface);
  color: var(--ink2); font-size: 0.88rem; }}
.empty .t {{ color: var(--ink); font-weight: 600; margin-bottom: 0.25rem; display: flex; gap: 0.4rem; align-items: center; }}
.empty code {{ display: block; margin-top: 0.55rem; padding: 0.45rem 0.6rem; background: var(--surface2);
  border-radius: 4px; color: var(--ink); font-size: 0.8rem; white-space: pre-wrap; }}

.caption {{ color: var(--ink3); font-size: 0.76rem; margin-top: 0.35rem; line-height: 1.45; }}
.note {{ background: var(--surface2); border-radius: var(--r); padding: 0.7rem 0.9rem; color: var(--ink2); font-size: 0.85rem; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 0.4rem 1rem; align-items: center; font-size: 0.78rem;
  color: var(--ink2); margin-top: 0.45rem; }}
.legend .msr {{ font-size: 1.05rem; }}
.ur {{ font-family: 'Noto Nastaliq Urdu', 'Jameel Noori Nastaleeq', serif; direction: rtl; text-align: right; line-height: 2; }}

/* streamlit chrome */
header[data-testid="stHeader"] {{ background: var(--bg); border-bottom: 1px solid var(--rule); }}
[data-testid="stSidebar"] {{ border-right: 1px solid var(--rule); }}
[data-testid="stSidebarNav"] a span {{ font-size: 0.9rem; }}
.stTabs [data-baseweb="tab-list"] {{ gap: 1.2rem; border-bottom: 1px solid var(--rule); }}
.stTabs [data-baseweb="tab"] {{ padding: 0.45rem 0; font-weight: 500; }}
iframe {{ border-radius: var(--r); }}
@media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; animation: none !important; }} }}
</style>
"""


def esc(x) -> str:
    return html.escape("" if x is None else str(x))


def icon(name: str, color: str | None = None) -> str:
    style = f' style="color:{color}"' if color else ""
    return f'<span class="msr" aria-hidden="true"{style}>{esc(name)}</span>'


def pill(tier: str, label: str | None = None) -> str:
    t = tier if tier in TIER_LABEL else "no_data"
    return (f'<span class="pill" style="color:var(--t-{t});background:var(--t-{t}-bg)">'
            f'{icon(TIER_ICON[t])}{esc(label or TIER_LABEL[t])}</span>')


def banner(tier: str, level: str, headline: str, body: str, right_html: str) -> str:
    t = tier if tier in TIER_LABEL else "no_data"
    return (f'<div class="banner" role="status" style="--tc:var(--t-{t});--tb:var(--t-{t}-bg)">'
            f'<div class="ic">{icon(TIER_ICON[t])}</div>'
            f'<div><div class="lvl">{esc(level)}</div><div class="hd">{esc(headline)}</div>'
            f'<div class="bd">{esc(body)}</div></div><div class="rt">{right_html}</div></div>')


def kpis(items: list[dict]) -> str:
    """items: label, value, sub, icon, bad (bool), text (bool: value is words not numbers)."""
    cells = []
    for k in items:
        ic = icon(k["icon"]) if k.get("icon") else ""
        cells.append(f'<div class="kpi"><div class="l">{ic}{esc(k["label"])}</div>'
                     f'<div class="v{" t" if k.get("text") else ""}" title="{esc(k["value"])}">{esc(k["value"])}</div>'
                     f'<div class="s{" bad" if k.get("bad") else ""}">{esc(k.get("sub", ""))}</div></div>')
    return f'<div class="kpis">{"".join(cells)}</div>'


def section(title: str, meta: str = "") -> str:
    return f'<div class="ph3"><h3>{esc(title)}</h3><span class="m">{esc(meta)}</span></div>'


def page_header(title: str, sub: str, meta_html: str = "") -> str:
    return (f'<div class="ph"><div><h1>{esc(title)}</h1><div class="sub">{esc(sub)}</div></div>'
            f'<div class="meta">{meta_html}</div></div>')


def empty_state(title: str, body: str, command: str | None = None, ic: str = "info") -> str:
    cmd = f"<code>{esc(command)}</code>" if command else ""
    return f'<div class="empty"><div class="t">{icon(ic)}{esc(title)}</div>{esc(body)}{cmd}</div>'


def legend_tiers(tiers=("alert", "warning", "watch", "normal", "no_data")) -> str:
    spans = "".join(f'<span style="color:var(--t-{t})">{icon(TIER_ICON[t])}'
                    f'<span style="color:var(--ink2)"> {TIER_LABEL[t]}</span></span>' for t in tiers)
    return f'<div class="legend">{spans}</div>'


def altair_theme(mode: str):
    m = MODES[mode]

    def theme():
        return {"config": {
            "font": "IBM Plex Sans", "background": m["surface"], "padding": 8,
            "view": {"stroke": None},
            "axis": {"labelColor": m["ink2"], "titleColor": m["ink2"], "gridColor": m["rule"],
                     "gridOpacity": 0.6, "domainColor": m["rule"], "tickColor": m["rule"],
                     "labelFontSize": 11, "titleFontSize": 11, "titleFontWeight": 500},
            "legend": {"labelColor": m["ink2"], "titleColor": m["ink2"], "labelFontSize": 11,
                       "titleFontSize": 11, "orient": "top", "symbolStrokeWidth": 0},
            "title": {"color": m["ink"], "fontSize": 13, "fontWeight": 600, "anchor": "start"},
            "text": {"color": m["ink2"]},
        }}
    return theme
