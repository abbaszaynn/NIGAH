"""Collect Gilgit-Baltistan news items from free RSS feeds (no paid X API).

Feeds and keywords live in config/settings.toml [nlp]. Items that mention
none of the keywords are dropped. New items are appended to
outputs/reports_raw.csv, de-duplicated by link.

Run:
    python -m src.nlp.scrape
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

import feedparser
import pandas as pd

from src.common import OUTPUTS, out_path, settings

COLUMNS = ["id", "published", "source", "title", "summary", "link", "collected"]


def _clean(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html or "")).strip()


def fetch(feeds: list[str], keywords: list[str]) -> pd.DataFrame:
    kw = [k.lower() for k in keywords]
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for url in feeds:
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            print(f"  skip {url}: {feed.bozo_exception}")
            continue
        for e in feed.entries:
            title, summary = _clean(e.get("title", "")), _clean(e.get("summary", ""))
            text = f"{title} {summary}".lower()
            if not any(k in text for k in kw):
                continue
            ts = e.get("published_parsed") or e.get("updated_parsed")
            pub = datetime(*ts[:6], tzinfo=timezone.utc).isoformat() if ts else ""
            link = e.get("link", "")
            rows.append({"id": hashlib.sha1(link.encode()).hexdigest()[:12], "published": pub,
                         "source": feed.feed.get("title", url), "title": title,
                         "summary": summary[:1000], "link": link, "collected": now})
        print(f"  {url}: {len(feed.entries)} entries")
    return pd.DataFrame(rows, columns=COLUMNS)


def main():
    cfg = settings()["nlp"]
    new = fetch(cfg["feeds"], cfg["keywords"])
    path = OUTPUTS / "reports_raw.csv"
    old = pd.read_csv(path) if path.exists() else pd.DataFrame(columns=COLUMNS)
    merged = pd.concat([old, new]).drop_duplicates("link", keep="first")
    merged.to_csv(out_path("reports_raw.csv"), index=False)
    print(f"{len(merged) - len(old)} new relevant items, {len(merged)} total -> {path}")


if __name__ == "__main__":
    main()
