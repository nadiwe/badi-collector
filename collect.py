import asyncio
import websockets
import json
import csv
import os
from datetime import datetime

WEBSOCKET_URL = "wss://badi-public.crowdmonitor.ch:9591/api"

def _csv_safe(value):
    """Prefix formula-triggering characters to prevent CSV injection."""
    s = str(value) if value is not None else ""
    return ("'" + s) if s.startswith(("=", "+", "-", "@", "\t", "\r")) else s

# Nur diese Badis speichern (Zürich)
ZUERICH_IDS = [
    "SSD-1", "SSD-2", "SSD-3", "SSD-4", "SSD-6", "SSD-7", "SSD-8", "SSD-10",
    "BADI-1", "flb6939", "flb6940", "flb8803", "flb6941",
    "fb006", "fb008", "fb012", "LETZI-1", "SSD-11", "fb018",
    "seb6946", "seb6947", "seb6948", "SSD-5"
]

async def collect():
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    csv_file = f"data/{now.strftime('%G-W%V')}.csv"

    for attempt in range(3):
        try:
            async with websockets.connect(WEBSOCKET_URL) as ws:
                await ws.send("")
                message = await asyncio.wait_for(ws.recv(), timeout=30)
                data = json.loads(message)
            break
        except (TimeoutError, asyncio.TimeoutError) as e:
            if attempt == 2:
                raise
            print(f"Versuch {attempt + 1} fehlgeschlagen, erneuter Versuch...")
            await asyncio.sleep(5)

    os.makedirs("data", exist_ok=True)
    file_exists = os.path.isfile(csv_file)

    with open(csv_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        
        # Spaltenüberschriften beim ersten Mal
        if not file_exists:
            writer.writerow(["timestamp", "uid", "name", "currentfill", "freespace", "maxspace"])
        
        for bad in data:
            if bad.get("uid") in ZUERICH_IDS:
                writer.writerow([
                    timestamp,
                    _csv_safe(bad.get("uid")),
                    _csv_safe(bad.get("name")),
                    bad.get("currentfill"),
                    bad.get("freespace"),
                    bad.get("maxspace"),
                ])

    print(f"✓ Daten gespeichert: {timestamp}")

asyncio.run(collect())
