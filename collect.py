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
    """Prefix formula-triggering characters to prevent CSV injection."""
    s = str(value) if value is not None else ""
    return ("'" + s) if s.startswith(("=", "+", "-", "@", "\t", "\r")) else s


# Besucherzahlen — interne UIDs aus dem Crowdmonitor WebSocket (ohne SSD-1)
BESUCHER_IDS = {
    "SSD-2", "SSD-3", "SSD-4", "SSD-6", "SSD-7", "SSD-8", "SSD-10",
    "BADI-1", "flb6939", "flb6940", "flb8803", "flb6941",
    "fb006", "fb008", "fb012", "LETZI-1", "SSD-11", "fb018",
    "seb6946", "seb6947", "seb6948", "SSD-5",
}

# Temperaturen — poiids aus der Stadt-Zürich-API (ohne Hallenbad Altstetten)
TEMPERATUREN_IDS = {
    "flb6939", "flb6940", "flb8803", "flb6941",   # Flussbäder
    "fb002",                                         # Letzigraben  (= LETZI-1)
    "fb006", "fb008", "fb012", "fb013", "fb018",   # Freibäder (fb013 = Seebach = SSD-11)
    "seb6943",                                       # Seebad Enge  (= BADI-1)
    "seb6945",                                       # Seebad Utoquai (= SSD-10)
    "seb6946", "seb6947", "seb6948",               # Strandbäder
}


def _week_file(subdir: str) -> str:
    now = datetime.now(_ZURICH)
    path = f"data/{subdir}/{now.strftime('%G-W%V')}.csv"
    os.makedirs(f"data/{subdir}", exist_ok=True)
    return path


async def collect_besucher():
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

    file_exists = os.path.isfile(csv_file)
    with open(csv_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "uid", "name", "currentfill", "freespace", "maxspace"])
        for bad in data:
            if bad.get("uid") in BESUCHER_IDS:
                writer.writerow([
                    timestamp,
                    _csv_safe(bad.get("uid")),
                    _csv_safe(bad.get("name")),
                    bad.get("currentfill"),
                    bad.get("freespace"),
                    bad.get("maxspace"),
                ])

    print(f"✓ Besucherzahlen gespeichert: {timestamp}")


def collect_temperaturen():
    now       = datetime.now(_ZURICH)
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    csv_file  = _week_file("temperaturen")

    with urllib.request.urlopen(TEMPERATUREN_URL, timeout=30) as resp:
        root = ET.fromstring(resp.read())

    file_exists = os.path.isfile(csv_file)
    with open(csv_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["timestamp", "uid", "name", "temperatureWater", "openClosed"])
        for bath in root.findall(".//bath"):
            uid = (bath.findtext("poiid") or "").strip()
            if uid not in TEMPERATUREN_IDS:
                continue
            writer.writerow([
                timestamp,
                _csv_safe(uid),
                _csv_safe((bath.findtext("title") or "").strip()),
                (bath.findtext("temperatureWater") or "").strip(),
                (bath.findtext("openClosedTextPlain") or "").strip(),
            ])

    print(f"✓ Temperaturen gespeichert: {timestamp}")


asyncio.run(collect_besucher())
collect_temperaturen()
