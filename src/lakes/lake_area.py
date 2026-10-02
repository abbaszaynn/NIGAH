"""Glacial-lake area time series from Sentinel-2 (+ Sentinel-1, + Landsat).

Water rules
  S2:      MNDWI(B3, B11) > t  AND slope < 10 deg AND lit (not terrain shadow)
           AND Cloud Score+ cs_cdf >= 0.6. Scenes kept if >= 80% of AOI usable.
  S1:      focal-median VV < t dB AND slope < 10 deg. Fills cloudy gaps.
           Wet snow and radar shadow also read dark: treat S1 as gap-fill only.
  Landsat: MNDWI(green, swir1) on Collection 2 L2 with QA_PIXEL cloud mask.
           For pre-2016 history (e.g. Attabad 2010). Labelled partial.

Run:
    python -m src.lakes.lake_area --lake shisper --project YOUR_GEE_PROJECT
    python -m src.lakes.lake_area --lake attabad --sensors landsat --start 2009-01-01 --end 2011-12-31

Writes outputs/<lake>_area.csv (one row per date per sensor) and outputs/<lake>_area.png.
"""

from __future__ import annotations

import argparse

import matplotlib
import pandas as pd

from src.common import aoi, ee_geometry, init_ee, out_path, settings

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

LANDSAT = {
    # collection: (green, swir1)
    "LANDSAT/LT05/C02/T1_L2": ("SR_B2", "SR_B5"),
    "LANDSAT/LE07/C02/T1_L2": ("SR_B2", "SR_B5"),
    "LANDSAT/LC08/C02/T1_L2": ("SR_B3", "SR_B6"),
    "LANDSAT/LC09/C02/T1_L2": ("SR_B3", "SR_B6"),
}


def _terrain(ee, geom, max_slope):
    dem = (ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM")
           .filterBounds(geom).mosaic()
           .setDefaultProjection("EPSG:4326", None, 30))
    return dem, ee.Terrain.slope(dem).lt(max_slope)


def _stats(ee, water, valid, geom, scale, date, sensor, scene):
    stats = (ee.Image.cat(water.rename("water"), valid.rename("valid"))
             .multiply(ee.Image.pixelArea())
             .reduceRegion(ee.Reducer.sum(), geom, scale, maxPixels=1e9))
    return ee.Feature(None, {"date": date, "water_m2": stats.get("water"),
                             "valid_m2": stats.get("valid"), "sensor": sensor,
                             "scene": scene})


def s2_collection(ee, geom, start, end, cfg):
    s2c = cfg["lakes"]["s2"]
    months = cfg["lakes"]["months"]
    dem, flat = _terrain(ee, geom, s2c["max_slope_deg"])
    cs = ee.ImageCollection("GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED")
    col = (ee.ImageCollection("COPERNICUS/S2_HARMONIZED")
           .filterBounds(geom).filterDate(start, end)
           .filter(ee.Filter.calendarRange(months[0], months[1], "month"))
           .linkCollection(cs, ["cs_cdf"])
           .filter(ee.Filter.listContains("system:band_names", "cs_cdf")))

    def measure(img):
        clear = img.select("cs_cdf").gte(s2c["clear_threshold"])
        lit = ee.Terrain.hillShadow(dem, img.getNumber("MEAN_SOLAR_AZIMUTH_ANGLE"),
                                    img.getNumber("MEAN_SOLAR_ZENITH_ANGLE"), 100, True)
        valid = clear.And(lit)
        mndwi = img.normalizedDifference(["B3", "B11"])
        water = mndwi.gt(s2c["mndwi_threshold"]).And(flat).And(valid)
        return _stats(ee, water, valid, geom, cfg["lakes"]["scale_m"],
                      img.date().format("YYYY-MM-dd"), "s2", img.get("system:index"))

    return col.map(measure)


def s1_collection(ee, geom, start, end, cfg):
    s1c = cfg["lakes"]["s1"]
    months = cfg["lakes"]["months"]
    _, flat = _terrain(ee, geom, cfg["lakes"]["s2"]["max_slope_deg"])
    col = (ee.ImageCollection("COPERNICUS/S1_GRD")
           .filterBounds(geom).filterDate(start, end)
           .filter(ee.Filter.calendarRange(months[0], months[1], "month"))
           .filter(ee.Filter.eq("instrumentMode", "IW"))
           .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VV")))

    def measure(img):
        vv = img.select("VV").focalMedian(s1c["speckle_radius_m"], "circle", "meters")
        valid = vv.mask().gt(0)
        water = vv.lt(s1c["vv_threshold_db"]).And(flat).And(valid)
        return _stats(ee, water, valid, geom, 10,
                      img.date().format("YYYY-MM-dd"), "s1", img.get("system:index"))

    return col.map(measure)


def landsat_collection(ee, geom, start, end, cfg):
    s2c = cfg["lakes"]["s2"]
    months = cfg["lakes"]["months"]
    dem, flat = _terrain(ee, geom, s2c["max_slope_deg"])
    merged = None
    for coll_id, (green, swir) in LANDSAT.items():
        col = (ee.ImageCollection(coll_id).filterBounds(geom).filterDate(start, end)
               .filter(ee.Filter.calendarRange(months[0], months[1], "month")))

        def measure(img, green=green, swir=swir):
            qa = img.select("QA_PIXEL")
            # bits: 1 dilated cloud, 3 cloud, 4 cloud shadow
            clear = (qa.bitwiseAnd(1 << 1).eq(0).And(qa.bitwiseAnd(1 << 3).eq(0))
                     .And(qa.bitwiseAnd(1 << 4).eq(0)))
            refl = img.select([green, swir]).multiply(0.0000275).add(-0.2)
            lit = ee.Terrain.hillShadow(dem, img.getNumber("SUN_AZIMUTH"),
                                        ee.Number(90).subtract(img.getNumber("SUN_ELEVATION")),
                                        100, True)
            valid = clear.And(lit).And(refl.select(green).mask())
            mndwi = refl.normalizedDifference([green, swir])
            water = mndwi.gt(s2c["mndwi_threshold"]).And(flat).And(valid)
            return _stats(ee, water, valid, geom, 30, img.date().format("YYYY-MM-dd"),
                          "landsat", img.get("system:index"))

        mapped = col.map(measure)
        merged = mapped if merged is None else merged.merge(mapped)
    return merged


SENSORS = {"s2": s2_collection, "s1": s1_collection, "landsat": landsat_collection}


def lake_series(lake: str, sensors: list[str], start: str, end: str,
                project: str | None = None) -> pd.DataFrame:
    ee = init_ee(project)
    cfg = settings()
    geom = ee_geometry(aoi(lake))
    aoi_m2 = geom.area(1).getInfo()

    rows = []
    # Chunk by year so each getInfo stays inside the EE compute limit.
    years = range(pd.Timestamp(start).year, pd.Timestamp(end).year + 1)
    for sensor in sensors:
        for y in years:
            y0 = max(pd.Timestamp(start), pd.Timestamp(f"{y}-01-01"))
            y1 = min(pd.Timestamp(end), pd.Timestamp(f"{y}-12-31"))
            fc = ee.FeatureCollection(SENSORS[sensor](ee, geom, y0.strftime("%Y-%m-%d"),
                                                      y1.strftime("%Y-%m-%d"), cfg))
            feats = fc.getInfo()["features"]
            rows += [f["properties"] for f in feats]
            print(f"  {sensor} {y}: {len(feats)} scenes")

    if not rows:
        return pd.DataFrame(columns=["date", "sensor", "area_km2", "valid_frac", "scene"])
    df = pd.DataFrame(rows).dropna(subset=["water_m2", "valid_m2"])
    df["date"] = pd.to_datetime(df["date"])
    df["valid_frac"] = df["valid_m2"] / aoi_m2
    # one row per date and sensor: the scene with the most usable pixels
    df = (df.sort_values("valid_frac").groupby(["date", "sensor"]).tail(1)
            .sort_values("date"))
    min_clear = cfg["lakes"]["s2"]["min_clear_frac"]
    df = df[df["valid_frac"] >= min_clear].copy()
    df["area_km2"] = df["water_m2"] / 1e6
    return df[["date", "sensor", "area_km2", "valid_frac", "scene"]].reset_index(drop=True)


def plot(df: pd.DataFrame, lake_name: str, path) -> None:
    fig, ax = plt.subplots(figsize=(11, 4))
    styles = {"s2": ("#1F6F8B", "o", "Sentinel-2 MNDWI"),
              "s1": ("#8A6A2F", "^", "Sentinel-1 VV (gap-fill)"),
              "landsat": ("#5B5B8F", "s", "Landsat MNDWI")}
    for sensor, g in df.groupby("sensor"):
        color, marker, label = styles[sensor]
        ax.plot(g["date"], g["area_km2"], marker=marker, ms=3, lw=0.8, color=color, label=label)
    ax.set_ylabel("Lake area (km²)")
    ax.set_title(f"{lake_name}: water area within AOI (Apr-Oct scenes)")
    ax.legend(frameon=False)
    d0, d1 = df["date"].min().date(), df["date"].max().date()
    fig.text(0.01, 0.01, f"Source: {', '.join(styles[s][2] for s in sorted(df['sensor'].unique()))}"
             f" via Google Earth Engine. Dates {d0} to {d1}.", fontsize=7, color="#4A5862")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(path, dpi=150)
    plt.close(fig)


def main():
    cfg = settings()
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--lake", required=True, help="AOI id from config/aoi.geojson")
    p.add_argument("--project", help="GEE Cloud project id")
    p.add_argument("--sensors", default="s2,s1" if cfg["lakes"]["s1"]["enabled"] else "s2",
                   help="comma list of s2,s1,landsat")
    p.add_argument("--start", default=cfg["lakes"]["start"])
    p.add_argument("--end", default=cfg["lakes"]["end"])
    args = p.parse_args()

    feat = aoi(args.lake)
    sensors = [s.strip() for s in args.sensors.split(",") if s.strip()]
    df = lake_series(args.lake, sensors, args.start, args.end, args.project)
    csv = out_path(f"{args.lake}_area.csv")
    df.to_csv(csv, index=False)
    if df.empty:
        print(f"No clear observations for {args.lake}. Wrote empty {csv}")
        return
    plot(df, feat["properties"]["name"], out_path(f"{args.lake}_area.png"))
    print(f"{len(df)} clear observations ({', '.join(sensors)}), "
          f"{df['date'].min().date()} to {df['date'].max().date()} -> {csv}")


if __name__ == "__main__":
    main()
