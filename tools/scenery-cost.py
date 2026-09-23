#!/usr/bin/env python3
"""SCENERY COST - which half of the scenery costs the frame, the walk or the raster.

    .venv/Scripts/python tools/scenery-cost.py

IT ASSERTS NOTHING. It is an instrument, not a gate.

WHY IT EXISTS. `layer-cost.py` found the scenery to be the largest single cost
anywhere in the frame - 18.0 fps in a CITY and 13.9 in a COASTAL, and nothing at
all in a MOUNTAIN - and unlike the three fills it came with NO known remedy. The
owner asked on 2026-09-23 for each cost to be proposed and fixed one at a time,
so this is the measurement that has to come before a line of it is changed.

THE QUESTION IS WHICH HALF, BECAUSE THE TWO HALVES WANT OPPOSITE FIXES. If the
cost is the WALK - the hashes, the projections, the crest gates, the saves and
clips, run per object per row per side per slice - then the remedy is to decide
sooner and walk less. If the cost is the RASTER - two `drawImage` calls per
object - then the remedy is to draw fewer or smaller objects, and walking less
would buy nothing.

THREE ARMS, ALTERNATING ON ONE ROAD IN ONE PAGE:

  full        everything as it ships
  no raster   the whole walk, and neither drawImage        -> full to this is the RASTER
  no scenery  the layer never runs                         -> this to no-raster is the WALK

`API.sceneryRaster` and `API.layerOff` are the two switches. Paired samples and
several roads, for the reasons recorded in `layer-cost.py`: this machine's
baseline swings too far for unpaired samples, and the road is generated fresh at
every load so one road is not a measurement.

IT ALSO COUNTS WHAT THE WALK DID, which is what turns a number into a remedy: how
many objects were painted, how many were thrown away as too small, off the side
of the screen, or hidden behind a crest - and how many of those were thrown away
AFTER the work of placing them was done.
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

COUNT = """(ms) => new Promise(res => {
  let n = 0; const t0 = performance.now();
  (function tick(){ n++;
    if (performance.now() - t0 < ms) requestAnimationFrame(tick);
    else res(n / ((performance.now() - t0) / 1000));
  })();
})"""


def median(xs):
    v = sorted(xs)
    n = len(v)
    return v[n//2] if n % 2 else (v[n//2 - 1] + v[n//2]) / 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--places', default='CITY,FOREST,COASTAL,SWAMP,DESERT,TUNDRA,MOUNTAIN')
    ap.add_argument('--roads', type=int, default=3)
    ap.add_argument('--rounds', type=int, default=3)
    ap.add_argument('--window', type=int, default=800)
    ap.add_argument('--phase', type=float, default=0.75)
    ap.add_argument('--speed', type=float, default=0.55)
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

    places = [x.strip() for x in args.places.split(',') if x.strip()]
    raster, walk, counts = {}, {}, {}
    with sync_playwright() as p:
        br = launch_chromium(p, headless=True)
        pg = br.new_page(viewport={'width': 480, 'height': 900})
        pg.add_init_script(init)
        for road in range(args.roads):
            boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
            until(pg, '!!window.__probe.road', timeout=15000)
            pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=15000)
            pg.click('[data-act="play"]')
            pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=8000)
            pg.click('[data-act="drive"]')
            pg.wait_for_timeout(2200)
            for place in places:
                pg.evaluate("(k) => window.__probe.road.setBiomePair(k,k)", place)
                # THE HOUR IS PINNED BEFORE THE OBJECTS ARE COUNTED. The first
                # cut counted them straight after the place was set, with the
                # clock wherever it had drifted to - and reported a CITY lighting
                # all 345 of its windows at midday, which is the count from dusk.
                pg.evaluate("(v) => window.__probe.road.setPhase(v)", args.phase)
                pg.evaluate("(v) => window.__probe.road.setSpd(window.__probe.road.MAX_SPD*v)",
                            args.speed)
                pg.wait_for_timeout(700)
                counts.setdefault(place, []).append(
                    pg.evaluate("() => window.__probe.road.sceneryCount()"))
                dR, dW = [], []
                for _ in range(args.rounds):
                    def arm(rasterOn, layerOn):
                        pg.evaluate("(v) => window.__probe.road.setSpd(window.__probe.road.MAX_SPD*v)",
                                    args.speed)
                        pg.evaluate("(v) => window.__probe.road.setPhase(v)", args.phase)
                        pg.evaluate("(v) => window.__probe.road.sceneryRaster(v)", rasterOn)
                        pg.evaluate("(o) => window.__probe.road.layerOff(o)",
                                    {} if layerOn else {'scenery': 1})
                        return pg.evaluate(COUNT, args.window)
                    full = arm(True, True)
                    noRaster = arm(False, True)
                    noScenery = arm(False, False)
                    dR.append(noRaster - full)         # what the raster cost
                    dW.append(noScenery - noRaster)    # what the walk cost
                pg.evaluate("() => { window.__probe.road.sceneryRaster(true);"
                            " window.__probe.road.layerOff(); }")
                raster.setdefault(place, []).append(median(dR))
                walk.setdefault(place, []).append(median(dW))
        br.close()
    srv.shutdown()

    print()
    print('  WHICH HALF OF THE SCENERY COSTS THE FRAME')
    print('  %d roads, %d pairs of %dms an arm; the hour is pinned at phase %.2f'
          % (args.roads, args.rounds, args.window, args.phase))
    print()
    print('  %-10s %8s %8s   %s' % ('place', 'raster', 'walk', 'road to road, raster / walk'))
    for place in places:
        r, w = raster.get(place, []), walk.get(place, [])
        if not r:
            continue
        print('  %-10s %8.1f %8.1f   %.1f to %.1f / %.1f to %.1f'
              % (place, median(r), median(w), min(r), max(r), min(w), max(w)))

    print()
    print('  WHAT THE WALK DID WITH THE OBJECTS IT PLACED, per frame, middle road')
    print('  %-10s %7s %7s %7s %7s %7s %7s'
          % ('place', 'slices', 'painted', 'lit', 'tiny', 'offside', 'hidden'))
    for place in places:
        c = counts.get(place, [])
        if not c:
            continue
        def mid(k):
            return median([x[k] for x in c])
        print('  %-10s %7d %7d %7d %7d %7d %7d'
              % (place, mid('slices'), mid('objects'), mid('lit'),
                 mid('tiny'), mid('offscreen'), mid('hidden')))
    print()
    print('  tiny, offside and hidden are objects THROWN AWAY AFTER being placed:')
    print('  every hash, every size and every position was computed for them first')
    print()
    print('  AND HOW THE PAINTED AREA IS SPREAD, by how wide the object is drawn.')
    print('  A remedy that drops small objects buys the AREA column, not the count.')
    print('  %-10s %-28s %s' % ('place', 'objects under 2/4/8/16/32/more px',
                                'per cent of the area each'))
    for place in places:
        c = counts.get(place, [])
        if not c or not c[0].get('w'):
            continue
        w = [median([x['w'][i] for x in c]) for i in range(6)]
        a2 = [median([x['a'][i] for x in c]) for i in range(6)]
        tot = sum(a2) or 1
        print('  %-10s %-28s %s'
              % (place, '/'.join('%d' % v for v in w),
                 '/'.join('%.0f%%' % (100.0 * v / tot) for v in a2)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
