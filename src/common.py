"""Shared config loading, paths and Earth Engine init.

Every script reads config/ and writes outputs/ through these helpers.
"""

from __future__ import annotations

import json
import os
import tomllib
from functools import lru_cache
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config"
# NIGAH_OUTPUTS lets tests point every script at a scratch directory
OUTPUTS = Path(os.environ.get("NIGAH_OUTPUTS", ROOT / "outputs"))

ALPHAEARTH_ATTRIBUTION = ("The AlphaEarth Foundations Satellite Embedding dataset "
                          "is produced by Google and Google DeepMind.")


@lru_cache
def settings() -> dict:
    with open(CONFIG / "settings.toml", "rb") as f:
        return tomllib.load(f)


def aois() -> dict[str, dict]:
    """AOI features keyed by id. Features without geometry are kept so callers
    can say clearly that an AOI has not been drawn yet."""
    with open(CONFIG / "aoi.geojson", encoding="utf-8") as f:
        fc = json.load(f)
    return {feat["properties"]["id"]: feat for feat in fc["features"]}


def aoi(aoi_id: str) -> dict:
    feats = aois()
    if aoi_id not in feats:
        raise SystemExit(f"Unknown AOI '{aoi_id}'. Known: {', '.join(feats)}")
    feat = feats[aoi_id]
    if feat["geometry"] is None:
        raise SystemExit(f"AOI '{aoi_id}' has no geometry yet. Draw it in the GEE Code "
                         f"Editor and paste it into config/aoi.geojson.")
    return feat


def events() -> pd.DataFrame:
    df = pd.read_csv(CONFIG / "events.csv", parse_dates=["date"])
    df["verified"] = df["verified"].astype(str).str.lower().eq("true")
    return df


def out_path(name: str) -> Path:
    OUTPUTS.mkdir(exist_ok=True)
    return OUTPUTS / name


def init_ee(project: str | None = None):
    """Initialise Earth Engine. Project comes from the argument, then the
    NIGAH_GEE_PROJECT env var, then config/settings.toml."""
    import ee

    project = project or os.environ.get("NIGAH_GEE_PROJECT") or settings()["gee"]["project"]
    if not project:
        raise SystemExit("No GEE project id. Pass --project, set NIGAH_GEE_PROJECT, "
                         "or fill [gee].project in config/settings.toml.")
    sa_key = os.environ.get("NIGAH_GEE_SERVICE_ACCOUNT_KEY")
    if sa_key:  # CI: service-account JSON in a secret
        info = json.loads(sa_key)
        creds = ee.ServiceAccountCredentials(info["client_email"], key_data=sa_key)
        ee.Initialize(creds, project=project)
    else:
        ee.Initialize(project=project)
    return ee


def ee_geometry(feature: dict):
    import ee

    return ee.Geometry(feature["geometry"])
