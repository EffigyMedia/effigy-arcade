#!/usr/bin/env python3
"""CARRYOVER TEST - does any pixel of the frame survive from the frame before it?

    EFFIGY_NO_GPU=1 PYTHONIOENCODING=utf-8 .venv/Scripts/python tools/carryover-test.py
    ... tools/carryover-test.py --places MOUNTAIN --stops 10 --selftest

Owner, 2026-09-24 and again 2026-09-26, from the device: "When the road falls away after a
crest, the ground (not the road) is see through", and "when the player crests a hill the
ground is invisible beyond a certain y cording on screen." [[RLG-337]]

▶ WHY A NEW CHECK WHEN crest-hole-test ALREADY ASKS ABOUT THE CREST. That one compares the
tiled ground against the old fill-to-the-bottom, so it can only find ground the OLD fill
painted. This asks a different and larger question: is every pixel of the frame painted by
THIS frame at all. A region nothing paints is see-through whatever put the hole there, and
the answer does not depend on knowing which layer was supposed to cover it.

▶ HOW IT ASKS. The canvas is never cleared - the sky and the far field's fill are what
cover it, and everything else is painted over them. So a pixel nothing paints this frame
still holds what the LAST frame left there. Park the car, photograph the frame, send the
car far up the road so that a completely different picture is drawn, bring it back to the
same spot, and photograph again. Every pixel that something painted comes out identical.
Every pixel that nothing paints comes back carrying the other picture.

A PARKED CAR IS WHY THIS FAULT HAS SURVIVED FOUR ROUNDS OF MEASUREMENT. Every harness here
stops the car to hold the tone, the hour and the weather still, and a hole over a still
picture shows the frame before it - which is the same frame. It is invisible by
construction. The jump is what puts a different picture underneath without the car, the
hour or the weather moving at all.

▶ AND THE CONTROL IS THE SAME JOURNEY TWICE. Two round trips land on the same spot from the
same place, so whatever they carry over they carry over alike: B against B is what the
frame's own restlessness is worth, and it is subtracted from the finding rather than
assumed to be zero. The day clock, the weather and the traffic are pinned and cleared for
the same reason.

▶ --selftest PROVES THE CHECK CAN FAIL, AND WHAT IT TAKES TO MAKE IT FAIL IS ITSELF THE
ANSWER TO HALF THE QUESTION. Switching the GROUND off is not enough: the run came back at
zero carried pixels, because the far field's own fill paints from the horizon down before
the ground does and CLEARS the whole band every frame. So the selftest takes `farground`
away as well, and only then is there a region nothing paints. That result stands on its
own: below the horizon this renderer cannot carry a pixel over, so see-through ground is
not a hole showing the frame before it. Four guards in this project passed with the bug
present before they were fixed, and this one would have been the fifth.
"""
import argparse
import functools
import http.server
import io
import socketserver
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
from harness import console_utf8, launch_chromium, boot, until   # noqa: E402
from playwright.sync_api import sync_playwright                  # noqa: E402

fails = []

DEFAULT_PLACES = 'MOUNTAIN,CANYON,FOREST'

# a channel has to move by more than this for a pixel to count as carried over. The canvas
# antialiases an edge differently depending on nothing anybody controls, and a level or two
# of that is not a hole.
TOL = 6

# the title bar and the HUD are drawn by the shell over the top of the canvas and are not
# the road's to paint, so the read starts below the horizon, which is where the ground is.
# `API.horizon` is asked at every sample because a crest moves it.
HORIZON_PAD = 2

# ---- WHAT --selftest TAKES AWAY, AND WHY IT IS THIS LONG A LIST --------------
# A falsifier has to open a hole that nothing could be mistaken for. Switching off the
# GROUND alone left 823 pixels against a control of 859, which is not a proof of anything:
# the far field's fill still cleared the band, and the road, the rail, the drop, the
# massif and the scenery still covered nearly all of what was left. Every layer that
# paints below the horizon comes off, and the massif with them - it has its own switch and
# `layerOff` cannot reach it.
FALSIFY = ('ground', 'farground', 'road', 'kerb', 'lanes', 'edges', 'rail', 'truss',
           'joint', 'drop', 'rim', 'cliff', 'scenery', 'lamp', 'sea', 'marsh', 'wall',
           'face', 'range', 'sprites', 'player', 'beams')

SNAP = """(key) => {
  const c = document.getElementById('cv');
  const g = c.getContext('2d', { willReadFrequently: true });
  window.__s = window.__s || {};
  window.__s[key] = Array.from(g.getImageData(0, 0, c.width, c.height).data);
  return [c.width, c.height];
}"""

# ---- WHERE THE TWO PICTURES DISAGREE, AND HOW FAR DOWN THE FRAME -------------
# The rows are counted as well as the pixels: the owner's report is that the ground goes
# from a row DOWNWARD, so the top row of the carry-over is the number that matches the
# words, and it is printed whether the run passes or fails.
CMP = """([a, b, tol, fromY]) => {
  const c = document.getElementById('cv');
  const A = window.__s[a], B = window.__s[b];
  const w = c.width, h = c.height, y0 = Math.floor(fromY * h);
  let n = 0, top = -1, bot = -1, left = w, right = -1;
  for (let y = y0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4;
      if (Math.max(Math.abs(A[i] - B[i]), Math.abs(A[i+1] - B[i+1]),
                   Math.abs(A[i+2] - B[i+2])) <= tol) continue;
      n++;
      if (top < 0) top = y;
      bot = y;
      if (x < left) left = x;
      if (x > right) right = x;
    }
  }
  return { n: n, top: top, bot: bot, left: left, right: right,
           px: w * (h - y0), h: h };
}"""


def check(label, condition, detail=''):
    print('%s  %s%s' % ('PASS' if condition else 'FAIL', label,
                        ('  [%s]' % detail) if detail else ''))
    if not condition:
        fails.append(label)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--places', default=DEFAULT_PLACES)
    ap.add_argument('--stops', type=int, default=8, help='places along the road to read at')
    ap.add_argument('--hill', type=float, default=1.0,
                    help='the hill factor forced onto each place. 1.0 is the hilliest the '
                         'game ships. Pass -1 to leave the place as it is')
    ap.add_argument('--phase', type=float, default=0.75, help='0.75 is midday')
    ap.add_argument('--away', type=int, default=400000,
                    help='how far up the road the car is sent between the two frames')
    ap.add_argument('--drive', type=int, default=900, help='ms of driving per hunting burst')
    ap.add_argument('--hunt', type=int, default=30,
                    help='bursts of driving spent looking for a crest before reading anyway')
    ap.add_argument('--min-skips', type=int, default=2,
                    help='slices behind a crest that make a read count as a crest read')
    ap.add_argument('--allow', type=int, default=1200,
                    help='pixels of carry-over that count as none. Measured, not guessed. '
                         'At three settling passes two identical journeys came back 988 '
                         'pixels apart on one stop in four; at five they came back 33 '
                         'apart over eight stops in two places, so the number was the '
                         'frame settling and not the road. The selftest opens a hole of '
                         '4,064 to 15,040, which is where the two regimes sit')
    ap.add_argument('--selftest', action='store_true',
                    help='run one stop with the ground AND the far fill switched off, '
                         'and fail if that does not register as carry-over')
    ap.add_argument('--trace', action='store_true',
                    help='print the crest count at every burst of the hunt')
    ap.add_argument('--shots', default='', help='where to write a picture of each stop that carries over')
    args = ap.parse_args()
    console_utf8()

    places = [p for p in args.places.split(',') if p]
    shots = Path(args.shots) if args.shots else (ROOT / 'docs' / 'fleet' / '_carryover')

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

    worst = {'n': 0}
    worst_ctrl = 0
    reads = 0
    crested = 0
    selftest_saw = -1
    print()
    print('  %-9s %3s %7s %8s %8s %8s  %s'
          % ('place', 'st', 'hidden', 'control', 'carried', 'of', 'rows'))
    try:
        with sync_playwright() as p:
            br = launch_chromium(p, headless=True)
            pg = br.new_page(viewport={'width': 480, 'height': 900})
            pg.add_init_script(init)
            for place in places:
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
                # THE RUN CLOCK KILLS ANY HARNESS THAT PARKS THE CAR (RLG-125), and this
                # one parks at every stop.
                pg.evaluate("""([k]) => { const R = window.__probe.road;
                    R.setTimed(false); R.clearTraffic(); R.setDmg(0);
                    R.setBiomePair(k, k); R.watchDraw(true); }""", [place])

                def pin():
                    # EVERYTHING THAT MOVES THE PICTURE ON ITS OWN, HELD. The place, the
                    # hour, the weather and the snow all tint the land and not one of them
                    # stops while the car is parked - `setPhase` sets the clock, it does
                    # not halt it. crest-hole-test read up to 21,515 pixels of drift
                    # before it pinned all four.
                    pg.evaluate("""([k, v]) => { const R = window.__probe.road;
                        R.setBiomePair(k, k); R.setPhase(v); R.setWet(0); R.setSnow(0);
                        R.setInstanceTemp(0.5); R.clearTraffic(); }""", [place, args.phase])

                def visit(z, key, settle=5):
                    """stand at z, let the frame draw, and photograph it"""
                    pg.evaluate("(q) => { const R = window.__probe.road;"
                                " R.holdSpd(0); R.setSpd(0); R.jumpTo(q); }", z)
                    for _ in range(settle):
                        pin()
                        pg.wait_for_timeout(160)
                    return pg.evaluate(SNAP, key)

                for stop in range(args.stops):
                    cr = {'n': 0}
                    seen = []
                    for _ in range(args.hunt):
                        pg.evaluate("() => window.__probe.road.holdSpd("
                                    "window.__probe.road.MAX_SPD * 0.75)")
                        pg.wait_for_timeout(args.drive)
                        pg.evaluate("() => { const R = window.__probe.road;"
                                    " R.holdSpd(0); R.setSpd(0); }")
                        pg.wait_for_timeout(250)
                        cr = pg.evaluate("() => window.__probe.road.groundSkips()")
                        seen.append(cr['n'])
                        if cr['n'] >= args.min_skips:
                            break
                    # the countdown after a wreck holds the world still behind a banner,
                    # and two frames taken across it compare a banner
                    for _ in range(20):
                        if pg.evaluate("() => window.__probe.road.launch().count") <= 0:
                            break
                        pg.wait_for_timeout(500)
                        pin()

                    here = pg.evaluate("() => window.__probe.road.roadPos()"
                                       " + window.__probe.road.PLAYER_Z")
                    away = here + args.away
                    away2 = here + args.away * 2 + 137000

                    off = bool(args.selftest and stop == 0 and place == places[0])
                    if off:
                        # THE GROUND ALONE IS NOT A HOLE - the far field's fill covers the
                        # same band, and so do the road, the rail and the massif.
                        pg.evaluate("(o) => { const R = window.__probe.road;"
                                    " R.layerOff(o); R.massModel({ off: 1 }); }",
                                    {k: 1 for k in FALSIFY})

                    # ---- THE READING, AND ITS CONTROL --------------------------------
                    # THREE JOURNEYS TO THE SAME SPOT, AND TWO OF THEM ARE THE SAME
                    # JOURNEY. A and C are arrived at from one place up the road, B from a
                    # different one. A against C is the control - same journey twice, so
                    # whatever the frame carries over anyway it carries alike. A against B
                    # is the finding, because the only thing that differs is the picture
                    # that was on the canvas before.
                    #
                    # NOTHING IS PHOTOGRAPHED STRAIGHT OFF THE HUNT. The first cut read A
                    # immediately after three quarters of top speed and got 9,925 pixels
                    # against a control of nothing, which is the dials and the lamps still
                    # settling rather than a hole. Every read now arrives the same way.
                    visit(away, 'x')
                    visit(here, 'a')
                    visit(away2, 'x')
                    visit(here, 'b')
                    visit(away, 'x')
                    visit(here, 'c')
                    if off:
                        pg.evaluate("() => { const R = window.__probe.road;"
                                    " R.layerOff({}); R.massModel({ off: 0 }); }")

                    fromY = pg.evaluate(
                        "(pad) => { const c = document.getElementById('cv');"
                        " return (window.__probe.road.horizon() + pad) / c.height; }",
                        HORIZON_PAD)
                    ctrl = pg.evaluate(CMP, ['a', 'c', TOL, fromY])
                    got = pg.evaluate(CMP, ['a', 'b', TOL, fromY])
                    reads += 1
                    if cr['n'] >= args.min_skips:
                        crested += 1
                    if args.trace:
                        print('        hunted: %s' % seen)
                    rows = ('rows %d-%d, x %d-%d'
                            % (got['top'], got['bot'], got['left'], got['right'])
                            ) if got['n'] else ''
                    print('  %-9s %3d %7d %8d %8d %8d  %s%s'
                          % (place, stop + 1, cr['n'], ctrl['n'], got['n'], got['px'],
                             rows, '   <- ground OFF, selftest' if off else ''))
                    if off:
                        selftest_saw = got['n']
                        continue
                    if ctrl['n'] > worst_ctrl:
                        worst_ctrl = ctrl['n']
                    if got['n'] > worst['n']:
                        worst = dict(got, place=place, stop=stop + 1, ctrl=ctrl['n'])
                    if got['n'] > args.allow:
                        shots.mkdir(parents=True, exist_ok=True)
                        pg.screenshot(path=str(shots / ('carry_%s_s%d.png'
                                                        % (place, stop + 1))))
            br.close()
    finally:
        srv.shutdown()

    print()
    print('  %d read(s) across %d place(s), %d of them with a crest in view'
          % (reads, len(places), crested))
    print('  control: worst %d pixel(s) carried between two identical journeys' % worst_ctrl)
    if worst['n']:
        print('  worst: %d pixel(s) of %d, rows %d-%d, at %s stop %d'
              % (worst['n'], worst['px'], worst['top'], worst['bot'],
                 worst['place'], worst['stop']))
    print()
    if args.selftest:
        check('the check can fail - the ground and the far fill switched off carry over',
              selftest_saw > args.allow,
              '%d pixel(s) with nothing painting below the horizon' % selftest_saw)
    check('the reading reached crests at all', crested > 0,
          '%d of %d read(s) had at least %d slice(s) hidden behind a crest'
          % (crested, reads, args.min_skips))
    check('two identical journeys draw the same frame', worst_ctrl <= args.allow,
          '%d pixel(s) moved between two identical journeys' % worst_ctrl)
    check('nothing in the frame survives from the frame before it',
          worst['n'] <= args.allow,
          ('%d pixel(s) at %s stop %d, rows %d-%d'
           % (worst['n'], worst['place'], worst['stop'], worst['top'], worst['bot']))
          if worst['n'] else 'every pixel below the horizon was painted this frame')
    print()
    if fails:
        print('FAILED: %d' % len(fails))
        for f in fails:
            print('  - %s' % f)
        sys.exit(1)
    print('ALL CHECKS PASSED')


if __name__ == '__main__':
    main()
