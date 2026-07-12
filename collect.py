import asyncio
import csv
import json
import os
import urllib.request
import websockets
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo

_ZURICH = ZoneInfo("Europe/Zurich")

WEBSOCKET_URL    = "wss://badi-public.crowdmonitor.ch:9591/api"
TEMPERATUREN_URL = "https://www.stadt-zuerich.ch/stzh/bathdatadownload"


def _csv_safe(value):
    s = str(value) if value is not None else ""
    return ("'" + s) if s.startswith(("=", "+", "-", "@", "\t", "\r")) else s


# Besucherzahlen — interne UIDs aus dem Crowdmonitor WebSocket (ohne SSD-1)
BESUCHER_IDS = {
    "SSD-2", "SSD-3", "SSD-4", "SSD-6", "SSD-7", "SSD-10",
    "BADI-1", "flb6939", "flb6940", "flb8803", "flb6941",
    "fb006", "fb008", "fb012", "LETZI-1", "SSD-11", "fb018",
    "seb6946", "seb6947", "seb6948", "SSD-5",
}

# Temperaturen — poiids aus der Stadt-Zürich-API (ohne Hallenbad Altstetten)
TEMPERATUREN_IDS = {
    "flb6938", "flb6939", "flb6940", "flb8803", "flb6941", "flb6942",
    "fb002",
    "fb006", "fb008", "fb012", "fb013", "fb016", "fb018",
    "seb6943",
    "seb6945",
    "seb6946", "seb6947", "seb6948",
}

# Mapping: Crowdmonitor-UID → Stadt-Zürich-Temperatur-poiid
# (nur wo die UIDs nicht identisch sind)
_TEMP_UID = {
    "BADI-1":  "seb6943",
    "LETZI-1": "fb002",
    "SSD-10":  "seb6945",
    "SSD-11":  "fb013",
}


def _week_file(subdir: str) -> str:
    now = datetime.now(_ZURICH)
    path = f"data/{subdir}/{now.strftime('%G-W%V')}.csv"
    os.makedirs(f"data/{subdir}", exist_ok=True)
    return path


async def collect_besucher() -> tuple[dict, str]:
    now       = datetime.now(_ZURICH)
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    csv_file  = _week_file("besucher")

    for attempt in range(3):
        try:
            async with websockets.connect(WEBSOCKET_URL) as ws:
                await ws.send("")
                message = await asyncio.wait_for(ws.recv(), timeout=30)
                data = json.loads(message)
            break
        except (TimeoutError, asyncio.TimeoutError):
            if attempt == 2:
                raise
            print(f"Besucher: Versuch {attempt + 1} fehlgeschlagen, erneuter Versuch...")
            await asyncio.sleep(5)

    snapshot: dict = {}
    file_exists = os.path.isfile(csv_file)
    with open(csv_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "uid", "name", "currentfill", "freespace", "maxspace"])
        for bad in data:
            uid = bad.get("uid")
            if uid in BESUCHER_IDS:
                writer.writerow([
                    timestamp,
                    _csv_safe(uid),
                    _csv_safe(bad.get("name")),
                    bad.get("currentfill"),
                    bad.get("freespace"),
                    bad.get("maxspace"),
                ])
                snapshot[uid] = {
                    "currentfill": bad.get("currentfill"),
                    "freespace":   bad.get("freespace"),
                    "maxspace":    bad.get("maxspace"),
                }

    print(f"✓ Besucherzahlen gespeichert: {timestamp}")
    return snapshot, timestamp


def collect_temperaturen() -> dict:
    now       = datetime.now(_ZURICH)
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    csv_file  = _week_file("temperaturen")

    with urllib.request.urlopen(TEMPERATUREN_URL, timeout=30) as resp:
        root = ET.fromstring(resp.read())

    snapshot: dict = {}
    file_exists = os.path.isfile(csv_file)
    with open(csv_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "uid", "name", "temperatureWater", "openClosed"])
        for bath in root.findall(".//bath"):
            uid = (bath.findtext("poiid") or "").strip()
            if uid not in TEMPERATUREN_IDS:
                continue
            temp = (bath.findtext("temperatureWater") or "").strip()
            status = (bath.findtext("openClosedTextPlain") or "").strip()
            writer.writerow([
                timestamp,
                _csv_safe(uid),
                _csv_safe((bath.findtext("title") or "").strip()),
                temp,
                status,
            ])
            snapshot[uid] = {
                "temperatureWater": temp or None,
                "openClosed":       status or None,
            }

    print(f"✓ Temperaturen gespeichert: {timestamp}")
    return snapshot


# Venues nur in der XML-API (keine Besucherzahlen via Crowdmonitor)
_XML_ONLY_IDS = {
    "flb6938":   "flb6938",   # Flussbad Au-Höngg
    "flb6942":   "flb6942",   # Männerbad Schanzengraben
    "DOLDER-1":  "fb016",     # Freibad Dolder
}


def generate_live_json(besucher: dict, temperaturen: dict, timestamp: str) -> None:
    venues: dict = {}
    for uid in BESUCHER_IDS:
        b = besucher.get(uid)
        if b is None:
            continue
        temp_uid = _TEMP_UID.get(uid, uid)
        t = temperaturen.get(temp_uid, {})
        venues[uid] = {
            "currentfill":      b.get("currentfill"),
            "freespace":        b.get("freespace"),
            "maxspace":         b.get("maxspace"),
            "temperatureWater": t.get("temperatureWater"),
            "openClosed":       t.get("openClosed"),
        }
    for uid, temp_uid in _XML_ONLY_IDS.items():
        t = temperaturen.get(temp_uid, {})
        if not t:
            continue
        venues[uid] = {
            "currentfill":      None,
            "freespace":        None,
            "maxspace":         None,
            "temperatureWater": t.get("temperatureWater"),
            "openClosed":       t.get("openClosed"),
        }
    payload = {"timestamp": timestamp, "venues": venues}
    with open("data/live.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"✓ live.json aktualisiert: {timestamp}")


besucher_snap, ts = asyncio.run(collect_besucher())
temp_snap = collect_temperaturen()
generate_live_json(besucher_snap, temp_snap, ts)
