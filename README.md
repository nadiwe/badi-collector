# Badi Auslastung Zürich

Sammelt automatisch alle 15 Minuten die aktuelle Besucherzahl aller Zürcher Badis.

## Daten

Die gesammelten Daten findest du in `data/badi_data.csv` mit folgenden Spalten:

| Spalte | Bedeutung |
|---|---|
| timestamp | Zeitpunkt der Messung |
| uid | Interne Bad-ID |
| name | Name des Bades |
| currentfill | Auslastung in % |
| freespace | Noch freie Plätze |
| maxspace | Maximale Kapazität |

## Quelle

Die Daten kommen von `wss://badi-public.crowdmonitor.ch:9591/api` — dem System das auch die offizielle Stadt-Zürich-Website verwendet.
