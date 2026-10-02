"""Weekly lake check: refresh recent scenes, recompute tiers, log and send new alerts.

For every lake AOI with a geometry:
  1. pull the last --days of Sentinel-2 (+S1) scenes and merge into outputs/<lake>_area.csv
  2. recompute tiers with the active thresholds
  3. append observations at watch or above that are not yet logged to outputs/alert_log.csv
  4. send each new one to Telegram

Run (GitHub Actions does this weekly):
    python -m src.alerts.check --project YOUR_GEE_PROJECT
    python -m src.alerts.check --no-refresh     # recompute from existing CSVs only
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone

import pandas as pd

from src.alerts.telegram import lake_message, send
from src.common import OUTPUTS, aois, out_path, settings
from src.lakes import qa
from src.lakes.anomaly import add_alerts, load_area, thresholds

LOG_COLS = ["logged_at", "lake", "date", "sensor", "tier", "area_km2", "z", "growth_15d", "sent"]


def refresh(lake: str, days: int, project: str | None):
    from src.lakes.lake_area import lake_series

    cfg = settings()
    end = date.today()
    start = (pd.Timestamp(end) - pd.Timedelta(days=days)).date()
    sensors = ["s2", "s1"] if cfg["lakes"]["s1"]["enabled"] else ["s2"]
    new = lake_series(lake, sensors, start.isoformat(), end.isoformat(), project)
    path = OUTPUTS / f"{lake}_area.csv"
    old = pd.read_csv(path, parse_dates=["date"]) if path.exists() else new.iloc[:0]
    merged = (pd.concat([old, new]).drop_duplicates(["date", "sensor"], keep="last")
              .sort_values("date"))
    merged.to_csv(out_path(f"{lake}_area.csv"), index=False)
    print(f"  {lake}: +{len(new)} recent observations")


def main():
    p = argparse.ArgumentParser(description="Weekly lake check")
    p.add_argument("--project")
    p.add_argument("--days", type=int, default=120, help="refresh window")
    p.add_argument("--no-refresh", action="store_true")
    p.add_argument("--no-send", action="store_true")
    args = p.parse_args()

    th = thresholds()
    log_path = OUTPUTS / "alert_log.csv"
    log = pd.read_csv(log_path) if log_path.exists() else pd.DataFrame(columns=LOG_COLS)
    seen = set(zip(log["lake"], log["date"].astype(str), log["sensor"]))
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    new_rows = []
    for lake_id, feat in aois().items():
        if feat["properties"]["kind"] != "lake" or feat["geometry"] is None:
            continue
        if not args.no_refresh:
            refresh(lake_id, args.days, args.project)
        try:
            df = add_alerts(load_area(lake_id, "s2"), th)
        except FileNotFoundError:
            print(f"  {lake_id}: no area series yet")
            continue
        df.to_csv(out_path(f"{lake_id}_alerts.csv"))
        issues = qa.check(pd.read_csv(OUTPUTS / f"{lake_id}_area.csv"), feat)
        if qa.failed(issues):
            print(f"  {lake_id}: QA failed, alerts suppressed: "
                  + "; ".join(i["message"] for i in issues if i["level"] == "fail"))
            continue
        hits = df[df["tier"].isin(["watch", "warning", "alert"])]
        for d, r in hits.iterrows():
            key = (lake_id, d.date().isoformat(), "s2")
            if key in seen:
                continue
            row = {"logged_at": now, "lake": lake_id, "date": key[1], "sensor": "s2",
                   "tier": r["tier"], "area_km2": r["area_km2"], "z": r["z"],
                   "growth_15d": r["growth_15d"], "sent": False}
            # only push recent observations; old back-filled ones are logged quietly
            recent = (pd.Timestamp(now).tz_localize(None) - d).days <= args.days
            if recent and not args.no_send:
                row["sent"] = send(lake_message(feat["properties"]["name"], row, th["source"]))
            new_rows.append(row)

    if new_rows:
        log = pd.concat([log, pd.DataFrame(new_rows)], ignore_index=True)
    log.to_csv(out_path("alert_log.csv"), index=False)
    print(f"{len(new_rows)} new alert-log entries -> {log_path}")


if __name__ == "__main__":
    main()
