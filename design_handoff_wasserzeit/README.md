# Handoff: Wasserzeit — Zürich Badi Finder

## Overview
Wasserzeit is a live status app for Zürich's public swimming spots (Badis): river, lake, outdoor and indoor pools. It shows current guest counts, water temperature, opening status, and typical-vs-actual crowd levels, sourced from the city's official temperature/status feed and a crowd-monitoring API. Users browse a filterable list, then open a detail view per venue with weekly comparisons and a usage chart.

## About the Design Files
The file in this bundle (`Wasserzeit.dc.html`) is a **design reference built in HTML/React-like pseudocode** (a proprietary internal prototyping format — logic lives in a `DCLogic`-style class, template markup uses `{{ }}` bindings and `<sc-for>`/`<sc-if>` loop/conditional tags). It is **not production code to copy verbatim**. Treat it as a fully-specified interactive mock: reimplement the same layout, states, copy, and behavior using the target codebase's actual framework (React, Vue, SwiftUI, native Android, etc.) and its established component/design-system patterns. If no frontend framework exists yet in the target repo, choose the framework best suited to the project and implement there.

The pseudocode is still useful as source-of-truth for: exact conditional logic (open/closed, deviation coloring, sort/filter rules), copy text (Swiss-German), and computed view-model shapes (`cardVM`, `detailVM`) — read it alongside this README.

## Fidelity
**High-fidelity.** Colors, typography, spacing, copy, and interaction states are final as designed. Recreate pixel-precisely with the target codebase's component library/primitives, substituting only technical implementation (e.g. native chart library instead of hand-rolled SVG, if desired) while preserving visual output.

## Screens / Views

### 1. Home — List View
**Purpose:** Browse all Badis, filter by type or favorites, sort by "ruhigste" (quietest) or "wärmste" (warmest), tap a card to open detail.

**Layout:**
- Page background `#E4E2E0`, padding `clamp(16px, 3.5vw, 40px)`.
- Content column: `max-width: 1120px`, centered, `display:flex; flex-direction:column; gap:22px`.
- Header row: title "Wasserziit" (Outfit, 600, `clamp(28px,4vw,40px)`, color `#173D34`, line-height .95) + a monospace timestamp line below it ("Stand {date}, {time} Uhr", IBM Plex Mono 11px, color `#8C8C8C`).
- White card (`#FFFFFF`, border-radius 28px, padding 22px, box-shadow `0 4px 22px rgba(23,61,52,.08)`) contains:
  - **Filter chip row**: pill buttons, wrapping flex, gap 6px. First chip "★ Favorit" (purple accent), then "Alli" (all), "Fluss" (river), "See" (lake), "Frei" (outdoor pool), "Halle" (indoor pool) — each shows a count badge. Active chip = filled background in its accent color + white text; inactive = 1.5px border in that color, transparent bg, colored text.
  - **Result count line**: small uppercase monospace meta text, e.g. "12 Badis · 9 von 12 offen".
  - **Empty state** (when filtered list is empty): centered text, bold title + muted instructional subtext.
  - **Card grid**: CSS grid, `repeat(auto-fill, minmax(300px,1fr))`, gap 12px. Two card variants (toggle via a "kartenVariante" setting — Kompakt/tile or Übersicht/detailed):
    - **Kompakt (tile) card**: solid color background per Badi type (river=purple `#6E3BF2`, lake=ink `#173D34`, outdoor=orange `#F47B43`, indoor=black; closed venues render dark grey `#4A4A4A` at 68% opacity), white text, border-radius 22px, padding 16px 17px. Shows type label, venue name, large guest count (40px Outfit 600) + "Gäste jetzt" label, status dot + temp inline, and a small bar-gauge of typical hourly load with a "now" highlight bar.
    - **Übersicht (detailed) card**: light grey background (`#F7F7F6`/`#F4F4F4` open/closed), border-radius 22px, padding 16-17px. Shows type label + optional note, venue name (Outfit 19px 600), large guest count (44px) at top-right with "Gäste jetzt" label, status row (dot + "offen"/"geschlossen", temp, favorite star button), then a bottom section "Auslastung heute" with a line+area sparkline chart (SVG, not canvas) and a deviation indicator (▲/▼/≈ + "X% voller/ruhiger als sonst").
  - Favorite star toggle (☆/★) on every card; persisted client-side.

**Footer:** small monospace attribution block (data sources: Sportamt Stadt Zürich, Crowdmonitor API) + external link "stadt-zuerich.ch ↗".

### 2. Detail — Modal Overlay
**Purpose:** Deep dive on one Badi: current guest count, temperature, hours, and a historical/typical usage chart with day/period toggles.

**Layout:**
- Full-screen dark scrim (`rgba(0,0,0,.55)`, backdrop-blur 2px), centered white sheet, `max-width:740px`, rounded `clamp(16px,4vw,28px)`, padding `clamp(16px,4vw,24px)`, scrollable.
- Header: type label + status pill (dot + "offen"/"geschlossen" + season), close "×" button top-right.
- Title row: venue name (Outfit, `clamp(28px,4vw,40px)`, 600) + favorite star button beside it; optional note line; address line (monospace, muted).
- **Three stat cards in a row** (flex, gap 10px, wrap on narrow screens, `min-width:150px` each, background `#F4F4F4`, border-radius 20px, padding `clamp(14px,3.5vw,20px)`):
  1. **Gäste jetzt** (guest count) — big number (Outfit 600, `clamp(36px,8vw,52px)`), clickable to expand a 7-day (Mo–So) guest-count comparison list, with today's row highlighted in the venue-type accent color.
  2. **Wassertemperatur** (water temp) — same pattern, big number + "°", expandable 7-day temp comparison list. Disabled/no-expand when temp is null (shown as "–").
  3. **Öffnigszeite** (opening hours) — shown only when venue is open today; big hours string, expandable 7-day hours list. Hidden entirely when closed.
  - **Important interaction rule (recently changed):** the Guest and Temperature cards are visually adjacent ("nebeneinander", side-by-side) and are meant to feel like one paired unit — clicking either one expands **both together**. The Hours card only joins that combined expand/collapse when all three cards are actually rendered in the same visual row (e.g. wide/desktop layout); on narrower layouts where Hours wraps to its own row below, it expands/collapses independently. Implementation detail: group membership is decided by comparing the live rendered top-offset of each card at click time, not a fixed breakpoint — replicate with an equivalent "are these two elements currently in the same row" check (e.g. compare bounding rects) rather than a hardcoded media query, so it stays correct across arbitrary container widths.
- **"Wie voll isch es" (how full is it) section**: heading, then a row of period tabs — "Hüt" (today, purple), "Die Wuche" (the week, ink), "Summer" (☀ orange), optionally "Winter" (❄ black, only for year-round/indoor venues) — plus, when "Hüt" is active, a secondary resolution toggle ("15 Min" / "Std") and a "Zoom" button. When "Die Wuche" is active, a full weekday selector row appears (Mäntig/Zistig/Mittwuch/Dunstig/Friitg/Samstig/Suntig — Swiss-German day names, abbreviated to 2 letters on narrow widths).
  - Chart: custom SVG bar/line chart, y-axis gridlines with formatted value labels, x-axis hour/day labels. "Today" mode shows a bell-curve-shaped typical-load profile with the actual current value overlaid as a highlighted bar/ghost-line deviation marker. "Week" mode shows an area+line chart with a dashed "average" line and a solid "actual" line. "Season" modes show a coarser month-by-month bar profile. Zoom mode makes the chart horizontally scrollable at fixed per-bar pixel width and auto-scrolls to center the "now" marker.

## Interactions & Behavior
- Tapping a list card opens the Detail overlay for that venue (resets weekday to Saturday, period to "heute", all three stat-card expansions closed) and scrolls to top.
- Tapping the scrim (outside the sheet) or the "×" button closes the overlay back to the list. Clicks inside the sheet don't propagate to the scrim.
- Favorite star: toggles a boolean per venue id, persisted to `localStorage` (key `wasserzeit_favs`), independent of open/closed state of the venue.
- Filter chips and sort tabs: single-select, instantly re-filter/re-sort the list client-side.
- Guest/Temp/Hours stat-card expand: see the paired-row rule above. No animation duration specified beyond CSS default transitions on hover shadows (150ms) and background changes.
- All hover states: cards get a stronger box-shadow (`0 4px 22px rgba(23,61,52,.14)` light cards / `.22` on colored tiles) on hover; no color changes.
- Closed venues are visually de-emphasized (opacity ~0.6–0.68, grey status colors, "–" placeholders for guest count) but remain visible/browsable, not hidden.
- No page transitions/routing — everything is a single-page state machine (`screen: 'home' | 'detail'`).

## State Management
Minimal client state, no backend calls in the prototype (data is static/simulated per venue):
- `screen`: `'home' | 'detail'`
- `currentId`: id of venue shown in detail
- `sort`: `'ruhig' | 'warm'` (quietest / warmest)
- `filter`: `'alle' | 'fluss' | 'see' | 'frei' | 'halle' | 'fav'`
- `weekday`: `'mo'|'di'|'mi'|'do'|'fr'|'sa'|'so'` (chart weekday selector, detail view)
- `period`: `'heute' | 'woche' | 'sommer' | 'winter'` (chart period selector, detail view)
- `hoursOpen` / `tempOpen` / `guestOpen`: booleans, expand state of the three stat cards (see paired-row rule)
- `favs`: `{ [venueId]: true }`, persisted to `localStorage`
- `chartRes`: `'Fein (15-Min)' | 'Stündlich'`, chart resolution for "today" period
- `chartZoomed`: boolean, horizontal-scroll zoom mode for the chart

In production, guest counts, temperatures, open/closed status, and deviation-from-typical values should come from live data (see Assets/data sources below) rather than the static seed array in the prototype; the "typical" curve shapes (bell curve per venue, weighted by a popularity/amplitude value) can be derived from historical aggregation.

## Design Tokens

**Colors**
- Background: `#E4E2E0` (page), `#FFFFFF` (cards), `#F4F4F4`/`#F7F7F6` (nested/closed card surfaces)
- Ink (primary text/accent): `#173D34`
- Purple accent (favorites, river venues, "today" period): `#6E3BF2` (hover/alt `#7849F1`)
- Orange accent (outdoor pools, "summer" period): `#F47B43`
- Black accent (indoor pools, "winter" period): `#000000`
- Muted/meta text: `#8C8C8C`
- Disabled/placeholder grey: `#CFCFCC` / `#DEDEDE` / `#E9E9E9` / `#ECECE9`
- Selection highlight: `#6E3BF2` bg / white text

**Typography**
- Display/headings: **Outfit**, weights 300/400/500/600/700
- Body/UI/monospace data: **IBM Plex Sans** (400/500/600) for body copy; **IBM Plex Mono** (400/500/600) for all labels, meta text, numbers, buttons, timestamps
- Key sizes: H1 `clamp(28px,4vw,40px)` 600; card title 19px 600; big stat numbers `clamp(36px,8vw,52px)` / 40–44px on cards; meta/labels 9.5–12.5px, often uppercase with `letter-spacing: .1–.12em`

**Spacing / Shape**
- Outer page padding: `clamp(16px,3.5vw,40px)`
- Card border-radius: 20–28px (large containers), 999px (pills/buttons)
- Card gap: 12px (grid), 22px (page sections), 6–10px (chip rows)
- Card shadow: `0 4px 22px rgba(23,61,52,.08)` default, `.14`–`.22` on hover

## Assets
No bitmap images or icon assets — all visuals (charts, gauges, sparklines, favorite star) are drawn as inline SVG generated from data, plus a Unicode "★/☆" glyph for favorites and "▲/▼/≈" for deviation arrows. No external icon font. Two Google Fonts: Outfit, IBM Plex Mono/IBM Plex Sans (loaded via Google Fonts CDN link in the file).

**Data sources (for real implementation):**
- Water temperature & open/closed status: Sportamt Stadt Zürich
- Live visitor counts: Crowdmonitor (`badi-public.crowdmonitor.ch:9591/api`)
- "Typical/average load" curves: not an official source — bespoke aggregation from collected live data (should be re-derived from real historical data in production, not hardcoded per-venue constants as in the prototype)
- Official data portal link: https://www.stadt-zuerich.ch/stzh/bathdatadownload

## Files
- `Wasserzeit.dc.html` — the full design reference (template + view logic + static seed data for 22 Zürich Badis). Read the `RAW` array and `cardVM`/`detailVM` methods for exact per-venue field shapes and the precise conditional/formatting rules (number formatting with Swiss thousands-separator `'`, comma decimals, occupancy word/color logic, deviation-from-typical thresholds at ±10%, etc).
