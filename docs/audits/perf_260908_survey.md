# Cursory optimisation survey — 2026-09-08, v0.13.37

Owner, 2026-09-07, closing the testing queue: *"let's finish with a cursory optimisation
analysis."* [RLG-168](../fragments/RLG-168.md).

**This is a survey and not a sweep.** It says where the frames go, what the worst case costs
and what would be worth doing. It changes no code. RLG-137 is the sweep and it stays where it
is.

**Every number carries its spread, and that is not a formality.** One unchanged build has
measured a forest at 48, 54 and 60 fps. Two scenery decisions were made against single
readings inside that spread before anyone noticed, and one reached a shipped changelog entry
before being withdrawn. **A change is only real if two ranges do not overlap.**

**Measured on a desktop browser at 480×900, headless, five samples a place.** That is not the
target device and no conclusion below is about a phone. What it can say is which places are
expensive *relative to each other*, and where the headroom has gone.

---

## What was measured

`tools/fps-test.py --phase 0.75 --samples 5` and the same at `--phase 0.25`. The hour is
pinned, because a sample that spans dusk is partly a measurement of the street lighting
switching on.

### Midday — only one place leaves the cap

| Place | fps, lowest–highest of 5 | samples |
|---|---|---|
| CITY | 60.4 – 60.4 | 60.4, 60.4, 60.4, 60.4, 60.4 |
| DESERT | 60.4 – 60.4 | 60.4, 60.4, 60.4, 60.4, 60.4 |
| **FOREST** | **51.6 – 60.0** | 51.6, 51.6, 60.0, 58.0, 58.0 |
| MOUNTAIN | 60.4 – 60.4 | 60.4, 60.4, 60.4, 60.4, 60.4 |
| TUNDRA | 56.4 – 60.4 | 58.8, 56.4, 60.4, 60.4, 60.4 |
| COASTAL | 60.4 – 60.4 | 60.4, 60.4, 60.4, 60.4, 60.4 |
| SWAMP | 57.2 – 60.4 | 59.6, 57.2, 59.6, 59.6, 60.4 |

**60.4 is the cap, not a measurement.** Five of seven places sit on it at midday, which means
the engine is finishing its frame with time to spare and the reading says nothing about how
much. Only the forest is genuinely working, and the tundra and the swamp are on the edge.

### Midnight — everywhere except the desert

| Place | fps, lowest–highest of 5 | samples |
|---|---|---|
| CITY | 49.2 – 59.6 | 59.6, 54.0, 56.0, 49.2, 49.2 |
| DESERT | 60.4 – 60.4 | 60.4, 60.4, 60.4, 60.4, 60.4 |
| **FOREST** | **44.4 – 52.0** | 44.4, 51.6, 52.0, 50.4, 52.0 |
| MOUNTAIN | 58.0 – 60.4 | 59.2, 59.2, 60.4, 58.8, 58.0 |
| TUNDRA | 49.6 – 59.2 | 59.2, 56.8, 49.6, 58.8, 56.0 |
| COASTAL | 54.8 – 60.4 | 57.6, 60.0, 58.8, 60.4, 54.8 |
| **SWAMP** | **47.6 – 53.6** | 51.2, 47.6, 48.8, 49.6, 53.6 |

---

## Findings

### 1. Night is the dominant term, and the forest is the worst place in it

**This is the headline and it is not what the record predicted.** The standing suspect was the
forest, named in the thread and in RLG-059, and the forest *is* the worst place at both hours —
but at midday it is the only place that leaves the cap, and at midnight **six of the seven
places do.** The forest loses about 8 fps going from day to night; the city loses about 10 and
the swamp about 9. Night costs more than the forest does.

**The forest at night is therefore the case to test on a device**, at 44.4–52.0. It is the
worst combination the game produces and it is the number RLG-149 — the owner's question about
an older iPad — should be asked against.

### 2. The desert is the control, and it says the cost is scenery rather than light

The desert holds 60.4 at midnight while everything else falls. Two candidates were separated:

- **Lit lamps are NOT the cost.** Counted per frame at midnight, the desert lights **415** and
  holds the cap, while the forest lights **304** and falls to 44. More lamps, no cost. Whatever
  night is charging for, it is not the number of lit bulbs.
- **Scenery volume is the common factor.** The desert has the least scenery of any place, and
  it is the only one that does not fall. The forest and the swamp have the most, and they fall
  furthest at both hours. Night appears to multiply a per-scenery-item cost rather than to add
  a fixed one.

**That is an inference from two data points and it is stated as one.** It has not been proved
by turning the scenery off, because this survey changes no code. **The next measurement anyone
takes should be exactly that**: a build with `SCENERY.FOREST.rows` or `rowDensity` cut, measured
against this table. If the forest's night range moves clear of 44–52, the mechanism is settled.

### 3. The vehicle sprite counts are not where the work is

Counted per frame, the drawn sprite totals run from 1 to 14 across every place at both hours,
with almost nothing culled and a handful clipped. **A dozen billboards is not a frame's work.**
Whatever the road is spending, it is not the cars.

---

## What would be worth doing, in order

1. **Prove the scenery mechanism before tuning anything.** Cut the forest's rows in a scratch
   build and re-run this table. One measurement settles finding 2, and finding 2 decides
   whether the levers named in the record are the right ones.
2. **Then decide the forest at night on a device rather than here.** 44–52 on a desktop browser
   has no fixed translation to a phone, and the whole point of RLG-149 is a device the engine
   has never been measured on.
3. **Leave the vehicle path alone.** Finding 3 says the sprites are not the cost, and a sweep
   through the drawing code would be spent where the time is not.

## What this survey does NOT say

- **Nothing about a phone.** Every number is a headless desktop browser. The relative ordering
  of places is likely to travel; the absolute numbers certainly do not.
- **Nothing about the frame's internals.** Where inside a frame the time goes was not profiled.
  This counts frames, not milliseconds by function.
- **Nothing about the new work in this queue individually.** The radar detector, the deer, the
  cloud form, the aurora and the far road were all added today and are all in these numbers;
  none was measured on its own against a build without it. If a regression is suspected later,
  this table is the baseline to measure against rather than the evidence that there is none.
