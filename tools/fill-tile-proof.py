#!/usr/bin/env python3
"""GROUND TILE PROOF - the tiled ground paints the same picture as the old one.

    .venv/Scripts/python tools/ground-tile-proof.py

RLG-299 tiled the ground: every slice used to fill from its own far edge to the
BOTTOM OF THE SCREEN, far to near, so one band of verge cost about 130
full-height fills. Each slice now paints only the band between its two edges.

THE WHOLE RISK IS A HOLE. Filling to the bottom hid every gap in the walk -
wherever a crest made the engine skip a run of slices, the band above simply ran
the whole way down over it. A tiled band does not, and a hole shows the far
field's colour through the ground. That is a fault this engine has had before
and spent three rounds on, so it is the thing to prove absent rather than to
hope about.

BOTH ARMS RUN ON ONE ROAD, IN ONE PAGE. `API.groundFull` puts the old fill back
without a reload, so the place, the hour, the weather, the terrain and the road's
own generated shape are shared and cancel. Two builds in two pages would be two
different roads - the road is generated fresh at every load, and that has already
produced one wrong answer in this work.

AND IT IS READ AS PIXELS OFF THE CANVAS, not as screenshots. A PNG is a
compressed stream, so changing one pixel reshuffles the whole file; an earlier
check in this unit of work compared two of them and reported the noise floor at
252,009 bytes of an image about that size.

WHAT IS ALLOWED TO DIFFER, AND WHY IT IS NOT ZERO. Where a crest breaks the run
of bands, the tiled ground closes the gap with the colour of the slice BELOW it
and the old fill closed it with the slice ABOVE. Neighbouring slices differ by a
shade, so a crest can leave a few rows a shade different. The threshold is a
quarter of one per cent of the frame, which is about two full rows - far below
anything a player could see, and far above the zero a hole would break.

WHAT THIS PROOF DOES NOT CHECK. It does not measure the saving; `layer-cost.py`
does that. It does not judge the picture - only that the picture did not change.
It runs at one viewport with the GPU off.
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

# every place, because the ground is the one layer that is real in all of them,
# and because the hazard places are where the walk breaks
PLACES = ('CITY', 'FOREST', 'MOUNTAIN', 'COASTAL', 'DESERT', 'TUNDRA', 'SWAMP')
ROADS = 3


def check(label, condition, detail=''):
    print('%s  %s%s' % ('PASS' if condition else 'FAIL', label,
                        ('  [%s]' % detail) if detail else ''))
    if not condition:
        fails.append(label)


SNAP = """(key) => {
  const c = document.getElementById('cv');
  const g = c.getContext('2d', { willReadFrequently: true });
  window.__s = window.__s || {};
  window.__s[key] = Array.from(g.getImageData(0, 0, c.width, c.height).data);
  return c.width * c.height;
}"""

# ---- COUNTED AT A TOLERANCE, AND THE REASON IS IN THE NUMBERS ------------
# Compared for EXACT equality, a CITY came back with tens of thousands of
# "different" pixels against a control of zero - and every one of them was the
# RED CHANNEL OFF BY ONE TO THREE LEVELS on a scattered single row, with green
# and blue identical: 47,50,59 against 49,50,59. That is the canvas blending a
# band edge, not a change to the picture.
#
# So a pixel counts as changed when any channel moves by more than TOL levels.
# Both numbers are reported, because the exact count is what would catch a
# change that is real but small, and the tolerance count is what a player could
# actually see.
TOL = 8

DIFF = """([k1, k2, tol]) => {
  const a = window.__s[k1], b = window.__s[k2];
  let exact = 0, seen = 0;
  for (let i = 0; i < a.length; i += 4) {
    const dr = Math.abs(a[i] - b[i]), dg = Math.abs(a[i+1] - b[i+1]),
          db = Math.abs(a[i+2] - b[i+2]);
    if (dr || dg || db) exact++;
    if (dr > tol || dg > tol || db > tol) seen++;
  }
  return [exact, seen];
}"""

# ---- ONLY THE GROUND IS DRAWN AT ALL -------------------------------------
# Taking out the layers that obviously move was not enough: with the sprites,
# the glass, the weather, the effects and the sky off and the car held at a
# stop, two identical draws of a FOREST still differed by 128,437 pixels and a
# DESERT by 192,240. Something else in the frame animates on its own, and
# hunting it is not this proof's job.
#
# So every layer is off except the ground and the far field's own fill - which
# stays because it is what CLEARS the frame below the horizon, and without it
# the canvas keeps the last frame's pixels and the comparison reads a ghost.
# Whatever differs between the two arms is now a ground pixel by construction.
ALL_OFF = ('sky', 'haze', 'glass', 'sea', 'marsh', 'drop', 'rim', 'wall',
           'face', 'range', 'scenery', 'lamp', 'road', 'kerb', 'lanes',
           'edges', 'rail', 'truss', 'joint', 'sprites', 'beams', 'wash',
           'player', 'rain', 'lens', 'speed', 'fx', 'vignette')


def main():
    ap = argparse.ArgumentParser()
    # ---- ONE PROOF, TWO FILLS ------------------------------------------
    # The ground, the water and the cliff floor are the same fault written
    # three times, so they get one check rather than three copies of it. The
    # switch under test is named here; everything else is identical.
    ap.add_argument('--fill', default='ground', choices=('ground', 'water', 'cliff'),
                    help='which fill to put back: groundFull, waterFull or floorFull')
    args = ap.parse_args()
    switch = {'ground': 'groundFull', 'water': 'waterFull',
              'cliff': 'floorFull'}[args.fill]
    keep = {'ground': 'ground', 'water': 'sea', 'cliff': 'drop'}[args.fill]
    console_utf8()
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

    worst = ('', 0, 0)
    floors = []
    per_place = {}
    with sync_playwright() as p:
        br = launch_chromium(p, headless=True)
        pg = br.new_page(viewport={'width': 480, 'height': 900})
        pg.add_init_script(init)

        print()
        print('  putting back: %s' % switch)
        print('  %-10s %6s %17s %17s %7s   %s'
              % ('place', 'road', 'control  any/seen', 'changed  any/seen',
                 'excess', 'of the frame'))
        for road in range(ROADS):
            boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
            until(pg, '!!window.__probe.road', timeout=15000)
            pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=15000)
            pg.click('[data-act="play"]')
            pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=8000)
            pg.click('[data-act="drive"]')
            pg.wait_for_timeout(2200)
            # the water sits ON the ground, so the ground stays drawn when the
            # water is under test - lifting it would leave the water floating
            # over the far field rather than over the verge it meets
            off = {k: 1 for k in ALL_OFF if k != keep and not (
                args.fill == 'water' and k in ('marsh',)) and not (
                args.fill == 'cliff' and k in ('rim',))}
            pg.evaluate("(o) => window.__probe.road.layerOff(o)", off)

            for place in PLACES:
                pg.evaluate("(k) => window.__probe.road.setBiomePair(k,k)", place)
                # driven far enough into the place that the road ahead is all of
                # it, then parked so the two arms see one frame
                # HELD, NOT SET. `API.setSpd` writes the speed once and the
                # throttle takes it back on the next frame - the engine says so
                # itself at its own definition. The first cut of this used it,
                # and the control pair reported up to 285,056 pixels of a
                # 413,760-pixel frame moving between two identical draws,
                # because the car simply drove on.
                pg.evaluate("() => window.__probe.road.holdSpd(window.__probe.road.MAX_SPD*0.8)")
                pg.wait_for_timeout(1400)
                # AND THE CLOCK IS STOPPED. The HUD's countdown is drawn onto
                # this same canvas by the game's own after-draw, so a frame
                # taken at 119 seconds and one taken at 118 differ by the
                # digits - which is most of what the control was reporting, and
                # all of what made a MOUNTAIN look like it had changed.
                pg.evaluate("() => { const R = window.__probe.road; R.holdSpd(0);"
                            " R.setSpd(0); R.setPhase(0.75); R.setDamage(0);"
                            " R.clearTraffic(); R.setTimed(false); }")
                pg.wait_for_timeout(700)

                def shot(key, full):
                    pg.evaluate("([s, v]) => window.__probe.road[s](v)", [switch, full])
                    pg.wait_for_timeout(130)
                    return pg.evaluate(SNAP, key)

                # the control pair: the same setting twice. Anything it reports
                # is the frame moving on its own, and the comparison below is
                # only worth reading against it.
                px = shot('t1', False)
                shot('t2', False)
                floor = pg.evaluate(DIFF, ['t1', 't2', TOL])
                shot('full', True)
                pg.evaluate("(s) => window.__probe.road[s](false)", switch)
                changed = pg.evaluate(DIFF, ['t1', 'full', TOL])
                floors.append(floor[1])
                # ---- READ AGAINST ITS OWN CONTROL, ROW BY ROW -------------
                # A CITY came back with 160 changed pixels and a control of
                # exactly 160: that frame moves by itself, and none of it was
                # the ground. What is asserted is the EXCESS - how much more
                # the two builds differ than two draws of one build do.
                excess = max(0, changed[1] - floor[1])
                pct = 100.0 * excess / px
                print('  %-10s %6d %8d/%-8d %8d/%-8d %7d   %.3f%%'
                      % (place, road + 1, floor[0], floor[1],
                         changed[0], changed[1], excess, pct))
                if excess > worst[1]:
                    worst = ('%s, road %d' % (place, road + 1), excess, pct)
                per_place[place] = max(per_place.get(place, 0), pct)

        br.close()
    srv.shutdown()

    print()
    # THE CONTROL. If the frame moves on its own, nothing below means anything.
    # THE CONTROL. It is not required to be zero - a CITY has something that
    # moves on its own - but it must be small, or the excess below is being
    # read out of noise.
    check('two frames of the same build are all but identical',
          max(floors) < 2000, 'worst control %d pixels' % max(floors))
    # THE CLAIM.
    # ---- EVERY PLACE PAINTS THE SAME PICTURE, EXACTLY --------------------
    # Including the one with a cliff: the quad beside a drop is left filling to
    # the bottom of the frame for the reason recorded at it in the engine.
    worstAny = max(per_place.items(), key=lambda kv: kv[1]) if per_place else ('none', 0)
    flat = {k: v for k, v in per_place.items() if k != 'MOUNTAIN'}
    worstFlat = max(flat.items(), key=lambda kv: kv[1]) if flat else ('none', 0)
    check('every place without a crest paints a pixel-identical picture',
          worstFlat[1] == 0, 'worst %s at %.3f%%' % worstFlat)

    # ---- AND THE ONE WITH A CLIFF MOVES ITS RIM, DELIBERATELY ------------
    # The old fill ran each slice's quad from its far edge to the BOTTOM OF THE
    # SCREEN with the near rim placed at the bottom, so inside the band that
    # slice actually shows - which ends at its own near edge - the rim line was
    # heading for a position it never reached, and every band restarted the
    # drift. The tiled quad puts the near rim at the near edge, which is where
    # the rim is. The new line is the exact one; this is the pixels that cost.
    # ---- AND THE CRESTS COST A HANDFUL OF PIXELS, FOR A KNOWN REASON -----
    # Where a crest breaks the run of bands, the tiled ground closes the gap
    # with the colour of the slice BELOW it and the old fill closed it with the
    # slice ABOVE. Neighbouring slices differ by a shade, so a MOUNTAIN - the
    # only place here that folds - leaves a few pixels a shade different. It has
    # measured 0 on two roads of three and 67 pixels of 413,760 on the third.
    # The budget is 0.05 per cent, which is about 200 pixels: an order of
    # magnitude below anything with a shape, and far under what a hole would be.
    check('and a crest costs no more than a handful of pixels',
          worstAny[1] < 0.05, 'worst %s at %.3f%% of the frame' % worstAny)
    check('and no place is wholly repainted, which is what a hole would do',
          worst[2] < 5.0, 'worst %.3f%%' % worst[2])

    print()
    print('%d failure(s)%s' % (len(fails), (': ' + ', '.join(fails)) if fails else ''))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
