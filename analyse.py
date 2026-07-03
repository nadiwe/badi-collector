#!/usr/bin/env python3
"""Auswertung der gesammelten Badi-Belegungsdaten."""

import calendar
import csv
import glob
import json
import os
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
    bettag    = _nth_weekday(year, 9, 6, 3)
    knaben_sa = bettag - timedelta(days=8)
    knaben_so = bettag - timedelta(days=7)
    knaben_mo = bettag - timedelta(days=6)
    return {
        date(year, 1,  1):           "Neujahr",
        date(year, 8,  1):           "Bundesfeiertag",
        date(year, 12, 24):          "Heiligabend",
        date(year, 12, 25):          "Weihnachten",
        date(year, 12, 26):          "Stephanstag",
        date(year, 12, 31):          "Silvester",
        _nth_weekday(year, 4, 0, 3): "Sechseläuten",
        e + timedelta(days=39):      "Auffahrt",
        e + timedelta(days=49):      "Pfingstsonntag",
        e + timedelta(days=50):      "Pfingstmontag",
        knaben_sa:                   "Knabenschiessen (Sa)",
        knaben_so:                   "Knabenschiessen (So)",
        knaben_mo:                   "Knabenschiessen (Mo, halber Feiertag)",
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
    return f"{ts.hour:02d}:{(ts.minute // 15) * 15:02d}"


def _strip_csv_safe(value: str) -> str:
    return value[1:] if value.startswith("'") else value


def load_data(data_dir: str = "data") -> list:
    rows = []
    for path in sorted(glob.glob(f"{data_dir}/*.csv")):
        with open(path, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    ts       = datetime.strptime(row["timestamp"], "%Y-%m-%d %H:%M:%S")
                    maxspace = int(row["maxspace"])    if row.get("maxspace")    else 0
                    fill     = int(row["currentfill"]) if row.get("currentfill") else 0
                    util     = (fill / maxspace * 100) if maxspace > 0 else None
                    rows.append({
                        "ts":        ts,
                        "date":      ts.date(),
                        "slot":      _slot(ts),
                        "day_type":  _day_type(ts.date()),
                        "uid":       _strip_csv_safe(row.get("uid", "")),
                        "name":      _strip_csv_safe(row.get("name", "")),
                        "fill":      fill,
                        "maxspace":  maxspace,
                        "util":      util,
                        "estimated": False,
                    })
                except (ValueError, KeyError, ZeroDivisionError):
                    continue
    return rows


# ── Hilfsfunktionen ───────────────────────────────────────────────────────

def _open_days(rows: list) -> set:
    """(uid, date)-Paare wo die Badi mindestens einmal offen war (maxspace > 0)."""
    daily_max: dict = defaultdict(int)
    for r in rows:
        key = (r["uid"], r["date"])
        daily_max[key] = max(daily_max[key], r["maxspace"])
    return {k for k, v in daily_max.items() if v > 0}


def _output_levels(active: list) -> list:
    dates = {r["date"] for r in active}
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


# ── Lückenfüllung (Imputation) ────────────────────────────────────────────

IMPUTE_WINDOW = timedelta(days=14)


def _find_in_season_gaps(rows: list, open_d: set) -> set:
    """
    Gibt (uid, date)-Paare zurück, die Lücken innerhalb der Saison sind.
    Bedingung: im Dataset vorhanden mit maxspace=0, aber offene Tage
    innerhalb 14 Tagen davor UND danach (→ kein Winterschluss).
    """
    all_uid_dates = {(r["uid"], r["date"]) for r in rows}
    gap_candidates = all_uid_dates - open_d

    uid_open: dict = defaultdict(set)
    for uid, d in open_d:
        uid_open[uid].add(d)

    result = set()
    for uid, gap_date in gap_candidates:
        open_dates = uid_open.get(uid, set())
        before = any(gap_date - IMPUTE_WINDOW <= od < gap_date for od in open_dates)
        after  = any(gap_date < od <= gap_date + IMPUTE_WINDOW for od in open_dates)
        if before and after:
            result.add((uid, gap_date))
    return result


def _impute(rows: list, open_d: set, in_season_gaps: set) -> list:
    """
    Schätzt Auslastungswerte für Lückentage basierend auf dem Durchschnitt
    der umliegenden 2 Wochen (gleicher Wochentag, gleicher 15-Minuten-Slot).
    """
    if not in_season_gaps:
        return []

    # Reale Messwerte indexed nach (uid, date, slot)
    real_utils: dict = defaultdict(list)
    for r in rows:
        if (r["uid"], r["date"]) in open_d and r["util"] is not None:
            real_utils[(r["uid"], r["date"], r["slot"])].append(r["util"])

    uid_name  = {r["uid"]: r["name"] for r in rows}
    uid_open: dict = defaultdict(set)
    for uid, d in open_d:
        uid_open[uid].add(d)

    imputed = []
    for uid, gap_date in sorted(in_season_gaps):
        open_dates = uid_open[uid]
        weekday    = gap_date.weekday()

        # Referenztage: offene Tage im Fenster davor und danach, gleicher Wochentag
        ref_dates = [
            d for d in open_dates
            if d.weekday() == weekday and (
                gap_date - IMPUTE_WINDOW <= d < gap_date or
                gap_date < d <= gap_date + IMPUTE_WINDOW
            )
        ]
        if not ref_dates:
            continue

        # Alle Slots die an Referenztagen vorkamen
        slots = {slot for (u, d, slot) in real_utils if u == uid and d in ref_dates}

        for slot in slots:
            ref_values = [
                v
                for d in ref_dates
                for v in real_utils.get((uid, d, slot), [])
                if v is not None
            ]
            if not ref_values:
                continue

            imputed.append({
                "ts":        datetime.combine(gap_date, datetime.strptime(slot, "%H:%M").time()),
                "date":      gap_date,
                "slot":      slot,
                "day_type":  _day_type(gap_date),
                "uid":       uid,
                "name":      uid_name.get(uid, uid),
                "fill":      0,
                "maxspace":  0,
                "util":      sum(ref_values) / len(ref_values),
                "estimated": True,
            })
    return imputed


# ── Konsolen-Ausgabe ──────────────────────────────────────────────────────

DAY_TYPES = ["Werktag", "Wochenende", "Feiertag"]
COL = 15


def _print_slot_table(slot_avg: dict, slot_est: dict, badi: str, present_types: list):
    slots = sorted({k[2] for k in slot_avg if k[0] == badi})
    if not slots:
        return
    header = f"    {'Zeit':>5}" + "".join(f"  {t:>{COL}}" for t in present_types)
    print(header)
    print("    " + "─" * (len(header) - 4))
    for s in slots:
        line = f"    {s:>5}"
        for dt in present_types:
            v   = slot_avg.get((badi, dt, s))
            est = slot_est.get((badi, dt, s), False)
            if v is not None:
                marker = "*" if est else " "
                line += f"  {f'{v:.1f}%{marker}':>{COL}}"
            else:
                line += f"  {'—':>{COL}}"
        print(line)


# ── JSON-Export ───────────────────────────────────────────────────────────

def _save_json(
    slot_avg:  dict,
    slot_est:  dict,
    active:    list,
    levels:    list,
    d_min:     date,
    d_max:     date,
    badis:     list,
    p_types:   list,
) -> None:
    uid_map = {r["name"]: r["uid"] for r in active}

    # Saisondurchschnitte
    sb: dict = defaultdict(list)
    for r in active:
        season = "Sommer_Mai_Sep" if 5 <= r["date"].month <= 9 else "Winter_Okt_Apr"
        sb[(r["name"], season)].append(r["util"])

    # Echte vs. geschätzte Tage pro Badi
    real_days: dict = defaultdict(set)
    est_days:  dict = defaultdict(set)
    for r in active:
        if r["estimated"]:
            est_days[r["name"]].add(r["date"])
        else:
            real_days[r["name"]].add(r["date"])

    badis_out = []
    for badi in badis:
        slots_obj: dict = {}
        for dt in DAY_TYPES:
            entries = []
            for s in sorted({k[2] for k in slot_avg if k[0] == badi and k[1] == dt}):
                v = slot_avg.get((badi, dt, s))
                if v is not None:
                    entries.append({
                        "zeit":       s,
                        "auslastung": round(v, 1),
                        "geschaetzt": slot_est.get((badi, dt, s), False),
                    })
            slots_obj[dt] = entries

        saison: dict = {}
        if "seasonal" in levels:
            for key, label in [("Sommer_Mai_Sep", "Sommer_Mai_Sep"),
                                ("Winter_Okt_Apr", "Winter_Okt_Apr")]:
                v = sb.get((badi, key))
                saison[label] = round(sum(v) / len(v), 1) if v else None

        real = sorted(real_days.get(badi, set()))
        badis_out.append({
            "uid":              uid_map.get(badi, ""),
            "name":             badi,
            "messtage_echt":    len(real_days.get(badi, set())),
            "tage_geschaetzt":  len(est_days.get(badi, set())),
            "erste_messung":    str(real[0])  if real else None,
            "letzte_messung":   str(real[-1]) if real else None,
            "slots":            slots_obj,
            "saison":           saison if saison else None,
        })

    output = {
        "meta": {
            "generiert": datetime.now().isoformat(timespec="seconds"),
            "von":        str(d_min),
            "bis":        str(d_max),
        },
        "badis": badis_out,
    }

    os.makedirs("auswertung", exist_ok=True)
    with open("auswertung/auswertung.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print("  → auswertung/auswertung.json gespeichert\n")


# ── Hauptprogramm ─────────────────────────────────────────────────────────

def main():
    rows = load_data()
    if not rows:
        print("Keine Daten in data/ gefunden.")
        return

    open_d         = _open_days(rows)
    in_season_gaps = _find_in_season_gaps(rows, open_d)
    imputed_rows   = _impute(rows, open_d, in_season_gaps)

    real_active = [r for r in rows if (r["uid"], r["date"]) in open_d and r["util"] is not None]
    active      = real_active + imputed_rows

    if not active:
        print("Keine auswertbaren Daten gefunden.")
        return

    levels  = _output_levels(active)
    d_min   = min(r["date"] for r in rows)
    d_max   = max(r["date"] for r in rows)
    badis   = sorted({r["name"] for r in active})
    p_types = [t for t in DAY_TYPES if any(r["day_type"] == t for r in active)]

    # Slot-Durchschnitte mit geschätzt-Flag
    bucket:     dict = defaultdict(list)
    bucket_est: dict = defaultdict(bool)
    for r in active:
        key = (r["name"], r["day_type"], r["slot"])
        bucket[key].append(r["util"])
        if r["estimated"]:
            bucket_est[key] = True
    slot_avg = {k: sum(v) / len(v) for k, v in bucket.items()}
    slot_est = dict(bucket_est)

    n_gaps = len({d for (_, d) in in_season_gaps})

    print(f"\n{'═' * 64}")
    print(f"  Badi-Auslastung Zürich  │  {d_min} – {d_max}")
    if n_gaps:
        print(f"  Lückenfüllung: {n_gaps} Tage geschätzt  (* = enthält Schätzwerte)")
    print(f"{'═' * 64}")

    # ── Slot-Tabellen ───────────────────────────────────────────────────
    print("\n── Durchschnittliche Auslastung pro Zeitslot ──────────────\n")
    for badi in badis:
        print(f"  ▸ {badi}")
        _print_slot_table(slot_avg, slot_est, badi, p_types)
        print()

    if n_gaps:
        print("  * Wert enthält mindestens einen geschätzten Tag\n")

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

    # ── JSON speichern ──────────────────────────────────────────────────
    _save_json(slot_avg, slot_est, active, levels, d_min, d_max, badis, p_types)


if __name__ == "__main__":
    main()
