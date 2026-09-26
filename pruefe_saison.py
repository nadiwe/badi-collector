#!/usr/bin/env python3
"""Saison und Öffnungszeiten der Sommerbäder bei der Stadt Zürich prüfen.

Liest auf jeder Bad-Seite die Tabelle «Öffnungszeiten <Jahr>» und trägt
Saisonstart/-ende (saison_<jahr>) und die Zeiträume (oeffnungszeiten_<jahr>)
in data/badi-stammdaten.json ein, sobald die Stadt sie veröffentlicht hat.

Aufruf:  python pruefe_saison.py [jahr]
Ausgabe: Zusammenfassung als Markdown in pruefung_saison.md
"""

import html
import json
import re
import sys
import urllib.request
from datetime import date

STAMMDATEN = "data/badi-stammdaten.json"
SECTIONS   = ["freibäder", "flussbäder", "seebäder"]
MONATE     = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
              "August", "September", "Oktober", "November", "Dezember"]
MON        = {m: i + 1 for i, m in enumerate(MONATE)}


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (wasserziit-pruefung)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return html.unescape(r.read().decode("utf-8", "ignore"))


def strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", " ", s).strip()


def parse_range(text: str, year: int):
    """«9.–29. Mai» / «30. Mai–16. August» → ("2026-05-09", "2026-05-29")."""
    t = re.sub(r"\s", "", text)
    m = re.match(r"(\d{1,2})\.([A-Za-zäöüÄÖÜ]+)?[–-](\d{1,2})\.([A-Za-zäöüÄÖÜ]+)$", t)
    if not m or m.group(4) not in MON:
        return None
    d1, m1, d2, m2 = m.groups()
    m1 = m1 or m2
    if m1 not in MON:
        return None
    return f"{year}-{MON[m1]:02d}-{int(d1):02d}", f"{year}-{MON[m2]:02d}-{int(d2):02d}"


def hm(x: str) -> str:
    h, _, m = x.replace(".", ":").partition(":")
    return f"{int(h):02d}:{(m or '00'):0>2}"


def parse_hours(cell: str):
    m = re.search(r"(\d{1,2}(?:[.:]\d{2})?)\s*[–-]\s*(\d{1,2}(?:[.:]\d{2})?)\s*Uhr", strip_tags(cell))
    return (hm(m.group(1)), hm(m.group(2))) if m else None


def perioden_von_seite(page: str, year: int):
    """Zeiträume aus der Tabelle, zu der die Überschrift «Öffnungszeiten <jahr>» gehört."""
    head = page.find(f'id="oeffnungszeiten_{year}"')
    if head < 0:
        return None
    tables = list(re.finditer(r'<stzh-datatable columns="(\[.*?\])" rows="(\[.*?\])"', page, re.S))
    # Die Überschrift steht je nach Seite vor oder nach der Tabelle:
    # die nächstgelegene Tabelle mit Datumsbereichen ist die richtige
    for t in sorted(tables, key=lambda m: abs(m.start() - head)):
        try:
            perioden = _perioden_aus_rows(json.loads(t.group(2)), year)
        except (json.JSONDecodeError, KeyError, IndexError):
            continue
        if perioden:
            return perioden
    return None


def _perioden_aus_rows(rows: list, year: int) -> list:
    perioden = []
    for row in rows:
        rg = parse_range(strip_tags(row[0]["value"]), year)
        hs = [h for h in (parse_hours(c["value"]) for c in row[1:]) if h]
        if not rg or not hs:
            continue
        p = {"von": rg[0], "bis": rg[1], "zeit": f"{hs[0][0]}–{hs[-1][1]}"}
        if len(hs) > 1:
            p["schoenwetter_ab"] = hs[1][0]     # 2. Spalte = «nur bei schönem Wetter»
        if "Sonntag–Freitag" in " ".join(c["value"] for c in row[1:]):
            p["tage"] = "so-fr"
        perioden.append(p)
    return perioden


def fmt(iso: str) -> str:
    return f"{int(iso[8:])}. {MONATE[int(iso[5:7]) - 1]}"


def main():
    year = int(sys.argv[1]) if len(sys.argv) > 1 else date.today().year
    with open(STAMMDATEN, encoding="utf-8") as f:
        data = json.load(f)

    geaendert, unveraendert, offen, manuell = [], [], [], []
    seiten: dict = {}

    for section in SECTIONS:
        for e in data.get(section, []):
            name = e["name"]
            # Stadt-Seite: zuerst die zuletzt verwendete Quelle, sonst die offizielle URL (auch Kurzlinks)
            kandidaten = [(e.get(k) or {}).get("quelle", "") for k in
                          (f"oeffnungszeiten_{year}", f"saison_{year}", f"oeffnungszeiten_{year - 1}", f"saison_{year - 1}")]
            url = next((u for u in kandidaten if "stadt-zuerich.ch" in u), e.get("officialUrl", ""))
            if "stadt-zuerich.ch" not in url:
                manuell.append(f"- **{name}** – nicht bei der Stadt, bitte manuell prüfen ({e.get('officialUrl', '?')})")
                continue
            try:
                page = seiten.get(url) or fetch(url)
                seiten[url] = page
            except Exception as ex:                      # Seite nicht erreichbar
                offen.append(f"- **{name}** – Seite nicht erreichbar: {ex}")
                continue

            perioden = perioden_von_seite(page, year)
            if not perioden:
                offen.append(f"- **{name}** – Öffnungszeiten {year} noch nicht veröffentlicht")
                continue

            von, bis = perioden[0]["von"], perioden[-1]["bis"]
            neu_saison = {"wert": f"{fmt(von)} – {fmt(bis)}", "von": von, "bis": bis,
                          "quelle": url, "typ": "automatisch", "pruefung": "jährlich"}
            neu_oz = {"quelle": url, "typ": "automatisch", "pruefung": "jährlich", "perioden": perioden}

            alt_saison = e.get(f"saison_{year}", {})
            alt_oz     = e.get(f"oeffnungszeiten_{year}", {})
            if (alt_saison.get("von"), alt_saison.get("bis")) == (von, bis) and alt_oz.get("perioden") == perioden:
                unveraendert.append(f"- {name}: {neu_saison['wert']}")
                continue

            vorher = alt_saison.get("wert", "—")
            e[f"saison_{year}"] = neu_saison
            e[f"oeffnungszeiten_{year}"] = neu_oz
            geaendert.append(f"- **{name}**: {vorher} → **{neu_saison['wert']}** ({len(perioden)} Zeiträume)")

    if geaendert:
        with open(STAMMDATEN, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    teile = [f"## 🌊 Saison-Prüfung {year}\n"]
    teile.append(f"### Aktualisiert ({len(geaendert)})\n" + ("\n".join(geaendert) or "_Keine Änderungen_"))
    teile.append(f"### Noch offen ({len(offen)})\n" + ("\n".join(offen) or "_Alles gefunden_"))
    teile.append(f"### Manuell prüfen ({len(manuell)})\n" + ("\n".join(manuell) or "_Keine_"))
    teile.append(f"### Unverändert ({len(unveraendert)})\n" + ("\n".join(unveraendert) or "_–_"))
    bericht = "\n\n".join(teile) + "\n"
    with open("pruefung_saison.md", "w", encoding="utf-8") as f:
        f.write(bericht)
    print(bericht)


if __name__ == "__main__":
    main()
