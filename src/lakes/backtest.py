"""Back-test the lake alert rules against known events.

Honesty rules enforced here:
  - thresholds are tuned only on [backtest].tune_start..tune_end
  - an event with role=test inside the tuning period is reported as a violation
  - every number in the report is computed below from outputs/<lake>_area.csv

Run:
    python -m src.lakes.backtest --tune     # fit thresholds on 2019-2021, then report
    python -m src.lakes.backtest            # report with current thresholds
Writes outputs/backtest_report.md, outputs/backtest_summary.csv,
outputs/backtest_<lake>_<date>.png and (with --tune) outputs/tuned_thresholds.json.
"""

from __future__ import annotations

import argparse
import itertools
import json
from datetime import date

import matplotlib
import pandas as pd

from src.common import OUTPUTS, events, out_path, settings
from src.lakes.anomaly import add_alerts, load_area, thresholds

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

TIER_COLORS = {"watch": "#B7791F", "warning": "#C2581C", "alert": "#B42318"}


def available_series(lakes) -> dict[str, tuple[str, pd.DataFrame]]:
    """lake -> (sensor, area df). Prefers S2; falls back to Landsat (partial)."""
    out = {}
    for lake in lakes:
        for sensor in ("s2", "landsat"):
            try:
                df = load_area(lake, sensor)
            except FileNotFoundError:
                break
            if len(df):
                out[lake] = (sensor, df)
                break
    return out


def in_any_window(idx: pd.DatetimeIndex, ev_dates, lead_days: int) -> pd.Series:
    mask = pd.Series(False, index=idx)
    for d in ev_dates:
        mask |= (idx >= d - pd.Timedelta(days=lead_days)) & (idx < d)
    return mask


def false_alerts(df: pd.DataFrame, ev_dates, lead_days: int) -> tuple[int, int]:
    """Warnings outside every pre-event window, and number of seasons covered."""
    if df.empty:
        return 0, 0
    inside = in_any_window(df.index, ev_dates, lead_days)
    fa = int((df["warning"] & ~inside).sum())
    return fa, df.index.year.nunique()


def tune(series, ev: pd.DataFrame, cfg: dict) -> dict:
    bt = cfg["backtest"]
    t0, t1 = pd.Timestamp(bt["tune_start"]), pd.Timestamp(bt["tune_end"])
    tune_events = ev[(ev["date"] >= t0) & (ev["date"] <= t1)]
    if (tune_events["role"] == "test").any():
        raise SystemExit("A test event falls inside the tuning period. Fix config/events.csv "
                         "or the tuning dates: never tune on the test event.")
    rows = []
    base = thresholds()
    for z, g in itertools.product(bt["z_grid"], bt["growth_grid"]):
        th = {**base, "warning": {"z": z, "growth": g},
              "watch": {"z": round(z * 2 / 3, 2), "growth": round(g * 0.6, 3)}}
        fa_total, seasons, hits = 0, 0, 0
        for lake, (_, area) in series.items():
            full = add_alerts(area, th)
            win = full[(full.index >= t0) & (full.index <= t1)]
            lake_ev = tune_events[tune_events["lake"] == lake]["date"]
            fa, s = false_alerts(win, lake_ev, bt["lead_window_days"])
            fa_total, seasons = fa_total + fa, seasons + s
            for d in lake_ev:
                pre = win[(win.index >= d - pd.Timedelta(days=bt["lead_window_days"]))
                          & (win.index < d)]
                hits += int(pre["warning"].any())
        rows.append({"z": z, "growth": g, "false_alerts": fa_total, "seasons": seasons,
                     "false_per_season": fa_total / seasons if seasons else float("nan"),
                     "tune_event_hits": hits})
    grid = pd.DataFrame(rows)
    grid.to_csv(out_path("tuning_grid.csv"), index=False)
    if grid["seasons"].max() == 0:
        raise SystemExit(f"No observations between {bt['tune_start']} and {bt['tune_end']}; "
                         "cannot tune. Run lake_area.py over that period first.")
    ok = grid[grid["false_per_season"] <= bt["max_false_per_season"]]
    pick = (ok if len(ok) else grid.sort_values("false_per_season").head(1))
    best = pick.sort_values(["tune_event_hits", "z", "growth"],
                            ascending=[False, True, True]).iloc[0]
    result = {"warning": {"z": float(best["z"]), "growth": float(best["growth"])},
              "watch": {"z": round(float(best["z"]) * 2 / 3, 2),
                        "growth": round(float(best["growth"]) * 0.6, 3)},
              "tune_start": bt["tune_start"], "tune_end": bt["tune_end"],
              "false_per_season": float(best["false_per_season"]),
              "tune_event_hits": int(best["tune_event_hits"]),
              "constraint_met": bool(len(ok)),
              "lakes": sorted(series), "computed_on": date.today().isoformat()}
    out_path("tuned_thresholds.json").write_text(json.dumps(result, indent=2))
    return result


def event_figure(lake, sensor, df, ev_row, lead_days, path):
    d = ev_row["date"]
    w = df[(df.index >= d - pd.Timedelta(days=200)) & (df.index <= d + pd.Timedelta(days=60))]
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.plot(w.index, w["area_km2"], ".-", lw=1, color="#1F6F8B", label="Lake area")
    for tier, color in TIER_COLORS.items():
        t = w[w["tier"] == tier]
        if len(t):
            ax.scatter(t.index, t["area_km2"], color=color, zorder=3, s=22, label=tier.title())
    ax.axvspan(d - pd.Timedelta(days=lead_days), d, color="#14212B", alpha=0.05,
               label=f"{lead_days}-day lead window")
    ax.axvline(d, color="#14212B", ls="--", lw=1)
    ax.set_ylabel("Area (km²)")
    ax.set_title(f"{ev_row['name']} ({d.date()})")
    ax.legend(frameon=False, fontsize=7, loc="upper left")
    src = {"s2": "Sentinel-2 MNDWI", "landsat": "Landsat C2 MNDWI (partial)"}[sensor]
    rng = f"{w.index.min().date()} to {w.index.max().date()}" if len(w) else "no scenes"
    fig.text(0.01, 0.01, f"Source: {src}, Google Earth Engine. Dates {rng}.",
             fontsize=7, color="#4A5862")
    fig.tight_layout(rect=(0, 0.05, 1, 1))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def report(series, ev: pd.DataFrame, cfg: dict) -> str:
    bt = cfg["backtest"]
    th = thresholds()
    t0, t1 = pd.Timestamp(bt["tune_start"]), pd.Timestamp(bt["tune_end"])
    lead = bt["lead_window_days"]
    lines = [
        "# NIGAH lake back-test report", "",
        f"Generated {date.today().isoformat()} by `src/lakes/backtest.py`. "
        "Every number below is computed from `outputs/<lake>_area.csv`.", "",
        "## Thresholds", "",
        f"- Source: {th['source']}",
        f"- Watch: z > {th['watch']['z']} or 15-day growth > {th['watch']['growth']:.0%}",
        f"- Warning: z > {th['warning']['z']} or 15-day growth > {th['warning']['growth']:.0%}",
        f"- Alert: both warning rules on one observation, or {th['consecutive_warnings']} "
        "consecutive warnings",
        f"- Tuning period: {bt['tune_start']} to {bt['tune_end']}. No test event may fall inside it.",
    ]
    tuned = OUTPUTS / "tuned_thresholds.json"
    if tuned.exists():
        t = json.loads(tuned.read_text())
        met = ("met" if t["constraint_met"] else
               "**not met**: no grid point reached the target, so the lowest-false-alarm point was used")
        lines += [f"- Tuning result: {t['false_per_season']:.2f} false warnings per season on the tuning "
                  f"period (target <= {bt['max_false_per_season']}, {met})."]
    lines += [
        "", "## Events", "",
        "| Event | Date | Lake | Sensor | Obs. in window | First warning | Lead time (days) | First watch | Notes |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    summary = []
    for _, e in ev.iterrows():
        notes = []
        if not e["verified"]:
            notes.append("event date/source not verified")
        if e["role"] == "test" and t0 <= e["date"] <= t1:
            notes.append("**VIOLATION: test event inside tuning period**")
        row = {"event": e["name"], "date": e["date"].date().isoformat(), "lake": e["lake"],
               "sensor": "", "obs_in_window": 0, "first_warning": "", "lead_days": None,
               "first_watch": "", "status": "no_data"}
        if e["lake"] not in series:
            notes.append(f"no area series (run lake_area.py --lake {e['lake']})")
        else:
            sensor, area = series[e["lake"]]
            df = add_alerts(area, th)
            if sensor == "landsat" or e["role"] == "partial":
                notes.append("partial: Landsat only, predates Sentinel-2 and AlphaEarth")
            win = df[(df.index >= e["date"] - pd.Timedelta(days=lead)) & (df.index < e["date"])]
            warn = win[win["warning"]]
            watch = win[win["tier"].isin(["watch", "warning", "alert"])]
            row.update(sensor=sensor, obs_in_window=len(win),
                       status="hit" if len(warn) else ("miss" if len(win) else "no_obs"))
            if len(warn):
                row["first_warning"] = warn.index[0].date().isoformat()
                row["lead_days"] = int((e["date"] - warn.index[0]).days)
            if len(watch):
                row["first_watch"] = watch.index[0].date().isoformat()
            if not len(win):
                notes.append(f"no clear scenes in the {lead} days before")
            fig = out_path(f"backtest_{e['lake']}_{e['date'].date()}.png")
            event_figure(e["lake"], sensor, df, e, lead, fig)
            notes.append(f"figure: `{fig.name}`")
        row["notes"] = "; ".join(notes)
        summary.append(row)
        lines.append(f"| {row['event']} | {row['date']} | {row['lake']} | {row['sensor'] or '-'} | "
                     f"{row['obs_in_window']} | {row['first_warning'] or '-'} | "
                     f"{row['lead_days'] if row['lead_days'] is not None else '-'} | "
                     f"{row['first_watch'] or '-'} | {row['notes']} |")

    lines += ["", "## False alerts per season (test period, after tuning)", "",
              "| Lake | Sensor | Seasons | Warnings outside pre-event windows | Per season |",
              "|---|---|---|---|---|"]
    for lake, (sensor, area) in series.items():
        df = add_alerts(area, th)
        test = df[df.index > t1]
        fa, seasons = false_alerts(test, ev[ev["lake"] == lake]["date"], lead)
        per = f"{fa / seasons:.2f}" if seasons else "-"
        lines.append(f"| {lake} | {sensor} | {seasons} | {fa} | {per} |")

    lines += ["", "## Missing data", "",
              "- Attabad 2010 predates Sentinel-2 (2015) and AlphaEarth (2017): "
              "only Landsat 5/7 scenes exist, so its result is partial.",
              "- Lakes without a drawn AOI in `config/aoi.geojson` have no series.", ""]
    pd.DataFrame(summary).to_csv(out_path("backtest_summary.csv"), index=False)
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description="Back-test lake alert rules")
    p.add_argument("--tune", action="store_true", help="fit thresholds on the tuning period first")
    args = p.parse_args()

    cfg = settings()
    ev = events()
    series = available_series(sorted(set(ev["lake"])))
    if not series:
        raise SystemExit(f"No area series in {OUTPUTS}. Run src.lakes.lake_area first.")
    if args.tune:
        res = tune(series, ev, cfg)
        print(f"Tuned on {res['tune_start']}..{res['tune_end']}: warning z>{res['warning']['z']}, "
              f"growth>{res['warning']['growth']:.0%}, {res['false_per_season']:.2f} false/season")
    md = report(series, ev, cfg)
    path = out_path("backtest_report.md")
    path.write_text(md, encoding="utf-8")
    print(f"Report -> {path}")


if __name__ == "__main__":
    main()
