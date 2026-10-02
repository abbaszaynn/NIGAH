"""Telegram alert messages (free Bot API).

Needs env vars TELEGRAM_BOT_TOKEN (from @BotFather) and TELEGRAM_CHAT_ID.

Run:
    python -m src.alerts.telegram --test     # send one test message to your phone
"""

from __future__ import annotations

import argparse
import os

import requests

TIER_LABEL = {"watch": "WATCH", "warning": "WARNING", "alert": "ALERT"}
DISCLAIMER = "NIGAH prototype. Not an official NDMA/GBDMA warning."


def send(text: str) -> bool:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        print("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set; message not sent:\n" + text)
        return False
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": text, "disable_web_page_preview": True},
                      timeout=20)
    if not r.ok:
        print(f"Telegram error {r.status_code}: {r.text[:200]}")
    return r.ok


def lake_message(lake_name: str, row: dict, threshold_source: str) -> str:
    growth = row.get("growth_15d")
    z = row.get("z")
    parts = [f"NIGAH {TIER_LABEL[row['tier']]}: {lake_name}",
             f"Observed {row['date']} ({row['sensor'].upper()})",
             f"Lake area {row['area_km2']:.3f} km²"]
    if growth == growth and growth is not None:  # not NaN
        parts.append(f"Growth {growth:+.0%} per 15 days")
    if z == z and z is not None:
        parts.append(f"Robust z-score {z:.1f} vs prior 60 days")
    parts += [f"Thresholds: {threshold_source}", DISCLAIMER]
    return "\n".join(parts)


def main():
    p = argparse.ArgumentParser(description="Telegram alerts")
    p.add_argument("--test", action="store_true", help="send a test message")
    args = p.parse_args()
    if args.test:
        ok = send("NIGAH test message. If you can read this, alerts reach your phone.\n" + DISCLAIMER)
        print("sent" if ok else "not sent")


if __name__ == "__main__":
    main()
