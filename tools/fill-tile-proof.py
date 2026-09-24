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

DIFF = """([k1, k2, tol, minY, maxY, maxX]) => {
  const c = document.getElementById('cv');
  const a = window.__s[k1], b = window.__s[k2];
  const first = Math.floor(minY * c.height) * c.width * 4;
  const last = maxY > 0 ? Math.floor(maxY * c.height) * c.width * 4 : a.length;
  const xEnd = maxX > 0 ? Math.floor(maxX * c.width) : c.width;
  let exact = 0, seen = 0;
  for (let i = first; i < last; i += 4) {
    if (maxX > 0 && ((i / 4) % c.width) >= xEnd) continue;
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
    ap.add_argument('--fill', default='ground', choices=('ground', 'water', 'cliff', 'sky', 'vignette'),
                    help='which fill to put back: groundFull, waterFull, floorFull or bakedOff')
    ap.add_argument('--phase', type=float, default=0.75,
                    help='the hour to pin: 0.00 dusk, 0.25 midnight, 0.50 dawn, 0.75 midday')
    args = ap.parse_args()
    switch = {'ground': 'groundFull', 'water': 'waterFull',
              'cliff': 'floorFull', 'sky': 'bakedOff',
              'vignette': 'bakedOff'}[args.fill]
    # what stays drawn while everything else is taken away. The baked arm needs
    # both of the gradients it bakes.
    keep = {'ground': ('ground',), 'water': ('sea', 'marsh'),
            'cliff': ('drop', 'rim'),
            'sky': ('sky',),
            # the sky stays drawn with the vignette, because it is what CLEARS
            # the top of the frame - and a vignette drawn with alpha over an
            # uncleared canvas composites over its own last draw and darkens
            # until it saturates, which is not a comparison of anything
            'vignette': ('vignette',)}[args.fill]
    # ---- THE GAUGES ARE ON THIS CANVAS TOO ---------------------------
    # The dials are drawn onto the game's own canvas by the after-draw, and their
    # needles settle for a while after the car is stopped - so a comparison of
    # the WHOLE frame never had a still control, and reported 5,352 pixels moving
    # between two identical draws. The fills all sit below the horizon and are
    # read whole; the two baked gradients cover the frame, so they are read down
    # to 0.6 of it, which is above the dials and well into both of them.
    # ---- AND EACH ONE IS READ WHERE IT ACTUALLY PAINTS ------------------
    # THE SKY'S BAND WAS WRONG FIRST AND THE CHECK PASSED ON IT. Both baked
    # gradients were read at 0.45 to 0.60 of the frame - which is BELOW the
    # horizon, where the sky paints nothing at all. Zero was guaranteed and the
    # proof was a ceremony. The sky is read ABOVE the horizon, which sits near
    # 0.40 of the frame, and the vignette below it.
    # THE VIGNETTE'S BAND WAS WRONG AND THE CHECK PASSED ON A BROKEN BAKE.
    # Read at 0.45 to 0.60 of the frame, it reported every place identical even
    # with the baked image built at 0.40 alpha against the live 0.55 - because
    # that band is the middle of a radial that is TRANSPARENT there. A vignette
    # has to be read where it is dark, which is the top and the corners.
    MAXY = {'sky': 0.34, 'vignette': 0.99}.get(args.fill, 0)
    # ---- AND NOTHING CLEARS A CANVAS WITH THE SKY AND THE FAR GROUND OFF -
    # The vignette is drawn with alpha, so with nothing clearing the frame it
    # composites over its own last draw and DARKENS every frame until it
    # saturates - which the control caught as 3,889 pixels moving between two
    # identical draws. The far field's fill stays on for these two, because it
    # is what clears below the horizon, and the comparison reads the band it
    # clears: under the horizon and above the dials.
    MINY = {'sky': 0.02, 'vignette': 0.90}.get(args.fill, 0)
    # ---- AND THE VIGNETTE IS READ IN ITS BOTTOM-LEFT CORNER --------------
    # It has to be read somewhere that is DARK, that something CLEARS, and that
    # nothing else animates. The middle of the frame is transparent, the top is
    # the sky's and its clouds drift, and the bottom right is where the dials
    # are drawn onto this same canvas. The bottom-left corner is the one place
    # that is all three: the far field's fill clears it every frame, the radial
    # is at its darkest there, and nothing moves in it.
    MAXX = 0.30 if args.fill == 'vignette' else 0
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
    stats = None
    with sync_playwright() as p:
        br = launch_chromium(p, headless=True)
        pg = br.new_page(viewport={'width': 480, 'height': 900})
        pg.add_init_script(init)

        print()
        print('  putting back: %s' % switch)
        print('  %-14s %2s %17s %17s %7s   %s'
              % ('place', 'rd', 'control  any/seen', 'changed  any/seen',
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
            off = {k: 1 for k in ALL_OFF if k not in keep}
            # THE BAKED ARM TAKES THE GROUND AWAY AS WELL. Everything else in
            # ALL_OFF leaves the verge drawn, because the water and the cliff sit
            # on it - but the two baked gradients sit on nothing, and with the
            # road pass still running the control could not settle. Only the sky
            # and the vignette are left, so any difference is one of them.
            if args.fill in ('sky', 'vignette'):
                off['ground'] = 1
            pg.evaluate("(o) => window.__probe.road.layerOff(o)", off)

            # ---- A MOUNTAIN IS MEASURED TWICE WHEN THE GROUND IS UNDER TEST -
            # The ground beside a cliff is tiled, and that MOVES THE RIM - the
            # one part of this work that changes the picture on purpose. A bound
            # on it would only say the change is small. Measuring the same place
            # again with `API.dropOff`, which paints the ground straight across
            # and leaves no rim at all, says WHERE the change is: if that arm is
            # pixel-identical then every changed pixel was the rim.
            todo = [(p2, False) for p2 in PLACES]
            if args.fill == 'ground':
                todo.append(('MOUNTAIN', True))
            for place, noRim in todo:
                pg.evaluate("(v) => window.__probe.road.dropOff(v)", noRim)
                label = place + (' no rim' if noRim else '')
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
                    # THE HOUR IS RE-PINNED AT EVERY SNAPSHOT. `setPhase` sets the
                    # clock, it does not stop it, and the sky's colours move with
                    # it - so two frames 130ms apart have different skies and the
                    # control reported 9,368 pixels of a still frame moving.
                    pg.evaluate("(v) => window.__probe.road.setPhase(v)", args.phase)
                    pg.wait_for_timeout(130)
                    pg.evaluate("(v) => window.__probe.road.setPhase(v)", args.phase)
                    return pg.evaluate(SNAP, key)

                # the control pair: the same setting twice. Anything it reports
                # is the frame moving on its own, and the comparison below is
                # only worth reading against it.
                px = shot('t1', False)
                shot('t2', False)
                floor = pg.evaluate(DIFF, ['t1', 't2', TOL, MINY, MAXY, MAXX])
                shot('full', True)
                pg.evaluate("(s) => window.__probe.road[s](false)", switch)
                changed = pg.evaluate(DIFF, ['t1', 'full', TOL, MINY, MAXY, MAXX])
                floors.append(floor[1])
                # ---- READ AGAINST ITS OWN CONTROL, ROW BY ROW -------------
                # A CITY came back with 160 changed pixels and a control of
                # exactly 160: that frame moves by itself, and none of it was
                # the ground. What is asserted is the EXCESS - how much more
                # the two builds differ than two draws of one build do.
                excess = max(0, changed[1] - floor[1])
                pct = 100.0 * excess / px
                print('  %-14s %2d %8d/%-8d %8d/%-8d %7d   %.3f%%'
                      % (label, road + 1, floor[0], floor[1],
                         changed[0], changed[1], excess, pct))
                if excess > worst[1]:
                    worst = ('%s, road %d' % (label, road + 1), excess, pct)
                per_place[label] = max(per_place.get(label, 0), pct)

        if args.fill in ('sky', 'vignette'):
            stats = pg.evaluate("() => window.__probe.road.bakeStats()")
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
    rim = 'MOUNTAIN' if args.fill == 'ground' else None
    if args.fill in ('sky', 'vignette'):
        # ---- AND THE CACHE HAS TO ACTUALLY BE A CACHE -------------------
        # A baked image rebuilt on every frame paints exactly the same pixels
        # and is SLOWER than no cache at all, and every check above would pass
        # on it. So the counters are read: how many times each image was drawn
        # again, against how many frames used the one already there.
        st = stats or {}
        # THE VIGNETTE CAN ONLY BE REBUILT BY A RESIZE, so it is held to a hard
        # line. THE SKY CANNOT BE: its four stop colours move with the hour, and
        # the hour moves every frame, so the cache is rebuilt whenever a colour
        # changes by one level. Measured at about one frame in four - which
        # still makes copies of the other three, and whether that is a net win
        # is `fill-gain.py --fill baked`'s question, not this one's. The line
        # here is only that the image is reused more often than it is rebuilt.
        for name, ratio in ((args.fill, 1 if args.fill == 'sky' else 8),):
            built, hit = st.get(name, 0), st.get(name + 'Hit', 0)
            check('the %s image is reused more than it is rebuilt' % name,
                  hit > built * ratio,
                  'rebuilt %d times against %d frames that reused it, %d%% rebuilt'
                  % (built, hit, round(100.0 * built / max(1, built + hit))))
    flat = {k: v for k, v in per_place.items() if k != rim}
    worstFlat = max(flat.items(), key=lambda kv: kv[1]) if flat else ('none', 0)
    # ---- A CREST COSTS A HANDFUL OF PIXELS, FOR A KNOWN REASON -----------
    # Where a crest breaks the run of bands, a tiled fill closes the gap with
    # the colour of the slice BELOW it and the old fill closed it with the slice
    # ABOVE. Neighbouring slices differ by a shade, so a place that folds leaves
    # a few pixels a shade different: measured at 67 of 413,760 on one road and
    # 12 on another, and zero on most. The budget is 0.05 per cent, about 200
    # pixels - an order of magnitude below anything with a shape, and far below
    # what a hole would be.
    check('every place paints the same picture, to within a crest',
          worstFlat[1] < 0.05, 'worst %s at %.3f%%' % worstFlat)

    # ---- AND THE ONE WITH A CLIFF MOVES ITS RIM, DELIBERATELY ------------
    # The old fill ran each slice's quad from its far edge to the BOTTOM OF THE
    # SCREEN with the near rim placed at the bottom, so inside the band that
    # slice actually shows - which ends at its own near edge - the rim line was
    # heading for a position it never reached, and every band restarted the
    # drift. The tiled quad puts the near rim at the near edge, which is where
    # the rim is. The new line is the exact one; this is the pixels that cost.
    # ---- THE ONE PLACE THAT CHANGES, AND ONLY WHERE IT IS MEANT TO -------
    # The line above already proves the MOUNTAIN arm with no rim is identical,
    # because that arm is in `flat`. So whatever the arm WITH a rim reports is
    # the rim, and nothing else. It is bounded as well, because a rim that moved
    # a long way would be a fault rather than an exact line.
    # THE BOUND IS MEASURED, NOT CHOSEN. Across six roads the rim moved by
    # 0.011, 0.053, 0.082, 0.134, 0.280 and 1.531 per cent of the frame - a
    # sliver along a long diagonal edge, wider when the cliff is near the
    # camera. An earlier gap fill that stepped square across the rim instead of
    # following it reached 7.8 per cent, so 2.5 sits above the line and an
    # order of magnitude below the fault it would catch.
    if rim:
        check('a cliff rim moves, and it is the only thing that does',
              per_place.get(rim, 0) < 2.5,
              '%s at %.3f%% of the frame, and %s no rim at %.3f%%'
              % (rim, per_place.get(rim, 0), rim, per_place.get(rim + ' no rim', 0)))
    check('and no place is wholly repainted, which is what a hole would do',
          worstAny[1] < 5.0, 'worst %.3f%%' % worstAny[1])

    print()
    print('%d failure(s)%s' % (len(fails), (': ' + ', '.join(fails)) if fails else ''))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
