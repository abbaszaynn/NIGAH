"""LightGBM landslide susceptibility with spatial block cross-validation.

Compares out-of-fold AUC for terrain-only vs terrain + AlphaEarth features.
No random splits: samples are grouped into square blocks ([landslide].block_size_km)
and whole blocks are held out together (GroupKFold).

Run:
    python -m src.landslide.train
Reads  outputs/landslide_samples.csv (+ outputs/landslide_grid.npz for the map)
Writes outputs/landslide_auc.csv, outputs/landslide_shap.png,
       outputs/susceptibility.tif, outputs/susceptibility.png, outputs/susceptibility_bounds.json
"""

from __future__ import annotations

import json

import lightgbm as lgb
import matplotlib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import GroupKFold

from src.common import ALPHAEARTH_ATTRIBUTION, OUTPUTS, out_path, settings

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

TERRAIN = ["elevation", "slope", "aspect_sin", "aspect_cos", "curvature", "dist_drainage",
           "ndvi", "rain_mm_yr", "dist_road", "dist_fault"]
PARAMS = dict(n_estimators=400, learning_rate=0.03, num_leaves=15, min_child_samples=10,
              subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1)


def blocks(df: pd.DataFrame, km: float) -> pd.Series:
    lat0 = np.deg2rad(df["lat"].mean())
    bx = np.floor(df["lon"] * 111.32 * np.cos(lat0) / km).astype(int)
    by = np.floor(df["lat"] * 110.57 / km).astype(int)
    return bx.astype(str) + "_" + by.astype(str)


def spatial_cv(df, feats, groups, n_folds, seed) -> dict:
    n_folds = min(n_folds, groups.nunique())
    oof = np.full(len(df), np.nan)
    fold_auc = []
    for tr, te in GroupKFold(n_splits=n_folds).split(df, df["label"], groups):
        if df["label"].iloc[te].nunique() < 2:
            continue  # a block set with one class has no AUC
        m = lgb.LGBMClassifier(random_state=seed, **PARAMS).fit(df[feats].iloc[tr], df["label"].iloc[tr])
        oof[te] = m.predict_proba(df[feats].iloc[te])[:, 1]
        fold_auc.append(roc_auc_score(df["label"].iloc[te], oof[te]))
    ok = ~np.isnan(oof)
    return {"auc_oof": roc_auc_score(df["label"][ok], oof[ok]),
            "auc_fold_mean": float(np.mean(fold_auc)), "auc_fold_std": float(np.std(fold_auc)),
            "folds_scored": len(fold_auc), "n_features": len(feats)}


def write_map(model, feats, grid_path):
    g = np.load(grid_path, allow_pickle=False)
    stack, bands, (x0, dx, y1, dy) = g["stack"], list(g["bands"]), g["transform"]
    h, w, _ = stack.shape
    X = pd.DataFrame(stack.reshape(-1, len(bands)), columns=bands)[feats]
    valid = X.notna().all(axis=1).to_numpy()
    prob = np.full(len(X), np.nan, dtype="float32")
    prob[valid] = model.predict_proba(X[valid])[:, 1]
    prob = prob.reshape(h, w)

    try:
        import rasterio
        from rasterio.transform import from_origin
        with rasterio.open(out_path("susceptibility.tif"), "w", driver="GTiff", height=h, width=w,
                           count=1, dtype="float32", crs="EPSG:4326", nodata=np.nan,
                           transform=from_origin(x0, y1, dx, -dy)) as dst:
            dst.write(prob, 1)
    except ImportError:
        np.save(out_path("susceptibility.npy"), prob)
        print("rasterio not installed: wrote susceptibility.npy instead of GeoTIFF")

    cmap = matplotlib.colormaps["YlOrRd"]
    rgba = (cmap(np.nan_to_num(prob)) * 255).astype("uint8")
    rgba[..., 3] = np.where(np.isnan(prob), 0, 170)
    plt.imsave(out_path("susceptibility.png"), rgba)
    bounds = {"west": float(x0), "east": float(x0 + w * dx),
              "north": float(y1), "south": float(y1 + h * dy)}
    out_path("susceptibility_bounds.json").write_text(json.dumps(bounds))


def main():
    cfg = settings()["landslide"]
    path = OUTPUTS / "landslide_samples.csv"
    if not path.exists():
        raise SystemExit(f"{path} missing. Run: python -m src.landslide.features")
    df = pd.read_csv(path)
    terrain = [c for c in TERRAIN if c in df.columns]
    alpha = [c for c in df.columns if c.startswith("A") and c[1:].isdigit()]
    groups = blocks(df, cfg["block_size_km"])
    print(f"{len(df)} samples, {int(df['label'].sum())} positives, {groups.nunique()} spatial blocks")

    sets = {"terrain": terrain, "terrain+alphaearth": terrain + alpha}
    if not alpha:
        del sets["terrain+alphaearth"]
        print("No AlphaEarth columns in samples; comparing terrain only.")
    rows = []
    for name, feats in sets.items():
        r = spatial_cv(df, feats, groups, cfg["n_folds"], cfg["seed"])
        rows.append({"feature_set": name, **r})
        print(f"{name:>20}: OOF AUC {r['auc_oof']:.3f} "
              f"(fold mean {r['auc_fold_mean']:.3f} ± {r['auc_fold_std']:.3f}, {r['folds_scored']} folds)")
    auc = pd.DataFrame(rows)
    auc["cv"] = f"GroupKFold on {cfg['block_size_km']} km blocks"
    auc.to_csv(out_path("landslide_auc.csv"), index=False)

    best = auc.sort_values("auc_oof", ascending=False).iloc[0]["feature_set"]
    feats = sets[best]
    model = lgb.LGBMClassifier(random_state=cfg["seed"], **PARAMS).fit(df[feats], df["label"])

    import shap
    sv = shap.TreeExplainer(model).shap_values(df[feats])
    sv = sv[1] if isinstance(sv, list) else sv
    plt.figure()
    shap.summary_plot(sv, df[feats], max_display=20, show=False)
    caption = (f"SHAP for LightGBM ({best}), {len(df)} samples. GLO30 DEM, HydroSHEDS, S2 NDVI, "
               f"CHIRPS, AlphaEarth {cfg['alphaearth_year']}.")
    plt.gcf().text(0.01, 0.005, caption, fontsize=7, color="#4A5862")
    plt.tight_layout(rect=(0, 0.03, 1, 1))
    plt.savefig(out_path("landslide_shap.png"), dpi=150)
    plt.close()

    grid = OUTPUTS / "landslide_grid.npz"
    if grid.exists():
        write_map(model, feats, grid)
        print("Susceptibility map -> outputs/susceptibility.tif / .png")
    if alpha:
        print(ALPHAEARTH_ATTRIBUTION)


if __name__ == "__main__":
    main()
