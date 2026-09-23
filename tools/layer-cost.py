#!/usr/bin/env python3
"""LAYER COST - what each drawn layer costs a frame, measured against itself.

    .venv/Scripts/python tools/layer-cost.py
    .venv/Scripts/python tools/layer-cost.py --places MOUNTAIN --rounds 4
    .venv/Scripts/python tools/layer-cost.py --layers ground,glass,scenery

IT ASSERTS NOTHING. It is an instrument, not a gate. RLG-299 asks for exactly
this: measure the frame cost before optimising anything, and the standing
suspect - the ground painted from every slice to the bottom of the screen - has
never been measured at all.

HOW IT MEASURES, AND WHY THIS WAY. `wall-cost.py` established the method and the
reason: two fps runs on this machine cannot be compared, because one fps-test run
put MOUNTAIN at 52.0-59.2 and the next at 40.4-50.0 while COASTAL, which had not
been touched, moved with it. So every arm runs INSIDE ONE PAGE on ONE road,
alternating with a baseline arm, and the place, the hour, the weather, the
terrain, the browser and the machine's load are shared and cancel.

AND THE SAMPLES ARE PAIRED, WHICH ONE PAGE ALONE DOES NOT GIVE YOU. The first cut
compared a range of samples with the layer against a range without it, and it
could not see past its own noise: CITY's baseline swung 18.9 to 60.6 fps in a
single run, and the END FACE - a layer that cannot possibly make a frame faster -
came back at minus 3.4. The car is DRIVING, so two samples a few seconds apart
are two different places. Each sample is therefore taken back to back with its
own control, and what is reported is the spread of the DIFFERENCES. Whatever the
terrain, the traffic and the machine were doing, both halves of a pair had it.

`API.layerOff` is the switch. It takes the whole state in one call, so an arm
never inherits what the last arm turned off.

WHY NOT A TIMER ROUND EACH PAINT. A canvas call records into a display list and
the raster happens later, so a timer round `ctx.fill()` measures the recording
and reports nearly nothing for the very thing this is looking for - overdraw.
Taking a layer away moves the raster, and that is what shows.

A COST IS ONLY REAL IF EVERY PAIR AGREES ON ITS SIGN. That is fps-test's rule -
two ranges that overlap are one range - carried onto the paired differences,
where it is far stricter: a layer that costs nothing has half its pairs negative.
The count is printed beside every row for that reason.

THE HOUR IS PINNED AT MIDDAY unless --phase says otherwise. Every number in
RLG-299's table is a midday number, and RLG-168 measured six of seven places
leaving the frame cap at midnight against two at midday - so a night run is a
different measurement, not a better one.
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

# the layers, in the order the frame draws them. The name is the key
# `API.layerOff` takes; the text is what a reader has to be told to understand
# the number beside it.
LAYERS = [
    ('sky',       'the sky, its band and everything in it'),
    ('farground', 'the far field, horizon to the bottom of the frame'),
    ('haze',      'the haze over the far field'),
    ('glass',     'the mirror - a second render of the world'),
    ('ground',    'the verge, painted from EVERY slice to the bottom'),
    ('sea',       'the water beside the road'),
    ('marsh',     'the swamp water beside the road'),
    ('drop',      'the cliff floor beside the road'),
    ('rim',       'the lit lip along the cliff edge'),
    ('wall',      'the canyon and mountain walls'),
    ('face',      'the end face where a place changes'),
    ('range',     'the valley range peaks'),
    ('scenery',   'the roadside objects - trees, rocks, buildings'),
    ('lamp',      'the street lamps and their light'),
    ('road',      'the tarmac quads'),
    ('kerb',      'the kerbs either side'),
    ('lanes',     'the lane markings'),
    ('edges',     'the white lines down each edge'),
    ('rail',      'the guard rails'),
    ('truss',     'the bridge structure'),
    ('joint',     'the deck joints'),
    ('sprites',   'every car, gantry, roadblock and crate'),
    ('beams',     'the headlight cones'),
    ('wash',      'the pursuit wash'),
    ('player',    'the player car'),
    ('rain',      'the precipitation'),
    ('lens',      'the drops on the lens'),
    ('speed',     'the speed lines'),
    ('fx',        'the impact effects'),
    ('vignette',  'the vignette over the finished frame'),
]

# counted from INSIDE the page, on the engine's own animation frames. Counting
# round trips from Python measures the round trips.
COUNT = """(ms) => new Promise(res => {
  let n = 0; const t0 = performance.now();
  (function tick(){ n++;
    if (performance.now() - t0 < ms) requestAnimationFrame(tick);
    else res(n / ((performance.now() - t0) / 1000));
  })();
})"""


def sample(pg, off, window):
    pg.evaluate("(o) => window.__probe.road.layerOff(o)", off)
    return pg.evaluate(COUNT, window)


def median(xs):
    s = sorted(xs)
    n = len(s)
    return s[n//2] if n % 2 else (s[n//2 - 1] + s[n//2]) / 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--places', default='CITY,FOREST,MOUNTAIN,COASTAL')
    ap.add_argument('--layers', default='', help='a comma list; the default is every layer')
    ap.add_argument('--rounds', type=int, default=3)
    ap.add_argument('--window', type=int, default=1600, help='ms a sample')
    ap.add_argument('--phase', type=float, default=0.75,
                    help='0.00 dusk, 0.25 midnight, 0.50 dawn, 0.75 midday')
    ap.add_argument('--speed', type=float, default=0.55, help='fraction of top speed')
    ap.add_argument('--roads', type=int, default=3,
                    help='how many freshly generated roads to drive; NEVER quote one')
    args = ap.parse_args()
    console_utf8()

    want = [x.strip() for x in args.layers.split(',') if x.strip()]
    layers = [l for l in LAYERS if not want or l[0] in want]
    if want:
        known = {l[0] for l in LAYERS}
        for w in want:
            if w not in known:
                print('  no such layer: %s' % w)
                return 2

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

    def drive(pg):
        """open the game and get the car moving. Called once a ROAD, because the
        road is generated at load and a reload is the only way to get another
        one."""
        boot(pg, 'http://127.0.0.1:%d/games/sw/interstate.html' % port)
        until(pg, '!!window.__probe.road', timeout=15000)
        pg.wait_for_selector('#veil:not(.hidden) [data-act="play"]', timeout=15000)
        pg.click('[data-act="play"]')
        pg.wait_for_selector('#veil:not(.hidden) [data-act="drive"]', timeout=8000)
        pg.click('[data-act="drive"]')
        pg.wait_for_timeout(2500)

    with sync_playwright() as p:
        br = launch_chromium(p, headless=True)
        pg = br.new_page(viewport={'width': 480, 'height': 900})
        pg.add_init_script(init)

        print()
        print('  WHAT EACH LAYER COSTS, as frames per second recovered when it is taken away')
        print('  %d roads, %d pairs of %dms a side, alternating; the hour is pinned at phase %.2f'
              % (args.roads, args.rounds, args.window, args.phase))
        print('  A COST IS ONLY REAL IF EVERY PAIR AGREES ON ITS SIGN')

        # ---- AND IT IS MEASURED ON SEVERAL ROADS (RLG-299) ----------------
        # The road is generated fresh at every load, so a MOUNTAIN with a cliff
        # beside it and a MOUNTAIN without one are two different measurements of
        # the same place name. The first version drove ONE road and reported the
        # cliff floor at 16.0 fps; the next load put the same layer at 1.1,
        # because that road had barely any cliff. Neither number was wrong.
        #
        # `occlusion-test.py` carries this warning already and was given the same
        # treatment for the same reason: its cull count swung 0, 40 and 147 on
        # one unchanged build. NEVER QUOTE ONE ROAD.
        per_place = {}
        for road in range(args.roads):
            drive(pg)
            for place in [x.strip() for x in args.places.split(',') if x.strip()]:
                pg.evaluate("(k) => window.__probe.road.setBiomePair(k,k)", place)
                pg.wait_for_timeout(600)
                rows = per_place.setdefault(place, {})
                base_all = rows.setdefault('__base', [])
                for name, what in layers:
                    # ---- PAIRED, AND THAT IS THE WHOLE OF THE METHOD -------------
                    # The first cut of this took several samples with the layer and
                    # several without, and compared the two ranges. It could not see
                    # past its own noise: CITY's baseline swung 18.9 to 60.6 fps in
                    # one run, and the END FACE - which cannot make a frame faster -
                    # came back at minus 3.4. The road moves under the measurement,
                    # so two samples a few seconds apart are two different places.
                    #
                    # So each sample is PAIRED with the one beside it, on and off
                    # back to back, and what is reported is the spread of the
                    # DIFFERENCES. Whatever the terrain, the traffic and the machine
                    # were doing, both halves of a pair had it.
                    ds, on_all = [], []
                    for _ in range(args.rounds):
                        pg.evaluate("(v) => window.__probe.road.setSpd(window.__probe.road.MAX_SPD*v)",
                                    args.speed)
                        pg.evaluate("(v) => window.__probe.road.setPhase(v)", args.phase)
                        withIt = sample(pg, {}, args.window)
                        pg.evaluate("(v) => window.__probe.road.setSpd(window.__probe.road.MAX_SPD*v)",
                                    args.speed)
                        pg.evaluate("(v) => window.__probe.road.setPhase(v)", args.phase)
                        without = sample(pg, {name: 1}, args.window)
                        ds.append(without - withIt)
                        on_all.append(withIt)
                    pg.evaluate("() => window.__probe.road.layerOff()")
                    base_all += on_all
                    rows.setdefault(name, []).append((median(ds), ds))

        # ---- what every road agreed on -----------------------------------
        for place in [x.strip() for x in args.places.split(',') if x.strip()]:
            rows = per_place.get(place, {})
            base_all = rows.get('__base', [0])
            table = []
            for name, what in layers:
                got = rows.get(name, [])
                if not got:
                    continue
                meds = [m for m, _ in got]
                every = [d for _, ds in got for d in ds]
                up = sum(1 for d in every if d > 0)
                table.append((name, what, median(meds), min(meds), max(meds), up, len(every)))
            table.sort(key=lambda r: -r[2])
            print()
            print('  %s   baseline %.1f - %.1f fps over %d roads'
                  % (place, min(base_all), max(base_all), args.roads))
            print('  %-10s %8s %17s %7s  %s' % ('layer', 'gain', 'road to road', 'up', ''))
            for name, what, med, lo, hi, up, n in table:
                sure = ' ' if lo > 0 else ('.' if up * 2 > n else '?')
                print('  %-10s %7.1f%s %7.1f - %7.1f %4d/%d  %s'
                      % (name, med, sure, lo, hi, up, n, what))
            print('  the gain is the MIDDLE ROAD; the spread beside it is road to road, not sample to sample')
            print('  a blank is a layer that cost something on EVERY road; . is most pairs; ? is neither')
        br.close()
    srv.shutdown()
    return 0


if __name__ == '__main__':
    sys.exit(main())
