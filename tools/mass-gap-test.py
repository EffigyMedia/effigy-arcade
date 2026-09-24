#!/usr/bin/env python3
"""MASS GAP TEST - every slice of the up face is painted by something.

    EFFIGY_NO_GPU=1 PYTHONIOENCODING=utf-8 .venv/Scripts/python tools/mass-gap-test.py
    ... tools/mass-gap-test.py --places CANYON --stops 12

Owner, 2026-09-24, from the device, with shots of both places that have a mass: "there is
a strip not rendering on the upward face. It's at a static distance so it stays there. Like
all the strips passing through a certain spot don't get rendered." [[RLG-336]]

THE UP FACE IN THOSE TWO PLACES IS THE MASSIF, NOT THE WALL. `drawRoad`'s wall painter
hands the side over with `if(dB.mass && !massOff) continue`, and MOUNTAIN and CANYON are
the only two places in the game that declare `mass:1`. So `wallSeam`, which the first read
of this report pointed at, never runs for either of them and cannot be the cause.

WHAT IS CHECKED. `massSlice` merges a run of slices into one quad past `MASS_MERGE` of the
draw. The engine records which slices each quad COVERS, and this asserts that every slice
in the draw is covered by one. Nothing here reimplements the merge rule - a check that
re-derives the decision it is checking agrees with itself and proves nothing, which is
RLG-065's lesson and this file would have been the fourth to learn it.

THE GAP IT WAS WRITTEN AGAINST, measured on a draw of 300 with MASS_RUN 6 and MASS_MERGE
0.40: the anchors stood at n = 125, 131 and 137 against a threshold of 120, so n = 121 to
124 was covered by nothing at all, identically in both places. The merge test read the
SLICE's distance while the run is anchored on the slice's ABSOLUTE index, and the two
disagree at the boundary.

AND IT HOLDS STATION BECAUSE THE THRESHOLD IS A FRACTION OF THE DRAW, which is a fixed
distance ahead of the car - so the hole sits at one spot in the picture while the world
moves through it. That is the owner's "static distance" exactly, and it is the thing that
tells this fault apart from anything belonging to a piece of world.

TO WATCH IT FAIL, put the merge test back on the slice's own distance in `massSlice`:
`if(n > DRAW * MASS_MERGE)` in place of `if(n - inRun > DRAW * MASS_MERGE)`.
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

# the only two places that declare a mass, which is what makes this their fault and not
# every place's. A third would have to be added here the day one is added to the table.
DEFAULT_PLACES = 'CANYON,MOUNTAIN'

READ = """() => {
  const R = window.__probe.road, m = R.massModel();
  return { run: m.run, merge: m.merge, quads: m.quads, slices: m.slices,
           draw: R.drawSegments(), pos: Math.round(R.roadPos()),
           covered: Object.keys(m.covered).map(Number),
           painted: Object.keys(m.top).map(Number) };
}"""


def check(label, condition, detail=''):
    print('%s  %s%s' % ('PASS' if condition else 'FAIL', label,
                        ('  [%s]' % detail) if detail else ''))
    if not condition:
        fails.append(label)


def gaps(covered, lo, hi):
    """the runs of slice numbers between lo and hi that nothing covered"""
    have = set(covered)
    out = []
    for n in range(lo, hi + 1):
        if n in have:
            continue
        if out and n == out[-1][-1] + 1:
            out[-1].append(n)
        else:
            out.append([n])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--places', default=DEFAULT_PLACES)
    ap.add_argument('--stops', type=int, default=10,
                    help='places along the road to read the draw at')
    ap.add_argument('--drive', type=int, default=700, help='ms of driving between reads')
    ap.add_argument('--near', type=int, default=8,
                    help='slices nearest the car to leave out - the massif is behind the '
                         'camera there and the road pass drops them for its own reasons')
    args = ap.parse_args()
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

    worst = {'len': 0}
    reads = 0
    print()
    print('  %-9s %3s %6s %7s %8s %8s  %s'
          % ('place', 'st', 'draw', 'quads', 'covered', 'widest', 'gaps'))
    with sync_playwright() as p:
        br = launch_chromium(p, headless=True)
        pg = br.new_page(viewport={'width': 480, 'height': 900})
        pg.add_init_script(init)
        for place in [q for q in args.places.split(',') if q]:
            boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
            until(pg, '!!window.__probe.road', timeout=15000)
            pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=15000)
            pg.click('[data-act="play"]')
            pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=8000)
            pg.click('[data-act="drive"]')
            pg.wait_for_timeout(2000)
            pg.evaluate("(k) => window.__probe.road.setBiomePair(k, k)", place)
            # THE RUN CLOCK KILLS ANY HARNESS THAT PARKS THE CAR (RLG-125), and this one
            # stops ten times.
            pg.evaluate("() => { const R = window.__probe.road;"
                        " R.setTimed(false); R.clearTraffic(); R.watchDraw(true); }")
            for stop in range(args.stops):
                # THE CAR IS MOVED BETWEEN READS AND THE REASON IS THE FAULT ITSELF.
                # The run's anchor is fixed in the WORLD and the threshold is fixed
                # against the CAR, so which slices fall either side of it depends on
                # where the car is standing. One read would be one alignment out of six.
                pg.evaluate("() => window.__probe.road.holdSpd("
                            "window.__probe.road.MAX_SPD * 0.5)")
                pg.wait_for_timeout(args.drive)
                pg.evaluate("() => { const R = window.__probe.road;"
                            " R.holdSpd(0); R.setSpd(0); }")
                pg.wait_for_timeout(350)
                d = pg.evaluate(READ)
                reads += 1
                run = gaps(d['covered'], args.near, d['draw'])
                widest = max([len(g) for g in run] or [0])
                print('  %-9s %3d %6d %7d %8d %8d  %s'
                      % (place, stop + 1, d['draw'], d['quads'], len(d['covered']),
                         widest, [(g[0], g[-1]) for g in run][:6]))
                if widest > worst['len']:
                    worst = {'len': widest, 'place': place, 'stop': stop + 1,
                             'at': [(g[0], g[-1]) for g in run if len(g) == widest],
                             'thr': d['draw'] * d['merge'], 'painted': sorted(d['painted'])}
        br.close()

    print()
    print('  %d read(s) across %d place(s)' % (reads, len(args.places.split(','))))
    if worst['len']:
        print('  widest gap %d slice(s) at %s stop %d, %s, with the merge threshold at n=%.0f'
              % (worst['len'], worst['place'], worst['stop'], worst['at'], worst['thr']))
    print()
    check('the draw was actually read', reads > 0, '%d read(s)' % reads)
    check('every slice of the up face is covered by a quad',
          worst['len'] == 0,
          ('widest gap %d slice(s) at %s, %s'
           % (worst['len'], worst['place'], worst['at']))
          if worst['len'] else 'no gap at any read, in any place')
    print()
    if fails:
        print('FAILED: %d' % len(fails))
        for f in fails:
            print('  - %s' % f)
        sys.exit(1)
    print('ALL CHECKS PASSED')


if __name__ == '__main__':
    main()
