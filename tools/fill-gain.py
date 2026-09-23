#!/usr/bin/env python3
"""GROUND GAIN - what tiling the ground bought, measured against the old fill.

    .venv/Scripts/python tools/ground-gain.py

IT ASSERTS NOTHING. It is an instrument, not a gate.

`layer-cost.py` says what the ground COSTS by taking it away, which is the
measurement that chose this work. This says what the CHANGE bought, by putting
the old fill back: `API.groundFull` paints every slice to the bottom of the
screen again, without a reload, so both arms run on one road in one page and the
place, the hour, the weather, the terrain and the machine's load cancel.

The samples are paired - old and new back to back - for the reason recorded in
`layer-cost.py`: this machine's baseline swung 18.9 to 60.6 fps inside one run,
and unpaired samples could not see past it. Several roads, because the road is
generated fresh at every load and one road is not a measurement.
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
    s = sorted(xs)
    n = len(s)
    return s[n//2] if n % 2 else (s[n//2 - 1] + s[n//2]) / 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--places', default='CITY,FOREST,MOUNTAIN,COASTAL,DESERT,TUNDRA,SWAMP')
    # one instrument for the three fills, the same way one proof covers them
    ap.add_argument('--fill', default='ground', choices=('ground', 'water', 'cliff'))
    ap.add_argument('--roads', type=int, default=3)
    ap.add_argument('--rounds', type=int, default=4)
    ap.add_argument('--window', type=int, default=800)
    ap.add_argument('--phase', type=float, default=0.75)
    ap.add_argument('--speed', type=float, default=0.55)
    args = ap.parse_args()
    switch = {'ground': 'groundFull', 'water': 'waterFull', 'cliff': 'floorFull'}[args.fill]
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
    got = {}
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
                pg.wait_for_timeout(600)
                ds = []
                for _ in range(args.rounds):
                    for full in (True, False):
                        pg.evaluate("(v) => window.__probe.road.setSpd(window.__probe.road.MAX_SPD*v)",
                                    args.speed)
                        pg.evaluate("(v) => window.__probe.road.setPhase(v)", args.phase)
                        pg.evaluate("([s, v]) => window.__probe.road[s](v)", [switch, full])
                        fps = pg.evaluate(COUNT, args.window)
                        if full:
                            old = fps
                        else:
                            ds.append(fps - old)
                pg.evaluate("(s) => window.__probe.road[s](false)", switch)
                got.setdefault(place, []).append(median(ds))
        br.close()
    srv.shutdown()

    print()
    print('  WHAT TILING THE %s BOUGHT, in frames per second' % args.fill.upper())
    print('  %d roads, %d pairs of %dms a side; each pair is the old fill then the new'
          % (args.roads, args.rounds, args.window))
    print()
    print('  %-10s %8s   %s' % ('place', 'gain', 'road to road'))
    for place in places:
        v = got.get(place, [])
        if not v:
            continue
        print('  %-10s %8.1f   %.1f to %.1f' % (place, median(v), min(v), max(v)))
    print()
    if args.fill == 'ground':
        print('  the ground beside a cliff is tiled too since 0.14.133, which is what')
        print('  took a MOUNTAIN from 0.7 fps to 6.8 - see the note at the fill')
    elif args.fill == 'water':
        print('  only a COASTAL and a SWAMP have water beside the road; the rest are')
        print('  the control, and are expected to show nothing at all')
    else:
        print('  only a place with a hazard side has a cliff floor; the rest are the')
        print('  control, and are expected to show nothing at all')
    return 0


if __name__ == '__main__':
    sys.exit(main())
