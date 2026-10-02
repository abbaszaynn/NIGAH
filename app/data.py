"""Data layer for the dashboard: loaders, lake status, freshness, health checks, weather.

Everything here is read from outputs/ and config/ (or fetched live from Open-Meteo for
weather context). Nothing is invented: missing inputs come back as None.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

from src.common import CONFIG, OUTPUTS, ROOT, aois, events, settings
from src.lakes import qa
from src.lakes.anomaly import add_alerts, thresholds

PKT = timezone(timedelta(hours=5), "PKT")
ACTIVE_DAYS = 14   # an alert stays active this long after its scene date
STALE_DAYS = 12    # in season, a latest scene older than this means monitoring is degraded
HAZARD = ["watch", "warning", "alert"]
SENSOR_LABEL = {"s2": "Sentinel-2", "s1": "Sentinel-1", "landsat": "Landsat"}


def mode() -> str:
    try:
        t = st.context.theme.type
    except Exception:
        t = None
    return "light" if t == "light" else "dark"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def in_season(d: datetime | None = None) -> bool:
    m0, m1 = settings()["lakes"]["months"]
    return m0 <= (d or now_utc()).month <= m1


def mtime(p: Path) -> float:
    return p.stat().st_mtime if p.exists() else 0.0


def outputs_signature() -> float:
    """Changes whenever any output file changes; drives auto-refresh."""
    return max((mtime(p) for p in OUTPUTS.glob("*") if p.is_file()), default=0.0)


@st.cache_data(show_spinner=False)
def _read_csv(path: str, mt: float, kw_json: str) -> pd.DataFrame | None:
    return pd.read_csv(path, **json.loads(kw_json)) if mt else None


def csv(name: str, **kw) -> pd.DataFrame | None:
    p = OUTPUTS / name
    df = _read_csv(str(p), mtime(p), json.dumps(kw))
    return None if df is None else df.copy()


def area(lake: str) -> pd.DataFrame | None:
    df = csv(f"{lake}_area.csv", parse_dates=["date"])
    return None if df is None or df.empty else df


@st.cache_data(show_spinner=False)
def _alerts(lake: str, mt: float, th_json: str) -> pd.DataFrame | None:
    if not mt:
        return None
    df = pd.read_csv(OUTPUTS / f"{lake}_area.csv", parse_dates=["date"])
    s2 = df[df["sensor"] == "s2"].sort_values("date").groupby("date").last()
    return add_alerts(s2, json.loads(th_json)) if len(s2) else None


def alerts(lake: str, th: dict) -> pd.DataFrame | None:
    return _alerts(lake, mtime(OUTPUTS / f"{lake}_area.csv"), json.dumps(th, sort_keys=True))


# ---------------------------------------------------------------- lake status

@dataclass
class Lake:
    id: str
    name: str
    valley: str
    feature: dict
    drawn: bool
    verified: bool
    downstream: list[str]
    tier: str = "no_data"          # display status (hazard tier, qa_failed, stale, no_data)
    hazard_tier: str = "no_data"   # tier computed by the alert rules
    date: pd.Timestamp | None = None
    age_days: int | None = None
    area: float | None = None
    baseline: float | None = None
    departure: float | None = None
    growth: float | None = None
    z: float | None = None
    n_obs: int = 0
    n_season: int = 0
    issues: list[dict] = field(default_factory=list)
    series: pd.DataFrame | None = None
    raw: pd.DataFrame | None = None

    @property
    def active(self) -> bool:
        return self.tier in HAZARD

    @property
    def centroid(self) -> tuple[float, float] | None:
        g = self.feature["geometry"]
        if not g:
            return None
        ring = g["coordinates"][0]
        return (sum(p[1] for p in ring[:-1]) / (len(ring) - 1),
                sum(p[0] for p in ring[:-1]) / (len(ring) - 1))


def lake_status(feat: dict, th: dict, now: datetime) -> Lake:
    pr = feat["properties"]
    lk = Lake(id=pr["id"], name=pr["name"], valley=pr.get("valley", ""), feature=feat,
              drawn=feat["geometry"] is not None, verified=bool(pr.get("verified")),
              downstream=list(pr.get("downstream", [])))
    if not lk.drawn:
        return lk
    raw = area(lk.id)
    al = alerts(lk.id, th)
    if raw is None or al is None or al.empty:
        return lk
    lk.raw, lk.series = raw, al
    lk.issues = qa.check(raw, feat)
    last = al.iloc[-1]
    lk.date = al.index[-1]
    lk.age_days = (now.replace(tzinfo=None) - lk.date.to_pydatetime()).days
    lk.area, lk.growth, lk.z = last["area_km2"], last["growth_15d"], last["z"]
    lk.baseline = last.get("baseline_median")
    if lk.baseline and lk.baseline == lk.baseline and lk.baseline > 0:
        lk.departure = lk.area / lk.baseline - 1
    lk.n_obs = len(al)
    lk.n_season = int((al.index.year == lk.date.year).sum())
    lk.hazard_tier = last["tier"]
    if qa.failed(lk.issues):
        lk.tier = "qa_failed"
    elif in_season(now) and lk.age_days > STALE_DAYS:
        lk.tier = "stale"
    elif lk.age_days > ACTIVE_DAYS:
        lk.tier = "off_season"   # winter: the last scene is from autumn, nothing is in force
    else:
        lk.tier = lk.hazard_tier
    return lk


# ---------------------------------------------------------------- context

@dataclass
class Ctx:
    now: datetime
    th: dict
    features: dict
    lakes: list[Lake]
    events: pd.DataFrame
    log: pd.DataFrame | None
    reports: pd.DataFrame | None
    overall: dict
    mode: str


def overall_status(lakes: list[Lake], now: datetime) -> dict:
    rank = {"alert": 3, "warning": 2, "watch": 1}
    active = sorted([l for l in lakes if l.active], key=lambda l: -rank[l.tier])
    monitored = [l for l in lakes if l.series is not None]
    season = in_season(now)
    if active:
        top = active[0]
        others = f" and {len(active) - 1} more" if len(active) > 1 else ""
        return {"tier": top.tier, "level": f"{top.tier} in force",
                "headline": f"{top.name}{others}",
                "body": f"Latest scene {top.date.date()}: water area {top.area:.3f} km²"
                        + (f", {top.growth:+.0%} per 15 days" if top.growth == top.growth and top.growth is not None else "")
                        + ". See Alerts & bulletins for the suggested action."}
    if not monitored:
        return {"tier": "no_data", "level": "Monitoring not started",
                "headline": "No lake has a satellite series yet",
                "body": "Run the lake-area pipeline for at least one AOI. Until then NIGAH cannot say whether any lake is safe."}
    failed = [l for l in monitored if l.tier == "qa_failed"]
    stale = [l for l in monitored if l.tier == "stale"]
    if failed or stale:
        bits = []
        if failed:
            bits.append(f"{len(failed)} lake series failed quality checks ({', '.join(l.name for l in failed)})")
        if stale:
            bits.append(f"{len(stale)} lake{'s' if len(stale) > 1 else ''} without a recent clear scene")
        return {"tier": "qa_failed" if failed else "stale", "level": "Monitoring degraded",
                "headline": "No reliable alert status for every lake",
                "body": "; ".join(bits) + ". Absence of an alert here does not mean a lake is safe."}
    if not season:
        return {"tier": "normal", "level": "Off season",
                "headline": "No active alerts. Lakes are frozen; satellite monitoring resumes in April",
                "body": "Watch field reports for winter events (avalanches, rockfall)."}
    return {"tier": "normal", "level": "No active alerts",
            "headline": f"All {len(monitored)} monitored lake{'s' if len(monitored) > 1 else ''} within normal range",
            "body": "Based on the latest clear Sentinel-2 scene of each lake."}


def ctx() -> Ctx:
    now = now_utc()
    th = thresholds()
    feats = aois()
    lakes = [lake_status(f, th, now) for f in feats.values() if f["properties"]["kind"] == "lake"]
    log = csv("alert_log.csv")
    reports = csv("reports_triaged.csv")
    if reports is not None:
        reports["published"] = pd.to_datetime(reports["published"], errors="coerce", utc=True)
    return Ctx(now=now, th=th, features=feats, lakes=lakes, events=events(), log=log,
               reports=reports, overall=overall_status(lakes, now), mode=mode())


# ---------------------------------------------------------------- schedule & health

def next_scheduled_run(now: datetime) -> datetime | None:
    wf = ROOT / ".github" / "workflows" / "weekly.yml"
    if not wf.exists():
        return None
    m = re.search(r'cron:\s*"(\d+) (\d+) \* \* (\d)"', wf.read_text())
    if not m:
        return None
    minute, hour, dow = int(m[1]), int(m[2]), int(m[3])  # cron: 0 = Sunday
    target = (dow - 1) % 7                                # python: 0 = Monday
    d = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    d += timedelta(days=(target - d.weekday()) % 7)
    return d if d > now else d + timedelta(days=7)


PIPELINE = [
    # name, glob, producer, expected cadence (days) or None for on demand
    ("Lake area series", "*_area.csv", "python -m src.lakes.lake_area / src.alerts.check", 7),
    ("Alert tiers", "*_alerts.csv", "python -m src.alerts.check", 7),
    ("Alert log", "alert_log.csv", "python -m src.alerts.check", 7),
    ("Tuned thresholds", "tuned_thresholds.json", "python -m src.lakes.backtest --tune", None),
    ("Back-test report", "backtest_report.md", "python -m src.lakes.backtest", None),
    ("Landslide samples", "landslide_samples.csv", "python -m src.landslide.features", None),
    ("Landslide model AUC", "landslide_auc.csv", "python -m src.landslide.train", None),
    ("Susceptibility map", "susceptibility.png", "python -m src.landslide.train", None),
    ("Field reports collected", "reports_raw.csv", "python -m src.nlp.scrape", 7),
    ("Field reports triaged", "reports_triaged.csv", "python -m src.nlp.classify predict", 7),
]


def pipeline_status(now: datetime) -> pd.DataFrame:
    rows = []
    for name, pattern, producer, cadence in PIPELINE:
        files = sorted(OUTPUTS.glob(pattern))
        if not files:
            rows.append({"component": name, "status": "Missing", "updated": None, "age_days": None,
                         "files": 0, "cadence": f"every {cadence} d" if cadence else "on demand",
                         "producer": producer})
            continue
        latest = max(mtime(f) for f in files)
        upd = datetime.fromtimestamp(latest, timezone.utc)
        age = (now - upd).total_seconds() / 86400
        ok = cadence is None or age <= cadence * 1.5
        rows.append({"component": name, "status": "OK" if ok else "Overdue", "updated": upd,
                     "age_days": round(age, 1), "files": len(files),
                     "cadence": f"every {cadence} d" if cadence else "on demand", "producer": producer})
    return pd.DataFrame(rows)


def secret_present(name: str) -> bool:
    if os.environ.get(name):
        return True
    try:
        return name in st.secrets
    except Exception:
        return False


def config_checks(c: Ctx) -> list[dict]:
    lakes_f = [f for f in c.features.values()]
    drawn = sum(f["geometry"] is not None for f in lakes_f)
    verified = sum(bool(f["properties"].get("verified")) for f in lakes_f)
    ev = c.events
    sourced = int((ev["source_url"].fillna("").str.len() > 0).sum())
    gz = pd.read_csv(CONFIG / "gazetteer.csv")
    gz_ok = int(gz["verified"].astype(str).str.lower().eq("true").sum())
    project = os.environ.get("NIGAH_GEE_PROJECT") or settings()["gee"]["project"]
    tuned = c.th["tuned"]
    return [
        {"ok": bool(project), "name": "Earth Engine project configured",
         "hint": "config/settings.toml [gee].project or NIGAH_GEE_PROJECT", "value": "set" if project else "missing"},
        {"ok": drawn == len(lakes_f), "name": "All AOIs drawn",
         "hint": "Draw missing polygons in the GEE Code Editor", "value": f"{drawn}/{len(lakes_f)}"},
        {"ok": verified == len(lakes_f), "name": "AOIs verified on imagery",
         "hint": "Set verified=true in config/aoi.geojson after checking", "value": f"{verified}/{len(lakes_f)}"},
        {"ok": sourced == len(ev) and bool(ev["verified"].all()), "name": "Events dated and sourced",
         "hint": "Add source_url and verified=true in config/events.csv", "value": f"{sourced}/{len(ev)} sourced"},
        {"ok": tuned, "name": "Thresholds tuned on 2019–2021",
         "hint": "python -m src.lakes.backtest --tune", "value": "tuned" if tuned else "defaults"},
        {"ok": secret_present("TELEGRAM_BOT_TOKEN") and secret_present("TELEGRAM_CHAT_ID"),
         "name": "Telegram channel configured", "hint": "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID secrets",
         "value": "configured" if secret_present("TELEGRAM_BOT_TOKEN") else "not set"},
        {"ok": gz_ok == len(gz), "name": "Gazetteer coordinates verified",
         "hint": "config/gazetteer.csv verified column", "value": f"{gz_ok}/{len(gz)}"},
    ]


def pillars(c: Ctx, pipe: pd.DataFrame, checks: list[dict]) -> list[dict]:
    """UN Early Warnings for All / WMO MHEWS four pillars, scored from what exists."""
    have = set(pipe.loc[pipe["status"] != "Missing", "component"])
    monitored = sum(l.series is not None for l in c.lakes)
    qa_ok = sum(l.series is not None and not qa.failed(l.issues) for l in c.lakes)
    chk = {x["name"]: x["ok"] for x in checks}
    return [
        {"pillar": "1. Risk knowledge", "status": "partial" if "Landslide model AUC" in have else "gap",
         "evidence": ("Susceptibility model trained" if "Landslide model AUC" in have else "No susceptibility model yet")
                     + f"; AOIs verified {sum(bool(f['properties'].get('verified')) for f in c.features.values())}/{len(c.features)}"},
        {"pillar": "2. Detection & monitoring", "status": "ok" if qa_ok and qa_ok == monitored == len(c.lakes) else ("partial" if monitored else "gap"),
         "evidence": f"{monitored}/{len(c.lakes)} lakes have a series; {qa_ok} pass QA"},
        {"pillar": "3. Warning dissemination", "status": "ok" if chk["Telegram channel configured"] else "partial",
         "evidence": "CAP 1.2 messages generated; Telegram " + ("configured" if chk["Telegram channel configured"] else "not configured")},
        {"pillar": "4. Preparedness & response", "status": "partial",
         "evidence": "Suggested tier actions drafted; not yet agreed with GBDMA/NDMA"},
    ]


# ---------------------------------------------------------------- weather (Open-Meteo, free, no key)

@st.cache_data(ttl=3600, show_spinner=False)
def weather(lat: float, lon: float) -> pd.DataFrame | None:
    import requests
    try:
        r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=10, params={
            "latitude": round(lat, 4), "longitude": round(lon, 4), "timezone": "Asia/Karachi",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "hourly": "freezing_level_height", "forecast_days": 7})
        r.raise_for_status()
        j = r.json()
    except Exception:
        return None
    d = pd.DataFrame(j["daily"]).rename(columns={"time": "date"})
    h = pd.DataFrame(j["hourly"])
    h["date"] = h["time"].str.slice(0, 10)
    d = d.merge(h.groupby("date")["freezing_level_height"].max().rename("freezing_level_max").reset_index(), on="date")
    d["date"] = pd.to_datetime(d["date"])
    d.attrs["elevation"] = j.get("elevation")
    d.attrs["fetched"] = now_utc().astimezone(PKT).strftime("%Y-%m-%d %H:%M PKT")
    return d
