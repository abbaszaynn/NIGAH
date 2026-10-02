"""XLM-R triage of Urdu/English reports + gazetteer place extraction.

Labels: rockfall / road_block / flood_glof / irrelevant (config/settings.toml [nlp]).

Steps:
    python -m src.nlp.classify export     # outputs/reports_to_label.csv for labelling
    # label it (LLM pre-label, human correct), save as config/reports_labeled.csv (text,label)
    python -m src.nlp.classify train      # fine-tune, held-out per-class F1, confusion matrix
    python -m src.nlp.classify predict    # triage outputs/reports_raw.csv -> reports_triaged.csv

predict without a trained model still extracts places but leaves label empty:
it never invents a class.
"""

from __future__ import annotations

import argparse
import re

import numpy as np
import pandas as pd

from src.common import CONFIG, OUTPUTS, out_path, settings

MODEL_DIR = OUTPUTS / "xlmr_triage"


# ---------- places ----------

def gazetteer() -> list[tuple[re.Pattern, dict]]:
    gz = pd.read_csv(CONFIG / "gazetteer.csv")
    out = []
    for r in gz.itertuples():
        names = [r.name] + [n for n in str(r.alt_names).split("|") if n and n != "nan"]
        alts = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
        # \b does not work for Urdu script; use non-letter lookarounds instead
        pat = re.compile(rf"(?<![\w]){'(?:' + alts + ')'}(?![\w])", re.IGNORECASE)
        out.append((pat, {"place": r.name, "district": r.district, "lat": r.lat, "lon": r.lon}))
    return out


def extract_places(text: str, gz=None) -> list[dict]:
    gz = gz or gazetteer()
    return [info for pat, info in gz if pat.search(text or "")]


# ---------- model ----------

def _text(df: pd.DataFrame) -> pd.Series:
    if "text" in df:
        return df["text"].fillna("")
    return (df["title"].fillna("") + ". " + df["summary"].fillna("")).str.strip()


def export():
    raw = pd.read_csv(OUTPUTS / "reports_raw.csv")
    out = pd.DataFrame({"id": raw["id"], "text": _text(raw), "label": ""})
    out.to_csv(out_path("reports_to_label.csv"), index=False)
    print(f"{len(out)} items -> outputs/reports_to_label.csv. Labels: {settings()['nlp']['labels']}")


def train(epochs: int, seed: int = 42):
    import torch
    from sklearn.metrics import classification_report, confusion_matrix
    from sklearn.model_selection import train_test_split
    from transformers import (AutoModelForSequenceClassification, AutoTokenizer, Trainer,
                              TrainingArguments)

    cfg = settings()["nlp"]
    labels = cfg["labels"]
    df = pd.read_csv(CONFIG / "reports_labeled.csv").dropna(subset=["label"])
    df = df[df["label"].isin(labels)]
    if len(df) < 100:
        raise SystemExit(f"Only {len(df)} labelled items; the plan asks for 500-1000.")
    y = df["label"].map({l: i for i, l in enumerate(labels)})
    tr, te = train_test_split(df.index, test_size=0.2, stratify=y, random_state=seed)

    tok = AutoTokenizer.from_pretrained(cfg["model"])
    model = AutoModelForSequenceClassification.from_pretrained(
        cfg["model"], num_labels=len(labels), id2label=dict(enumerate(labels)),
        label2id={l: i for i, l in enumerate(labels)})

    class DS(torch.utils.data.Dataset):
        def __init__(self, idx):
            self.enc = tok(list(df.loc[idx, "text"]), truncation=True, max_length=256, padding=True)
            self.y = list(y.loc[idx])
        def __len__(self):
            return len(self.y)
        def __getitem__(self, i):
            return {**{k: torch.tensor(v[i]) for k, v in self.enc.items()},
                    "labels": torch.tensor(self.y[i])}

    args = TrainingArguments(output_dir=str(MODEL_DIR / "ckpt"), num_train_epochs=epochs,
                             per_device_train_batch_size=16, learning_rate=2e-5,
                             weight_decay=0.01, seed=seed, save_strategy="no", report_to=[])
    trainer = Trainer(model=model, args=args, train_dataset=DS(tr))
    trainer.train()
    trainer.save_model(str(MODEL_DIR))
    tok.save_pretrained(str(MODEL_DIR))

    pred = trainer.predict(DS(te)).predictions.argmax(-1)
    true = y.loc[te].to_numpy()
    rep = classification_report(true, pred, labels=range(len(labels)), target_names=labels,
                                output_dict=True, zero_division=0)
    pd.DataFrame(rep).T.to_csv(out_path("nlp_f1.csv"))
    cm = confusion_matrix(true, pred, labels=range(len(labels)))
    pd.DataFrame(cm, index=labels, columns=labels).to_csv(out_path("nlp_confusion.csv"))
    _plot_cm(cm, labels, len(te))

    ex = df.loc[te].assign(predicted=[labels[i] for i in pred]).head(20)
    lines = ["| Text | True | Predicted |", "|---|---|---|"]
    lines += [f"| {t[:140].replace('|', '/')} | {a} | {b} |"
              for t, a, b in zip(ex["text"], ex["label"], ex["predicted"])]
    out_path("nlp_examples.md").write_text("\n".join(lines), encoding="utf-8")
    print(pd.DataFrame(rep).T.round(3))


def _plot_cm(cm, labels, n):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(5, 4.4))
    ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(labels)), labels, rotation=30, ha="right")
    ax.set_yticks(range(len(labels)), labels)
    for i in range(len(labels)):
        for j in range(len(labels)):
            ax.text(j, i, cm[i, j], ha="center", va="center",
                    color="white" if cm[i, j] > cm.max() / 2 else "#14212B")
    ax.set_xlabel("Predicted")
    ax.set_ylabel("True")
    fig.text(0.01, 0.01, f"XLM-R triage, held-out set n={n}. Source: GB RSS news, hand-labelled.",
             fontsize=7, color="#4A5862")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(out_path("nlp_confusion.png"), dpi=150)
    plt.close(fig)


def predict():
    raw = pd.read_csv(OUTPUTS / "reports_raw.csv")
    text = _text(raw)
    gz = gazetteer()
    places = [extract_places(t, gz) for t in text]
    raw["places"] = ["; ".join(p["place"] for p in ps) for ps in places]
    raw["lat"] = [ps[0]["lat"] if ps else np.nan for ps in places]
    raw["lon"] = [ps[0]["lon"] if ps else np.nan for ps in places]
    raw["label"], raw["confidence"] = "", np.nan

    if (MODEL_DIR / "config.json").exists():
        from transformers import pipeline
        clf = pipeline("text-classification", model=str(MODEL_DIR), truncation=True, max_length=256)
        res = clf(list(text), batch_size=16)
        raw["label"] = [r["label"] for r in res]
        raw["confidence"] = [round(r["score"], 3) for r in res]
    else:
        print("No trained model in outputs/xlmr_triage: places extracted, labels left empty.")
    raw.to_csv(out_path("reports_triaged.csv"), index=False)
    print(f"{len(raw)} reports, {raw['lat'].notna().sum()} geolocated -> outputs/reports_triaged.csv")


def main():
    p = argparse.ArgumentParser(description="Report triage")
    p.add_argument("step", choices=["export", "train", "predict"])
    p.add_argument("--epochs", type=int, default=4)
    args = p.parse_args()
    {"export": export, "predict": predict}.get(args.step, lambda: train(args.epochs))()


if __name__ == "__main__":
    main()
