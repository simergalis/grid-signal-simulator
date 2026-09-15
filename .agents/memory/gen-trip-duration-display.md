---
name: Gen-trip duration display
description: Operator-facing formatting for generator-trip contingency durations.
---

Gen-trip ride-through and generator close timing should be shown as rounded minutes,
using hours and minutes when the duration is at least one hour, rather than exposing
raw seconds in the compact operator status tile.

**Why:** Raw second values are difficult to interpret quickly during an operational
decision; the tile is meant to communicate the practical response horizon.

**How to apply:** Keep the compact status tile and its details modal on the same
hours/minutes convention. Preserve infinity/full-reserve states as a non-numeric label.