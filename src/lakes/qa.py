"""Data-quality checks on a lake-area series.

A lake that fails QA must not raise alerts: its tier is replaced by "qa_failed"
in the dashboard and src.alerts.check does not send it.
"""

from __future__ import annotations

import pandas as pd

MIN_OBS = 10
SATURATION_SHARE = 0.3   # share of scenes within 2% of the series maximum
SATURATION_TOL = 0.02


def check(area: pd.DataFrame, feature: dict) -> list[dict]:
    """Return issues as {level: fail|warn, code, message}. area: rows of one lake, any sensors."""
    issues = []
    pr = feature["properties"]
    if not pr.get("verified"):
        issues.append({"level": "warn", "code": "aoi_unverified",
                       "message": "AOI box not verified on imagery; area may not be the lake."})
    s2 = area[area["sensor"] == "s2"]["area_km2"] if "sensor" in area else area["area_km2"]
    if len(s2) < MIN_OBS:
        issues.append({"level": "warn", "code": "few_obs",
                       "message": f"Only {len(s2)} clear Sentinel-2 scenes."})
        return issues
    mx = s2.max()
    share = (s2 >= mx * (1 - SATURATION_TOL)).mean()
    if mx > 0 and share >= SATURATION_SHARE:
        issues.append({"level": "fail", "code": "saturated",
                       "message": f"{share:.0%} of scenes sit at the series maximum ({mx:.3f} km²): "
                                  "the water mask is hitting a ceiling (snow/ice read as water, or the "
                                  "flat-terrain mask is smaller than the lake). Redraw the AOI and "
                                  "re-run before trusting any tier."})
    return issues


def failed(issues: list[dict]) -> bool:
    return any(i["level"] == "fail" for i in issues)
