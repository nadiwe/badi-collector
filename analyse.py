#!/usr/bin/env python3
"""Auswertung der gesammelten Badi-Belegungsdaten."""

import calendar
import csv
import glob
from collections import defaultdict
from datetime import date, datetime, timedelta


# ── Feiertage ─────────────────────────────────────────────────────────────

def _easter(year: int) -> date:
    """Osterdatum nach Meeus/Jones/Butcher."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    L = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * L) // 451
    month, day = divmod(h + L - 7 * m + 114, 31)
    return date(year, month, day + 1)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-ter `weekday` (0=Mo … 6=So) im Monat (n ist 1-basiert)."""
    d = date(year, month, 1)
    delta = (weekday - d.weekday()) % 7
    return d + timedelta(days=delta + 7 * (n - 1))


def _holidays_for_year(year: int) -> dict:
    e = _easter(year)
    bettag    = _nth_weekday(year, 9, 6, 3)       # 3. Sonntag im September
    knaben_sa = bettag - timedelta(days=8)
    knaben_so = bettag - timedelta(days=7)
    knaben_mo = bettag - timedelta(days=6)         # halber Feiertag
    return {
        date(year, 1,  1):               "Neujahr",
        date(year, 8,  1):               "Bundesfeiertag",
        date(year, 12, 24):              "Heiligabend",
        date(year, 12, 25):              "Weihnachten",
        date(year, 12, 26):              "Stephanstag",
        date(year, 12, 31):              "Silvester",
        _nth_weekday(year, 4, 0, 3):     "Sechseläuten",
        e + timedelta(days=39):          "Auffahrt",
        e + timedelta(days=49):          "Pfingstsonntag",
        e + timedelta(days=50):          "Pfingstmontag",
        knaben_sa:                       "Knabenschiessen (Sa)",
        knaben_so:                       "Knabenschiessen (So)",
        knaben_mo:                       "Knabenschiessen (Mo, halber Feiertag)",
    }


_holiday_cache: dict = {}


def _day_type(d: date) -> str:
    if d.year not in _holiday_cache:
        _holiday_cache[d.year] = _holidays_for_year(d.year)
    if d in _holiday_cache[d.year]:
        return "Feiertag"
    if d.weekday() >= 5:
        return "Wochenende"
    return "Werktag"


# ── Daten laden ───────────────────────────────────────────────────────────

def _slot(ts: datetime) -> str:
    """Rundet Timestamp auf 15-Minuten-Grenze (floor), gibt 'HH:MM' zurück."""
    return f"{ts.hour:02d}:{(ts.minute // 15) * 15:02d}"


def _strip_csv_safe(value: str) -> str:
    """Entfernt das von _csv_safe() hinzugefügte führende Apostroph."""
    return value[1:] if value.startswith("'") else value


def load_data(data_dir: str = "data") -> list:
    rows = []
    for path in sorted(glob.glob(f"{data_dir}/*.csv")):
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    ts       = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
                    maxspace = int(row["maxspace"])   if row.get("maxspace")   else 0
                    fill     = int(row["currentfill"]) if row.get("currentfill") else 0
                    util     = (fill / maxspace * 100) if maxspace > 0 else None
                    rows.append({
                        "ts":       ts,
                        "date":     ts.date(),
                        "slot":     _slot(ts),
                        "day_type": _day_type(ts.date()),
                        "uid":      _strip_csv_safe(row.get("uid", "")),
                        "name":     _strip_csv_safe(row.get("name", "")),
                        "fill":     fill,
                        "maxspace": maxspace,
                        "util":     util,
                    })
                except (ValueError, KeyError, ZeroDivisionError):
                    continue
    return rows


# ── Hilfsfunktionen ───────────────────────────────────────────────────────

def _open_days(rows: list) -> set:
    """(uid, date)-Paare wo die Badi an diesem Tag mindestens einmal offen war."""
    daily_max: dict = defaultdict(int)
    for r in rows:
        key = (r["uid"], r["date"])
        daily_max[key] = max(daily_max[key], r["maxspace"])
    return {k for k, v in daily_max.items() if v > 0}


def _output_levels(rows: list) -> list:
    dates = {r["date"] for r in rows}
    if not dates:
        return []
    levels = ["slots"]
    if len(dates) <= 1:
        return levels
    if len({d.isocalendar()[:2] for d in dates}) >= 2:
        levels.append("weekly")
    if len({(d.year, d.month) for d in dates}) >= 2:
        levels.append("monthly")
    if any(5 <= d.month <= 9 for d in dates) and any(
        d.month < 5 or d.month > 9 for d in dates
    ):
        levels.append("seasonal")
    return levels


# ── Ausgabe ───────────────────────────────────────────────────────────────

DAY_TYPES = ["Werktag", "Wochenende", "Feiertag"]
COL = 14


def _print_slot_table(slot_avg: dict, badi: str, present_types: list):
    slots = sorted({k[2] for k in slot_avg if k[0] == badi})
    if not slots:
        return
    header = f"    {'Zeit':>5}" + "".join(f"  {t:>{COL}}" for t in present_types)
    print(header)
    print("    " + "─" * (len(header) - 4))
    for s in slots:
        line = f"    {s:>5}"
        for dt in present_types:
            v = slot_avg.get((badi, dt, s))
            line += f"  {f'{v:.1f}%':>{COL}}" if v is not None else f"  {'—':>{COL}}"
        print(line)


def main():
    rows = load_data()
    if not rows:
        print("Keine Daten in data/ gefunden.")
        return

    open_d  = _open_days(rows)
    active  = [r for r in rows if (r["uid"], r["date"]) in open_d and r["util"] is not None]
    levels  = _output_levels(rows)
    d_min   = min(r["date"] for r in rows)
    d_max   = max(r["date"] for r in rows)
    badis   = sorted({r["name"] for r in active})
    p_types = [t for t in DAY_TYPES if any(r["day_type"] == t for r in active)]

    print(f"\n{'═' * 64}")
    print(f"  Badi-Auslastung Zürich  │  {d_min} – {d_max}")
    print(f"{'═' * 64}")

    # ── Slot-Durchschnitte ──────────────────────────────────────────────
    bucket: dict = defaultdict(list)
    for r in active:
        bucket[(r["name"], r["day_type"], r["slot"])].append(r["util"])
    slot_avg = {k: sum(v) / len(v) for k, v in bucket.items()}

    print("\n── Durchschnittliche Auslastung pro Zeitslot ──────────────\n")
    for badi in badis:
        print(f"  ▸ {badi}")
        _print_slot_table(slot_avg, badi, p_types)
        print()

    # ── Wochendurchschnitt ──────────────────────────────────────────────
    if "weekly" in levels:
        print("── Wochendurchschnitt ──────────────────────────────────────\n")
        wb: dict = defaultdict(list)
        for r in active:
            iso = r["date"].isocalendar()
            wb[(r["name"], iso[0], iso[1])].append(r["util"])
        for badi in badis:
            kws = sorted((y, w) for (n, y, w) in wb if n == badi)
            if not kws:
                continue
            print(f"  ▸ {badi}")
            for y, w in kws:
                v = wb.get((badi, y, w))
                if v:
                    print(f"    KW {w:02d}/{y}: {sum(v)/len(v):.1f}%")
            print()

    # ── Monatsdurchschnitt ──────────────────────────────────────────────
    if "monthly" in levels:
        print("── Monatsdurchschnitt ──────────────────────────────────────\n")
        mb: dict = defaultdict(list)
        for r in active:
            mb[(r["name"], r["date"].year, r["date"].month)].append(r["util"])
        for badi in badis:
            months = sorted((y, mo) for (n, y, mo) in mb if n == badi)
            if not months:
                continue
            print(f"  ▸ {badi}")
            for y, mo in months:
                v = mb.get((badi, y, mo))
                if v:
                    print(f"    {calendar.month_abbr[mo]} {y}: {sum(v)/len(v):.1f}%")
            print()

    # ── Saisonvergleich ─────────────────────────────────────────────────
    if "seasonal" in levels:
        print("── Saisonvergleich (Sommer: Mai–Sep │ Winter: Okt–Apr) ────\n")
        sb: dict = defaultdict(list)
        for r in active:
            season = "Sommer (Mai–Sep)" if 5 <= r["date"].month <= 9 else "Winter (Okt–Apr)"
            sb[(r["name"], season)].append(r["util"])
        for badi in badis:
            parts = []
            for season in ["Sommer (Mai–Sep)", "Winter (Okt–Apr)"]:
                v = sb.get((badi, season))
                if v:
                    parts.append(f"{season}: {sum(v)/len(v):.1f}%")
            if parts:
                print(f"  {badi:44s} {' │ '.join(parts)}")
        print()


if __name__ == "__main__":
    main()
