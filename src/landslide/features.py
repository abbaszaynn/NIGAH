"""Landslide feature stack and samples from Google Earth Engine.

Inputs
  config/landslide_points.csv   lon,lat,source  (positives: NASA GLC + digitized scars)
  config/kkh_line.geojson       optional KKH centreline  -> dist_road
  config/faults.geojson         optional fault traces    -> dist_fault

Features (30 m unless noted)
  elevation, slope, aspect_sin, aspect_cos, curvature (Laplacian of GLO30 DEM)
  dist_drainage   distance to HydroSHEDS flow accumulation > 500 cells
  ndvi            Sentinel-2 Jun-Sep median of the AlphaEarth year
  rain_mm_yr      CHIRPS mean annual precipitation 2017 onwards
  A00..A63        AlphaEarth annual embedding (10 m, resampled)

Run:
    python -m src.landslide.features --project YOUR_GEE_PROJECT
Writes outputs/landslide_samples.csv and outputs/landslide_grid.npz (prediction grid).
"""

from __future__ import annotations

import argparse
import json

import numpy as np
import pandas as pd

from src.common import ALPHAEARTH_ATTRIBUTION, CONFIG, aoi, ee_geometry, init_ee, out_path, settings

GRID_SCALE_DEG = 0.0006  # ~60 m prediction grid; keeps computePixels under its size cap


def _dist(ee, fc_path, geom, name):
    if not fc_path.exists():
        return None
    gj = json.loads(fc_path.read_text(encoding="utf-8"))
    fc = ee.FeatureCollection(gj)
    return (ee.Image().byte().paint(fc, 1).unmask(0).fastDistanceTransform(256)
            .sqrt().multiply(ee.Image.pixelArea().sqrt()).rename(name).clip(geom.buffer(5000)))


def feature_image(ee, geom, year: int):
    dem = (ee.ImageCollection("COPERNICUS/DEM/GLO30").select("DEM").filterBounds(geom)
           .mosaic().setDefaultProjection("EPSG:4326", None, 30))
    terrain = ee.Terrain.products(dem)
    aspect = terrain.select("aspect").multiply(np.pi / 180)
    curvature = dem.convolve(ee.Kernel.laplacian8()).rename("curvature")

    acc = ee.Image("WWF/HydroSHEDS/15ACC").select("b1")
    streams = acc.gt(500).selfMask()
    dist_drain = (streams.unmask(0).fastDistanceTransform(256).sqrt()
                  .multiply(ee.Image.pixelArea().sqrt()).rename("dist_drainage"))

    ndvi = (ee.ImageCollection("COPERNICUS/S2_HARMONIZED").filterBounds(geom)
            .filterDate(f"{year}-06-01", f"{year}-09-30")
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 30))
            .median().normalizedDifference(["B8", "B4"]).rename("ndvi"))

    rain = (ee.ImageCollection("UCSB-CHG/CHIRPS/DAILY").filterDate("2017-01-01", f"{year + 1}-01-01")
            .sum().divide(year - 2017 + 1).rename("rain_mm_yr"))

    emb = (ee.ImageCollection("GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL").filterBounds(geom)
           .filterDate(f"{year}-01-01", f"{year + 1}-01-01").mosaic())

    bands = [dem.rename("elevation"), terrain.select("slope"),
             aspect.sin().rename("aspect_sin"), aspect.cos().rename("aspect_cos"),
             curvature, dist_drain, ndvi, rain, emb]
    for path, name in [(CONFIG / "kkh_line.geojson", "dist_road"),
                       (CONFIG / "faults.geojson", "dist_fault")]:
        d = _dist(ee, path, geom, name)
        if d is not None:
            bands.append(d)
    return ee.Image.cat(bands).toFloat()


def samples(ee, img, geom, cfg) -> pd.DataFrame:
    pts_path = CONFIG / "landslide_points.csv"
    if not pts_path.exists():
        raise SystemExit("config/landslide_points.csv missing (columns lon,lat,source). "
                         "Add 150-300 landslide points from the NASA Global Landslide Catalog "
                         "and digitized scars.")
    pts = pd.read_csv(pts_path)
    if len(pts) < 150:
        print(f"Note: only {len(pts)} positives; the plan asks for 150-300.")
    pos = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([r.lon, r.lat]), {"label": 1})
                                for r in pts.itertuples()])
    lc = cfg["landslide"]
    # negatives: random points in the AOI, at least 250 m from any positive
    exclusion = pos.geometry().buffer(250)
    neg = (ee.FeatureCollection.randomPoints(geom.difference(exclusion, 1),
                                             len(pts) * lc["negative_ratio"], lc["seed"])
           .map(lambda f: f.set("label", 0)))
    fc = img.sampleRegions(pos.merge(neg), ["label"], 30, geometries=True)
    rows = []
    for f in fc.getInfo()["features"]:
        lon, lat = f["geometry"]["coordinates"]
        rows.append({"lon": lon, "lat": lat, **f["properties"]})
    return pd.DataFrame(rows)


def grid(ee, img, geom) -> dict:
    ring = geom.bounds().coordinates().getInfo()[0]
    xs, ys = [c[0] for c in ring], [c[1] for c in ring]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    w, h = int((x1 - x0) / GRID_SCALE_DEG), int((y1 - y0) / GRID_SCALE_DEG)
    arr = ee.data.computePixels({
        "expression": img.clip(geom),
        "fileFormat": "NUMPY_NDARRAY",
        "grid": {"dimensions": {"width": w, "height": h},
                 "affineTransform": {"scaleX": GRID_SCALE_DEG, "shearX": 0, "translateX": x0,
                                     "shearY": 0, "scaleY": -GRID_SCALE_DEG, "translateY": y1},
                 "crsCode": "EPSG:4326"}})
    names = list(arr.dtype.names)
    stack = np.stack([arr[n].astype("float32") for n in names], axis=-1)
    return {"stack": stack, "bands": np.array(names),
            "transform": np.array([x0, GRID_SCALE_DEG, y1, -GRID_SCALE_DEG])}


def main():
    cfg = settings()
    p = argparse.ArgumentParser(description="Build landslide features")
    p.add_argument("--project")
    p.add_argument("--no-grid", action="store_true", help="skip the prediction grid download")
    args = p.parse_args()

    ee = init_ee(args.project)
    geom = ee_geometry(aoi(cfg["landslide"]["aoi"]))
    img = feature_image(ee, geom, cfg["landslide"]["alphaearth_year"])

    df = samples(ee, img, geom, cfg)
    df.to_csv(out_path("landslide_samples.csv"), index=False)
    print(f"{len(df)} samples ({int(df['label'].sum())} positives) -> outputs/landslide_samples.csv")
    if not args.no_grid:
        g = grid(ee, img, geom)
        np.savez_compressed(out_path("landslide_grid.npz"), **g)
        print(f"Prediction grid {g['stack'].shape} -> outputs/landslide_grid.npz")
    print(ALPHAEARTH_ATTRIBUTION)


if __name__ == "__main__":
    main()
