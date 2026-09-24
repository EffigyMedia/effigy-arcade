#!/usr/bin/env python3
"""CREST HOLE TEST - does the tiled ground leave a hole where the road falls away?

    EFFIGY_NO_GPU=1 PYTHONIOENCODING=utf-8 .venv/Scripts/python tools/crest-hole-test.py
    ... tools/crest-hole-test.py --places MOUNTAIN --hill 1.0 --stops 12

Owner, 2026-09-24, from the device: "When the road falls away after a crest, the ground
(not the road) is see through." [[RLG-337]]

THIS ANSWERS ONE QUESTION AND NOTHING ELSE: is that hole the TILING? `API.groundFull(true)`
puts the old fill-to-the-bottom back at runtime, so both arms run on ONE road in ONE page
and the place, the hour, the weather and the road's own generated shape all cancel. If the
tiled arm is missing ground the full arm paints, it is [[RLG-299]]'s tiling and it is ours.
If the two agree everywhere, the hole is the older fault at the far field's fill, and the
next step is a different one.

WHY THIS EXISTS WHEN `fill-tile-proof.py` ALREADY COMPARES THE SAME TWO ARMS. That proof
parks the car wherever it happens to be after a fixed wait, at seven places on three roads,
and found them pixel-identical. It could only prove what stood in front of it, and a crest
severe enough to break the chain of bands may simply never have. This one FORCES the
geometry: the hill factor is raised so the road folds hard, and the car stops at many
places along each road instead of one.

AND IT READS THE HOLE, NOT JUST A DIFFERENCE. A shade along a band edge is not a hole; a
hole is what lies behind the ground showing THROUGH it. So three frames are taken at each
stop - tiled, full, and the same frame with the ground layer off altogether - and a
differing pixel only counts as a hole when it matches the frame that has no ground in it.
Both counts are printed, because the plain difference is what would catch a change that is
real but small.

THE BOTTOM OF THE FRAME IS COUNTED SEPARATELY. The old fill ran every band to the bottom of
the screen, so the first band alone covered it. A tiled chain reaches the bottom only if
some slice's near edge does, and a road that folds at the camera may have no such slice.
That is a hole the total would report as one number among many, so it gets its own bound.

A CREST HAS TO BE IN VIEW OR THE SAMPLE SAYS NOTHING, and the car is driven until one is.
`API.groundSkips` reports the slices the walk dropped because they sit behind a crest, which
is exactly the stretch whose absence the chain of bands has to cover. THE INVERTED SLICE IS
NOT THE CREST and was tried first: over forty samples with the hill factor at its ceiling,
every inversion in the draw was under three tenths of a pixel, which is the road flattening
toward the horizon rather than a hill.

WHAT IT DOES NOT DO. It judges no picture and measures no frame rate. It runs at one
viewport with the GPU off, and every figure is software rasterisation.
"""
import argparse
import functools
import http.server
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot, until   # noqa: E402
from playwright.sync_api import sync_playwright                  # noqa: E402

fails = []

# every place whose ground is plain field, plus the two with a roll hazard - they paint a
# cut quad rather than a band, and that arm of the tiling closes the same gaps
DEFAULT_PLACES = 'FOREST,CITY,MOUNTAIN,TUNDRA,DESERT,SWAMP,COASTAL'

# every layer off except the ground and the far field's own fill, which stays because it is
# what CLEARS the frame below the horizon - without it the canvas keeps the last frame's
# pixels and the comparison reads a ghost. fill-tile-proof.py learned that expensively.
ALL_OFF = ('sky', 'haze', 'glass', 'sea', 'marsh', 'drop', 'rim', 'wall',
           'face', 'range', 'scenery', 'lamp', 'road', 'kerb', 'lanes',
           'edges', 'rail', 'truss', 'joint', 'sprites', 'beams', 'wash',
           'player', 'rain', 'lens', 'speed', 'fx', 'vignette')

# a pixel counts as changed when a channel moves by more than this. The canvas antialiases a
# band edge and reports the red channel off by one to three levels on scattered rows, which
# is not a change to the picture.
TOL = 8

# ---- READ FROM THE HORIZON DOWN, AND THE HORIZON IS ASKED FOR ----------------
# Nothing clears the frame above the horizon once the sky is off, so what sits up there
# is the last frame that drew anything - a ghost. It is STILL, so a control pair never
# catches it, and two arms that ghosted different frames would be compared as though the
# ground had changed. The far field's fill clears from the horizon down and that is the
# band the ground paints in, so that is the band that is read. `API.horizon` is asked at
# every sample rather than guessed, because a crest moves it.
HORIZON_PAD = 4
# and the bottom eighth is where the old fill's reach to the screen edge is judged
BOT_Y = 0.875

SNAP = """(key) => {
  const c = document.getElementById('cv');
  const g = c.getContext('2d', { willReadFrequently: true });
  window.__s = window.__s || {};
  window.__s[key] = Array.from(g.getImageData(0, 0, c.width, c.height).data);
  return [c.width, c.height];
}"""

CTRL = """([tol, fromY]) => {
  const c = document.getElementById('cv');
  const a = window.__s.c1, b = window.__s.c2;
  let n = 0;
  for (let i = Math.floor(fromY * c.height) * c.width * 4; i < a.length; i += 4)
    if (Math.max(Math.abs(a[i] - b[i]), Math.abs(a[i+1] - b[i+1]),
                 Math.abs(a[i+2] - b[i+2])) > tol) n++;
  return n;
}"""

# ---- THE HOLE, AS OPPOSED TO A DIFFERENCE ------------------------------------
# `tiled` against `full` says the two arms disagree. `tiled` against `bare` - the same frame
# with the ground layer off altogether - says the tiled arm is showing what lies BEHIND the
# ground. A pixel that is both is a hole.
#
# AND "MATCHES BARE" IS A MUCH TIGHTER TEST THAN "DIFFERS FROM FULL". The first cut used one
# tolerance for both and reported holes that were not holes: at a row read as see-through the
# three arms came out tiled 44,47,54 / full 52,57,65 / bare 51,54,62, so the tiled arm was
# EIGHT levels off the bare frame and was counted as equal to it, while the coverage
# composited from the band list for that same row was 1.000 - the ground was there and a
# shade dark. Bare means bare: BARE_TOL is levels, not a shade.
BARE_TOL = 2
HOLE = """([tol, fromY, botY, bareTol]) => {
  const c = document.getElementById('cv');
  const S = window.__s, t = S.tiled, f = S.full, b = S.bare;
  const w = c.width, h = c.height;
  const y0 = Math.floor(fromY * h), yB = Math.floor(botY * h);
  let diff = 0, hole = 0, holeBot = 0, topHole = -1, botRow = -1;
  for (let y = y0; y < h; y++) {
    let rowHole = 0;
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4;
      if (Math.max(Math.abs(t[i] - f[i]), Math.abs(t[i+1] - f[i+1]),
                   Math.abs(t[i+2] - f[i+2])) <= tol) continue;
      diff++;
      if (Math.max(Math.abs(t[i] - b[i]), Math.abs(t[i+1] - b[i+1]),
                   Math.abs(t[i+2] - b[i+2])) <= bareTol) {
        hole++; rowHole++;
        if (topHole < 0) topHole = y;
      }
    }
    if (rowHole) { botRow = y; if (y >= yB) holeBot += rowHole; }
  }
  return { diff: diff, hole: hole, holeBot: holeBot, topHole: topHole,
           botRow: botRow, px: w * (h - y0) };
}"""

# the slices the walk dropped because a crest stands in front of them, and the largest drop
CREST = """() => {
  const R = window.__probe.road, s = R.groundSkips();
  return { crests: s.n, worst: s.worst };
}"""


def check(label, condition, detail=''):
    print('%s  %s%s' % ('PASS' if condition else 'FAIL', label,
                        ('  [%s]' % detail) if detail else ''))
    if not condition:
        fails.append(label)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--places', default=DEFAULT_PLACES)
    ap.add_argument('--roads', type=int, default=2,
                    help='reloads - the road is generated fresh at every load')
    ap.add_argument('--stops', type=int, default=8, help='places along each road to stop at')
    ap.add_argument('--hill', type=float, default=1.0,
                    help='the hill factor forced onto each place. 1.0 is the hilliest the '
                         'game ships. Pass -1 to leave the place as it is')
    ap.add_argument('--phase', type=float, default=0.75, help='0.75 is midday')
    ap.add_argument('--drive', type=int, default=900, help='ms of driving per hunting burst')
    ap.add_argument('--hunt', type=int, default=14,
                    help='bursts of driving to spend looking for a crest before sampling anyway')
    ap.add_argument('--min-skips', type=int, default=4,
                    help='slices behind a crest that make a sample count as a crest sample')
    ap.add_argument('--settle', type=int, default=6,
                    help='tries to let the frame go still before reading it')
    ap.add_argument('--quiet', type=int, default=120,
                    help='pixels of movement between two identical draws that counts as still')
    ap.add_argument('--shots', default='',
                    help='where to write a picture of each stop that shows a hole')
    args = ap.parse_args()
    console_utf8()

    places = [p for p in args.places.split(',') if p]
    shots = Path(args.shots) if args.shots else (ROOT / 'docs' / 'fleet' / '_crest_hole')

    h = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    srv = socketserver.TCPServer(('127.0.0.1', 0), h)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    init = """
    window.__probe = { road: null };
    (function(){ var real=null, wrapped=null;
      Object.defineProperty(window,'ROAD',{configurable:true,
        get:function(){return real?wrapped:undefined;},
        set:function(fn){real=fn;wrapped=function(CFG){var api=real(CFG);
          window.__probe.road=api||(CFG&&CFG.api)||null;return api;};}});})();
    """

    worst = {'hole': 0}
    worst_rim = {'hole': 0}
    worst_bot = {'holeBot': 0}
    worst_diff = {'diff': 0}
    quiet_floors = []
    samples = 0
    quiet_samples = 0
    restless = 0
    crested = 0
    print()
    print('  hill forced to %s, %d place(s), %d road(s), %d stop(s) each'
          % ('the place\'s own' if args.hill < 0 else '%.2f' % args.hill,
             len(places), args.roads, args.stops))
    print()
    print('  %-9s %2s %3s %7s %7s %8s %8s %8s %8s  %s'
          % ('place', 'rd', 'st', 'hidden', 'bypx', 'control', 'diff', 'hole',
             'no rim', 'where'))
    with sync_playwright() as p:
        br = launch_chromium(p, headless=True)
        pg = br.new_page(viewport={'width': 480, 'height': 900})
        pg.add_init_script(init)
        for place in places:
            for road in range(args.roads):
                boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
                until(pg, '!!window.__probe.road', timeout=15000)
                pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=15000)
                pg.click('[data-act="play"]')
                pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=8000)
                pg.click('[data-act="drive"]')
                pg.wait_for_timeout(2000)
                if args.hill >= 0:
                    pg.evaluate("([k, hl]) => window.__probe.road.setBiomeShape(k, hl, null)",
                                [place, args.hill])
                pg.evaluate("(k) => window.__probe.road.setBiomePair(k, k)", place)
                off_ground = {k: 1 for k in ALL_OFF}
                off_ground['ground'] = 0
                pg.evaluate("(o) => window.__probe.road.layerOff(o)", off_ground)
                # THE RUN CLOCK KILLS ANY HARNESS THAT PARKS THE CAR (RLG-125). A parked car
                # reaches no checkpoint, the sixty seconds run out, and every driving number
                # freezes where it stood. Eight stops are well past that.
                pg.evaluate("() => { const R = window.__probe.road;"
                            " R.setTimed(false); R.clearTraffic(); R.setDmg(0); }")
                pg.evaluate("() => window.__probe.road.watchDraw(true)")

                def pin():
                    # ---- EVERYTHING THAT MOVES THE GROUND'S TONE, HELD -----------
                    # The place, the hour, the weather and the snow on the land all
                    # tint the ground, and not one of them stops on its own while the
                    # car is parked. `setBiomePair` starts the place again rather than
                    # stopping its countdown, `setPhase` sets the clock rather than
                    # halting it, and the cover keeps accumulating.
                    pg.evaluate("([k, v]) => { const R = window.__probe.road;"
                                " R.setBiomePair(k, k); R.setPhase(v);"
                                " R.setWet(0); R.setSnow(0); R.setInstanceTemp(0.5); }",
                                [place, args.phase])

                for stop in range(args.stops):
                    # ---- DRIVEN UNTIL A CREST IS ACTUALLY IN FRONT OF THE CAR ------
                    # A sample taken on flat road cannot say anything about a fault
                    # reported at a crest, and a fixed wait lands wherever it lands.
                    # HELD, NOT SET: `setSpd` writes the speed once and the throttle
                    # takes it back on the next frame - the engine says so at its own
                    # definition, and fill-tile-proof paid for finding out.
                    cr = {'crests': 0, 'worst': 0}
                    for _ in range(args.hunt):
                        pg.evaluate("() => window.__probe.road.holdSpd("
                                    "window.__probe.road.MAX_SPD * 0.75)")
                        pg.wait_for_timeout(args.drive)
                        pg.evaluate("() => { const R = window.__probe.road;"
                                    " R.holdSpd(0); R.setSpd(0); }")
                        pg.wait_for_timeout(300)
                        cr = pg.evaluate(CREST)
                        if cr['crests'] >= args.min_skips:
                            break
                    # ---- AND THE COUNTDOWN IS WAITED OUT ---------------------------
                    # The car can wreck against the roadside on the way to a crest, and
                    # the run then starts again with GO over the frame and the world
                    # held still until it clears. Two captures taken across that are a
                    # comparison of a banner. `API.launch().count` is the countdown.
                    for _ in range(20):
                        if pg.evaluate("() => window.__probe.road.launch().count") <= 0:
                            break
                        pg.wait_for_timeout(500)
                        pin()

                    def shot(key, full, bare=False):
                        # ---- THE WHOLE LAYER STATE, EVERY TIME -----------------------
                        # `layerOff` takes the layers named and PUTS EVERY OTHER ONE
                        # BACK - its own note says so, and it is deliberate, so that an
                        # alternating harness never has to remember what it turned off
                        # last. Passing `{ground: 0}` on its own therefore restores the
                        # sky, the sprites, the weather and the glass, and this check
                        # read the resulting animation as up to 29,194 pixels of hole.
                        off = {k: 1 for k in ALL_OFF}
                        off['ground'] = 1 if bare else 0
                        pg.evaluate("([f, o]) => { const R = window.__probe.road;"
                                    " R.groundFull(f); R.layerOff(o); }", [full, off])
                        # ---- THE HOUR AND THE PLACE ARE BOTH RE-PINNED AT EVERY
                        # SNAPSHOT. `setPhase` sets the clock, it does not stop it, and
                        # the ground's tone moves with the light. `setBiomePair` does not
                        # stop the countdown either - the game starts its own change of
                        # place while the car is parked, and the ground then blends from
                        # one tone to the other for as long as it takes. That was read as
                        # up to 21,515 pixels moving between two identical draws, and it
                        # only began on the fourth stop, which is what made it look like a
                        # fault rather than a clock.
                        pin()
                        pg.wait_for_timeout(140)
                        pin()
                        return pg.evaluate(SNAP, key)

                    # ---- THE CONTROL PAIR, AND THE FRAME IS WAITED OUT UNTIL IT IS
                    # QUIET. The same setting twice: whatever it reports is the frame
                    # moving on its own, and nothing below means anything under it. The
                    # first cut read the pair once and got 2,290 to 4,665 pixels, which
                    # swallowed every figure whole - the car had just come off three
                    # quarters of its top speed and the dials were still settling.
                    fromY = pg.evaluate(
                        "(pad) => { const c = document.getElementById('cv');"
                        " return (window.__probe.road.horizon() + pad) / c.height; }",
                        HORIZON_PAD)
                    ctrl = None
                    for _ in range(args.settle):
                        shot('c1', False)
                        shot('c2', False)
                        ctrl = pg.evaluate(CTRL, [TOL, fromY])
                        if ctrl <= args.quiet:
                            break
                        pg.wait_for_timeout(700)
                    shot('tiled', False)
                    shot('full', True)
                    shot('bare', False, True)
                    r = pg.evaluate(HOLE, [TOL, fromY, BOT_Y, BARE_TOL])
                    # ---- AND THE SAME STOP AGAIN WITH NO CLIFF RIM ---------------
                    # Tiling the ground beside a drop MOVES THE RIM, and that is the one
                    # part of RLG-299 that changes the picture on purpose - the owner
                    # decided it on 2026-09-23 and fill-tile-proof measures it at up to
                    # 1.3 per cent of a MOUNTAIN. Ground that is missing because the rim
                    # moved is not a hole a crest opened, and the two would be added
                    # together in one number. `API.dropOff` paints the ground straight
                    # across and leaves no rim at all, so whatever survives that arm is
                    # not the rim.
                    pg.evaluate("() => window.__probe.road.dropOff(true)")
                    shot('tiled', False)
                    shot('full', True)
                    shot('bare', False, True)
                    pg.evaluate("() => window.__probe.road.dropOff(false)")
                    rn = pg.evaluate(HOLE, [TOL, fromY, BOT_Y, BARE_TOL])
                    pg.evaluate("(o) => { const R = window.__probe.road;"
                                " R.groundFull(false); R.layerOff(o); }", off_ground)
                    samples += 1
                    # ---- A SAMPLE THAT NEVER WENT STILL IS THROWN AWAY -----------
                    # Every figure below is a difference between two frames, so a frame
                    # that is still moving on its own cannot answer the question. The
                    # first cut kept such samples and raised the bound to swallow them,
                    # which is the same as not checking. They are counted and named
                    # instead, and too many of them fails the run on its own.
                    if ctrl > args.quiet:
                        restless += 1
                        print('  %-9s %2d %3d %7d %7.2f %8d   -- restless, discarded'
                              % (place, road + 1, stop + 1, cr['crests'], cr['worst'], ctrl))
                        continue
                    quiet_samples += 1
                    quiet_floors.append(ctrl)
                    if cr['crests'] >= args.min_skips:
                        crested += 1
                    where = ('rows %d-%d' % (rn['topHole'], rn['botRow'])) if rn['hole'] else ''
                    print('  %-9s %2d %3d %7d %7.2f %8d %8d %8d %8d  %s'
                          % (place, road + 1, stop + 1, cr['crests'], cr['worst'],
                             ctrl, r['diff'], r['hole'], rn['hole'], where))
                    if rn['hole'] > worst['hole']:
                        worst = dict(rn, place=place, road=road + 1, stop=stop + 1)
                    if rn['holeBot'] > worst_bot['holeBot']:
                        worst_bot = dict(rn, place=place, road=road + 1, stop=stop + 1)
                    if r['diff'] > worst_diff['diff']:
                        worst_diff = dict(r, place=place, road=road + 1, stop=stop + 1)
                    if r['hole'] > worst_rim['hole']:
                        worst_rim = dict(r, place=place, road=road + 1, stop=stop + 1)
                    if max(r['hole'], rn['hole']) > args.quiet:
                        # FOUR PICTURES, NOT TWO. The ground on its own is what shows the
                        # hole, because nothing else is in the frame to hide it; the whole
                        # scene is what the owner is looking at. Both arms of both.
                        shots.mkdir(parents=True, exist_ok=True)
                        stem = 'hole_%s_r%d_s%d' % (place, road + 1, stop + 1)
                        whole = {}
                        for view, layers in (('ground', off_ground), ('scene', whole)):
                            pg.evaluate("(o) => window.__probe.road.layerOff(o)", layers)
                            for arm, full in (('tiled', False), ('full', True)):
                                pg.evaluate("(v) => window.__probe.road.groundFull(v)", full)
                                pin()
                                pg.wait_for_timeout(140)
                                pg.screenshot(path=str(shots / ('%s_%s_%s.png'
                                                                % (stem, view, arm))))
                        pg.evaluate("([o]) => { const R = window.__probe.road;"
                                    " R.groundFull(false); R.layerOff(o); }", [off_ground])
        br.close()

    print()
    floor = max(quiet_floors) if quiet_floors else 0
    print('  %d sample(s) taken, %d still enough to read, %d discarded as restless'
          % (samples, quiet_samples, restless))
    print('  %d of the readable ones had a crest in view' % crested)
    print('  control: worst %d pixel(s) moving between two identical draws' % floor)
    print('  worst bare with the cliff rim in: %d pixel(s)%s'
          % (worst_rim['hole'],
             ('  [%s road %d stop %d]' % (worst_rim['place'], worst_rim['road'],
                                          worst_rim['stop'])) if worst_rim['hole'] else ''))
    print('  widest plain difference: %d pixel(s)%s'
          % (worst_diff['diff'],
             ('  [%s road %d stop %d]' % (worst_diff['place'], worst_diff['road'],
                                          worst_diff['stop'])) if worst_diff['diff'] else ''))
    print()
    # ---- WHAT IS ASSERTED, AND THE BOUND IS A QUARTER OF A ROW --------------------
    # The control is the noise floor and nothing under it means anything. It comes out at
    # zero once the place, the hour and the weather are pinned, so the bound is nearly
    # all margin - and it is deliberately SMALLER THAN ONE ROW OF THE FRAME, because a
    # hairline along a shared edge is the fault this codebase has met four times and the
    # rule it wrote down is to overlap the edge rather than meet on it. A bound of one
    # row would call a hairline clean. Restless samples are not in the floor; they were
    # thrown away.
    bound = floor + 120
    check('enough samples went still to read', quiet_samples >= max(3, samples // 2),
          '%d of %d readable, %d restless' % (quiet_samples, samples, restless))
    check('the sampling reached crests at all', crested > 0,
          '%d of %d readable samples had at least %d slice(s) hidden behind a crest'
          % (crested, quiet_samples, args.min_skips))
    check('the tiled ground leaves no hole the old fill covered',
          worst['hole'] <= bound,
          ('worst %d bare pixel(s) at %s road %d stop %d, rows %d-%d, bound %d'
           % (worst['hole'], worst['place'], worst['road'], worst['stop'],
              worst['topHole'], worst['botRow'], bound))
          if worst['hole'] else 'nothing bare anywhere, over %d readable samples'
          % quiet_samples)
    check('the tiled chain still reaches the bottom of the frame',
          worst_bot['holeBot'] <= bound,
          ('worst %d bare pixel(s) in the bottom eighth, at %s road %d stop %d'
           % (worst_bot['holeBot'], worst_bot['place'], worst_bot['road'],
              worst_bot['stop']))
          if worst_bot['holeBot'] else 'the bottom eighth is covered at every stop')
    print()
    if fails:
        print('FAILED: %d' % len(fails))
        for f in fails:
            print('  - %s' % f)
        sys.exit(1)
    print('ALL CHECKS PASSED')


if __name__ == '__main__':
    main()
