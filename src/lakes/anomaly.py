"""Alert rules for lake-area series.

Two rules per observation:
  z          robust z-score of area vs the prior 60-day baseline (median / MAD)
  growth_15d relative area change since the previous observation, scaled to 15 days

Tiers (highest wins):
  alert    warning-level z AND warning-level growth on one observation,
           or warning on N consecutive observations
  warning  z > warning.z  OR growth > warning.growth
  watch    z > watch.z    OR growth > watch.growth
  normal   rules computed, nothing fired
  no_baseline  not enough history to compute either rule

Thresholds come from outputs/tuned_thresholds.json if backtest --tune wrote it,
otherwise from config/settings.toml.

Run:
    python -m src.lakes.anomaly --lake shisper
Writes outputs/<lake>_alerts.csv.
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from src.common import OUTPUTS, out_path, settings

TIERS = ["no_baseline", "normal", "watch", "warning", "alert"]
TIER_RANK = {t: i for i, t in enumerate(TIERS)}


def thresholds() -> dict:
    """Active thresholds and where they came from."""
    cfg = settings()["alerts"]
    th = {"watch": dict(cfg["watch"]), "warning": dict(cfg["warning"]),
          "consecutive_warnings": cfg["alert"]["consecutive_warnings"],
          "source": "config/settings.toml (untuned defaults)"}
    tuned = OUTPUTS / "tuned_thresholds.json"
    if tuned.exists():
        t = json.loads(tuned.read_text())
        th["watch"], th["warning"] = t["watch"], t["warning"]
        th["source"] = f"outputs/tuned_thresholds.json (tuned on {t['tune_start']} to {t['tune_end']})"
    return th


def load_area(lake: str, sensor: str = "s2") -> pd.DataFrame:
    path = OUTPUTS / f"{lake}_area.csv"
    if not path.exists():
        raise FileNotFoundError(f"{path} missing. Run: python -m src.lakes.lake_area --lake {lake}")
    df = pd.read_csv(path, parse_dates=["date"])
    df = df[df["sensor"] == sensor].sort_values("date")
    # rolling time windows need a unique, sorted DatetimeIndex
    return df.groupby("date", as_index=True).last()


def add_alerts(df: pd.DataFrame, th: dict | None = None) -> pd.DataFrame:
    th = th or thresholds()
    cfg = settings()["alerts"]
    df = df.copy()
    a = df["area_km2"]

    roll = a.rolling(cfg["baseline"], closed="left")
    med = roll.median()
    n = roll.count()
    mad = (a - med).abs().rolling(cfg["baseline"], closed="left").median()
    z = (a - med) / (1.4826 * mad + 1e-4)
    df["z"] = z.where(n >= cfg["min_baseline_obs"])
    df["baseline_median"] = med.where(n >= cfg["min_baseline_obs"])
    df["baseline_mad"] = mad.where(n >= cfg["min_baseline_obs"])
    df["baseline_n"] = n

    prev = a.shift(1)
    days = df.index.to_series().diff().dt.days
    growth = ((a - prev) / prev.clip(lower=1e-3)) * (cfg["growth_window_days"] / days)
    df["growth_15d"] = growth.where(days <= cfg["max_gap_days"])

    z_, g_ = df["z"].fillna(-np.inf), df["growth_15d"].fillna(-np.inf)
    watch = (z_ > th["watch"]["z"]) | (g_ > th["watch"]["growth"])
    warn = (z_ > th["warning"]["z"]) | (g_ > th["warning"]["growth"])
    both = (z_ > th["warning"]["z"]) & (g_ > th["warning"]["growth"])
    k = th["consecutive_warnings"]
    run = warn.astype(int).rolling(k, min_periods=k).sum().eq(k)
    alert = both | run

    tier = np.select([alert, warn, watch], ["alert", "warning", "watch"], default="normal")
    no_base = df["z"].isna() & df["growth_15d"].isna()
    df["tier"] = np.where(no_base, "no_baseline", tier)
    df["warning"] = df["tier"].isin(["warning", "alert"])
    return df


def main():
    p = argparse.ArgumentParser(description="Compute alert tiers for a lake")
    p.add_argument("--lake", required=True)
    p.add_argument("--sensor", default="s2")
    args = p.parse_args()

    th = thresholds()
    df = add_alerts(load_area(args.lake, args.sensor), th)
    path = out_path(f"{args.lake}_alerts.csv")
    df.to_csv(path)
    last = df.iloc[-1]
    print(f"Thresholds from {th['source']}")
    print(f"{len(df)} observations -> {path}")
    print(f"Latest {df.index[-1].date()}: area {last['area_km2']:.3f} km², tier {last['tier']}")


if __name__ == "__main__":
    main()
