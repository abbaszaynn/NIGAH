"""Tier protocol and OASIS CAP 1.2 messages for NIGAH lake alerts.

The tier -> CAP severity/urgency/certainty mapping and the suggested actions
are NIGAH's own proposal. They must be agreed with GBDMA/NDMA before any
operational use; until then every message is issued with status "Exercise".
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from xml.sax.saxutils import escape

SENDER = "nigah.prototype@users.noreply.github.com"
SENDER_NAME = "NIGAH research prototype (not an official NDMA/GBDMA warning)"

PROTOCOL = {
    # tier: CAP fields + suggested action (English, Urdu)
    "watch": {
        "severity": "Minor", "urgency": "Future", "certainty": "Possible", "valid_days": 7,
        "headline": "Lake growth above normal",
        "action": "Monitor. Check the next satellite pass and field reports. No public message.",
        "action_ur": "نگرانی جاری رکھیں۔ اگلی سیٹلائٹ تصویر اور مقامی اطلاعات دیکھیں۔",
    },
    "warning": {
        "severity": "Moderate", "urgency": "Expected", "certainty": "Possible", "valid_days": 7,
        "headline": "Rapid lake growth: outburst flood possible",
        "action": "Inform district DMA and local committees. Request a field check of the lake and "
                  "outlet. Review evacuation routes downstream.",
        "action_ur": "ضلعی ڈی ایم اے اور مقامی کمیٹیوں کو آگاہ کریں۔ جھیل کا موقع پر معائنہ کروائیں۔ "
                     "نشیبی علاقوں کے انخلا کے راستوں کا جائزہ لیں۔",
    },
    "alert": {
        "severity": "Severe", "urgency": "Expected", "certainty": "Likely", "valid_days": 7,
        "headline": "Sustained rapid lake growth: high outburst flood risk",
        "action": "Escalate to GBDMA. Alert downstream communities and KKH traffic control. "
                  "Pre-position response teams.",
        "action_ur": "جی بی ڈی ایم اے کو فوری اطلاع دیں۔ نشیبی آبادی اور شاہراہ قراقرم کی ٹریفک کو "
                     "خبردار کریں۔ امدادی ٹیمیں تیار رکھیں۔",
    },
}

TIER_UR = {"watch": "نگرانی", "warning": "انتباہ", "alert": "خطرہ"}


def _cap_polygon(geometry: dict | None) -> str:
    if not geometry or geometry.get("type") != "Polygon":
        return ""
    ring = geometry["coordinates"][0]
    pts = " ".join(f"{lat:.5f},{lon:.5f}" for lon, lat in ring)
    return f"      <polygon>{pts}</polygon>\n"


def identifier(lake_id: str, obs_date: str, tier: str) -> str:
    return f"NIGAH-{lake_id}-{obs_date}-{tier}"


def cap_xml(lake: dict, obs: dict, sent: datetime | None = None, web: str = "") -> str:
    """CAP 1.2 alert for one lake observation.

    lake: AOI feature (properties + geometry). obs: date, tier, area_km2, growth_15d, z, sensor.
    """
    pr = lake["properties"]
    p = PROTOCOL[obs["tier"]]
    sent = (sent or datetime.now(timezone.utc)).replace(microsecond=0)
    expires = sent + timedelta(days=p["valid_days"])
    facts = [f"Water area {obs['area_km2']:.3f} km2 in the {obs['sensor'].upper()} scene of {obs['date']}."]
    g, z = obs.get("growth_15d"), obs.get("z")
    if g is not None and g == g:
        facts.append(f"Growth {g:+.0%} per 15 days.")
    if z is not None and z == z:
        facts.append(f"Robust z-score {z:.1f} against the previous 60 days.")
    facts.append("Derived automatically from satellite imagery; not field-verified.")
    downstream = ", ".join(pr.get("downstream", []))
    area_desc = f"{pr['name']}, {pr.get('valley', '')}" + (f"; downstream: {downstream}" if downstream else "")
    e = escape
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<alert xmlns="urn:oasis:names:tc:emergency:cap:1.2">
  <identifier>{e(identifier(pr['id'], obs['date'], obs['tier']))}</identifier>
  <sender>{SENDER}</sender>
  <sent>{sent.isoformat()}</sent>
  <status>Exercise</status>
  <msgType>Alert</msgType>
  <scope>Public</scope>
  <note>Research prototype output. Not an official warning.</note>
  <info>
    <language>en</language>
    <category>Geo</category>
    <category>Met</category>
    <event>Glacial lake outburst flood potential</event>
    <responseType>Monitor</responseType>
    <urgency>{p['urgency']}</urgency>
    <severity>{p['severity']}</severity>
    <certainty>{p['certainty']}</certainty>
    <effective>{sent.isoformat()}</effective>
    <expires>{expires.isoformat()}</expires>
    <senderName>{e(SENDER_NAME)}</senderName>
    <headline>{e(p['headline'] + ': ' + pr['name'])}</headline>
    <description>{e(' '.join(facts))}</description>
    <instruction>{e(p['action'])}</instruction>
    {f'<web>{e(web)}</web>' if web else ''}
    <parameter><valueName>NIGAH_TIER</valueName><value>{obs['tier']}</value></parameter>
    <area>
      <areaDesc>{e(area_desc)}</areaDesc>
{_cap_polygon(lake.get('geometry'))}    </area>
  </info>
</alert>
"""


def bulletin(lake: dict, obs: dict) -> tuple[str, str]:
    """Plain-language bulletin text in English and Urdu."""
    pr, p = lake["properties"], PROTOCOL[obs["tier"]]
    en = (f"{obs['tier'].upper()}: {p['headline']} at {pr['name']} ({pr.get('valley', '')}). "
          f"Satellite scene {obs['date']}: water area {obs['area_km2']:.3f} km². {p['action']}")
    ur = (f"{TIER_UR[obs['tier']]}: {pr['name']} ({pr.get('valley', '')})۔ "
          f"سیٹلائٹ تصویر {obs['date']}: جھیل کا رقبہ {obs['area_km2']:.3f} مربع کلومیٹر۔ {p['action_ur']}")
    return en, ur
